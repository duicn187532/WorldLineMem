"""Experiment B: when Pragma's Curator is offered the old memory during the new-evidence
session, does the model select it?

Context: docs/DIAGNOSTICS.md §1.6 and docs/DECISION_GATES.md (Gate B). Pragma (Santi 2026,
KBS 353:117193; source @e53eace) curates on every user turn from active AND dormant
episodes and revives what the model selects; post-session reconsolidation then re-reads the
three most similar ACTIVE episodes. So whether reinterpretation can reach the old evidence
m_o depends on one model judgement this script measures.

For each sampled STALE case (old evidence o, new evidence n; gold indices used ONLY to score):

  1. CONSOLIDATE sessions 0..n with Pragma's own consolidation prompt (one call per session,
     cached across cases). Salience from Pragma's Eq. (3); effective salience with Pragma's
     half-life, "now" = timestamp of session n; dormant below Pragma's threshold.
     Not simulated: Curator recalls during sessions 0..n-1 (they would reinforce and reset
     clocks), beliefs, reconsolidation of earlier sessions.
  2. For every user turn of session n, in order: Pragma's keyword prefilter (10 candidates,
     3 of them the latest; episodes already on the desk excluded), Pragma's episode cards and
     Curator prompt, one model call. Pragma's parse rules: valid refs, deduped, cap 6; on a
     failed call Pragma falls back to the first 6 candidates (recorded as `fallback`).
  3. Reconsolidation reach: is m_o among the 3 past episodes sharing >=2 words with the new
     episode (Pragma's keyword path), counting m_o as active only if it was not dormant or
     was selected (revived) in step 2.

Pragma's prompts, tokenizer and constants are read from a local checkout at run time
(AGPL-3.0; nothing is copied into this repository). Prompts are English and describe "an
AI coding agent" - that is Pragma's wording and is kept.

Model calls go through the same Ollama client as the rest of the framework. Prompts ask for
JSON via Ollama's `format: json` (Pragma enforces a JSON schema on llama.cpp; close, not
identical). Label results "Local Adaptation".

    python scripts/measure_pragma_curator.py configs/local/pragma_curator.toml --pragma <checkout>
    python scripts/measure_pragma_curator.py <config> --pragma <checkout> --sample 100 --seed 0

Resumable: finished cases in <out>/cases.jsonl are skipped; consolidations are cached in
<out>/episodes.jsonl keyed by model and transcript.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import re
import subprocess
import sys
import time
import tomllib
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from wlmem.backends import make_chat  # noqa: E402
from wlmem.benchmarks import make_benchmark  # noqa: E402
from wlmem.memory.decay import days_between, parse_time  # noqa: E402

PRAGMA_REVISION = "e53eace"


# ── Pragma pieces, read from the checkout ───────────────────────────────────────────────

def _first_str(node: ast.AST) -> str:
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str) and len(sub.value) > 200:
            return sub.value
    raise ValueError("no prompt string found")


def _assigned(tree: ast.Module, name: str) -> ast.AST:
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return node.value
    raise KeyError(name)


def _config_default(src: str, name: str) -> float:
    m = re.search(rf'^{name}\s*=\s*\w+\(\s*os\.environ\.get\(\s*"{name}"\s*,\s*"([^"]+)"', src, re.M)
    if not m:
        raise KeyError(f"{name} not found in Pragma config.py")
    return float(m.group(1))


class Pragma:
    def __init__(self, root: Path):
        core = root / "core"
        cfg = (core / "config.py").read_text(encoding="utf-8")
        c = {k: _config_default(cfg, k) for k in (
            "CURATOR_CANDIDATES_EPISODES", "CURATOR_CANDIDATES_RECENT", "CURATOR_MAX_FRAGMENTS",
            "MEMORY_NARRATIVE_CHARS", "MEMORY_INTERPRETATION_CHARS", "EPISODE_DECAY_HALF_LIFE_DAYS",
            "EPISODE_DORMANT_THRESHOLD", "SALIENCE_BASE", "SALIENCE_SURPRISE_WEIGHT",
            "SALIENCE_IMPORTANCE_WEIGHT", "SALIENCE_CAP")}
        self.const = c
        cur_src = (core / "curator.py").read_text(encoding="utf-8")
        self.curator_system = ast.literal_eval(_assigned(ast.parse(cur_src), "_CURATOR_SYSTEM"))
        ns: dict = {"re": re}
        exec(cur_src[cur_src.index("_WORD = re.compile"):cur_src.index("def _terms")], ns)
        self.tokens = ns["_tokens"]
        tool_src = (core / "tools" / "episode_consolidate" / "tool.py").read_text(encoding="utf-8")
        self.episode_system = (_first_str(_assigned(ast.parse(tool_src), "_EPISODE_SYSTEM"))
                               .replace("NAR_CHARS", str(int(c["MEMORY_NARRATIVE_CHARS"])))
                               .replace("INT_CHARS", str(int(c["MEMORY_INTERPRETATION_CHARS"]))))
        try:
            self.revision = subprocess.run(["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
                                           capture_output=True, text=True, check=True).stdout.strip()
        except Exception:
            self.revision = "unknown"

    # episodes.effective_salience
    def effective(self, salience: float, age_days: float) -> float:
        half = self.const["EPISODE_DECAY_HALF_LIFE_DAYS"]
        return salience if half <= 0 else salience * 0.5 ** (age_days / half)

    # episode_consolidate Eq. (3)
    def salience(self, ep: dict) -> float:
        c = self.const
        return min(c["SALIENCE_CAP"], c["SALIENCE_BASE"] + c["SALIENCE_SURPRISE_WEIGHT"] * len(ep["surprises"])
                   + c["SALIENCE_IMPORTANCE_WEIGHT"] * ep["importance"])


def extract_json(raw: str):
    """Pragma's json_parser.extract_json, reduced: the outermost {...} of the reply."""
    raw = re.sub(r"<think>.*?</think>", "", raw or "", flags=re.S)
    i, j = raw.find("{"), raw.rfind("}")
    if i < 0 or j <= i:
        return None
    try:
        return json.loads(raw[i:j + 1])
    except json.JSONDecodeError:
        return None


