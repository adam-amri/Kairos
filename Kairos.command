#!/bin/bash
# Double-cliquable depuis le Finder.
# Rendre executable une seule fois :  chmod +x Kairos.command
cd "$(dirname "$0")"
if [ -d .venv ]; then source .venv/bin/activate; fi
exec python3 app.py --source ibkr --port 7497 --notionnel 1000
