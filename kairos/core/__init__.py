"""Types du domaine — partages par le backtest ET la production.

Un Order, un Fill, un Portfolio ne sont pas des objets de simulation. Ce sont les
memes en backtest et en reel, et c'est precisement ce qui permet a une strategie de
tourner sans modification dans les deux contextes.

Les avoir loges dans `backtest/` etait une erreur : cela creait une dependance
circulaire (backtest -> strategy -> backtest) et suggerait a tort que la simulation
possede ces concepts.
"""
from kairos.core.orders import Action, Fill, Order, OrderStatus, OrderType, Side
from kairos.core.portfolio import Portfolio

__all__ = ["Action", "Fill", "Order", "OrderStatus", "OrderType", "Side", "Portfolio"]
