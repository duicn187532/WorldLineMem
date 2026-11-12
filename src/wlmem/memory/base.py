"""Memory adapter interface.

A memory method plugs into every benchmark by implementing four methods. The runner
guarantees:

* ``reset()`` is called on a fresh instance before each case (cases never share memory);
* ``ingest(session)`` is called once per session, in chronological order, and only for
  sessions that happened before the query being answered;
* ``retrieve(query)`` sees the query text and its non-gold metadata, never the answer;
* gold labels (``Case.gold``) are never passed in.

Methods that call an LLM or an embedding model while writing or reading memory must use
``services.llm`` / ``services.embedder`` so their cost is metered separately from the
answer model.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable

from ..types import MemoryContext, Query, Session


@dataclass
class Services:
    llm: Any = None        # chat backend for memory-internal calls (extraction, consolidation, ...)
    embedder: Any = None   # embedding backend
    seed: int = 42


class MemoryAdapter(ABC):
    name: str = "base"

    def __init__(self, services: Services, **params: Any):
        self.services = services
        self.params = params

    @abstractmethod
    def reset(self) -> None: ...

    @abstractmethod
    def ingest(self, session: Session) -> None: ...

    @abstractmethod
    def retrieve(self, query: Query) -> MemoryContext: ...

    def describe(self) -> dict[str, Any]:
        """Configuration recorded in the run manifest."""
        return {"method": self.name, **self.params}

    def size(self) -> dict[str, Any]:
        """Current memory footprint, logged after each case (units, characters, ...)."""
        return {}


REGISTRY: dict[str, Callable[..., MemoryAdapter]] = {}


def register(name: str):
    def deco(cls):
        cls.name = name
        REGISTRY[name] = cls
        return cls
    return deco


def make_memory(method: str, services: Services, params: dict[str, Any]) -> MemoryAdapter:
    if method not in REGISTRY:
        raise ValueError(f"unknown memory method {method!r}; available: {sorted(REGISTRY)}")
    return REGISTRY[method](services, **params)
