#!/usr/bin/env python3
"""Lance un backtest et produit le rapport de performance.

    python scripts/backtest.py --duration 300 --latency-ms 50 --trials 1

Le parametre --trials est le plus important et le plus facile a se mentir a
soi-meme : c'est le nombre de configurations que tu as REELLEMENT essayees. Chaque
variante de parametre compte. Le Deflated Sharpe s'en sert pour distinguer une
decouverte d'un maximum de bruit.
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kairos.backtest import BacktestEngine, CostModel
from kairos.backtest.metrics import report
from kairos.feed.synthetic import SyntheticFeed
from kairos.strategy import PassiveQuoter


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--duration", type=int, default=300, help="secondes simulees")
    ap.add_argument("--ticks-per-s", type=int, default=20)
    ap.add_argument("--latency-ms", type=float, default=50.0)
    ap.add_argument("--trade-ratio", type=float, default=0.5,
                    help="fraction des diminutions de taille qui font avancer la file")
    ap.add_argument("--edge-bps", type=float, default=1.0)
    ap.add_argument("--qty", type=float, default=25_000)
    ap.add_argument("--commission-bps", type=float, default=0.20)
    ap.add_argument("--commission-floor", type=float, default=2.00)
    ap.add_argument("--trials", type=int, default=1,
                    help="nombre HONNETE de configurations essayees")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    quotes = [q for q in SyntheticFeed(duration_s=args.duration,
                                       ticks_per_s=args.ticks_per_s,
                                       seed=args.seed).stream()
              if q.symbol == "EUR/USD"]

    engine = BacktestEngine(
        strategy=PassiveQuoter(edge_bps=args.edge_bps, qty=args.qty),
        cost=CostModel(commission_bps=args.commission_bps,
                       commission_floor=args.commission_floor),
        latency_ns=int(args.latency_ms * 1e6),
        trade_ratio=args.trade_ratio,
        initial_cash=100_000.0,
    )
    res = engine.run(quotes)

    print("=" * 58)
    print("EXECUTION")
    print("=" * 58)
    print(f"Quotes traitees   : {res.n_quotes:,}")
    print(f"Ordres emis       : {res.n_orders:,}")
    print(f"Executions        : {res.n_fills:,}")
    print(f"Annulations       : {res.n_cancelled:,}")
    taux = res.n_fills / res.n_orders * 100 if res.n_orders else 0
    print(f"Taux d'execution  : {taux:.2f} %")
    print(f"Commissions       : {res.portfolio.total_commission:,.2f}")
    print(f"Position finale   : {res.portfolio.position:,.0f}")
    print()
    print("=" * 58)
    print("PERFORMANCE")
    print("=" * 58)
    eq = [v for _, v in res.equity_curve]
    # Frequence deduite de l'etendue temporelle REELLE des donnees, et non d'une
    # convention posee a la main : c'est la seule facon d'avoir un facteur juste.
    span_s = (res.equity_curve[-1][0] - res.equity_curve[0][0]) / 1e9
    ppy = len(res.returns) * (365.25 * 24 * 3600) / span_s if span_s > 0 else 252
    print(report(res.returns, eq, n_trials=args.trials, periods_per_year=ppy))
    print()
    print("Rappel : trade_ratio =", args.trade_ratio,
          "— hypothese non calibree. Tout resultat passif reste indicatif")
    print("tant qu'elle n'a pas ete confrontee aux executions reelles (Phase 3).")


if __name__ == "__main__":
    main()
