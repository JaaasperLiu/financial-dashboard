"""Candlestick chart with SMA overlays and a volume subplot (pyqtgraph)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pyqtgraph as pg
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QPainter, QPicture
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from app.indicators import sma


class CandlestickItem(pg.GraphicsObject):
    """Draws OHLC candles. Data is a list of (t, open, high, low, close)."""

    def __init__(self, data: list[tuple[float, float, float, float, float]]):
        super().__init__()
        self._data = data
        self._picture: QPicture | None = None
        self._generate()

    def _generate(self) -> None:
        self._picture = QPicture()
        if not self._data:
            return
        painter = QPainter(self._picture)
        # width = 0.6 * avg spacing
        if len(self._data) > 1:
            width = 0.6 * (self._data[1][0] - self._data[0][0])
        else:
            width = 0.6
        up_pen = pg.mkPen("#26a69a")
        up_brush = pg.mkBrush("#26a69a")
        down_pen = pg.mkPen("#ef5350")
        down_brush = pg.mkBrush("#ef5350")
        for t, o, h, l, c in self._data:
            if c >= o:
                painter.setPen(up_pen)
                painter.setBrush(up_brush)
            else:
                painter.setPen(down_pen)
                painter.setBrush(down_brush)
            painter.drawLine(pg.QtCore.QPointF(t, l), pg.QtCore.QPointF(t, h))
            rect = QRectF(t - width / 2, o, width, c - o)
            painter.drawRect(rect)
        painter.end()

    def paint(self, painter, *args) -> None:
        if self._picture is not None:
            painter.drawPicture(0, 0, self._picture)

    def boundingRect(self) -> QRectF:
        if self._picture is None:
            return QRectF()
        return QRectF(self._picture.boundingRect())


class DateAxis(pg.AxisItem):
    """X-axis that formats integer indices as dates via a supplied list."""

    def __init__(self, dates: list[pd.Timestamp], *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._dates = dates

    def set_dates(self, dates: list[pd.Timestamp]) -> None:
        self._dates = dates

    def tickStrings(self, values, scale, spacing):
        out = []
        n = len(self._dates)
        for v in values:
            i = int(round(v))
            if 0 <= i < n:
                out.append(self._dates[i].strftime("%Y-%m-%d"))
            else:
                out.append("")
        return out


class ChartView(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        pg.setConfigOption("background", "#0f1115")
        pg.setConfigOption("foreground", "#d0d4dc")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._date_axis_price = DateAxis([], orientation="bottom")
        self._date_axis_vol = DateAxis([], orientation="bottom")

        self.price_plot = pg.PlotWidget(axisItems={"bottom": self._date_axis_price})
        self.price_plot.showGrid(x=True, y=True, alpha=0.2)
        self.price_plot.setLabel("left", "Price")
        self.price_plot.addLegend(offset=(10, 10))

        self.volume_plot = pg.PlotWidget(axisItems={"bottom": self._date_axis_vol})
        self.volume_plot.showGrid(x=True, y=True, alpha=0.2)
        self.volume_plot.setLabel("left", "Volume")
        self.volume_plot.setMaximumHeight(140)
        self.volume_plot.setXLink(self.price_plot)

        layout.addWidget(self.price_plot, stretch=3)
        layout.addWidget(self.volume_plot, stretch=1)

        self._candle_item: CandlestickItem | None = None
        self._df: pd.DataFrame | None = None

        # --- Crosshair overlay (shown on hover) ---
        crosshair_pen = pg.mkPen("#6a6f7a", width=1, style=Qt.PenStyle.DashLine)
        self._vline = pg.InfiniteLine(angle=90, movable=False, pen=crosshair_pen)
        self._hline = pg.InfiniteLine(angle=0, movable=False, pen=crosshair_pen)
        self._hover_label = pg.TextItem(
            anchor=(0, 1),
            color="#e6eaf2",
            fill=pg.mkBrush(20, 22, 28, 220),
            border=pg.mkPen("#3a3f4b"),
        )
        self._attach_crosshair()
        self._set_crosshair_visible(False)

        # Throttled mouse-move handler on the price plot's scene.
        self._mouse_proxy = pg.SignalProxy(
            self.price_plot.scene().sigMouseMoved,
            rateLimit=60,
            slot=self._on_mouse_moved,
        )

    def _attach_crosshair(self) -> None:
        self.price_plot.addItem(self._vline, ignoreBounds=True)
        self.price_plot.addItem(self._hline, ignoreBounds=True)
        self.price_plot.addItem(self._hover_label, ignoreBounds=True)

    def _set_crosshair_visible(self, visible: bool) -> None:
        self._vline.setVisible(visible)
        self._hline.setVisible(visible)
        self._hover_label.setVisible(visible)

    def clear(self) -> None:
        self.price_plot.clear()
        self.volume_plot.clear()
        self._candle_item = None
        self._df = None
        # price_plot.clear() removes the crosshair overlay items too — re-add.
        self._attach_crosshair()
        self._set_crosshair_visible(False)

    def set_data(self, symbol: str, ohlcv: pd.DataFrame) -> None:
        self.clear()
        if ohlcv is None or ohlcv.empty:
            self.price_plot.setTitle(f"{symbol} — no data")
            return

        df = ohlcv.dropna().copy()
        self._df = df
        dates = [pd.Timestamp(ix) for ix in df.index]
        self._date_axis_price.set_dates(dates)
        self._date_axis_vol.set_dates(dates)

        xs = np.arange(len(df), dtype=float)
        candle_data = list(
            zip(
                xs.tolist(),
                df["Open"].tolist(),
                df["High"].tolist(),
                df["Low"].tolist(),
                df["Close"].tolist(),
            )
        )
        self._candle_item = CandlestickItem(candle_data)
        self.price_plot.addItem(self._candle_item)

        # SMA overlays.
        sma20 = sma(df["Close"], 20)
        sma50 = sma(df["Close"], 50)
        self.price_plot.plot(
            xs, sma20.to_numpy(dtype=float),
            pen=pg.mkPen("#f0a020", width=1.5), name="SMA 20",
        )
        self.price_plot.plot(
            xs, sma50.to_numpy(dtype=float),
            pen=pg.mkPen("#4fc3f7", width=1.5), name="SMA 50",
        )

        # Volume bars colored by up/down day.
        up = df["Close"] >= df["Open"]
        colors_up = np.where(up, 1, 0)
        vol_up_xs = xs[colors_up == 1]
        vol_up_ys = df["Volume"].to_numpy()[colors_up == 1]
        vol_dn_xs = xs[colors_up == 0]
        vol_dn_ys = df["Volume"].to_numpy()[colors_up == 0]

        self.volume_plot.addItem(
            pg.BarGraphItem(x=vol_up_xs, height=vol_up_ys, width=0.6, brush="#26a69a")
        )
        self.volume_plot.addItem(
            pg.BarGraphItem(x=vol_dn_xs, height=vol_dn_ys, width=0.6, brush="#ef5350")
        )

        self.price_plot.setTitle(f"{symbol}")
        self.price_plot.enableAutoRange()
        self.volume_plot.enableAutoRange()

    # ---------- hover tooltip ----------

    def _on_mouse_moved(self, evt) -> None:
        if self._df is None or self._df.empty:
            return
        pos = evt[0]
        if not self.price_plot.sceneBoundingRect().contains(pos):
            self._set_crosshair_visible(False)
            return
        vb = self.price_plot.getPlotItem().vb
        mouse_pt = vb.mapSceneToView(pos)
        x = int(round(mouse_pt.x()))
        n = len(self._df)
        if x < 0 or x >= n:
            self._set_crosshair_visible(False)
            return

        row = self._df.iloc[x]
        date = pd.Timestamp(self._df.index[x])
        close = float(row["Close"])
        open_ = float(row["Open"])
        change = close - open_
        pct = (change / open_ * 100) if open_ else 0.0
        sign = "+" if change >= 0 else ""
        color = "#26a69a" if change >= 0 else "#ef5350"

        self._vline.setPos(x)
        self._hline.setPos(mouse_pt.y())
        self._hover_label.setHtml(
            f"<div style='font-family:monospace; padding:4px;'>"
            f"<b>{date.strftime('%Y-%m-%d')}</b><br>"
            f"O&nbsp;{open_:>9,.2f}&nbsp;&nbsp;H&nbsp;{float(row['High']):>9,.2f}<br>"
            f"L&nbsp;{float(row['Low']):>9,.2f}&nbsp;&nbsp;C&nbsp;{close:>9,.2f}<br>"
            f"<span style='color:{color}'>{sign}{change:,.2f} ({sign}{pct:.2f}%)</span><br>"
            f"Vol&nbsp;{float(row['Volume']):>12,.0f}"
            f"</div>"
        )
        # Anchor the label above the high so it doesn't cover the candle.
        self._hover_label.setPos(x, float(row["High"]))
        self._set_crosshair_visible(True)
