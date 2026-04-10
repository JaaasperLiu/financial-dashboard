"""Simple logistic-regression predictor for next-day direction.

Deliberately minimal and transparent: feature engineering is in
``app.indicators.build_feature_frame`` and the model is a scaled
logistic regression. Output is the calibrated probability that the
next-day close will exceed today's close, plus a backtest accuracy
computed via a time-series split.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from app.data import db
from app.data.yahoo_client import get_history
from app.indicators import build_feature_frame


@dataclass
class PredictionResult:
    symbol: str
    prob_up: float
    accuracy: Optional[float]
    horizon_days: int = 1
    top_features: list[tuple[str, float]] = field(default_factory=list)
    feature_values: dict[str, float] = field(default_factory=dict)
    n_train: int = 0

    def to_json(self) -> str:
        return json.dumps(
            {
                "prob_up": self.prob_up,
                "accuracy": self.accuracy,
                "horizon_days": self.horizon_days,
                "top_features": self.top_features,
                "feature_values": self.feature_values,
                "n_train": self.n_train,
            }
        )


def _prepare_dataset(ohlcv: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    """Return (X, y, latest_features) aligned on completed rows."""
    feats = build_feature_frame(ohlcv)
    # Target: next-day up (1) or not (0).
    next_ret = ohlcv["Close"].shift(-1) / ohlcv["Close"] - 1
    y = (next_ret > 0).astype(int)

    # Latest feature row corresponds to "today"; target is unknown -> exclude.
    latest = feats.iloc[-1]
    train = feats.iloc[:-1]
    target = y.iloc[:-1]

    data = train.join(target.rename("target")).dropna()
    X = data.drop(columns=["target"])
    y_clean = data["target"].astype(int)
    return X, y_clean, latest


def _backtest_accuracy(X: pd.DataFrame, y: pd.Series) -> Optional[float]:
    if len(X) < 120:
        return None
    try:
        tscv = TimeSeriesSplit(n_splits=5)
        accs: list[float] = []
        for train_idx, test_idx in tscv.split(X):
            pipe = Pipeline(
                [("scaler", StandardScaler()), ("clf", LogisticRegression(max_iter=1000))]
            )
            pipe.fit(X.iloc[train_idx], y.iloc[train_idx])
            preds = pipe.predict(X.iloc[test_idx])
            accs.append(float((preds == y.iloc[test_idx].to_numpy()).mean()))
        return float(np.mean(accs))
    except Exception:
        return None


def predict_symbol(symbol: str, period: str = "2y") -> Optional[PredictionResult]:
    """Train on recent history and return a next-day probability."""
    ohlcv = get_history(symbol, period=period)
    if ohlcv is None or ohlcv.empty or len(ohlcv) < 80:
        return None

    X, y, latest = _prepare_dataset(ohlcv)
    if len(X) < 60 or y.nunique() < 2:
        return None

    pipe = Pipeline(
        [("scaler", StandardScaler()), ("clf", LogisticRegression(max_iter=1000))]
    )
    pipe.fit(X, y)

    latest_df = latest.to_frame().T.dropna(axis=1)
    # Any NaN in the latest row means we can't predict safely.
    if latest_df.shape[1] != X.shape[1]:
        return None

    prob_up = float(pipe.predict_proba(latest_df[X.columns])[0, 1])

    # Feature contributions (coef * scaled value) for the latest row.
    scaler: StandardScaler = pipe.named_steps["scaler"]
    clf: LogisticRegression = pipe.named_steps["clf"]
    scaled_latest = scaler.transform(latest_df[X.columns])[0]
    contribs = list(zip(X.columns.tolist(), (clf.coef_[0] * scaled_latest).tolist()))
    contribs.sort(key=lambda kv: abs(kv[1]), reverse=True)
    top = contribs[:3]

    # Raw (unscaled) feature values for the top drivers, used by the UI to
    # render human-readable explanations.
    feature_values = {
        name: float(latest_df[name].iloc[0]) for name, _ in top if name in latest_df
    }

    acc = _backtest_accuracy(X, y)

    result = PredictionResult(
        symbol=symbol.upper(),
        prob_up=prob_up,
        accuracy=acc,
        horizon_days=1,
        top_features=top,
        feature_values=feature_values,
        n_train=len(X),
    )
    try:
        db.save_prediction(
            symbol=result.symbol,
            prob_up=result.prob_up,
            horizon_days=result.horizon_days,
            accuracy=result.accuracy,
            features_json=result.to_json(),
        )
    except Exception:
        pass
    return result
