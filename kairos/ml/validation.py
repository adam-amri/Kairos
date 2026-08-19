"""Validation croisee pour series temporelles financieres.

POURQUOI LA VALIDATION CROISEE ORDINAIRE EST INVALIDE ICI
    Un k-fold standard suppose des echantillons independants. En finance ils ne le
    sont pas : l'etiquette de l'echantillon a l'instant t depend de ce qui se passe
    entre t et t+h. Si t est dans l'apprentissage et t+1 dans le test, leurs
    fenetres se chevauchent et l'information du test a fuite dans l'apprentissage.

    Le modele obtient alors des scores splendides en validation et s'effondre en
    reel. C'est la premiere cause d'echec du machine learning applique aux marches,
    devant le choix du modele, largement.

DEUX CORRECTIFS (Lopez de Prado)
    PURGE   retirer de l'apprentissage tout echantillon dont la fenetre d'etiquette
            chevauche la periode de test.
    EMBARGO retirer en plus une bande juste apres le test, car l'autocorrelation
            des series fait fuiter l'information au-dela du simple chevauchement.
"""
from __future__ import annotations

from typing import Iterator

import numpy as np


class PurgedKFold:
    """K-fold avec purge et embargo, blocs de test contigus et chronologiques.

    On ne melange JAMAIS les indices : l'ordre temporel est l'information.
    """

    def __init__(self, n_splits: int = 5, embargo_pct: float = 0.01) -> None:
        if n_splits < 2:
            raise ValueError("n_splits doit valoir au moins 2")
        if not 0.0 <= embargo_pct < 1.0:
            raise ValueError("embargo_pct doit etre dans [0, 1)")
        self.n_splits = n_splits
        self.embargo_pct = embargo_pct

    def split(
        self, n_samples: int, label_end: np.ndarray | list[int] | None = None
    ) -> Iterator[tuple[np.ndarray, np.ndarray]]:
        """label_end[i] : indice auquel l'etiquette de i est connue.

        Par defaut label_end[i] = i, soit une etiquette instantanee et aucun
        chevauchement — c'est rarement le cas reel, et le renseigner est ce qui
        rend la purge utile.
        """
        if label_end is None:
            label_end = np.arange(n_samples)
        label_end = np.asarray(label_end)
        if len(label_end) != n_samples:
            raise ValueError("label_end doit avoir la meme longueur que n_samples")

        embargo = int(n_samples * self.embargo_pct)
        indices = np.arange(n_samples)

        for test_idx in np.array_split(indices, self.n_splits):
            if len(test_idx) == 0:
                continue
            t0, t1 = int(test_idx[0]), int(test_idx[-1])

            in_test = (indices >= t0) & (indices <= t1)
            # Purge : fenetre [i, label_end[i]] chevauchant [t0, t1]
            overlaps = (indices <= t1) & (label_end >= t0)
            # Embargo : bande immediatement posterieure au test
            embargoed = (indices > t1) & (indices <= t1 + embargo)

            train_idx = indices[~(in_test | overlaps | embargoed)]
            yield train_idx, test_idx


def triple_barrier_labels(
    prices: np.ndarray,
    horizon: int,
    upper_pct: float,
    lower_pct: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Etiquetage par triple barriere.

    Une etiquette a horizon fixe ignore le chemin : « +2 % dans 10 minutes » traite
    identiquement une montee reguliere et une chute de 5 % suivie d'un rebond. Or la
    seconde aurait declenche un stop, et le trade n'aurait jamais atteint la dixieme
    minute.

    Trois barrieres : profit, perte, temps. La premiere touchee decide.

    Retourne (etiquettes dans {-1, 0, +1}, indice de resolution de chaque etiquette)
    — ce second tableau est exactement le `label_end` attendu par PurgedKFold.
    """
    n = len(prices)
    labels = np.zeros(n, dtype=int)
    end_idx = np.arange(n)

    for i in range(n):
        stop = min(i + horizon, n - 1)
        p0 = prices[i]
        up, lo = p0 * (1 + upper_pct), p0 * (1 - lower_pct)
        end_idx[i] = stop                       # par defaut : barriere temporelle
        for j in range(i + 1, stop + 1):
            if prices[j] >= up:
                labels[i], end_idx[i] = 1, j
                break
            if prices[j] <= lo:
                labels[i], end_idx[i] = -1, j
                break
    return labels, end_idx
