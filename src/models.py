"""Data models for strategy testing."""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
import time
import uuid


class StrategyType(Enum):
    """Trading strategy types."""
    UNDERVALUED = "undervalued"  # Buy when price <= threshold
    MOMENTUM = "momentum"        # Buy when price >= threshold


class Outcome(Enum):
    """Market outcome."""
    UP = "Up"
    DOWN = "Down"


class OrderStatus(Enum):
    """Order status."""
    PENDING = "pending"      # Waiting to be placed
    OPEN = "open"           # Placed, waiting for fill
    FILLED = "filled"       # Completely filled
    CANCELLED = "cancelled" # Cancelled before fill
    EXPIRED = "expired"     # Market resolved without fill


class TradeResult(Enum):
    """Trade outcome result."""
    WIN = "win"
    LOSS = "loss"
    PENDING = "pending"


@dataclass
class MarketWindow:
    """A 15-minute market window."""
    slug: str
    condition_id: str
    up_token_id: str
    down_token_id: str
    start_time: int      # Unix timestamp when market becomes active
    end_time: int        # Unix timestamp when market resolves
    winner: Optional[Outcome] = None  # Resolved outcome (UP/DOWN)
    
    def countdown_to_active(self) -> int:
        """Seconds until market becomes active."""
        return max(0, self.start_time - int(time.time()))
    
    def countdown_to_end(self) -> int:
        """Seconds until market resolves."""
        return max(0, self.end_time - int(time.time()))
    
    def is_in_entry_window(self, entry_countdown: int) -> bool:
        """Check if we're in the entry window (countdown <= entry_countdown)."""
        return self.countdown_to_active() <= entry_countdown
    
    def is_past_exit_point(self, exit_countdown: int) -> bool:
        """Check if we've passed the exit point (countdown <= exit_countdown)."""
        return self.countdown_to_active() <= exit_countdown
    
    def to_dict(self) -> dict:
        return {
            "slug": self.slug,
            "condition_id": self.condition_id,
            "up_token_id": self.up_token_id,
            "down_token_id": self.down_token_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "countdown_to_active": self.countdown_to_active(),
            "countdown_to_end": self.countdown_to_end(),
        }


@dataclass
class PaperOrder:
    """A paper trading order."""
    id: str
    strategy: StrategyType
    market_slug: str
    outcome: Outcome
    price: float
    size: float
    status: OrderStatus = OrderStatus.PENDING
    filled_size: float = 0.0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    
    @classmethod
    def create(cls, strategy: StrategyType, market_slug: str, 
               outcome: Outcome, price: float, size: float) -> "PaperOrder":
        return cls(
            id=str(uuid.uuid4()),
            strategy=strategy,
            market_slug=market_slug,
            outcome=outcome,
            price=price,
            size=size,
        )
    
    def fill(self, size: float) -> None:
        """Fill the order (fully or partially)."""
        self.filled_size = min(self.size, self.filled_size + size)
        if self.filled_size >= self.size:
            self.status = OrderStatus.FILLED
        self.updated_at = time.time()
    
    def cancel(self) -> None:
        """Cancel the order."""
        self.status = OrderStatus.CANCELLED
        self.updated_at = time.time()
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "strategy": self.strategy.value,
            "market_slug": self.market_slug,
            "outcome": self.outcome.value,
            "price": self.price,
            "size": self.size,
            "status": self.status.value,
            "filled_size": self.filled_size,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass  
class Trade:
    """A completed trade with resolution."""
    id: str
    strategy: StrategyType
    market_slug: str
    outcome: Outcome
    entry_price: float
    size: float
    entry_time: float
    filled_size: float = 0.0  # Track partial fills
    resolution_time: Optional[float] = None
    result: TradeResult = TradeResult.PENDING
    pnl: float = 0.0
    
    @classmethod
    def from_order(cls, order: PaperOrder) -> "Trade":
        """Create a trade from a filled order."""
        return cls(
            id=str(uuid.uuid4()),
            strategy=order.strategy,
            market_slug=order.market_slug,
            outcome=order.outcome,
            entry_price=order.price,
            size=order.size,
            filled_size=order.filled_size,  # Track how much was filled
            entry_time=order.updated_at,     # Use fill time, not order creation time
        )
    
    def resolve(self, winning_outcome: Outcome) -> None:
        """Resolve the trade with the winning outcome."""
        self.resolution_time = time.time()
        if self.outcome == winning_outcome:
            # Win: get $1.00 per share
            self.pnl = self.size * (1.0 - self.entry_price)
            self.result = TradeResult.WIN
        else:
            # Loss: lose entry cost
            self.pnl = -self.size * self.entry_price
            self.result = TradeResult.LOSS
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "strategy": self.strategy.value,
            "market_slug": self.market_slug,
            "outcome": self.outcome.value,
            "entry_price": self.entry_price,
            "size": self.size,
            "filled_size": self.filled_size,
            "entry_time": self.entry_time,
            "resolution_time": self.resolution_time,
            "result": self.result.value,
            "pnl": self.pnl,
        }


@dataclass
class StrategyMetrics:
    """Aggregated metrics for a strategy."""
    strategy: StrategyType
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    pending: int = 0
    total_pnl: float = 0.0
    total_invested: float = 0.0
    
    @property
    def win_rate(self) -> float:
        """Win rate as a percentage."""
        completed = self.wins + self.losses
        return (self.wins / completed * 100) if completed > 0 else 0.0
    
    @property
    def roi(self) -> float:
        """Return on investment as a percentage."""
        return (self.total_pnl / self.total_invested * 100) if self.total_invested > 0 else 0.0
    
    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy.value,
            "total_trades": self.total_trades,
            "wins": self.wins,
            "losses": self.losses,
            "pending": self.pending,
            "win_rate": round(self.win_rate, 1),
            "total_pnl": round(self.total_pnl, 2),
            "total_invested": round(self.total_invested, 2),
            "roi": round(self.roi, 1),
        }
