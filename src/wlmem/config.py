"""TOML run configuration. See configs/README.md for every key."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REQUIRED = ("run", "benchmark", "memory", "answer_model")


@dataclass
class Config:
    run: dict[str, Any]
    benchmark: dict[str, Any]
    memory: dict[str, Any]
    answer_model: dict[str, Any]
    judge: dict[str, Any] = field(default_factory=dict)
    embedding: dict[str, Any] | None = None
    memory_model: dict[str, Any] | None = None
    text: str = ""
    path: Path | None = None

    @classmethod
    def load(cls, path: str | Path) -> "Config":
        p = Path(path)
        text = p.read_text(encoding="utf-8")
        data = tomllib.loads(text)
        missing = [k for k in REQUIRED if k not in data]
        if missing:
            raise ValueError(f"{p}: missing sections {missing}")
        unknown = set(data) - set(REQUIRED) - {"judge", "embedding", "memory_model"}
        if unknown:
            raise ValueError(f"{p}: unknown sections {sorted(unknown)}")
        for key in ("name",):
            if key not in data["run"]:
                raise ValueError(f"{p}: [run] needs '{key}'")
        if "method" not in data["memory"]:
            raise ValueError(f"{p}: [memory] needs 'method'")
        if any("CHANGE_ME" in line.split("#")[0] for line in text.splitlines()):
            raise ValueError(f"{p}: replace every CHANGE_ME value (model names, run name) before running")
        return cls(
            run=data["run"],
            benchmark=data["benchmark"],
            memory=data["memory"],
            answer_model=data["answer_model"],
            judge=data.get("judge", {}),
            embedding=data.get("embedding"),
            memory_model=data.get("memory_model"),
            text=text,
            path=p,
        )
