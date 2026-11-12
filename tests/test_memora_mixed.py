"""The mixed-store protocol (derived, not official): stream construction and invariants."""
import json

import pytest

from conftest import needs_memora
from wlmem.benchmarks import make_benchmark
from wlmem.config import Config
from wlmem.memory import Services, make_memory
from wlmem.runner import evaluate, run
from wlmem.types import MemoryContext

PERSONAS = ["academic_researcher", "sales_manager", "software_engineer", "startup_founder"]


def _case(**params):
    return next(make_benchmark("memora_mixed", {"personas": PERSONAS, **params}).cases())


@needs_memora
def test_reduces_to_official_memora_for_one_person():
    mixed = make_benchmark("memora_mixed", {"personas": ["academic_researcher"], "group_size": 1, "prompt": "official"})
    official = make_benchmark("memora", {"periods": ["weekly"], "personas": ["academic_researcher"]})
    cm, co = next(mixed.cases()), next(official.cases())
    assert [q.text for q in cm.queries] == [q.text for q in co.queries]
    assert [s.turns for s in cm.sessions] == [s.turns for s in co.sessions]
    for qm, qo in zip(cm.queries[:3], co.queries[:3]):
        assert mixed.render(cm, qm, MemoryContext(sessions=cm.sessions)) == official.render(co, qo, MemoryContext(sessions=co.sessions))


@needs_memora
def test_stream_keeps_each_persons_order_and_hides_who_is_who():
    case = _case(group_size=4, context_signal="none", seed=3)
    personas = set(PERSONAS)
    visible = json.dumps([[s.session_id, s.context, s.display] for s in case.sessions]) + json.dumps(
        [[q.query_id, q.context, q.meta] for q in case.queries])
    assert not any(p in visible for p in personas), "persona names must not reach a memory method"
    assert all(s.context is None for s in case.sessions) and all(q.context is None for q in case.queries)
    assert [s.order for s in case.sessions] == list(range(len(case.sessions)))
    assert [s.timestamp for s in case.sessions] == sorted(s.timestamp for s in case.sessions)
    # each person's sessions appear in their original order and nothing is lost or duplicated
    for alias, persona in case.gold["alias_persona"].items():
        official = next(make_benchmark("memora", {"periods": ["weekly"], "personas": [persona]}).cases())
        mine = [s.turns for s in case.sessions if case.gold["owner"][s.session_id] == alias]
        assert mine == [s.turns for s in official.sessions]


@needs_memora
def test_questions_follow_the_askers_last_block_and_keep_official_gold():
    case = _case(group_size=4, context_signal="boundary", seed=1)
    for q in case.queries:
        who = case.gold["asker"][q.query_id]
        last = case.sessions[q.visible_sessions - 1]
        assert case.gold["owner"][last.session_id] == who
        assert q.context == last.context == case.gold["block"][last.session_id]
        later_own = [s for s in case.sessions[q.visible_sessions:] if case.gold["owner"][s.session_id] == who]
        assert not later_own, "every session of the asker precedes the question"
    # a block never mixes people, and gold is the untouched official question record
    owners_per_block = {}
    for s in case.sessions:
        owners_per_block.setdefault(s.context, set()).add(case.gold["owner"][s.session_id])
    assert all(len(v) == 1 for v in owners_per_block.values())
    persona = case.gold["alias_persona"]["U1"]
    official = next(make_benchmark("memora", {"periods": ["weekly"], "personas": [persona]}).cases())
    mine = [v for k, v in case.gold["questions"].items() if k.split("/")[-2] == "U1"]
    assert mine == list(official.gold["questions"].values())


@needs_memora
def test_same_seed_same_stream_and_seed_changes_it():
    a, b, c = (_case(group_size=4, seed=s) for s in (5, 5, 6))
    assert [s.turns for s in a.sessions] == [s.turns for s in b.sessions]
    assert [s.turns for s in a.sessions] != [s.turns for s in c.sessions]


@needs_memora
def test_scope_context_isolates_by_label_and_needs_a_signal():
    case = _case(group_size=4, context_signal="label")
    q = case.queries[0]

    def retrieve(scope, c=case, query=q):
        m = make_memory("rag", Services(), {"granularity": "round", "retriever": "bm25", "top_k": 12, "scope": scope})
        m.reset()
        for s in c.sessions[: query.visible_sessions]:
            m.ingest(s)
        return [c.gold["owner"][r.split(":")[0]] for r in m.retrieve(query).retrieved_ids]

    assert set(retrieve("context")) == {case.gold["asker"][q.query_id]}
    assert len(set(retrieve("global"))) > 1, "global retrieval pulls in other people's memory"
    flat = _case(group_size=4, context_signal="none")
    with pytest.raises(ValueError):
        retrieve("context", flat, flat.queries[0])


@needs_memora
def test_prompt_shows_the_signal_and_the_live_conversation():
    for signal, marker in (("label", "Current context: U"), ("boundary", "Current context: b"), ("none", None)):
        bench = make_benchmark("memora_mixed", {"personas": PERSONAS, "group_size": 4, "context_signal": signal})
        case = next(bench.cases())
        q = case.queries[0]
        system, user = (m["content"] for m in bench.render(case, q, MemoryContext(sessions=case.sessions[:5])))
        assert "with this user" not in system and "several different people" in system
        assert "# Current Conversation" in user and user.index("# Current Conversation") < user.index("# Current Question")
        live = case.sessions[q.visible_sessions - 1]
        assert live.turns[-1].content in user.split("# Current Conversation")[1]
        assert (marker in user) if marker else ("Current context:" not in user and "[context:" not in user)


@needs_memora
def test_end_to_end_with_mock_models_is_labelled_and_reports_foreign_retrieval(tmp_path):
    cfg_path = tmp_path / "c.toml"
    cfg_path.write_text(f'''
[run]
name = "mixed_mock"
output_dir = "{tmp_path.as_posix()}"
cache_dir = "{tmp_path.as_posix()}/cache"
[benchmark]
name = "memora_mixed"
personas = ["academic_researcher", "sales_manager"]
group_size = 2
context_signal = "none"
question_limit = 2
[memory]
method = "rag"
top_k = 8
[answer_model]
backend = "mock"
[judge]
backend = "mock"
''', encoding="utf-8")
    cfg = Config.load(str(cfg_path))
    out = run(cfg)
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["benchmark"]["protocol"].startswith("DERIVED")
    report = evaluate(cfg)
    assert report["complete"] and report["answered_queries"] == 4
    fr = report["metrics"]["foreign_retrieval"]
    assert fr["queries_with_retrieval"] == 4 and 0.0 <= fr["unit_share"] <= 1.0
    assert set(report["metrics"]["fama_by_asker"]) == {"weekly/mix2-s0-g0/U1", "weekly/mix2-s0-g0/U2"}


def test_derived_protocols_are_labelled_in_results():
    from wlmem.runner import _label

    class Derived:
        derived_protocol = True

    cfg = type("C", (), {"run": {"label": "local_adaptation"}})()
    assert _label(cfg, object(), Derived()) == "derived_protocol:local_adaptation"
    assert _label(cfg, object(), object()) == "local_adaptation"
