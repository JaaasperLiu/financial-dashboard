"""QMainWindow wiring the watchlist, chart, metrics and prediction panels."""
from __future__ import annotations

import pandas as pd
from PyQt6.QtCore import Qt, QThreadPool, QRunnable, pyqtSignal, QObject, QTimer
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from app.config import (
    APP_NAME,
    CHART_PERIODS,
    DEFAULT_PERIOD,
    QUOTE_REFRESH_MS,
)
from app.data import db
from app.data.yahoo_client import Quote, get_history, get_info, get_quotes
from app.ml.predictor import PredictionResult, predict_symbol
from app.ui.chart_view import ChartView
from app.ui.metrics_panel import MetricsPanel
from app.ui.prediction_panel import PredictionPanel
from app.ui.watchlist_panel import WatchlistPanel


# ---------- Worker plumbing ----------

class _WorkerSignals(QObject):
    history = pyqtSignal(str, object)           # (symbol, DataFrame)
    info = pyqtSignal(str, dict)                # (symbol, info)
    quotes = pyqtSignal(dict)                   # {symbol: Quote}
    prediction = pyqtSignal(str, object)        # (symbol, PredictionResult | None)
    error = pyqtSignal(str)


class _HistoryJob(QRunnable):
    def __init__(self, signals: _WorkerSignals, symbol: str, period: str):
        super().__init__()
        self._signals = signals
        self._symbol = symbol
        self._period = period

    def run(self) -> None:
        try:
            df = get_history(self._symbol, period=self._period)
            self._signals.history.emit(self._symbol, df)
        except Exception as exc:
            self._signals.error.emit(f"history {self._symbol}: {exc}")


class _InfoJob(QRunnable):
    def __init__(self, signals: _WorkerSignals, symbol: str):
        super().__init__()
        self._signals = signals
        self._symbol = symbol

    def run(self) -> None:
        try:
            info = get_info(self._symbol)
            self._signals.info.emit(self._symbol, info)
        except Exception as exc:
            self._signals.error.emit(f"info {self._symbol}: {exc}")


class _QuotesJob(QRunnable):
    def __init__(self, signals: _WorkerSignals, symbols: list[str]):
        super().__init__()
        self._signals = signals
        self._symbols = symbols

    def run(self) -> None:
        try:
            quotes = get_quotes(self._symbols)
            self._signals.quotes.emit(quotes)
        except Exception as exc:
            self._signals.error.emit(f"quotes: {exc}")


class _PredictJob(QRunnable):
    def __init__(self, signals: _WorkerSignals, symbol: str):
        super().__init__()
        self._signals = signals
        self._symbol = symbol

    def run(self) -> None:
        try:
            result = predict_symbol(self._symbol)
            self._signals.prediction.emit(self._symbol, result)
        except Exception as exc:
            self._signals.error.emit(f"predict {self._symbol}: {exc}")


