"""Run a (benchmark, memory method, answer model) configuration and log everything.

Output directory ``<output_dir>/<run.name>/``:
    config.toml        the exact config used (copied)
    manifest.json      versions, hashes, model digests, git commit, label
    answers.jsonl      one line per query (answer, costs, retrieved ids, prompt hash)
    cases.jsonl        one line per finished case (ingest cost, memory size)
    errors.jsonl       failures, with traceback; the query is retried on resume
    prompts.jsonl      full prompts, only when [run] save_prompts = true
    eval/              written by ``wlmem evaluate``

Resuming: re-running the same config skips queries already in answers.jsonl. A case
with unfinished queries is rebuilt from scratch (memory is re-ingested), so resumed
results are identical to uninterrupted ones for deterministic methods.
"""
from __future__ import annotations

import hashlib
import json
import platform
import shutil
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__
from .backends import make_chat, make_embedder
from .benchmarks import make_benchmark
from .benchmarks.base import REPO_ROOT
from .config import Config
from .memory import Services, make_memory
from .textutil import estimate_tokens


def _git_state() -> dict[str, Any]:
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "src", "configs"], cwd=REPO_ROOT,
                                    capture_output=True, text=True).stdout.strip())
        return {"commit": commit, "dirty_src_or_configs": dirty}
    except Exception as e:
        return {"error": str(e)}


def _label(cfg: Config, answer: Any, benchmark: Any = None) -> str:
    if getattr(answer, "is_mock", False):
        return "PIPELINE_CHECK_MOCK_MODEL (not a result)"
    label = cfg.run.get("label", "local_adaptation")
    # protocols defined in this repository must never be read as official benchmark results
    return f"derived_protocol:{label}" if getattr(benchmark, "derived_protocol", False) else label


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _append(path: Path, obj: dict[str, Any]) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def run(cfg: Config) -> Path:
    out = Path(cfg.run.get("output_dir", REPO_ROOT / "runs")) / cfg.run["name"]
    out.mkdir(parents=True, exist_ok=True)
    cache_dir = Path(cfg.run.get("cache_dir", REPO_ROOT / ".cache"))

    benchmark = make_benchmark(cfg.benchmark["name"], {k: v for k, v in cfg.benchmark.items() if k != "name"})
    answer = make_chat(cfg.answer_model)
    memory_llm = make_chat(cfg.memory_model) if cfg.memory_model else None
    embedder = make_embedder(cfg.embedding, cache_dir)
    seed = int(cfg.run.get("seed", 42))
    method = cfg.memory["method"]
    mparams = {k: v for k, v in cfg.memory.items() if k != "method"}

    manifest_path = out / "manifest.json"
    manifest = {
        "label": _label(cfg, answer, benchmark),
        "run_name": cfg.run["name"],
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "wlmem_version": __version__,
        "git": _git_state(),
        "python": sys.version,
        "platform": platform.platform(),
        "seed": seed,
        "benchmark": benchmark.describe(),
        "memory": make_memory(method, Services(memory_llm, embedder, seed), mparams).describe(),
        "answer_model": answer.describe(),
        "memory_model": memory_llm.describe() if memory_llm else None,
        "embedding": embedder.describe() if embedder else None,
        "config_sha256": hashlib.sha256(cfg.text.encode("utf-8")).hexdigest(),
    }
    if manifest_path.exists():
        old = json.loads(manifest_path.read_text(encoding="utf-8"))
        if old.get("config_sha256") != manifest["config_sha256"]:
            raise RuntimeError(f"{out} was produced by a different config. Use a new [run] name.")
        manifest["resumed_from"] = old.get("created_utc")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    if cfg.path:
        shutil.copyfile(cfg.path, out / "config.toml")

    done = {r["query_id"] for r in _read_jsonl(out / "answers.jsonl")}
    save_prompts = bool(cfg.run.get("save_prompts", False))
    gen_kwargs = benchmark.answer_kwargs()
    gen_kwargs.update(cfg.run.get("answer_overrides", {}))
    print(f"[run] {cfg.run['name']}: benchmark={cfg.benchmark['name']} method={method} model={getattr(answer, 'model', '?')}")
    print(f"[run] label: {manifest['label']}; {len(done)} queries already done")

    n_new = 0
    for case in benchmark.cases():
        pending = [q for q in case.queries if q.query_id not in done]
        if not pending:
            continue
        services = Services(llm=memory_llm, embedder=embedder, seed=seed)
        mem = make_memory(method, services, mparams)
        mem.reset()
        meters0 = _meters(memory_llm, embedder)
        t_case = time.perf_counter()
        ingest_s = 0.0
        ingested = 0
        for q in sorted(case.queries, key=lambda q: q.visible_sessions):
            while ingested < q.visible_sessions:
                t0 = time.perf_counter()
                mem.ingest(case.sessions[ingested])
                ingest_s += time.perf_counter() - t0
                ingested += 1
            if q.query_id in done:
                continue
            try:
                t0 = time.perf_counter()
                ctx = mem.retrieve(q)
                retrieve_s = time.perf_counter() - t0
                messages = benchmark.render(case, q, ctx)
                prompt_text = "\n".join(m["content"] for m in messages)
                est_tokens = estimate_tokens(prompt_text)
                # Second guard besides the backend's own count: with prompt caching Ollama
                # may report only the uncached part of the prompt.
                num_ctx = getattr(answer, "num_ctx", None)
                reserve = gen_kwargs.get("max_tokens") or getattr(answer, "num_predict", 0)
                overflow_risk = bool(num_ctx and est_tokens + reserve > num_ctx)
                res = answer.chat(messages, **gen_kwargs)
                rec = {
                    "query_id": q.query_id,
                    "case_id": case.case_id,
                    "method": method,
                    "query_meta": q.meta,
                    "query_context": q.context,
                    "response": res.text,
                    "answer": {
                        "prompt_tokens": res.prompt_tokens,
                        "completion_tokens": res.completion_tokens,
                        "latency_s": round(res.latency_s, 3),
                        "done_reason": res.done_reason,
                        "ctx_overflow": res.ctx_overflow,
                        "ctx_overflow_risk": overflow_risk,
                        "thinking_chars": len(res.thinking or ""),
                    },
                    "prompt_sha256": hashlib.sha256(prompt_text.encode("utf-8")).hexdigest(),
                    "prompt_chars": len(prompt_text),
                    "prompt_est_tokens": est_tokens,
                    "sessions_visible": q.visible_sessions,
                    "retrieved_ids": ctx.retrieved_ids,
                    "memory_stats": ctx.stats,
                    "retrieve_s": round(retrieve_s, 4),
                    "ts_utc": datetime.now(timezone.utc).isoformat(),
                }
                _append(out / "answers.jsonl", rec)
                if save_prompts:
                    _append(out / "prompts.jsonl", {"query_id": q.query_id, "messages": messages})
                if res.ctx_overflow or overflow_risk:
                    print(f"  [WARN] {q.query_id}: prompt (~{est_tokens} est. tokens, backend {res.prompt_tokens}) "
                          f"may exceed num_ctx={num_ctx}; the backend truncates silently")
                done.add(q.query_id)
                n_new += 1
            except Exception as e:  # keep going; the query is retried on the next run
                _append(out / "errors.jsonl", {"query_id": q.query_id, "case_id": case.case_id, "error": repr(e),
                                               "traceback": traceback.format_exc(), "ts_utc": datetime.now(timezone.utc).isoformat()})
                print(f"  [ERROR] {q.query_id}: {e!r}")
        meters1 = _meters(memory_llm, embedder)
        _append(out / "cases.jsonl", {
            "case_id": case.case_id,
            "n_sessions": len(case.sessions),
            "sessions_ingested": ingested,
            "ingest_s": round(ingest_s, 3),
            "case_wall_s": round(time.perf_counter() - t_case, 3),
            "memory_size": mem.size(),
            "memory_llm": _diff(meters0["llm"], meters1["llm"]),
            "embedding": _diff(meters0["emb"], meters1["emb"]),
        })
        print(f"  case {case.case_id}: {len(pending)} queries, ingest {ingest_s:.1f}s")
    print(f"[run] finished: {n_new} new answers -> {out}")
    return out


