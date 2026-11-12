"""Reference baselines that need no external service.

no_memory     answers from the question alone (lower bound)
full_context  the whole visible history, oldest sessions dropped first if over budget
rag           retrieval over sessions or user/assistant rounds (BM25 or dense embeddings)

They are deliberately plain: they are the comparison floor, not tuned systems.

``full_context`` and ``rag`` take ``scope``:
    "global"   (default) every stored session is eligible
    "context"  only sessions whose ``Session.context`` equals ``Query.context``. This is
               hard isolation by a signal the benchmark supplies; it is an oracle reference
               for multi-context protocols, not a method. It fails loudly when the
               benchmark supplies no signal.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from ..textutil import BM25, estimate_tokens
from ..types import MemoryContext, Query, Session, Turn
from .base import MemoryAdapter, register
from .decay import DecayCurve, days_between, parse_time


def session_text(turns: tuple[Turn, ...] | list[Turn]) -> str:
    return "\n".join(f"{t.role}: {t.content}" for t in turns)


def _scope(params: dict[str, Any]) -> str:
    scope = params.get("scope", "global")
    if scope not in ("global", "context"):
        raise ValueError("scope must be 'global' or 'context'")
    return scope


def _in_scope(params: dict[str, Any], session: Session, query: Query) -> bool:
    if _scope(params) == "global":
        return True
    if query.context is None:
        raise ValueError("scope='context' needs a benchmark that sets Query.context (no context signal was given)")
    return session.context == query.context


@register("no_memory")
class NoMemory(MemoryAdapter):
    def reset(self) -> None:
        self.n_seen = 0

    def ingest(self, session: Session) -> None:
        self.n_seen += 1  # observed, not stored

    def retrieve(self, query: Query) -> MemoryContext:
        return MemoryContext(sessions=[], stats={"sessions_seen": self.n_seen})


@register("full_context")
class FullContext(MemoryAdapter):
    """Keep everything; at query time return the most recent sessions that fit the budget.

    params:
        max_context_tokens  budget for the history (cl100k estimate). Set it from the answer
                            model's num_ctx minus prompt template and answer length.
                            None means no limit.
    """

    def reset(self) -> None:
        _scope(self.params)
        self.sessions: list[Session] = []
        self.tokens: list[int] = []

    def ingest(self, session: Session) -> None:
        self.sessions.append(session)
        self.tokens.append(estimate_tokens(session_text(session.turns)))

    def retrieve(self, query: Query) -> MemoryContext:
        budget = self.params.get("max_context_tokens")
        eligible = [(s, t) for s, t in zip(self.sessions, self.tokens) if _in_scope(self.params, s, query)]
        keep = len(eligible)
        if budget is not None:
            total = 0
            keep = 0
            for _, tok in reversed(eligible):
                if total + tok > budget:
                    break
                total += tok
                keep += 1
        chosen = eligible[len(eligible) - keep:]
        return MemoryContext(
            sessions=[s for s, _ in chosen],
            retrieved_ids=[s.session_id for s, _ in chosen],
            stats={
                "sessions_total": len(self.sessions),
                "sessions_in_scope": len(eligible),
                "sessions_included": keep,
                "truncated": keep < len(eligible),
                "est_history_tokens": sum(t for _, t in chosen),
            },
        )

    def size(self) -> dict[str, Any]:
        return {"sessions": len(self.sessions), "est_tokens": sum(self.tokens)}


@dataclass
class _Unit:
    session: Session
    turn_idx: tuple[int, ...]
    text: str


@register("rag")
class RAG(MemoryAdapter):
    """Flat retrieval-augmented memory.

    params:
        granularity         "round" (a user turn plus the assistant reply that follows) or "session"
        retriever           "bm25" or "dense"
        top_k               number of units returned
        max_context_tokens  optional budget; lowest-ranked units are dropped first
        query_instruction   optional prefix for dense query embedding (model specific)
        scope               "global" | "context" (see module docstring)
        decay               optional table: FadeMem decay curve only (memory/decay.py):
                            lambda_base, beta, mu, importance, initial, plus
                            mode = "multiply" (rank by relevance x strength) or
                            "dormant" (drop units whose strength < dormant_threshold).
                            Time is the session timestamp; "now" is Query.asked_at, or the
                            latest ingested session when the benchmark gives no question time.
                            No access reinforcement: retrieval never changes strength.
    Retrieved units are regrouped into their sessions and returned in chronological order.
    """

    def reset(self) -> None:
        self.units: list[_Unit] = []
        self.vecs: list[np.ndarray] = []
        self.bm25 = BM25()
        _scope(self.params)
        g = self.params.get("granularity", "round")
        r = self.params.get("retriever", "bm25")
        if g not in ("round", "session"):
            raise ValueError("granularity must be 'round' or 'session'")
        if r not in ("bm25", "dense"):
            raise ValueError("retriever must be 'bm25' or 'dense'")
        if r == "dense" and self.services.embedder is None:
            raise ValueError("retriever='dense' needs an [embedding] section in the config")
        dp = self.params.get("decay")
        self.decay = DecayCurve.from_params(dp)
        self.decay_mode = (dp or {}).get("mode", "multiply")
        if self.decay_mode not in ("multiply", "dormant"):
            raise ValueError("decay.mode must be 'multiply' or 'dormant'")
        self.dormant_threshold = float((dp or {}).get("dormant_threshold", 0.15))
        self.latest = None

    def _split(self, s: Session) -> list[_Unit]:
        if self.params.get("granularity", "round") == "session":
            return [_Unit(s, tuple(range(len(s.turns))), session_text(s.turns))]
        units, i = [], 0
        while i < len(s.turns):
            idx = [i]
            if s.turns[i].role == "user" and i + 1 < len(s.turns) and s.turns[i + 1].role == "assistant":
                idx.append(i + 1)
            units.append(_Unit(s, tuple(idx), session_text([s.turns[j] for j in idx])))
            i = idx[-1] + 1
        return units

    def ingest(self, session: Session) -> None:
        t = parse_time(session.timestamp)
        if t is not None and (self.latest is None or t > self.latest):
            self.latest = t
        new = self._split(session)
        self.units.extend(new)
        if self.params.get("retriever", "bm25") == "bm25":
            for u in new:
                self.bm25.add(u.text)
        else:
            vecs = self.services.embedder.embed([u.text for u in new])
            self.vecs.extend(_normalise(np.asarray(v, dtype=np.float32)) for v in vecs)

    def retrieve(self, query: Query) -> MemoryContext:
        if not self.units:
            return MemoryContext(sessions=[], stats={"units": 0})
        if self.params.get("retriever", "bm25") == "bm25":
            scores = np.asarray(self.bm25.scores(query.text))
        else:
            q = (self.params.get("query_instruction") or "") + query.text
            qv = _normalise(np.asarray(self.services.embedder.embed([q])[0], dtype=np.float32))
            scores = (np.stack(self.vecs) @ qv + 1.0) / 2.0  # cosine mapped to [0, 1] so decay can scale it
        strengths = None
        if self.decay is not None:
            now = parse_time(query.asked_at) or self.latest
            strengths = np.asarray([self.decay.strength(days_between(parse_time(u.session.timestamp), now))
                                    for u in self.units])
            if self.decay_mode == "multiply":
                scores = scores * strengths
            else:
                scores = np.where(strengths >= self.dormant_threshold, scores, -np.inf)
        k = int(self.params.get("top_k", 10))
        order = [int(i) for i in np.argsort(-scores, kind="stable")
                 if np.isfinite(scores[int(i)]) and _in_scope(self.params, self.units[int(i)].session, query)][:k]
        budget = self.params.get("max_context_tokens")
        picked, used = [], 0
        for i in order:
            tok = estimate_tokens(self.units[i].text)
            if budget is not None and used + tok > budget:
                continue
            picked.append(int(i))
            used += tok
        # regroup into partial sessions, chronological
        by_session: dict[str, tuple[Session, set[int]]] = {}
        for i in picked:
            u = self.units[i]
            by_session.setdefault(u.session.session_id, (u.session, set()))[1].update(u.turn_idx)
        sessions = []
        for s, idx in sorted(by_session.values(), key=lambda x: x[0].order):
            turns = tuple(s.turns[j] for j in sorted(idx))
            sessions.append(Session(s.session_id, s.order, s.timestamp, turns, s.display, s.context))
        return MemoryContext(
            sessions=sessions,
            retrieved_ids=[f"{self.units[i].session.session_id}:{','.join(map(str, self.units[i].turn_idx))}" for i in picked],
            stats={
                "units": len(self.units),
                "returned_units": len(picked),
                "top_scores": [round(float(scores[i]), 4) for i in picked[:5]],
                **({"dormant_units": int(np.sum(strengths < self.dormant_threshold)),
                    "min_returned_strength": round(float(min(strengths[i] for i in picked)), 4) if picked else None}
                   if strengths is not None else {}),
                "est_history_tokens": used,
            },
        )

    def size(self) -> dict[str, Any]:
        return {"units": len(self.units), "chars": sum(len(u.text) for u in self.units)}


def _normalise(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    return v / n if n else v
