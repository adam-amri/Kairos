#!/usr/bin/env python3
"""Analyse : le verdict chiffre de la Phase 1.

    python scripts/analyze.py data/quotes_*.parquet
"""
from __future__ import annotations
import argparse
import glob
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import yaml

from kairos.analysis import analyse_triangle


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+", help="chemins ou motifs glob")
    ap.add_argument("--config", default="config.yaml")
    args = ap.parse_args()

    paths: list[str] = []
    for pat in args.files:
        paths.extend(glob.glob(pat))
    if not paths:
        sys.exit("aucun fichier trouve")

    def _read(fp: str) -> pd.DataFrame:
        return pd.read_parquet(fp) if fp.endswith(".parquet") else pd.read_csv(fp)

    df = pd.concat([_read(p) for p in sorted(paths)], ignore_index=True)

    cfg_path = Path(args.config)
    costs = (yaml.safe_load(cfg_path.read_text()).get("costs", {})
             if cfg_path.exists() else {})

    res = analyse_triangle(
        df,
        notional_usd=costs.get("notional_usd", 10_000),
        commission_bps=costs.get("commission_bps", 0.20),
        commission_floor_usd=costs.get("commission_floor_usd", 2.00),
        spread_bps=costs.get("spread_bps", 0.28),
        legs=costs.get("legs", 3),
    )

    print(json.dumps(res, indent=2, ensure_ascii=False))
    print()
    print(f"  Verdict : {res.get('verdict')}")
    print(f"  {res.get('pct_au_dessus_du_seuil')}% des instants depassent le seuil de cout")


if __name__ == "__main__":
    main()
