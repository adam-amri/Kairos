# Kairos — état des missions M1 à M7

*15 août 2026*

---

## Constat d'ouverture

**Les fichiers annoncés n'existent nulle part.** `include/kairos/arb/detector.hpp`, `dashboard/`, `bridge/live_bridge.py`, `docs/raspberry.md` : absents de ma copie de travail comme de `~/Documents/kairos-projet`, qui était **vide** au moment de l'exploration. Le chemin Windows `C:\Users\adama\...` n'est pas atteignable depuis un Mac.

J'ai donc écrit le détecteur depuis zéro, à partir des critères de vérification que tu as fournis. **Si les fichiers de l'autre session existent, envoie-les** : je comparerai les deux implémentations plutôt que d'imposer la mienne.

---

## Deux chiffres de référence qui ne se vérifient pas

Le projet a pour règle qu'une référence se calcule, jamais ne se rappelle. Appliquée à tes propres chiffres, elle en invalide deux.

### Comptage des cycles

| Jambes | Annoncé | Calculé | Formule |
|---:|---:|---:|---|
| 3 | 70 | **70** ✓ | C(7,3) × 2! |
| 4 | 280 | **210** ✗ | C(7,4) × 3! |
| 5 | 784 | **504** ✗ | C(7,5) × 4! |

Vérifié deux fois : par la formule *et* par énumération brute. Aucune définition standard — cycles dirigés distincts, cycles ancrés sur une devise de base, séquences énumérées — ne produit 280 ni 784.

**Définition retenue, explicite dans le code :** rotations identifiées, sens distincts, chaque devise au plus une fois. C'est la définition qui compte les opportunités *économiquement distinctes*.

### Comptage filtré sur 12 paires

14/34/50 n'est **ni vérifiable ni reproductible** sans la liste exacte des 12 paires. Avec un jeu plausible de majeures j'obtiens 16/24/20. Le comptage filtré dépend entièrement de la topologie du graphe — envoie la liste et je recalculerai.

---

## M1 — Détecteur N-jambes ✅

**`include/kairos/arb/detector.hpp` — écrit, compilé, 29 tests, 0 échec.**

### Le bug de convention de cotation, reproduit exactement

C'était le critère le plus précis de ta liste, et il tombe juste :

| | Résultat |
|---|---:|
| Aller-retour GBP→USD→GBP, orientation correcte | **−0,7864 bps** |
| Spread coté de la paire | 0,7864 bps |
| Version naïve (taux × taux dans les deux sens) | **+6 167 bps** |

L'aller-retour correct perd **exactement le spread** — c'est le comportement attendu. La version naïve produit les ~6 170 bps fictifs que tu avais relevés. Le test `test_convention_de_cotation` verrouille les deux.

La règle encodée : une paire cotée `BASE/QUOTE` se lit « QUOTE par BASE ». Convertir BASE→QUOTE **multiplie par le bid** ; QUOTE→BASE **divise par le ask**. Les deux sens existent, avec des formules différentes.

### Modèle de coûts — reproduit le rapport au centième

| Notionnel | Rapport | Détecteur |
|---:|---:|---:|
| 5 000 | 12,42 | **12,420** |
| 10 000 | 6,42 | **6,420** |
| 25 000 | 2,82 | **2,820** |
| 50 000 | 1,62 | **1,620** |
| 100 000 | 1,02 | **1,020** |
| 1 000 000 | 1,02 | **1,020** |

Le seuil du plancher est vérifié à 100 000 $ exactement.

### Philosophie encodée dans l'API

`scan()` retourne par défaut **uniquement les opportunités nettes**. `Opportunity` porte les trois chiffres — brut, coût, net — pour que l'écart soit visible. C'est la mesure fondatrice du projet (63,8 % de bruts positifs pour 0,00 % au-dessus du seuil) transformée en contrainte d'interface : un détecteur qui expose le brut seul invite à se tromper.

Test de détection : triangle cohérent à 10k → **0 opportunité nette**. Dislocation de +20 bps injectée à 100k → détectée, net +18,88 bps.

### CI étendue au C++

`.github/workflows/cpp.yml` : compilation et tests sur Ubuntu et macOS, plus **un job qui échoue si `-ffast-math` réapparaît** dans le Makefile ou le CMakeLists. Sa présence est désormais une erreur de build, pas une préférence de style.

`make test` lance les 58 tests du noyau **et** les 29 du détecteur.

---

## Interface minimaliste ✅

**`dashboard/kairos.html`** — un seul fichier, aucune dépendance, aucun `npm install`. Double-clic et ça s'ouvre.

