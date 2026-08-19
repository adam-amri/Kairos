"""Types d'evenements normalises.

Regle d'architecture : aucune specificite de venue ne franchit cette frontiere.
Chaque connecteur traduit vers ces types et rien d'autre ne circule en aval.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict


@dataclass(slots=True, frozen=True)
class Quote:
    """Meilleure limite des deux cotes, a un instant donne."""

    venue: str
    symbol: str          # forme canonique "EUR/USD"
    bid: float
    ask: float
    bid_size: float
    ask_size: float

    # Trois horloges, et il faut les trois.
    ts_venue_ns: int     # horodatage annonce par le venue (peut etre faux ou absent)
    ts_wall_ns: int      # heure murale locale a la reception (comparable entre machines)
    ts_mono_ns: int      # horloge monotone locale (seule valide pour un delta de latence)

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0

    @property
    def spread_bps(self) -> float:
        m = self.mid
        return (self.ask - self.bid) / m * 10_000 if m else float("nan")

    @property
    def latency_ns(self) -> int:
        """Ecart venue -> reception. Negatif = horloges desynchronisees (verifier NTP)."""
        return self.ts_wall_ns - self.ts_venue_ns if self.ts_venue_ns else 0

    def as_row(self) -> dict:
        d = asdict(self)
        d["spread_bps"] = self.spread_bps
        d["latency_us"] = self.latency_ns / 1_000
        return d
