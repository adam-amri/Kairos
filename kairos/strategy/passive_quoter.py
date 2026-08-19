"""Strategie de reference — cotation passive des deux cotes.

Son role n'est PAS de gagner de l'argent. C'est d'etre la ligne de base contre
laquelle tout le reste se mesure. Sans reference, on ne peut pas dire si un modele
de machine learning apporte quoi que ce soit : un Sharpe de 1,2 ne veut rien dire
si une regle triviale en fait 1,3.

Elle affiche un achat sous le mid et une vente au-dessus, a une distance fixe, et
se replie des que l'inventaire depasse une limite. C'est la forme la plus simple
d'un market making, deliberement naive.
"""
from __future__ import annotations

from kairos.core.orders import Action, Fill, Order, OrderType, Side
from kairos.core.portfolio import Portfolio
from kairos.events import Quote
from kairos.strategy.base import Strategy


class PassiveQuoter(Strategy):
    def __init__(
        self,
        edge_bps: float = 1.0,        # distance au mid de chaque cote
        qty: float = 25_000,
        max_inventory: float = 50_000,
        requote_bps: float = 0.5,     # derive tolerée avant de replacer
    ) -> None:
        self.edge_bps = edge_bps
        self.qty = qty
        self.max_inventory = max_inventory
        self.requote_bps = requote_bps
        self.live: dict[Side, tuple[int, float]] = {}   # side -> (client_id, prix)
        self._next_client_id = 0

    def on_quote(self, q: Quote, pf: Portfolio) -> list[Action] | None:
        actions: list[Action] = []
        mid = q.mid
        d = mid * self.edge_bps / 10_000

        want = {
            Side.BUY:  mid - d if pf.position < self.max_inventory else None,
            Side.SELL: mid + d if pf.position > -self.max_inventory else None,
        }

        for side, target in want.items():
            cur = self.live.get(side)

            if target is None:
                if cur is not None:
                    actions.append(Action(kind="cancel", client_id=cur[0]))
                    self.live.pop(side, None)
                continue

            if cur is not None:
                drift_bps = abs(cur[1] - target) / mid * 10_000
                if drift_bps < self.requote_bps:
                    continue                       # assez proche, on ne bouge pas
                actions.append(Action(kind="cancel", client_id=cur[0]))

            self._next_client_id += 1
            cid = self._next_client_id
            actions.append(Action(
                kind="submit",
                order=Order(id=0, client_id=cid, side=side, qty=self.qty,
                            type=OrderType.LIMIT, price=target),
            ))
            self.live[side] = (cid, target)

        return actions

    def on_fill(self, fill: Fill) -> None:
        self.live.pop(fill.side, None)
