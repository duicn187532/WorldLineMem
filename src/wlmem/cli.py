"""Command line entry point.

    wlmem run configs/smoke/longmemeval_oracle_full_context.toml
    wlmem evaluate configs/smoke/longmemeval_oracle_full_context.toml
    wlmem verify-data [stale longmemeval memora]
    wlmem check-ollama --model qwen3:8b
    wlmem methods
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys


def _ensure_utf8() -> None:
    """On Windows the default file encoding follows the locale (cp950 for zh-TW). The
    official benchmark code opens files without an encoding argument in places, so the
    process is restarted in Python UTF-8 mode."""
    if os.name == "nt" and not sys.flags.utf8_mode and os.environ.get("WLMEM_NO_REEXEC") != "1":
        env = dict(os.environ, PYTHONUTF8="1", WLMEM_NO_REEXEC="1")
        sys.exit(subprocess.call([sys.executable, "-X", "utf8", "-m", "wlmem.cli", *sys.argv[1:]], env=env))


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8()
    ap = argparse.ArgumentParser(prog="wlmem")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run", help="generate answers for a config")
    p.add_argument("config")
    p = sub.add_parser("evaluate", help="score a finished run with the official metric")
    p.add_argument("config")
    p = sub.add_parser("verify-data", help="check pinned datasets and report known quirks")
    p.add_argument("names", nargs="*")
    p = sub.add_parser("check-ollama", help="one tiny chat call to confirm the server and model")
    p.add_argument("--model", required=True)
    p.add_argument("--base-url", default="http://127.0.0.1:11434")
    sub.add_parser("methods", help="list registered memory methods")
    args = ap.parse_args(argv)

    if args.cmd == "run":
        from .config import Config
        from .runner import run
        run(Config.load(args.config))
    elif args.cmd == "evaluate":
        from .config import Config
        from .runner import evaluate
        evaluate(Config.load(args.config))
    elif args.cmd == "verify-data":
        from .integrity import verify
        return 0 if verify(args.names or None) else 1
    elif args.cmd == "check-ollama":
        from .backends import OllamaChat, check_truncation_guard
        b = OllamaChat(args.model, base_url=args.base_url, num_ctx=2048, num_predict=16)
        r = b.chat([{"role": "user", "content": "Reply with the single word: ready"}])
        guard = check_truncation_guard(args.base_url, args.model)
        print(json.dumps({"reply": r.text, "prompt_tokens": r.prompt_tokens, "latency_s": round(r.latency_s, 2),
                          "rejects_over_long_prompts": guard, "model": b.describe()}, ensure_ascii=False, indent=2))
        if not guard:
            print("WARNING: this Ollama truncates over-long prompts silently (truncate=false not honoured). "
                  "Upgrade Ollama, or rely on ctx_overflow_risk only.")
            return 1
    elif args.cmd == "methods":
        from .memory import REGISTRY
        print("\n".join(sorted(REGISTRY)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
