# Lancer Kairos sur ton compte simulation IBKR

*Chaque clic, chaque champ, dans l'ordre*

---

## D'abord, la réponse à ta question

**Oui.** IBKR TWS te branche sur les vrais marchés, en temps réel.

Le marché des changes cote en continu du dimanche 23 h (Paris) au vendredi 23 h. Ce lundi 17 août à 21 h 45, tu es en **pleine séance de New York**, l'une des plus liquides de la journée. Les prix que tu verras bougeront réellement, tick par tick.

**Une nuance importante :** ce que tu reçois dépend de ta **souscription aux données de marché**. Sans elle, TWS se connecte, ton pont tourne, tout a l'air de fonctionner — et tu ne reçois que des prix différés de 15 minutes, inutilisables. L'étape 2 traite ce point, et c'est celle que tout le monde rate.

**Le compte est simulé, les prix ne le sont pas.** C'est exactement ce qu'on veut : de vraies données, zéro argent en jeu.

---

## Étape 1 — Créer le compte simulation

1. Va sur **interactivebrokers.fr**, connecte-toi au **portail client**
2. En haut à droite, clique sur ton **nom** → **Paramètres**
3. Section **Compte** → cherche **« Compte Paper Trading »** (ou *Paper Trading Account*)
4. Clique sur **Créer** ou **Activer**

IBKR génère un identifiant distinct, qui commence par **DU** suivi de chiffres. **Note-le** — c'est avec celui-là que tu te connecteras à TWS, pas avec ton identifiant habituel.

Le mot de passe est le même que ton compte réel, sauf si tu le changes.

---

## Étape 2 — Partager les données de marché

**Sans cette étape, rien ne marchera correctement.**

1. Toujours dans le portail client : **Paramètres** → **Abonnements aux données de marché**
2. Vérifie que tu as bien une souscription qui couvre le **Forex** (souvent incluse dans *IDEALPRO*, sinon cherche une ligne mentionnant *Spot FX* ou *Cash Forex*)
3. Cherche l'option **« Partager les données de marché avec le compte Paper Trading »** — parfois libellée *Share market data with paper account*
4. **Active-la**, puis valide

Le partage peut prendre quelques minutes à se propager. Si tu viens de l'activer, attends dix minutes.

---

## Étape 3 — Fixer le solde à 1 000 $

Ton compte paper démarre à un million. Pour le ramener à mille :

1. Portail client → **Paramètres** → **Compte Paper Trading**
2. Cherche **« Réinitialiser le solde »** (*Reset Paper Trading Account Balance*)
3. Saisis **1000** dans le champ du montant
4. Valide

> **Mais ce n'est pas ce qui compte pour Kairos.**
>
> Le pont est en **lecture seule** : il ne passe aucun ordre, donc le solde du compte n'a aucune influence sur ce qu'il calcule. Ce qui compte, c'est le **notionnel** — la taille de la boucle que le modèle simule. Il se règle en ligne de commande :
>
> ```
> --notionnel 1000
> ```
>
> **Et il faut que tu voies ce que ça fait à l'arithmétique**, parce que c'est brutal.

### Ce que 1 000 $ coûte réellement

Le plancher de commission d'IBKR est de **2 $ par ordre**. Sur 1 000 $ de notionnel, cela représente **20 bps par jambe** — cent fois le tarif affiché de 0,20 bps.

| Notionnel | Commission par jambe | Coût d'une boucle à 3 jambes | Face aux 0,46 bps disponibles |
|---:|---:|---:|---:|
| **1 000 $** | **20,00 bps** | **60,00 bps** | **130×** |
| 10 000 $ | 2,00 bps | 6,00 bps | 13× |
| 100 000 $ | 0,20 bps | 0,60 bps | 1,3× |

À 1 000 $, il faudrait **130 fois plus d'inefficience qu'il n'en existe**. Et sur une boucle à 5 jambes, le coût monte à 100 bps, soit 217×.

**Ce n'est pas une raison de ne pas le faire.** C'est même le bon choix pour commencer : tu valides la plomberie, tu mesures ta latence réelle, tu confirmes les conventions de cotation. Mais tu sauras que le tableau restera vide — et que **c'est le résultat attendu**, pas une panne.

---

## Étape 4 — Installer et lancer TWS

Si ce n'est pas déjà fait, dans le Terminal du Mac :

```bash
brew install --cask ibkr-trader-workstation
```

Si macOS refuse de l'ouvrir : **Réglages Système** → **Confidentialité et sécurité** → descends en bas → **Ouvrir quand même**.

Au lancement, TWS demande tes identifiants :

- **Nom d'utilisateur :** celui qui commence par **DU**
- **Mot de passe :** le tien
- Vérifie que le mode indiqué est bien **Paper Trading** (souvent affiché en jaune ou orange)

---

## Étape 5 — Activer l'API

Dans TWS, menu du haut :

**File** → **Global Configuration…** → dans l'arbre de gauche, déplie **API** → clique sur **Settings**

Coche et remplis exactement ceci :

