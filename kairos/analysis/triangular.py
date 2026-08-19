"""Deviation triangulaire — le livrable chiffre de la Phase 1.

Sur le triangle EUR / USD / JPY, deux boucles sont possibles.

  Sens 1 : EUR -> USD -> JPY -> EUR
      vendre EUR contre USD  au BID de EUR/USD
      vendre USD contre JPY  au BID de USD/JPY
      racheter EUR avec JPY  a l'ASK de EUR/JPY
      multiplicateur = bid(EURUSD) * bid(USDJPY) / ask(EURJPY)

  Sens 2 : EUR -> JPY -> USD -> EUR
      multiplicateur = bid(EURJPY) / ask(USDJPY) / ask(EURUSD)

Un multiplicateur superieur a 1 signale un profit BRUT. Il faut ensuite le
confronter au cout total de la boucle : c'est la seule comparaison qui decide.

On prend systematiquement bid pour vendre et ask pour acheter. Utiliser le mid
produit des deviations fantomes et c'est l'erreur la plus commune sur ce calcul.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def cost_threshold_bps(
    notional_usd: float = 10_000,
    commission_bps: float = 0.20,
    commission_floor_usd: float = 2.00,
    spread_bps: float = 0.28,
    legs: int = 3,
    slippage_bps: float = 0.0,
) -> float:
    """Seuil de rentabilite, identique a la formule de l'onglet Hypotheses."""
    commission_eff = max(commission_bps, commission_floor_usd / notional_usd * 10_000)
    return legs * (commission_eff + spread_bps / 2 + slippage_bps)


def _latest_snapshot(df: pd.DataFrame, symbols: list[str]) -> pd.DataFrame:
    """Reconstitue l'etat simultane des trois paires a chaque tick.

    Chaque tick met a jour SA paire ; les deux autres conservent leur derniere
    valeur connue. C'est exactement ce que voit un systeme en production.
    """
    wide = df.pivot_table(
        index="ts_wall_ns", columns="symbol",
        values=["bid", "ask"], aggfunc="last",
    )
    wide = wide.sort_index().ffill().dropna()
    return wide


def analyse_triangle(
    df: pd.DataFrame,
    symbols: tuple[str, str, str] = ("EUR/USD", "USD/JPY", "EUR/JPY"),
    threshold_bps: float | None = None,
    **cost_kwargs,
) -> dict:
    ab, bc, ac = symbols                      # EUR/USD, USD/JPY, EUR/JPY
    if threshold_bps is None:
        threshold_bps = cost_threshold_bps(**cost_kwargs)

    wide = _latest_snapshot(df, list(symbols))
    if wide.empty:
        return {"error": "aucun instant ou les trois paires sont connues"}

    bid = {s: wide[("bid", s)].to_numpy() for s in symbols}
    ask = {s: wide[("ask", s)].to_numpy() for s in symbols}

    mult_1 = bid[ab] * bid[bc] / ask[ac]
    mult_2 = bid[ac] / ask[bc] / ask[ab]

    dev_1 = (mult_1 - 1.0) * 10_000
    dev_2 = (mult_2 - 1.0) * 10_000
    best = np.maximum(dev_1, dev_2)           # la meilleure des deux boucles

    n = len(best)
    above = best > threshold_bps
    positive = best > 0

    return {
        "n_observations": int(n),
        "seuil_de_cout_bps": round(float(threshold_bps), 4),
        "deviation_max_bps": round(float(best.max()), 4),
        "deviation_p99_bps": round(float(np.percentile(best, 99)), 4),
        "deviation_p50_bps": round(float(np.percentile(best, 50)), 4),
        "deviation_moyenne_bps": round(float(best.mean()), 4),
        "n_brut_positif": int(positive.sum()),
        "pct_brut_positif": round(float(positive.mean() * 100), 3),
        "n_au_dessus_du_seuil": int(above.sum()),
        "pct_au_dessus_du_seuil": round(float(above.mean() * 100), 4),
        "marge_nette_si_max_bps": round(float(best.max() - threshold_bps), 4),
        "verdict": (
            "VIABLE" if above.mean() > 0.001 and best.max() > 2 * threshold_bps
            else "MARGINAL" if above.sum() > 0
            else "NON VIABLE"
        ),
    }
