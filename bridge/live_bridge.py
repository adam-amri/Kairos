#!/usr/bin/env python3
"""Pont marche -> kairos-live.json. LECTURE SEULE, sans exception.

GARANTIE STRUCTURELLE
    Ce fichier ne contient AUCUN code de passage d'ordre. Pas de placeOrder,
    pas de Order, pas d'import du module de trading. Ce n'est pas une politique
    qu'on pourrait desactiver par une option : la capacite n'existe pas.
    Le test tests/test_bridge.py verifie cette absence a chaque execution de CI.

    C'est le niveau N0 du gradient d'autonomie : observer, journaliser, ne rien
    faire. On n'en sort que par un historique mesure.

POURQUOI LE COMPTE SIMULATION D'ABORD, ET CE QU'IL PROUVE VRAIMENT
    Le paper trading d'IBKR remplit les ordres de facon optimiste : il ne
    modelise ni la file d'attente ni la selection adverse. Un resultat brillant
    en simulation n'est donc PAS une preuve d'avantage — c'est meme un signal
    d'erreur sur une strategie de capture de spread.

    Ce que la simulation valide reellement : la PLOMBERIE. Reconnexion, doublons
    d'ordres, desynchronisation d'etat, conventions de cotation, fraicheur des
    donnees. C'est deja beaucoup, et c'est ce qui casse en premier.

    Le modele predit ZERO opportunite nette a taille retail. Si le pont affiche
    zero, ce n'est pas une panne : c'est le verdict, confirme sur tes donnees.

Usage :
    python bridge/live_bridge.py --source ibkr --port 7497        # TWS paper
    python bridge/live_bridge.py --source ibkr --port 4002        # Gateway paper
    python bridge/live_bridge.py --serve 8765                     # + HTTP/CORS
"""
from __future__ import annotations

import argparse
import json
import math
import os
import signal
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kairos.arb import CostModel, Detector, DeviationBasis, PairQuote
from kairos.journal import DailyJournal, OrderRecord

# Les 8 majeures. Un graphe plus large multiplie les cycles sans ajouter de
# liquidite : au-dela, on paie des lignes de donnees pour du bruit.
PAIRES = [("EUR","USD"), ("USD","JPY"), ("GBP","USD"), ("EUR","GBP"),
          ("USD","CHF"), ("AUD","USD"), ("EUR","JPY"), ("GBP","JPY")]

_stop = threading.Event()


