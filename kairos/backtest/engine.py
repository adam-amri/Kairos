"""Moteur de backtest evenementiel, deterministe.

TROIS GARANTIES, et ce sont elles qui font la difference entre un backtest et une
illusion.

1. AUCUN LOOK-AHEAD. La strategie ne voit qu'une quote a la fois, dans l'ordre
   chronologique. Elle n'a aucun acces au futur, par construction et non par
   discipline.

2. LATENCE INCOMPRESSIBLE. Un ordre decide sur la quote au temps t n'arrive chez le
   venue qu'a t + latence. Il ne peut donc PAS etre execute contre la quote qui l'a
   declenche. C'est l'erreur la plus rentable des backtests naifs : elle permet de
   reagir a une information a l'instant meme ou elle apparait, ce qu'aucun systeme
   reel ne peut faire.

3. DETERMINISME. Memes entrees, meme sortie, toujours. Sans cela, on ne peut ni
   reproduire un incident, ni comparer deux versions, ni faire confiance a quoi que
   ce soit. C'est aussi ce qui permet le test de non-regression backtest/live.

Le meme objet Strategy tourne ici et en production. Seule la source d'evenements
change.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from kairos.backtest.fills import CostModel, FillModel
from kairos.core.orders import Order, OrderStatus, OrderType
from kairos.core.portfolio import Portfolio
from kairos.events import Quote

if TYPE_CHECKING:                      # rompt le cycle backtest <-> strategy
    from kairos.strategy.base import Strategy


@dataclass
class BacktestResult:
    equity_curve: list[tuple[int, float]] = field(default_factory=list)
    portfolio: Portfolio = field(default_factory=Portfolio)
    n_quotes: int = 0
    n_orders: int = 0
    n_fills: int = 0
    n_cancelled: int = 0

    @property
    def returns(self) -> list[float]:
        """Rendements simples entre points successifs de la courbe d'equity."""
        out = []
        for (_, a), (_, b) in zip(self.equity_curve, self.equity_curve[1:]):
            out.append((b - a) / abs(a) if a else 0.0)
        return out


class BacktestEngine:
    def __init__(
        self,
        strategy: "Strategy",
        cost: CostModel | None = None,
        latency_ns: int = 50_000_000,     # 50 ms : ordre de grandeur retail non colocalise
        trade_ratio: float = 0.5,
        initial_cash: float = 0.0,
    ) -> None:
        if latency_ns <= 0:
            raise ValueError(
                "latency_ns doit etre > 0 : une latence nulle autorise la strategie a "
                "s'executer contre la quote qui l'a declenchee, ce qui est impossible."
            )
        self.strategy = strategy
        self.fill_model = FillModel(cost=cost, trade_ratio=trade_ratio)
        self.latency_ns = latency_ns
        self.initial_cash = initial_cash

    def run(self, quotes: list[Quote]) -> BacktestResult:
        res = BacktestResult()
        res.portfolio.cash = self.initial_cash
        pf = res.portfolio

        pending: list[Order] = []      # emis, pas encore arrives (latence)
        resting: dict[int, Order] = {}
        by_client: dict[int, Order] = {}             # client_id -> ordre
        pending_cancels: list[tuple[int, int]] = []  # (ts_arrivee, client_id)
        next_id = 1
        prev_q: Quote | None = None

        for q in quotes:
            now = q.ts_wall_ns
            res.n_quotes += 1

            # 1. Les annulations arrivees prennent effet
            still = []
            for ts_arr, cid in pending_cancels:
                if ts_arr <= now:
                    o = by_client.get(cid)
                    # Une annulation doit atteindre un ordre ENCORE EN VOL comme un
                    # ordre deja pose. Ne traiter que le carnet laisse passer tous
                    # les ordres emis dans la derniere fenetre de latence, qui se
                    # posent ensuite alors qu'on les croyait annules.
                    if o is not None and o.is_active:
                        o.status = OrderStatus.CANCELLED
                        resting.pop(o.id, None)
                        if o in pending:
                            pending.remove(o)
                        res.n_cancelled += 1
                else:
                    still.append((ts_arr, cid))
            pending_cancels = still

            # 2. Les ordres arrives entrent dans le carnet
            remaining_pending = []
            for o in pending:
                if o.status is OrderStatus.CANCELLED:
                    continue
                if o.ts_arrive_ns <= now:
                    o.status = OrderStatus.RESTING
                    resting[o.id] = o
                else:
                    remaining_pending.append(o)
            pending = remaining_pending

            # 3. Confrontation des ordres au carnet
            for oid in list(resting.keys()):
                o = resting[oid]
                fill = self.fill_model.process(o, q, prev_q)
                if fill is None:
                    continue
                o.filled_qty += fill.qty
                o.avg_fill_price = fill.price
                o.status = OrderStatus.FILLED
                pf.apply(fill)
                res.n_fills += 1
                del resting[oid]
                self.strategy.on_fill(fill)

            # 4. La strategie decide — APRES les executions, sur l'etat courant
            actions = self.strategy.on_quote(q, pf) or []
            for a in actions:
                if a.kind == "submit" and a.order is not None:
                    o = a.order
                    o.id = next_id
                    next_id += 1
                    o.ts_created_ns = now
                    o.ts_arrive_ns = now + self.latency_ns   # la latence, toujours
                    o.status = OrderStatus.PENDING
                    pending.append(o)
                    by_client[o.client_id] = o
                    res.n_orders += 1
                elif a.kind == "cancel" and a.client_id is not None:
                    pending_cancels.append((now + self.latency_ns, a.client_id))

            # 5. Marquage au mid
            res.equity_curve.append((now, pf.equity(q.mid)))
            prev_q = q

        return res
