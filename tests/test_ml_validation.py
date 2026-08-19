"""Validation croisee purgee — la fuite est ce qu'on teste."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pytest
from kairos.ml.validation import PurgedKFold, triple_barrier_labels


class TestPurgedKFold:
    def test_apprentissage_et_test_disjoints(self):
        for train, test in PurgedKFold(n_splits=5, embargo_pct=0.0).split(100):
            assert len(np.intersect1d(train, test)) == 0

    def test_les_blocs_de_test_couvrent_tout_et_restent_ordonnes(self):
        blocs = [t for _, t in PurgedKFold(n_splits=4, embargo_pct=0.0).split(100)]
        assert sorted(np.concatenate(blocs).tolist()) == list(range(100))
        for b in blocs:
            assert list(b) == sorted(b)          # contigu et chronologique

    def test_la_purge_retire_les_etiquettes_chevauchantes(self):
        """Une etiquette qui deborde sur le test doit sortir de l'apprentissage."""
        n = 100
        label_end = np.arange(n) + 10            # chaque etiquette couvre 10 pas
        cv = PurgedKFold(n_splits=5, embargo_pct=0.0)
        for train, test in cv.split(n, label_end):
            t0 = int(test[0])
            for i in train:
                if i < t0:
                    assert label_end[i] < t0     # aucune fuite vers le test

    def test_l_embargo_retire_la_bande_posterieure(self):
        n = 100
        cv = PurgedKFold(n_splits=5, embargo_pct=0.10)   # 10 echantillons
        for train, test in cv.split(n):
            t1 = int(test[-1])
            interdits = set(range(t1 + 1, min(t1 + 11, n)))
            assert not (set(train.tolist()) & interdits)

    def test_sans_purge_ni_embargo_on_retrouve_le_kfold_classique(self):
        cv = PurgedKFold(n_splits=5, embargo_pct=0.0)
        for train, test in cv.split(100):
            assert len(train) + len(test) == 100

    def test_parametres_invalides(self):
        with pytest.raises(ValueError):
            PurgedKFold(n_splits=1)
        with pytest.raises(ValueError):
            PurgedKFold(embargo_pct=1.5)
        with pytest.raises(ValueError):
            list(PurgedKFold().split(10, label_end=[1, 2, 3]))


class TestTripleBarriere:
    def test_barriere_haute_touchee(self):
        prix = np.array([100.0, 101.0, 105.0, 100.0])
        lab, end = triple_barrier_labels(prix, horizon=3, upper_pct=0.03, lower_pct=0.03)
        assert lab[0] == 1
        assert end[0] == 2                     # touchee a l'indice 2

    def test_barriere_basse_touchee(self):
        prix = np.array([100.0, 99.0, 95.0, 100.0])
        lab, _ = triple_barrier_labels(prix, horizon=3, upper_pct=0.03, lower_pct=0.03)
        assert lab[0] == -1

    def test_barriere_temporelle_quand_rien_ne_bouge(self):
        prix = np.array([100.0, 100.1, 99.9, 100.0])
        lab, end = triple_barrier_labels(prix, horizon=3, upper_pct=0.03, lower_pct=0.03)
        assert lab[0] == 0
        assert end[0] == 3

    def test_la_premiere_barriere_touchee_gagne(self):
        """Chute d'abord, remontee ensuite : l'etiquette doit etre negative."""
        prix = np.array([100.0, 95.0, 110.0])
        lab, _ = triple_barrier_labels(prix, horizon=2, upper_pct=0.05, lower_pct=0.03)
        assert lab[0] == -1

    def test_end_idx_est_directement_utilisable_par_purgedkfold(self):
        prix = np.cumprod(1 + np.random.RandomState(0).normal(0, 0.01, 200)) * 100
        _, end = triple_barrier_labels(prix, horizon=10, upper_pct=0.02, lower_pct=0.02)
        for train, test in PurgedKFold(n_splits=4).split(len(prix), end):
            assert len(np.intersect1d(train, test)) == 0
