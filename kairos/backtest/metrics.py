"""Metriques de performance, avec correction du multiple testing.

LE PROBLEME QUE CE MODULE RESOUT
    Teste deux cents configurations, garde la meilleure, et son Sharpe sera
    flatteur meme si aucune n'a le moindre pouvoir predictif : c'est le maximum
    d'un echantillon de bruit. Rapporter ce Sharpe brut, c'est rapporter le
    resultat d'une selection, pas d'une decouverte.

    Le Deflated Sharpe Ratio (Bailey & Lopez de Prado, 2014) corrige cela. Il
    repond a : « quelle est la probabilite que ce Sharpe depasse ce qu'on obtiendrait
    par pure chance, sachant que j'ai essaye N fois, et compte tenu de l'asymetrie
    et des queues epaisses de mes rendements ? »

    Un DSR inferieur a 0,95 signifie qu'on ne peut pas rejeter la chance.
    C'est un critere de rejet, pas un indicateur decoratif.

Aucune dependance externe : NormalDist vient de la bibliotheque standard.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import NormalDist

_N = NormalDist()
EULER_MASCHERONI = 0.5772156649015329
_INV_SQRT2 = 0.7071067811865476


def norm_cdf(x: float) -> float:
    """P(X <= x), sans annulation catastrophique.

    DEFAUT CORRIGE, MESURE.
        statistics.NormalDist.cdf emploie 0.5 * (1 + erf(x / V2)). Quand x est
        tres negatif, erf tend vers -1 et la somme 1 + (-1) perd tous ses chiffres
        significatifs. Mesure a x = -10 : la forme naive renvoie EXACTEMENT 0.0
        alors que la valeur vraie est 7.61985302416059e-24. Erreur relative 100 %.

        Consequence concrete : le PSR d'une strategie mediocre valait exactement 0
        au lieu d'une valeur exploitable, rendant deux mauvais resultats
        indiscernables l'un de l'autre.

        La forme 0.5 * erfc(-x / V2) est exacte sur toute la plage.

    Limite residuelle : l'arrondi sur l'argument -x/V2 est amplifie d'un facteur
    ~2a^2 dans la queue, soit environ 1e-13 vers x = -37. L'implementation C++
    corrige aussi ce terme par un calcul d'argument en double-double et atteint
    1.7e-16 ; en Python le gain ne justifie pas la complexite.
    """
    return 0.5 * math.erfc(-x * _INV_SQRT2)


def norm_quantile_upper(q: float) -> float:
    """Phi^-1(1 - q), calcule SANS jamais former 1 - q.

    DEFAUT CORRIGE, MESURE.
        Phi^-1(1 - 1/N) echoue des que 1 - 1/N s'arrondit a 1.0, ce qui survient
        pour N >= 1e16 en double : StatisticsError, purement et simplement. Et la
        precision se degrade avant l'echec — 7e-4 d'erreur des N = 1e15.

        Par symetrie Phi^-1(1 - q) = -Phi^-1(q), et l'argument reste alors loin
        de 1. Couvre tout N jusqu'a 1e300.
    """
    return -_N.inv_cdf(q)


# ---------------------------------------------------------------- moments
def _central_moment(xs: list[float], k: int) -> float:
    n = len(xs)
    if n == 0:
        return 0.0
    m = sum(xs) / n
    return sum((x - m) ** k for x in xs) / n


def skewness(xs: list[float]) -> float:
    """Asymetrie (population). Nulle pour une loi symetrique."""
    m2 = _central_moment(xs, 2)
    if m2 <= 0:
        return 0.0
    return _central_moment(xs, 3) / m2 ** 1.5


def kurtosis(xs: list[float]) -> float:
    """Kurtosis BRUT, non excedentaire : vaut 3 pour une loi normale.

    C'est la convention de la formule du PSR. Passer un kurtosis excedentaire
    (normal = 0) fausse silencieusement le resultat.
    """
    m2 = _central_moment(xs, 2)
    if m2 <= 0:
        return 3.0
    return _central_moment(xs, 4) / m2 ** 2


# ---------------------------------------------------------------- Sharpe
def _is_numerically_flat(sd: float, xs: list[float]) -> bool:
    """Un ecart-type indiscernable de zero, a l'echelle des donnees.

    Tester `sd == 0` ne suffit pas. Sur une serie constante, l'arithmetique
    flottante laisse une variance residuelle de l'ordre de 1e-18 : le Sharpe
    calcule vaut alors 1e15 au lieu de zero. C'est un mode de defaillance
    silencieux et dangereux, parce qu'un Sharpe absurde ressemble a une
    decouverte avant de ressembler a un bug.
    """
    scale = max((abs(x) for x in xs), default=0.0) or 1.0
    return sd <= scale * 1e-12


def sharpe_ratio(returns: list[float], periods_per_year: int | None = None) -> float:
    """Sharpe par observation, ou annualise si periods_per_year est fourni."""
    n = len(returns)
    if n < 2:
        return 0.0
    mean = sum(returns) / n
    var = sum((r - mean) ** 2 for r in returns) / (n - 1)
    sd = math.sqrt(var)
    if _is_numerically_flat(sd, returns):
        return 0.0
    sr = mean / sd
    return sr * math.sqrt(periods_per_year) if periods_per_year else sr


def probabilistic_sharpe_ratio(returns: list[float], sr_benchmark: float = 0.0) -> float:
    """PSR : probabilite que le vrai Sharpe depasse sr_benchmark.

    sr_benchmark et le Sharpe observe doivent tous deux etre exprimes PAR
    OBSERVATION, jamais annualises. Melanger les deux echelles est l'erreur
    classique sur cette formule.
    """
    T = len(returns)
    if T < 3:
        return 0.0
    sr = sharpe_ratio(returns)
    g3, g4 = skewness(returns), kurtosis(returns)

    denom_sq = 1.0 - g3 * sr + (g4 - 1.0) / 4.0 * sr ** 2
    if denom_sq <= 0:
        return 0.0                     # variance estimee non valide
    z = (sr - sr_benchmark) * math.sqrt(T - 1) / math.sqrt(denom_sq)
    return norm_cdf(z)          # erfc : exacte jusqu'a 1e-300


def expected_max_sharpe(n_trials: float, sr_variance: float) -> float:
    """Sharpe maximal ESPERE sous l'hypothese nulle, apres n_trials essais.

    C'est le seuil que le hasard seul atteint. Il croit avec le nombre d'essais :
    plus on cherche, plus le meilleur resultat fortuit est bon.
    """
    if n_trials < 2 or sr_variance <= 0:
        return 0.0
    g = EULER_MASCHERONI
    # Forme complementaire : l'argument reste 1/N, jamais 1 - 1/N.
    a = norm_quantile_upper(1.0 / n_trials)
    b = norm_quantile_upper(1.0 / (n_trials * math.e))
    return math.sqrt(sr_variance) * ((1.0 - g) * a + g * b)


def deflated_sharpe_ratio(
    returns: list[float], n_trials: float, sr_variance: float | None = None
) -> float:
    """DSR : PSR mesure contre le seuil du hasard plutot que contre zero.

    n_trials    nombre HONNETE de configurations essayees. Compte tout : chaque
                variante de parametre, chaque univers, chaque fenetre. Sous-declarer
                revient a se mentir avec plus d'etapes.
    sr_variance variance des Sharpe entre essais. A defaut, on approxime par la
                variance de l'estimateur sous la nulle, 1/(T-1).
    """
    T = len(returns)
    if T < 3:
        return 0.0
    if sr_variance is None:
        sr_variance = 1.0 / (T - 1)
    sr0 = expected_max_sharpe(n_trials, sr_variance)
    return probabilistic_sharpe_ratio(returns, sr_benchmark=sr0)


# ---------------------------------------------------------------- risque
def max_drawdown(equity: list[float]) -> tuple[float, int, int]:
    """Perte maximale depuis un sommet, en fraction. Retourne (dd, i_pic, i_creux)."""
    if not equity:
        return 0.0, 0, 0
    peak, peak_i = equity[0], 0
    worst, wi, wj = 0.0, 0, 0
    for i, v in enumerate(equity):
        if v > peak:
            peak, peak_i = v, i
        dd = (peak - v) / abs(peak) if peak else 0.0
        if dd > worst:
            worst, wi, wj = dd, peak_i, i
    return worst, wi, wj


def sortino_ratio(returns: list[float], periods_per_year: int | None = None) -> float:
    """Comme le Sharpe, mais ne penalise que la volatilite a la baisse."""
    n = len(returns)
    if n < 2:
        return 0.0
    mean = sum(returns) / n
    downside = [r for r in returns if r < 0]
    if not downside:
        return float("inf") if mean > 0 else 0.0
    dd = math.sqrt(sum(r ** 2 for r in downside) / len(downside))
    if _is_numerically_flat(dd, returns):
        return 0.0
    s = mean / dd
    return s * math.sqrt(periods_per_year) if periods_per_year else s


# ---------------------------------------------------------------- synthese
@dataclass
class PerformanceReport:
    n_observations: int
    total_return: float
    sharpe: float
    sharpe_annualised: float
    sortino: float
    max_drawdown: float
    psr: float
    dsr: float
    n_trials: int
    skew: float
    kurtosis: float
    verdict: str
    avertissement: str = ""

    def __str__(self) -> str:
        return (
            f"Observations      : {self.n_observations:,}\n"
            f"Rendement total   : {self.total_return:+.4%}\n"
            f"Sharpe (obs)      : {self.sharpe:+.4f}\n"
            f"Sharpe annualise  : {self.sharpe_annualised:+.4f}\n"
            f"Sortino           : {self.sortino:+.4f}\n"
            f"Drawdown max      : {self.max_drawdown:.4%}\n"
            f"Asymetrie         : {self.skew:+.4f}\n"
            f"Kurtosis (brut)   : {self.kurtosis:.4f}\n"
            f"PSR (vs 0)        : {self.psr:.4f}\n"
            f"DSR ({self.n_trials} essais)".ljust(18) + f": {self.dsr:.4f}\n"
            f"VERDICT           : {self.verdict}"
            + (f"\n\n! {self.avertissement}" if self.avertissement else "")
        )


def report(
    returns: list[float],
    equity: list[float],
    n_trials: int = 1,
    periods_per_year: float = 252,
) -> PerformanceReport:
    """periods_per_year doit refleter la frequence REELLE des observations.

    ATTENTION A L'ANNUALISATION. Multiplier un Sharpe par racine(N) suppose des
    rendements independants. A l'echelle du tick, ils sont fortement autocorreles :
    l'annualisation surestime alors massivement le resultat. Un Sharpe annualise a
    quatre chiffres n'est pas une performance, c'est un artefact d'echelle.

    A frequence tres elevee, le Sharpe PAR OBSERVATION est la seule grandeur
    interpretable, et c'est sur elle que reposent le PSR et le DSR.
    """
    dsr = deflated_sharpe_ratio(returns, n_trials)
    total = (equity[-1] - equity[0]) / abs(equity[0]) if equity and equity[0] else 0.0
    avert = ""
    if periods_per_year > 1_000_000:
        avert = (f"Facteur d'annualisation de {periods_per_year:,.0f} : le Sharpe annualise "
                 "n'est PAS interpretable a cette frequence (racine-temps suppose des "
                 "rendements independants, ce que le tick n'est pas). Lire le Sharpe "
                 "par observation et le DSR.")
    return PerformanceReport(
        n_observations=len(returns),
        total_return=total,
        sharpe=sharpe_ratio(returns),
        sharpe_annualised=sharpe_ratio(returns, periods_per_year),
        sortino=sortino_ratio(returns, periods_per_year),
        max_drawdown=max_drawdown(equity)[0],
        psr=probabilistic_sharpe_ratio(returns),
        dsr=dsr,
        n_trials=n_trials,
        skew=skewness(returns),
        kurtosis=kurtosis(returns),
        verdict=("RETENIR" if dsr > 0.95 else
                 "INSUFFISANT" if dsr > 0.50 else
                 "INDISCERNABLE DU HASARD"),
        avertissement=avert,
    )
