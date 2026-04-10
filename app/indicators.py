"""Pure-pandas technical indicators used by charts and the predictor."""
from __future__ import annotations

import numpy as np
import pandas as pd


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=window).mean()


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False, min_periods=span).mean()


def rsi(series: pd.Series, window: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    fast_ema = ema(series, fast)
    slow_ema = ema(series, slow)
    macd_line = fast_ema - slow_ema
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return pd.DataFrame({"macd": macd_line, "signal": signal_line, "hist": hist})


def bollinger(series: pd.Series, window: int = 20, n_std: float = 2.0) -> pd.DataFrame:
    mid = sma(series, window)
    std = series.rolling(window=window, min_periods=window).std()
    upper = mid + n_std * std
    lower = mid - n_std * std
    return pd.DataFrame({"mid": mid, "upper": upper, "lower": lower})


def log_return(series: pd.Series, periods: int = 1) -> pd.Series:
    return np.log(series / series.shift(periods))


def build_feature_frame(ohlcv: pd.DataFrame) -> pd.DataFrame:
    """Engineer the feature set used by the predictor.

    Input must contain columns: Open, High, Low, Close, Volume.
    """
    close = ohlcv["Close"]
    volume = ohlcv["Volume"]

    feats = pd.DataFrame(index=ohlcv.index)
    feats["ret_1d"] = log_return(close, 1)
    feats["ret_5d"] = log_return(close, 5)
    feats["ret_10d"] = log_return(close, 10)
    feats["rsi_14"] = rsi(close, 14)

    macd_df = macd(close)
    feats["macd_hist"] = macd_df["hist"]

    sma20 = sma(close, 20)
    sma50 = sma(close, 50)
    feats["close_over_sma20"] = close / sma20
    feats["close_over_sma50"] = close / sma50

    vol_avg = volume.rolling(window=20, min_periods=20).mean()
    feats["volume_ratio"] = volume / vol_avg

    boll = bollinger(close, 20, 2.0)
    width = (boll["upper"] - boll["lower"]).replace(0, np.nan)
    feats["bollinger_pos"] = (close - boll["lower"]) / width

    return feats
