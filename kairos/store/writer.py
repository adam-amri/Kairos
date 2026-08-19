"""Persistance par fragments.

Deux decisions importantes.

1. ECRITURE PAR FRAGMENTS, jamais en append.
   Relire le fichier entier pour y ajouter un lot donne un cout quadratique :
   sur une session de plusieurs millions de ticks le collecteur finit par passer
   tout son temps a recopier du disque. On ecrit donc des fragments numerotes,
   que l'analyseur relit d'un coup via un glob. C'est aussi ce qui rend une
   session interrompue exploitable : les fragments deja ecrits sont intacts.

2. REPLI SUR CSV si pyarrow est absent.
   Parquet reste le format cible — compression et typage. Mais un collecteur qui
   refuse de demarrer parce qu'une dependance optionnelle manque perd des donnees
   de marche qu'on ne pourra jamais rejouer. On degrade, on previent, on continue.
"""
from __future__ import annotations
import os
import warnings
from datetime import datetime, timezone

import pandas as pd

from kairos.events import Quote


def _parquet_available() -> bool:
    try:
        import pyarrow  # noqa: F401
        return True
    except ImportError:
        try:
            import fastparquet  # noqa: F401
            return True
        except ImportError:
            return False


class ParquetWriter:
    def __init__(self, path: str = "./data", flush_every: int = 5_000, prefix: str = "quotes") -> None:
        self.path = path
        self.flush_every = flush_every
        self.prefix = prefix
        self._buf: list[dict] = []
        self._written = 0
        self._shard = 0
        os.makedirs(path, exist_ok=True)

        self.use_parquet = _parquet_available()
        self.ext = "parquet" if self.use_parquet else "csv"
        if not self.use_parquet:
            warnings.warn(
                "pyarrow absent : repli sur CSV. Installe pyarrow pour la "
                "compression et le typage (pip install pyarrow).",
                RuntimeWarning,
                stacklevel=2,
            )

        self.stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.session = os.path.join(path, f"{prefix}_{self.stamp}")

    @property
    def filepath(self) -> str:
        """Motif glob de la session, a passer a l'analyseur."""
        return f"{self.session}_*.{self.ext}"

    def add(self, q: Quote) -> None:
        self._buf.append(q.as_row())
        if len(self._buf) >= self.flush_every:
            self.flush()

    def flush(self) -> None:
        if not self._buf:
            return
        df = pd.DataFrame(self._buf)
        target = f"{self.session}_{self._shard:04d}.{self.ext}"
        if self.use_parquet:
            df.to_parquet(target, index=False)
        else:
            df.to_csv(target, index=False)
        self._written += len(self._buf)
        self._shard += 1
        self._buf.clear()

    def close(self) -> dict:
        self.flush()
        return {
            "motif": self.filepath,
            "fragments": self._shard,
            "lignes": self._written,
            "format": self.ext,
        }
