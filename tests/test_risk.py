"""Couche de risque — c'est ici que les bugs coutent de l'argent."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from kairos.core.orders import Fill, Order, OrderType, Side
from kairos.core.portfolio import Portfolio
from kairos.risk import RiskDecision, RiskGate, RiskLimits, RiskState


def limites(**kw):
    base = dict(max_gross_position=100_000, max_net_position=50_000,
                max_order_notional=25_000, max_daily_loss_bps=200,
                max_leverage=3.0, min_margin_ratio=0.10)
    base.update(kw)
    return RiskLimits(**base)


def ordre(qty=100, side=Side.BUY, price=100.0):
    return Order(id=1, side=side, qty=qty, type=OrderType.LIMIT, price=price)


class TestConfiguration:
    def test_une_limite_nulle_est_refusee(self):
        """Une limite absente n'est pas une limite infinie."""
        for champ in ("max_gross_position", "max_net_position", "max_order_notional",
                      "max_daily_loss_bps", "max_leverage", "min_margin_ratio"):
            with pytest.raises(ValueError):
                limites(**{champ: 0})

    def test_une_limite_negative_est_refusee(self):
        with pytest.raises(ValueError):
            limites(max_leverage=-1)

    def test_nette_ne_peut_exceder_brute(self):
        with pytest.raises(ValueError):
            limites(max_net_position=200_000, max_gross_position=100_000)


class TestCoupeCircuit:
    def test_le_fichier_declenche_l_arret(self, tmp_path):
        ks = tmp_path / "STOP"
        ks.write_text("")
        g = RiskGate(limites(kill_switch_path=ks), RiskState(capital_reference=100_000))
        d, motif = g.check(ordre(), Portfolio(), 100.0)
        assert d is RiskDecision.HALT
        assert "kill switch" in motif

    def test_absent_le_systeme_fonctionne(self, tmp_path):
        g = RiskGate(limites(kill_switch_path=tmp_path / "absent"),
                     RiskState(capital_reference=100_000))
        assert g.check(ordre(), Portfolio(), 100.0)[0] is RiskDecision.ALLOW

    def test_l_arret_persiste_apres_suppression_du_fichier(self, tmp_path):
        """Retirer le fichier ne relance pas le systeme : la reprise est manuelle."""
        ks = tmp_path / "STOP"
        ks.write_text("")
        g = RiskGate(limites(kill_switch_path=ks), RiskState(capital_reference=100_000))
        g.check(ordre(), Portfolio(), 100.0)
        ks.unlink()
        assert g.check(ordre(), Portfolio(), 100.0)[0] is RiskDecision.HALT

    def test_la_reprise_manuelle_debloque(self, tmp_path):
        ks = tmp_path / "STOP"
        ks.write_text("")
        g = RiskGate(limites(kill_switch_path=ks), RiskState(capital_reference=100_000))
        g.check(ordre(), Portfolio(), 100.0)
        ks.unlink()
        g.reprise_manuelle()
        assert g.check(ordre(), Portfolio(), 100.0)[0] is RiskDecision.ALLOW


class TestPerteJournaliere:
    def test_l_atteinte_de_la_limite_arrete_tout(self):
        pf = Portfolio()
        pf.apply(Fill(order_id=1, side=Side.BUY, qty=1000, price=100.0,
                      ts_ns=0, is_maker=True))
        # capital 100k, perte de 2 500 -> 250 bps > limite de 200
        g = RiskGate(limites(), RiskState(capital_reference=100_000))
        d, motif = g.check(ordre(), pf, mark=97.5)
        assert d is RiskDecision.HALT
        assert "perte journaliere" in motif

    def test_une_perte_sous_la_limite_passe(self):
        pf = Portfolio()
        pf.apply(Fill(order_id=1, side=Side.BUY, qty=1000, price=100.0,
                      ts_ns=0, is_maker=True))
        g = RiskGate(limites(max_gross_position=1_000_000),
                     RiskState(capital_reference=100_000))
        assert g.check(ordre(), pf, mark=99.5)[0] is RiskDecision.ALLOW   # 50 bps

    def test_nouvelle_journee_ne_leve_pas_un_arret(self):
        """Le compteur repart, pas le systeme."""
        pf = Portfolio()
        pf.apply(Fill(order_id=1, side=Side.BUY, qty=1000, price=100.0,
                      ts_ns=0, is_maker=True))
        g = RiskGate(limites(), RiskState(capital_reference=100_000))
        g.check(ordre(), pf, mark=97.5)
        g.nouvelle_journee(pf.total_pnl(97.5))
        assert g.check(ordre(), pf, mark=97.5)[0] is RiskDecision.HALT


