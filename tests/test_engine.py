"""Moteur — les garanties structurelles, pas la performance."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from kairos.backtest.engine import BacktestEngine
from kairos.backtest.fills import CostModel, FillModel
from kairos.core.orders import Action, Order, OrderStatus, OrderType, Side
from kairos.events import Quote
from kairos.strategy.base import Strategy

MS = 1_000_000


def quote(ts_ms, bid, ask, bid_size=1_000_000, ask_size=1_000_000):
    ts = ts_ms * MS
    return Quote(venue="t", symbol="EUR/USD", bid=bid, ask=ask,
                 bid_size=bid_size, ask_size=ask_size,
                 ts_venue_ns=ts, ts_wall_ns=ts, ts_mono_ns=ts)


class SubmitOnce(Strategy):
    """Emet un seul ordre a la premiere quote, puis n'agit plus."""

    def __init__(self, side=Side.BUY, price=None, otype=OrderType.LIMIT, qty=100):
        self.done = False
        self.side, self.price, self.otype, self.qty = side, price, otype, qty
        self.fills = []

    def on_quote(self, q, pf):
        if self.done:
            return None
        self.done = True
        return [Action(kind="submit",
                       order=Order(id=0, side=self.side, qty=self.qty,
                                   type=self.otype, price=self.price))]

    def on_fill(self, fill):
        self.fills.append(fill)


class TestLatence:
    def test_latence_nulle_refusee(self):
        with pytest.raises(ValueError):
            BacktestEngine(SubmitOnce(), latency_ns=0)

    def test_pas_d_execution_sur_la_quote_declencheuse(self):
        """Le coeur de l'anti-look-ahead.

        L'ordre est decide sur la quote 0 et serait immediatement executable.
        Avec 50 ms de latence et des quotes espacees de 10 ms, il ne peut pas
        etre servi avant la quote 5.
        """
        strat = SubmitOnce(side=Side.BUY, price=1.0850)   # tres au-dessus du marche
        quotes = [quote(i * 10, 1.0800, 1.0802) for i in range(10)]
        res = BacktestEngine(strat, latency_ns=50 * MS,
                             cost=CostModel(commission_floor=0.0)).run(quotes)
        assert res.n_fills == 1
        # arrivee a t=50 ms : la premiere quote atteignable est celle a 50 ms
        assert strat.fills[0].ts_ns == 50 * MS

    def test_une_latence_plus_grande_retarde_l_execution(self):
        quotes = [quote(i * 10, 1.0800, 1.0802) for i in range(30)]
        t = []
        for lat_ms in (20, 100, 200):
            s = SubmitOnce(price=1.0850)
            BacktestEngine(s, latency_ns=lat_ms * MS,
                           cost=CostModel(commission_floor=0.0)).run(quotes)
            t.append(s.fills[0].ts_ns)
        assert t[0] < t[1] < t[2]

    def test_determinisme(self):
        quotes = [quote(i * 10, 1.0800 + i * 1e-5, 1.0802 + i * 1e-5) for i in range(50)]
        runs = []
        for _ in range(3):
            r = BacktestEngine(SubmitOnce(price=1.0850), latency_ns=30 * MS).run(quotes)
            runs.append((r.n_fills, r.portfolio.cash, tuple(v for _, v in r.equity_curve)))
        assert runs[0] == runs[1] == runs[2]


class TestExecution:
    def test_ordre_marche_paie_l_ask(self):
        strat = SubmitOnce(side=Side.BUY, otype=OrderType.MARKET, price=None)
        quotes = [quote(i * 10, 1.0800, 1.0802) for i in range(10)]
        BacktestEngine(strat, latency_ns=20 * MS,
                       cost=CostModel(commission_floor=0.0)).run(quotes)
        assert strat.fills[0].price == pytest.approx(1.0802)
        assert strat.fills[0].is_maker is False

    def test_limite_non_atteinte_jamais_executee(self):
        strat = SubmitOnce(side=Side.BUY, price=1.0700)   # loin sous le marche
        quotes = [quote(i * 10, 1.0800, 1.0802) for i in range(20)]
        res = BacktestEngine(strat, latency_ns=20 * MS).run(quotes)
        assert res.n_fills == 0

    def test_l_ordre_passif_encaisse_son_prix(self):
        strat = SubmitOnce(side=Side.BUY, price=1.0801)
        quotes = [quote(i * 10, 1.0800, 1.0802) for i in range(5)] + \
                 [quote(i * 10, 1.0798, 1.0800) for i in range(5, 15)]
        BacktestEngine(strat, latency_ns=20 * MS,
                       cost=CostModel(commission_floor=0.0)).run(quotes)
        assert strat.fills[0].price == pytest.approx(1.0801)
        assert strat.fills[0].is_maker is True


