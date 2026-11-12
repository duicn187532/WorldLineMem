"""LongMemEval (ICLR 2025, arXiv:2410.10813), 2025-09 cleaned release.

Data:   longmemeval_oracle.json (evidence sessions only) and longmemeval_s_cleaned.json
        (~50 sessions, ~115K tokens). 500 questions each; types single-session-user,
        single-session-assistant, single-session-preference, multi-session,
        temporal-reasoning, knowledge-update; 30 abstention questions (``*_abs``).
Prompt: the answer templates of the official ``src/generation/run_generation.py``.
        That file imports torch/transformers at module level, so the template strings are
        copied verbatim below; ``tests/test_official_provenance.py`` checks that every
        copied string still occurs in the pinned official file.
Metric: the official judge prompts (``get_anscheck_prompt`` imported from the pinned
        ``src/evaluation/evaluate_qa.py``), temperature 0, max_tokens 10, label = 'yes' in
        reply; the official script's own ``main`` is not used because it hard-codes the judge
        endpoint. Aggregation follows ``print_qa_metrics.py``.

Deviations (documented in docs/EXPERIMENT_PROTOCOL.md):
* Turn field ``has_answer`` (a gold evidence label) is removed before anything reaches a
  memory method or a prompt. The official json history format would serialise it.
* Original session ids (``answer_*`` reveals evidence) are replaced by neutral ids.
* Sessions are ingested in timestamp order (stable sort). Some official files are not
  sorted; the official long-context prompt keeps file order.
* Sessions dated after the question are kept by default (``exclude_future_sessions=false``)
  because in the released data they include evidence sessions; dropping them would change
  the task. Counts are reported by ``wlmem verify-data``.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from ..types import Case, MemoryContext, Query, Session, Turn
from .base import Benchmark, check_official_checkout, data_file, load_official, sha256_file

FILES = {"oracle": "longmemeval_oracle.json", "s": "longmemeval_s_cleaned.json"}
DATE_FMT = "%Y/%m/%d (%a) %H:%M"

# Verbatim from src/generation/run_generation.py (pinned commit), retriever_type orig-session / flat-session
ANSWER_TEMPLATE = 'I will give you several history chats between you and a user. Please answer the question based on the relevant chat history.\n\n\nHistory Chats:\n\n{}\n\nCurrent Date: {}\nQuestion: {}\nAnswer:'
ANSWER_TEMPLATE_COT = 'I will give you several history chats between you and a user. Please answer the question based on the relevant chat history. Answer the question step by step: first extract all the relevant information, and then reason over the information to get the answer.\n\n\nHistory Chats:\n\n{}\n\nCurrent Date: {}\nQuestion: {}\nAnswer (step by step):'
SESSION_TEMPLATE = '\n### Session {}:\nSession Date: {}\nSession Content:\n{}\n'
NL_TURN_TEMPLATE = "\n\n{}: {}"
OFFICIAL_GEN_LENGTH = {False: 500, True: 800}  # gen_length = 500 if not args.cot else 800

TYPES = ["single-session-user", "single-session-preference", "single-session-assistant",
         "multi-session", "temporal-reasoning", "knowledge-update"]


def parse_date(s: str) -> datetime:
    return datetime.strptime(s, DATE_FMT)


class LongMemEvalBenchmark(Benchmark):
    name = "longmemeval"

    @property
    def variant(self) -> str:
        v = self.params.get("variant", "oracle")
        if v not in FILES:
            raise ValueError(f"variant must be one of {sorted(FILES)} (longmemeval_m is not supported)")
        return v

    def _records(self) -> list[dict[str, Any]]:
        if not hasattr(self, "_cache"):
            with open(data_file("longmemeval", FILES[self.variant]), encoding="utf-8") as f:
                self._cache = json.load(f)
        return self._cache

    def cases(self) -> Iterator[Case]:
        recs = {r["question_id"]: r for r in self._records()}
        qtypes = self.params.get("question_types")
        ids = [q for q, r in recs.items() if not qtypes or r["question_type"] in qtypes]
        exclude_future = bool(self.params.get("exclude_future_sessions", False))
        for qid in self._select(ids):
            r = recs[qid]
            items = sorted(
                zip(r["haystack_dates"], r["haystack_session_ids"], r["haystack_sessions"]),
                key=lambda x: parse_date(x[0]),
            )
            sessions = [
                Session(
                    session_id=f"s{i:03d}",
                    order=i,
                    timestamp=date,
                    turns=tuple(Turn(t["role"], t["content"]) for t in sess),  # has_answer dropped
                )
                for i, (date, _sid, sess) in enumerate(items)
            ]
            qdate = parse_date(r["question_date"])
            visible = len(sessions)
            if exclude_future:
                visible = sum(1 for s in sessions if parse_date(s.timestamp) <= qdate)
            gold = {
                "question_type": r["question_type"],
                "answer": r["answer"],
                "abstention": qid.endswith("_abs"),
                "answer_session_ids": r["answer_session_ids"],
                "neutral_to_original_session_id": {f"s{i:03d}": sid for i, (_, sid, _) in enumerate(items)},
            }
            yield Case(
                case_id=qid,
                sessions=sessions,
                queries=[Query(query_id=qid, text=r["question"], visible_sessions=visible, asked_at=r["question_date"])],
                gold=gold,
            )

    def render(self, case: Case, query: Query, ctx: MemoryContext) -> list[dict[str, str]]:
        cot = bool(self.params.get("cot", False))
        fmt = self.params.get("history_format", "json")
        if ctx.text is not None:
            history = ctx.text
        else:
            history = ""
            for i, s in enumerate(ctx.sessions or []):
                turns = [{"role": t.role, "content": t.content} for t in s.turns]
                if fmt == "json":
                    body = "\n" + json.dumps(turns)
                elif fmt == "nl":
                    body = "".join(NL_TURN_TEMPLATE.format(t["role"], t["content"].strip()) for t in turns)
                else:
                    raise ValueError("history_format must be 'json' or 'nl'")
                history += SESSION_TEMPLATE.format(i + 1, s.timestamp, body)
        template = ANSWER_TEMPLATE_COT if cot else ANSWER_TEMPLATE
        return [{"role": "user", "content": template.format(history, query.asked_at, query.text)}]

    def answer_kwargs(self) -> dict[str, Any]:
        return {"max_tokens": OFFICIAL_GEN_LENGTH[bool(self.params.get("cot", False))], "temperature": 0.0}

    def describe(self) -> dict[str, Any]:
        p = data_file("longmemeval", FILES[self.variant])
        return {
            "benchmark": self.name,
            "variant": self.variant,
            "data_file": str(p),
            "data_sha256": sha256_file(p),
            "official": check_official_checkout("longmemeval"),
            "history_format": self.params.get("history_format", "json"),
            "cot": bool(self.params.get("cot", False)),
            "exclude_future_sessions": bool(self.params.get("exclude_future_sessions", False)),
            "prompt_source": "src/generation/run_generation.py (templates copied verbatim, provenance-tested)",
            "metric_source": "src/evaluation/evaluate_qa.py: get_anscheck_prompt; aggregation as print_qa_metrics.py",
        }

    def evaluate(self, records: list[dict[str, Any]], judge: Any, out_dir: Path) -> dict[str, Any]:
        out_dir.mkdir(parents=True, exist_ok=True)
        off = load_official("longmemeval", "src/evaluation/evaluate_qa.py")
        refs = {r["question_id"]: r for r in self._records()}
        judge_name = getattr(judge, "model", "unknown")
        hyp_path = out_dir / "longmemeval_hypotheses.jsonl"
        log_path = out_dir / f"longmemeval_hypotheses.jsonl.eval-results-{judge_name.replace(':', '_').replace('/', '_')}"
        type2acc: dict[str, list[int]] = {t: [] for t in TYPES}
        abst: list[int] = []
        with open(hyp_path, "w", encoding="utf-8") as hf, open(log_path, "w", encoding="utf-8") as lf:
            for r in records:
                qid = r["query_id"]
                entry = {"question_id": qid, "hypothesis": r["response"]}
                print(json.dumps(entry, ensure_ascii=False), file=hf)
                ref = refs[qid]
                prompt = off.get_anscheck_prompt(ref["question_type"], ref["question"], ref["answer"],
                                                 r["response"], abstention="_abs" in qid)
                reply = judge.chat([{"role": "user", "content": prompt}], temperature=0.0, max_tokens=10).text.strip()
                label = "yes" in reply.lower()
                entry["autoeval_label"] = {"model": judge_name, "label": label, "raw": reply}
                print(json.dumps(entry, ensure_ascii=False), file=lf)
                type2acc[ref["question_type"]].append(int(label))
                if "_abs" in qid:
                    abst.append(int(label))
        mean = lambda v: sum(v) / len(v) if v else None  # noqa: E731
        allv = [x for v in type2acc.values() for x in v]
        present = [mean(v) for v in type2acc.values() if v]
        return {
            "metric": "accuracy (official judge prompts, local judge)",
            "variant": self.variant,
            "overall_accuracy": mean(allv),
            "task_averaged_accuracy": sum(present) / len(present) if present else None,
            "abstention_accuracy": mean(abst),
            "per_type": {t: {"accuracy": mean(v), "n": len(v)} for t, v in type2acc.items()},
            "n_questions": len(allv),
            "official_format_files": {"hypotheses": str(hyp_path), "eval_log": str(log_path)},
        }
