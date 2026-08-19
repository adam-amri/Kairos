"""Detecteur d'arbitrage a N jambes — implementation Python.

Sert deux fins : le prototypage, et la VALIDATION CROISEE du noyau C++. Les deux
implementations doivent produire les memes chiffres a 1e-12 pres sur les memes
entrees ; toute divergence est un bug dans l'une des deux.

LA CONVENTION DE COTATION
    Une paire BASE/QUOTE se lit « QUOTE par BASE ». GBP/USD = 1,2715 signifie
    1,2715 USD par GBP. Convertir GBP -> USD MULTIPLIE par le bid ; USD -> GBP
    DIVISE par le ask. Une implementation qui multiplie dans les deux sens
    calcule, pour l'aller-retour, 1,2715^2 = 1,6167 : une deviation fictive de
    +6 167 bps.

LA BASE DE MESURE
    Mid        — le spread n'est pas dans la deviation, on l'ajoute au cout.
    Executable — le spread est deja paye dans le produit des taux ; seul reste
                 la commission. C'est la base de evaluate(), qui prend bid/ask.
    Melanger les deux compte le spread deux fois : mesure a 0,420 bps d'erreur
    sur trois jambes, et davantage a spread plus large.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from itertools import combinations, permutations


class DeviationBasis(str, Enum):
    MID = "mid"
    EXECUTABLE = "executable"


@dataclass(frozen=True)
class PairQuote:
    base: str
    quote: str
    bid: float
    ask: float

    def __post_init__(self) -> None:
        if not (self.bid > 0 and self.ask > 0 and self.ask >= self.bid):
            raise ValueError(f"cotation invalide pour {self.base}/{self.quote}")

    @property
    def mid(self) -> float:
        return 0.5 * (self.bid + self.ask)

    @property
    def spread_bps(self) -> float:
        m = self.mid
        return (self.ask - self.bid) / m * 10_000 if m > 0 else 0.0


@dataclass(frozen=True)
class Leg:
    frm: str
    to: str
    pair: str
    rate: float
    inverted: bool
    spread_bps: float


@dataclass
class CostModel:
    commission_bps: float = 0.20
    commission_floor: float = 2.00
    slippage_bps: float = 0.0

    def leg_cost_bps(self, notional: float, spread_bps: float) -> float:
        comm = max(self.commission_bps, self.commission_floor / notional * 10_000)
        return comm + spread_bps / 2.0 + self.slippage_bps


@dataclass
class Opportunity:
    legs: list[Leg]
    gross_bps: float
    cost_bps: float
    net_bps: float
    notional: float

    @property
    def n_legs(self) -> int:
        return len(self.legs)

    @property
    def profitable(self) -> bool:
        return self.net_bps > 0.0

    @property
    def path(self) -> list[str]:
        return [self.legs[0].frm] + [l.to for l in self.legs] if self.legs else []

    def path_string(self) -> str:
        return " -> ".join(self.path)


class Detector:
    def __init__(self) -> None:
        self._names: list[str] = []
        self._ids: dict[str, int] = {}
        self._quotes: dict[tuple[int, int], PairQuote] = {}

    def _intern(self, c: str) -> int:
        if c not in self._ids:
            self._ids[c] = len(self._names)
            self._names.append(c)
        return self._ids[c]

    def add_pair(self, q: PairQuote) -> None:
        self._quotes[(self._intern(q.base), self._intern(q.quote))] = q

    @property
    def currencies(self) -> list[str]:
        return list(self._names)

    def resolve(self, frm: int | str, to: int | str) -> Leg | None:
        f = self._ids.get(frm) if isinstance(frm, str) else frm
        t = self._ids.get(to) if isinstance(to, str) else to
        if f is None or t is None:
            return None
        if (q := self._quotes.get((f, t))) is not None:
            # Paire cotee dans ce sens : on VEND la base -> bid
            return Leg(self._names[f], self._names[t],
                       f"{self._names[f]}/{self._names[t]}", q.bid, False, q.spread_bps)
        if (q := self._quotes.get((t, f))) is not None:
            # Paire cotee a l'envers : on ACHETE la base -> 1 / ask
            return Leg(self._names[f], self._names[t],
                       f"{self._names[t]}/{self._names[f]}", 1.0 / q.ask, True, q.spread_bps)
        return None

    def enumerate_cycles(self, k: int) -> list[list[int]]:
        """Cycles diriges distincts : rotations identifiees, sens distincts."""
        n = len(self._names)
        if k < 2 or k > n:
            return []
        out = []
        for combo in combinations(range(n), k):
            anchor, rest = combo[0], sorted(combo[1:])
            for perm in permutations(rest):
                cyc = [anchor, *perm]
                if all(self.resolve(cyc[i], cyc[(i + 1) % k]) for i in range(k)):
                    out.append(cyc)
        return out

    def evaluate(self, cycle: list[int]) -> tuple[list[Leg], float] | None:
        legs, product = [], 1.0
        for i in range(len(cycle)):
            leg = self.resolve(cycle[i], cycle[(i + 1) % len(cycle)])
            if leg is None:
                return None
            product *= leg.rate
            legs.append(leg)
        return legs, (product - 1.0) * 10_000

    def scan(self, cost: CostModel, notional: float, min_legs: int = 3,
             max_legs: int = 5, only_profitable: bool = True,
             basis: DeviationBasis = DeviationBasis.EXECUTABLE) -> list[Opportunity]:
        out: list[Opportunity] = []
        for k in range(min_legs, max_legs + 1):
            for cyc in self.enumerate_cycles(k):
                ev = self.evaluate(cyc)
                if ev is None:
                    continue
                legs, gross = ev
                c = sum(cost.leg_cost_bps(
                    notional, l.spread_bps if basis is DeviationBasis.MID else 0.0)
                    for l in legs)
                o = Opportunity(legs, gross, c, gross - c, notional)
                if not only_profitable or o.profitable:
                    out.append(o)
        out.sort(key=lambda o: o.net_bps, reverse=True)
        return out
