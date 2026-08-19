#!/usr/bin/env python3
"""Validation d'une connexion IBKR en compte simulation, etape par etape.

    python scripts/paper_test.py                  # TWS paper, port 7497
    python scripts/paper_test.py --port 4002      # IB Gateway paper
    python scripts/paper_test.py --demo           # sans TWS, valide le script

Chaque etape rend PASS ou ECHEC, et un ECHEC affiche la correction exacte.
Les etapes sont ordonnees comme les problemes surviennent reellement : inutile
de diagnostiquer les cotations si le port n'est meme pas ouvert.

CE QUE CETTE VALIDATION PROUVE — ET CE QU'ELLE NE PROUVE PAS
    Elle valide la PLOMBERIE : connexion, reception, fraicheur, conventions de
    cotation, coherence du graphe. C'est ce qui casse en premier, et c'est
    beaucoup.

    Elle ne prouve RIEN sur la rentabilite. Le paper trading d'IBKR remplit de
    facon optimiste — ni file d'attente, ni selection adverse. Le modele predit
    zero opportunite nette : si l'etape 9 affiche zero, ce n'est pas une panne,
    c'est le verdict confirme sur tes donnees.
"""
from __future__ import annotations

import argparse
import math
import socket
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kairos.arb import CostModel, Detector, DeviationBasis, PairQuote

PAIRES = [("EUR","USD"), ("USD","JPY"), ("GBP","USD"), ("EUR","GBP"),
          ("USD","CHF"), ("AUD","USD"), ("EUR","JPY"), ("GBP","JPY")]

# Plages volontairement LARGES : on cherche une paire inversee ou un mauvais
# contrat, pas a juger le niveau du marche. Une inversion se voit d'un facteur
# 100, pas de quelques pourcents.
PLAGES = {
    "EUR/USD": (0.80, 1.60), "USD/JPY": (80.0, 220.0),
    "GBP/USD": (1.00, 2.00), "EUR/GBP": (0.60, 1.00),
    "USD/CHF": (0.70, 1.30), "AUD/USD": (0.50, 1.00),
    "EUR/JPY": (90.0, 240.0), "GBP/JPY": (110.0, 300.0),
}

PORTS = {7497: ("TWS", "SIMULATION"), 7496: ("TWS", "REEL"),
         4002: ("Gateway", "SIMULATION"), 4001: ("Gateway", "REEL")}

OK, KO, WARN = "  [OK]   ", "  [ECHEC]", "  [!]    "
problemes: list[str] = []
_n = 0


def etape(titre: str) -> None:
    global _n
    _n += 1
    print(f"\n{_n}. {titre}")


def verif(nom: str, ok: bool, detail: str = "", correction: str = "") -> bool:
    print(f"{OK if ok else KO} {nom}" + (f" — {detail}" if detail else ""))
    if not ok and correction:
        problemes.append(f"{nom}\n        -> {correction}")
    return ok


def alerte(nom: str, detail: str = "") -> None:
    print(f"{WARN} {nom}" + (f" — {detail}" if detail else ""))


# ---------------------------------------------------------------- collecte
def collecter_ibkr(host: str, port: int, client_id: int,
                   duree: float) -> tuple[dict, list[float], str]:
    """Retourne (quotes, latences_us, id_de_compte)."""
    from ib_async import IB, Forex

    quotes: dict[str, dict] = {}
    latences: list[float] = []

    ib = IB()
    ib.connect(host, port, clientId=client_id, readonly=True, timeout=15)

    comptes = ib.managedAccounts()
    compte = comptes[0] if comptes else ""

    contrats = {}
    for base, quote in PAIRES:
        c = Forex(f"{base}{quote}")
        ib.qualifyContracts(c)
        contrats[f"{base}/{quote}"] = c.conId
        ib.reqTickByTickData(c, "BidAsk", 0, False)
        ib.reqMktData(c, "", False, False)     # filet de securite
    par_id = {v: k for k, v in contrats.items()}

    def _fini(x):
        return x is not None and isinstance(x, (int, float)) and not math.isnan(x) and x > 0

    def on_pending(tickers):
        # ib_async publie tout par pendingTickersEvent, y compris le tick-by-tick.
        recu = time.time()
        for t in tickers:
            sym = par_id.get(t.contract.conId)
            if sym is None:
                continue
            for tb in (getattr(t, "tickByTicks", None) or ()):
                if _fini(getattr(tb, "bidPrice", None)) and _fini(getattr(tb, "askPrice", None)):
                    quotes[sym] = {"bid": float(tb.bidPrice), "ask": float(tb.askPrice)}
                    if getattr(tb, "time", None) is not None:
                        latences.append((recu - tb.time.timestamp()) * 1e6)
            if sym not in quotes and _fini(t.bid) and _fini(t.ask):
                quotes[sym] = {"bid": float(t.bid), "ask": float(t.ask)}

    ib.pendingTickersEvent += on_pending
    fin = time.time() + duree
    while time.time() < fin:
        ib.sleep(0.05)
    ib.disconnect()
    return quotes, latences, compte


