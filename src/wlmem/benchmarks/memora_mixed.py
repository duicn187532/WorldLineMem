"""Mixed-store protocol over Memora: several people, one memory, one uninterrupted stream.

THIS IS NOT AN OFFICIAL BENCHMARK. It is a derived protocol defined in
docs/MIXED_MEMORY_PROTOCOL.md. Everything that carries the answer is official and
unchanged: the Memora sessions, the questions, the yes/no evaluation sub-questions, the
judge prompt and ``fama_score``. Only the composition of the history changes: the sessions
of ``group_size`` Memora personas are interleaved into one stream that is written into one
memory store, and each persona's own questions are then asked against that shared store.

Why Memora: the ten personas cover the same week and share question wordings ("How much
have I spent on coffee this week?" is asked of all ten), so another person's memory is a
plausible but wrong source for the same question.

Stream construction (deterministic for a given ``seed``)
    * Personas are shuffled and cut into groups of ``group_size``. One group is one case.
    * Inside a group every persona gets an alias ``U1..Uk``. Persona names are never shown:
      they name a profession and would give the answer to "whose session is this" away.
    * For each calendar day the personas take turns in a shuffled order. One turn is a
      *block*: all sessions that persona had on that day, in their original order. A block
      models one uninterrupted stretch of the agent being with the same person.
    * A persona's questions are asked right after that persona's last block on the
      question date, so later blocks of other people are not yet in memory.

What the agent is told about the situation (``context_signal``)
    "label"     every session and every question carries the speaker's alias
    "boundary"  every session and every question carries an opaque token of its block, so
                the agent knows which sessions form one stretch but not whose stretch it is;
                linking a block to earlier blocks of the same person is left to the method
    "none"      nothing; the stream is flat
In all three the answer prompt ends with the ``lead_in_sessions`` sessions that came right
before the question (the live conversation), because a question such as "what is my step
goal" has no answer without knowing who is asking.

Prompt (``prompt``)
    "mixed"     the official PromptBuilder output with two official sentences replaced (they
                state that the whole history belongs to "this user") and the live
                conversation appended. The same wording is used for every ``group_size``,
                so runs with different group sizes differ only in what is in memory.
    "official"  byte-identical to the official Memora prompt; only allowed for
                group_size = 1, context_signal = "none", lead_in_sessions = 0. It exists
                to show that the protocol reduces to Memora in that corner.

Extra metric (deterministic, no judge): ``foreign_retrieval`` = share of the units a method
handed to the answer prompt that belong to someone other than the asker.
"""
from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any, Iterator

from ..types import Case, MemoryContext, Query, Session, Turn
from .memora import PERIODS, SPEAKER_ROLE, TASK_LABEL, TASKS, MemoraBenchmark, _quiet

SIGNALS = ("label", "boundary", "none")

# The two official sentences that assert a single user. They are replaced, not paraphrased
# around; render() fails if the official text ever stops containing them.
OFFICIAL_HEADER = "The following contains all your previous conversations with this user, in chronological order:"
MIXED_HEADER = (
    "The following contains conversations from your memory, in chronological order. "
    "You talk with several different people, so a conversation may belong to someone other than the person asking now:"
)
OFFICIAL_SYSTEM = "The conversation history below contains ALL your previous conversations with this user"
MIXED_SYSTEM = (
    "The conversation history below contains conversations from your memory. "
    "You talk with several different people, so a conversation may belong to someone other than the person asking now"
)


