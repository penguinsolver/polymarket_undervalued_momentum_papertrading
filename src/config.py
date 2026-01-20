"""Configuration management."""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass
class Config:
    """Application configuration."""
    
    # Strategy thresholds
    undervalued_threshold: float = 0.48  # Buy when price <= this
    momentum_threshold: float = 0.52     # Buy when price >= this
    order_size: float = 10.0             # Shares per order
    
    # Timing (in seconds relative to market start)
    entry_countdown: int = 1200   # 20 minutes before market starts
    exit_countdown: int = 930     # 15 min 30 sec before market starts
    
    # Paper trading
    paper_mode: bool = True
    sim_fill_probability: float = 0.7
    
    # Logging
    log_level: str = "INFO"
    
    # API URLs
    gamma_api_url: str = "https://gamma-api.polymarket.com"
    clob_api_url: str = "https://clob.polymarket.com"
    
    @classmethod
    def from_env(cls) -> "Config":
        """Load config from environment variables."""
        # Load .env file if it exists
        env_path = Path(__file__).parent.parent / ".env"
        if env_path.exists():
            load_dotenv(env_path)
        
        return cls(
            undervalued_threshold=float(os.getenv("UNDERVALUED_THRESHOLD", "0.48")),
            momentum_threshold=float(os.getenv("MOMENTUM_THRESHOLD", "0.52")),
            order_size=float(os.getenv("ORDER_SIZE_SHARES", "10")),
            entry_countdown=int(os.getenv("ENTRY_COUNTDOWN_SECONDS", "1200")),
            exit_countdown=int(os.getenv("EXIT_COUNTDOWN_SECONDS", "930")),
            paper_mode=os.getenv("PAPER_MODE", "true").lower() == "true",
            sim_fill_probability=float(os.getenv("SIM_FILL_PROBABILITY", "0.7")),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
        )


# Global config instance
_config: Config | None = None


def get_config() -> Config:
    """Get the global config instance."""
    global _config
    if _config is None:
        _config = Config.from_env()
    return _config