def _text(v) -> str:
    return v if isinstance(v, str) else "" if v is None else str(v)


def _list(v) -> list[str]:
    return [str(x).strip() for x in v if str(x).strip()] if isinstance(v, list) else []


def _placeholder(s: str) -> bool:
    return not s or set(s.strip()) <= set(".… ")


# ── Consolidation (cached) ──────────────────────────────────────────────────────────────

class Consolidator:
    def __init__(self, pragma: Pragma, chat, cache: Path, max_tokens: int):
        self.p, self.chat, self.cache, self.max_tokens = pragma, chat, cache, max_tokens
        self.memo: dict[str, dict] = {}
        if cache.exists():
            for line in cache.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    r = json.loads(line)
                    self.memo[r["key"]] = r["episode"]
        self.calls = 0

    def __call__(self, transcript: str) -> dict:
        key = hashlib.sha256(f"{self.chat.model}\n{self.p.revision}\n{transcript}".encode()).hexdigest()
        if key in self.memo:
            return self.memo[key]
        data, err = None, ""
        for note in ("", "\n\n[IMPORTANT: your previous reply was cut off before any JSON appeared — too much "
                         "thinking out loud. Reply with ONLY the JSON object: the character '{' must be the "
                         "FIRST character of your reply. No preamble, no reasoning narration.]"):
            try:
                r = self.chat.chat([{"role": "system", "content": self.p.episode_system},
                                    {"role": "user", "content": f"Session transcript:\n\n{transcript}{note}"}],
                                   json_mode=True, max_tokens=self.max_tokens)
                self.calls += 1
                data = extract_json(r.text)
                if isinstance(data, dict):
                    break
            except Exception as e:  # noqa: BLE001 - recorded, as Pragma does
                err = f"{type(e).__name__}: {str(e)[:120]}"
        data = data if isinstance(data, dict) else {}
        goal, narrative = _text(data.get("goal")).strip(), _text(data.get("narrative")).strip()
        degraded = _placeholder(goal) or _placeholder(narrative)
        if degraded:  # Pragma's minimal deterministic episode
            first_user = next((ln[5:].strip() for ln in transcript.splitlines() if ln.startswith("USER:")), "")
            goal, narrative, data = (first_user or "unlabeled session")[:200], transcript[:800], {}
        try:
            importance = max(0.0, min(1.0, float(data.get("importance", 0.4))))
        except (TypeError, ValueError):
            importance = 0.4
        interp = _text(data.get("interpretation")).strip()
        ep = {"goal": goal, "narrative": narrative, "interpretation": "" if _placeholder(interp) else interp,
              "surprises": [s[:300] for s in _list(data.get("surprises"))],
              "keywords": [k.lower() for k in _list(data.get("keywords"))][:12],
              "importance": importance, "degraded": degraded, "error": err}
        self.memo[key] = ep
        with open(self.cache, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"key": key, "episode": ep}, ensure_ascii=False) + "\n")
        return ep


