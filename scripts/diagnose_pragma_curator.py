"""Does Pragma's per-turn Curator reopen the old memory before reconsolidation can see it?

Follow-up to diagnose_stale_decay.py. Pragma (Santi 2026, KBS 353:117193; source @e53eace)
curates memory on EVERY user turn, searching active AND dormant episodes, and revives what
the model selects. Post-session, the forgetting sweep runs and episodic reconsolidation
re-reads the three past episodes most similar to the new one (active only). So a dormant
old memory m_o can still be reinterpreted if the Curator selects it during the new-evidence
session n. diagnose_stale_decay.py did not model that step.

This script measures, on the keyword path of Pragma (no embedding server), with one episode
per STALE session and the episode text approximated by the session's turns:

  offered_any     m_o is among the 10 Curator candidates for at least one user turn of n
  offered_first   ... for the first user turn of n
  top3_if_active  m_o is among the 3 past episodes reconsolidation would re-read (>=2 shared
                  words), assuming it was revived
  reach_upper     offered_any AND top3_if_active: an UPPER bound on reinterpretation reach,
                  reached only if the Curator model selects m_o whenever it is offered

Pragma's own tokenizer is loaded from a local checkout at run time (AGPL-3.0, not copied
here). No language model is called; gold indices are used only for scoring.

    python scripts/diagnose_pragma_curator.py --pragma <path to pragma checkout>
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from wlmem.benchmarks import make_benchmark  # noqa: E402

N_CAND, RECENT, RECON_MAX, MIN_SHARED = 10, 3, 3, 2  # config.py / episode_consolidate @e53eace


def load_tokenizer(pragma: Path):
    src = (pragma / "core" / "curator.py").read_text(encoding="utf-8")
    ns: dict = {"re": re}
    exec(src[src.index("_WORD = re.compile"):src.index("def _terms")], ns)
    return ns["_tokens"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pragma", required=True, type=Path)
    ap.add_argument("--out", default="runs/diagnostics/pragma_curator")
    args = ap.parse_args()
    tok = load_tokenizer(args.pragma)
    try:
        rev = subprocess.run(["git", "-C", str(args.pragma), "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        rev = "unknown"
    rows = []
    for case in make_benchmark("stale", {}).cases():
        o, n = case.gold["relevant_session_index"][:2]
        eps = [tok(" ".join(t.content for t in s.turns)) for s in case.sessions]
        past = list(range(n))

        def candidates(task: set[str]) -> list[int]:
            kw = {j: len(eps[j] & task) for j in past}
            matched = sorted((j for j in past if kw[j] > 0), key=lambda j: (kw[j], j), reverse=True)
            if not matched:
                return sorted(past, reverse=True)[:N_CAND]
            out = matched[:N_CAND - RECENT]
            for j in sorted(past, reverse=True):
                if len(out) >= N_CAND:
                    break
                if j not in out:
                    out.append(j)
            return out

        offered = [o in candidates(tok(t.content)) for t in case.sessions[n].turns if t.role == "user"]
        sim = sorted(((j, len(eps[j] & eps[n])) for j in past), key=lambda t: (t[1], t[0]), reverse=True)
        top = [j for j, s in sim if s >= MIN_SHARED][:RECON_MAX]
        rows.append({"uid": case.case_id, "offered_any": any(offered),
                     "offered_first": bool(offered and offered[0]),
                     "offered_share": sum(offered) / max(1, len(offered)),
                     "top3_if_active": o in top, "reach_upper": any(offered) and o in top})
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "per_case.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    keys = ("offered_any", "offered_first", "top3_if_active", "reach_upper")
    summary = {"cases": len(rows), "pragma_revision": rev,
               **{k: round(sum(r[k] for r in rows) / len(rows), 4) for k in keys},
               "median_offered_share": statistics.median(r["offered_share"] for r in rows)}
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
