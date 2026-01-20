"""Market tracker for discovering and monitoring 15-minute BTC markets."""
import httpx
import asyncio
import time
import logging
from typing import Optional, List

from .config import get_config
from .models import MarketWindow, Outcome

logger = logging.getLogger(__name__)

# Constants for 15-minute bucket math
BUCKET_SIZE_SECONDS = 900  # 15 minutes


def get_bucket_start(now_epoch: int) -> int:
    """Get the start timestamp of the current 15-minute bucket."""
    return (now_epoch // BUCKET_SIZE_SECONDS) * BUCKET_SIZE_SECONDS


def generate_slug(bucket_start: int) -> str:
    """Generate the market slug for a given bucket start time."""
    return f"btc-updown-15m-{bucket_start}"


def get_expanded_slugs(now_epoch: int, back: int = 2, forward: int = 6) -> list[str]:
    """Get all slug candidates for expanded bucket range."""
    bucket_start = get_bucket_start(now_epoch)
    slugs = []
    for k in range(-back, forward + 1):
        bucket = bucket_start + BUCKET_SIZE_SECONDS * k
        slugs.append(generate_slug(bucket))
    return slugs


class MarketTracker:
    """Tracks Polymarket 15-minute BTC Up/Down markets."""
    
    def __init__(self):
        self._config = get_config()
        self._client = httpx.AsyncClient(timeout=15.0)
        self._markets: List[MarketWindow] = []
        self._last_refresh: float = 0
        self._refresh_interval: float = 30.0  # Refresh every 30 seconds
    
    async def refresh(self) -> None:
        """Refresh the list of markets using slug enumeration."""
        now = time.time()
        if now - self._last_refresh < self._refresh_interval:
            return
        
        now_int = int(now)
        slugs = get_expanded_slugs(now_int, back=2, forward=6)
        
        logger.info(f"Checking {len(slugs)} market slugs...")
        
        markets = []
        for slug in slugs:
            market = await self._fetch_market_by_slug(slug)
            if market:
                markets.append(market)
        
        # Sort by start time
        markets.sort(key=lambda m: m.start_time)
        self._markets = markets
        self._last_refresh = now
        logger.info(f"Refreshed markets: {len(markets)} found")
    
    async def _fetch_market_by_slug(self, slug: str) -> Optional[MarketWindow]:
        """Fetch a single market by its slug."""
        try:
            # Try the /events endpoint first (events contain multiple markets)
            url = f"{self._config.gamma_api_url}/events"
            params = {"slug": slug}
            response = await self._client.get(url, params=params)
            
            if response.status_code == 200:
                data = response.json()
                if data and len(data) > 0:
                    event = data[0]
                    # Events contain markets array
                    event_markets = event.get("markets", [])
                    if event_markets:
                        market = event_markets[0]
                        return self._parse_market(market, slug)
            
            # Fallback: try /markets with slug filter
            url = f"{self._config.gamma_api_url}/markets"
            params = {"slug": slug}
            response = await self._client.get(url, params=params)
            
            if response.status_code == 200:
                data = response.json()
                if data and len(data) > 0:
                    return self._parse_market(data[0], slug)
                    
        except Exception as e:
            logger.debug(f"Failed to fetch {slug}: {e}")
        
        return None
    
    def _parse_market(self, market: dict, slug: str) -> Optional[MarketWindow]:
        """Parse market data into MarketWindow."""
        import json
        try:
            # Extract token IDs from tokens or clobTokenIds
            tokens = market.get("tokens", [])
            clob_token_ids = market.get("clobTokenIds", [])
            outcomes = market.get("outcomes", [])
            outcome_prices = market.get("outcomePrices", [])
            
            # Handle JSON string format for outcomes, clobTokenIds and outcomePrices
            if isinstance(outcomes, str):
                try:
                    outcomes = json.loads(outcomes)
                except:
                    outcomes = []
            if isinstance(clob_token_ids, str):
                try:
                    clob_token_ids = json.loads(clob_token_ids)
                except:
                    clob_token_ids = []
            if isinstance(outcome_prices, str):
                try:
                    outcome_prices = json.loads(outcome_prices)
                except:
                    outcome_prices = []
            
            up_token_id = None
            down_token_id = None
            winner = None
            
            if tokens:
                up_token = next((t for t in tokens if t.get("outcome") == "Up"), None)
                down_token = next((t for t in tokens if t.get("outcome") == "Down"), None)
                if up_token:
                    up_token_id = up_token.get("token_id", "")
                if down_token:
                    down_token_id = down_token.get("token_id", "")
            elif clob_token_ids and outcomes:
                # Parse from clobTokenIds array based on outcomes order
                for i, outcome in enumerate(outcomes):
                    if i < len(clob_token_ids):
                        if outcome == "Up":
                            up_token_id = clob_token_ids[i]
                        elif outcome == "Down":
                            down_token_id = clob_token_ids[i]
            
            # Determine winner if we have outcomes and prices
            if outcome_prices and len(outcome_prices) >= 2 and outcomes and len(outcomes) >= 2:
                # Price "1" indicates the winner (binary market)
                if str(outcome_prices[0]) == "1":
                    winner = Outcome.UP if outcomes[0] == "Up" else Outcome.DOWN
                elif str(outcome_prices[1]) == "1":
                    winner = Outcome.DOWN if outcomes[1] == "Down" else Outcome.UP
            
            if not up_token_id or not down_token_id:
                logger.debug(f"Missing tokens for {slug}: up={up_token_id}, down={down_token_id}")
                return None
            
            # Extract start_time from slug
            parts = slug.split("-")
            start_time = int(parts[-1])
            end_time = start_time + 900  # 15 minutes
            
            return MarketWindow(
                slug=slug,
                condition_id=market.get("conditionId", market.get("condition_id", "")),
                up_token_id=up_token_id,
                down_token_id=down_token_id,
                start_time=start_time,
                end_time=end_time,
                winner=winner
            )
        except Exception as e:
            logger.error(f"Error parsing market {slug}: {e}")
            return None
    
    def get_active_market(self) -> Optional[MarketWindow]:
        """Get the currently active market (countdown <= 0, not yet resolved)."""
        now = int(time.time())
        for market in self._markets:
            if market.start_time <= now < market.end_time:
                return market
        return None
    
    def get_t1_market(self) -> Optional[MarketWindow]:
        """Get the t+1 market (next market to become active)."""
        now = int(time.time())
        for market in self._markets:
            if market.start_time > now:
                return market
        return None
    
    def get_t2_market(self) -> Optional[MarketWindow]:
        """Get the t+2 market (market after t+1)."""
        t1 = self.get_t1_market()
        if not t1:
            return None
        
        for market in self._markets:
            if market.start_time > t1.start_time:
                return market
        return None
    
    def get_market_by_slug(self, slug: str) -> Optional[MarketWindow]:
        """Get a market by its slug."""
        for market in self._markets:
            if market.slug == slug:
                return market
        return None
    
    def get_status(self) -> dict:
        """Get current market tracker status."""
        active = self.get_active_market()
        t1 = self.get_t1_market()
        t2 = self.get_t2_market()
        
        return {
            "active_market": active.to_dict() if active else None,
            "t1_market": t1.to_dict() if t1 else None,
            "t2_market": t2.to_dict() if t2 else None,
            "total_markets": len(self._markets),
            "last_refresh": self._last_refresh,
        }
    
    async def fetch_market_resolution(self, slug: str) -> Optional[Outcome]:
        """Fetch resolution for a specific market, even if expired."""
        # Check cached markets first
        entries = [m for m in self._markets if m.slug == slug]
        if entries and entries[0].winner:
            return entries[0].winner
            
        # Fallback to API fetch
        market = await self._fetch_market_by_slug(slug)
        if market:
            return market.winner
        return None

    async def close(self):
        """Close the HTTP client."""
        await self._client.aclose()


# Global instance
_tracker: Optional[MarketTracker] = None


def get_market_tracker() -> MarketTracker:
    """Get the global market tracker."""
    global _tracker
    if _tracker is None:
        _tracker = MarketTracker()
    return _tracker