def transcript_of(session) -> str:
    return "\n".join(f"{'USER' if t.role == 'user' else 'ASSISTANT'}: {t.content}" for t in session.turns)


# ── Curator ─────────────────────────────────────────────────────────────────────────────

def episode_text(ep: dict) -> str:  # curator._episode_text
    return " ".join([ep["goal"], " ".join(ep["keywords"]), ep["narrative"], " ".join(ep["surprises"])])


def when(ts: datetime | None, today: datetime | None) -> str:  # curator._when
    if ts is None or today is None:
        return ""
    days = (today.date() - ts.date()).days
    if days < 0:
        return ts.strftime("%Y-%m-%d")
    return "today" if days == 0 else "yesterday" if days == 1 else f"{days} days ago" if days < 14 \
        else ts.strftime("%Y-%m-%d")


def truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit].rstrip() + "..."


def card(p: Pragma, ref: str, ep: dict, dormant: bool, ts, today) -> str:  # curator._episode_card
    stamp = when(ts, today)
    lines = [f"{ref}{' [dormant]' if dormant else ''}{f' ({stamp})' if stamp else ''} goal: {ep['goal']}"]
    nar = truncate(ep["narrative"], int(p.const["MEMORY_NARRATIVE_CHARS"]))
    if nar:
        lines.append(f"   what happened: {nar}")
    if ep["surprises"]:
        lines.append(f"   surprises: {'; '.join(ep['surprises'][:2])}")
    interp = truncate(ep["interpretation"], int(p.const["MEMORY_INTERPRETATION_CHARS"]))
    if interp:
        lines.append(f"   meaning: {interp}")
    return "\n".join(lines)


def candidates(p: Pragma, task: str, past: list[int], eps: list[dict], eff: list[float],
               stamps: list[str], skip: set[int]) -> list[int]:
    """curator._episode_candidates, keyword path (no embedding server), no date seats."""
    n, recent = int(p.const["CURATOR_CANDIDATES_EPISODES"]), int(p.const["CURATOR_CANDIDATES_RECENT"])
    q = p.tokens(task)
    pool = [j for j in past if j not in skip]
    kw = {j: len(p.tokens(episode_text(eps[j])) & q) for j in pool}
    by_ts = sorted(pool, key=lambda j: (stamps[j], j), reverse=True)
    matched = [j for j in pool if kw[j] > 0]
    if not matched:
        return by_ts[:n]
    matched.sort(key=lambda j: (kw[j], eff[j], stamps[j]), reverse=True)
    out = matched[:max(n - recent, 0)]
    for j in by_ts:
        if len(out) >= n:
            break
        if j not in out:
            out.append(j)
    return out


