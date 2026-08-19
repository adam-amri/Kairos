"""Cash and carry — liquidation, funding, regles de decision."""
import math
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from kairos.backtest.carry import (
    CarryConfig, CarrySimulator, chemin_choc, funding_regulier,
)
from kairos.core.funding import FundingEvent
from kairos.strategy.cash_and_carry import CarrySignal, CashAndCarryStrategy

TS0 = 1_700_000_000_000_000_000
P0 = 100.0


class TestFundingEvent:
    def test_un_short_encaisse_un_funding_positif(self):
        ev = FundingEvent(ts_ns=0, rate_bps=1.0, mark_price=100.0)
        assert ev.payment(position=-10) == pytest.approx(10 * 100 * 1e-4)

    def test_un_long_paie_un_funding_positif(self):
        ev = FundingEvent(ts_ns=0, rate_bps=1.0, mark_price=100.0)
        assert ev.payment(position=+10) < 0

    def test_un_funding_negatif_inverse_le_flux(self):
        ev = FundingEvent(ts_ns=0, rate_bps=-1.0, mark_price=100.0)
        assert ev.payment(position=-10) < 0      # le short paie


class TestPrixDeLiquidation:
    def test_formule_calculee_a_la_main(self):
        """p = p0 (1/L + 1) / (1 + mmr) ; L=2, mmr=0,005 -> 100 x 1,5/1,005"""
        sim = CarrySimulator(CarryConfig(max_leverage=2.0,
                                         maintenance_margin_rate=0.005))
        assert sim.prix_de_liquidation(100.0) == pytest.approx(100 * 1.5 / 1.005)

    def test_un_levier_plus_eleve_rapproche_la_liquidation(self):
        seuils = [CarrySimulator(CarryConfig(max_leverage=L)).prix_de_liquidation(100.0)
                  for L in (2.0, 5.0, 10.0, 20.0)]
        assert seuils == sorted(seuils, reverse=True)

    def test_la_marge_croisee_supprime_le_seuil(self):
        sim = CarrySimulator(CarryConfig(isolated_margin=False))
        assert sim.prix_de_liquidation(100.0) == math.inf

    def test_le_plafond_europeen_exige_pres_de_50_pourcent(self):
        sim = CarrySimulator(CarryConfig(max_leverage=2.0))
        hausse = sim.prix_de_liquidation(100.0) / 100.0 - 1
        assert 0.48 < hausse < 0.50


