#!/usr/bin/env python3
"""KAIROS — application de bureau.

Un seul processus, une seule fenetre, un double-clic.

CE QUE CE FICHIER REMPLACE
    Avant : un terminal pour le pont, un second pour `python -m http.server`,
    puis un navigateur a ouvrir a la main. Trois choses a lancer dans le bon
    ordre, et un oubli laissait l'interface vide sans dire pourquoi.

    Maintenant : le pont tourne dans un fil, l'interface est servie en local,
    et la fenetre native s'ouvre. Rien d'autre a faire.

POURQUOI PAS UN NAVIGATEUR
    Chrome bloque `fetch` sur les fichiers `file://` : ouvrir le HTML par
    double-clic donnait une page morte sans message clair. Le serveur local
    integre supprime le probleme.

POURQUOI PAS DU C++ POUR LA FENETRE
    Une interface Qt en C++ representerait des semaines de travail pour afficher
    exactement le meme tableau. Le C++ du projet est la ou il rapporte — le
    moteur de rejeu, mesure 56x plus rapide. Ici, le goulot est l'oeil humain.

Usage :
    python app.py                                   # demo, sans broker
    python app.py --source ibkr --port 7497 --notionnel 1000
"""
from __future__ import annotations

import argparse
import http.server
import os
import socket
import socketserver
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

RACINE = Path(__file__).resolve().parent
DASHBOARD = RACINE / "dashboard"


def port_libre(depart: int = 8765) -> int:
    """Premier port disponible a partir de `depart`.

    Un port code en dur echoue silencieusement si une session precedente ne
    s'est pas fermee proprement — et l'utilisateur voit une fenetre vide sans
    savoir pourquoi.
    """
    for p in range(depart, depart + 60):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", p)) != 0:
                return p
    raise RuntimeError("aucun port libre entre 8765 et 8825")


class Serveur(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def servir(dossier: Path, port: int) -> None:
    class H(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(dossier), **k)

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            super().end_headers()

        def log_message(self, *a):        # pas de bruit dans la console
            pass

    Serveur(("127.0.0.1", port), H).serve_forever()


def lancer_pont(args) -> threading.Thread | None:
    """Le pont dans un sous-processus : s'il tombe, l'interface survit et
    l'affiche, au lieu d'emporter la fenetre avec lui."""
    cmd = [sys.executable, str(RACINE / "bridge" / "live_bridge.py"),
           "--source", args.source,
           "--out", str(DASHBOARD / "kairos-live.json"),
           "--notionnel", str(args.notionnel),
           "--intervalle", str(args.intervalle)]
    if args.source == "ibkr":
        cmd += ["--host", args.host, "--port", str(args.port),
                "--client-id", str(args.client_id)]
    if args.journal:
        cmd += ["--journal", str(RACINE / args.journal)]
    if args.store:
        cmd += ["--store", str(RACINE / args.store)]

    print("[app] pont :", " ".join(cmd[1:]), flush=True)
    proc = subprocess.Popen(cmd, cwd=RACINE)

    def surveiller():
        code = proc.wait()
        if code not in (0, -2, -15):
            print(f"[app] le pont s'est arrete (code {code})", flush=True)

    t = threading.Thread(target=surveiller, daemon=True)
    t.start()
    return proc


def ouvrir_fenetre(url: str, titre: str = "Kairos") -> bool:
    """Fenetre native si pywebview est present, sinon Chrome en mode app."""
    try:
        import webview
        webview.create_window(titre, url, width=1600, height=980,
                              min_size=(1100, 700))
        webview.start()
        return True
    except ImportError:
        pass

    # Chrome en mode application : pas de barre d'adresse, pas d'onglets.
    for chemin in ("/Applications/Google Chrome.app",
                   "/Applications/Microsoft Edge.app",
                   "/Applications/Brave Browser.app"):
        if Path(chemin).exists():
            subprocess.Popen(["open", "-na", chemin, "--args", f"--app={url}"])
            return False
    webbrowser.open(url)
    return False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["ibkr", "demo"], default="demo")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=7497,
                    help="7497 TWS simulation · 4002 Gateway simulation")
    ap.add_argument("--client-id", type=int, default=21)
    ap.add_argument("--notionnel", type=float, default=1000)
    ap.add_argument("--intervalle", type=float, default=0.5)
    ap.add_argument("--journal", default="journal")
    ap.add_argument("--store", default="")
    ap.add_argument("--sans-pont", action="store_true",
                    help="l'interface seule, si le pont tourne deja ailleurs")
    args = ap.parse_args()

    if not (DASHBOARD / "kairos.html").exists():
        sys.exit(f"kairos.html introuvable dans {DASHBOARD}")

    proc = None if args.sans_pont else lancer_pont(args)

    web = port_libre(8000)
    threading.Thread(target=servir, args=(DASHBOARD, web), daemon=True).start()
    url = f"http://127.0.0.1:{web}/kairos.html"
    print(f"[app] interface : {url}", flush=True)

    time.sleep(0.6)     # laisse le serveur se lier avant d'ouvrir la fenetre

    try:
        natif = ouvrir_fenetre(url)
        if not natif:
            print("[app] fenetre externe ouverte — Ctrl+C ici pour tout arreter",
                  flush=True)
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        print("[app] arret propre", flush=True)


if __name__ == "__main__":
    main()
