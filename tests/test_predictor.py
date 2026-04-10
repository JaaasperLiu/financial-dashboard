"""Tests for the predictor module's data preparation and model output.

Network is disabled by monkeypatching ``get_history`` in the predictor.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.ml import predictor as predmod


def _synthetic_trending_ohlcv(n: int = 400, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2022-01-01", periods=n, freq="B")
    # Mild upward drift with noise so a predictor can learn something.
    drift = np.linspace(0, 20, n)
    noise = rng.normal(0, 1.0, size=n).cumsum() * 0.1
    close = 100 + drift + noise
    open_ = close - rng.normal(0, 0.3, size=n)
    high = np.maximum(open_, close) + rng.uniform(0, 0.4, size=n)
    low = np.minimum(open_, close) - rng.uniform(0, 0.4, size=n)
    volume = rng.integers(500_000, 2_000_000, size=n).astype(float)
    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume},
        index=idx,
    )


def test_prepare_dataset_shapes():
    df = _synthetic_trending_ohlcv(300)
    X, y, latest = predmod._prepare_dataset(df)
    # X and y must be aligned.
    assert len(X) == len(y)
    assert not X.isna().any().any()
    assert set(y.unique()).issubset({0, 1})
    # latest is a Series of features for "today".
    assert isinstance(latest, pd.Series)


def test_predict_symbol_returns_valid_probability(monkeypatch, tmp_path):
    # Avoid writing to the real SQLite file.
    monkeypatch.setattr(predmod.db, "save_prediction", lambda *a, **kw: None)
    monkeypatch.setattr(
        predmod,
        "get_history",
        lambda symbol, period="2y": _synthetic_trending_ohlcv(400),
    )
    result = predmod.predict_symbol("FAKE")
    assert result is not None
    assert 0.0 <= result.prob_up <= 1.0
    assert result.horizon_days == 1
    assert result.n_train > 50
    # Top features should be populated.
    assert len(result.top_features) <= 3


def test_predict_symbol_handles_empty(monkeypatch):
    monkeypatch.setattr(
        predmod,
        "get_history",
        lambda symbol, period="2y": pd.DataFrame(),
    )
    assert predmod.predict_symbol("EMPTY") is None