class Etat:
    """Dernieres cotations connues, protegees par un verrou."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.quotes: dict[str, dict] = {}
        self.n_maj = 0
        self.demarre = time.time()
        # Compteurs CUMULATIFS depuis le demarrage.
        # `boucles_examinees` renvoyait le nombre de boucles du balayage EN COURS
        # — une constante, 14. L'interface affichait donc un compteur fige, et le
        # taux de retenue se calculait sur un denominateur de 14 au lieu du
        # travail reellement accompli. Le taux etait faux de plusieurs ordres de
        # grandeur.
        self.balayages = 0
        self.boucles_cumul = 0
        self.opportunites_cumul = 0
        # Diagnostic expose a l'interface : elle affiche l'etat de chaque
        # maillon plutot que de dire « ca ne marche pas ».
        self.diag: dict = {
            "connecte": False, "hote": "", "port": 0, "client_id": 0,
            "compte": "", "mode": "", "erreur": "", "latences_us": [],
        }

    def maj(self, base: str, quote: str, bid: float, ask: float,
            ts_venue_ms: int | None = None) -> None:
        if not (bid > 0 and ask > 0 and ask >= bid):
            return                      # cotation aberrante : on ignore, jamais on ne trade dessus
        with self.lock:
            self.quotes[f"{base}/{quote}"] = {
                "base": base, "quote": quote, "bid": bid, "ask": ask,
                "ts": ts_venue_ms or int(time.time() * 1000),
                "ts_recu": int(time.time() * 1000),
            }
            self.n_maj += 1

    def instantane(self) -> list[dict]:
        with self.lock:
            return list(self.quotes.values())


def construire_json(etat: Etat, cost: CostModel, notional: float,
                    source: str) -> dict:
    """Le contrat de sortie. Un seul chemin de calcul : c'est CE detecteur qui
    tourne, le meme qu'en backtest."""
    quotes = etat.instantane()
    d = Detector()
    for q in quotes:
        try:
            d.add_pair(PairQuote(q["base"], q["quote"], q["bid"], q["ask"]))
        except ValueError:
            continue

    # Base Executable : la deviation est calculee sur bid/ask, le spread y est
    # deja. Passer Mid ici compterait le spread deux fois.
    toutes = d.scan(cost, notional, 3, 5, only_profitable=False,
                    basis=DeviationBasis.EXECUTABLE)
    nettes = [o for o in toutes if o.profitable]

    with etat.lock:
        etat.balayages += 1
        etat.boucles_cumul += len(toutes)
        etat.opportunites_cumul += len(nettes)
        balayages = etat.balayages
        boucles_cumul = etat.boucles_cumul
        opportunites_cumul = etat.opportunites_cumul

    maintenant = int(time.time() * 1000)
    plus_vieille = min((q["ts_recu"] for q in quotes), default=maintenant)

    lat = sorted(etat.diag["latences_us"])
    lat_p50 = lat[len(lat) // 2] if lat else 0.0

    return {
        "version": 1,
        "genere": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "lecture_seule": True,
        "quotes": quotes,
        "n_paires": len(quotes),
        "fraicheur_ms": maintenant - plus_vieille,
        # Cumul depuis le demarrage : c'est le travail reellement accompli.
        "boucles_examinees": boucles_cumul,
        # Nombre de boucles du graphe a un instant donne — une constante.
        "boucles_par_balayage": len(toutes),
        "balayages": balayages,
        "opportunites_cumul": opportunites_cumul,
        "opportunites": [
            {
                "parcours": o.path,
                "jambes": o.n_legs,
                "brut_bps": round(o.gross_bps, 4),
                "cout_bps": round(o.cost_bps, 4),
                "net_bps": round(o.net_bps, 4),
                "net_eur": round(o.net_bps / 10_000 * notional, 2),
            } for o in nettes[:20]
        ],
        "meilleure_boucle": (
            {
                "parcours": toutes[0].path,
                "net_bps": round(toutes[0].net_bps, 4),
            } if toutes else None
        ),
        "notionnel": notional,
        "latence_p50_us": round(lat_p50, 1),
        # Diagnostic maillon par maillon, pour l'ecran de lancement.
        "connexion": {
            "connecte": etat.diag["connecte"],
            "hote": etat.diag["hote"],
            "port": etat.diag["port"],
            "client_id": etat.diag["client_id"],
            "compte": etat.diag["compte"],
            "mode": etat.diag["mode"],
            "erreur": etat.diag["erreur"],
            "compte_simule": str(etat.diag["compte"]).upper().startswith(("DU", "DF")),
        },
        "n_maj": etat.n_maj,
        "uptime_s": round(time.time() - etat.demarre, 1),
    }


def ecrire_atomique(chemin: Path, data: dict) -> None:
    """Ecrire puis renommer. Sans cela le lecteur peut tomber sur un fichier
    a moitie ecrit et conclure a une panne alors que tout va bien."""
    tmp = chemin.with_suffix(chemin.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False))
    os.replace(tmp, chemin)


