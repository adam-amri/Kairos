"""Comptabilite — teste contre des valeurs calculees a la main."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from kairos.core.orders import Fill, Side
from kairos.core.portfolio import Portfolio


def f(side, qty, price, comm=0.0):
    return Fill(order_id=1, side=side, qty=qty, price=price, ts_ns=0,
                is_maker=True, commission=comm)


class TestPortfolio:
    def test_achat_simple(self):
        pf = Portfolio()
        pf.apply(f(Side.BUY, 100, 10.0))
        assert pf.position == 100
        assert pf.avg_price == 10.0
        assert pf.cash == -1000.0
        assert pf.realised_pnl == 0.0

    def test_aller_retour_gagnant(self):
        pf = Portfolio()
        pf.apply(f(Side.BUY, 100, 10.0))
        pf.apply(f(Side.SELL, 100, 11.0))
        assert pf.position == 0
        assert pf.realised_pnl == pytest.approx(100.0)
        assert pf.cash == pytest.approx(100.0)

    def test_renforcement_moyenne_ponderee(self):
        pf = Portfolio()
        pf.apply(f(Side.BUY, 100, 10.0))
        pf.apply(f(Side.BUY, 100, 12.0))
        assert pf.position == 200
        assert pf.avg_price == pytest.approx(11.0)
        assert pf.realised_pnl == 0.0

    def test_reduction_partielle_ne_bouge_pas_la_moyenne(self):
        pf = Portfolio()
        pf.apply(f(Side.BUY, 100, 10.0))
        pf.apply(f(Side.SELL, 40, 12.0))
        assert pf.position == 60
        assert pf.avg_price == pytest.approx(10.0)     # inchangee
        assert pf.realised_pnl == pytest.approx(80.0)  # 40 x 2

    def test_inversion_de_position(self):
        """+100 puis vente de 150 : solder 100 puis ouvrir -50."""
        pf = Portfolio()
        pf.apply(f(Side.BUY, 100, 10.0))
        pf.apply(f(Side.SELL, 150, 12.0))
        assert pf.position == -50
        assert pf.realised_pnl == pytest.approx(200.0)  # 100 x 2, pas 150 x 2
        assert pf.avg_price == pytest.approx(12.0)

    def test_vente_a_decouvert_gagnante(self):
        pf = Portfolio()
        pf.apply(f(Side.SELL, 100, 12.0))
        assert pf.position == -100
        pf.apply(f(Side.BUY, 100, 10.0))
        assert pf.realised_pnl == pytest.approx(200.0)

    def test_les_commissions_sortent_de_la_tresorerie(self):
        pf = Portfolio()
        pf.apply(f(Side.BUY, 100, 10.0, comm=2.0))
        assert pf.cash == pytest.approx(-1002.0)
        assert pf.total_commission == pytest.approx(2.0)

    def test_latent_et_equity(self):
        pf = Portfolio()
        pf.apply(f(Side.BUY, 100, 10.0))
        assert pf.unrealised_pnl(11.0) == pytest.approx(100.0)
        assert pf.equity(11.0) == pytest.approx(100.0)   # -1000 + 100 x 11
        assert pf.total_pnl(11.0) == pytest.approx(100.0)
