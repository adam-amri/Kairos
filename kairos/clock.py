"""Horloges.

time.time_ns()        -> heure murale. Peut sauter (NTP, changement d'heure).
time.perf_counter_ns()-> monotone. Ne saute jamais. La SEULE base valide pour
                         mesurer une duree.

Confondre les deux produit des latences negatives et des backtests faux.
"""
from __future__ import annotations
import time


def wall_ns() -> int:
    return time.time_ns()


def mono_ns() -> int:
    return time.perf_counter_ns()


class LatencyTracker:
    """Accumule des deltas et restitue des quantiles.

    On garde les quantiles hauts : une moyenne de latence ne dit rien d'utile,
    c'est la queue de distribution qui decide si une strategie passe ou non.
    """

    def __init__(self) -> None:
        self._samples: list[int] = []

    def record(self, delta_ns: int) -> None:
        self._samples.append(delta_ns)

    def summary(self) -> dict:
        if not self._samples:
            return {}
        s = sorted(self._samples)
        n = len(s)

        def q(p: float) -> float:
            return s[min(int(p * n), n - 1)] / 1_000  # microsecondes

        return {
            "n": n,
            "p50_us": round(q(0.50), 1),
            "p95_us": round(q(0.95), 1),
            "p99_us": round(q(0.99), 1),
            "max_us": round(s[-1] / 1_000, 1),
        }
