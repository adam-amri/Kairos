# KAIROS — tout mettre en route

*Chaque commande, chaque clic, dans l'ordre. Ne saute aucune partie.*

---

# PARTIE 0 — Réparer Python

**C'est ce qui bloque tout en ce moment.** Ton environnement est en Python 3.9 ; Kairos exige 3.10 minimum, et c'est aussi ce qui faisait échouer `pyobjc` avec seize erreurs de compilation.

### 0.1 — Ouvrir le Terminal

**⌘ + Espace**, tape `Terminal`, **Entrée**.

### 0.2 — Aller dans le projet

```bash
cd ~/Documents/kairos-projet
```

### 0.3 — Supprimer l'ancien environnement

```bash
deactivate 2>/dev/null
rm -rf .venv
```

Si `deactivate` répond `command not found`, c'est normal — il n'était pas actif.

### 0.4 — Installer Python 3.12

```bash
brew install python@3.12
```

Si `brew` répond `command not found`, installe d'abord Homebrew :

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

On te demandera ton mot de passe de session — **il ne s'affiche pas pendant que tu tapes**, c'est normal. À la fin, Homebrew affiche deux ou trois lignes commençant par `echo` : **exécute-les**, puis ferme et rouvre le Terminal.

### 0.5 — Créer le nouvel environnement

```bash
cd ~/Documents/kairos-projet
$(brew --prefix)/bin/python3.12 -m venv .venv
source .venv/bin/activate
python --version
```

> **Arrête-toi ici si tu ne vois pas `Python 3.12.x`.** Rien ne fonctionnera sinon.

### 0.6 — Installer les dépendances

```bash
pip install --upgrade pip
pip install -r requirements.txt
pip install pytest
```

**N'installe pas `pywebview`.** C'est lui qui provoquait les seize erreurs. Le logiciel bascule tout seul sur Chrome en mode fenêtre — même résultat, zéro compilation.

### 0.7 — Vérifier

```bash
python scripts/doctor.py
```

Tout doit être `[OK]`. Chaque échec affiche la correction exacte.

```bash
python -m pytest tests/ -q
```

Tu dois voir **152 tests passés**.

---

# PARTIE 1 — Vérifier ton compte simulation

Tu l'as déjà. Il reste trois choses à contrôler, et la deuxième est celle qui fait échouer tout le monde.

> **Astuce de navigation.** Le portail IBKR change de mise en page régulièrement. Utilise la **loupe de recherche**, en haut du portail, plutôt que de fouiller les menus : tape le terme indiqué à chaque étape et clique le résultat.

### 1.1 — Retrouver ton identifiant DU

1. Va sur **interactivebrokers.fr** → **Connexion** → **Portail client**
2. En haut à droite, clique sur le **sélecteur de compte** (ton numéro de compte actuel)
3. La liste déroulante montre tes comptes. Celui qui commence par **DU** est le compte simulation.

**Note-le.** C'est cet identifiant-là que tu saisiras dans TWS, pas ton identifiant habituel. Le mot de passe est le même que celui de ton compte réel.

> Si aucun compte `DU` n'apparaît, cherche **`Paper Trading`** dans la loupe et active-le — il n'a jamais été créé.

### 1.2 — Vérifier le partage des données de marché

**C'est l'étape critique.** Un compte paper ne reçoit **pas** automatiquement les données du compte réel. Sans partage : TWS se connecte, le pont tourne, l'interface s'ouvre — et tu ne reçois que du différé de 15 minutes. Tout a l'air de marcher et rien n'est exploitable.

1. Dans la loupe, cherche **`Paper Trading`**
2. Ouvre la page de configuration du compte simulation
3. Repère la case **« Partager les données de marché avec le compte Paper Trading »** (*Share market data with paper trading account*)
4. Si elle est décochée : **coche-la**, puis valide

**Compte dix minutes de propagation**, et redémarre TWS après.

### 1.3 — Vérifier que tu as bien une souscription Forex

1. Dans la loupe, cherche **`Données de marché`** (ou *Market Data Subscriptions*)
2. Regarde la liste de tes souscriptions actives
3. Il te faut une ligne qui couvre le change au comptant — selon les cas : **Spot FX**, **Cash Forex**, ou une offre incluant **IDEALPRO**

