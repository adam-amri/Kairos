from kairos.feed.base import Feed
from kairos.feed.synthetic import SyntheticFeed

__all__ = ["Feed", "SyntheticFeed", "make_feed"]


def make_feed(cfg: dict) -> Feed:
    venue = cfg.get("venue", "synthetic")
    if venue == "synthetic":
        return SyntheticFeed(**cfg.get("synthetic", {}))
    if venue == "ibkr":
        from kairos.feed.ibkr import IBKRFeed   # import tardif : ib_async optionnel
        return IBKRFeed(**cfg.get("ibkr", {}))
    raise ValueError(f"venue inconnu : {venue}")
