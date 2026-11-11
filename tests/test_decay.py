import math

from wlmem.memory import Services, make_memory
from wlmem.memory.decay import DecayCurve, parse_time
from wlmem.types import Query, Session, Turn


def test_fademem_published_half_lives():
    # FadeMem section 2.2: at I = 0 and lambda_base = 0.1, ~11.25 days (beta 0.8) and ~5.02 days (beta 1.2)
    assert math.isclose(DecayCurve(0.1, 0.8).half_life_days(), 11.25, abs_tol=0.01)
    assert math.isclose(DecayCurve(0.1, 1.2).half_life_days(), 5.02, abs_tol=0.01)
    assert math.isclose(DecayCurve(0.1, 1.2).strength(DecayCurve(0.1, 1.2).half_life_days()), 0.5)
    assert DecayCurve(0.0, 1.0).strength(1e6) == 1.0


def test_timestamp_formats_of_pinned_benchmarks():
    for s in ("2020-04-24 18:15", "2023/05/20 (Sat) 02:21", "2025-06-01"):
        assert parse_time(s) is not None
    assert parse_time("not a date") is None


def _sessions():
    old = Session("s0", 0, "2020-01-01 10:00", (Turn("user", "I commute by bike every day"), Turn("assistant", "ok")))
    new = Session("s1", 1, "2020-12-01 10:00", (Turn("user", "my bike commute route changed"), Turn("assistant", "ok")))
    return old, new


def test_rag_decay_modes():
    old, new = _sessions()
    q = Query("q", "bike commute", 2, asked_at="2020-12-02 10:00")
    for mode, expect_old in (("multiply", True), ("dormant", False)):
        m = make_memory("rag", Services(), {"retriever": "bm25", "top_k": 5,
                                             "decay": {"lambda_base": 0.1, "beta": 1.2, "mode": mode}})
        m.reset()
        m.ingest(old)
        m.ingest(new)
        ctx = m.retrieve(q)
        assert ctx.retrieved_ids[0].startswith("s1")  # the recent unit ranks first
        assert any(r.startswith("s0") for r in ctx.retrieved_ids) == expect_old
    plain = make_memory("rag", Services(), {"retriever": "bm25", "top_k": 5})
    plain.reset()
    plain.ingest(old)
    plain.ingest(new)
    assert "dormant_units" not in plain.retrieve(q).stats
