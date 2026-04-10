"""Thin wrapper around yfinance with SQLite caching."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd
import yfinance as yf

from app.data import db


@dataclass
class Quote:
    symbol: str
    last: float
    prev_close: float

    @property
    def change(self) -> float:
        return self.last - self.prev_close

    @property
    def change_pct(self) -> float:
        if self.prev_close == 0:
            return 0.0
        return (self.last - self.prev_close) / self.prev_close * 100.0


def get_history(symbol: str, period: str = "1y", use_cache: bool = True) -> pd.DataFrame:
    """Fetch OHLCV daily bars, cached in SQLite.

    We always fetch fresh from yfinance for the requested period and upsert
    into the cache, so subsequent calls still benefit from cache if the
    network is unreachable.
    """
    symbol = symbol.upper()
    df: pd.DataFrame = pd.DataFrame()
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, auto_adjust=False)
    except Exception:
        df = pd.DataFrame()

    if not df.empty:
        # Strip tz for clean SQLite storage.
        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)
        db.cache_history(symbol, df)
        return df[["Open", "High", "Low", "Close", "Volume"]]

    if use_cache:
        return db.load_history(symbol)
    return df


def get_quotes(symbols: Iterable[str]) -> dict[str, Quote]:
    """Batch last-price fetch for a list of symbols.

    Uses a 2-day daily download; last row is the most recent close (or
    current intraday on an open session), previous row is prior close.
    """
    syms = [s.upper() for s in symbols]
    if not syms:
        return {}
    quotes: dict[str, Quote] = {}
    try:
        data = yf.download(
            tickers=" ".join(syms),
            period="5d",
            interval="1d",
            group_by="ticker",
            auto_adjust=False,
            progress=False,
            threads=True,
        )
    except Exception:
        return quotes

    if data is None or data.empty:
        return quotes

    if len(syms) == 1:
        sym = syms[0]
        closes = data["Close"].dropna()
        if len(closes) >= 2:
            quotes[sym] = Quote(sym, float(closes.iloc[-1]), float(closes.iloc[-2]))
        elif len(closes) == 1:
            quotes[sym] = Quote(sym, float(closes.iloc[-1]), float(closes.iloc[-1]))
        return quotes

    for sym in syms:
        try:
            closes = data[sym]["Close"].dropna()
        except KeyError:
            continue
        if len(closes) >= 2:
            quotes[sym] = Quote(sym, float(closes.iloc[-1]), float(closes.iloc[-2]))
        elif len(closes) == 1:
            quotes[sym] = Quote(sym, float(closes.iloc[-1]), float(closes.iloc[-1]))
    return quotes


def get_info(symbol: str) -> dict:
    """Fetch fundamentals / metadata. Returns {} on failure."""
    try:
        ticker = yf.Ticker(symbol.upper())
        info = ticker.info or {}
        return dict(info)
    except Exception:
        return {}
