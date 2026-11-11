"""STALE (arXiv:2605.06527): implicit conflicts in long-term user memory.

Data:   STALEproj/STALE T1_T2_400_FULL.json (400 cases = 200 Type I + 200 Type II), each a
        50-session haystack (~150K tokens) followed by three probing queries
        (dim1 State Resolution, dim2 Premise Resistance, dim3 Implicit Policy Adaptation).
Prompt: official ``Evaluation/run_target_model.py``: ``format_haystack`` + ``build_prompts``.
Metric: official ``Evaluation/full_eval_performance.py`` ``run_evaluation`` (all-in-one LLM
        judge, one call per case), run once per conflict type as in the official README.
        Overall = mean accuracy over the six (type x dimension) cells, as in the README table.

Not used: the official ``--enable-trim`` option. It keeps the two evidence sessions by
reading ``relevant_session_index`` (a gold label) and is therefore not allowed here.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Iterator

from ..types import Case, MemoryContext, Query, Session, Turn
from .base import AsyncOpenAIShim, Benchmark, check_official_checkout, data_file, load_official, sha256_file

DIMS = ("dim1", "dim2", "dim3")
DATA_FILE = "T1_T2_400_FULL.json"


class StaleBenchmark(Benchmark):
    name = "stale"

    def _records(self) -> list[dict[str, Any]]:
        if not hasattr(self, "_cache"):
            with open(data_file("stale", DATA_FILE), encoding="utf-8") as f:
                obj = json.load(f)
            self._cache = obj["data"] if isinstance(obj, dict) else obj
        return self._cache

    def cases(self) -> Iterator[Case]:
        recs = self._records()
        types = self.params.get("types") or ["T1", "T2"]
        recs = [r for r in recs if r["type"] in types]
        by_id = {r["uid"]: r for r in recs}
        for uid in self._select([r["uid"] for r in recs]):
            r = by_id[uid]
            sessions = [
                Session(
                    session_id=f"s{i:03d}",
                    order=i,
                    timestamp=r["timestamps"][i] if i < len(r["timestamps"]) else None,
                    turns=tuple(Turn(t["role"], t["content"]) for t in sess),
                )
                for i, sess in enumerate(r["haystack_session"])
            ]
            queries = [
                Query(
                    query_id=f"{uid}#{d}",
                    text=r["probing_queries"][f"{d}_query"],
                    visible_sessions=len(sessions),
                    meta={"dim": d},
                )
                for d in DIMS
            ]
            gold = {k: r[k] for k in ("uid", "M_old", "M_new", "explanation", "relevant_session_index", "type")}
            gold["probing_queries"] = r["probing_queries"]
            yield Case(case_id=uid, sessions=sessions, queries=queries, gold=gold)

    def render(self, case: Case, query: Query, ctx: MemoryContext) -> list[dict[str, str]]:
        off = load_official("stale", "STALE/Evaluation/run_target_model.py", extra_paths=["STALE"])
        if ctx.text is not None:
            history = ctx.text
        else:
            sess = [[{"role": t.role, "content": t.content} for t in s.turns] for s in ctx.sessions or []]
            stamps = [s.timestamp for s in ctx.sessions or []]
            history = off.format_haystack(sess, stamps if all(stamps) else None)
        sys_prompt, user_prompt = off.build_prompts(history, query.text, f"{query.meta['dim']}_query")
        return [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}]

    def describe(self) -> dict[str, Any]:
        p = data_file("stale", DATA_FILE)
        return {
            "benchmark": self.name,
            "data_file": str(p),
            "data_sha256": sha256_file(p),
            "official": check_official_checkout("stale"),
            "types": self.params.get("types") or ["T1", "T2"],
            "prompt_source": "STALE/Evaluation/run_target_model.py: format_haystack, build_prompts",
            "metric_source": "STALE/Evaluation/full_eval_performance.py: run_evaluation",
        }

    # ------------------------------------------------------------------ evaluation

    def evaluate(self, records: list[dict[str, Any]], judge: Any, out_dir: Path) -> dict[str, Any]:
        out_dir.mkdir(parents=True, exist_ok=True)
        gold = {r["uid"]: r for r in self._records()}
        answers: dict[str, dict[str, Any]] = {}
        for r in records:
            uid, dim = r["query_id"].split("#")
            a = answers.setdefault(uid, {"uid": uid, "target_model_responses": {}, "target_model_meta": {}})
            a["target_model_responses"][f"{dim}_response"] = r["response"]
            a["target_model_meta"][f"{dim}_meta"] = {
                "elapsed_seconds": r["answer"]["latency_s"],
                "usage": {"prompt_tokens": r["answer"]["prompt_tokens"] or 0,
                          "completion_tokens": r["answer"]["completion_tokens"] or 0,
                          "total_tokens": (r["answer"]["prompt_tokens"] or 0) + (r["answer"]["completion_tokens"] or 0)},
            }
        complete = {u: a for u, a in answers.items() if len(a["target_model_responses"]) == 3}
        skipped = sorted(set(answers) - set(complete))

        mod = load_official("stale", "STALE/Evaluation/full_eval_performance.py", extra_paths=["STALE", "STALE/Evaluation"])
        mod.eval_client = AsyncOpenAIShim(judge)
        mod.EVAL_MODEL = getattr(judge, "model", "unknown")
        mod.CONCURRENCY_LIMIT = 1

        cells: dict[str, dict[str, Any]] = {}
        files: dict[str, str] = {}
        for ctype in ("T1", "T2"):
            uids = [u for u in complete if gold[u]["type"] == ctype]
            if not uids:
                continue
            ans_path = out_dir / f"stale_{ctype}_answers.json"
            ref_path = out_dir / f"stale_{ctype}_reference.json"
            eval_path = out_dir / f"stale_{ctype}_eval.json"
            _dump(ans_path, [complete[u] for u in uids])
            # reference file: the official schema minus the haystack (the judge never reads it)
            _dump(ref_path, [{k: gold[u][k] for k in ("uid", "M_old", "M_new", "explanation", "probing_queries", "type")} for u in uids])
            asyncio.run(mod.run_evaluation(str(ans_path), str(ref_path), str(eval_path), "wlmem", ctype))
            with open(eval_path, encoding="utf-8") as f:
                summary = json.load(f)["summary"]["accuracy"][ctype]
            cells[ctype] = summary
            files[ctype] = str(eval_path)

        six = [cells[t][d]["accuracy"] for t in cells for d in DIMS]
        return {
            "metric": "accuracy (official all-in-one judge)",
            "per_type": cells,
            "overall_mean_of_cells": sum(six) / len(six) if six else None,
            "n_cases": len(complete),
            "incomplete_cases_skipped": skipped,
            "official_eval_files": files,
        }


def _dump(path: Path, obj: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