Si tu n'en as aucune, souscris-la depuis cette même page. C'est facturé quelques euros par mois, et sans elle il n'y a rien à mesurer.

> **Le doute se lève tout seul.** Tu n'as pas besoin de deviner : le script de la Partie 2.4 te dira si les données arrivent, à quelle fraîcheur, et sur combien de paires. Si tu vois `8/8 paires` et une fraîcheur sous la seconde, c'est bon.

### 1.4 — Régler le solde à 1 000 $ *(facultatif)*

Dans la loupe : **`Paper Trading`** → **Réinitialiser le solde** → saisis `1000`.

> **Ça ne change rien aux calculs de Kairos.** Le pont ne passe aucun ordre, donc le solde n'entre dans aucune formule. Ce qui compte est le paramètre `--notionnel 1000` de la Partie 3 — et lui a un effet considérable, détaillé plus bas.

---

# PARTIE 2 — TWS

### 2.1 — Installer

```bash
brew install --cask ibkr-trader-workstation
```

Si macOS refuse de l'ouvrir : **Réglages Système** → **Confidentialité et sécurité** → descendre tout en bas → **Ouvrir quand même**.

### 2.2 — Se connecter

- **Nom d'utilisateur :** celui qui commence par **DU**
- **Mot de passe :** le tien
- Vérifie que la mention **Paper Trading** apparaît (souvent en jaune)

### 2.3 — Activer l'API

Menu du haut : **File** → **Global Configuration…**
Dans l'arbre de gauche : déplie **API** → clique **Settings**

Règle exactement ceci :

| Champ | Valeur |
|---|---|
| **Enable ActiveX and Socket Clients** | ☑ coché |
| **Read-Only API** | ☑ **coché** |
| **Socket port** | **7497** |
| **Allow connections from localhost only** | ☑ coché |
| **Trusted IPs** | `127.0.0.1` |
| Master API client ID | *laisser vide* |

Puis **Apply**, puis **OK**.

**Laisse TWS ouvert** pendant toute la session.

> Les quatre ports, à ne jamais confondre : **7497** TWS simulation · 7496 TWS réel · **4002** Gateway simulation · 4001 Gateway réel.

### 2.4 — Vérifier la connexion

```bash
cd ~/Documents/kairos-projet
source .venv/bin/activate
python scripts/paper_test.py --port 7497
```

Le script écoute vingt secondes et contrôle dix points : port ouvert, compte en `DU`, 8 paires reçues, latence plausible, niveaux cohérents, et **EUR/JPY concorde avec EUR/USD × USD/JPY**.

**Ne continue que si tout est vert.**

---

# PARTIE 3 — Lancer Kairos

```bash
cd ~/Documents/kairos-projet
source .venv/bin/activate
python app.py --source ibkr --port 7497 --notionnel 1000
```

Une fenêtre s'ouvre sur la liste de diagnostic. Elle se rafraîchit toutes les deux secondes. Quand les lignes essentielles sont vertes, le bouton **LANCER L'ALGORITHME** s'active.

Depuis le Finder, tu peux aussi **double-cliquer sur `Kairos.command`**.

**Ctrl + C** dans le Terminal arrête tout, pont compris.

### Ce que tu vas voir

Le compteur **Boucles** montera vite. Le compteur **Ordres** restera à zéro.

**Ce n'est pas une panne.** À 1 000 $ de notionnel, le plancher de commission de 2 $ pèse **20 bps par jambe** — cent fois le tarif affiché. Une boucle à 3 jambes coûte **60 bps** quand le marché en offre **0,46**.

| Notionnel | Coût 3 jambes | Face aux 0,46 bps disponibles |
|---:|---:|---:|
| **1 000 $** | **60,00 bps** | **130×** |
| 10 000 $ | 6,00 bps | 13× |
| 100 000 $ | 0,60 bps | 1,3× |

Le système regarde des milliers de boucles et n'en retient aucune parce qu'aucune ne couvre ses frais. C'est le verdict du projet, confirmé sur tes propres données.

### Exporter

Bouton **EXPORTER CSV** en haut à droite : 20 colonnes, point-virgule, UTF-8 avec BOM — Excel français l'ouvre directement.

