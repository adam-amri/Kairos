#!/usr/bin/env python3
"""Diagnostic de l'installation — a lancer quand quelque chose ne marche pas.

    python scripts/doctor.py

Verifie, dans l'ordre ou les problemes surviennent reellement : la version de
Python, l'environnement virtuel, le dossier courant, le depot git, les fichiers
attendus, les dependances.
"""
from __future__ import annotations
import os
import shutil
import subprocess
import sys
from pathlib import Path

OK, KO, WARN = "  [OK]  ", "  [KO]  ", "  [!]   "
problemes: list[str] = []


def verifier(nom: str, ok: bool, detail: str = "", correction: str = "") -> None:
    print(f"{OK if ok else KO}{nom}" + (f" — {detail}" if detail else ""))
    if not ok and correction:
        problemes.append(f"{nom}\n     -> {correction}")


def main() -> None:
    print("=" * 66)
    print("DIAGNOSTIC KAIROS")
    print("=" * 66)

    # 1. Version de Python
    v = sys.version_info
    verifier(
        f"Python {v.major}.{v.minor}.{v.micro}",
        v >= (3, 10),
        "3.10 minimum requis",
        "deactivate && rm -rf .venv && $(brew --prefix)/bin/python3.12 -m venv .venv "
        "&& source .venv/bin/activate",
    )

    # 2. Environnement virtuel
    dans_venv = sys.prefix != sys.base_prefix
    verifier("Environnement virtuel actif", dans_venv,
             sys.prefix if dans_venv else "Python systeme",
             "source .venv/bin/activate")

    # 3. Dossier courant
    cwd = Path.cwd()
    racine = cwd / "kairos" / "__init__.py"
    sous_dossier = cwd / "kairos" / "kairos" / "__init__.py"
    if racine.exists():
        verifier("Dossier de travail", True, str(cwd))
    elif sous_dossier.exists():
        verifier("Dossier de travail", False,
                 "le projet est un niveau plus bas",
                 f"cd {cwd / 'kairos'}")
    else:
        verifier("Dossier de travail", False,
                 "aucun module kairos trouve ici",
                 "place-toi dans le dossier contenant README.md et requirements.txt")

    # 4. Depot git
    git_dispo = shutil.which("git") is not None
    verifier("git installe", git_dispo, correction="brew install git")
    if git_dispo:
        depot = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"],
                               capture_output=True, text=True).returncode == 0
        verifier("Depot git initialise", depot,
                 correction="git init   (pre-commit l'exige)")

    # 5. Fichiers attendus
    for f in ("requirements.txt", "config.yaml", ".gitignore", ".env.example"):
        verifier(f"Fichier {f}", Path(f).exists(),
                 correction="fichier manquant : verifie que le dossier est complet")

    for d in ("kairos", "tests", "scripts"):
        verifier(f"Dossier {d}/", Path(d).is_dir())

    # 6. Dependances
    for mod, paquet in (("pandas", "pandas"), ("numpy", "numpy"),
                        ("yaml", "PyYAML"), ("pytest", "pytest")):
        try:
            __import__(mod)
            verifier(f"Module {paquet}", True)
        except ImportError:
            verifier(f"Module {paquet}", False,
                     correction=f"pip install {paquet}")

    # 7. Le projet s'importe-t-il ?
    sys.path.insert(0, str(Path.cwd()))
    try:
        import kairos  # noqa: F401
        from kairos.backtest import BacktestEngine  # noqa: F401
        verifier("Import du projet", True)
    except Exception as e:
        verifier("Import du projet", False, f"{type(e).__name__}: {e}")

    print()
    print("=" * 66)
    if problemes:
        print(f"{len(problemes)} probleme(s) a corriger, dans cet ordre :\n")
        for i, p in enumerate(problemes, 1):
            print(f"  {i}. {p}")
        sys.exit(1)
    print("Tout est en place. Lance :  python -m pytest tests/ -v")


if __name__ == "__main__":
    main()
