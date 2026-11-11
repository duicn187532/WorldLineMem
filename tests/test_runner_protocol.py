"""Protocol guarantees of the runner, checked with a toy benchmark and mock models:
case isolation, chronological ingestion, no future sessions, no gold access, resume."""
import json
from pathlib import Path

from wlmem import benchmarks as B
from wlmem.backends import MockChat
from wlmem.benchmarks.base import Benchmark
from wlmem.config import Config
from wlmem.memory import MemoryAdapter, register
from wlmem.runner import evaluate, run
from wlmem.types import Case, MemoryContext, Query, Session, Turn

LOG: list[tuple] = []


class ToyBenchmark(Benchmark):
    name = "toy"

    def cases(self):
        for c in range(3):
            sessions = [Session(f"s{i}", i, f"2025-01-0{i+1}", (Turn("user", f"case{c} fact{i}"),)) for i in range(4)]
            queries = [
                Query(f"c{c}q_late", "late?", visible_sessions=4),
                Query(f"c{c}q_early", "early?", visible_sessions=2),
            ]
            yield Case(f"c{c}", sessions, queries, gold={"answer": "SECRET"})

    def render(self, case, query, ctx):
        hist = " | ".join(t.content for s in ctx.sessions for t in s.turns)
        return [{"role": "user", "content": f"{hist}\nQ: {query.text}"}]

    def evaluate(self, records, judge, out_dir):
        return {"n": len(records)}

    def describe(self):
        return {"benchmark": "toy"}


@register("spy")
class Spy(MemoryAdapter):
    def reset(self):
        self.store = []
        LOG.append(("reset",))

    def ingest(self, session):
        self.store.append(session)
        LOG.append(("ingest", session.order))

    def retrieve(self, query):
        LOG.append(("retrieve", query.query_id, len(self.store)))
        return MemoryContext(sessions=list(self.store))


def _cfg(tmp_path: Path) -> Config:
    text = f"""
[run]
name = "toy"
output_dir = "{tmp_path.as_posix()}"
cache_dir = "{(tmp_path / 'cache').as_posix()}"
[benchmark]
name = "toy"
[memory]
method = "spy"
[answer_model]
backend = "mock"
[judge]
backend = "mock"
"""
    p = tmp_path / "toy.toml"
    p.write_text(text, encoding="utf-8")
    return Config.load(p)


def test_isolation_order_visibility_and_resume(tmp_path, monkeypatch):
    monkeypatch.setitem(B.BENCHMARKS, "toy", ToyBenchmark)
    LOG.clear()
    out = run(_cfg(tmp_path))
    # one reset per case, before any ingestion of that case
    assert [e for e in LOG if e[0] == "reset"] == [("reset",)] * 3
    # within each case: ingestion is chronological and the early query sees only 2 sessions
    per_case = []
    for e in LOG:
        if e[0] == "reset":
            per_case.append([])
        else:
            per_case[-1].append(e)
    for case_log, c in zip(per_case, range(3)):
        assert case_log[:3] == [("ingest", 0), ("ingest", 1), ("retrieve", f"c{c}q_early", 2)]
        assert case_log[3:] == [("ingest", 2), ("ingest", 3), ("retrieve", f"c{c}q_late", 4)]
    answers = [json.loads(l) for l in (out / "answers.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(answers) == 6
    # the early prompt contains no future session and no gold
    mock_prompts = (out / "answers.jsonl").read_text(encoding="utf-8")
    assert "SECRET" not in mock_prompts
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["label"].startswith("PIPELINE_CHECK_MOCK")
    # resume: nothing new is produced
    LOG.clear()
    run(_cfg(tmp_path))
    assert [l for l in (out / "answers.jsonl").read_text(encoding="utf-8").splitlines()] and LOG == []
    report = evaluate(_cfg(tmp_path))
    assert report["complete"] and report["label"].startswith("PIPELINE_CHECK_MOCK")


def test_early_query_prompt_has_no_future_sessions(tmp_path, monkeypatch):
    monkeypatch.setitem(B.BENCHMARKS, "toy", ToyBenchmark)
    cfg = _cfg(tmp_path)
    bench = ToyBenchmark()
    case = next(bench.cases())
    mem = Spy(None)
    mem.reset()
    for s in case.sessions[:2]:
        mem.ingest(s)
    prompt = bench.render(case, case.queries[1], mem.retrieve(case.queries[1]))[0]["content"]
    assert "fact1" in prompt and "fact2" not in prompt and "fact3" not in prompt
