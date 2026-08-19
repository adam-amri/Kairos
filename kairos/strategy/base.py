"""Interface de strategie — IDENTIQUE en backtest et en production.

C'est la regle architecturale centrale du projet. Si le chemin de code differait
entre simulation et live, l'ecart entre les deux serait inexplicable, et le
backtest ne prouverait rien sur le comportement reel.

Une strategie ne touche jamais le carnet. Elle observe et retourne des intentions.
Le moteur — ou le venue — decide de ce qui se passe ensuite. Cette separation est
ce qui rend la meme classe rejouable et testable.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from kairos.core.orders import Action, Fill
from kairos.core.portfolio import Portfolio
from kairos.events import Quote


class Strategy(ABC):
    @abstractmethod
    def on_quote(self, q: Quote, pf: Portfolio) -> list[Action] | None:
        """Appelee a chaque quote, dans l'ordre chronologique. Retourne des intentions."""

    def on_fill(self, fill: Fill) -> None:
        """Notification d'execution. Par defaut, sans effet."""
        return None