# ---------------------------------------------------------------- sources
def source_ibkr(etat: Etat, host: str, port: int, client_id: int) -> None:
    """TWS ou IB Gateway. Aucun ordre n'est jamais transmis.

    Ports : 7497 TWS paper · 7496 TWS live · 4002 Gateway paper · 4001 live.
    """
    from ib_async import IB, Forex

    ib = IB()
    etat.diag.update(hote=host, port=port, client_id=client_id,
                     mode="SIMULATION" if port in (7497, 4002) else "REEL")
    try:
        ib.connect(host, port, clientId=client_id, readonly=True)  # readonly explicite
    except Exception as e:
        etat.diag.update(connecte=False, erreur=f"{type(e).__name__}: {e}")
        raise
    comptes = ib.managedAccounts()
    etat.diag.update(connecte=True, compte=comptes[0] if comptes else "", erreur="")

    contrats = {}
    for base, quote in PAIRES:
        c = Forex(f"{base}{quote}")
        ib.qualifyContracts(c)
        contrats[c.conId] = (base, quote)
        # Tick-by-tick : le seul flux dont l'horodatage soit exploitable.
        ib.reqTickByTickData(c, "BidAsk", 0, False)
        # Filet de securite : le haut de carnet agrege (~250 ms). Si le
        # tick-by-tick n'est pas disponible sur ce compte, on a quand meme
        # des prix — degrades, mais des prix.
        ib.reqMktData(c, "", False, False)

    def _fini(x) -> bool:
        return x is not None and isinstance(x, (int, float)) and not math.isnan(x) and x > 0

    def on_pending(tickers) -> None:
        """ib_async ne publie PAS d'evenement tickByTickBidAskEvent.

        Les mises a jour, tick-by-tick comprises, arrivent toutes par
        pendingTickersEvent ; chaque Ticker porte alors une liste tickByTicks.
        Utiliser un nom d'evenement inexistant levait une AttributeError dans
        le fil de collecte : la connexion reussissait, le compte s'affichait,
        et zero paire n'arrivait jamais.
        """
        recu = time.time()
        for t in tickers:
            bq = contrats.get(t.contract.conId)
            if bq is None:
                continue

            bid = ask = None
            ts_ms = None

            # 1. Tick-by-tick, s'il y en a — horodatage du venue disponible
            for tb in (getattr(t, "tickByTicks", None) or ()):
                bp, ap = getattr(tb, "bidPrice", None), getattr(tb, "askPrice", None)
                if _fini(bp) and _fini(ap):
                    bid, ask = float(bp), float(ap)
                    tt = getattr(tb, "time", None)
                    if tt is not None:
                        ts_ms = int(tt.timestamp() * 1000)
                        etat.diag["latences_us"].append((recu - tt.timestamp()) * 1e6)

            # 2. Sinon le haut de carnet agrege
            if bid is None and _fini(t.bid) and _fini(t.ask):
                bid, ask = float(t.bid), float(t.ask)
                if getattr(t, "time", None) is not None:
                    ts_ms = int(t.time.timestamp() * 1000)

            if bid is None or ask is None:
                continue

            d = etat.diag["latences_us"]
            if len(d) > 400:
                del d[:200]
            etat.maj(bq[0], bq[1], bid, ask, ts_ms)

    ib.pendingTickersEvent += on_pending

    print(f"[pont] IBKR connecte sur {host}:{port} "
          f"({'PAPER' if port in (7497, 4002) else 'LIVE — attention'})", flush=True)
    try:
        while not _stop.is_set():
            ib.sleep(0.05)
    finally:
        ib.disconnect()


def source_demo(etat: Etat) -> None:
    """Marche synthetique — permet de tout valider sans compte broker."""
    import random
    rng = random.Random(7)
    niveaux = {("EUR","USD"):1.0800, ("USD","JPY"):157.00, ("GBP","USD"):1.2715,
               ("EUR","GBP"):0.8493, ("USD","CHF"):0.8812, ("AUD","USD"):0.6641,
               ("EUR","JPY"):169.56, ("GBP","JPY"):199.64}
    etat.diag.update(connecte=True, hote="local", port=0, client_id=0,
                     compte="—", mode="DEMO")
    print("[pont] source DEMO — donnees simulees, aucun marche connecte", flush=True)
    while not _stop.is_set():
        for (b, q), m in list(niveaux.items()):
            m *= 1 + rng.gauss(0, 0.00002)
            niveaux[(b, q)] = m
            h = m * 0.3 / 2 / 10_000
            etat.maj(b, q, m - h, m + h)
        time.sleep(0.25)