# ---------- Main window ----------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1400, 860)

        self._pool = QThreadPool.globalInstance()
        self._signals = _WorkerSignals()
        self._signals.history.connect(self._on_history)
        self._signals.info.connect(self._on_info)
        self._signals.quotes.connect(self._on_quotes)
        self._signals.prediction.connect(self._on_prediction)
        self._signals.error.connect(self._on_error)

        self._current_symbol: str | None = None
        self._current_period = DEFAULT_PERIOD
        self._last_quotes: dict[str, Quote] = {}

        # ----- central layout -----
        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)

        wid = db.default_watchlist_id()
        self._watchlist = WatchlistPanel(wid)
        self._watchlist.setFixedWidth(340)
        self._watchlist.symbol_selected.connect(self._on_symbol_selected)
        root.addWidget(self._watchlist)

        right = QVBoxLayout()
        root.addLayout(right, 1)

        self._chart = ChartView()
        right.addWidget(self._chart, 3)

        bottom = QHBoxLayout()
        self._metrics = MetricsPanel()
        self._prediction = PredictionPanel()
        bottom.addWidget(self._metrics, 1)
        bottom.addWidget(self._prediction, 1)
        right.addLayout(bottom, 2)

        self.setCentralWidget(central)

        # ----- toolbar -----
        toolbar = QToolBar("Main")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        refresh_act = QAction("Refresh", self)
        refresh_act.triggered.connect(self._refresh_all)
        toolbar.addAction(refresh_act)
        toolbar.addSeparator()

        toolbar.addWidget(QLabel("  Period:  "))
        for label, period in CHART_PERIODS:
            btn = QPushButton(label)
            btn.setCheckable(True)
            if period == DEFAULT_PERIOD:
                btn.setChecked(True)
            btn.clicked.connect(lambda _=False, p=period, b=btn: self._set_period(p, b))
            toolbar.addWidget(btn)
            # remember for exclusivity
            btn.setProperty("period", period)

        # ----- status bar -----
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Ready")

        # ----- quote refresh timer -----
        self._quote_timer = QTimer(self)
        self._quote_timer.setInterval(QUOTE_REFRESH_MS)
        self._quote_timer.timeout.connect(self._refresh_quotes)
        self._quote_timer.start()

        # Kick off initial loads.
        QTimer.singleShot(50, self._refresh_all)
        sym = self._watchlist.current_symbol()
        if sym:
            QTimer.singleShot(100, lambda s=sym: self._on_symbol_selected(s))

    # ---------- actions ----------

    def _set_period(self, period: str, btn: QPushButton) -> None:
        self._current_period = period
        # enforce single-check on period buttons
        toolbar = self.findChildren(QToolBar)[0]
        for b in toolbar.findChildren(QPushButton):
            if b.property("period"):
                b.setChecked(b is btn)
        if self._current_symbol:
            self._load_history(self._current_symbol)

    def _refresh_all(self) -> None:
        self._refresh_quotes()
        if self._current_symbol:
            self._on_symbol_selected(self._current_symbol)

    def _refresh_quotes(self) -> None:
        symbols = self._watchlist.symbols()
        if not symbols:
            return
        self._pool.start(_QuotesJob(self._signals, symbols))

    def _load_history(self, symbol: str) -> None:
        self.statusBar().showMessage(f"Loading {symbol} ({self._current_period})…")
        self._pool.start(_HistoryJob(self._signals, symbol, self._current_period))

    def _on_symbol_selected(self, symbol: str) -> None:
        self._current_symbol = symbol
        self._metrics.clear()
        self._prediction.show_loading(symbol)
        self._load_history(symbol)
        self._pool.start(_InfoJob(self._signals, symbol))
        self._pool.start(_PredictJob(self._signals, symbol))

    # ---------- signals from workers ----------

    def _on_history(self, symbol: str, df: pd.DataFrame) -> None:
        if symbol != self._current_symbol:
            return
        self._chart.set_data(symbol, df)
        if df is not None and not df.empty:
            self.statusBar().showMessage(
                f"{symbol}: {len(df)} rows  "
                f"({df.index[0].date()} → {df.index[-1].date()})"
            )
        else:
            self.statusBar().showMessage(f"{symbol}: no data")

    def _on_info(self, symbol: str, info: dict) -> None:
        if symbol != self._current_symbol:
            return
        q = self._last_quotes.get(symbol)
        last = q.last if q else info.get("regularMarketPrice")
        prev = q.prev_close if q else info.get("regularMarketPreviousClose")
        self._metrics.update_from(symbol, info, last, prev)

    def _on_quotes(self, quotes: dict) -> None:
        self._last_quotes.update(quotes)
        self._watchlist.apply_quotes(quotes)
        # Also refresh metrics headline price if the selected symbol changed.
        if self._current_symbol and self._current_symbol in quotes:
            q = quotes[self._current_symbol]
            self._metrics.update_from(self._current_symbol, {}, q.last, q.prev_close)

    def _on_prediction(self, symbol: str, result: PredictionResult | None) -> None:
        if symbol != self._current_symbol:
            return
        self._prediction.show_result(result, symbol)

    def _on_error(self, message: str) -> None:
        self.statusBar().showMessage(f"Error: {message}", 8000)

    def closeEvent(self, event) -> None:
        # Stop the timer and wait for any in-flight worker jobs so they
        # don't emit into a deleted signals object during teardown.
        self._quote_timer.stop()
        try:
            self._signals.blockSignals(True)
        except RuntimeError:
            pass
        self._pool.waitForDone(3000)
        super().closeEvent(event)
