"""Prediction panel: probability bar + human-readable driver explanations."""
from __future__ import annotations

import math

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QGroupBox,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from app.ml.predictor import PredictionResult


def _describe_feature(name: str, value: float) -> str:
    """Turn a raw feature value into a plain-English phrase."""
    try:
        if name == "rsi_14":
            band = (
                "overbought" if value >= 70
                else "oversold" if value <= 30
                else "neutral"
            )
            return f"RSI(14) is <b>{value:.0f}</b> ({band})"
        if name == "ret_1d":
            pct = (math.exp(value) - 1) * 100
            return f"yesterday's return was <b>{pct:+.2f}%</b>"
        if name == "ret_5d":
            pct = (math.exp(value) - 1) * 100
            return f"5-day return is <b>{pct:+.2f}%</b>"
        if name == "ret_10d":
            pct = (math.exp(value) - 1) * 100
            return f"10-day return is <b>{pct:+.2f}%</b>"
        if name == "macd_hist":
            tone = "bullish" if value > 0 else "bearish" if value < 0 else "flat"
            return f"MACD histogram is <b>{value:+.3f}</b> ({tone})"
        if name == "close_over_sma20":
            pct = (value - 1) * 100
            rel = "above" if pct >= 0 else "below"
            return f"price is <b>{abs(pct):.1f}%</b> {rel} its 20-day average"
        if name == "close_over_sma50":
            pct = (value - 1) * 100
            rel = "above" if pct >= 0 else "below"
            return f"price is <b>{abs(pct):.1f}%</b> {rel} its 50-day average"
        if name == "volume_ratio":
            return f"volume is <b>{value:.1f}×</b> the 20-day average"
        if name == "bollinger_pos":
            if value >= 0.8:
                zone = "near the upper Bollinger band"
            elif value <= 0.2:
                zone = "near the lower Bollinger band"
            else:
                zone = "mid-range inside the Bollinger bands"
            return f"price is {zone} (<b>{value:.2f}</b>)"
    except (ValueError, OverflowError):
        pass
    return f"{name} = <b>{value:.3f}</b>"


def _explain_driver(name: str, value: float, contrib: float) -> str:
    """Render one driver row as HTML: direction arrow + plain-English reason."""
    if contrib >= 0:
        arrow = "▲"
        color = "#26a69a"
        tone = "supports UP"
    else:
        arrow = "▼"
        color = "#ef5350"
        tone = "supports DOWN"
    phrase = _describe_feature(name, value)
    return (
        f"<div style='margin-bottom:4px;'>"
        f"<span style='color:{color}; font-weight:bold;'>{arrow} {tone}</span>"
        f" — {phrase}"
        f" <span style='color:#9aa0a6;'>(weight {contrib:+.2f})</span>"
        f"</div>"
    )


class PredictionPanel(QGroupBox):
    def __init__(self, parent: QWidget | None = None):
        super().__init__("Next-day Forecast (baseline model)", parent)
        layout = QVBoxLayout(self)

        self._headline = QLabel("Select a symbol to see a forecast.")
        self._headline.setStyleSheet("font-size: 14pt; font-weight: bold;")
        layout.addWidget(self._headline)

        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(50)
        self._bar.setFormat("P(up) = %p%")
        layout.addWidget(self._bar)

        self._accuracy = QLabel("")
        layout.addWidget(self._accuracy)

        self._features_title = QLabel("<b>Why the model thinks so</b>")
        layout.addWidget(self._features_title)
        self._features = QLabel("")
        self._features.setTextFormat(Qt.TextFormat.RichText)
        self._features.setWordWrap(True)
        layout.addWidget(self._features)

        layout.addStretch(1)

        disclaimer = QLabel(
            "<i>Educational baseline — not financial advice. "
            "Logistic regression on technical features.</i>"
        )
        disclaimer.setWordWrap(True)
        disclaimer.setStyleSheet("color: #9aa0a6;")
        layout.addWidget(disclaimer)

    def clear(self) -> None:
        self._headline.setText("Select a symbol to see a forecast.")
        self._bar.setValue(50)
        self._accuracy.setText("")
        self._features.setText("")

    def show_loading(self, symbol: str) -> None:
        self._headline.setText(f"Training model for {symbol}…")
        self._bar.setValue(50)
        self._accuracy.setText("")
        self._features.setText("")

    def show_result(self, result: PredictionResult | None, symbol: str) -> None:
        if result is None:
            self._headline.setText(f"{symbol}: not enough data to forecast")
            self._bar.setValue(50)
            self._accuracy.setText("")
            self._features.setText("")
            return

        pct = int(round(result.prob_up * 100))
        direction = "UP" if result.prob_up >= 0.5 else "DOWN"
        color = "#26a69a" if result.prob_up >= 0.5 else "#ef5350"
        self._headline.setText(
            f"<span style='color:{color}'>{result.symbol}: {direction} ({pct}%)</span>"
        )
        self._bar.setValue(pct)

        if result.accuracy is not None:
            self._accuracy.setText(
                f"Backtest accuracy: {result.accuracy * 100:.1f}%  "
                f"(train rows: {result.n_train})"
            )
        else:
            self._accuracy.setText(f"Train rows: {result.n_train}")

        if result.top_features:
            lines = [
                _explain_driver(name, result.feature_values.get(name, 0.0), contrib)
                for name, contrib in result.top_features
            ]
            self._features.setText("".join(lines))
        else:
            self._features.setText("")