def ask_curator(p: Pragma, chat, task: str, cards: list[str], today, max_tokens: int):
    payload = f"TODAY: {today.strftime('%Y-%m-%d') if today else ''}\n\nTASK:\n{task}\n\nCANDIDATES:\n" \
              + "\n".join(cards)
    try:
        r = chat.chat([{"role": "system", "content": p.curator_system}, {"role": "user", "content": payload}],
                      json_mode=True, max_tokens=max_tokens)
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {str(e)[:160]}", {}
    data = extract_json(r.text)
    if not isinstance(data, dict):
        return None, "reply was not JSON: " + " ".join(r.text.split())[:120], {}
    sel = data.get("selected", [])
    if not isinstance(sel, list):
        return [], _text(data.get("reason")), {}
    uses = {}
    if isinstance(data.get("uses"), list):
        for ref, u in zip(sel, data["uses"]):
            if str(u).strip().lower() in ("substantive", "procedural"):
                uses[str(ref).strip().upper()] = str(u).strip().lower()
    valid = {f"E{i}" for i in range(1, len(cards) + 1)}
    out: list[str] = []
    for ref in sel:
        ref = str(ref).strip().upper()
        if ref in valid and ref not in out:
            out.append(ref)
        if len(out) >= int(p.const["CURATOR_MAX_FRAGMENTS"]):
            break
    return out, _text(data.get("reason")), {r: u for r, u in uses.items() if r in out}


# ── One case ────────────────────────────────────────────────────────────────────────────

def run_case(p: Pragma, chat, consolidate: Consolidator, case, max_tokens: int) -> dict:
    o, n = case.gold["relevant_session_index"][:2]
    sessions = case.sessions[:n + 1]
    eps = [consolidate(transcript_of(s)) for s in sessions]
    today = parse_time(sessions[n].timestamp)
    stamps = [s.timestamp or "" for s in sessions]
    times = [parse_time(s.timestamp) for s in sessions]
    eff = [p.effective(p.salience(ep), days_between(times[j], today)) for j, ep in enumerate(eps)]
    thr = p.const["EPISODE_DORMANT_THRESHOLD"]
    past = list(range(n))
    dormant = {j for j in past if eff[j] < thr}
    desk: set[int] = set()
    turns, selected_o, offered_o = [], False, False
    for t_i, turn in enumerate(t for t in sessions[n].turns if t.role == "user"):
        cand = candidates(p, turn.content, past, eps, eff, stamps, desk)
        cards = [card(p, f"E{i}", eps[j], j in dormant, times[j], today) for i, j in enumerate(cand, 1)]
        refs, reason, uses = ask_curator(p, chat, turn.content, cards, today, max_tokens) if cand else ([], "", {})
        fallback = refs is None
        if fallback:  # curator._fallback
            refs = [f"E{i}" for i in range(1, len(cand) + 1)][:int(p.const["CURATOR_MAX_FRAGMENTS"])]
        chosen = [cand[int(r[1:]) - 1] for r in refs]
        in_cand = o in cand
        o_was_dormant = o in dormant
        offered_o |= in_cand
        picked = o in chosen
        selected_o |= picked
        for j in chosen:
            desk.add(j)
            dormant.discard(j)  # revived
        turns.append({"turn": t_i, "offered": in_cand, "rank": cand.index(o) + 1 if in_cand else 0,
                      "o_dormant_tag": in_cand and o_was_dormant,
                      "selected": picked, "use": uses.get(f"E{cand.index(o) + 1}") if picked else None,
                      "n_candidates": len(cand), "n_selected": len(chosen), "fallback": fallback,
                      "reason": reason})
    # reconsolidation targets after the session (keyword path, >=2 shared words, top 3 active)
    q = p.tokens(episode_text(eps[n]))
    active = [j for j in past if j not in dormant]
    sim = sorted(((j, len(p.tokens(episode_text(eps[j])) & q)) for j in active), key=lambda t: t[1], reverse=True)
    targets = [j for j, s in sim if s >= 2][:3]
    return {"uid": case.case_id, "type": case.gold["type"], "o": o, "n": n,
            "o_dormant_at_n": eff[o] < thr, "o_eff_salience": round(eff[o], 4),
            "offered_any": offered_o, "selected_any": selected_o,
            "selected_any_model_only": any(t["selected"] and not t["fallback"] for t in turns),
            "reach": o in targets, "turns": turns,
            "degraded_episodes": sum(ep["degraded"] for ep in eps)}


