"""SQLite persistence: schema init, watchlist CRUD, OHLCV cache, predictions."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd

from app.config import DB_PATH, DEFAULT_WATCHLIST

SCHEMA = """
CREATE TABLE IF NOT EXISTS watchlists (
    id   INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS watchlist_items (
    watchlist_id INTEGER NOT NULL REFERENCES watchlists(id) ON DELETE CASCADE,
    symbol       TEXT NOT NULL,
    asset_type   TEXT NOT NULL CHECK (asset_type IN ('stock','crypto')),
    position     INTEGER NOT NULL DEFAULT 0,
    added_at     TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (watchlist_id, symbol)
);

CREATE TABLE IF NOT EXISTS price_cache (
    symbol TEXT NOT NULL,
    date   TEXT NOT NULL,
    open   REAL, high REAL, low REAL, close REAL, volume REAL,
    PRIMARY KEY (symbol, date)
);

CREATE TABLE IF NOT EXISTS predictions (
    symbol        TEXT NOT NULL,
    run_at        TEXT NOT NULL,
    prob_up       REAL NOT NULL,
    horizon_days  INTEGER NOT NULL,
    accuracy      REAL,
    features_json TEXT,
    PRIMARY KEY (symbol, run_at)
);
"""


def _connect(path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def get_conn(path: Path = DB_PATH):
    conn = _connect(path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(path: Path = DB_PATH) -> None:
    """Create tables and seed a default watchlist if none exists."""
    with get_conn(path) as conn:
        conn.executescript(SCHEMA)
        # Migration: older databases may lack `position` on watchlist_items.
        cols = {r[1] for r in conn.execute("PRAGMA table_info(watchlist_items)")}
        if "position" not in cols:
            conn.execute(
                "ALTER TABLE watchlist_items "
                "ADD COLUMN position INTEGER NOT NULL DEFAULT 0"
            )
            # Backfill position from added_at so existing rows keep their order.
            conn.execute(
                """
                UPDATE watchlist_items AS t
                SET position = (
                    SELECT COUNT(*) - 1
                    FROM watchlist_items AS u
                    WHERE u.watchlist_id = t.watchlist_id
                      AND u.added_at <= t.added_at
                )
                """
            )
        cur = conn.execute("SELECT COUNT(*) FROM watchlists")
        if cur.fetchone()[0] == 0:
            conn.execute("INSERT INTO watchlists (name) VALUES (?)", ("Default",))
            wid = conn.execute(
                "SELECT id FROM watchlists WHERE name = ?", ("Default",)
            ).fetchone()[0]
            conn.executemany(
                "INSERT INTO watchlist_items "
                "(watchlist_id, symbol, asset_type, position) VALUES (?, ?, ?, ?)",
                [(wid, s, t, i) for i, (s, t) in enumerate(DEFAULT_WATCHLIST)],
            )


# ---------- watchlist ----------

def default_watchlist_id(path: Path = DB_PATH) -> int:
    with get_conn(path) as conn:
        row = conn.execute("SELECT id FROM watchlists ORDER BY id LIMIT 1").fetchone()
        return int(row[0])


def list_watchlist(watchlist_id: int, path: Path = DB_PATH) -> list[dict]:
    with get_conn(path) as conn:
        rows = conn.execute(
            "SELECT symbol, asset_type FROM watchlist_items "
            "WHERE watchlist_id = ? ORDER BY position, added_at",
            (watchlist_id,),
        ).fetchall()
    return [{"symbol": r["symbol"], "asset_type": r["asset_type"]} for r in rows]


def add_symbol(watchlist_id: int, symbol: str, asset_type: str, path: Path = DB_PATH) -> None:
    with get_conn(path) as conn:
        next_pos = conn.execute(
            "SELECT COALESCE(MAX(position), -1) + 1 FROM watchlist_items "
            "WHERE watchlist_id = ?",
            (watchlist_id,),
        ).fetchone()[0]
        conn.execute(
            "INSERT OR IGNORE INTO watchlist_items "
            "(watchlist_id, symbol, asset_type, position) VALUES (?, ?, ?, ?)",
            (watchlist_id, symbol.upper(), asset_type, int(next_pos)),
        )


def remove_symbol(watchlist_id: int, symbol: str, path: Path = DB_PATH) -> None:
    with get_conn(path) as conn:
        conn.execute(
            "DELETE FROM watchlist_items WHERE watchlist_id = ? AND symbol = ?",
            (watchlist_id, symbol.upper()),
        )


def set_watchlist_order(
    watchlist_id: int, symbols_in_order: Iterable[str], path: Path = DB_PATH
) -> None:
    """Persist a new visual order for the watchlist."""
    with get_conn(path) as conn:
        for pos, sym in enumerate(symbols_in_order):
            conn.execute(
                "UPDATE watchlist_items SET position = ? "
                "WHERE watchlist_id = ? AND symbol = ?",
                (pos, watchlist_id, sym.upper()),
            )


# ---------- price cache ----------

def cache_history(symbol: str, df: pd.DataFrame, path: Path = DB_PATH) -> None:
    """Upsert daily OHLCV rows into the cache. Expects index = DatetimeIndex."""
    if df is None or df.empty:
        return
    records: list[tuple] = []
    for idx, row in df.iterrows():
        date_str = pd.Timestamp(idx).strftime("%Y-%m-%d")
        records.append(
            (
                symbol.upper(),
                date_str,
                float(row.get("Open", row.get("open", 0)) or 0),
                float(row.get("High", row.get("high", 0)) or 0),
                float(row.get("Low", row.get("low", 0)) or 0),
                float(row.get("Close", row.get("close", 0)) or 0),
                float(row.get("Volume", row.get("volume", 0)) or 0),
            )
        )
    with get_conn(path) as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO price_cache "
            "(symbol, date, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?)",
            records,
        )


def load_history(symbol: str, path: Path = DB_PATH) -> pd.DataFrame:
    with get_conn(path) as conn:
        rows = conn.execute(
            "SELECT date, open, high, low, close, volume FROM price_cache "
            "WHERE symbol = ? ORDER BY date",
            (symbol.upper(),),
        ).fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(
        rows, columns=["date", "Open", "High", "Low", "Close", "Volume"]
    )
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    return df


def latest_cached_date(symbol: str, path: Path = DB_PATH) -> str | None:
    with get_conn(path) as conn:
        row = conn.execute(
            "SELECT MAX(date) FROM price_cache WHERE symbol = ?", (symbol.upper(),)
        ).fetchone()
    return row[0] if row and row[0] else None


# ---------- predictions ----------

def save_prediction(
    symbol: str,
    prob_up: float,
    horizon_days: int,
    accuracy: float | None,
    features_json: str,
    path: Path = DB_PATH,
) -> None:
    with get_conn(path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO predictions "
            "(symbol, run_at, prob_up, horizon_days, accuracy, features_json) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                symbol.upper(),
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
                float(prob_up),
                int(horizon_days),
                float(accuracy) if accuracy is not None else None,
                features_json,
            ),
        )
