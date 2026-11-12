"""Model backends: chat (answer / judge) and embeddings.

Ollama is called through its native HTTP API (``/api/chat``, ``/api/embed``) rather than
the OpenAI-compatible endpoint, because only the native API exposes ``think`` (needed to
switch off Qwen3-style reasoning output), ``num_ctx`` and the exact token counts.

By default Ollama silently cuts a prompt that is longer than ``num_ctx`` (in a test with
num_ctx=512 it kept 258 tokens and reported only those). Requests are therefore sent with
``truncate: false``: the server then rejects an over-long prompt with an error that names
its exact token count, the runner logs it in errors.jsonl, and no truncated answer is
ever recorded. ``wlmem check-ollama`` verifies that the installed Ollama honours this.

The mock backends exist only for unit tests and pipeline checks without a model. Their
outputs are labelled as mock in every log line and must never be reported as results.
"""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ChatResult:
    text: str
    prompt_tokens: int | None
    completion_tokens: int | None
    latency_s: float
    done_reason: str | None = None
    ctx_overflow: bool = False
    thinking: str | None = None


@dataclass
class CostMeter:
    """Counts calls and tokens; one instance per role (answer, memory, judge, embed)."""

    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    seconds: float = 0.0
    overflows: int = 0

    def add(self, r: ChatResult) -> None:
        self.calls += 1
        self.prompt_tokens += r.prompt_tokens or 0
        self.completion_tokens += r.completion_tokens or 0
        self.seconds += r.latency_s
        self.overflows += int(r.ctx_overflow)

    def snapshot(self) -> dict[str, Any]:
        return dict(self.__dict__)


def _post_json(url: str, payload: dict, timeout: float, retries: int = 3) -> dict:
    data = json.dumps(payload).encode("utf-8")
    last: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:  # 4xx is a request problem, do not retry
            body = e.read().decode("utf-8", "replace")
            if 400 <= e.code < 500:
                raise RuntimeError(f"Ollama {url} -> HTTP {e.code}: {body}") from e
            last = e
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last = e
        time.sleep(2 ** attempt)
    raise RuntimeError(f"Ollama request failed after {retries} attempts: {last}")


def _get_json(url: str, timeout: float = 10) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


class OllamaChat:
    def __init__(
        self,
        model: str,
        base_url: str = "http://127.0.0.1:11434",
        temperature: float = 0.0,
        seed: int = 42,
        num_ctx: int = 8192,
        num_predict: int = 512,
        think: bool | None = False,
        top_p: float | None = None,
        timeout_s: float = 1800,
        keep_alive: str = "30m",
        truncate: bool = False,
    ):
        self.model = model
        self.truncate = truncate
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature
        self.seed = seed
        self.num_ctx = num_ctx
        self.num_predict = num_predict
        self.think = think
        self.top_p = top_p
        self.timeout_s = timeout_s
        self.keep_alive = keep_alive
        self.meter = CostMeter()

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        json_mode: bool = False,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> ChatResult:
        options: dict[str, Any] = {
            "temperature": self.temperature if temperature is None else temperature,
            "seed": self.seed,
            "num_ctx": self.num_ctx,
            "num_predict": self.num_predict if max_tokens is None else max_tokens,
        }
        if self.top_p is not None:
            options["top_p"] = self.top_p
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": options,
            "keep_alive": self.keep_alive,
            "truncate": self.truncate,
        }
        if self.think is not None:
            payload["think"] = self.think
        if json_mode:
            payload["format"] = "json"
        t0 = time.perf_counter()
        out = _post_json(f"{self.base_url}/api/chat", payload, self.timeout_s)
        latency = time.perf_counter() - t0
        msg = out.get("message", {})
        prompt_tokens = out.get("prompt_eval_count")
        # truncate=False: an over-long prompt raised above, so nothing was cut.
        # truncate=True: Ollama does not report a cut; the runner's estimate-based
        # ctx_overflow_risk is the only signal, so this flag stays False.
        overflow = False
        r = ChatResult(
            text=msg.get("content", ""),
            prompt_tokens=prompt_tokens,
            completion_tokens=out.get("eval_count"),
            latency_s=latency,
            done_reason=out.get("done_reason"),
            ctx_overflow=overflow,
            thinking=msg.get("thinking"),
        )
        self.meter.add(r)
        return r

    def describe(self) -> dict[str, Any]:
        info: dict[str, Any] = {
            "backend": "ollama",
            "model": self.model,
            "base_url": self.base_url,
            "temperature": self.temperature,
            "seed": self.seed,
            "num_ctx": self.num_ctx,
            "num_predict": self.num_predict,
            "think": self.think,
            "top_p": self.top_p,
            "truncate": self.truncate,
        }
        info.update(ollama_model_info(self.base_url, self.model))
        return info


def check_truncation_guard(base_url: str, model: str) -> bool:
    """True if the server rejects an over-long prompt when truncate=false."""
    b = OllamaChat(model, base_url=base_url, num_ctx=256, num_predict=4)
    try:
        b.chat([{"role": "user", "content": " ".join(f"w{i}" for i in range(2000))}])
        return False
    except RuntimeError as e:
        return "exceeds" in str(e) or "context" in str(e)


