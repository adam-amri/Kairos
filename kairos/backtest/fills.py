"""Modele d'execution — la piece qui decide si un backtest ment ou non.

Un backtest optimiste sur les executions produit un P&L de fiction. Trois
mecanismes sont modelises ici, et le troisieme est celui que presque tous les
backtests amateurs omettent.

1. TAKER — un ordre marche franchit le spread. Execution immediate au meilleur
   prix oppose. Simple et honnete.

2. TRAVERSEE — un ordre limite dont le prix est franchi par le marche est execute.
   Un achat a 1,0800 est servi si le meilleur ask descend a 1,0800 ou en dessous.

3. FILE D'ATTENTE — le cas passif, et le seul qui compte pour une strategie de
   capture de spread. Poster une limite ne suffit pas : on entre au FOND de la file
   du niveau de prix, derriere tout le volume deja affiche. On n'est servi qu'une
   fois ce volume consomme.

HYPOTHESE CENTRALE, ET IL FAUT LA CONNAITRE
    Avec des donnees de haut de carnet (L1) seules, on observe la taille affichee
    diminuer sans savoir si c'est une execution (qui fait avancer notre place) ou
    une annulation devant nous (qui la fait avancer aussi) ou derriere nous (qui ne
    change rien). `trade_ratio` est la fraction des diminutions attribuee a ce qui
    nous fait reellement avancer.

    C'est L'HYPOTHESE LA PLUS INFLUENTE de tout backtest passif. Une valeur trop
    haute rend n'importe quelle strategie rentable. Le defaut est volontairement
    pessimiste, et cette valeur DOIT etre recalibree contre les executions reelles
    de la Phase 3. Tant que ce n'est pas fait, tout resultat passif est indicatif.
"""
from __future__ import annotations

from dataclasses import dataclass

from kairos.core.orders import Fill, Order, OrderStatus, OrderType, Side
from kairos.events import Quote


@dataclass
class CostModel:
    """Reprend exactement la formule du classeur, plancher compris."""

    commission_bps: float = 0.20
    commission_floor: float = 2.00
    maker_bps: float | None = None      # si defini, remplace commission_bps en passif

    def commission(self, notional: float, is_maker: bool) -> float:
        bps = self.maker_bps if (is_maker and self.maker_bps is not None) else self.commission_bps
        return max(self.commission_floor, abs(notional) * bps / 10_000)


class FillModel:
    def __init__(self, cost: CostModel | None = None, trade_ratio: float = 0.5) -> None:
        if not 0.0 <= trade_ratio <= 1.0:
            raise ValueError("trade_ratio doit etre dans [0, 1]")
        self.cost = cost or CostModel()
        self.trade_ratio = trade_ratio

    # ------------------------------------------------------------------ taker
    def fill_market(self, order: Order, q: Quote) -> Fill:
        price = q.ask if order.side is Side.BUY else q.bid
        notional = order.remaining * price
        return Fill(
            order_id=order.id, side=order.side, qty=order.remaining, price=price,
            ts_ns=q.ts_wall_ns, is_maker=False,
            commission=self.cost.commission(notional, is_maker=False),
        )

    # ------------------------------------------------------------------ passif
    def _size_at_our_level(self, order: Order, q: Quote) -> float:
        return q.bid_size if order.side is Side.BUY else q.ask_size

    def _at_touch(self, order: Order, q: Quote) -> bool:
        """Notre prix est-il le meilleur de notre cote ?"""
        best = q.bid if order.side is Side.BUY else q.ask
        return abs(best - order.price) < 1e-12

    def _crossed(self, order: Order, q: Quote) -> bool:
        """Le marche a-t-il traverse notre prix ?"""
        if order.side is Side.BUY:
            return q.ask <= order.price + 1e-12
        return q.bid >= order.price - 1e-12

    def try_fill_limit(self, order: Order, q: Quote, prev: Quote | None) -> Fill | None:
        # Traversee : le marche vient nous chercher, on est servi a NOTRE prix
        if self._crossed(order, q):
            notional = order.remaining * order.price
            return Fill(
                order_id=order.id, side=order.side, qty=order.remaining,
                price=order.price, ts_ns=q.ts_wall_ns, is_maker=True,
                commission=self.cost.commission(notional, is_maker=True),
            )

        if not self._at_touch(order, q):
            # Hors du meilleur prix : on ne peut pas etre execute, et on quitte la
            # file. Si le marche revient, on se replacera au fond.
            order.joined_queue = False
            return None

        # Entree dans la file : tout le volume affiche est devant nous
        if not order.joined_queue:
            order.queue_ahead = self._size_at_our_level(order, q)
            order.joined_queue = True
            return None

        # Progression : la diminution de taille nous fait avancer, partiellement
        if prev is not None and self._at_touch(order, prev):
            size_now = self._size_at_our_level(order, q)
            size_before = prev.bid_size if order.side is Side.BUY else prev.ask_size
            consumed = max(0.0, size_before - size_now)
            order.queue_ahead -= consumed * self.trade_ratio

        if order.queue_ahead > 0:
            return None

        notional = order.remaining * order.price
        return Fill(
            order_id=order.id, side=order.side, qty=order.remaining,
            price=order.price, ts_ns=q.ts_wall_ns, is_maker=True,
            commission=self.cost.commission(notional, is_maker=True),
        )

    def process(self, order: Order, q: Quote, prev: Quote | None) -> Fill | None:
        if order.status is not OrderStatus.RESTING:
            return None
        if order.type is OrderType.MARKET:
            return self.fill_market(order, q)
        return self.try_fill_limit(order, q, prev)
