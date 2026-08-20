# Kairos

Système de capture de dislocations de prix. Phase 1 : collecte et mesure. 

## Démarrage sans compte broker

```bash
pip install -r requirements.txt
python scripts/collect.py --venue synthetic --duration 60
python scripts/analyze.py 'data/quotes_*'
```

Le feed synthétique injecte un bruit d'amplitude **connue** dans la relation de
non-arbitrage. L'analyseur doit le retrouver. S'il ne le retrouve pas, le bug est
dans l'analyseur — et tu l'apprends sans avoir risqué un euro.

## Avec IBKR

Prérequis : IB Gateway ou TWS lancé, API activée, port cohérent avec `config.yaml`
(4002 = Gateway paper, 4001 = live, 7497 = TWS paper).

```bash
python scripts/collect.py --venue ibkr
```

### Limites d'IBKR à connaître avant de déboguer

- 100 lignes de données de marché simultanées par défaut
- Pacing à ~50 messages/seconde ; au-delà le flux est étranglé sans erreur claire
- Le flux standard n'est **pas** du tick-by-tick : ce sont des snapshots agrégés
  (~250 ms). D'où `reqTickByTickData`, indispensable à toute mesure sérieuse
- Le Gateway impose un redémarrage quotidien

### Redémarrage quotidien

IBC est **retiré le 1er septembre 2026**. Utilise le mécanisme d'autorestart natif
de TWS/Gateway plutôt que de construire sur une brique dont la péremption est connue.
Alternative de fond : migrer vers la Web API d'IBKR avec OAuth, qui supprime la
dépendance au gateway de bureau.

## Sécurité — à faire avant toute ligne de code d'exécution

Clés API avec **retrait désactivé** et **liste blanche d'adresses IP**. Une clé
compromise sans droit de retrait coûte des trades indésirables ; avec droit de
retrait, elle coûte tout.

Secrets hors dépôt. Vérifie ton `.gitignore` avant le premier commit.

## Architecture

Une règle : **le même code de stratégie tourne en backtest et en live**, seule la
source d'événements change. C'est la seule défense contre l'écart backtest/live.

Aucune spécificité de venue ne franchit la frontière de `feed/`.

## Structure

| Module | Rôle |
|---|---|
| `events.py` | `Quote` normalisé, trois horloges |
| `clock.py` | Murale vs monotone, quantiles de latence |
| `feed/` | Connecteurs → format interne unique |
| `store/` | Persistance par fragments, repli CSV |
| `analysis/` | Déviation triangulaire, verdict chiffré |

## Trois pièges encodés dans ce dépôt

**Trois horodatages par quote, et il faut les trois.** L'horloge murale est
comparable entre machines mais peut sauter ; la monotone ne saute jamais et c'est
la seule base valide pour un delta de durée ; celle du venue peut être fausse ou
absente. Les confondre produit des latences négatives et des backtests faux.

**Bid pour vendre, ask pour acheter — jamais le mid.** Calculer une déviation
triangulaire sur les mid produit des opportunités fantômes, et rend un backtest
brillamment rentable et entièrement faux.

**Fragments, jamais d'append.** Relire un fichier entier à chaque lot donne un coût
quadratique. Second mérite : une session interrompue reste exploitable.
