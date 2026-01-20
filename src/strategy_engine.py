"""Strategy engine for managing dual-strategy paper trading."""
import asyncio
import time
import random
import logging
from typing import Dict, List, Optional, Set

from .config import get_config
from .models import (
    StrategyType, Outcome, OrderStatus, TradeResult,
    MarketWindow, PaperOrder, Trade, StrategyMetrics
)
from .market_tracker import get_market_tracker
from .clob_client import get_clob_client

logger = logging.getLogger(__name__)


class StrategyEngine:
    """Manages dual-strategy paper trading."""
    
    def __init__(self):
        self._config = get_config()
        self._orders: Dict[str, PaperOrder] = {}  # order_id -> order
        self._trades: List[Trade] = []
        self._processed_markets: Set[str] = set()  # Markets we've already traded
        self._running: bool = False
        self._loop_task: Optional[asyncio.Task] = None
        self._start_time: Optional[float] = None
        
    @property
    def is_running(self) -> bool:
        return self._running
    
    async def start(self) -> None:
        """Start the strategy engine."""
        if self._running:
            return
        
        self._running = True
        self._start_time = time.time()
        self._loop_task = asyncio.create_task(self._run_loop())
        logger.info("Strategy engine started")
    
    async def stop(self) -> None:
        """Stop the strategy engine."""
        self._running = False
        if self._loop_task:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
        logger.info("Strategy engine stopped")
    
    async def _run_loop(self) -> None:
        """Main trading loop."""
        tracker = get_market_tracker()
        clob = get_clob_client()
        
        while self._running:
            try:
                # Refresh market data
                await tracker.refresh()
                
                # Get t+1 market
                t1 = tracker.get_t1_market()
                if not t1:
                    await asyncio.sleep(5)
                    continue
                
                countdown = t1.countdown_to_active()
                
                logger.info(f"Loop tick: t1={t1.slug}, countdown={countdown}s, processed={t1.slug in self._processed_markets}")
                
                # Check if we should enter (within entry window and not already processed)
                # Entry window: countdown <= 20min (1200s) and market not yet active (countdown > 0)
                if (t1.slug not in self._processed_markets and 
                    countdown <= self._config.entry_countdown and
                    countdown > 0):
                    
                    await self._check_entry_conditions(t1, clob)
                
                # Check if we should exit/cancel unfilled orders
                # Note: For paper trading, we simulate fills anyway so this is for completeness
                
                # Check for resolved markets
                await self._check_resolutions(tracker)
                
                # Simulate fills for open orders
                await self._simulate_fills(clob)
                
                await asyncio.sleep(2)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in strategy loop: {e}")
                await asyncio.sleep(5)
    
    async def _check_entry_conditions(self, market: MarketWindow, clob) -> None:
        """Check if entry conditions are met for either strategy."""
        up_price, down_price = await clob.get_prices(
            market.up_token_id, 
            market.down_token_id
        )
        
        if up_price is None or down_price is None:
            logger.warning(f"No prices for {market.slug}")
            return
        
        logger.info(f"[{market.slug}] Prices: UP=${up_price:.2f}, DOWN=${down_price:.2f}, Countdown={market.countdown_to_active()}s")
        
        # Strategy A: Undervalued (buy when price <= threshold)
        if up_price <= self._config.undervalued_threshold:
            await self._place_order(StrategyType.UNDERVALUED, market, Outcome.UP, up_price)
        elif down_price <= self._config.undervalued_threshold:
            await self._place_order(StrategyType.UNDERVALUED, market, Outcome.DOWN, down_price)
        
        # Strategy B: Momentum (buy when price >= threshold)
        if up_price >= self._config.momentum_threshold:
            await self._place_order(StrategyType.MOMENTUM, market, Outcome.UP, up_price)
        elif down_price >= self._config.momentum_threshold:
            await self._place_order(StrategyType.MOMENTUM, market, Outcome.DOWN, down_price)
        
        # Mark market as processed
        self._processed_markets.add(market.slug)
    
    async def _place_order(self, strategy: StrategyType, market: MarketWindow, 
                          outcome: Outcome, price: float) -> None:
        """Place a paper order."""
        order = PaperOrder.create(
            strategy=strategy,
            market_slug=market.slug,
            outcome=outcome,
            price=price,
            size=self._config.order_size,
        )
        order.status = OrderStatus.OPEN
        self._orders[order.id] = order
        
        logger.info(f"📝 PLACED [{strategy.value}] {outcome.value} @ ${price:.2f} x {order.size} ({market.slug})")
    
    async def _handle_exit(self, market: MarketWindow) -> None:
        """Cancel unfilled orders at exit point."""
        for order in list(self._orders.values()):
            if order.market_slug == market.slug and order.status == OrderStatus.OPEN:
                if order.filled_size == 0:
                    order.cancel()
                    logger.info(f"❌ CANCELLED [{order.strategy.value}] {order.outcome.value} ({market.slug})")
    
    async def _check_resolutions(self, tracker) -> None:
        """Check for resolved markets and update trades."""
        now = int(time.time())
        
        # Store resolution check times to avoid spamming API
        if not hasattr(self, '_resolution_check_times'):
            self._resolution_check_times = {}

        for trade in self._trades:
            if trade.result != TradeResult.PENDING:
                continue
            
            market = tracker.get_market_by_slug(trade.market_slug)
            
            # Determine end_time
            if market:
                end_time = market.end_time
            else:
                # If market not in tracker (too old), parse from slug
                try:
                    # Slug format: btc-updown-15m-{timestamp}
                    parts = trade.market_slug.split("-")
                    start_time = int(parts[-1])
                    end_time = start_time + 900  # 15 minutes duration
                except (ValueError, IndexError):
                    logger.warning(f"Could not determine end time for market {trade.market_slug}")
                    continue
            
            # Check if market has resolved (past end_time)
            if now > end_time:
                # Throttle API checks (every 15 seconds)
                last_check = self._resolution_check_times.get(trade.market_slug, 0)
                if now - last_check < 15:
                    continue
                    
                self._resolution_check_times[trade.market_slug] = now
                
                # Fetch actual resolution from Polymarket API
                winning_outcome = await tracker.fetch_market_resolution(trade.market_slug)
                
                if winning_outcome:
                    trade.resolve(winning_outcome)
                    
                    result_emoji = "✅" if trade.result == TradeResult.WIN else "❌"
                    logger.info(f"{result_emoji} RESOLVED [{trade.strategy.value}] {trade.outcome.value} -> "
                               f"Winner={winning_outcome.value}, P&L=${trade.pnl:.2f} ({trade.market_slug})")
                else:
                    # Market ended but not yet resolved on API, keep pending
                    pass
    
    async def _simulate_fills(self, clob) -> None:
        """Simulate order fills for paper trading."""
        for order in list(self._orders.values()):
            if order.status != OrderStatus.OPEN:
                continue
            
            if order.filled_size > 0:
                continue  # Already filled
            
            # Simulate fill probability
            if random.random() < self._config.sim_fill_probability:
                order.fill(order.size)
                
                # Create trade from filled order
                trade = Trade.from_order(order)
                self._trades.append(trade)
                
                logger.info(f"💰 FILLED [{order.strategy.value}] {order.outcome.value} @ ${order.price:.2f} x {order.size}")
    
    def get_open_orders(self) -> List[PaperOrder]:
        """Get all open orders."""
        return [o for o in self._orders.values() if o.status == OrderStatus.OPEN]
    
    def get_all_orders(self) -> List[PaperOrder]:
        """Get all orders."""
        return list(self._orders.values())
    
    def get_trades(self, strategy: Optional[StrategyType] = None) -> List[Trade]:
        """Get trades, optionally filtered by strategy."""
        if strategy:
            return [t for t in self._trades if t.strategy == strategy]
        return self._trades
    
    def get_metrics(self, strategy: StrategyType) -> StrategyMetrics:
        """Calculate metrics for a strategy."""
        trades = self.get_trades(strategy)
        
        metrics = StrategyMetrics(strategy=strategy)
        for trade in trades:
            metrics.total_trades += 1
            metrics.total_invested += trade.size * trade.entry_price
            
            if trade.result == TradeResult.WIN:
                metrics.wins += 1
                metrics.total_pnl += trade.pnl
            elif trade.result == TradeResult.LOSS:
                metrics.losses += 1
                metrics.total_pnl += trade.pnl
            else:
                metrics.pending += 1
        
        return metrics
    
    def get_status(self) -> dict:
        """Get full engine status."""
        return {
            "is_running": self._running,
            "start_time": self._start_time,
            "paper_mode": True,
            "config": {
                "undervalued_threshold": self._config.undervalued_threshold,
                "momentum_threshold": self._config.momentum_threshold,
                "order_size": self._config.order_size,
                "entry_countdown": self._config.entry_countdown,
                "exit_countdown": self._config.exit_countdown,
            },
            "orders": {
                "open": len(self.get_open_orders()),
                "total": len(self._orders),
            },
            "trades": {
                "total": len(self._trades),
                "pending": sum(1 for t in self._trades if t.result == TradeResult.PENDING),
            },
            "processed_markets": len(self._processed_markets),
        }


# Global instance
_engine: Optional[StrategyEngine] = None


def get_strategy_engine() -> StrategyEngine:
    """Get the global strategy engine."""
    global _engine
    if _engine is None:
        _engine = StrategyEngine()
    return _engine
