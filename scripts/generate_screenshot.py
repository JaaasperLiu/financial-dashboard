"""Render a deterministic screenshot of the MainWindow for the README.

Runs headless via Qt's offscreen platform — no display required.

Usage:
    QT_QPA_PLATFORM=offscreen python scripts/generate_screenshot.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

# Must be set before any PyQt6 import.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pandas as pd
from PyQt6.QtCore import QRunnable
from PyQt6.QtWidgets import QApplication

# Allow running as a script from the repo root.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app import config  # noqa: E402

# Use a throwaway DB so the screenshot always shows the seed watchlist,
# not whatever the developer has personally added.
_TMP_DB = Path(tempfile.gettempdir()) / "fd_screenshot.sqlite"
_TMP_DB.unlink(missing_ok=True)
config.DB_PATH = _TMP_DB

from app.data import db  # noqa: E402
db.DB_PATH = _TMP_DB

from app.data.yahoo_client import Quote  # noqa: E402
from app.ml.predictor import PredictionResult  # noqa: E402
import app.ui.main_window as mw  # noqa: E402


class _NoopJob(QRunnable):
    """Stand-in worker that does nothing — keeps the render deterministic."""

    def __init__(self, *args, **kwargs):
        super().__init__()

    def run(self) -> None:
        pass


# Replace background jobs BEFORE MainWindow is constructed, so the
# QTimer.singleShot callbacks fired during construction can't hit the network
# or emit into the signals object during teardown.
mw._HistoryJob = _NoopJob
mw._InfoJob = _NoopJob
mw._QuotesJob = _NoopJob
mw._PredictJob = _NoopJob

from app.ui.main_window import MainWindow  # noqa: E402


def _synthetic_ohlcv(n: int = 180, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2025-01-01", periods=n, freq="B")
    drift = np.linspace(0, 25, n)
    noise = rng.normal(0, 1.2, size=n).cumsum()
    close = 170 + drift + noise
    open_ = close - rng.normal(0, 0.5, size=n)
    high = np.maximum(open_, close) + rng.uniform(0, 1.0, size=n)
    low = np.minimum(open_, close) - rng.uniform(0, 1.0, size=n)
    volume = rng.integers(800_000, 3_000_000, size=n).astype(float)
    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume},
        index=idx,
    )


def main() -> int:
    db.init_db()
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    w = MainWindow()
    w.resize(1400, 860)
    w.show()

    # Freeze the window — stop timers and prevent real network jobs kicking in.
    w._quote_timer.stop()

    # Let the initial QTimer.singleShot(50/100ms) callbacks in MainWindow.__init__
    # fire (they are no-ops now because of the _NoopJob patch above). We have to
    # wait real wall time, not just spin processEvents, otherwise the timers
    # fire AFTER we inject fake data and overwrite it.
    deadline = time.monotonic() + 0.35
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)

    # Chart: synthetic 180 business days of OHLCV.
    w._current_symbol = "AAPL"
    df = _synthetic_ohlcv()
    w._chart.set_data("AAPL", df)

    last = float(df["Close"].iloc[-1])
    prev = float(df["Close"].iloc[-2])

    # Metrics: plausible fake fundamentals.
    info = {
        "longName": "Apple Inc.",
        "sector": "Technology",
        "marketCap": 3_500_000_000_000,
        "trailingPE": 32.4,
        "fiftyTwoWeekHigh": 237.50,
        "fiftyTwoWeekLow": 164.08,
        "volume": 42_318_000,
    }
    w._metrics.update_from("AAPL", info, last, prev)

    # Prediction: hand-crafted deterministic result.
    result = PredictionResult(
        symbol="AAPL",
        prob_up=0.63,
        accuracy=0.546,
        horizon_days=1,
        top_features=[
            ("close_over_sma20", 0.42),
            ("rsi_14", -0.31),
            ("macd_hist", 0.18),
        ],
        feature_values={
            "close_over_sma20": 1.048,
            "rsi_14": 68.0,
            "macd_hist": 0.213,
        },
        n_train=458,
    )
    w._prediction.show_result(result, "AAPL")

    # Watchlist: fake live quotes for the seed symbols.
    quotes = {
        "AAPL": Quote("AAPL", 185.24, 182.91),
        "MSFT": Quote("MSFT", 418.62, 415.30),
        "SPY": Quote("SPY", 517.88, 519.42),
        "BTC-USD": Quote("BTC-USD", 68234.11, 66912.47),
        "ETH-USD": Quote("ETH-USD", 3421.09, 3470.62),
    }
    w._watchlist.apply_quotes(quotes)

    # Paint a few more frames so the injected state is fully rendered.
    for _ in range(8):
        app.processEvents()

    out_dir = PROJECT_ROOT / "docs"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "screenshot.png"
    pixmap = w.grab()
    pixmap.save(str(out_path), "PNG")
    print(f"saved {out_path}  ({pixmap.width()}x{pixmap.height()})")

    # Clean teardown — closeEvent waits for any pool work and blocks signals.
    w.close()
    app.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