Le pont écrit aussi, en continu, dans `journal/` : un fichier d'ordres par jour et un résumé quotidien cumulatif.

---

# PARTIE 4 — GitHub

### 4.1 — Git est-il installé ?

```bash
git --version
```

- Si tu vois un numéro de version → passe à 4.2
- Si macOS ouvre une fenêtre **« Installer les outils de développement en ligne de commande »** → clique **Installer**, attends, puis relance la commande

### 4.2 — Ton identité

```bash
git config --global user.name "Adam Mac"
git config --global user.email "adam.macmc@gmail.com"
```

### 4.3 — Créer le dépôt local

```bash
cd ~/Documents/kairos-projet
git init
git branch -M main
```

### 4.4 — Vérifier ce qui va partir

**Fais-le avant le premier commit.** C'est le seul moment où une erreur coûte encore zéro.

```bash
git status --short
```

Tu dois voir environ 88 fichiers. **Tu ne dois PAS voir** : `.venv`, `data/`, `journal/`, `.env`, `kairos-live.json`, `.DS_Store`.

S'ils apparaissent, arrête-toi et dis-le-moi.

### 4.5 — Premier commit

```bash
git add .
git commit -m "Kairos — détecteur d'arbitrage, backtest C++, pont IBKR"
```

### 4.6 — Créer le dépôt sur GitHub

1. Va sur **github.com**, connecte-toi
2. En haut à droite, clique le **`+`** → **New repository**
3. **Repository name :** `kairos`
4. **Description :** *Système de détection de dislocations de prix* (facultatif)
5. Choisis **Private** — c'est ton travail, et il contient ta stratégie
6. **NE COCHE RIEN** dans « Initialize this repository » : ni README, ni .gitignore, ni licence. Tu les as déjà, et les cocher créerait un conflit au premier push.
7. Clique **Create repository**

### 4.7 — La clé SSH

GitHub n'accepte plus les mots de passe. La clé SSH est la méthode la plus simple à long terme : tu la crées une fois, tu n'y penses plus.

```bash
ssh-keygen -t ed25519 -C "adam.macmc@gmail.com"
```

Trois questions :

- **Enter file in which to save the key** → appuie **Entrée** (accepte le défaut)
- **Enter passphrase** → appuie **Entrée** (vide, plus simple)
- **Enter same passphrase again** → **Entrée**

Puis copie la clé publique dans le presse-papier :

```bash
pbcopy < ~/.ssh/id_ed25519.pub
```

Sur GitHub :

1. Clique ta **photo de profil** en haut à droite → **Settings**
2. Dans le menu de gauche → **SSH and GPG keys**
3. Bouton vert **New SSH key**
4. **Title :** `MacBook Adam`
5. **Key type :** `Authentication Key`
6. **Key :** colle avec **⌘ + V**
7. **Add SSH key**

Vérifie :

```bash
ssh -T git@github.com
```

Réponds `yes` à la question de confiance. Tu dois lire : *Hi adamamri! You've successfully authenticated…*

### 4.8 — Envoyer

Remplace `TON-PSEUDO` par ton identifiant GitHub :

```bash
git remote add origin git@github.com:TON-PSEUDO/kairos.git
git push -u origin main
```

Recharge la page GitHub : ton code y est.

### 4.9 — Les fois suivantes

```bash
git add .
git commit -m "ce que j'ai changé"
git push
```

---

# Le mémo quotidien

```bash
cd ~/Documents/kairos-projet
source .venv/bin/activate                              # INDISPENSABLE
python app.py --source ibkr --port 7497 --notionnel 1000
```

Si une commande échoue avec `ModuleNotFoundError`, c'est presque toujours la ligne 2 oubliée. Vérifie que ton invite commence bien par `(.venv)`.

---

# En cas de blocage

```bash
python scripts/doctor.py
```

Il vérifie, dans l'ordre où les problèmes surviennent : version de Python, environnement virtuel, dossier courant, dépôt git, fichiers attendus, dépendances, import du projet. Chaque échec affiche sa correction.

Envoie-moi sa sortie complète si quelque chose résiste.

---

*Le pont est en lecture seule par construction : aucun ordre ne peut être transmis, sur aucun compte. Ce document ne constitue pas un conseil en investissement.*
