"""Comptabilite des positions et du P&L.

Deux precautions qui evitent les erreurs classiques.

PRIX MOYEN D'ENTREE, pas un empilement naif. Quand une position s'agrandit, le
prix moyen se met a jour ; quand elle se reduit, le P&L realise est constate mais
le prix moyen ne bouge PAS. Confondre les deux fausse tout le P&L realise.

INVERSION DE POSITION. Passer de +100 a -50 en une execution de 150, c'est solder
+100 (P&L realise) puis ouvrir -50 au prix de l'execution. Traiter ce cas comme un
simple ajustement est une source silencieuse d'erreur.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from kairos.core.orders import Fill


@dataclass
class Portfolio:
    cash: float = 0.0
    position: float = 0.0
    avg_price: float = 0.0

    realised_pnl: float = 0.0
    total_commission: float = 0.0
    fills: list[Fill] = field(default_factory=list)

    def apply(self, fill: Fill) -> None:
        qty = fill.signed_qty                     # signe : + achat, - vente
        self.cash -= qty * fill.price
        self.cash -= fill.commission
        self.total_commission += fill.commission
        self.fills.append(fill)

        old_pos, old_avg = self.position, self.avg_price
        new_pos = old_pos + qty

        if old_pos == 0 or (old_pos > 0) == (qty > 0):
            # Ouverture ou renforcement : moyenne ponderee
            self.avg_price = (
                (abs(old_pos) * old_avg + abs(qty) * fill.price) / abs(new_pos)
                if new_pos != 0 else 0.0
            )
        elif abs(qty) <= abs(old_pos):
            # Reduction partielle ou solde exact : on realise, la moyenne ne bouge pas
            closed = abs(qty)
            direction = 1 if old_pos > 0 else -1
            self.realised_pnl += closed * (fill.price - old_avg) * direction
            if new_pos == 0:
                self.avg_price = 0.0
        else:
            # Inversion : solder l'ancienne position puis ouvrir la nouvelle
            closed = abs(old_pos)
            direction = 1 if old_pos > 0 else -1
            self.realised_pnl += closed * (fill.price - old_avg) * direction
            self.avg_price = fill.price

        self.position = new_pos

    def unrealised_pnl(self, mark: float) -> float:
        if self.position == 0:
            return 0.0
        return self.position * (mark - self.avg_price)

    def equity(self, mark: float) -> float:
        """Valeur liquidative : tresorerie + valeur de marche de la position."""
        return self.cash + self.position * mark

    def total_pnl(self, mark: float) -> float:
        return self.realised_pnl + self.unrealised_pnl(mark)
