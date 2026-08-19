"""Strategie cash and carry — regles d'entree, de sortie et de surveillance.

Elle ne cherche aucun signal directionnel : la position est delta neutre par
construction. Les seules decisions sont QUAND entrer, QUAND sortir, et QUAND
renforcer la marge.

La regle de sortie la plus importante n'est pas le profit : c'est le passage du
funding en territoire negatif de facon persistante. A ce moment, la position ne
rapporte plus, elle coute — et le cout court tant qu'on la garde.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class CarrySignal(str, Enum):
    ENTRER = "entrer"
    TENIR = "tenir"
    SORTIR = "sortir"
    RENFORCER_MARGE = "renforcer_marge"
    ATTENDRE = "attendre"


@dataclass
class CashAndCarryStrategy:
    """Regles explicites, toutes justifiees par le modele de couts."""

    # Seuil d'entree : le funding doit couvrir les frais dans un delai acceptable.
    cout_aller_retour_bps: float = 54.0      # France, grille Kraken
    jours_amortissement_max: float = 25.0    # au-dela, on ne s'engage pas

    # Sortie sur funding durablement negatif
    fenetre_funding: int = 9                 # 9 periodes = 3 jours
    seuil_negatifs_pour_sortir: int = 6      # majorite nette sur la fenetre

    # Marge
    ratio_marge_cible: float = 0.30
    ratio_marge_alerte: float = 0.15

    _historique: list[float] = field(default_factory=list)

    # ------------------------------------------------------------------
    def funding_minimal_requis_bps(self) -> float:
        """Funding par periode en dessous duquel l'entree n'a pas de sens."""
        periodes = self.jours_amortissement_max * 3
        return self.cout_aller_retour_bps / periodes

    def observer_funding(self, rate_bps: float) -> None:
        self._historique.append(rate_bps)
        if len(self._historique) > self.fenetre_funding:
            self._historique.pop(0)

    # ------------------------------------------------------------------
    def decider(
        self, en_position: bool, funding_actuel_bps: float,
        ratio_marge: float | None = None,
    ) -> tuple[CarrySignal, str]:
        self.observer_funding(funding_actuel_bps)

        if not en_position:
            seuil = self.funding_minimal_requis_bps()
            if funding_actuel_bps < seuil:
                return (CarrySignal.ATTENDRE,
                        f"funding {funding_actuel_bps:.3f} bps < seuil {seuil:.3f} bps "
                        f"(amortissement des frais en plus de {self.jours_amortissement_max:.0f} j)")
            return (CarrySignal.ENTRER,
                    f"funding {funding_actuel_bps:.3f} bps >= seuil {seuil:.3f} bps")

        # En position — la marge prime sur toute consideration de rendement
        if ratio_marge is not None:
            if ratio_marge < self.ratio_marge_alerte:
                return (CarrySignal.SORTIR,
                        f"ratio de marge {ratio_marge:.3f} sous le seuil d'alerte "
                        f"{self.ratio_marge_alerte:.3f} — on debouche avant d'etre debouche")
            if ratio_marge < self.ratio_marge_cible:
                return (CarrySignal.RENFORCER_MARGE,
                        f"ratio de marge {ratio_marge:.3f} sous la cible "
                        f"{self.ratio_marge_cible:.3f}")

        negatifs = sum(1 for r in self._historique if r < 0)
        if (len(self._historique) >= self.fenetre_funding
                and negatifs >= self.seuil_negatifs_pour_sortir):
            return (CarrySignal.SORTIR,
                    f"{negatifs}/{len(self._historique)} periodes de funding negatif — "
                    "la position coute au lieu de rapporter")

        return CarrySignal.TENIR, "funding positif, marge suffisante"
