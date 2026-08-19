# Kairos — lancer le logiciel

*Un double-clic, une fenêtre*

---

## Ce qui a changé

Avant : un terminal pour le pont, un second pour le serveur web, puis le navigateur à ouvrir à la main. Trois choses à lancer dans le bon ordre, et un oubli laissait l'interface vide sans dire pourquoi.

Maintenant : **`app.py`** fait tout. Il démarre le pont, sert l'interface en local, et ouvre une fenêtre native.

---

## Installation, une seule fois

```bash
cd ~/Documents/kairos-projet
source .venv/bin/activate
pip install pywebview
chmod +x Kairos.command
```

`pywebview` donne une vraie fenêtre macOS, sans barre d'adresse ni onglets. S'il est absent, `app.py` bascule sur Chrome en mode application — ça marche aussi, c'est juste moins net.

---

## Lancer

**Depuis le Finder :** double-clic sur **`Kairos.command`**.

**Depuis le Terminal :**

```bash
cd ~/Documents/kairos-projet
source .venv/bin/activate
python app.py --source ibkr --port 7497 --notionnel 1000
```

Sans TWS, pour vérifier que tout s'ouvre :

```bash
python app.py --source demo
```

**Ctrl + C** arrête tout — pont compris. Fermer la fenêtre suffit également.

---

## L'écran de lancement

La fenêtre s'ouvre sur une liste d'états, rafraîchie toutes les deux secondes. Elle se met à jour toute seule quand tu démarres TWS : pas besoin de recharger.

| Ligne | Ce qu'elle vérifie |
|---|---|
| Pont de données | Le fichier `kairos-live.json` est écrit et lisible |
| Source | L'adresse interrogée |
| Connexion IBKR | Hôte et port, et si la poignée de main a réussi |
| Identifiant client | Le `clientId` utilisé — deux programmes ne peuvent pas partager le même |
| Compte | L'identifiant renvoyé par IBKR |
| Mode | **SIMULATION** ou **RÉEL** |
| Lecture seule | Le pont confirme qu'il ne peut pas passer d'ordre |
| Paires reçues | Combien sur les 8 attendues |
| Fraîcheur | Âge de la cotation la plus ancienne |
| Latence médiane | Écart venue → réception |
| Boucles surveillées | Combien de cycles le détecteur examine |
| Notionnel | La taille utilisée dans les calculs |

Chaque ligne porte un **✓ vert**, une **✗ rouge** ou un **·** gris.

Le bouton **LANCER L'ALGORITHME** reste désactivé tant que les maillons indispensables ne sont pas verts — et il **refuse de s'activer en mode RÉEL**. C'est délibéré : tant que la Phase 1 n'est pas close, aucune raison de pointer vers un compte réel, même en lecture seule.

---

## Le paramètre qui compte

```bash
--notionnel 1000
```

Le solde de ton compte paper n'entre dans aucun calcul — le pont ne passe aucun ordre. C'est le **notionnel** qui fixe la taille des boucles simulées.

Et il faut savoir ce qu'il fait :

| Notionnel | Commission/jambe | Coût 3 jambes | Face aux 0,46 bps disponibles |
|---:|---:|---:|---:|
| **1 000 $** | **20,00 bps** | **60,00 bps** | **130×** |
| 10 000 $ | 2,00 bps | 6,00 bps | 13× |
| 100 000 $ | 0,20 bps | 0,60 bps | 1,3× |

Le plancher IBKR de 2 $ pèse 20 bps par jambe sur mille dollars — cent fois le tarif affiché. Le tableau restera vide, et **c'est le résultat attendu**, pas une panne.

---

## Les options

| Option | Défaut | Rôle |
|---|---|---|
| `--source` | `demo` | `ibkr` ou `demo` |
| `--port` | `7497` | 7497 TWS simulation · 4002 Gateway simulation |
| `--host` | `127.0.0.1` | L'IP du Mac si le Pi s'y connecte |
| `--client-id` | `21` | Doit être unique par programme connecté |
| `--notionnel` | `1000` | Taille des boucles simulées |
| `--journal` | `journal` | Dossier des CSV quotidiens |
| `--store` | *(vide)* | Persistance des ticks, pour la Phase 1 |
| `--sans-pont` | — | Interface seule, si le pont tourne ailleurs |

Pour la collecte de cinq jours :

```bash
python app.py --source ibkr --port 7497 --notionnel 1000 \
              --store data/phase1 --journal journal
```

---

## En faire une vraie application

Pour obtenir un **`Kairos.app`** dans le Dock, avec icône :

```bash
pip install pyinstaller
pyinstaller --windowed --name Kairos \
            --add-data "dashboard:dashboard" \
            --add-data "bridge:bridge" \
            --add-data "kairos:kairos" \
            app.py
```

Le résultat apparaît dans `dist/Kairos.app`. Glisse-le dans **Applications**.

Au premier lancement, macOS le bloquera — il n'est pas signé. **Réglages Système → Confidentialité et sécurité → Ouvrir quand même**.

> Pour un usage personnel, `Kairos.command` suffit largement et évite de recompiler à chaque modification du code. Le `.app` a surtout un intérêt le jour où tu voudras l'installer sur une autre machine.

---

## Sur le C++

Tu es revenu plusieurs fois sur l'idée de tout porter en C++ pour passer les ordres plus vite. Le chiffre, mesuré :

| Poste | Temps | Nature |
|---|---:|---|
| Balayage complet du détecteur | 24 µs | ton code |
| Aller-retour réseau vers le broker | 50 000 µs | incompressible |
| Passerelle IBKR → venue | 10 000 µs | incompressible |
| Pacing IBKR | 20 000 µs | incompressible |

**Le calcul représente 0,15 % du trajet.** Le porter intégralement en C++ gagnerait 0,075 % — et une interface Qt en C++ demanderait des semaines pour afficher exactement le même tableau.

Le C++ est déjà dans le projet, là où il rapporte : le **moteur de rejeu**, mesuré **56× plus rapide** que Python. Ce facteur ne change pas ta latence d'exécution ; il change combien d'hypothèses tu peux tester par semaine.

---

## Récapitulatif

```bash
# une seule fois
pip install pywebview && chmod +x Kairos.command

# à chaque session
python app.py --source ibkr --port 7497 --notionnel 1000
```

TWS doit être ouvert, connecté au compte **DU**, avec l'API activée sur le port **7497** et **Read-Only API** cochée.

---

*Le pont est en lecture seule par construction. Aucun ordre ne peut être transmis, sur aucun compte.*
