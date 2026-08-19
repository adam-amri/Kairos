"""Metriques — valeurs calculees a la main, jamais la sortie du code."""
import math
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from kairos.backtest.metrics import (
    deflated_sharpe_ratio, expected_max_sharpe, kurtosis, max_drawdown,
    probabilistic_sharpe_ratio, report, sharpe_ratio, skewness,
)


class TestMoments:
    def test_asymetrie_nulle_sur_serie_symetrique(self):
        assert skewness([-1, 1, -1, 1]) == pytest.approx(0.0)

    def test_asymetrie_positive_a_droite(self):
        assert skewness([1, 1, 1, 10]) > 0

    def test_kurtosis_est_brut_pas_excedentaire(self):
        """Convention du PSR : la normale vaut 3, pas 0."""
        # Serie a deux points : m2 = 1, m4 = 1 -> kurtosis = 1
        assert kurtosis([-1, 1, -1, 1]) == pytest.approx(1.0)

    def test_les_queues_epaisses_augmentent_le_kurtosis(self):
        assert kurtosis([0, 0, 0, 0, 10, -10]) > kurtosis([-1, 1, -1, 1])


class TestSharpe:
    def test_valeur_calculee_a_la_main(self):
        r = [0.01, 0.02, -0.01, 0.03]
        # moyenne 0,0125 ; variance (n-1) = 8,75e-4/3 ; ecart-type 0,0170783
        assert sharpe_ratio(r) == pytest.approx(0.0125 / math.sqrt(8.75e-4 / 3), rel=1e-9)

    def test_annualisation(self):
        r = [0.01, 0.02, -0.01, 0.03]
        assert sharpe_ratio(r, 252) == pytest.approx(sharpe_ratio(r) * math.sqrt(252))

    def test_volatilite_nulle_donne_zero_pas_une_division_par_zero(self):
        assert sharpe_ratio([0.01] * 10) == 0.0

    def test_serie_trop_courte(self):
        assert sharpe_ratio([0.01]) == 0.0


class TestPSRetDSR:
    def test_psr_croit_avec_le_sharpe(self):
        faible = [0.001, 0.002, -0.001, 0.002] * 30
        fort = [0.01, 0.012, 0.009, 0.011] * 30
        assert probabilistic_sharpe_ratio(fort) > probabilistic_sharpe_ratio(faible)

    def test_le_seuil_du_hasard_croit_avec_le_nombre_d_essais(self):
        """Plus on cherche, meilleur est le meilleur resultat fortuit."""
        v = 0.01
        assert (expected_max_sharpe(2, v) < expected_max_sharpe(50, v)
                < expected_max_sharpe(1000, v))

    def test_un_seul_essai_ne_deflate_pas(self):
        assert expected_max_sharpe(1, 0.01) == 0.0

    def test_le_dsr_est_toujours_plus_severe_que_le_psr(self):
        """C'est toute la raison d'etre du DSR."""
        r = [0.01, 0.015, -0.005, 0.02] * 30
        assert deflated_sharpe_ratio(r, n_trials=100) < probabilistic_sharpe_ratio(r)

    def test_le_dsr_decroit_quand_on_multiplie_les_essais(self):
        r = [0.01, 0.015, -0.005, 0.02] * 30
        assert (deflated_sharpe_ratio(r, 5) > deflated_sharpe_ratio(r, 100)
                > deflated_sharpe_ratio(r, 10_000))

    def test_dsr_borne_dans_zero_un(self):
        r = [0.01, 0.015, -0.005, 0.02] * 30
        for n in (2, 100, 10_000):
            assert 0.0 <= deflated_sharpe_ratio(r, n) <= 1.0


class TestDrawdown:
    def test_valeur_calculee_a_la_main(self):
        dd, i, j = max_drawdown([100, 120, 90, 130])
        assert dd == pytest.approx(0.25)     # de 120 a 90
        assert (i, j) == (1, 2)

    def test_courbe_monotone_sans_drawdown(self):
        assert max_drawdown([100, 110, 120])[0] == 0.0


class TestRapport:
    def test_le_verdict_se_durcit_avec_les_essais(self):
        r = [0.01, 0.012, -0.003, 0.015] * 40
        eq = [100.0]
        for x in r:
            eq.append(eq[-1] * (1 + x))
        peu = report(r, eq, n_trials=1)
        beaucoup = report(r, eq, n_trials=5000)
        assert beaucoup.dsr < peu.dsr
        assert beaucoup.n_trials == 5000


class TestRobustesseNumerique:
    """Non-regression sur un bug reel : variance residuelle des flottants."""

    def test_serie_constante_donne_sharpe_zero(self):
        # 0,01 x 10 / 10 != 0,01 exactement -> variance ~1e-18 -> Sharpe ~1e15
        assert sharpe_ratio([0.01] * 10) == 0.0

    def test_serie_constante_negative(self):
        assert sharpe_ratio([-0.003] * 50) == 0.0

    def test_une_vraie_faible_volatilite_reste_mesuree(self):
        """Le garde-fou ne doit pas ecraser un signal legitime."""
        r = [0.001, 0.0011, 0.0009, 0.0012] * 10
        assert sharpe_ratio(r) > 1.0


class TestAnnualisation:
    def test_un_facteur_extreme_declenche_un_avertissement(self):
        r = [0.0001, -0.0001, 0.0002, -0.00005] * 50
        eq = [100.0]
        for x in r:
            eq.append(eq[-1] * (1 + x))
        rep = report(r, eq, n_trials=1, periods_per_year=6.3e9)
        assert rep.avertissement != ""
        assert "n'est PAS interpretable" in rep.avertissement

    def test_pas_d_avertissement_a_frequence_journaliere(self):
        r = [0.01, 0.02, -0.01, 0.03] * 30
        eq = [100.0]
        for x in r:
            eq.append(eq[-1] * (1 + x))
        assert report(r, eq, n_trials=1, periods_per_year=252).avertissement == ""


class TestPrecisionNumerique:
    """Non-regression sur deux defauts mesures contre mpmath."""

    def test_la_cdf_ne_s_annule_pas_dans_la_queue(self):
        """statistics.NormalDist.cdf renvoyait EXACTEMENT 0.0 a x = -10."""
        from kairos.backtest.metrics import norm_cdf
        from statistics import NormalDist
        assert NormalDist().cdf(-10.0) == 0.0        # le defaut
        v = norm_cdf(-10.0)
        assert v > 0.0
        assert abs(v - 7.619853024160526e-24) / 7.619853024160526e-24 < 1e-13

    def test_la_cdf_reste_exacte_tres_loin(self):
        from kairos.backtest.metrics import norm_cdf
        assert norm_cdf(-37.0) > 0.0
        assert norm_cdf(-20.0) > 0.0

    def test_expected_max_sharpe_survit_aux_grands_nombres(self):
        """La forme 1 - 1/N levait StatisticsError des N >= 1e16."""
        import math
        for n in (1e15, 1e16, 1e20, 1e100, 1e300):
            v = expected_max_sharpe(n, 0.01)
            assert math.isfinite(v) and v > 0

    def test_le_seuil_du_hasard_reste_croissant_sur_toute_la_plage(self):
        vals = [expected_max_sharpe(n, 0.01) for n in (1e2, 1e8, 1e16, 1e50, 1e200)]
        assert vals == sorted(vals)

    def test_le_dsr_reste_fini_pour_un_nombre_d_essais_extreme(self):
        import math
        r = [0.01, 0.015, -0.005, 0.02] * 30
        v = deflated_sharpe_ratio(r, 1e20)
        assert math.isfinite(v) and 0.0 <= v <= 1.0
