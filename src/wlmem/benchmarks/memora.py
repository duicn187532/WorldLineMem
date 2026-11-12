"""Memora: "From Recall to Forgetting" (ACL 2026, arXiv:2604.20006).

Data:   the official repository's ``data/<period>/<persona>/`` (10 personas x weekly /
        monthly / quarterly; ~150 / ~600 / ~2000 sessions; 15 / 15 / 30 questions).
        One case = one (period, persona); all its questions share the history, as in the
        official Track 1.
Prompt: official Track 1 ``evals/model_eval/model_based_evaluator.py``: ``PromptBuilder``
        (``build_conversation_context`` + ``build_question_prompt``), imported unmodified.
Metric: official ``ModelEvaluator`` (yes/no judge prompt and parser) per sub-question and
        official ``fama_score`` per question; task and overall FAMA = mean of per-question FAMA
        x 100, as in the official ``_generate_report``.

Faithfulness notes:
* Session annotations ``session_type``, ``operation``, ``operation_details`` and the turn flag
  ``share_memory`` say which turns carry memory or forgetting. They are gold-like and are
  never given to memory methods (the official Track 1 prompt does not show them either).
* The official Track 1 reads ``question_data['session_date']``, a field the released
  question files do not have, so its prompt carries no current date. ``pass_question_date``
  (default false) keeps that behaviour; true supplies ``question_date`` instead and is a
  documented deviation.
* The released sessions label the human side ``user_agent``, but the official Track 1
  ``PromptBuilder`` only prints turns labelled ``ai_agent`` or ``user``. At the pinned commit
  its full-history prompt therefore contains no user turn at all (the official Track 2 agent
  integrations do map ``user_agent`` to ``user``). Memory methods here always receive both
  sides. The rendered history shows both sides by default; ``drop_user_turns = true``
  reproduces the official Track 1 prompt byte for byte.
* The official setup uses a three-judge majority (GPT-4.1, Claude Haiku 4.5, Gemini 2.5
  Flash via OpenRouter). Here a single local judge is used: Local Adaptation.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

from ..types import Case, MemoryContext, Query, Session, Turn
from .base import Benchmark, GenerateResponseShim, check_official_checkout, load_official, repo_dir

PERIODS = ("weekly", "monthly", "quarterly")
TASKS = ("remembering", "reasoning", "recommending")
TASK_LABEL = {"remembering": "Remembering", "reasoning": "Reasoning", "recommending": "Recommending"}
EVALUATOR = "evals/model_eval/model_based_evaluator.py"
# speaker labels in the released data ("user" only appears in official example code)
SPEAKER_ROLE = {"ai_agent": "assistant", "user_agent": "user", "user": "user"}


class MemoraBenchmark(Benchmark):
    name = "memora"

    def _data_dir(self) -> Path:
        return repo_dir("memora") / "data"

    def _official(self):
        return load_official("memora", EVALUATOR)

    def cases(self) -> Iterator[Case]:
        periods = self.params.get("periods") or list(PERIODS)
        ids = []
        for p in periods:
            if p not in PERIODS:
                raise ValueError(f"unknown period {p!r}")
            personas = self.params.get("personas") or sorted(
                d.name for d in (self._data_dir() / p).iterdir() if d.is_dir()
            )
            ids += [f"{p}/{persona}" for persona in personas]
        for case_id in self._select(ids):
            yield self._load_case(case_id)

    def _load_case(self, case_id: str) -> Case:
        period, persona = case_id.split("/")
        base = self._data_dir() / period / persona
        raw = []
        for f in sorted((base / "conversations").glob("session_*.json")):
            with open(f, encoding="utf-8") as fh:
                raw.append(json.load(fh))
        raw.sort(key=lambda s: s["session_id"])
        sessions = [
            Session(
                session_id=f"s{i:04d}",
                order=i,
                timestamp=s["date"],
                turns=tuple(
                    Turn(SPEAKER_ROLE[t["speaker"]], t["message"])
                    for t in s["conversation"]
                    if t.get("speaker") in SPEAKER_ROLE
                ),
                display={"session_id": s["session_id"], "date": s["date"]},
            )
            for i, s in enumerate(raw)
        ]
        with open(base / f"evaluation_questions_{persona}.json", encoding="utf-8") as fh:
            qfile = json.load(fh)
        queries, gold_q = [], {}
        for task in TASKS:
            for q in qfile["questions"].get(task, []):
                qid = f"{case_id}/{q['question_id']}"
                visible = sum(1 for s in sessions if s.timestamp <= q["question_date"])  # ISO dates
                queries.append(Query(qid, q["question"], visible, asked_at=q["question_date"], meta={"task": TASK_LABEL[task]}))
                gold_q[qid] = {**q, "task_type": TASK_LABEL[task]}
        # same as the official --limit: first N questions in Remembering, Reasoning, Recommending order
        if self.params.get("question_limit"):
            queries = queries[: int(self.params["question_limit"])]
        gold = {"questions": gold_q, "session_annotations": {
            s.session_id: {k: r.get(k) for k in ("session_type", "operation")} for s, r in zip(sessions, raw)}}
        return Case(case_id=case_id, sessions=sessions, queries=queries, gold=gold)

    def render(self, case: Case, query: Query, ctx: MemoryContext) -> list[dict[str, str]]:
        off = self._official()
        builder = off.PromptBuilder(model_name=None)
        # "user" is the only human label the official builder prints; "user_agent" (the label
        # in the released data) is silently skipped by it.
        human = "user_agent" if self.params.get("drop_user_turns", False) else "user"
        if ctx.text is not None:
            context = ctx.text
        else:
            convs = [
                {
                    "session_id": s.display["session_id"],
                    "date": s.display["date"],
                    "conversation": [
                        {"speaker": "ai_agent" if t.role == "assistant" else human, "message": t.content} for t in s.turns
                    ],
                }
                for s in ctx.sessions or []
            ]
            context, _meta = _quiet(builder.build_conversation_context, convs)
        current_date = query.asked_at if self.params.get("pass_question_date", False) else None
        system, user = _quiet(builder.build_question_prompt, context, query.text, current_date)
        return [{"role": "system", "content": system}, {"role": "user", "content": user}]

    def describe(self) -> dict[str, Any]:
        return {
            "benchmark": self.name,
            "periods": self.params.get("periods") or list(PERIODS),
            "personas": self.params.get("personas") or "all",
            "official": check_official_checkout("memora"),
            "pass_question_date": bool(self.params.get("pass_question_date", False)),
            "drop_user_turns": bool(self.params.get("drop_user_turns", False)),
            "prompt_source": f"{EVALUATOR}: PromptBuilder",
            "metric_source": f"{EVALUATOR}: ModelEvaluator, fama_score",
        }

    def evaluate(self, records: list[dict[str, Any]], judge: Any, out_dir: Path) -> dict[str, Any]:
        out_dir.mkdir(parents=True, exist_ok=True)
        off = self._official()
        evaluator = off.ModelEvaluator(GenerateResponseShim(judge))
        golds: dict[str, dict[str, Any]] = {}
        for case_id in sorted({r["case_id"] for r in records}):
            golds.update(self._load_case(case_id).gold["questions"])
        results = []
        for r in records:
            q = golds[r["query_id"]]
            evals = []
            for eq in q["evaluation"]["evaluation_questions"]:
                res = _quiet(
                    evaluator.evaluate_response,
                    model_response=r["response"],
                    evaluation_question=eq["evaluation_question"],
                    expected_answer=eq["expected_answer"],
                    question_context={"target_item": eq.get("target_item"), "evaluation_type": eq.get("evaluation_type")},
                )
                evals.append({**eq, "evaluation_result": res})
            mp = [e for e in evals if e.get("evaluation_type") == "memory_presence"]
            fa = [e for e in evals if e.get("evaluation_type") == "forgetting_absence"]
            mpc = sum(e["evaluation_result"]["is_correct"] for e in mp)
            fac = sum(e["evaluation_result"]["is_correct"] for e in fa)
            results.append({
                "question_id": r["query_id"], "case_id": r["case_id"], "task_type": q["task_type"],
                "model_response": r["response"], "evaluation_questions": evals,
                "memory_presence_correct": mpc, "memory_presence_total": len(mp),
                "forgetting_absence_correct": fac, "forgetting_absence_total": len(fa),
                "fama": off.fama_score(mpc, len(mp), fac, len(fa)),
            })
        with open(out_dir / "memora_eval_results.json", "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        def agg(rows: list[dict[str, Any]]) -> dict[str, Any]:
            if not rows:
                return {"n": 0}
            mpt = sum(x["memory_presence_total"] for x in rows)
            fat = sum(x["forgetting_absence_total"] for x in rows)
            return {
                "n": len(rows),
                "fama": 100 * sum(x["fama"] for x in rows) / len(rows),
                "memory_presence_accuracy": sum(x["memory_presence_correct"] for x in rows) / mpt if mpt else None,
                "forgetting_absence_accuracy": sum(x["forgetting_absence_correct"] for x in rows) / fat if fat else None,
            }

        by_cell: dict[str, Any] = {}
        for period in PERIODS:
            for task in TASK_LABEL.values():
                rows = [x for x in results if x["case_id"].startswith(period + "/") and x["task_type"] == task]
                if rows:
                    by_cell[f"{task}/{period}"] = agg(rows)
        return {
            "metric": "FAMA x100 (official ModelEvaluator + fama_score, single local judge)",
            "overall": agg(results),
            "by_task_period": by_cell,
            "official_format_files": {"results": str(out_dir / "memora_eval_results.json")},
        }


def _quiet(fn, *args, **kwargs):
    """The official code prints progress for every call; keep the runner log readable."""
    import contextlib
    import io

    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*args, **kwargs)
