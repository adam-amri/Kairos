"""Le pont ne doit JAMAIS pouvoir passer un ordre.

Ce n'est pas une politique desactivable par une option : on verifie que la
CAPACITE est absente. Un garde-fou contournable n'en est pas un.

METHODE : on inspecte l'ARBRE SYNTAXIQUE, pas le texte.
    Une premiere version cherchait les mots interdits dans le fichier brut. Elle
    echouait sur la docstring du pont, qui cite ces mots pour expliquer qu'ils
    sont absents — une mention en prose n'est pourtant pas une capacite.
    Chercher dans le texte confond ce que le code FAIT avec ce qu'il DIT.
"""
import ast
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

CHEMIN = Path(__file__).resolve().parents[1] / "bridge" / "live_bridge.py"
SOURCE = CHEMIN.read_text()
ARBRE = ast.parse(SOURCE)

INTERDITS = {"placeOrder", "place_order", "cancelOrder", "reqExecutions",
             "MarketOrder", "LimitOrder", "StopOrder", "exerciseOptions",
             "reqGlobalCancel"}


def identifiants_du_code() -> set[str]:
    """Tous les noms reellement references. Ni docstrings, ni commentaires."""
    noms: set[str] = set()
    for n in ast.walk(ARBRE):
        if isinstance(n, ast.Name):
            noms.add(n.id)
        elif isinstance(n, ast.Attribute):
            noms.add(n.attr)
        elif isinstance(n, ast.alias):
            noms.add(n.name.split(".")[-1])
            if n.asname:
                noms.add(n.asname)
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            noms.add(n.name)
    return noms


class TestLectureSeule:
    def test_aucune_capacite_de_passage_d_ordre(self):
        presents = INTERDITS & identifiants_du_code()
        assert not presents, f"capacite de trading referencee : {sorted(presents)}"

    def test_la_prose_peut_citer_les_mots_sans_faire_echouer(self):
        """Non-regression sur le test lui-meme : la docstring cite bien
        'placeOrder' pour expliquer son absence, et cela doit rester valide."""
        assert "placeOrder" in SOURCE            # present en prose
        assert "placeOrder" not in identifiants_du_code()   # absent du code

    def test_la_connexion_est_declaree_readonly(self):
        for n in ast.walk(ARBRE):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
               and n.func.attr == "connect":
                assert any(kw.arg == "readonly" and kw.value.value is True
                           for kw in n.keywords), "connect() sans readonly=True"

    def test_le_contrat_annonce_la_lecture_seule(self):
        assert '"lecture_seule": True' in SOURCE

    def test_avertissement_sur_les_ports_reels(self):
        assert "7496" in SOURCE and "4001" in SOURCE

    def test_ecriture_atomique(self):
        assert "replace" in identifiants_du_code()

    def test_les_cotations_aberrantes_sont_rejetees(self):
        import re
        assert re.search(r"if not \(bid > 0 and ask > 0 and ask >= bid\)", SOURCE)


class TestEvenementsIbAsync:
    """Non-regression sur un bug reel, trouve en production.

    Le pont s'abonnait a `ib.tickByTickBidAskEvent`, qui N'EXISTE PAS dans
    ib_async. Consequence : AttributeError levee dans le fil de collecte,
    donc invisible dans le terminal principal. La connexion reussissait, le
    compte s'affichait, le mode aussi — et zero paire n'arrivait jamais.

    ib_async publie TOUTES les mises a jour, tick-by-tick comprises, par
    `pendingTickersEvent` ; chaque Ticker porte alors une liste `tickByTicks`.
    """

    # Noms qui ressemblent a des evenements ib_async mais n'en sont pas.
    INEXISTANTS = ["tickByTickBidAskEvent", "tickByTickAllLastEvent",
                   "tickByTickMidPointEvent", "marketDataEvent"]

    def test_aucun_evenement_inexistant(self):
        noms = identifiants_du_code()
        fautifs = [n for n in self.INEXISTANTS if n in noms]
        assert not fautifs, f"evenement ib_async inexistant : {fautifs}"

    def test_le_bon_evenement_est_utilise(self):
        assert "pendingTickersEvent" in identifiants_du_code()

    def test_un_filet_de_securite_existe(self):
        """Si le tick-by-tick n'est pas disponible, le haut de carnet agrege
        doit prendre le relais — des prix degrades valent mieux que rien."""
        noms = identifiants_du_code()
        assert "reqTickByTickData" in noms
        assert "reqMktData" in noms

    def test_les_prix_non_finis_sont_filtres(self):
        """ib_async renvoie NaN pour un prix non encore recu. Le laisser
        passer polluerait le detecteur avec des cotations invalides."""
        assert "isnan" in SOURCE
