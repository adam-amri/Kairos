"""Contrat commun a tous les connecteurs."""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Callable, Iterator
from kairos.events import Quote


class Feed(ABC):
    """Une source d'evenements normalises.

    Le meme code de strategie doit pouvoir consommer un feed live, un feed
    synthetique ou un rejeu d'archive sans changer d'une ligne. C'est la seule
    defense contre l'ecart backtest/live.
    """

    name: str = "base"

    @abstractmethod
    def stream(self) -> Iterator[Quote]:
        """Produit des Quote jusqu'a epuisement ou interruption."""

    def run(self, on_quote: Callable[[Quote], None]) -> None:
        for q in self.stream():
            on_quote(q)
