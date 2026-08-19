"""Connecteur IBKR via ib_async.

Prerequis : IB Gateway ou TWS lance, API activee, port coherent avec config.yaml.

Limites d'IBKR a connaitre AVANT de deboguer :
  - 100 lignes de donnees de marche simultanees par defaut
  - pacing a ~50 messages/seconde, au-dela le flux est etrangle sans erreur claire
  - le flux standard n'est PAS du tick-by-tick : ce sont des snapshots agreges
    (~250 ms). D'ou reqTickByTickData ci-dessous, indispensable pour toute mesure
    de microstructure serieuse.
  - le Gateway impose un redemarrage quotidien (voir README, section exploitation)
"""
from __future__ import annotations
import queue
from typing import Iterator

from kairos.clock import mono_ns, wall_ns
from kairos.events import Quote
from kairos.feed.base import Feed


class IBKRFeed(Feed):
    name = "ibkr"

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 4002,
        client_id: int = 17,
        pairs: list | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.client_id = client_id
        self.pairs = [tuple(p) for p in (pairs or [("EUR", "USD"), ("USD", "JPY"), ("EUR", "JPY")])]
        self._q: "queue.Queue[Quote]" = queue.Queue()

    def stream(self) -> Iterator[Quote]:
        from ib_async import IB, Forex   # import ici : le module reste importable sans ib_async

        ib = IB()
        ib.connect(self.host, self.port, clientId=self.client_id)

        contracts = {}
        for base, quote in self.pairs:
            c = Forex(f"{base}{quote}")
            ib.qualifyContracts(c)
            symbol = f"{base}/{quote}"
            contracts[c.conId] = symbol
            # BidAsk en tick-by-tick : la seule voie vers un horodatage exploitable
            ib.reqTickByTickData(c, "BidAsk", 0, False)

        def on_tick(ticks, has_new: bool) -> None:
            for t in ticks:
                symbol = contracts.get(t.contract.conId)
                if symbol is None:
                    continue
                self._q.put(
                    Quote(
                        venue=self.name,
                        symbol=symbol,
                        bid=float(t.bidPrice),
                        ask=float(t.askPrice),
                        bid_size=float(t.bidSize or 0),
                        ask_size=float(t.askSize or 0),
                        ts_venue_ns=int(t.time.timestamp() * 1e9) if t.time else 0,
                        ts_wall_ns=wall_ns(),
                        ts_mono_ns=mono_ns(),
                    )
                )

        ib.tickByTickBidAskEvent += on_tick

        try:
            while True:
                ib.sleep(0.01)          # laisse tourner la boucle asyncio d'ib_async
                while not self._q.empty():
                    yield self._q.get_nowait()
        except KeyboardInterrupt:
            pass
        finally:
            ib.disconnect()
