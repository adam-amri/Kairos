# Kairos — connecter TWS et monter le Raspberry Pi

*De A à Z, pour quelqu'un qui ne connaît ni l'un ni l'autre*

---

# Partie 1 — Le compte simulation IBKR

## 1.1 Ce que la simulation prouve, et ce qu'elle ne prouve pas

Avant de brancher quoi que ce soit, une mise au point qui change la façon de lire les résultats.

**Le paper trading d'IBKR remplit les ordres de façon optimiste.** Il ne modélise ni la position dans la file d'attente, ni la sélection adverse. Sur une stratégie de capture de spread, un résultat brillant en simulation est donc un **signal d'erreur**, pas une bonne nouvelle.

Ce que la simulation valide réellement, et c'est déjà beaucoup :

- La **plomberie** — reconnexion, doublons d'ordres, désynchronisation d'état
- Les **conventions de cotation** — celles qui produisent les +6 167 bps fictifs
- La **fraîcheur des données** et ta latence réelle
- Le fait que le système tourne **des jours sans intervention**

**Ce que le modèle prédit :** zéro opportunité nette. Sur le graphe de test à 8 paires, les 14 boucles sont toutes négatives, la meilleure à **−6,44 bps**. Si le pont affiche zéro, ce n'est pas une panne — **c'est le verdict, confirmé sur tes données**. Et un chiffre que tu as mesuré toi-même vaut infiniment plus qu'un chiffre reçu.

## 1.2 Ouvrir le compte

