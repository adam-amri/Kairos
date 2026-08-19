import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from kairos.ops.watchdog import Heartbeat, Watchdog, WatchdogVerdict

NS = 1_000_000_000


@pytest.fixture
def hb_path(tmp_path):
    return tmp_path / "heartbeat.json"


class TestWatchdog:
    def test_absence_de_fichier_n_est_jamais_un_ok(self, hb_path):
        v, _ = Watchdog(hb_path).check()
        assert v is WatchdogVerdict.NO_HEARTBEAT

    def test_fichier_corrompu_n_est_jamais_un_ok(self, hb_path):
        hb_path.write_text("{ ceci n'est pas du json")
        v, _ = Watchdog(hb_path).check()
        assert v is WatchdogVerdict.NO_HEARTBEAT

    def test_heartbeat_frais(self, hb_path):
        Heartbeat.now().write(hb_path)
        v, ctx = Watchdog(hb_path).check()
        assert v is WatchdogVerdict.OK
        assert ctx["age_s"] < 1

    def test_escalade_stale_puis_dead(self, hb_path):
        now = time.time_ns()
        Heartbeat(ts_wall_ns=now, healthy=True, state="long",
                  open_positions=1, pnl_bps=0.0).write(hb_path)
        wd = Watchdog(hb_path, stale_after_s=30, dead_after_s=120)

        assert wd.check(now_ns=now + 10 * NS)[0] is WatchdogVerdict.OK
        assert wd.check(now_ns=now + 60 * NS)[0] is WatchdogVerdict.STALE
        assert wd.check(now_ns=now + 300 * NS)[0] is WatchdogVerdict.DEAD

    def test_trader_malade_avec_positions_prime_sur_la_fraicheur(self, hb_path):
        """Vivant mais en erreur avec des positions ouvertes : il faut agir."""
        Heartbeat(ts_wall_ns=time.time_ns(), healthy=False, state="long",
                  open_positions=2, pnl_bps=-15.0,
                  last_error="rejet broker repete").write(hb_path)
        v, _ = Watchdog(hb_path).check()
        assert v is WatchdogVerdict.UNHEALTHY
        assert Watchdog.should_flatten(v)

    def test_trader_malade_mais_plat_ne_declenche_pas_de_liquidation(self, hb_path):
        """Rien a liquider : on n'escalade pas."""
        Heartbeat(ts_wall_ns=time.time_ns(), healthy=False, state="flat",
                  open_positions=0, pnl_bps=0.0).write(hb_path)
        v, _ = Watchdog(hb_path).check()
        assert not Watchdog.should_flatten(v)

    def test_stale_seul_ne_liquide_pas(self, hb_path):
        """Un hoquet reseau ne doit pas coder pour une liquidation."""
        assert not Watchdog.should_flatten(WatchdogVerdict.STALE)

    def test_seuils_incoherents_refuses(self, hb_path):
        with pytest.raises(ValueError):
            Watchdog(hb_path, stale_after_s=120, dead_after_s=30)

    def test_ecriture_atomique_pas_de_fichier_temporaire_resident(self, hb_path):
        Heartbeat.now().write(hb_path)
        assert hb_path.exists()
        assert not hb_path.with_suffix(hb_path.suffix + ".tmp").exists()
