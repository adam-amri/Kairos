"""Simulateur cash and carry — la strategie cible, avec son risque de liquidation.

Le classeur chiffre les couts mais DESIGNE la liquidation comme risque numero un
sans la chiffrer. Ce module comble ce trou.

LA MECANIQUE
    Long X de spot, short X de perpetuel. Les deux jambes se compensent : si le
    prix monte, le spot gagne exactement ce que le perpetuel perd. La position est
    delta neutre et le revenu vient du funding.

LE PIEGE, ET C'EST LUI QUI LIQUIDE LES GENS
    Les deux jambes ne vivent PAS sur le meme compte. Le spot est sur le compte au
    comptant, le perpetuel sur le compte derives — separation renforcee sous MiFID.

    En MARGE ISOLEE, la jambe perpetuelle peut donc etre liquidee alors meme qu'on
    detient une plus-value latente EXACTEMENT EGALE sur le spot, simplement parce
    qu'elle n'est pas mobilisable assez vite comme collateral.

    On est alors liquide sur une position dont le risque net etait nul. Ce n'est
    pas un risque de marche, c'est un risque de PLOMBERIE — et c'est bien pour cela
    qu'il faut le simuler plutot que le raisonner.

    En MARGE CROISEE, les deux jambes se compensent et le probleme disparait
    largement. La difference entre les deux modes est ce que ce module mesure.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from kairos.core.funding import FundingEvent


@dataclass
class CarryConfig:
    spot_fee_bps: float = 25.0            # Kraken UE, tier de base
    perp_fee_bps: float = 2.0
    max_leverage: float = 2.0             # plafond retail UE sur crypto majeurs
    maintenance_margin_rate: float = 0.005   # 0,5 % du notionnel
    isolated_margin: bool = True          # LE parametre decisif
    slippage_bps: float = 2.0

    def __post_init__(self) -> None:
        if self.max_leverage <= 0:
            raise ValueError("max_leverage doit etre strictement positif")
        if not 0 < self.maintenance_margin_rate < 1:
            raise ValueError("maintenance_margin_rate doit etre dans ]0, 1[")


@dataclass
class CarryResult:
    entry_price: float
    exit_price: float
    notional: float
    margin_posted: float
    capital_engage: float

    funding_recu_bps: float = 0.0
    frais_totaux_bps: float = 0.0
    net_sur_position_bps: float = 0.0
    net_sur_capital_bps: float = 0.0

    liquide: bool = False
    ts_liquidation: int | None = None
    prix_liquidation_theorique: float = 0.0
    marge_minimale_atteinte: float = math.inf

    jours_detenus: float = 0.0
    n_funding: int = 0
    funding_negatifs: int = 0
    historique_marge: list[tuple[int, float]] = field(default_factory=list)

    @property
    def net_annualise(self) -> float:
        if self.jours_detenus <= 0:
            return 0.0
        return self.net_sur_capital_bps / 10_000 * 365 / self.jours_detenus


class CarrySimulator:
    def __init__(self, config: CarryConfig | None = None) -> None:
        self.cfg = config or CarryConfig()

    # ------------------------------------------------------------------
    def prix_de_liquidation(self, entry_price: float) -> float:
        """Prix au-dela duquel la jambe short est liquidee, en marge isolee.

        Marge restante = M + X(p0 - p), exigence = mmr . X . p
        Liquidation quand  M/X + p0 - p <= mmr . p
        soit               p >= (p0/L + p0) / (1 + mmr)

        En marge croisee, la plus-value du spot compense la perte du perpetuel :
        le seuil est repousse tres loin, et on renvoie l'infini.
        """
        c = self.cfg
        if not c.isolated_margin:
            return math.inf
        return entry_price * (1 / c.max_leverage + 1) / (1 + c.maintenance_margin_rate)

    # ------------------------------------------------------------------
    def run(
        self,
        prices: list[tuple[int, float]],          # (ts_ns, prix)
        funding: list[FundingEvent],
        capital: float = 10_000.0,
    ) -> CarryResult:
        if not prices:
            raise ValueError("aucun prix fourni")
        c = self.cfg

        ts0, p0 = prices[0]

        # Capital = spot (1) + marge sur le short (1/L). D'ou 1 + 1/L par unite.
        capital_par_unite = 1 + 1 / c.max_leverage
        notional_valeur = capital / capital_par_unite
        qty = notional_valeur / p0
        margin = notional_valeur / c.max_leverage

        frais_entree_bps = c.spot_fee_bps + c.perp_fee_bps + c.slippage_bps / 2
        frais_sortie_bps = c.spot_fee_bps + c.perp_fee_bps + c.slippage_bps / 2

        res = CarryResult(
            entry_price=p0, exit_price=p0, notional=notional_valeur,
            margin_posted=margin, capital_engage=capital,
            prix_liquidation_theorique=self.prix_de_liquidation(p0),
        )

        funding_cumule = 0.0
        idx_f = 0
        f_tries = sorted(funding, key=lambda e: e.ts_ns)

        for ts, p in prices:
            # Funding echu depuis le dernier point de prix
            while idx_f < len(f_tries) and f_tries[idx_f].ts_ns <= ts:
                ev = f_tries[idx_f]
                # position perpetuelle = -qty (short)
                funding_cumule += ev.payment(-qty)
                res.n_funding += 1
                if ev.rate_bps < 0:
                    res.funding_negatifs += 1
                idx_f += 1

            # Perte latente de la jambe short
            perp_latent = qty * (p0 - p)
            equity_perp = margin + perp_latent + funding_cumule

            if not c.isolated_margin:
                # Marge croisee : la plus-value du spot est mobilisable
                spot_latent = qty * (p - p0)
                equity_perp += spot_latent

            exigence = c.maintenance_margin_rate * qty * p
            ratio = equity_perp / (qty * p) if qty * p > 0 else 0.0
            res.marge_minimale_atteinte = min(res.marge_minimale_atteinte, ratio)
            res.historique_marge.append((ts, ratio))

            if equity_perp <= exigence:
                res.liquide = True
                res.ts_liquidation = ts
                res.exit_price = p
                break

            res.exit_price = p

        ts_fin = res.ts_liquidation or prices[-1][0]
        res.jours_detenus = (ts_fin - ts0) / 1e9 / 86_400

        res.funding_recu_bps = funding_cumule / notional_valeur * 10_000
        res.frais_totaux_bps = frais_entree_bps + (0.0 if res.liquide else frais_sortie_bps)

        if res.liquide:
            # Liquidation : la marge du perpetuel est perdue. Le spot est conserve,
            # avec sa plus-value latente — mais la couverture a disparu et la
            # position n'est plus neutre.
            perte_marge_bps = -margin / notional_valeur * 10_000
            res.net_sur_position_bps = (res.funding_recu_bps + perte_marge_bps
                                        - res.frais_totaux_bps)
        else:
            res.net_sur_position_bps = res.funding_recu_bps - res.frais_totaux_bps

        res.net_sur_capital_bps = res.net_sur_position_bps * (notional_valeur / capital)
        return res


# ---------------------------------------------------------------- utilitaires
def funding_regulier(
    ts0: int, jours: float, rate_bps: float, mark: float, par_jour: int = 3
) -> list[FundingEvent]:
    """Serie de funding a taux constant — pour un scenario de reference."""
    pas = int(86_400e9 / par_jour)
    n = int(jours * par_jour)
    return [FundingEvent(ts_ns=ts0 + (i + 1) * pas, rate_bps=rate_bps, mark_price=mark)
            for i in range(n)]


def chemin_choc(
    ts0: int, jours: float, p0: float, choc_pct: float, jour_du_choc: float,
    points_par_jour: int = 24,
) -> list[tuple[int, float]]:
    """Prix plat, puis choc lineaire sur une journee, puis plat.

    Volontairement simple : on cherche a isoler l'effet du choc, pas a simuler un
    marche realiste. Un chemin plus riche viendra des donnees de la Phase 1.
    """
    pas = int(86_400e9 / points_par_jour)
    n = int(jours * points_par_jour)
    debut = int(jour_du_choc * points_par_jour)
    fin = debut + points_par_jour
    out = []
    for i in range(n):
        if i < debut:
            p = p0
        elif i < fin:
            p = p0 * (1 + choc_pct * (i - debut) / (fin - debut))
        else:
            p = p0 * (1 + choc_pct)
        out.append((ts0 + i * pas, p))
    return out
