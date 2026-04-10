"""Global configuration and paths."""
from __future__ import annotations

from pathlib import Path

APP_NAME = "Financial Dashboard"

# Data directory lives next to the project so it's easy to inspect/delete.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data_store"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "dashboard.sqlite"

# Refresh cadence (milliseconds).
QUOTE_REFRESH_MS = 30_000

# Default watchlist seeded on first run.
DEFAULT_WATCHLIST = [
    ("AAPL", "stock"),
    ("MSFT", "stock"),
    ("SPY", "stock"),
    ("BTC-USD", "crypto"),
    ("ETH-USD", "crypto"),
]

# Period options shown in the chart toolbar: label -> yfinance period string.
CHART_PERIODS = [
    ("1M", "1mo"),
    ("3M", "3mo"),
    ("6M", "6mo"),
    ("1Y", "1y"),
    ("5Y", "5y"),
    ("Max", "max"),
]
DEFAULT_PERIOD = "1y"

# Historical window used to train the predictor.
PREDICTOR_TRAIN_PERIOD = "2y"
