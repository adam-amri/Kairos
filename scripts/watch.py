#!/usr/bin/env python3
"""Boucle du watchdog — a executer sur le Raspberry, jamais sur le VPS.

    python scripts/watch.py --heartbeat /shared/heartbeat.json

Escalade volontairement asymetrique : alerter tot, liquider tard. Liquider sur un
hoquet reseau coute des frais et des positions fermees pour rien ; ne pas liquider
sur une vraie panne coute beaucoup plus.
"""
from __future__ import annotations
import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kairos.ops.watchdog import Watchdog, WatchdogVerdict


def alert(msg: str) -> None:
    url = os.environ.get("ALERT_WEBHOOK_URL", "")
    print(f"[watchdog] {msg}", flush=True)
    if not url:
        return
    try:
        import requests
        requests.post(url, json={"text": f"[Kairos] {msg}"}, timeout=5)
    except Exception as e:                       # une alerte ne doit jamais tuer le watchdog
        print(f"[watchdog] echec de l'alerte : {e}", flush=True)


def flatten() -> None:
    """Liquidation d'urgence via les cles propres au watchdog.

    A IMPLEMENTER contre ta plateforme, et a TESTER en paper avant tout usage reel.
    Un coupe-circuit jamais declenche en repetition n'est pas un coupe-circuit,
    c'est une intention.
    """
    alert("LIQUIDATION D'URGENCE DECLENCHEE")
    raise NotImplementedError(
        "Implemente la liquidation contre ton venue, puis teste-la en paper."
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--heartbeat", default=os.environ.get("HEARTBEAT_PATH", "/shared/heartbeat.json"))
    ap.add_argument("--interval", type=float, default=5.0)
    ap.add_argument("--stale-after", type=float, default=float(os.environ.get("STALE_AFTER_S", 30)))
    ap.add_argument("--dead-after", type=float, default=float(os.environ.get("DEAD_AFTER_S", 120)))
    ap.add_argument("--dry-run", action="store_true", help="alerte sans liquider")
    args = ap.parse_args()

    wd = Watchdog(args.heartbeat, stale_after_s=args.stale_after, dead_after_s=args.dead_after)
    print(f"[watchdog] surveillance de {args.heartbeat} "
          f"(stale {args.stale_after}s / dead {args.dead_after}s)", flush=True)

    last = None
    while True:
        verdict, ctx = wd.check()
        if verdict is not last:                  # on n'alerte qu'aux transitions
            alert(f"{verdict.value} — {ctx}")
            last = verdict
        if Watchdog.should_flatten(verdict):
            if args.dry_run:
                alert("dry-run : liquidation qui aurait ete declenchee")
            else:
                flatten()
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