# ---------------------------------------------------------------- serveur
def serveur_http(chemin: Path, port: int) -> None:
    """Sert le fichier avec CORS, pour que le dashboard du PC lise celui du Pi."""
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            if not self.path.startswith("/kairos-live.json"):
                self.send_error(404); return
            try:
                corps = chemin.read_bytes()
            except OSError:
                self.send_error(503); return
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(corps)))
            self.end_headers()
            self.wfile.write(corps)

        def log_message(self, *a):        # pas de bruit dans le journal
            pass

    srv = HTTPServer(("0.0.0.0", port), H)
    print(f"[pont] HTTP sur le port {port} — http://<ip>:{port}/kairos-live.json", flush=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()


# ---------------------------------------------------------------- principal
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["ibkr", "demo"], default="demo")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=7497,
                    help="7497 TWS paper (defaut) · 4002 Gateway paper")
    ap.add_argument("--client-id", type=int, default=21)
    ap.add_argument("--out", default="dashboard/kairos-live.json")
    ap.add_argument("--serve", type=int, default=0, help="port HTTP, 0 = desactive")
    ap.add_argument("--intervalle", type=float, default=0.5)
    ap.add_argument("--notionnel", type=float, default=25_000)
    ap.add_argument("--store", default="", help="dossier de persistance des quotes")
    ap.add_argument("--journal", default="journal",
                    help="dossier du journal quotidien (CSV). Vide = desactive")
    args = ap.parse_args()

    if args.source == "ibkr" and args.port in (7496, 4001):
        print("[pont] ATTENTION : port de compte REEL. Le pont reste en lecture "
              "seule, mais utilise 7497 ou 4002 tant que la Phase 1 n'est pas close.",
              flush=True)

    chemin = Path(args.out)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    etat = Etat()
    cost = CostModel(0.20, 2.00, 0.0)

    signal.signal(signal.SIGINT,  lambda *_: _stop.set())
    signal.signal(signal.SIGTERM, lambda *_: _stop.set())

    cible = source_ibkr if args.source == "ibkr" else source_demo
    kw = dict(host=args.host, port=args.port, client_id=args.client_id) \
         if args.source == "ibkr" else {}
    threading.Thread(target=cible, args=(etat,), kwargs=kw, daemon=True).start()

    if args.serve:
        serveur_http(chemin, args.serve)

    # Le journal bascule tout seul a minuit local et rouvre un fichier par jour.
    # Il survit aux redemarrages : le cumul est relu depuis le resume existant.
    journal = DailyJournal(dossier=args.journal) if args.journal else None
    if journal:
        print(f"[pont] journal quotidien dans {args.journal}/ "
              f"(cumul repris : {journal.net_cumule:.2f})", flush=True)

    writer = None
    if args.store:
        from kairos.store import ParquetWriter
        writer = ParquetWriter(path=args.store, flush_every=2000, prefix="live")

    print(f"[pont] ecriture de {chemin} toutes les {args.intervalle}s", flush=True)
    dernier_log = 0.0
    while not _stop.is_set():
        data = construire_json(etat, cost, args.notionnel, args.source)
        ecrire_atomique(chemin, data)

        if writer is not None:
            from kairos.events import Quote
            for q in data["quotes"]:
                writer.add(Quote(venue=args.source, symbol=f"{q['base']}/{q['quote']}",
                                 bid=q["bid"], ask=q["ask"], bid_size=0, ask_size=0,
                                 ts_venue_ns=q["ts"] * 1_000_000,
                                 ts_wall_ns=q["ts_recu"] * 1_000_000,
                                 ts_mono_ns=time.perf_counter_ns()))

        if journal is not None:
            ts_ms = int(time.time() * 1000)
            # Le journal recoit le DELTA, pas le cumul : lui aussi additionne.
            journal.observer(ts_ms, data["boucles_par_balayage"])
            for i, o in enumerate(data["opportunites"]):
                journal.enregistrer(OrderRecord(
                    id=f"{ts_ms}-{i}", ts_ms=ts_ms,
                    # Niveau N0 du gradient d'autonomie : on DETECTE, on n'execute pas.
                    statut="detecte",
                    parcours=o["parcours"], brut_bps=o["brut_bps"],
                    cout_bps=o["cout_bps"], net_bps=o["net_bps"],
                    notionnel=args.notionnel,
                    fraicheur_ms=data["fraicheur_ms"], source=args.source,
                ))

        if time.time() - dernier_log > 30:
            print(f"[pont] {data['n_paires']} paires · fraicheur {data['fraicheur_ms']} ms "
                  f"· {data['balayages']:,} balayages · {data['boucles_examinees']:,} boucles "
                  f"· {data['opportunites_cumul']} nette(s) au total", flush=True)
            dernier_log = time.time()
        time.sleep(args.intervalle)

    if journal is not None:
        f = journal.cloturer()
        print(f"[pont] journal cloture : {f}", flush=True)
    if writer is not None:
        print("[pont]", writer.close(), flush=True)
    print("[pont] arret propre", flush=True)


if __name__ == "__main__":
    main()
