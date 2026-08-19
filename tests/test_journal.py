"""Journal quotidien — bascule, cumul, continuite."""
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from kairos.journal import DailyJournal, OrderRecord

UTC = timezone.utc


def ms(y, m, d, h=12, mi=0, s=0):
    return int(datetime(y, m, d, h, mi, s, tzinfo=UTC).timestamp() * 1000)


def ordre(ts, net_bps=1.5, statut="execute", parcours=None):
    p = parcours or ["EUR", "USD", "JPY", "EUR"]
    return OrderRecord(
        id=f"o{ts}", ts_ms=ts, statut=statut, parcours=p,
        brut_bps=net_bps + 6.0, cout_bps=6.0, net_bps=net_bps,
        notionnel=25_000, taux_produit=1.00015,
        jambes=[{"de": p[i], "vers": p[i+1], "taux": 1.1, "paire": f"{p[i]}/{p[i+1]}",
                 "inverse": i % 2 == 1} for i in range(len(p) - 1)],
    )


@pytest.fixture
def j(tmp_path):
    return DailyJournal(dossier=tmp_path, tz_local=UTC)


class TestEcriture:
    def test_le_csv_du_jour_est_cree_avec_son_entete(self, j, tmp_path):
        j.enregistrer(ordre(ms(2026, 8, 20)))
        f = tmp_path / "ordres_2026-08-20.csv"
        assert f.exists()
        lignes = list(csv.DictReader(f.open(encoding="utf-8")))
        assert len(lignes) == 1
        assert lignes[0]["parcours"] == "EUR -> USD -> JPY -> EUR"
        assert lignes[0]["n_jambes"] == "3"

    def test_le_detail_des_jambes_est_lisible(self, j, tmp_path):
        j.enregistrer(ordre(ms(2026, 8, 20)))
        l = list(csv.DictReader((tmp_path / "ordres_2026-08-20.csv").open(encoding="utf-8")))[0]
        d = l["jambes_detail"]
        assert d.count("|") == 2                      # trois jambes
        assert "EUR>USD@" in d and "[EUR/USD]" in d
        assert ",inv]" in d                           # le sens inverse est marque

    def test_le_net_en_devise_est_coherent(self, j, tmp_path):
        j.enregistrer(ordre(ms(2026, 8, 20), net_bps=2.0))
        l = list(csv.DictReader((tmp_path / "ordres_2026-08-20.csv").open(encoding="utf-8")))[0]
        assert float(l["net_devise"]) == pytest.approx(2.0 / 10_000 * 25_000)

    def test_le_brut_et_le_net_sont_tous_deux_conserves(self, j, tmp_path):
        j.enregistrer(ordre(ms(2026, 8, 20), net_bps=1.5))
        l = list(csv.DictReader((tmp_path / "ordres_2026-08-20.csv").open(encoding="utf-8")))[0]
        assert float(l["brut_bps"]) == pytest.approx(7.5)
        assert float(l["net_bps"]) == pytest.approx(1.5)


class TestBascule:
    def test_le_changement_de_jour_ouvre_un_nouveau_fichier(self, j, tmp_path):
        j.enregistrer(ordre(ms(2026, 8, 20, 23, 59)))
        j.enregistrer(ordre(ms(2026, 8, 21, 0, 1)))
        assert (tmp_path / "ordres_2026-08-20.csv").exists()
        assert (tmp_path / "ordres_2026-08-21.csv").exists()

    def test_la_bascule_cloture_le_jour_precedent(self, j, tmp_path):
        j.enregistrer(ordre(ms(2026, 8, 20, 23, 59)))
        j.enregistrer(ordre(ms(2026, 8, 21, 0, 1)))
        r = list(csv.DictReader((tmp_path / "resume_quotidien.csv").open(encoding="utf-8")))
        assert [x["date"] for x in r] == ["2026-08-20"]

    def test_une_seconde_cloture_ne_duplique_pas(self, j, tmp_path):
        j.enregistrer(ordre(ms(2026, 8, 20)))
        j.cloturer(); j.cloturer(); j.cloturer()
        r = list(csv.DictReader((tmp_path / "resume_quotidien.csv").open(encoding="utf-8")))
        assert len(r) == 1


