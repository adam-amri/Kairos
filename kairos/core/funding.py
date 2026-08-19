"""Evenement de funding — le revenu du cash and carry.

Le funding est un paiement periodique entre longs et shorts d'un perpetuel,
generalement toutes les 8 heures. Il arrime le prix du perpetuel a celui du spot.

Quand le funding est POSITIF, les longs paient les shorts. Etre short perpetuel
et long spot revient donc a encaisser ce flux tout en restant delta neutre.

Quand il devient NEGATIF, le flux s'inverse et on paie. C'est le risque principal
du modele economique, et il est frequent en regime baissier.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class FundingEvent:
    ts_ns: int
    rate_bps: float        # positif = les longs paient les shorts
    mark_price: float

    def payment(self, position: float) -> float:
        """Flux percu par une position donnee, en devise de cotation.

        position negative (short) et rate positif -> paiement recu.
        Le signe est donc inverse : -position * rate.
        """
        return -position * self.mark_price * self.rate_bps / 10_000
