#!/usr/bin/env python3
"""Stress test du cash and carry — chiffre le risque que le classeur ne chiffre pas.

    python scripts/stress_carry.py

Repond a trois questions :
  1. Quel mouvement de prix liquide la jambe short, selon le levier ?
  2. Que change la marge isolee par rapport a la marge croisee ?
  3. Que coute un regime de funding negatif ?
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kairos.backtest.carry import (
    CarryConfig, CarrySimulator, chemin_choc, funding_regulier,
)
from kairos.core.funding import FundingEvent

TS0 = 1_700_000_000_000_000_000
P0 = 100.0
CAPITAL = 10_000.0
JOURS = 90


def titre(t: str) -> None:
    print(f"\n{'=' * 74}\n{t}\n{'=' * 74}")


# ---------------------------------------------------------------- 1
titre("1. QUEL MOUVEMENT DE PRIX LIQUIDE LA JAMBE SHORT ?  (marge isolee)")
print(f"{'Levier':>8} {'Marge/notionnel':>17} {'Prix liq.':>11} {'Hausse requise':>16} {'Contexte':>14}")
for lev, ctx in [(2.0, "UE retail"), (3.0, ""), (5.0, "offshore"),
                 (10.0, "offshore"), (20.0, "offshore")]:
    sim = CarrySimulator(CarryConfig(max_leverage=lev))
    pl = sim.prix_de_liquidation(P0)
    print(f"{lev:>7.0f}x {1/lev:>16.1%} {pl:>11.2f} {(pl/P0 - 1):>15.1%} {ctx:>14}")

print("\nLecture : le plafond europeen de 2:1 coute un tiers d'efficience du capital,")
print("mais il exige une hausse de pres de 50 % pour liquider. La contrainte")
print("reglementaire est un ARBITRAGE, pas une perte seche.")

# ---------------------------------------------------------------- 2
titre("2. MARGE ISOLEE CONTRE MARGE CROISEE  (choc de prix au jour 30)")
funding = funding_regulier(TS0, JOURS, rate_bps=1.0, mark=P0)
print(f"{'Choc':>8} {'Levier':>7} {'Isolee':>22} {'Croisee':>22}")
for choc in (0.10, 0.25, 0.45, 0.55, 0.80):
    for lev in (2.0, 5.0):
        prices = chemin_choc(TS0, JOURS, P0, choc, jour_du_choc=30)
        out = []
        for iso in (True, False):
            r = CarrySimulator(CarryConfig(max_leverage=lev, isolated_margin=iso)) \
                .run(prices, funding, capital=CAPITAL)
            out.append("LIQUIDE" if r.liquide else f"net {r.net_sur_capital_bps:+7.1f} bps")
        print(f"{choc:>7.0%} {lev:>6.0f}x {out[0]:>22} {out[1]:>22}")

print("\nLecture : a levier egal, la marge CROISEE survit a des chocs qui liquident")
print("la marge isolee. La position est pourtant identique et son risque net est nul :")
print("la plus-value du spot compense exactement la perte du perpetuel. C'est un")
print("risque de PLOMBERIE — les deux jambes vivent sur des comptes separes.")

# ---------------------------------------------------------------- 3
titre("3. LE COUT D'UN REGIME DE FUNDING NEGATIF")
prices = [(TS0 + int(i * 86_400e9 / 24), P0) for i in range(JOURS * 24)]
print(f"{'Regime':>15} {'Funding':>10} {'Percu':>10} {'Frais':>8} {'Net capital':>13} {'Annualise':>11}")
for taux, label in [(2.0, "haussier"), (1.0, "median"), (0.3, "faible"),
                    (0.0, "neutre"), (-0.5, "baissier"), (-1.0, "tres baissier")]:
    f = funding_regulier(TS0, JOURS, rate_bps=taux, mark=P0)
    r = CarrySimulator(CarryConfig()).run(prices, f, capital=CAPITAL)
    print(f"{label:>15} {taux:>7.1f}bps {r.funding_recu_bps:>9.1f} "
          f"{r.frais_totaux_bps:>7.1f} {r.net_sur_capital_bps:>12.1f} {r.net_annualise:>10.2%}")

# Seuil de bascule, CALCULE par recherche binaire plutot qu'affirme
bas, haut = -2.0, 2.0
for _ in range(60):
    mid = (bas + haut) / 2
    f = funding_regulier(TS0, JOURS, rate_bps=mid, mark=P0)
    r = CarrySimulator(CarryConfig()).run(prices, f, capital=CAPITAL)
    if r.net_sur_capital_bps < 0:
        bas = mid
    else:
        haut = mid
seuil = (bas + haut) / 2
print(f"\nSEUIL DE BASCULE CALCULE : {seuil:.4f} bps par periode "
      f"(soit {seuil * 3 * 365 / 100:.2f} %/an de funding brut)")
print("En dessous, la position perd de l'argent SANS AUCUN choc de prix.")
print("Le rendement de 5,84 % du classeur suppose 1,0 bps constant — hypothese forte,")
print(f"mais la marge de securite est reelle : {1.0 / seuil:.1f}x le seuil.")

# ---------------------------------------------------------------- 4
titre("4. SCENARIO COMBINE : funding qui se degrade PUIS choc de prix")
f_degrade = []
pas = int(86_400e9 / 3)
for i in range(JOURS * 3):
    jour = i / 3
    taux = 1.5 if jour < 30 else (0.5 if jour < 60 else -0.8)
    f_degrade.append(FundingEvent(ts_ns=TS0 + (i + 1) * pas, rate_bps=taux, mark_price=P0))

for choc, jour_choc in [(0.0, 999), (0.30, 70), (0.50, 70), (0.75, 70), (1.20, 70)]:
    prices = (chemin_choc(TS0, JOURS, P0, choc, jour_choc) if choc
              else [(TS0 + int(i * 86_400e9 / 24), P0) for i in range(JOURS * 24)])
    r = CarrySimulator(CarryConfig()).run(prices, f_degrade, capital=CAPITAL)
    etat = "LIQUIDE" if r.liquide else "tenu"
    print(f"  choc {choc:>4.0%} -> {etat:>8} | funding {r.funding_recu_bps:>7.1f} bps "
          f"({r.funding_negatifs} periodes negatives) | net capital "
          f"{r.net_sur_capital_bps:>7.1f} bps | {r.net_annualise:>7.2%}")

print("\nLe funding accumule agit comme MARGE SUPPLEMENTAIRE : une position ancienne")
print("et beneficiaire resiste a des chocs qui liquideraient une position recente.")

print("\n" + "=" * 74)
print("CONCLUSION")
print("=" * 74)
print("La liquidation n'est PAS le risque dominant sous plafond europeen de 2:1 :")
print("il faut une hausse de pres de 50 %. Le plafond qui coute un tiers")
print("d'efficience du capital achete en echange une resistance considerable.")
print()
print("Le risque dominant est le FUNDING NEGATIF. Il erode le rendement sans aucun")
print("evenement spectaculaire, ne declenche aucune alerte, et c'est precisement")
print("pour cela qu'il passe inapercu. C'est aussi ce qui fait de la prevision du")
print("regime de funding la meilleure cible de machine learning du projet.")
