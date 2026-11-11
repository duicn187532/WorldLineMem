"""Retrieval-level diagnostic: how does time decay interact with stale-memory revision on STALE?

No language model is called; every number is deterministic. The gold field
``relevant_session_index`` (old evidence m_o, new evidence m_n) is used ONLY to score which
units were retrieved; memory construction never sees it.

For every STALE case and every decay configuration it measures

  write time   just before m_n is ingested, memory holds sessions 0..n-1. The user turns of
               session n are used as the query, "now" = timestamp of session n. This is the
               moment a write-time adjudicator (CUPMem, StateGraph, Pragma reconsolidation)
               must find the old memory in order to revise it.
                 old_hit@k        a unit of m_o is among the top-k
                 old_dormant      every unit of m_o has strength < dormant threshold
                                  (Pragma-style stores exclude such units from re-reading)
  query time   all 50 sessions ingested, "now" = last timestamp, one query per probe (dim1-3)
                 new_hit@k, old_hit@k
                 new_rank         best rank of an m_n unit (1-based; 0 = not retrievable)

Decay curves (memory/decay.py, FadeMem eq. 4-6 only; mu and importance unknown, set to 0):
  none, fademem_sml (lambda 0.1, beta 1.2), fademem_lml (lambda 0.1, beta 0.8),
  halflife30 (exponential, 30-day half-life as Pragma's default), each ranked by relevance x
  strength; plus dormant variants that drop units below a strength threshold; and
  pragma_revive, where dormancy applies at write time only and question-time recall can
  revive any unit (Pragma's split between re-reading and recall).

    python scripts/diagnose_stale_decay.py --out runs/diagnostics/stale_decay
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from wlmem.benchmarks import make_benchmark  # noqa: E402
from wlmem.memory import Services, make_memory  # noqa: E402
from wlmem.memory.decay import DecayCurve, days_between, parse_time  # noqa: E402

LN2 = math.log(2)
CONFIGS = {
    "none":                (None, "multiply", None),
    "fademem_sml":         (DecayCurve(0.1, 1.2), "multiply", None),
    "fademem_lml":         (DecayCurve(0.1, 0.8), "multiply", None),
    "halflife30":          (DecayCurve(LN2 / 30, 1.0), "multiply", None),
    "fademem_lml_dormant": (DecayCurve(0.1, 0.8), "dormant", 0.15),
    # Pragma defaults: half-life 30 days on effective salience, dormant below 0.15; a new
    # episode's salience is set by the consolidator, 0.5 is used here as a neutral value
    "pragma_dormant":      (DecayCurve(LN2 / 30, 1.0, initial=0.5), "dormant", 0.15),
    # Closer to Pragma's actual split (core/tools/episode_consolidate/tool.py and core/curator.py
    # @e53eace): re-reading at write time sees ACTIVE episodes only, while recall at question
    # time searches active AND dormant episodes and revives what it selects.
    "pragma_revive":       (DecayCurve(LN2 / 30, 1.0, initial=0.5), "dormant", 0.15),
}
# configurations whose question-time retrieval ignores dormancy (revival on match)
REVIVE_AT_QUERY = {"pragma_revive"}
KS = (5, 10, 20)


def build(sessions):
    m = make_memory("rag", Services(), {"granularity": "round", "retriever": "bm25"})
    m.reset()
    for s in sessions:
        m.ingest(s)
    return m


def ranked(m, query_text, now, curve, mode, thr):
    raw = np.asarray(m.bm25.scores(query_text), dtype=float)
    sessions = [u.session.session_id for u in m.units]
    if curve is None:
        strength = np.ones(len(raw))
    else:
        strength = np.asarray([curve.strength(days_between(parse_time(u.session.timestamp), now)) for u in m.units])
    score = raw * strength if mode == "multiply" else np.where(strength >= thr, raw, -np.inf)
    order = [int(i) for i in np.argsort(-score, kind="stable") if np.isfinite(score[i])]
    return order, sessions, strength


def first_rank(order, sessions, sid):
    for r, i in enumerate(order, 1):
        if sessions[i] == sid:
            return r
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="runs/diagnostics/stale_decay")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    bench = make_benchmark("stale", {"limit": args.limit} if args.limit else {})
    rows = []
    t0 = time.time()
    for case in bench.cases():
        o, n = case.gold["relevant_session_index"][:2]
        sid_o, sid_n = case.sessions[o].session_id, case.sessions[n].session_id
        t_n = parse_time(case.sessions[n].timestamp)
        before = build(case.sessions[:n])
        full = build(case.sessions)
        probe = " ".join(t.content for t in case.sessions[n].turns if t.role == "user")
        row = {"uid": case.case_id, "type": case.gold["type"], "o": o, "n": n,
               "days_o_to_n": days_between(parse_time(case.sessions[o].timestamp), t_n),
               "days_n_to_query": days_between(t_n, parse_time(case.queries[0].asked_at)), "cfg": {}}
        for name, (curve, mode, thr) in CONFIGS.items():
            order, sess, strength = ranked(before, probe, t_n, curve, mode, thr)
            old_units = [i for i, s in enumerate(sess) if s == sid_o]
            r_old_w = first_rank(order, sess, sid_o)
            res = {"write_old_rank": r_old_w,
                   "write_old_max_strength": float(max(strength[i] for i in old_units)) if old_units else None,
                   "write_old_dormant": bool(old_units and max(strength[i] for i in old_units) < 0.15),
                   "query": {}}
            for q in case.queries:
                now = parse_time(q.asked_at)
                if name in REVIVE_AT_QUERY:
                    order, sess, strength = ranked(full, q.text, now, None, "multiply", None)
                else:
                    order, sess, strength = ranked(full, q.text, now, curve, mode, thr)
                res["query"][q.meta["dim"]] = {"new_rank": first_rank(order, sess, sid_n),
                                               "old_rank": first_rank(order, sess, sid_o)}
            row["cfg"][name] = res
        rows.append(row)
    (out / "per_case.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")

    def hit(r, k):
        return 0 < r <= k

    summary = {"cases": len(rows), "seconds": round(time.time() - t0, 1),
               "days_o_to_n_median": statistics.median(r["days_o_to_n"] for r in rows),
               "days_n_to_query_median": statistics.median(r["days_n_to_query"] for r in rows),
               "configs": {}}
    for name in CONFIGS:
        cs = [r["cfg"][name] for r in rows]
        qs = [(r["type"], d, v) for r, c in zip(rows, cs) for d, v in c["query"].items()]
        s = {"write_old_dormant": sum(c["write_old_dormant"] for c in cs) / len(cs)}
        for k in KS:
            s[f"write_old_hit@{k}"] = sum(hit(c["write_old_rank"], k) for c in cs) / len(cs)
            s[f"query_new_hit@{k}"] = sum(hit(v["new_rank"], k) for _, _, v in qs) / len(qs)
            s[f"query_old_hit@{k}"] = sum(hit(v["old_rank"], k) for _, _, v in qs) / len(qs)
            # the pattern a write-time adjudicator cannot fix: old memory unreachable at write
            # time, yet retrieved (stale) at query time
            s[f"masked_then_stale@{k}"] = sum(
                (not hit(c["write_old_rank"], k)) and any(hit(v["old_rank"], k) for v in c["query"].values())
                for c in cs) / len(cs)
            for typ in ("T1", "T2"):
                sub = [v for t, _, v in qs if t == typ]
                if sub:
                    s[f"query_new_hit@{k}_{typ}"] = sum(hit(v["new_rank"], k) for v in sub) / len(sub)
        summary["configs"][name] = {k: round(v, 4) for k, v in s.items()}
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
