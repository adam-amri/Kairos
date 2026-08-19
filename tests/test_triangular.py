"""Tests de la logique qui decide d'engager de l'argent.

On teste contre des valeurs calculees a la main, jamais contre la sortie du code
lui-meme : un test qui compare le code a lui-meme ne prouve rien.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import pytest

from kairos.analysis.triangular import analyse_triangle, cost_threshold_bps


class TestCostThreshold:
    def test_plancher_domine_les_petits_tickets(self):
        # 2 USD sur 10 000 = 2 bps par jambe, bien au-dessus des 0,20 affiches
        # 3 x (2,00 + 0,14) = 6,42
        assert cost_threshold_bps(notional_usd=10_000) == pytest.approx(6.42, abs=1e-9)

    def test_le_plancher_cesse_a_100k(self):
        # 2 / 0,000020 = 100 000 : le taux et le plancher s'egalisent exactement
        assert cost_threshold_bps(notional_usd=100_000) == pytest.approx(1.02, abs=1e-9)

    def test_au_dela_de_100k_le_cout_est_constant(self):
        assert cost_threshold_bps(notional_usd=1_000_000) == pytest.approx(
            cost_threshold_bps(notional_usd=100_000), abs=1e-9
        )

    def test_coherence_avec_le_classeur(self):
        # Doit reproduire l'onglet Hypotheses au centieme de bp pres
        for notional, attendu in [(5_000, 12.42), (25_000, 2.82), (50_000, 1.62)]:
            assert cost_threshold_bps(notional_usd=notional) == pytest.approx(attendu, abs=1e-9)


def _triangle(eurusd_bid, eurusd_ask, usdjpy_bid, usdjpy_ask, eurjpy_bid, eurjpy_ask):
    rows, ts = [], 1_000
    for sym, b, a in [("EUR/USD", eurusd_bid, eurusd_ask),
                      ("USD/JPY", usdjpy_bid, usdjpy_ask),
                      ("EUR/JPY", eurjpy_bid, eurjpy_ask)]:
        rows.append({"ts_wall_ns": ts, "symbol": sym, "bid": b, "ask": a})
        ts += 1
    return pd.DataFrame(rows)


class TestTriangular:
    def test_parite_parfaite_donne_une_deviation_negative(self):
        """Sans spread ni bruit, la boucle rend exactement 1 -> deviation nulle."""
        df = _triangle(1.08, 1.08, 157.0, 157.0, 1.08 * 157.0, 1.08 * 157.0)
        res = analyse_triangle(df)
        assert res["deviation_max_bps"] == pytest.approx(0.0, abs=1e-6)
        assert res["n_au_dessus_du_seuil"] == 0

    def test_le_spread_creuse_la_deviation(self):
        """Avec du spread, la boucle perd : c'est le cout de trois franchissements."""
        s = 1.0001
        df = _triangle(1.08 / s, 1.08 * s, 157.0 / s, 157.0 * s,
                       1.08 * 157.0 / s, 1.08 * 157.0 * s)
        res = analyse_triangle(df)
        assert res["deviation_max_bps"] < 0

    def test_une_dislocation_injectee_est_retrouvee(self):
        """+50 bps sur la croisee doivent ressortir a ~50 bps sur le sens 2."""
        eurjpy_juste = 1.08 * 157.0
        df = _triangle(1.08, 1.08, 157.0, 157.0,
                       eurjpy_juste * 1.005, eurjpy_juste * 1.005)
        res = analyse_triangle(df)
        assert res["deviation_max_bps"] == pytest.approx(50.0, rel=0.02)

    def test_on_utilise_bid_et_ask_jamais_le_mid(self):
        """Garde-fou contre l'erreur la plus commune du calcul triangulaire.

        Un spread large doit degrader la deviation. Si quelqu'un remplace bid/ask
        par le mid, la deviation devient nulle et ce test echoue.
        """
        large = _triangle(1.07, 1.09, 156.0, 158.0, 1.08 * 157.0 * 0.99, 1.08 * 157.0 * 1.01)
        etroit = _triangle(1.0799, 1.0801, 156.99, 157.01,
                           1.08 * 157.0 * 0.9999, 1.08 * 157.0 * 1.0001)
        assert analyse_triangle(large)["deviation_max_bps"] < \
               analyse_triangle(etroit)["deviation_max_bps"]