Ce choix est délibéré : le Vite + React + Tailwind annoncé demande une chaîne de build à installer et entretenir. Pour une interface dont le cahier des charges est « strict minimum, amateur », un fichier HTML autonome est plus robuste et plus honnête.

**Ce qu'elle montre, et rien de plus :**

1. **Le gain cumulé net**, en gros, en haut. Net de commissions et de spread — jamais de brut.
2. **La courbe d'évolution** du cumul. SVG dessiné à la main, sans bibliothèque.
3. **Le tableau des arbitrages** : heure, parcours complet devise par devise (`EUR → USD → JPY → EUR`), nombre de jambes, gain net.
4. **Trois compteurs** : arbitrages réalisés, boucles examinées, taux de retenue après frais.

**Le nombre de jambes est libre** — 3, 4 ou 5 devises, la boucle se referme toujours. Vérifié sur 3 000 tirages : aucune boucle ouverte, aucune devise répétée.

**Ce que j'ai ajouté, et pourquoi.** Le compteur « boucles examinées » face à « arbitrages réalisés » rend visible la leçon centrale du projet : on regarde des milliers de boucles pour n'en retenir presque aucune. Sans ce rapport affiché, un observateur croirait que l'arbitrage est fréquent.

**Le mode démonstration s'annonce comme tel.** Sans marché connecté, la page génère des données — et le dit explicitement, en gras, dans la note du bas. Afficher un P&L de fiction sans le signaler serait exactement ce que le projet s'interdit.

**Un seul chemin de calcul.** Le rendu, le cumul et la courbe sont identiques que les données viennent de `kairos-live.json` ou du générateur. Seule la source d'événements change — principe n° 4.

---

## M2 à M7 — état réel, sans enjolivement

| Mission | État | Blocage |
|---|---|---|
| **M2** Durée de vie des déviations | ⬜ Non fait | Exige les données de Phase 1, qui n'existent pas encore |
| **M3** Risque de jambe / profondeur L2 | ⬜ Non fait | Faisable sans données — voir plus bas |
| **M4** IBKR paper + 5 jours de collecte | 🔴 **Impossible pour moi** | Exige ton compte, ton TWS, et cinq jours réels |
| **M5** Raspberry Pi, 48 h de collecte | 🔴 **Impossible pour moi** | Exige le matériel et 48 h réelles |
| **M6** Évolution du dashboard React | 🟡 Remplacé | Le `dashboard/` annoncé n'existe pas ; j'ai livré l'interface minimaliste demandée |
| **M7** Hygiène du dépôt | 🟡 Partiel | CI C++ faite ; génération des constantes et unification du décompte de tests à faire |

**Sur M4 et M5, soyons nets :** je n'ai accès ni à ton compte IBKR, ni à un Raspberry Pi, ni à cinq jours de temps réel. Les livrables demandés — capture d'écran du dashboard en LIVE, histogramme de Phase 1, 48 h de collecte ininterrompue — sont des **actions que toi seul peux exécuter**. Je peux écrire le pont, le service systemd et le script de diagnostic ; je ne peux pas les faire tourner.

**Sur M3, une remarque de fond.** La profondeur de carnet L2 est probablement hors de portée : le flux IBKR standard livre des instantanés agrégés (~250 ms) et le tick-by-tick ne donne que le haut de carnet. Sans L2 réel, un modèle de profondeur serait de la fiction paramétrée. Le risque de jambe, lui, est modélisable dès maintenant — et devrait l'être avant tout capital réel.

---

## Ce que je propose ensuite, par ordre de valeur

1. **Le risque de jambe** (M3, partie faisable). Mode de défaillance canonique de l'arbitrage multi-jambes, modélisable sans données, et bloquant pour toute exécution réelle.
2. **Le pont de données** `bridge/live_bridge.py` + service systemd + `doctor.py` du Pi. Je les écris, tu les lances.
3. **M7 complet** : générer les constantes de `normal.hpp` par script mpmath, unifier le décompte de tests (aujourd'hui 58 C++ + 29 détecteur + 128 Python = **215**, et les documents citent encore des chiffres partiels).
4. **M2** dès que tu auras cinq jours de données.

---

## Ce dont j'ai besoin de toi

- **Les fichiers de l'autre session**, s'ils existent — pour comparer plutôt qu'écraser.
- **La liste exacte des 12 paires** utilisée pour le comptage 14/34/50.
- **Lancer la collecte.** C'est le seul chemin vers M2 et vers le verdict de Phase 1, et il passe par ta machine.

---

*Chaque chiffre de ce document est calculé et reproductible par `make test` et `make arb`. Aucun n'est rappelé de mémoire.*