| Champ | Valeur | Pourquoi |
|---|---|---|
| **Enable ActiveX and Socket Clients** | ☑ coché | Sans cela, aucune connexion possible |
| **Read-Only API** | ☑ **coché** | Le broker refuse tout ordre, quoi qu'envoie le code |
| **Socket port** | **7497** | Port du compte simulation |
| **Allow connections from localhost only** | ☑ coché | Sauf si le Raspberry doit s'y connecter |
| **Trusted IPs** | `127.0.0.1` | Ajoute l'IP du Pi le moment venu |
| Master API client ID | *laisser vide* | — |

Puis **Apply**, puis **OK**.

> **Coche « Read-Only API ».** Le pont ne contient aucune capacité de passer un ordre — un test l'inspecte à chaque exécution de la CI. Mais cette case ajoute une seconde barrière, côté broker cette fois. Deux garde-fous indépendants valent mieux qu'un seul.

**Ne ferme pas TWS.** Il doit rester ouvert pendant toute la session.

---

## Étape 6 — Vérifier avant de lancer

Dans le Terminal :

```bash
cd ~/Documents/kairos-projet
source .venv/bin/activate
python scripts/paper_test.py --port 7497
```

Le script écoute vingt secondes et contrôle dix points : le port répond, le compte commence bien par `DU`, les 8 paires arrivent, la latence est plausible, aucun niveau n'est aberrant, et EUR/JPY concorde avec EUR/USD × USD/JPY.

Chaque échec affiche la correction exacte. **Ne passe à l'étape suivante que si tout est vert.**

---

## Étape 7 — Lancer le pont

```bash
python bridge/live_bridge.py --source ibkr --port 7497 \
       --notionnel 1000 \
       --out dashboard/kairos-live.json \
       --journal journal
```

Tu dois voir défiler, toutes les 30 secondes :

```
[pont] 8 paires · fraicheur 120 ms · 14 boucles · 0 nette(s)
```

Laisse cette fenêtre ouverte. **Ctrl + C** pour arrêter.

---

## Étape 8 — Ouvrir l'interface

Le navigateur bloque la lecture de fichiers locaux en JavaScript. Il faut donc un petit serveur — une seule commande, dans **un second onglet de Terminal** :

```bash
cd ~/Documents/kairos-projet/dashboard
python3 -m http.server 8000
```

Puis ouvre dans le navigateur :

```
http://localhost:8000/kairos.html
```

L'écran d'accueil s'affiche. **Rien n'est visible tant que tu n'as pas cliqué sur « LANCER L'ALGORITHME ».** Aucune donnée simulée : le tableau ne se remplit qu'avec ce que le marché envoie réellement.

Si la connexion échoue, l'interface te dit exactement quoi faire — elle ne bascule jamais en démonstration.

Pour l'avoir en fenêtre autonome à côté de TWS :

```bash
open -na "Google Chrome" --args --app="http://localhost:8000/kairos.html"
```

---

## Étape 9 — Exporter le tableau

Bouton **« EXPORTER CSV »** en haut à droite. Il produit un fichier avec les 20 colonnes, séparateur point-virgule et encodage UTF-8 avec BOM — Excel français l'ouvre directement, sans caractères cassés.

Le pont écrit **aussi** son propre journal, en continu, dans `journal/` :

- `ordres_AAAA-MM-JJ.csv` — une ligne par opération, avec le détail jambe par jambe
- `resume_quotidien.csv` — une ligne par jour : boucles examinées, taux de retenue, P&L, couverture de la collecte, nombre de trous

Ces deux fichiers-là survivent à la fermeture du navigateur. L'export du bouton est un instantané ; le journal est la trace.

---

## Le récapitulatif en cinq lignes

```bash
# Terminal 1 — le pont
cd ~/Documents/kairos-projet && source .venv/bin/activate
python scripts/paper_test.py --port 7497          # vérifier
python bridge/live_bridge.py --source ibkr --port 7497 --notionnel 1000 \
       --out dashboard/kairos-live.json --journal journal

# Terminal 2 — l'interface
cd ~/Documents/kairos-projet/dashboard && python3 -m http.server 8000
```

Puis **http://localhost:8000/kairos.html** → **LANCER L'ALGORITHME**.

---

## Ce que tu vas voir, et comment le lire

Le compteur **« Boucles »** va monter vite — plusieurs milliers par minute. Le compteur **« Ordres »** restera probablement à zéro.

**Ce n'est pas un dysfonctionnement.** C'est la mesure fondatrice du projet, confirmée sur tes propres données : le marché offre 0,46 bps d'inefficience, ta boucle en coûte 60 à 1 000 $ de notionnel. Le système regarde des milliers d'opportunités et n'en retient aucune parce qu'aucune ne couvre ses frais.

Le jour où tu verras une ligne à trois chiffres en bps, ce sera une paire mal orientée, pas une fortune.

---

*Le pont est en lecture seule par construction. Aucun ordre ne peut être transmis, sur aucun compte, simulé ou réel.*
