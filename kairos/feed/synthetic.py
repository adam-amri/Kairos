"""Feed synthetique — permet de valider tout le pipeline sans compte broker.

Le generateur construit EUR/USD et USD/JPY par marche aleatoire, puis derive
EUR/JPY de la relation de non-arbitrage a laquelle on ajoute un bruit CONNU.
L'analyseur doit retrouver ce bruit. S'il ne le retrouve pas, le bug est dans
l'analyseur, pas dans le marche — et on l'apprend avant d'avoir risque un euro.
"""
from __future__ import annotations
import random
import time
from typing import Iterator

from kairos.clock import wall_ns
from kairos.events import Quote
from kairos.feed.base import Feed


class SyntheticFeed(Feed):
    name = "synthetic"

    def __init__(
        self,
        duration_s: int = 60,
        ticks_per_s: int = 20,
        noise_bps: float = 0.8,
        spread_bps: float = 0.28,
        seed: int = 42,
        realtime: bool = False,
        start_ns: int | None = None,
    ) -> None:
        self.duration_s = duration_s
        self.ticks_per_s = ticks_per_s
        self.noise_bps = noise_bps
        self.spread_bps = spread_bps
        self.realtime = realtime
        self.start_ns = start_ns
        self.rng = random.Random(seed)

    def _quote(self, symbol: str, mid: float, venue_ns: int, recv_ns: int) -> Quote:
        half = mid * self.spread_bps / 2 / 10_000
        return Quote(
            venue=self.name,
            symbol=symbol,
            bid=mid - half,
            ask=mid + half,
            bid_size=1_000_000,
            ask_size=1_000_000,
            ts_venue_ns=venue_ns,
            ts_wall_ns=recv_ns,
            ts_mono_ns=recv_ns,
        )

    def stream(self) -> Iterator[Quote]:
        eurusd, usdjpy = 1.0800, 157.00
        n = self.duration_s * self.ticks_per_s
        dt = 1.0 / self.ticks_per_s
        dt_ns = int(1e9 / self.ticks_per_s)

        # HORLOGE SIMULEE, et c'est essentiel.
        # Horodater avec l'heure reelle de generation comprimerait 60 secondes de
        # marche dans les quelques millisecondes que met la boucle a tourner. Toute
        # latence modelisee depasserait alors la duree totale du jeu de donnees et
        # aucun ordre n'arriverait jamais : le backtest afficherait zero execution
        # sans la moindre erreur. Le temps simule doit avancer par pas de dt.
        t0 = self.start_ns if self.start_ns is not None else wall_ns()

        for i in range(n):
            # Marche aleatoire sur les deux jambes independantes
            eurusd *= 1 + self.rng.gauss(0, 0.00003)
            usdjpy *= 1 + self.rng.gauss(0, 0.00003)

            # La croisee derive de la parite, plus un bruit d'amplitude connue
            noise = self.rng.gauss(0, self.noise_bps / 10_000)
            eurjpy = eurusd * usdjpy * (1 + noise)

            venue_ns = t0 + i * dt_ns
            recv_ns = venue_ns + self.rng.randint(200_000, 2_000_000)  # 0,2-2 ms de transport

            yield self._quote("EUR/USD", eurusd, venue_ns, recv_ns)
            yield self._quote("USD/JPY", usdjpy, venue_ns, recv_ns)
            yield self._quote("EUR/JPY", eurjpy, venue_ns, recv_ns)

            if self.realtime:
                time.sleep(dt)
