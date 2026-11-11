"""Benchmark interface and helpers for loading the pinned official code."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from abc import ABC, abstractmethod
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, Iterator

from ..types import Case, MemoryContext, Query

REPO_ROOT = Path(__file__).resolve().parents[3]


def external_root() -> Path:
    return Path(os.environ.get("WLMEM_EXTERNAL", REPO_ROOT / "external")).resolve()


def lock() -> dict[str, Any]:
    return json.loads((REPO_ROOT / "external.lock.json").read_text(encoding="utf-8"))


def repo_dir(name: str) -> Path:
    return external_root() / "repos" / name


def data_file(name: str, fname: str) -> Path:
    p = external_root() / "data" / name / fname
    if not p.exists():
        raise FileNotFoundError(f"{p} missing. Run: python scripts/setup_external.py --only {name}")
    return p


def check_official_checkout(name: str) -> dict[str, Any]:
    """Refuse to run against an official checkout that is not the pinned, unmodified commit."""
    d = repo_dir(name)
    if not (d / ".git").exists():
        raise FileNotFoundError(f"{d} missing. Run: python scripts/setup_external.py --only {name}")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=d, capture_output=True, text=True, check=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=d, capture_output=True, text=True, check=True).stdout.strip()
    pinned = lock()["repos"][name]["commit"]
    if head != pinned:
        raise RuntimeError(f"{name}: checkout is at {head}, pinned commit is {pinned}")
    if dirty:
        raise RuntimeError(f"{name}: official checkout has local modifications:\n{dirty}")
    return {"repo": lock()["repos"][name]["url"], "commit": head}


_MODULES: dict[str, ModuleType] = {}


def load_official(name: str, relpath: str, extra_paths: list[str] = ()) -> ModuleType:
    """Import a file from an official repository without copying or editing it."""
    key = f"{name}:{relpath}"
    if key in _MODULES:
        return _MODULES[key]
    check_official_checkout(name)
    base = repo_dir(name)
    path = base / relpath
    for p in [path.parent, *(base / e for e in extra_paths)]:
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    mod_name = f"_official_{name}_{Path(relpath).stem}"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    _MODULES[key] = mod
    return mod


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


class Benchmark(ABC):
    name: str = "base"

    def __init__(self, **params: Any):
        self.params = params

    @abstractmethod
    def cases(self) -> Iterator[Case]:
        """Yield cases in a fixed order. Honour params ``limit`` and ``case_ids``."""

    @abstractmethod
    def render(self, case: Case, query: Query, ctx: MemoryContext) -> list[dict[str, str]]:
        """Build the answer-model messages with the benchmark's official prompt."""

    def answer_kwargs(self) -> dict[str, Any]:
        """Per-benchmark generation settings taken from the official code (e.g. max tokens)."""
        return {}

    @abstractmethod
    def evaluate(self, records: list[dict[str, Any]], judge: Any, out_dir: Path) -> dict[str, Any]:
        """Score answer records with the official metric code; write official-format files."""

    @abstractmethod
    def describe(self) -> dict[str, Any]:
        """Dataset file, hash, official commit, variant: recorded in the run manifest."""

    def _select(self, ids: list[str]) -> list[str]:
        wanted = self.params.get("case_ids") or []
        if wanted:
            missing = set(wanted) - set(ids)
            if missing:
                raise ValueError(f"unknown case ids: {sorted(missing)[:5]}")
            ids = [i for i in ids if i in set(wanted)]
        limit = self.params.get("limit")
        return ids[:limit] if limit else ids


class AsyncOpenAIShim:
    """Duck-typed ``AsyncOpenAI`` so official async judge code can call a local backend.

    Only ``client.chat.completions.create(model, messages, temperature, response_format,
    max_tokens)`` is implemented, which is all the official STALE judge uses.
    """

    def __init__(self, backend: Any):
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))
        self.backend = backend

    async def _create(self, model: str, messages: list[dict[str, str]], temperature: float = 0.0,
                      response_format: dict | None = None, max_tokens: int | None = None, **_: Any):
        json_mode = bool(response_format and response_format.get("type") == "json_object")
        r = self.backend.chat(messages, json_mode=json_mode, temperature=temperature, max_tokens=max_tokens)
        usage = SimpleNamespace(prompt_tokens=r.prompt_tokens or 0, completion_tokens=r.completion_tokens or 0,
                                total_tokens=(r.prompt_tokens or 0) + (r.completion_tokens or 0))
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=r.text))], usage=usage)


class GenerateResponseShim:
    """Duck-typed client for Memora's ``ModelEvaluator(api_client)``."""

    def __init__(self, backend: Any):
        self.backend = backend
        self.model = getattr(backend, "model", "unknown")

    def generate_response(self, system_prompt: str, user_prompt: str, temperature: float = 0.7, **_: Any) -> str:
        msgs = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
        return self.backend.chat(msgs, temperature=temperature).text
