"""Split STALE judge outcomes by what the memory method handed to the answer model.

For a finished run (``wlmem run`` + ``wlmem evaluate``), every probe is put in one cell of

    new evidence in context?  x  old evidence in context?  x  judge pass?

using ``retrieved_ids`` from answers.jsonl and the official judge's per-probe ``pass`` from
eval/<judge>/stale_T*_eval.json. The gold ``relevant_session_index`` is used only here, for
scoring. Methods that return whole sessions (full_context) count a session as in context when
its id appears in retrieved_ids.

    python scripts/decompose_stale_errors.py runs/<run_name> [--judge <eval subdir>]

Reading the table:
    new missing            a retrieval failure: the answer model never saw the update
    new present, fail      a use failure: the update was visible and still not acted on
    new present, old present, fail   the case STALE calls "retrieved but not applied"
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from wlmem.benchmarks import make_benchmark  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir")
    ap.add_argument("--judge", default=None, help="eval subdirectory; default: the only one present")
    args = ap.parse_args()
    run = Path(args.run_dir)
    evals = sorted((run / "eval").iterdir()) if (run / "eval").is_dir() else []
    if args.judge:
        evals = [run / "eval" / args.judge]
    if len(evals) != 1:
        print(f"choose one judge with --judge: {[e.name for e in evals]}")
        return 2
    passed: dict[str, bool] = {}
    for f in evals[0].glob("stale_T*_eval.json"):
        for d in json.loads(f.read_text(encoding="utf-8"))["details"]:
            for dim in ("dim1", "dim2", "dim3"):
                ev = (d.get("evaluation") or {}).get(f"{dim}_eval")
                if ev is not None:
                    passed[f"{d['uid']}#{dim}"] = bool(ev.get("pass"))
    gold = {r["uid"]: r["relevant_session_index"][:2] for r in make_benchmark("stale", {})._records()}
    cells: Counter = Counter()
    by_dim: dict[str, Counter] = {}
    with open(run / "answers.jsonl", encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            if r["query_id"] not in passed:
                continue
            uid, dim = r["query_id"].split("#")
            o, n = gold[uid]
            ids = {x.split(":", 1)[0] for x in r.get("retrieved_ids") or []}
            key = (f"s{n:03d}" in ids, f"s{o:03d}" in ids, passed[r["query_id"]])
            cells[key] += 1
            by_dim.setdefault(dim, Counter())[key] += 1
    total = sum(cells.values())
    if not total:
        print("no evaluated probes found")
        return 1

    def table(c: Counter, n: int) -> list[str]:
        rows = []
        for new in (True, False):
            for old in (True, False):
                p, f = c[(new, old, True)], c[(new, old, False)]
                rows.append(f"| {'yes' if new else 'no'} | {'yes' if old else 'no'} | {p + f} | {p} | {f} | {(p + f) / n:.1%} |")
        return rows

    out = ["| new evidence in context | old evidence in context | probes | pass | fail | share |",
           "|---|---|---|---|---|---|", *table(cells, total)]
    fail_missing = sum(v for (new, _, ok), v in cells.items() if not new and not ok)
    fail_present = sum(v for (new, _, ok), v in cells.items() if new and not ok)
    out += ["", f"probes: {total}; failures with the update missing (retrieval): {fail_missing}; "
                f"failures with the update in context (use): {fail_present}"]
    for dim, c in sorted(by_dim.items()):
        out += ["", f"### {dim}", "| new | old | probes | pass | fail | share |", "|---|---|---|---|---|---|",
                *table(c, sum(c.values()))]
    text = "\n".join(out)
    (evals[0] / "error_decomposition.md").write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