def summarize(rows: list[dict]) -> dict:
    def rate(num, den):
        return {"k": num, "n": den, "rate": round(num / den, 4) if den else None,
                "wilson95": wilson(num, den)}
    offered = [r for r in rows if r["offered_any"]]
    turns = [t for r in rows for t in r["turns"]]
    off_t = [t for t in turns if t["offered"]]
    return {
        "cases": len(rows),
        "B1_select_given_offered_case": rate(sum(r["selected_any_model_only"] for r in offered), len(offered)),
        "B1_as_deployed_incl_fallback": rate(sum(r["selected_any"] for r in offered), len(offered)),
        "B2_reach": rate(sum(r["reach"] for r in rows), len(rows)),
        "offered_any": rate(len(offered), len(rows)),
        "o_dormant_at_n": rate(sum(r["o_dormant_at_n"] for r in rows), len(rows)),
        "select_given_offered_turn": rate(sum(t["selected"] and not t["fallback"] for t in off_t),
                                          sum(not t["fallback"] for t in off_t)),
        "select_given_offered_dormant_tag": rate(
            sum(t["selected"] for t in off_t if t["o_dormant_tag"] and not t["fallback"]),
            sum(1 for t in off_t if t["o_dormant_tag"] and not t["fallback"])),
        "use_labels_when_selected": {u: sum(t["use"] == u for t in turns if t["selected"])
                                     for u in ("substantive", "procedural", None)},
        "curator_fallback_turns": rate(sum(t["fallback"] for t in turns), len(turns)),
        "degraded_episode_share": round(sum(r["degraded_episodes"] for r in rows)
                                        / max(1, sum(r["n"] + 1 for r in rows)), 4),
    }


def wilson(k: int, n: int, z: float = 1.96):
    if not n:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(c - h, 4), round(c + h, 4)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("config")
    ap.add_argument("--pragma", required=True, type=Path)
    ap.add_argument("--sample", type=int, default=None, help="number of cases; default all 400")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    cfg = tomllib.loads(Path(args.config).read_text(encoding="utf-8"))
    p = Pragma(args.pragma)
    if p.revision != PRAGMA_REVISION:
        print(f"WARNING: Pragma checkout is {p.revision}, this script was written against {PRAGMA_REVISION}")
    model_cfg = dict(cfg["memory_model"])
    max_tokens = int(model_cfg.pop("max_tokens", 2048))
    chat = make_chat(model_cfg)
    out = Path(args.out or f"runs/diagnostics/pragma_curator_llm/{cfg['run']['name']}")
    out.mkdir(parents=True, exist_ok=True)
    consolidate = Consolidator(p, chat, out / "episodes.jsonl", max_tokens)
    cases = sorted(make_benchmark("stale", {}).cases(),
                   key=lambda c: hashlib.sha256(f"{args.seed}:{c.case_id}".encode()).hexdigest())
    if args.sample:
        cases = cases[:args.sample]
    done_file = out / "cases.jsonl"
    rows = [json.loads(x) for x in done_file.read_text(encoding="utf-8").splitlines() if x.strip()] \
        if done_file.exists() else []
    done = {r["uid"] for r in rows}
    meta = {"pragma_revision": p.revision, "pragma_constants": p.const, "sample": args.sample, "seed": args.seed,
            "model": chat.describe() if hasattr(chat, "describe") else str(model_cfg),
            "label": cfg["run"].get("label", "local_adaptation"), "case_ids": [c.case_id for c in cases]}
    (out / "manifest.json").write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")
    t0 = time.time()
    for i, case in enumerate(cases, 1):
        if case.case_id in done:
            continue
        row = run_case(p, chat, consolidate, case, max_tokens)
        rows.append(row)
        with open(done_file, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"[{i}/{len(cases)}] {case.case_id} offered={row['offered_any']} selected={row['selected_any']} "
              f"reach={row['reach']} ({time.time() - t0:.0f}s, consolidation calls {consolidate.calls})", flush=True)
    rows = [r for r in rows if r["uid"] in set(meta["case_ids"])]
    summary = summarize(rows)
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