class TestCumul:
    def test_le_cumul_suit_les_ordres_executes(self, j):
        for i in range(4):
            j.enregistrer(ordre(ms(2026, 8, 20, 10, i), net_bps=1.0))
        assert j.net_cumule == pytest.approx(4 * 1.0 / 10_000 * 25_000)

    def test_un_ordre_detecte_non_execute_ne_compte_pas_au_pnl(self, j):
        j.enregistrer(ordre(ms(2026, 8, 20), net_bps=5.0, statut="detecte"))
        assert j.net_cumule == 0.0
        assert j.resume.opportunites_detectees == 1
        assert j.resume.arbitrages_executes == 0

    def test_le_cumul_survit_a_un_redemarrage(self, tmp_path):
        """Sans relecture, un redemarrage remettrait le P&L a zero et la courbe
        mentirait."""
        a = DailyJournal(dossier=tmp_path, tz_local=UTC)
        a.enregistrer(ordre(ms(2026, 8, 20), net_bps=2.0))
        a.cloturer()
        attendu = a.net_cumule
        b = DailyJournal(dossier=tmp_path, tz_local=UTC)
        assert b.net_cumule == pytest.approx(attendu)
        assert attendu > 0


class TestContinuite:
    def test_les_minutes_couvertes_sont_comptees(self, j):
        for m in range(30):
            j.observer(ms(2026, 8, 20, 10, m), boucles_examinees=14)
        assert j.resume.minutes_actives == 30
        assert j.resume.boucles_examinees == 30 * 14

    def test_un_trou_est_detecte(self, j):
        j.observer(ms(2026, 8, 20, 10, 0), 14)
        j.observer(ms(2026, 8, 20, 10, 1), 14)
        j.observer(ms(2026, 8, 20, 12, 0), 14)      # deux heures d'absence
        assert j.resume.n_trous == 1

    def test_une_collecte_reguliere_ne_signale_aucun_trou(self, j):
        for m in range(60):
            j.observer(ms(2026, 8, 20, 10, m), 14)
        assert j.resume.n_trous == 0

    def test_la_couverture_apparait_dans_le_resume(self, j, tmp_path):
        for m in range(720):                         # une demi-journee
            j.observer(ms(2026, 8, 20, m // 60, m % 60), 14)
        j.cloturer()
        r = list(csv.DictReader((tmp_path / "resume_quotidien.csv").open(encoding="utf-8")))[0]
        assert float(r["couverture_pct"]) == pytest.approx(50.0, abs=0.5)

    def test_un_jour_sans_opportunite_est_quand_meme_journalise(self, j, tmp_path):
        """Zero opportunite est une donnee, pas un vide."""
        for m in range(120):
            j.observer(ms(2026, 8, 20, 10 + m // 60, m % 60), 14)
        j.cloturer()
        r = list(csv.DictReader((tmp_path / "resume_quotidien.csv").open(encoding="utf-8")))[0]
        assert int(r["boucles_examinees"]) == 120 * 14
        assert int(r["opportunites_detectees"]) == 0
        assert float(r["taux_retenue_pct"]) == 0.0


class TestFormat:
    def test_les_colonnes_sont_stables(self, j, tmp_path):
        from kairos.journal.daily import COLONNES_ORDRES, COLONNES_RESUME
        j.enregistrer(ordre(ms(2026, 8, 20))); j.cloturer()
        with (tmp_path / "ordres_2026-08-20.csv").open(encoding="utf-8") as f:
            assert next(csv.reader(f)) == COLONNES_ORDRES
        with (tmp_path / "resume_quotidien.csv").open(encoding="utf-8") as f:
            assert next(csv.reader(f)) == COLONNES_RESUME

    def test_l_etat_est_exploitable_par_le_dashboard(self, j):
        j.observer(ms(2026, 8, 20, 10, 0), 14)
        j.enregistrer(ordre(ms(2026, 8, 20, 10, 1)))
        e = j.etat()
        assert e["jour"] == "2026-08-20"
        assert e["boucles_examinees"] == 14
        assert e["executes"] == 1