class TestSimulation:
    def _prix_plat(self, jours=90):
        return [(TS0 + int(i * 86_400e9 / 24), P0) for i in range(jours * 24)]

    def test_un_funding_positif_rapporte(self):
        r = CarrySimulator(CarryConfig()).run(
            self._prix_plat(), funding_regulier(TS0, 90, 1.0, P0), capital=10_000)
        assert not r.liquide
        assert r.funding_recu_bps > 0
        assert r.net_sur_capital_bps > 0

    def test_un_funding_negatif_coute(self):
        r = CarrySimulator(CarryConfig()).run(
            self._prix_plat(), funding_regulier(TS0, 90, -1.0, P0), capital=10_000)
        assert r.funding_recu_bps < 0
        assert r.net_sur_capital_bps < 0
        assert r.funding_negatifs == r.n_funding

    def test_sans_funding_les_frais_seuls_font_perdre(self):
        r = CarrySimulator(CarryConfig()).run(self._prix_plat(), [], capital=10_000)
        assert r.funding_recu_bps == 0.0
        assert r.net_sur_capital_bps < 0

    def test_un_petit_choc_ne_liquide_pas_a_2_pour_1(self):
        prices = chemin_choc(TS0, 90, P0, 0.25, jour_du_choc=30)
        r = CarrySimulator(CarryConfig(max_leverage=2.0)).run(
            prices, funding_regulier(TS0, 90, 1.0, P0), capital=10_000)
        assert not r.liquide

    def test_un_gros_choc_liquide_a_2_pour_1(self):
        prices = chemin_choc(TS0, 90, P0, 0.60, jour_du_choc=30)
        r = CarrySimulator(CarryConfig(max_leverage=2.0)).run(
            prices, funding_regulier(TS0, 90, 1.0, P0), capital=10_000)
        assert r.liquide
        assert r.ts_liquidation is not None

    def test_la_marge_croisee_survit_la_ou_l_isolee_liquide(self):
        """Position IDENTIQUE, risque net nul, issue opposee.

        C'est un risque de plomberie, pas de marche.
        """
        prices = chemin_choc(TS0, 90, P0, 0.30, jour_du_choc=30)
        f = funding_regulier(TS0, 90, 1.0, P0)
        iso = CarrySimulator(CarryConfig(max_leverage=5.0, isolated_margin=True)) \
            .run(prices, f, capital=10_000)
        cross = CarrySimulator(CarryConfig(max_leverage=5.0, isolated_margin=False)) \
            .run(prices, f, capital=10_000)
        assert iso.liquide
        assert not cross.liquide

    def test_l_efficience_du_capital_suit_le_plafond_de_levier(self):
        r = CarrySimulator(CarryConfig(max_leverage=2.0)).run(
            self._prix_plat(), funding_regulier(TS0, 90, 1.0, P0), capital=10_000)
        # capital = notionnel x (1 + 1/2) -> notionnel = capital / 1,5
        assert r.notional == pytest.approx(10_000 / 1.5)

    def test_le_seuil_de_bascule_est_coherent(self):
        """Frais 56 bps sur 270 periodes -> environ 0,207 bps par periode."""
        for taux, attendu_positif in ((0.25, True), (0.15, False)):
            r = CarrySimulator(CarryConfig()).run(
                self._prix_plat(), funding_regulier(TS0, 90, taux, P0), capital=10_000)
            assert (r.net_sur_capital_bps > 0) is attendu_positif

    def test_configuration_invalide(self):
        with pytest.raises(ValueError):
            CarryConfig(max_leverage=0)
        with pytest.raises(ValueError):
            CarryConfig(maintenance_margin_rate=1.5)

    def test_aucun_prix_refuse(self):
        with pytest.raises(ValueError):
            CarrySimulator().run([], [], capital=10_000)


class TestStrategie:
    def test_funding_insuffisant_on_attend(self):
        s = CashAndCarryStrategy(cout_aller_retour_bps=54.0, jours_amortissement_max=25)
        sig, _ = s.decider(en_position=False, funding_actuel_bps=0.5)
        assert sig is CarrySignal.ATTENDRE

    def test_funding_suffisant_on_entre(self):
        s = CashAndCarryStrategy(cout_aller_retour_bps=54.0, jours_amortissement_max=25)
        sig, _ = s.decider(en_position=False, funding_actuel_bps=1.5)
        assert sig is CarrySignal.ENTRER

    def test_le_seuil_correspond_a_l_amortissement(self):
        s = CashAndCarryStrategy(cout_aller_retour_bps=54.0, jours_amortissement_max=25)
        assert s.funding_minimal_requis_bps() == pytest.approx(54.0 / 75)

    def test_la_marge_prime_sur_le_funding(self):
        """Funding excellent mais marge critique : on sort quand meme."""
        s = CashAndCarryStrategy()
        sig, motif = s.decider(en_position=True, funding_actuel_bps=5.0, ratio_marge=0.05)
        assert sig is CarrySignal.SORTIR
        assert "marge" in motif

    def test_marge_basse_mais_pas_critique_on_renforce(self):
        s = CashAndCarryStrategy()
        sig, _ = s.decider(en_position=True, funding_actuel_bps=2.0, ratio_marge=0.20)
        assert sig is CarrySignal.RENFORCER_MARGE

    def test_funding_durablement_negatif_on_sort(self):
        s = CashAndCarryStrategy(fenetre_funding=9, seuil_negatifs_pour_sortir=6)
        for _ in range(9):
            sig, motif = s.decider(en_position=True, funding_actuel_bps=-0.5,
                                   ratio_marge=0.50)
        assert sig is CarrySignal.SORTIR
        assert "negatif" in motif

    def test_quelques_negatifs_isoles_ne_suffisent_pas(self):
        s = CashAndCarryStrategy(fenetre_funding=9, seuil_negatifs_pour_sortir=6)
        for r in [1.0, -0.5, 1.0, -0.5, 1.0, 1.0, 1.0, -0.5, 1.0]:
            sig, _ = s.decider(en_position=True, funding_actuel_bps=r, ratio_marge=0.50)
        assert sig is CarrySignal.TENIR
