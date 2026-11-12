"""Memory strength under time decay, for diagnosing how forgetting interacts with retrieval.

PARTIAL REIMPLEMENTATION, not FadeMem. FadeMem (arXiv:2601.18642v2) releases no code. This
module implements only its decay curve, eq. (4)-(6):

    v_i(t)  = v_i(0) * exp(-lambda_i * (t - tau_i) ** beta_i)          (4)
    lambda_i = lambda_base * exp(-mu * I_i(t))                          (5)
    beta_i  = 0.8 for long-term layer, 1.2 for short-term layer         (6)

with t in days. The paper reports lambda_base = 0.1 and the beta values above; it does not
report mu or how I_i(t) is computed in practice, so the importance term is fixed here
(``importance`` param, default 0, i.e. the paper's own lambda_i = lambda_base case). Access
reinforcement (eq. 7), conflict resolution (eq. 8-10) and fusion (eq. 11-13) are NOT
implemented. Results using this module must be labelled "FadeMem decay curve only".
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any

_FORMATS = ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d (%a) %H:%M", "%Y-%m-%d", "%Y/%m/%d")


def parse_time(stamp: str | None) -> datetime | None:
    """Parse the timestamp formats used by the pinned benchmarks; None when unknown."""
    if not stamp:
        return None
    for fmt in _FORMATS:
        try:
            return datetime.strptime(stamp.strip(), fmt)
        except ValueError:
            continue
    return None


def days_between(earlier: datetime | None, later: datetime | None) -> float:
    if earlier is None or later is None:
        return 0.0
    return max(0.0, (later - earlier).total_seconds() / 86400.0)


@dataclass(frozen=True)
class DecayCurve:
    """Strength as a function of elapsed days. lambda_base = 0 disables decay."""

    lambda_base: float = 0.1
    beta: float = 1.2
    mu: float = 0.0
    importance: float = 0.0
    initial: float = 1.0

    @classmethod
    def from_params(cls, p: dict[str, Any] | None) -> "DecayCurve | None":
        if not p:
            return None
        allowed = {"lambda_base", "beta", "mu", "importance", "initial"}
        unknown = set(p) - allowed - {"mode", "dormant_threshold"}
        if unknown:
            raise ValueError(f"unknown decay params: {sorted(unknown)}")
        return cls(**{k: float(v) for k, v in p.items() if k in allowed})

    def strength(self, elapsed_days: float) -> float:
        lam = self.lambda_base * math.exp(-self.mu * self.importance)
        if lam <= 0:
            return self.initial
        return self.initial * math.exp(-lam * max(0.0, elapsed_days) ** self.beta)

    def half_life_days(self) -> float:
        lam = self.lambda_base * math.exp(-self.mu * self.importance)
        return float("inf") if lam <= 0 else (math.log(2) / lam) ** (1.0 / self.beta)
