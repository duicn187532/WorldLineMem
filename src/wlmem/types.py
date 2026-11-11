"""Benchmark-neutral data types shared by loaders, memory adapters and the runner."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Turn:
    role: str  # "user" or "assistant"
    content: str


@dataclass(frozen=True)
class Session:
    """One chat session as a memory method is allowed to see it.

    ``session_id`` is a neutral id assigned by the loader (e.g. "s0007"). Original dataset
    ids are kept in ``Case.gold`` because some of them reveal answers
    (LongMemEval evidence sessions are named ``answer_*``).
    ``timestamp`` is the dataset's own timestamp string, unparsed.
    ``order`` is the chronological position (0-based) within the case.
    ``display`` holds non-gold presentation fields an official prompt needs
    (for example Memora's numeric session id).
    ``context`` is an optional, non-gold signal about the situation the session happened
    in (who the agent was talking to, or an opaque token for one uninterrupted stretch of
    conversation). Only multi-context protocols set it; ``None`` means the benchmark gives
    no such signal and a method has to infer the situation from the content.
    """

    session_id: str
    order: int
    timestamp: str | None
    turns: tuple[Turn, ...]
    display: dict[str, Any] = field(default_factory=dict)
    context: str | None = None


@dataclass(frozen=True)
class Query:
    """One question asked after ``visible_sessions`` sessions have happened."""

    query_id: str
    text: str
    visible_sessions: int
    asked_at: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)  # non-gold, e.g. STALE probing dimension
    context: str | None = None  # same signal as Session.context, for the situation of the question


@dataclass
class Case:
    """An isolated evaluation unit. Memory is reset between cases."""

    case_id: str
    sessions: list[Session]
    queries: list[Query]
    gold: dict[str, Any] = field(default_factory=dict)  # never passed to memory adapters


@dataclass
class MemoryContext:
    """What a memory method hands to the answer prompt.

    Either ``sessions`` (whole or partial sessions, rendered with the benchmark's own
    history format) or ``text`` (free-form memory, e.g. extracted facts) must be set.
    """

    sessions: list[Session] | None = None
    text: str | None = None
    retrieved_ids: list[str] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)
