"""Dataset integrity checks (``wlmem verify-data``).

Checks that the pinned files are present, unmodified and have the size and structure the
papers describe, and reports known data quirks. It never changes any file.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from typing import Any

from .benchmarks.base import check_official_checkout, data_file, lock, repo_dir, sha256_file


def _check(cond: bool, msg: str, out: list[str]) -> bool:
    out.append(("[OK]   " if cond else "[FAIL] ") + msg)
    return cond


def verify_stale(lines: list[str]) -> bool:
    spec = lock()["datasets"]["stale"]["files"]["T1_T2_400_FULL.json"]
    p = data_file("stale", "T1_T2_400_FULL.json")
    ok = _check(sha256_file(p) == spec["sha256"], f"STALE file sha256 matches lock ({spec['sha256'][:12]}...)", lines)
    with open(p, encoding="utf-8") as f:
        recs = json.load(f)
    ok &= _check(len(recs) == 400, f"STALE 400 records (found {len(recs)})", lines)
    types = Counter(r["type"] for r in recs)
    ok &= _check(types == Counter({"T1": 200, "T2": 200}), f"STALE 200 T1 + 200 T2 (found {dict(types)})", lines)
    ok &= _check(len({r["uid"] for r in recs}) == 400, "STALE uids unique", lines)
    ok &= _check(all(len(r["timestamps"]) == len(r["haystack_session"]) for r in recs), "STALE one timestamp per session", lines)
    fmt = "%Y-%m-%d %H:%M"
    ok &= _check(all([datetime.strptime(t, fmt) for t in r["timestamps"]] == sorted(datetime.strptime(t, fmt) for t in r["timestamps"]) for r in recs),
                 "STALE sessions in chronological order", lines)
    ok &= _check(all(set(r["probing_queries"]) == {"dim1_query", "dim2_query", "dim3_query"} for r in recs), "STALE three probing queries per case", lines)
    keys = {k for r in recs for s in r["haystack_session"] for t in s for k in t}
    ok &= _check(keys == {"role", "content"}, f"STALE turn fields only role/content (found {sorted(keys)})", lines)
    n = sorted(len(r["haystack_session"]) for r in recs)
    lines.append(f"[INFO] STALE sessions per case min/median/max {n[0]}/{n[len(n)//2]}/{n[-1]}")
    return ok


def verify_longmemeval(lines: list[str]) -> bool:
    ok = True
    fmt = "%Y/%m/%d (%a) %H:%M"
    for fname, spec in lock()["datasets"]["longmemeval"]["files"].items():
        p = data_file("longmemeval", fname)
        ok &= _check(sha256_file(p) == spec["sha256"], f"LongMemEval {fname} sha256 matches lock", lines)
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        ok &= _check(len(d) == 500, f"{fname}: 500 questions (found {len(d)})", lines)
        types = Counter(x["question_type"] for x in d)
        lines.append(f"[INFO] {fname}: types {dict(types)}; abstention {sum(x['question_id'].endswith('_abs') for x in d)}")
        has_ans = sum(1 for x in d for s in x["haystack_sessions"] for t in s if "has_answer" in t)
        lines.append(f"[INFO] {fname}: {has_ans} turns carry the gold field has_answer (stripped by the loader)")
        late = late_ev = unsorted = 0
        for x in d:
            q = datetime.strptime(x["question_date"], fmt)
            ds = [datetime.strptime(t, fmt) for t in x["haystack_dates"]]
            unsorted += ds != sorted(ds)
            for sid, dt in zip(x["haystack_session_ids"], ds):
                if dt > q:
                    late += 1
                    late_ev += sid in x["answer_session_ids"]
        lines.append(f"[INFO] {fname}: {unsorted} questions with sessions not in time order (loader sorts them)")
        lines.append(f"[INFO] {fname}: {late} sessions dated after their question, {late_ev} of them evidence sessions "
                     f"(kept by default, see exclude_future_sessions)")
    return ok


def verify_memora(lines: list[str]) -> bool:
    import hashlib

    info = check_official_checkout("memora")
    lines.append(f"[OK]   Memora checkout at pinned commit {info['commit'][:12]}")
    spec = lock()["repos"]["memora"]
    data_dir = repo_dir("memora") / "data"
    h = hashlib.sha256()
    files = sorted(p for p in data_dir.rglob("*.json") if "eval_results" not in p.parts)
    for p in files:
        h.update(p.relative_to(data_dir).as_posix().encode())
        h.update(bytes.fromhex(sha256_file(p)))
    ok = _check(h.hexdigest() == spec["data_tree_sha256"] and len(files) == spec["data_file_count"],
                f"Memora data tree hash matches lock ({len(files)} files)", lines)
    expect = {"weekly": 15, "monthly": 15, "quarterly": 30}
    for period, nq in expect.items():
        personas = sorted(x.name for x in (data_dir / period).iterdir() if x.is_dir())
        ok &= _check(len(personas) == 10, f"Memora {period}: 10 personas", lines)
        bad_q = late = 0
        sizes = []
        for persona in personas:
            with open(data_dir / period / persona / f"evaluation_questions_{persona}.json", encoding="utf-8") as f:
                qs = json.load(f)["questions"]
            n = sum(len(v) for v in qs.values())
            bad_q += n != nq
            dates = []
            for s in (data_dir / period / persona / "conversations").glob("session_*.json"):
                with open(s, encoding="utf-8") as f:
                    dates.append(json.load(f)["date"])
            sizes.append(len(dates))
            last = max(dates)
            late += sum(1 for v in qs.values() for q in v if q["question_date"] < last)
        ok &= _check(bad_q == 0, f"Memora {period}: {nq} questions per persona", lines)
        ok &= _check(late == 0, f"Memora {period}: no session dated after any question", lines)
        lines.append(f"[INFO] Memora {period}: sessions per persona {min(sizes)}-{max(sizes)}")
    return ok


def verify(names: list[str] | None = None) -> bool:
    checks = {"stale": verify_stale, "longmemeval": verify_longmemeval, "memora": verify_memora}
    ok = True
    for name, fn in checks.items():
        if names and name not in names:
            continue
        lines: list[str] = []
        try:
            ok &= fn(lines)
        except Exception as e:
            lines.append(f"[FAIL] {name}: {e!r}")
            ok = False
        print("\n".join(lines))
    print("DATA OK" if ok else "DATA CHECK FAILED")
    return ok