class OllamaEmbedder:
    def __init__(
        self,
        model: str,
        base_url: str = "http://127.0.0.1:11434",
        num_ctx: int | None = None,
        batch_size: int = 32,
        cache_path: str | Path | None = None,
        timeout_s: float = 600,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.num_ctx = num_ctx
        self.batch_size = batch_size
        self.timeout_s = timeout_s
        self.meter = CostMeter()
        self.cache = EmbeddingCache(cache_path, f"ollama:{model}:{num_ctx}") if cache_path else None

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float] | None] = [None] * len(texts)
        todo = list(range(len(texts)))
        if self.cache:
            hits = self.cache.get_many(texts)
            todo = [i for i in todo if hits[i] is None]
            for i, v in enumerate(hits):
                if v is not None:
                    out[i] = v
        for start in range(0, len(todo), self.batch_size):
            idx = todo[start:start + self.batch_size]
            payload: dict[str, Any] = {"model": self.model, "input": [texts[i] for i in idx], "truncate": True}
            if self.num_ctx:
                payload["options"] = {"num_ctx": self.num_ctx}
            t0 = time.perf_counter()
            res = _post_json(f"{self.base_url}/api/embed", payload, self.timeout_s)
            self.meter.add(ChatResult("", res.get("prompt_eval_count"), 0, time.perf_counter() - t0))
            for i, vec in zip(idx, res["embeddings"]):
                out[i] = vec
            if self.cache:
                self.cache.put_many([texts[i] for i in idx], res["embeddings"])
        if any(v is None for v in out):
            raise RuntimeError("embedding backend returned fewer vectors than inputs")
        return out  # type: ignore[return-value]

    def describe(self) -> dict[str, Any]:
        info = {"backend": "ollama", "model": self.model, "num_ctx": self.num_ctx, "truncate": True}
        info.update(ollama_model_info(self.base_url, self.model))
        return info


class EmbeddingCache:
    """sqlite cache keyed by (model key, sha256(text)). Safe to share across runs."""

    def __init__(self, path: str | Path, model_key: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.model_key = model_key
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self.conn.execute("CREATE TABLE IF NOT EXISTS emb (k TEXT PRIMARY KEY, v TEXT)")

    def _key(self, text: str) -> str:
        return self.model_key + ":" + hashlib.sha256(text.encode("utf-8")).hexdigest()

    def get_many(self, texts: list[str]) -> list[list[float] | None]:
        with self._lock:
            res = []
            for t in texts:
                row = self.conn.execute("SELECT v FROM emb WHERE k=?", (self._key(t),)).fetchone()
                res.append(json.loads(row[0]) if row else None)
            return res

    def put_many(self, texts: list[str], vecs: list[list[float]]) -> None:
        with self._lock:
            self.conn.executemany(
                "INSERT OR REPLACE INTO emb VALUES (?, ?)",
                [(self._key(t), json.dumps(v)) for t, v in zip(texts, vecs)],
            )
            self.conn.commit()


def ollama_model_info(base_url: str, model: str) -> dict[str, Any]:
    """Digest, quantisation and native context length, for the run manifest."""
    info: dict[str, Any] = {}
    try:
        tags = _get_json(f"{base_url}/api/tags")
        for m in tags.get("models", []):
            if m.get("name") == model or m.get("model") == model:
                info["digest"] = m.get("digest")
                info["size_bytes"] = m.get("size")
        show = _post_json(f"{base_url}/api/show", {"model": model}, 30)
        info["details"] = show.get("details")
        info["native_context_length"] = next(
            (v for k, v in show.get("model_info", {}).items() if k.endswith("context_length")), None
        )
        info["ollama_version"] = _get_json(f"{base_url}/api/version").get("version")
    except Exception as e:  # informational only
        info["info_error"] = str(e)
    return info


# --------------------------------------------------------------------------- mocks


class MockChat:
    """Deterministic stand-in for tests. Never use for reported numbers."""

    is_mock = True

    def __init__(self, reply: str = "MOCK ANSWER", judge_reply: str | None = None, **_: Any):
        self.reply = reply
        self.judge_reply = judge_reply
        self.model = "mock"
        self.num_ctx = 10 ** 9
        self.meter = CostMeter()
        self.calls: list[list[dict[str, str]]] = []

    def chat(self, messages, *, json_mode=False, max_tokens=None, temperature=None) -> ChatResult:
        self.calls.append(messages)
        text = self.judge_reply if (json_mode and self.judge_reply is not None) else self.reply
        n_in = sum(len(m["content"]) for m in messages) // 4
        r = ChatResult(text=text, prompt_tokens=n_in, completion_tokens=len(text) // 4, latency_s=0.0)
        self.meter.add(r)
        return r

    def describe(self) -> dict[str, Any]:
        return {"backend": "mock", "reply": self.reply, "judge_reply": self.judge_reply}


class HashEmbedder:
    """Bag-of-words hashing embedder for tests (no model needed)."""

    is_mock = True

    def __init__(self, dim: int = 256, **_: Any):
        self.dim = dim
        self.meter = CostMeter()

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for t in texts:
            v = [0.0] * self.dim
            for w in t.lower().split():
                v[int(hashlib.md5(w.encode()).hexdigest(), 16) % self.dim] += 1.0
            n = math.sqrt(sum(x * x for x in v)) or 1.0
            out.append([x / n for x in v])
        self.meter.calls += 1
        return out

    def describe(self) -> dict[str, Any]:
        return {"backend": "hash", "dim": self.dim}


def make_chat(cfg: dict[str, Any]):
    cfg = dict(cfg)
    kind = cfg.pop("backend", "ollama")
    if kind == "ollama":
        return OllamaChat(**cfg)
    if kind == "mock":
        return MockChat(**cfg)
    raise ValueError(f"unknown chat backend {kind!r}")


def make_embedder(cfg: dict[str, Any] | None, cache_dir: Path | None = None):
    if not cfg:
        return None
    cfg = dict(cfg)
    kind = cfg.pop("backend", "ollama")
    if kind == "ollama":
        if cache_dir is not None and "cache_path" not in cfg:
            cfg["cache_path"] = cache_dir / "embeddings.sqlite"
        return OllamaEmbedder(**cfg)
    if kind == "hash":
        return HashEmbedder(**cfg)
    raise ValueError(f"unknown embedding backend {kind!r}")
