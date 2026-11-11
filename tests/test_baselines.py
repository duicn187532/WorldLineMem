from wlmem.backends import HashEmbedder
from wlmem.memory import Services, make_memory
from wlmem.types import Query, Session, Turn


def _sessions():
    return [
        Session("s0", 0, "d0", (Turn("user", "I live in Seattle and bike to work"), Turn("assistant", "Nice"))),
        Session("s1", 1, "d1", (Turn("user", "My cat is called Mochi"), Turn("assistant", "Cute"),
                                Turn("user", "I broke my leg skiing"), Turn("assistant", "Sorry to hear"))),
        Session("s2", 2, "d2", (Turn("user", "Recommend a pasta recipe"), Turn("assistant", "Try carbonara"))),
    ]


def test_no_memory_returns_nothing():
    m = make_memory("no_memory", Services(), {})
    m.reset()
    for s in _sessions():
        m.ingest(s)
    assert m.retrieve(Query("q", "cat name?", 3)).sessions == []


def test_full_context_drops_oldest_first():
    m = make_memory("full_context", Services(), {"max_context_tokens": 25})
    m.reset()
    for s in _sessions():
        m.ingest(s)
    ctx = m.retrieve(Query("q", "x", 3))
    assert [s.session_id for s in ctx.sessions] == ["s2"] or ctx.sessions[-1].session_id == "s2"
    assert ctx.stats["truncated"]
    full = make_memory("full_context", Services(), {})
    full.reset()
    for s in _sessions():
        full.ingest(s)
    assert [s.session_id for s in full.retrieve(Query("q", "x", 3)).sessions] == ["s0", "s1", "s2"]


def test_rag_bm25_round_granularity_returns_chronological_partial_sessions():
    m = make_memory("rag", Services(), {"granularity": "round", "retriever": "bm25", "top_k": 2})
    m.reset()
    for s in _sessions():
        m.ingest(s)
    ctx = m.retrieve(Query("q", "what happened to my leg while skiing and where do I bike", 3))
    ids = [s.session_id for s in ctx.sessions]
    assert ids == sorted(ids, key=lambda x: int(x[1:]))  # chronological
    texts = " ".join(t.content for s in ctx.sessions for t in s.turns)
    assert "broke my leg" in texts and "Mochi" not in texts


def test_rag_dense_uses_embedder():
    emb = HashEmbedder()
    m = make_memory("rag", Services(embedder=emb), {"granularity": "session", "retriever": "dense", "top_k": 1})
    m.reset()
    for s in _sessions():
        m.ingest(s)
    ctx = m.retrieve(Query("q", "pasta recipe carbonara", 3))
    assert [s.session_id for s in ctx.sessions] == ["s2"]
