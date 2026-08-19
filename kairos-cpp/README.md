# Kairos C++

Noyau de calcul en C++20. En-tetes uniquement.

## Pourquoi C++, et pour quelle partie

C++ est le standard de l'industrie financiere — banques, teneurs de marche,
plateformes. Mais **ce n'est pas la boucle d'ordre qui le justifie ici** : le RTT
reseau vers un venue est de ~50 000 microsecondes, Python en coute ~100. Y porter
la boucle optimiserait 0,2 % du probleme.

Le gain est **dans le moteur de rejeu**, et il est mesure :

| | Python | C++ | Gain |
|---|---:|---:|---:|
| Moteur (100 000 quotes) | 479,5 ms | 8,5 ms | **56x** |
| Metriques | 163,7 ms | 2,0 ms | **81x** |
| Debit | 0,21 M quotes/s | 11,8 M quotes/s | **56x** |

Ce facteur ne change pas la latence d'execution. Il change la **vitesse
d'iteration en recherche** — le nombre d'hypotheses testables par semaine, seul
multiplicateur qui compte a ce stade.

## Compiler

Le plus simple, sans rien installer d'autre qu'un compilateur :

```bash
make test     # 58 tests
make bench    # 1 000 000 de quotes
make xval     # sortie de validation croisee
```

Avec CMake (`brew install cmake`) :

```bash
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j
./build/kairos_tests
```

Sur macOS, `clang++` fait l'affaire : `make CXX=clang++ test`.

## Ce qui a ete corrige par rapport a l'implementation Python

Trois defauts numeriques, tous **mesures** contre mpmath a 300 chiffres, jamais
supposes.

**1. Annulation catastrophique dans la queue de la loi normale.**
`0.5*(1 + erf(x/V2))` renvoie EXACTEMENT `0.0` des x = -10, la ou la valeur vraie
est 7.6e-24. Le PSR d'une strategie mediocre valait donc zero, rendant deux
mauvais resultats indiscernables. Corrige par `0.5*erfc(-x/V2)`.

**2. Amplification de l'erreur d'argument.**
`std::erfc` est exacte a 2,3e-15 — mesure. Pourtant `norm_cdf(-37)` affichait
8,8e-14 d'erreur. La cause n'est pas erfc mais l'arrondi sur `-x/V2` : dans la
queue, erfc se comporte comme exp(-a^2), donc une erreur relative sur `a` est
amplifiee d'un facteur ~2a^2, soit ~1370 a a = 26. Corrige par un calcul
d'argument en double-double (residu exact du produit recupere par `fma`) suivi
d'une correction au premier ordre. **Erreur ramenee de 8,8e-14 a 1,7e-16 —
facteur 500.**

**3. Echec du quantile pour un grand nombre d'essais.**
`Phi^-1(1 - 1/N)` echoue des N >= 1e16, car `1 - 1/N` s'arrondit a 1,0. La
precision se degradait deja avant : 7e-4 d'erreur a N = 1e15. Corrige par la
forme complementaire `-Phi^-1(1/N)`, valide jusqu'a N = 1e300.

## Ce qui a ete mesure puis REJETE

**Le point-fixe pour la monnaie.** 200 000 executions accumulees en `double`,
comparees a une reference `Decimal` exacte : **0,0000 centime d'erreur**. Le
double offre dix ordres de grandeur de marge a cette echelle. Le point-fixe reste
necessaire pour la reconciliation avec le venue, pas pour la simulation.

**La sommation compensee de Kahan-Neumaier.** Sur un million d'executions,
l'accumulation naive egale la reference exacte au bit pres. Aucun gain a
compenser une erreur nulle.

**Les moments en ligne de Pebay.** Confrontes a une reference rationnelle exacte,
ils sont **moins** precis que la methode a deux passes sur donnees fortement
decalees (1,3e-4 contre 8,0e-5). Le vrai correctif est le centrage explicite,
commun aux deux methodes. On garde deux passes : plus simple et plus rapide.

> Ajouter une complexite « par prudence » sans la mesurer produit du code plus
> difficile a auditer pour un gain nul. Chacun de ces trois choix est justifie par
> un chiffre, pas par une reputation.

## Validation croisee

`apps/crossvalidate.cpp` et son pendant Python calculent 27 grandeurs sur des
entrees identiques : Sharpe, Sortino, drawdown, PSR, DSR a cinq nombres d'essais,
les quatre moments, quatre grandeurs de portefeuille, et cinq du cash and carry.

**27/27 concordent a mieux que 1e-12.** Ecart maximal 2,0e-13, sur l'asymetrie —
attendu, le moment d'ordre trois amplifiant l'arrondi.

## Structure

```
include/kairos/
  math/normal.hpp      CDF par erfc, quantile Acklam + Halley, double-double
  math/moments.hpp     Moments deux passes, detection de platitude numerique
  core/types.hpp       Quote, Order, Fill, Side
  core/portfolio.hpp   Prix moyen, reduction, inversion
  backtest/fills.hpp   File d'attente, traversee, couts
  backtest/engine.hpp  Boucle deterministe, latence, annulation en vol
  backtest/metrics.hpp Sharpe, PSR, DSR, drawdown
  carry/simulator.hpp  Cash and carry, liquidation isolee contre croisee
```

## Note sur -ffast-math

**Proscrit.** Il autorise le reordonnancement des operations flottantes et
suppose l'absence de NaN et d'infinis. Le determinisme du moteur — memes entrees,
meme sortie, toujours — en depend, et c'est lui qui rend possibles le test de
non-regression backtest/live et l'analyse d'incident.
