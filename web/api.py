"""FastAPI backend for the strategy tester."""
import asyncio
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import get_config
from src.models import StrategyType
from src.market_tracker import get_market_tracker
from src.strategy_engine import get_strategy_engine
from src.clob_client import get_clob_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    # Initialize components
    tracker = get_market_tracker()
    await tracker.refresh()
    print("Market tracker initialized")
    yield
    # Cleanup
    engine = get_strategy_engine()
    await engine.stop()
    clob = get_clob_client()
    await clob.close()


app = FastAPI(title="Polymarket Strategy Tester", lifespan=lifespan)

# Serve static files
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
async def index():
    """Redirect to dashboard."""
    return FileResponse(static_dir / "dashboard.html")


# ==================== API ENDPOINTS ====================

@app.get("/api/status")
async def get_status():
    """Get overall system status."""
    engine = get_strategy_engine()
    tracker = get_market_tracker()
    
    return {
        "engine": engine.get_status(),
        "markets": tracker.get_status(),
        "timestamp": time.time(),
    }


@app.post("/api/start")
async def start_engine():
    """Start the strategy engine."""
    engine = get_strategy_engine()
    await engine.start()
    return {"success": True, "message": "Engine started"}


@app.post("/api/stop")
async def stop_engine():
    """Stop the strategy engine."""
    engine = get_strategy_engine()
    await engine.stop()
    return {"success": True, "message": "Engine stopped"}


@app.get("/api/markets")
async def get_markets():
    """Get current market data."""
    tracker = get_market_tracker()
    await tracker.refresh()
    
    status = tracker.get_status()
    
    # Get prices for t+1 market
    t1 = status.get("t1_market")
    if t1:
        clob = get_clob_client()
        # Get market window from tracker
        market = tracker.get_t1_market()
        if market:
            up_price, down_price = await clob.get_prices(
                market.up_token_id,
                market.down_token_id
            )
            t1["up_price"] = up_price
            t1["down_price"] = down_price
            t1["sum_price"] = (up_price + down_price) if (up_price and down_price) else None
    
    return status


@app.get("/api/orders")
async def get_orders():
    """Get all orders."""
    engine = get_strategy_engine()
    return {
        "orders": [o.to_dict() for o in engine.get_all_orders()],
        "open_count": len(engine.get_open_orders()),
    }


@app.get("/api/trades")
async def get_trades(strategy: str = None):
    """Get all trades."""
    engine = get_strategy_engine()
    
    if strategy:
        try:
            strat = StrategyType(strategy)
            trades = engine.get_trades(strat)
        except ValueError:
            trades = engine.get_trades()
    else:
        trades = engine.get_trades()
    
    return {
        "trades": [t.to_dict() for t in trades],
        "count": len(trades),
    }


@app.get("/api/metrics")
async def get_metrics():
    """Get metrics for both strategies."""
    engine = get_strategy_engine()
    
    undervalued = engine.get_metrics(StrategyType.UNDERVALUED)
    momentum = engine.get_metrics(StrategyType.MOMENTUM)
    
    return {
        "undervalued": undervalued.to_dict(),
        "momentum": momentum.to_dict(),
    }


@app.get("/api/prices")
async def get_current_prices():
    """Get current prices for t+1 market."""
    tracker = get_market_tracker()
    await tracker.refresh()
    
    t1 = tracker.get_t1_market()
    if not t1:
        return {"error": "No t+1 market found"}
    
    clob = get_clob_client()
    up_price, down_price = await clob.get_prices(t1.up_token_id, t1.down_token_id)
    
    config = get_config()
    
    return {
        "market_slug": t1.slug,
        "countdown": t1.countdown_to_active(),
        "up_price": up_price,
        "down_price": down_price,
        "sum_price": (up_price + down_price) if (up_price and down_price) else None,
        "undervalued_threshold": config.undervalued_threshold,
        "momentum_threshold": config.momentum_threshold,
        "entry_window": t1.countdown_to_active() <= config.entry_countdown,
    }


# ==================== WEBSOCKET ====================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket for real-time updates."""
    await websocket.accept()
    
    try:
        while True:
            engine = get_strategy_engine()
            tracker = get_market_tracker()
            
            # Get prices
            t1 = tracker.get_t1_market()
            prices = None
            if t1:
                clob = get_clob_client()
                up_price, down_price = await clob.get_prices(
                    t1.up_token_id, t1.down_token_id
                )
                prices = {
                    "up": up_price,
                    "down": down_price,
                    "sum": (up_price + down_price) if (up_price and down_price) else None,
                }
            
            state = {
                "timestamp": time.time(),
                "engine": engine.get_status(),
                "markets": tracker.get_status(),
                "prices": prices,
                "metrics": {
                    "undervalued": engine.get_metrics(StrategyType.UNDERVALUED).to_dict(),
                    "momentum": engine.get_metrics(StrategyType.MOMENTUM).to_dict(),
                },
                "orders": [o.to_dict() for o in engine.get_all_orders()],
                "recent_trades": [t.to_dict() for t in engine.get_trades()[-10:]],
            }
            
            await websocket.send_json(state)
            await asyncio.sleep(2)
            
    except WebSocketDisconnect:
        pass


if __name__ == "__main__":
    print("Starting Polymarket Strategy Tester on port 8002...")
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