1. Compte IBKR ouvert et financé (les données de marché et le paper trading fonctionnent sous 25 000 $ ; seul l'accès IDEALPRO est conditionné à ce seuil).
2. Dans le portail client : **Paramètres → Compte → Compte Paper Trading**. IBKR crée un second identifiant, distinct du réel.
3. Souscrire les données FX. Sans souscription, tu ne reçois que des données différées — inutilisables pour toute mesure de microstructure.

> Le compte paper reçoit les mêmes données de marché que le réel, mais **seulement si la souscription est partagée**. Dans le portail : **Données de marché → Partager avec le compte paper**.

## 1.3 Installer TWS ou IB Gateway

Deux logiciels, même API.

| | TWS | IB Gateway |
|---|---|---|
| Interface graphique | Complète | Minimale |
| Mémoire | ~1,5 Go | ~400 Mo |
| Usage | Débuter, voir ce qui se passe | Tourner 24/7 |

**Commence par TWS** — voir les prix bouger aide à comprendre. **Passe au Gateway** pour le Raspberry.

Sur Mac :

```bash
brew install --cask ibkr-trader-workstation
```

Si macOS refuse de l'ouvrir : **Réglages Système → Confidentialité et sécurité → Ouvrir quand même**.

## 1.4 Activer l'API — l'étape que tout le monde rate

Dans TWS : **File → Global Configuration → API → Settings**.

| Réglage | Valeur | Pourquoi |
|---|---|---|
| Enable ActiveX and Socket Clients | ✅ coché | Sans cela, aucune connexion |
| **Read-Only API** | ✅ **coché** | Le broker refuse tout ordre, quoi qu'envoie le code |
| Socket port | **7497** | Port du compte paper |
| Trusted IPs | `127.0.0.1` | Et l'IP du Pi si tu le connectes |
| Allow connections from localhost only | décoché si le Pi se connecte | — |

**Coche « Read-Only API ».** Le pont ne contient aucun code de passage d'ordre — c'est vérifié par un test qui inspecte l'arbre syntaxique. Mais cette case ajoute une seconde barrière, côté broker cette fois. Deux garde-fous indépendants valent mieux qu'un seul, aussi solide soit-il.

**Les quatre ports, à ne jamais confondre :**

| Port | Logiciel | Compte |
|---:|---|---|
| **7497** | TWS | **Simulation** ← celui-ci |
| 7496 | TWS | Réel |
| **4002** | Gateway | **Simulation** |
| 4001 | Gateway | Réel |

Le pont affiche un avertissement si tu passes 7496 ou 4001.

## 1.5 Lancer le pont

```bash
cd ~/Documents/kairos-projet
source .venv/bin/activate

# 1. Sans TWS, pour vérifier que la chaîne fonctionne
python bridge/live_bridge.py --source demo --out dashboard/kairos-live.json

# 2. Avec TWS paper lancé
python bridge/live_bridge.py --source ibkr --port 7497 \
       --out dashboard/kairos-live.json
```

Puis ouvre `dashboard/kairos.html`. Il bascule tout seul en direct.

## 1.6 Vérifier que les chiffres sont bons

Trois contrôles, dans cet ordre.

**La fraîcheur.** `fraicheur_ms` doit rester sous ~1 000 ms. Au-delà, le flux est étranglé — souvent le pacing IBKR (~50 messages/seconde).

**Les conventions.** Une déviation à trois ou quatre chiffres en bps n'est jamais une opportunité : c'est une paire mal orientée. Le détecteur résout les sens correctement, mais si tu ajoutes une paire exotique, vérifie ce point en premier.

**Le compte des boucles.** 8 paires sur 6 devises donnent 14 boucles. Si tu en vois 0, le graphe est déconnecté : il manque une paire pivot.

## 1.7 La collecte de Phase 1

C'est le vrai livrable.

```bash
python bridge/live_bridge.py --source ibkr --port 7497 \
       --store data/phase1 --serve 8765
```

Laisse tourner **cinq jours de bourse**. Le FX cote du dimanche 23 h au vendredi 22 h. Chaque interruption fait un trou, et un histogramme troué est un verdict faussé — c'est exactement pourquoi le Raspberry a un rôle.

---

# Partie 2 — Le Raspberry Pi, de A à Z

## 2.1 À quoi il sert ici, et pourquoi ce n'est pas gadget

**Rôle 1, maintenant : collecteur permanent.** Le FX cote 24 h sur 5 jours. Un Mac qui se met en veille crée des trous. Le Pi consomme ~5 W et ne s'éteint jamais. **Il n'améliore pas le P&L d'un centime** — il garantit que l'histogramme est complet.

**Rôle 2, plus tard : watchdog indépendant.** Le coupe-circuit ne doit jamais tourner sur la machine qu'il coupe. Si le PC gèle ou perd le réseau, un garde-fou hébergé dessus gèle avec lui. Le Pi a son matériel, son réseau, son alimentation : il reste vivant précisément dans les pannes graves.

## 2.2 Ce qu'il faut acheter

| Élément | Choix | Pourquoi |
|---|---|---|
| **Raspberry Pi 5, 4 Go** | ~80 € | 8 Go inutile ici |
| **Alimentation officielle 27 W USB-C** | ~15 € | Une alim tierce sous-dimensionnée provoque des redémarrages aléatoires — panne pénible à diagnostiquer |
| **SSD USB 128 Go** | ~25 € | ⚠️ **Pas de carte SD** |
| Boîtier avec ventilateur | ~15 € | Le Pi 5 throttle sous charge soutenue |
| Câble Ethernet | ~5 € | Le Wi-Fi décroche ; une collecte 24/7 n'aime pas ça |
| Petit onduleur USB | ~40 € | Optionnel maintenant, requis pour le rôle 2 |

**Total : ~140 €, ou ~180 € avec onduleur.**

> **Le SSD n'est pas un luxe.** Un collecteur écrit en continu. Une carte SD encaisse un nombre limité de cycles d'écriture et **meurt en quelques mois** — toujours au mauvais moment, en emportant les données. C'est la panne classique du Pi en collecte.

## 2.3 Installer le système

1. Télécharge **Raspberry Pi Imager** sur ton Mac (`raspberrypi.com/software`).
2. Branche le SSD sur le Mac via USB.
3. Dans l'Imager : **Raspberry Pi OS Lite (64-bit)** — sans bureau, inutile ici.
4. Clique la **roue dentée** avant d'écrire, et remplis :
   - Nom d'hôte : `kairos-pi`
   - Active **SSH** avec authentification par mot de passe
   - Utilisateur : `adam` + un mot de passe solide
   - Ignore le Wi-Fi si tu utilises l'Ethernet
5. Écris, puis branche le SSD sur un **port USB 3.0** du Pi (les bleus).
6. Branche l'Ethernet, puis l'alimentation.

## 2.4 S'y connecter

Depuis le Terminal du Mac :

```bash
ssh adam@kairos-pi.local
```

Si `.local` ne répond pas, trouve l'IP sur l'interface de ta box (cherche `kairos-pi`), puis `ssh adam@192.168.1.42`.

**Réserve l'adresse IP** dans ta box (« bail DHCP statique » ou « réservation »). Sans cela l'IP change au redémarrage et le dashboard perd le Pi.

## 2.5 Préparer la machine

```bash
sudo apt update && sudo apt full-upgrade -y
sudo apt install -y python3-venv python3-pip git chrony
```

**`chrony` n'est pas optionnel.** Toute mesure de latence exige une horloge fiable. Sans synchronisation, les horodatages dérivent de plusieurs secondes par jour et la mesure devient du bruit.

```bash
timedatectl                 # doit afficher « System clock synchronized: yes »
chronyc tracking            # doit montrer une dérive de quelques millisecondes
```

## 2.6 Installer Kairos

Depuis le **Mac**, copie le projet :

```bash
rsync -av --exclude '.venv' --exclude '__pycache__' --exclude 'data' \
      ~/Documents/kairos-projet/ adam@kairos-pi.local:~/kairos/
```

Puis sur le **Pi** :

```bash
cd ~/kairos
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/doctor.py         # le diagnostic doit être vert
```

## 2.7 Le faire démarrer tout seul

C'est ce qui distingue un collecteur d'une expérience.

```bash
sudo nano /etc/systemd/system/kairos-bridge.service
```

```ini
[Unit]
Description=Kairos — pont de collecte (lecture seule)
After=network-online.target chrony.service
Wants=network-online.target

[Service]
Type=simple
User=adam
WorkingDirectory=/home/adam/kairos
ExecStart=/home/adam/kairos/.venv/bin/python bridge/live_bridge.py \
          --source demo --serve 8765 --store /home/adam/kairos/data/phase1 \
          --out /home/adam/kairos/dashboard/kairos-live.json

Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

# Le pont n'écrit que dans son dossier de données.
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=/home/adam/kairos/data /home/adam/kairos/dashboard

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now kairos-bridge
systemctl status kairos-bridge
journalctl -u kairos-bridge -f        # les journaux en direct, Ctrl+C pour sortir
```

`Restart=always` relance après un plantage. `After=chrony` garantit que l'horloge est synchronisée **avant** le premier horodatage.

## 2.8 Brancher le dashboard du Mac sur le Pi

Le pont sert déjà le fichier en HTTP avec CORS. Sur le Mac, ouvre `dashboard/kairos.html` et ajoute avant le script principal :

```html
<script>window.KAIROS_URL = "http://kairos-pi.local:8765/kairos-live.json";</script>
```

Recharge : la page passe en direct, alimentée par le Pi.

## 2.9 Si TWS tourne sur le Mac

Le Pi ne peut pas héberger TWS confortablement. Deux montages :

**A — Le Pi lit TWS du Mac.** Dans TWS : **Trusted IPs → l'IP du Pi**, et décoche « localhost only ». Puis sur le Pi :

```
--source ibkr --host 192.168.1.10 --port 7497
```

Fragile : si le Mac dort, la collecte s'arrête. C'est précisément le problème qu'on cherchait à éviter.

**B — Le Pi utilise une source indépendante.** Le montage robuste : le Pi ne dépend d'aucune autre machine. C'est celui à viser pour la collecte de cinq jours.

## 2.10 Vérifier les 48 heures

```bash
# La collecte tourne-t-elle sans interruption ?
systemctl status kairos-bridge | grep Active
journalctl -u kairos-bridge --since "48 hours ago" | grep -ci "arret\|error"

# Combien de données ?
ls -la ~/kairos/data/phase1/ | wc -l
du -sh ~/kairos/data/phase1/

# Température et santé
vcgencmd measure_temp        # sous 70 °C en régime établi
df -h /                      # le SSD ne doit pas saturer
```

**Le contrôle qui compte : les trous.** Un collecteur qui redémarre proprement paraît sain dans le journal tout en ayant perdu vingt minutes. Compte les intervalles entre horodatages successifs — tout écart supérieur à quelques secondes est un trou, et cinq jours troués ne valent pas cinq jours pleins.

---

# Partie 3 — Rendre l'infrastructure vraiment efficace

## 3.1 Ne surdimensionne pas

Une stratégie de portage n'a **aucun besoin de faible latence**. Inutile de payer pour de la proximité géographique ou une machine puissante. Le Pi 5 à 4 Go traite huit paires sans transpirer.

**Le vrai goulot n'est pas la machine, c'est IBKR** : pacing à ~50 messages/seconde, 100 lignes de données simultanées par défaut. Optimiser le Pi ne déplace pas ce plafond.

## 3.2 Les trois mesures qui comptent

1. **Fraîcheur** — écart entre l'horodatage du venue et la réception. C'est ta latence réelle, et elle conditionne quelles stratégies te sont accessibles.
2. **Continuité** — pourcentage du temps de marché effectivement couvert. Vise > 99 %.
3. **Boucles examinées contre boucles retenues** — le rapport qui dit si une opportunité existe.

## 3.3 Sécurité, en cinq minutes

```bash
# Clés SSH plutôt que mot de passe — depuis le Mac
ssh-copy-id adam@kairos-pi.local

# Puis sur le Pi, désactiver le mot de passe
sudo sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
sudo systemctl restart ssh
```

**Le Pi ne doit jamais être exposé à Internet.** Il sert le fichier sur le réseau local uniquement. Si tu veux y accéder de l'extérieur, passe par un VPN — jamais par une redirection de port.

Et quand viendra le rôle 2 : **clés API avec retrait désactivé et liste blanche d'IP**. Une clé compromise sans droit de retrait coûte des trades indésirables ; avec droit de retrait, elle coûte tout.

## 3.4 L'ordre des opérations

1. Compte paper IBKR, données partagées
2. TWS installé, API activée, **Read-Only cochée**, port 7497
3. Pont testé en `--source demo` sur le Mac
4. Pont branché sur TWS paper, dashboard en direct
5. Pi commandé et monté, système sur SSD
6. Service systemd, 48 h de collecte vérifiées sans trou
7. Cinq jours de collecte
8. Histogramme et verdict chiffré

Les étapes 1 à 4 se font en une soirée. Les 5 à 8 prennent deux semaines, dont la plus grande partie est de l'attente — et c'est très bien : c'est le seul moyen d'obtenir un chiffre qui vaille quelque chose.

---

*Guide technique. Ne constitue pas un conseil en investissement. Le pont est en lecture seule par construction : aucun ordre ne peut être transmis, et un test le vérifie à chaque exécution de la CI.*