def collecter_demo(duree: float) -> tuple[dict, list[float], str]:
    import random
    rng = random.Random(7)
    niveaux = {"EUR/USD":1.0800, "USD/JPY":157.00, "GBP/USD":1.2715,
               "EUR/GBP":0.8493, "USD/CHF":0.8812, "AUD/USD":0.6641,
               "EUR/JPY":169.56, "GBP/JPY":199.64}
    quotes = {}
    for s, m in niveaux.items():
        h = m * 0.3 / 2 / 10_000
        quotes[s] = {"bid": m - h, "ask": m + h}
    latences = [rng.uniform(400, 2500) for _ in range(500)]
    time.sleep(min(duree, 1.0))
    return quotes, latences, "DU0000000"


# ---------------------------------------------------------------- principal
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=7497)
    ap.add_argument("--client-id", type=int, default=99)
    ap.add_argument("--duree", type=float, default=20.0,
                    help="secondes d'ecoute du marche")
    ap.add_argument("--demo", action="store_true",
                    help="sans TWS — valide le script lui-meme")
    args = ap.parse_args()

    print("=" * 68)
    print("VALIDATION IBKR — COMPTE SIMULATION")
    print("=" * 68)

    # --- 1
    etape("Environnement Python")
    v = sys.version_info
    verif(f"Python {v.major}.{v.minor}.{v.micro}", v >= (3, 10), "3.10 minimum",
          "deactivate && rm -rf .venv && $(brew --prefix)/bin/python3.12 -m venv .venv"
          " && source .venv/bin/activate && pip install -r requirements.txt")
    verif("Environnement virtuel actif", sys.prefix != sys.base_prefix,
          correction="source .venv/bin/activate")

    if not args.demo:
        try:
            import ib_async  # noqa: F401
            verif("Module ib_async", True)
        except ImportError:
            verif("Module ib_async", False, correction="pip install ib_async")

    # --- 2
    etape("Choix du port")
    logiciel, nature = PORTS.get(args.port, ("inconnu", "inconnu"))
    verif(f"Port {args.port} reconnu", args.port in PORTS,
          f"{logiciel}, compte {nature}",
          "utilise 7497 (TWS paper) ou 4002 (Gateway paper)")
    if nature == "REEL":
        alerte("PORT DE COMPTE REEL", "bascule sur 7497 ou 4002 tant que "
                                      "la Phase 1 n'est pas close")

    # --- 3
    etape("Le port repond-il ?")
    if args.demo:
        alerte("ignore en mode demo")
        joignable = True
    else:
        s = socket.socket(); s.settimeout(3)
        joignable = s.connect_ex((args.host, args.port)) == 0
        s.close()
        verif(f"{args.host}:{args.port} accessible", joignable,
              correction=(f"lance {logiciel}, puis File > Global Configuration > "
                          "API > Settings : coche 'Enable ActiveX and Socket Clients', "
                          f"met Socket port a {args.port}, et coche 'Read-Only API'"))
    if not joignable:
        rendu()
        return

    # --- 4
    etape("Connexion et reception des cotations")
    print(f"     ecoute du marche pendant {args.duree:.0f} s...")
    try:
        if args.demo:
            quotes, latences, compte = collecter_demo(args.duree)
        else:
            quotes, latences, compte = collecter_ibkr(
                args.host, args.port, args.client_id, args.duree)
    except Exception as e:
        verif("Connexion API", False, f"{type(e).__name__}: {e}",
              "verifie que l'API est activee et que 127.0.0.1 est dans Trusted IPs")
        rendu()
        return
    verif("Connexion API etablie", True)

    # --- 5
    etape("Le compte est-il bien en simulation ?")
    # Les comptes paper individuels commencent par DU, les reels par U.
    est_paper = compte.upper().startswith(("DU", "DF"))
    verif(f"Compte {compte or '(inconnu)'}", est_paper,
          "prefixe DU/DF = simulation" if est_paper else "ce compte semble REEL",
          "reconnecte-toi a TWS avec l'identifiant du compte paper")

    # --- 6
    etape("Reception des 8 paires")
    manquantes = [f"{b}/{q}" for b, q in PAIRES if f"{b}/{q}" not in quotes]
    verif(f"{len(quotes)}/8 paires recues", not manquantes,
          f"manquantes : {', '.join(manquantes)}" if manquantes else "",
          "souscris les donnees FX dans le portail web, puis 'Partager avec le "
          "compte paper'. Sans souscription, seules des donnees differees arrivent")

    # --- 7
    etape("Fraicheur des donnees")
    if latences:
        tri = sorted(latences)
        p50 = tri[len(tri)//2] / 1000
        p95 = tri[int(len(tri)*0.95)] / 1000
        print(f"     latence venue -> local : p50 {p50:.1f} ms · p95 {p95:.1f} ms "
              f"· {len(latences)} echantillons")
        verif("Latence plausible", 0 < p50 < 2000,
              correction="une latence negative signale des horloges desynchronisees : "
                         "verifie NTP (sudo sntp -sS time.apple.com sur macOS)")
        if p95 > 1000:
            alerte("p95 au-dela de 1 s", "flux probablement etrangle par le pacing IBKR")
    else:
        alerte("aucune mesure de latence", "le venue n'a pas horodate les ticks")

    # --- 8
    etape("Conventions de cotation")
    hors_plage = []
    for sym, q in quotes.items():
        lo, hi = PLAGES.get(sym, (0, 1e9))
        m = (q["bid"] + q["ask"]) / 2
        if not (lo <= m <= hi):
            hors_plage.append(f"{sym}={m:.4f} hors [{lo}, {hi}]")
    verif("Tous les niveaux sont plausibles", not hors_plage,
          " · ".join(hors_plage),
          "un niveau aberrant signale une paire inversee ou un mauvais contrat. "
          "Une paire BASE/QUOTE se lit 'QUOTE par BASE'")

    # --- 9
    etape("Coherence triangulaire")
    # EUR/JPY doit valoir EUR/USD x USD/JPY. Un ecart de plusieurs milliers de
    # bps est la signature du bug de convention (+6 167 bps mesures).
    if all(s in quotes for s in ("EUR/USD", "USD/JPY", "EUR/JPY")):
        eu = (quotes["EUR/USD"]["bid"] + quotes["EUR/USD"]["ask"]) / 2
        uj = (quotes["USD/JPY"]["bid"] + quotes["USD/JPY"]["ask"]) / 2
        ej = (quotes["EUR/JPY"]["bid"] + quotes["EUR/JPY"]["ask"]) / 2
        synth = eu * uj
        ecart_bps = (ej / synth - 1) * 10_000
        print(f"     EUR/JPY cote {ej:.4f} · synthetique {synth:.4f} "
              f"· ecart {ecart_bps:+.2f} bps")
        verif("Croisee coherente", abs(ecart_bps) < 50,
              correction="un ecart de plusieurs milliers de bps est le bug de "
                         "convention : une jambe multiplie au lieu de diviser")
    else:
        alerte("triangle incomplet", "impossible de verifier la coherence")

    # --- 10
    etape("Detecteur d'arbitrage")
    d = Detector()
    for sym, q in quotes.items():
        b, qt = sym.split("/")
        try:
            d.add_pair(PairQuote(b, qt, q["bid"], q["ask"]))
        except ValueError:
            continue
    cost = CostModel(0.20, 2.00, 0.0)
    for notional in (10_000, 100_000, 1_000_000):
        toutes = d.scan(cost, notional, 3, 5, False, DeviationBasis.EXECUTABLE)
        nettes = [o for o in toutes if o.profitable]
        best = toutes[0].net_bps if toutes else float("nan")
        print(f"     ticket {notional:>9,} $ : {len(toutes):>3} boucles · "
              f"{len(nettes)} nette(s) · meilleure {best:+.3f} bps")
    verif("Le graphe produit des boucles", len(toutes) > 0,
          correction="graphe deconnecte : il manque une paire pivot")

    rendu()


def rendu() -> None:
    print("\n" + "=" * 68)
    if problemes:
        print(f"{len(problemes)} probleme(s) a corriger, dans cet ordre :\n")
        for i, p in enumerate(problemes, 1):
            print(f"  {i}. {p}")
        sys.exit(1)
    print("PLOMBERIE VALIDEE.")
    print()
    print("Rappel : zero opportunite nette est le resultat ATTENDU. Le modele")
    print("predit qu'il n'y a rien a capturer a taille retail — cette validation")
    print("confirme que le systeme le mesure correctement, pas qu'il echoue.")
    print()
    print("Etape suivante : lancer la collecte de cinq jours.")
    print("  python bridge/live_bridge.py --source ibkr --port 7497 \\")
    print("         --store data/phase1 --out dashboard/kairos-live.json")


if __name__ == "__main__":
    main()