class TestLimitesDePosition:
    def test_ordre_trop_gros(self):
        g = RiskGate(limites(), RiskState(capital_reference=100_000))
        d, motif = g.check(ordre(qty=500, price=100.0), Portfolio(), 100.0)  # 50 000
        assert d is RiskDecision.REJECT
        assert "notionnel de l'ordre" in motif

    def test_position_nette_depassee(self):
        pf = Portfolio()
        pf.apply(Fill(order_id=1, side=Side.BUY, qty=49_950, price=100.0,
                      ts_ns=0, is_maker=True))
        g = RiskGate(limites(), RiskState(capital_reference=10_000_000))
        d, motif = g.check(ordre(qty=100, price=100.0), pf, 100.0)
        assert d is RiskDecision.REJECT
        assert "position nette" in motif

    def test_levier_depasse(self):
        g = RiskGate(limites(max_order_notional=1_000_000,
                             max_gross_position=10_000_000,
                             max_net_position=10_000_000),
                     RiskState(capital_reference=10_000))
        d, motif = g.check(ordre(qty=1000, price=100.0), Portfolio(), 100.0)  # 10x
        assert d is RiskDecision.REJECT
        assert "levier" in motif

    def test_marge_insuffisante_arrete(self):
        g = RiskGate(limites(), RiskState(capital_reference=100_000))
        d, motif = g.check(ordre(), Portfolio(), 100.0, margin_ratio=0.05)
        assert d is RiskDecision.HALT
        assert "marge" in motif

    def test_une_reduction_de_position_reste_permise(self):
        """On doit TOUJOURS pouvoir se degager, meme hors limites.

        Le portefeuille est ici tres au-dela de toutes les limites de position.
        Un ordre de vente doit malgre tout passer : bloquer la sortie
        transformerait un depassement passager en position subie.
        """
        pf = Portfolio()
        pf.apply(Fill(order_id=1, side=Side.BUY, qty=49_000, price=100.0,
                      ts_ns=0, is_maker=True))
        g = RiskGate(limites(), RiskState(capital_reference=10_000))
        d, motif = g.check(ordre(qty=100, side=Side.SELL, price=100.0), pf, 100.0)
        assert d is RiskDecision.ALLOW
        assert "reducteur" in motif

    def test_un_ordre_qui_augmente_le_risque_reste_bloque(self):
        """L'exception ne doit pas devenir une porte derobee."""
        pf = Portfolio()
        pf.apply(Fill(order_id=1, side=Side.BUY, qty=49_000, price=100.0,
                      ts_ns=0, is_maker=True))
        g = RiskGate(limites(), RiskState(capital_reference=10_000))
        assert g.check(ordre(qty=100, side=Side.BUY, price=100.0),
                       pf, 100.0)[0] is RiskDecision.REJECT

    def test_une_inversion_qui_aggrave_reste_bloquee(self):
        """Vendre 200 000 sur une position de +49 000 n'est pas une reduction."""
        pf = Portfolio()
        pf.apply(Fill(order_id=1, side=Side.BUY, qty=49_000, price=100.0,
                      ts_ns=0, is_maker=True))
        g = RiskGate(limites(max_order_notional=100_000_000),
                     RiskState(capital_reference=10_000))
        assert g.check(ordre(qty=200_000, side=Side.SELL, price=100.0),
                       pf, 100.0)[0] is RiskDecision.REJECT

    def test_les_rejets_sont_journalises(self):
        st = RiskState(capital_reference=100_000)
        g = RiskGate(limites(), st)
        g.check(ordre(qty=500, price=100.0), Portfolio(), 100.0)
        assert len(st.rejets) == 1
