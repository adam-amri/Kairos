"""Types d'ordres et d'executions."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"

    @property
    def sign(self) -> int:
        return 1 if self is Side.BUY else -1


class OrderType(str, Enum):
    MARKET = "market"   # franchit le spread, execution immediate, on paie le taker
    LIMIT = "limit"     # passif, on attend dans la file, on encaisse le maker


class OrderStatus(str, Enum):
    PENDING = "pending"      # emis, pas encore arrive chez le venue (latence)
    RESTING = "resting"      # actif dans le carnet
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


@dataclass
class Order:
    id: int
    side: Side
    qty: float
    type: OrderType = OrderType.LIMIT
    price: float | None = None          # None uniquement pour un MARKET

    # Identifiant choisi par la STRATEGIE. C'est lui que visent les annulations.
    # Une strategie ne peut pas connaitre l'identifiant attribue par le venue au
    # moment ou elle decide : referencer cet identifiant-la est impossible en reel.
    # C'est aussi le support de l'idempotence a la reconnexion : un client_id
    # deterministe empeche de dupliquer un ordre deja transmis.
    client_id: int = 0

    ts_created_ns: int = 0              # decision de la strategie
    ts_arrive_ns: int = 0               # arrivee chez le venue = created + latence
    status: OrderStatus = OrderStatus.PENDING

    filled_qty: float = 0.0
    avg_fill_price: float = 0.0

    # File d'attente : volume affiche devant nous au moment de l'entree dans la file.
    # Tant qu'il n'est pas consomme, aucune execution passive n'est possible.
    queue_ahead: float = 0.0
    joined_queue: bool = False

    def __post_init__(self) -> None:
        if self.type is OrderType.LIMIT and self.price is None:
            raise ValueError("un ordre LIMIT exige un prix")
        if self.qty <= 0:
            raise ValueError("qty doit etre strictement positive")

    @property
    def remaining(self) -> float:
        return self.qty - self.filled_qty

    @property
    def is_active(self) -> bool:
        return self.status in (OrderStatus.PENDING, OrderStatus.RESTING)


@dataclass
class Fill:
    order_id: int
    side: Side
    qty: float
    price: float
    ts_ns: int
    is_maker: bool
    commission: float = 0.0

    @property
    def signed_qty(self) -> float:
        return self.qty * self.side.sign


@dataclass
class Action:
    """Ce qu'une strategie demande. Elle ne touche jamais le carnet directement."""

    kind: str                       # "submit" | "cancel"
    order: Order | None = None
    client_id: int | None = None    # cible d'une annulation
    meta: dict = field(default_factory=dict)
