#!/usr/bin/env python3
"""Sortie machine du detecteur Python, a confronter au C++."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kairos.arb import CostModel, Detector, DeviationBasis, PairQuote

PAIRES = [
    ("EUR","USD",1.08000,1.08004), ("USD","JPY",157.000,157.006),
    ("GBP","USD",1.27150,1.27160), ("EUR","GBP",0.84930,0.84937),
    ("USD","CHF",0.88120,0.88127), ("AUD","USD",0.66410,0.66417),
    ("EUR","JPY",169.562,169.572), ("GBP","JPY",199.640,199.652),
]
d = Detector()
for b,q,bid,ask in PAIRES:
    d.add_pair(PairQuote(b,q,bid,ask))

print(f"n_devises {len(d.currencies)}")
print(f"n_paires {len(PAIRES)}")
for k in (3,4,5):
    print(f"cycles_{k} {len(d.enumerate_cycles(k))}")

c = CostModel(0.20, 2.00, 0.0)
for base in (DeviationBasis.EXECUTABLE, DeviationBasis.MID):
    for notional in (10_000, 100_000):
        opps = d.scan(c, notional, 3, 5, False, base)
        tag = f"{base.value}_{notional}"
        print(f"{tag}_n {len(opps)}")
        print(f"{tag}_best_gross {opps[0].gross_bps:.17e}")
        print(f"{tag}_best_cost {opps[0].cost_bps:.17e}")
        print(f"{tag}_best_net {opps[0].net_bps:.17e}")
        print(f"{tag}_sum_net {sum(o.net_bps for o in opps):.17e}")
        print(f"{tag}_worst_net {opps[-1].net_bps:.17e}")

l = d.resolve("GBP","USD"); print(f"gbpusd_rate {l.rate:.17e}")
l = d.resolve("USD","GBP"); print(f"usdgbp_rate {l.rate:.17e}")
