"""Couche de risque — controles prealables a tout ordre.

POURQUOI CETTE COUCHE MERITE PLUS D'ATTENTION QUE LA STRATEGIE
    Le bug qui coute de l'argent n'est presque jamais dans le signal. C'est un
    ordre duplique apres reconnexion, un etat desynchronise, un zero de trop dans
    un fichier de configuration. Un debutant passe des semaines sur l'alpha et une
    soiree sur la gestion des ordres : c'est exactement le mauvais partage.

TROIS PRINCIPES ENCODES ICI

    1. REFUS PAR DEFAUT. Toute situation non explicitement autorisee est refusee.
       Une limite absente n'est pas une limite infinie, c'est une erreur de
       configuration — et on ne trade pas sur une configuration incomprise.

    2. LE COUPE-CIRCUIT PRIME SUR TOUT. Il est verifie en premier, avant meme de
       regarder l'ordre. Il doit pouvoir etre actionne sans acces au processus.

    3. APRES UNE PERTE JOURNALIERE, LE REDEMARRAGE EST MANUEL. Jamais de reprise
       automatique. Un systeme qui repart seul apres avoir atteint sa limite de
       perte n'a pas de limite de perte, il a un ralentisseur.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from kairos.core.orders import Order, Side
from kairos.core.portfolio import Portfolio


class RiskDecision(str, Enum):
    ALLOW = "allow"
    REJECT = "reject"
    HALT = "halt"          # arret complet : redemarrage manuel obligatoire


@dataclass
class RiskLimits:
    """Toutes les limites sont OBLIGATOIRES. Aucune valeur par defaut permissive."""

    max_gross_position: float          # somme des valeurs absolues
    max_net_position: float            # exposition directionnelle nette
    max_order_notional: float          # taille d'un ordre unique
    max_daily_loss_bps: float          # sur le capital de reference
    max_leverage: float                # position / capital
    min_margin_ratio: float            # marge restante / notionnel
    kill_switch_path: str | Path | None = None

    def __post_init__(self) -> None:
        for nom in ("max_gross_position", "max_net_position", "max_order_notional",
                    "max_daily_loss_bps", "max_leverage", "min_margin_ratio"):
            v = getattr(self, nom)
            if v is None or v <= 0:
                raise ValueError(
                    f"{nom} doit etre strictement positif. Une limite absente n'est "
                    "pas une limite infinie, c'est une erreur de configuration."
                )
        if self.max_net_position > self.max_gross_position:
            raise ValueError("max_net_position ne peut exceder max_gross_position")


@dataclass
class RiskState:
    """Etat mutable suivi entre les appels."""

    capital_reference: float
    pnl_debut_de_jour: float = 0.0
    halted: bool = False
    motif_halt: str = ""
    rejets: list[str] = field(default_factory=list)

    def perte_du_jour_bps(self, pnl_courant: float) -> float:
        """Positive quand on perd."""
        if self.capital_reference <= 0:
            return 0.0
        return (self.pnl_debut_de_jour - pnl_courant) / self.capital_reference * 10_000


class RiskGate:
    def __init__(self, limits: RiskLimits, state: RiskState) -> None:
        self.limits = limits
        self.state = state

    # ------------------------------------------------------------------
    def kill_switch_actif(self) -> bool:
        """Presence d'un fichier : actionnable par SSH, script ou telephone.

        Deliberement primitif. Un coupe-circuit qui depend du bon fonctionnement
        du processus qu'il doit arreter ne sert a rien.
        """
        p = self.limits.kill_switch_path
        return bool(p) and Path(p).exists()

    # ------------------------------------------------------------------
    def check(
        self,
        order: Order,
        pf: Portfolio,
        mark: float,
        margin_ratio: float | None = None,
    ) -> tuple[RiskDecision, str]:
        L, S = self.limits, self.state

        # 1. Arret deja prononce : rien ne repart tout seul
        if S.halted:
            return RiskDecision.HALT, f"systeme arrete : {S.motif_halt}"

        # 2. Coupe-circuit, avant tout examen de l'ordre
        if self.kill_switch_actif():
            S.halted = True
            S.motif_halt = f"kill switch present ({L.kill_switch_path})"
            return RiskDecision.HALT, S.motif_halt

        # 3. Perte journaliere
        perte = S.perte_du_jour_bps(pf.total_pnl(mark))
        if perte >= L.max_daily_loss_bps:
            S.halted = True
            S.motif_halt = (f"perte journaliere {perte:.1f} bps >= limite "
                            f"{L.max_daily_loss_bps:.1f} bps — redemarrage manuel requis")
            return RiskDecision.HALT, S.motif_halt

        # 4. Marge insuffisante
        if margin_ratio is not None and margin_ratio < L.min_margin_ratio:
            S.halted = True
            S.motif_halt = (f"ratio de marge {margin_ratio:.4f} < minimum "
                            f"{L.min_margin_ratio:.4f}")
            return RiskDecision.HALT, S.motif_halt

        # 5. Taille de l'ordre
        notional = abs(order.qty * (order.price or mark))
        if notional > L.max_order_notional:
            return self._rejet(f"notionnel de l'ordre {notional:,.0f} > maximum "
                               f"{L.max_order_notional:,.0f}")

        # 6. UN ORDRE QUI REDUIT L'EXPOSITION EST TOUJOURS AUTORISE
        #
        # Sans cette exception, un depassement de limite — provoque par exemple par
        # un simple mouvement de prix, sans le moindre ordre de notre part — bloque
        # aussi les ordres de SORTIE. On se retrouve enferme dans une position
        # devenue trop grosse, sans pouvoir la reduire.
        #
        # Un garde-fou qui empeche de se degager est pire que pas de garde-fou :
        # il transforme un depassement passager en position subie.
        delta = order.qty * order.side.sign
        nouvelle = pf.position + delta
        reduit_le_risque = abs(nouvelle) < abs(pf.position)

        if reduit_le_risque:
            return RiskDecision.ALLOW, "ordre reducteur d'exposition, toujours autorise"

        # 7. Positions resultantes — uniquement pour les ordres qui AUGMENTENT le risque
        if abs(nouvelle) > L.max_net_position:
            return self._rejet(f"position nette resultante {nouvelle:,.0f} > maximum "
                               f"{L.max_net_position:,.0f}")

        brut = abs(nouvelle * mark)
        if brut > L.max_gross_position:
            return self._rejet(f"position brute resultante {brut:,.0f} > maximum "
                               f"{L.max_gross_position:,.0f}")

        # 8. Levier
        if S.capital_reference > 0:
            levier = brut / S.capital_reference
            if levier > L.max_leverage:
                return self._rejet(f"levier resultant {levier:.2f}x > maximum "
                                   f"{L.max_leverage:.2f}x")

        return RiskDecision.ALLOW, "ok"

    def _rejet(self, motif: str) -> tuple[RiskDecision, str]:
        self.state.rejets.append(motif)
        return RiskDecision.REJECT, motif

    # ------------------------------------------------------------------
    def nouvelle_journee(self, pnl_courant: float) -> None:
        """Reinitialise le compteur de perte. NE leve PAS un arret en cours."""
        self.state.pnl_debut_de_jour = pnl_courant

    def reprise_manuelle(self) -> None:
        """A n'appeler qu'apres avoir compris ce qui s'est passe."""
        self.state.halted = False
        self.state.motif_halt = ""
