#!/usr/bin/env python3
"""Collecte : branche un feed, normalise, persiste, mesure la latence.

    python scripts/collect.py                 # utilise config.yaml
    python scripts/collect.py --venue synthetic --duration 30
"""
from __future__ import annotations
import argparse
import json
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml

from kairos.clock import LatencyTracker
from kairos.feed import make_feed
from kairos.store import ParquetWriter

_stop = False


def _handle(_sig, _frm):
    global _stop
    _stop = True
    print("\n[kairos] arret demande, vidage du buffer...", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--venue", default=None, help="ecrase la valeur du fichier de config")
    ap.add_argument("--duration", type=int, default=None, help="secondes (feed synthetique)")
    args = ap.parse_args()

    cfg_path = Path(args.config)
    cfg = yaml.safe_load(cfg_path.read_text()) if cfg_path.exists() else {}
    if args.venue:
        cfg["venue"] = args.venue
    if args.duration:
        cfg.setdefault("synthetic", {})["duration_s"] = args.duration

    signal.signal(signal.SIGINT, _handle)

    feed = make_feed(cfg)
    store_cfg = cfg.get("store", {})
    writer = ParquetWriter(
        path=store_cfg.get("path", "./data"),
        flush_every=store_cfg.get("flush_every", 5_000),
    )
    lat = LatencyTracker()

    print(f"[kairos] collecte via '{feed.name}' -> {writer.filepath}", flush=True)
    count = 0
    try:
        for q in feed.stream():
            writer.add(q)
            if q.latency_ns:
                lat.record(q.latency_ns)
            count += 1
            if count % 5_000 == 0:
                print(f"[kairos] {count:,} quotes", flush=True)
            if _stop:
                break
    finally:
        info = writer.close()
        print(json.dumps({"collecte": info, "latence_venue_vers_local": lat.summary()},
                         indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