class MemoraMixedBenchmark(MemoraBenchmark):
    name = "memora_mixed"
    derived_protocol = True  # the runner prefixes the result label with "derived_protocol:"

    # ---- parameters -------------------------------------------------------------------
    def _p(self) -> dict[str, Any]:
        period = self.params.get("period", "weekly")
        if period not in PERIODS:
            raise ValueError(f"unknown period {period!r}")
        all_personas = sorted(d.name for d in (self._data_dir() / period).iterdir() if d.is_dir())
        personas = list(self.params.get("personas") or all_personas)
        unknown = set(personas) - set(all_personas)
        if unknown:
            raise ValueError(f"unknown personas: {sorted(unknown)}")
        k = int(self.params.get("group_size", len(personas)))
        if k < 1 or len(personas) % k:
            raise ValueError(f"group_size {k} must divide the number of personas ({len(personas)})")
        signal = self.params.get("context_signal", "none")
        if signal not in SIGNALS:
            raise ValueError(f"context_signal must be one of {SIGNALS}")
        prompt = self.params.get("prompt", "mixed")
        lead_in = int(self.params.get("lead_in_sessions", 0 if prompt == "official" else 1))
        if prompt not in ("mixed", "official"):
            raise ValueError("prompt must be 'mixed' or 'official'")
        if prompt == "official" and not (k == 1 and signal == "none" and lead_in == 0):
            raise ValueError("prompt='official' requires group_size=1, context_signal='none', lead_in_sessions=0")
        return {"period": period, "personas": personas, "group_size": k, "context_signal": signal,
                "prompt": prompt, "lead_in_sessions": lead_in, "seed": int(self.params.get("seed", 0))}

    def _groups(self) -> list[tuple[str, list[str]]]:
        p = self._p()
        order = list(p["personas"])
        random.Random(f"groups:{p['seed']}").shuffle(order)
        k = p["group_size"]
        return [(f"{p['period']}/mix{k}-s{p['seed']}-g{i // k}", order[i:i + k]) for i in range(0, len(order), k)]

    def cases(self) -> Iterator[Case]:
        groups = dict(self._groups())
        for case_id in self._select(list(groups)):
            yield self._build(case_id, groups[case_id])

    def _load_case(self, case_id: str) -> Case:  # used by the inherited evaluate()
        return self._build(case_id, dict(self._groups())[case_id])

    # ---- stream construction ----------------------------------------------------------
    def _build(self, case_id: str, personas: list[str]) -> Case:
        p = self._p()
        base = self._data_dir() / p["period"]
        alias = {persona: f"U{i + 1}" for i, persona in enumerate(personas)}  # group order is already shuffled
        raw: dict[str, list[dict[str, Any]]] = {}
        for persona in personas:
            rows = []
            for f in sorted((base / persona / "conversations").glob("session_*.json")):
                with open(f, encoding="utf-8") as fh:
                    rows.append(json.load(fh))
            rows.sort(key=lambda s: s["session_id"])
            raw[persona] = rows
        dates = sorted({s["date"] for rows in raw.values() for s in rows})

        sessions: list[Session] = []
        owner: dict[str, str] = {}
        block_of: dict[str, str] = {}
        annotations: dict[str, dict[str, Any]] = {}
        n_blocks = 0
        for date in dates:
            turn_order = list(personas)
            random.Random(f"day:{p['seed']}:{case_id}:{date}").shuffle(turn_order)
            for persona in turn_order:
                todays = [s for s in raw[persona] if s["date"] == date]
                if not todays:
                    continue
                block = f"b{n_blocks:04d}"
                n_blocks += 1
                for s in todays:
                    i = len(sessions)
                    sid = f"s{i:04d}"
                    context = {"label": alias[persona], "boundary": block, "none": None}[p["context_signal"]]
                    sessions.append(Session(
                        session_id=sid, order=i, timestamp=s["date"],
                        turns=tuple(Turn(SPEAKER_ROLE[t["speaker"]], t["message"])
                                    for t in s["conversation"] if t.get("speaker") in SPEAKER_ROLE),
                        display={"session_id": i + 1, "date": s["date"]},
                        context=context,
                    ))
                    owner[sid] = alias[persona]
                    block_of[sid] = block
                    annotations[sid] = {k: s.get(k) for k in ("session_type", "operation")}

        queries: list[Query] = []
        gold_q: dict[str, dict[str, Any]] = {}
        asker: dict[str, str] = {}
        for persona in personas:
            with open(base / persona / f"evaluation_questions_{persona}.json", encoding="utf-8") as fh:
                qfile = json.load(fh)
            mine = [s for s in sessions if owner[s.session_id] == alias[persona]]
            picked = []
            for task in TASKS:
                for q in qfile["questions"].get(task, []):
                    picked.append((task, q))
            if self.params.get("question_limit"):
                picked = picked[: int(self.params["question_limit"])]  # per persona, official order
            for task, q in picked:
                seen = [s for s in mine if s.timestamp <= q["question_date"]]
                if not seen:
                    raise ValueError(f"{persona}: question {q['question_id']} precedes every session")
                last = seen[-1]
                qid = f"{case_id}/{alias[persona]}/{q['question_id']}"
                queries.append(Query(qid, q["question"], last.order + 1, asked_at=q["question_date"],
                                     meta={"task": TASK_LABEL[task]}, context=last.context))
                gold_q[qid] = {**q, "task_type": TASK_LABEL[task]}
                asker[qid] = alias[persona]
        gold = {"questions": gold_q, "owner": owner, "block": block_of, "asker": asker,
                "alias_persona": {a: persona for persona, a in alias.items()}, "session_annotations": annotations}
        return Case(case_id=case_id, sessions=sessions, queries=queries, gold=gold)

    # ---- prompt -----------------------------------------------------------------------
    def _history(self, builder: Any, sessions: list[Session], annotate: bool) -> str:
        convs = [{"session_id": s.display["session_id"], "date": s.display["date"],
                  "conversation": [{"speaker": "ai_agent" if t.role == "assistant" else "user", "message": t.content}
                                   for t in s.turns]} for s in sessions]
        text, _meta = _quiet(builder.build_conversation_context, convs)
        if annotate:
            for s in sessions:
                if s.context is not None:
                    head = f"\n## Session {s.display['session_id']} - {s.display['date']}\n"
                    assert head in text, "official session header format changed"
                    text = text.replace(head, f"{head[:-1]} [context: {s.context}]\n", 1)
        return text

    def render(self, case: Case, query: Query, ctx: MemoryContext) -> list[dict[str, str]]:
        p = self._p()
        if p["prompt"] == "official":
            return super().render(case, query, ctx)
        builder = self._official().PromptBuilder(model_name=None)
        if ctx.text is not None:
            context = ctx.text
        else:
            context = self._history(builder, ctx.sessions or [], annotate=True)
            assert OFFICIAL_HEADER in context, "official history header changed"
            context = context.replace(OFFICIAL_HEADER, MIXED_HEADER, 1)
        # the live conversation: the sessions right before the question, never crossing a block
        n = p["lead_in_sessions"]
        end = query.visible_sessions
        live: list[Session] = []
        while n and end - 1 - len(live) >= 0:
            s = case.sessions[end - 1 - len(live)]
            if case.gold["block"][s.session_id] != case.gold["block"][case.sessions[end - 1].session_id]:
                break
            live.insert(0, s)
            n -= 1
        parts = ["", "---", "", "# Current Conversation"]
        if query.context is not None:
            parts.append(f"Current context: {query.context}")
        if live:
            body = self._history(builder, live, annotate=False)
            parts.append(body.split(OFFICIAL_HEADER, 1)[1].strip("\n"))
        if live or query.context is not None:
            context = context.rstrip("\n") + "\n" + "\n".join(parts) + "\n"
        current_date = query.asked_at if self.params.get("pass_question_date", False) else None
        system, user = _quiet(builder.build_question_prompt, context, query.text, current_date)
        assert OFFICIAL_SYSTEM in system, "official system prompt changed"
        system = system.replace(OFFICIAL_SYSTEM, MIXED_SYSTEM, 1)
        return [{"role": "system", "content": system}, {"role": "user", "content": user}]

    # ---- bookkeeping ------------------------------------------------------------------
    def describe(self) -> dict[str, Any]:
        d = super().describe()
        d.update({
            "benchmark": self.name,
            "protocol": "DERIVED: mixed-store protocol over Memora (docs/MIXED_MEMORY_PROTOCOL.md); not an official benchmark",
            **self._p(),
            "groups": {cid: "+".join(members) for cid, members in self._groups()},
            "prompt_source": "official PromptBuilder; two single-user sentences replaced and the live conversation appended"
                             if self._p()["prompt"] == "mixed" else d["prompt_source"],
        })
        d.pop("periods", None)
        return d

    def evaluate(self, records: list[dict[str, Any]], judge: Any, out_dir: Path) -> dict[str, Any]:
        metrics = super().evaluate(records, judge, out_dir)
        golds = {cid: self._load_case(cid).gold for cid in sorted({r["case_id"] for r in records})}
        with open(out_dir / "memora_eval_results.json", encoding="utf-8") as f:
            fama = {x["question_id"]: x["fama"] for x in json.load(f)}
        per_query, by_asker = [], {}
        for r in records:
            g = golds[r["case_id"]]
            who = g["asker"][r["query_id"]]
            owners = [g["owner"][rid.split(":", 1)[0]] for rid in r.get("retrieved_ids") or []]
            foreign = sum(o != who for o in owners)
            per_query.append({"query_id": r["query_id"], "units": len(owners), "foreign": foreign})
            by_asker.setdefault(f"{r['case_id']}/{who}", []).append(fama[r["query_id"]])
        with_units = [x for x in per_query if x["units"]]
        metrics["metric"] = "DERIVED PROTOCOL (mixed store). " + metrics["metric"]
        metrics["foreign_retrieval"] = {
            "definition": "units handed to the answer prompt that belong to someone other than the asker",
            "queries_with_retrieval": len(with_units),
            "unit_share": (sum(x["foreign"] for x in with_units) / sum(x["units"] for x in with_units)) if with_units else None,
            "queries_with_any_foreign_unit": (sum(x["foreign"] > 0 for x in with_units) / len(with_units)) if with_units else None,
        }
        metrics["fama_by_asker"] = {k: 100 * sum(v) / len(v) for k, v in sorted(by_asker.items())}
        metrics["protocol"] = self._p()
        with open(out_dir / "foreign_retrieval_per_query.json", "w", encoding="utf-8") as f:
            json.dump(per_query, f, indent=2)
        return metrics