class TestFileDAttente:
    def test_pas_d_execution_immediate_au_meilleur_prix(self):
        """Poster au touch ne suffit pas : il y a du volume devant."""
        fm = FillModel(cost=CostModel(commission_floor=0.0), trade_ratio=1.0)
        o = Order(id=1, side=Side.BUY, qty=100, type=OrderType.LIMIT, price=1.0800)
        o.status = OrderStatus.RESTING
        q = quote(0, 1.0800, 1.0802, bid_size=500)
        assert fm.try_fill_limit(o, q, None) is None
        assert o.queue_ahead == 500

    def test_la_file_doit_etre_consommee(self):
        fm = FillModel(cost=CostModel(commission_floor=0.0), trade_ratio=1.0)
        o = Order(id=1, side=Side.BUY, qty=100, type=OrderType.LIMIT, price=1.0800)
        o.status = OrderStatus.RESTING
        q1 = quote(0, 1.0800, 1.0802, bid_size=500)
        fm.try_fill_limit(o, q1, None)              # entree dans la file
        q2 = quote(10, 1.0800, 1.0802, bid_size=200)
        assert fm.try_fill_limit(o, q2, q1) is None  # 300 consommes, 200 restent
        assert o.queue_ahead == pytest.approx(200)
        q3 = quote(20, 1.0800, 1.0802, bid_size=0)
        assert fm.try_fill_limit(o, q3, q2) is not None

    def test_trade_ratio_pessimiste_ralentit_la_file(self):
        for ratio, attendu in ((1.0, 200.0), (0.5, 350.0)):
            fm = FillModel(cost=CostModel(commission_floor=0.0), trade_ratio=ratio)
            o = Order(id=1, side=Side.BUY, qty=100, type=OrderType.LIMIT, price=1.0800)
            o.status = OrderStatus.RESTING
            q1 = quote(0, 1.0800, 1.0802, bid_size=500)
            fm.try_fill_limit(o, q1, None)
            q2 = quote(10, 1.0800, 1.0802, bid_size=200)
            fm.try_fill_limit(o, q2, q1)
            assert o.queue_ahead == pytest.approx(attendu)

    def test_trade_ratio_hors_bornes_refuse(self):
        with pytest.raises(ValueError):
            FillModel(trade_ratio=1.5)

    def test_sortir_du_meilleur_prix_fait_perdre_sa_place(self):
        fm = FillModel(cost=CostModel(commission_floor=0.0))
        o = Order(id=1, side=Side.BUY, qty=100, type=OrderType.LIMIT, price=1.0800)
        o.status = OrderStatus.RESTING
        q1 = quote(0, 1.0800, 1.0802, bid_size=500)
        fm.try_fill_limit(o, q1, None)
        assert o.joined_queue is True
        q2 = quote(10, 1.0805, 1.0807)              # le marche s'eloigne
        fm.try_fill_limit(o, q2, q1)
        assert o.joined_queue is False


class TestCouts:
    def test_le_plancher_s_applique_aux_petits_notionnels(self):
        c = CostModel(commission_bps=0.20, commission_floor=2.0)
        assert c.commission(10_000, is_maker=False) == pytest.approx(2.0)   # 0,20 bps = 0,20
        assert c.commission(100_000, is_maker=False) == pytest.approx(2.0)  # egalite exacte
        assert c.commission(1_000_000, is_maker=False) == pytest.approx(20.0)

    def test_le_tarif_maker_remplace_le_taux_de_base(self):
        c = CostModel(commission_bps=10.0, commission_floor=0.0, maker_bps=2.0)
        assert c.commission(100_000, is_maker=True) == pytest.approx(20.0)
        assert c.commission(100_000, is_maker=False) == pytest.approx(100.0)