def _meters(llm: Any, emb: Any) -> dict[str, dict[str, Any]]:
    return {"llm": llm.meter.snapshot() if llm else {}, "emb": emb.meter.snapshot() if emb else {}}


def _diff(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    return {k: round(b[k] - a.get(k, 0), 3) for k in b}


def evaluate(cfg: Config, judge_cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    out = Path(cfg.run.get("output_dir", REPO_ROOT / "runs")) / cfg.run["name"]
    records = _read_jsonl(out / "answers.jsonl")
    if not records:
        raise RuntimeError(f"no answers in {out}; run first")
    benchmark = make_benchmark(cfg.benchmark["name"], {k: v for k, v in cfg.benchmark.items() if k != "name"})
    judge = make_chat(judge_cfg or cfg.judge)
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    eval_dir = out / "eval" / _safe(getattr(judge, "model", "judge"))
    eval_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    metrics = benchmark.evaluate(records, judge, eval_dir)
    expected = sum(len(c.queries) for c in benchmark.cases())
    label = manifest["label"]
    if getattr(judge, "is_mock", False):
        label = "PIPELINE_CHECK_MOCK_JUDGE (not a result)"
    report = {
        "label": label,
        "complete": len(records) >= expected,
        "answered_queries": len(records),
        "expected_queries": expected,
        "judge": judge.describe(),
        "judge_cost": judge.meter.snapshot(),
        "eval_wall_s": round(time.perf_counter() - t0, 2),
        "answer_cost": _answer_cost(records),
        "metrics": metrics,
        "evaluated_utc": datetime.now(timezone.utc).isoformat(),
    }
    (eval_dir / "metrics.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("label", "complete", "answered_queries", "expected_queries")}, ensure_ascii=False))
    print(json.dumps(metrics, ensure_ascii=False, indent=2)[:4000])
    print(f"[eval] -> {eval_dir / 'metrics.json'}")
    return report


def _answer_cost(records: list[dict[str, Any]]) -> dict[str, Any]:
    pt = [r["answer"]["prompt_tokens"] or 0 for r in records]
    ct = [r["answer"]["completion_tokens"] or 0 for r in records]
    lat = [r["answer"]["latency_s"] for r in records]
    return {
        "queries": len(records),
        "prompt_tokens_total": sum(pt),
        "prompt_tokens_mean": sum(pt) / len(pt),
        "completion_tokens_total": sum(ct),
        "latency_s_mean": sum(lat) / len(lat),
        "ctx_overflows": sum(bool(r["answer"].get("ctx_overflow")) for r in records),
        "ctx_overflow_risks": sum(bool(r["answer"].get("ctx_overflow_risk")) for r in records),
    }


def _safe(s: str) -> str:
    return "".join(c if c.isalnum() or c in "-._" else "_" for c in s)
