"""Non-regression sur trois bugs reels trouves a l'execution.

Chacun etait silencieux : aucune exception, aucun message. Le backtest tournait et
rendait un resultat faux. Ce sont les pires.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from kairos.backtest import BacktestEngine, CostModel
from kairos.core.orders import Action, Order, OrderType, Side
from kairos.feed.synthetic import SyntheticFeed
from kairos.strategy import PassiveQuoter
from kairos.strategy.base import Strategy

MS = 1_000_000


class TestHorlogeSimulee:
    """BUG 1 : le feed horodatait avec l'heure reelle de generation.

    Consequence : 60 s de marche comprimees dans quelques millisecondes, donc
    toute latence modelisee depassait la duree du jeu de donnees et AUCUN ordre
    n'arrivait jamais. Le backtest affichait zero execution, sans erreur.
    """

    def test_l_etendue_temporelle_correspond_a_la_duree_demandee(self):
        qs = [q for q in SyntheticFeed(duration_s=60, ticks_per_s=20).stream()
              if q.symbol == "EUR/USD"]
        span_s = (qs[-1].ts_wall_ns - qs[0].ts_wall_ns) / 1e9
        assert 55 < span_s < 65

    def test_horodatages_strictement_croissants(self):
        qs = [q for q in SyntheticFeed(duration_s=10, ticks_per_s=20).stream()
              if q.symbol == "EUR/USD"]
        ts = [q.ts_wall_ns for q in qs]
        assert ts == sorted(ts)

    def test_la_reception_est_posterieure_a_l_horodatage_venue(self):
        """Une latence negative signale des horloges incoherentes."""
        for q in SyntheticFeed(duration_s=5, ticks_per_s=20).stream():
            assert q.latency_ns > 0

    def test_start_ns_rend_le_feed_reproductible(self):
        a = list(SyntheticFeed(duration_s=5, start_ns=1_000_000_000).stream())
        b = list(SyntheticFeed(duration_s=5, start_ns=1_000_000_000).stream())
        assert [q.ts_wall_ns for q in a] == [q.ts_wall_ns for q in b]


class SubmitPuisCancel(Strategy):
    """Emet et annule, avec un decalage configurable en nombre de quotes."""

    def __init__(self, delai_quotes: int, price: float = 1.0850):
        self.step = 0
        self.delai = delai_quotes
        self.price = price

    def on_quote(self, q, pf):
        self.step += 1
        if self.step == 1:
            acts = [Action(kind="submit",
                           order=Order(id=0, client_id=77, side=Side.BUY, qty=100,
                                       type=OrderType.LIMIT, price=self.price))]
            if self.delai == 0:
                acts.append(Action(kind="cancel", client_id=77))
            return acts
        if self.delai > 0 and self.step == 1 + self.delai:
            return [Action(kind="cancel", client_id=77)]
        return None


def _q(ts_ms, bid, ask):
    from kairos.events import Quote
    ts = ts_ms * MS
    return Quote(venue="t", symbol="EUR/USD", bid=bid, ask=ask,
                 bid_size=1e6, ask_size=1e6,
                 ts_venue_ns=ts, ts_wall_ns=ts, ts_mono_ns=ts)


class TestAnnulationDesOrdresEnVol:
    """BUG 2 : l'annulation ne visait que le carnet.

    Tout ordre emis dans la derniere fenetre de latence echappait donc a son
    annulation, se posait ensuite, et pouvait etre execute alors que la strategie
    le croyait annule.
    """

    def test_un_ordre_encore_en_vol_est_bien_annule(self):
        """Emission et annulation sur la MEME quote : l'annulation atteint l'ordre
        pendant son vol, il ne doit jamais se poser."""
        quotes = [_q(i * 10, 1.0800, 1.0802) for i in range(20)]
        res = BacktestEngine(SubmitPuisCancel(delai_quotes=0), latency_ns=100 * MS,
                             cost=CostModel(commission_floor=0.0)).run(quotes)
        assert res.n_cancelled == 1
        assert res.n_fills == 0

    def test_une_annulation_trop_tardive_ne_defait_pas_une_execution(self):
        """Realisme des courses d'annulation, et ce n'est PAS un bug.

        L'ordre arrive a 100 ms et, immediatement executable, il est servi.
        L'annulation emise a 10 ms n'arrive qu'a 110 ms : elle est trop tard.
        Un moteur qui « annulerait » retroactivement une execution deja faite
        surestimerait la maitrise reelle qu'on a de ses ordres.
        """
        quotes = [_q(i * 10, 1.0800, 1.0802) for i in range(20)]
        res = BacktestEngine(SubmitPuisCancel(delai_quotes=1), latency_ns=100 * MS,
                             cost=CostModel(commission_floor=0.0)).run(quotes)
        assert res.n_fills == 1
        assert res.n_cancelled == 0

    def test_une_annulation_atteint_un_ordre_pose_non_executable(self):
        quotes = [_q(i * 10, 1.0800, 1.0802) for i in range(30)]
        res = BacktestEngine(SubmitPuisCancel(delai_quotes=1, price=1.0700),
                             latency_ns=100 * MS,
                             cost=CostModel(commission_floor=0.0)).run(quotes)
        assert res.n_fills == 0
        assert res.n_cancelled == 1


class TestIdentifiantClient:
    """BUG 3 : la strategie annulait par un identifiant local sans rapport avec
    celui du moteur. Les annulations partaient dans le vide et les ordres
    s'accumulaient indefiniment dans le carnet."""

    def test_la_strategie_annule_effectivement_ses_ordres(self):
        quotes = [q for q in SyntheticFeed(duration_s=60, ticks_per_s=20).stream()
                  if q.symbol == "EUR/USD"]
        res = BacktestEngine(PassiveQuoter(edge_bps=1.0, qty=25_000),
                             cost=CostModel(commission_floor=0.0),
                             latency_ns=20 * MS, initial_cash=100_000.0).run(quotes)
        assert res.n_orders > 0
        assert res.n_cancelled > 0          # sans le correctif : exactement 0

    def test_le_moteur_execute_reellement_des_ordres(self):
        """Verification de bout en bout : sans les trois correctifs, zero."""
        quotes = [q for q in SyntheticFeed(duration_s=120, ticks_per_s=20).stream()
                  if q.symbol == "EUR/USD"]
        res = BacktestEngine(PassiveQuoter(edge_bps=0.05, qty=25_000),
                             cost=CostModel(commission_floor=0.0),
                             latency_ns=20 * MS, initial_cash=100_000.0).run(quotes)
        assert res.n_fills > 0
