"""Unit tests for the SQLite persistence layer."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from app.data import db as dbmod


@pytest.fixture
def temp_db(tmp_path) -> Path:
    path = tmp_path / "test.sqlite"
    dbmod.init_db(path)
    return path


def test_init_seeds_default_watchlist(temp_db: Path):
    with dbmod.get_conn(temp_db) as conn:
        wl = conn.execute("SELECT name FROM watchlists").fetchall()
    assert len(wl) == 1
    assert wl[0]["name"] == "Default"


def test_add_and_remove_symbol(temp_db: Path):
    with dbmod.get_conn(temp_db) as conn:
        wid = conn.execute("SELECT id FROM watchlists LIMIT 1").fetchone()["id"]

    dbmod.add_symbol(wid, "NVDA", "stock", path=temp_db)
    items = dbmod.list_watchlist(wid, path=temp_db)
    symbols = {item["symbol"] for item in items}
    assert "NVDA" in symbols

    # Adding the same symbol is idempotent.
    dbmod.add_symbol(wid, "NVDA", "stock", path=temp_db)
    items2 = dbmod.list_watchlist(wid, path=temp_db)
    assert len([i for i in items2 if i["symbol"] == "NVDA"]) == 1

    dbmod.remove_symbol(wid, "NVDA", path=temp_db)
    items3 = dbmod.list_watchlist(wid, path=temp_db)
    assert "NVDA" not in {i["symbol"] for i in items3}


def test_price_cache_roundtrip(temp_db: Path):
    df = pd.DataFrame(
        {
            "Open": [10, 11, 12],
            "High": [10.5, 11.5, 12.5],
            "Low": [9.8, 10.8, 11.8],
            "Close": [10.2, 11.2, 12.2],
            "Volume": [1000, 1100, 1200],
        },
        index=pd.date_range("2024-01-01", periods=3, freq="D"),
    )
    dbmod.cache_history("TEST", df, path=temp_db)
    loaded = dbmod.load_history("TEST", path=temp_db)
    assert len(loaded) == 3
    assert list(loaded.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert loaded["Close"].iloc[-1] == pytest.approx(12.2)

    latest = dbmod.latest_cached_date("TEST", path=temp_db)
    assert latest == "2024-01-03"


def test_save_prediction(temp_db: Path):
    dbmod.save_prediction("AAPL", 0.62, 1, 0.54, "{}", path=temp_db)
    with dbmod.get_conn(temp_db) as conn:
        row = conn.execute(
            "SELECT symbol, prob_up, accuracy FROM predictions WHERE symbol = 'AAPL'"
        ).fetchone()
    assert row["symbol"] == "AAPL"
    assert row["prob_up"] == pytest.approx(0.62)
    assert row["accuracy"] == pytest.approx(0.54)
