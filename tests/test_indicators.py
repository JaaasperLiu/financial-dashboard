"""Unit tests for the technical indicators module."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.indicators import (
    bollinger,
    build_feature_frame,
    ema,
    log_return,
    macd,
    rsi,
    sma,
)


def _synthetic_ohlcv(n: int = 200, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2023-01-01", periods=n, freq="B")
    steps = rng.normal(0, 1, size=n).cumsum()
    close = 100 + steps
    open_ = close + rng.normal(0, 0.2, size=n)
    high = np.maximum(open_, close) + rng.uniform(0, 0.5, size=n)
    low = np.minimum(open_, close) - rng.uniform(0, 0.5, size=n)
    volume = rng.integers(1_000_000, 5_000_000, size=n).astype(float)
    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume},
        index=idx,
    )


def test_sma_matches_rolling_mean():
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    result = sma(s, 3)
    assert np.isnan(result.iloc[0])
    assert np.isnan(result.iloc[1])
    assert result.iloc[2] == pytest.approx(2.0)
    assert result.iloc[3] == pytest.approx(3.0)
    assert result.iloc[4] == pytest.approx(4.0)


def test_ema_is_finite_after_warmup():
    s = pd.Series(np.arange(1.0, 101.0))
    result = ema(s, 10)
    assert result.iloc[-1] > 0
    assert not np.isnan(result.iloc[-1])


def test_rsi_bounds():
    df = _synthetic_ohlcv(300)
    r = rsi(df["Close"], 14).dropna()
    assert (r >= 0).all() and (r <= 100).all()


def test_macd_columns_and_relationship():
    df = _synthetic_ohlcv(300)
    m = macd(df["Close"])
    assert set(m.columns) == {"macd", "signal", "hist"}
    # hist should equal macd - signal
    diff = (m["macd"] - m["signal"] - m["hist"]).dropna()
    assert np.allclose(diff, 0, atol=1e-9)


def test_bollinger_ordering():
    df = _synthetic_ohlcv(300)
    b = bollinger(df["Close"], 20, 2.0).dropna()
    assert (b["upper"] >= b["mid"]).all()
    assert (b["mid"] >= b["lower"]).all()


def test_log_return_first_is_nan():
    s = pd.Series([10.0, 11.0, 12.1])
    r = log_return(s, 1)
    assert np.isnan(r.iloc[0])
    assert r.iloc[1] == pytest.approx(np.log(11 / 10))


def test_build_feature_frame_has_expected_columns():
    df = _synthetic_ohlcv(300)
    feats = build_feature_frame(df)
    expected = {
        "ret_1d",
        "ret_5d",
        "ret_10d",
        "rsi_14",
        "macd_hist",
        "close_over_sma20",
        "close_over_sma50",
        "volume_ratio",
        "bollinger_pos",
    }
    assert expected.issubset(set(feats.columns))
    # Last row should be populated once we are past all warmups.
    assert not feats.iloc[-1].isna().any()
