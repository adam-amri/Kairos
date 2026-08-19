"""Watchdog independant — le role du Raspberry Pi.

PRINCIPE NON NEGOCIABLE
    Le coupe-circuit ne doit jamais tourner sur la machine qu'il coupe.
    Si le VPS gele, sature sa RAM ou perd le reseau, un garde-fou heberge sur ce
    meme VPS gele avec lui. Un kill switch co-localise est un kill switch decoratif.

D'ou la repartition :
    VPS       -> moteur d'execution, detient les positions
    Raspberry -> watchdog, materiel distinct, reseau distinct, alimentation distincte

Le watchdog possede SES PROPRES cles API, avec le droit de passer et d'annuler des
ordres mais SANS droit de retrait. Il peut donc liquider meme si le trader est mort,
et une compromission du Raspberry ne coute pas les fonds.

Le heartbeat porte un etat, pas seulement une date : un trader vivant mais bloque
dans une boucle d'erreur est aussi dangereux qu'un trader mort.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path


class WatchdogVerdict(str, Enum):
    OK = "ok"                    # tout va bien
    STALE = "stale"              # heartbeat en retard, on alerte
    DEAD = "dead"                # trop en retard, on liquide
    UNHEALTHY = "unhealthy"      # vivant mais il se declare en erreur
    NO_HEARTBEAT = "no_heartbeat"  # jamais vu de signe de vie


@dataclass
class Heartbeat:
    """Emis par le trader, lu par le watchdog."""

    ts_wall_ns: int
    healthy: bool
    state: str                   # "flat" | "long" | "short" | "reconciling" | "halted"
    open_positions: int
    pnl_bps: float
    last_error: str = ""

    def write(self, path: str | Path) -> None:
        """Ecriture atomique : ecrire puis renommer.

        Sans cela, le watchdog peut lire un fichier a moitie ecrit et conclure a
        une panne alors que tout va bien. Le renommage est atomique sur POSIX.
        """
        path = Path(path)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(asdict(self)))
        os.replace(tmp, path)

    @classmethod
    def read(cls, path: str | Path) -> "Heartbeat | None":
        p = Path(path)
        if not p.exists():
            return None
        try:
            return cls(**json.loads(p.read_text()))
        except (json.JSONDecodeError, TypeError):
            return None   # fichier corrompu : traite comme une absence, jamais comme un OK

    @classmethod
    def now(cls, healthy: bool = True, state: str = "flat", **kw) -> "Heartbeat":
        return cls(ts_wall_ns=time.time_ns(), healthy=healthy, state=state,
                   open_positions=kw.pop("open_positions", 0),
                   pnl_bps=kw.pop("pnl_bps", 0.0), **kw)


class Watchdog:
    """Evalue la sante du trader et decide de l'escalade.

    Deux seuils volontairement distincts : alerter tot, liquider tard. Liquider sur
    un simple hoquet reseau coute des frais et des positions fermees pour rien.
    """

    def __init__(
        self,
        heartbeat_path: str | Path,
        stale_after_s: float = 30.0,
        dead_after_s: float = 120.0,
    ) -> None:
        if dead_after_s <= stale_after_s:
            raise ValueError("dead_after_s doit etre strictement superieur a stale_after_s")
        self.heartbeat_path = Path(heartbeat_path)
        self.stale_after_s = stale_after_s
        self.dead_after_s = dead_after_s

    def check(self, now_ns: int | None = None) -> tuple[WatchdogVerdict, dict]:
        now_ns = now_ns if now_ns is not None else time.time_ns()
        hb = Heartbeat.read(self.heartbeat_path)

        if hb is None:
            return WatchdogVerdict.NO_HEARTBEAT, {"age_s": None}

        age_s = (now_ns - hb.ts_wall_ns) / 1e9
        ctx = {
            "age_s": round(age_s, 2),
            "state": hb.state,
            "open_positions": hb.open_positions,
            "last_error": hb.last_error,
        }

        # Un trader qui se declare malade avec des positions ouvertes prime sur l'age :
        # il est vivant, il repond, et c'est precisement pour cela qu'il faut agir.
        if not hb.healthy and hb.open_positions > 0:
            return WatchdogVerdict.UNHEALTHY, ctx
        if age_s > self.dead_after_s:
            return WatchdogVerdict.DEAD, ctx
        if age_s > self.stale_after_s:
            return WatchdogVerdict.STALE, ctx
        return WatchdogVerdict.OK, ctx

    @staticmethod
    def should_flatten(verdict: WatchdogVerdict) -> bool:
        """Seuls DEAD et UNHEALTHY declenchent une liquidation."""
        return verdict in (WatchdogVerdict.DEAD, WatchdogVerdict.UNHEALTHY)
