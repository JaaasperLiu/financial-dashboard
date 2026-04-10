"""Key metrics / fundamentals panel."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFormLayout, QGroupBox, QLabel, QVBoxLayout, QWidget


def _fmt_money(v) -> str:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return "—"
    for unit, size in (("T", 1e12), ("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if abs(n) >= size:
            return f"{n / size:,.2f}{unit}"
    return f"{n:,.2f}"


def _fmt_num(v, digits: int = 2) -> str:
    try:
        return f"{float(v):,.{digits}f}"
    except (TypeError, ValueError):
        return "—"


class MetricsPanel(QGroupBox):
    def __init__(self, parent: QWidget | None = None):
        super().__init__("Metrics", parent)
        outer = QVBoxLayout(self)
        self._form = QFormLayout()
        self._form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        outer.addLayout(self._form)

        self._labels: dict[str, QLabel] = {}
        for key in [
            "Name",
            "Sector",
            "Last Price",
            "Day Change",
            "Market Cap",
            "P/E (trailing)",
            "52w High",
            "52w Low",
            "Volume",
        ]:
            lbl = QLabel("—")
            lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self._form.addRow(f"{key}:", lbl)
            self._labels[key] = lbl

    def clear(self) -> None:
        for lbl in self._labels.values():
            lbl.setText("—")

    def update_from(self, symbol: str, info: dict, last_close: float | None, prev_close: float | None) -> None:
        self._labels["Name"].setText(
            info.get("longName") or info.get("shortName") or symbol
        )
        self._labels["Sector"].setText(info.get("sector") or info.get("quoteType") or "—")

        if last_close is not None:
            self._labels["Last Price"].setText(_fmt_num(last_close, 2))
        if last_close is not None and prev_close is not None and prev_close != 0:
            change = last_close - prev_close
            pct = (change / prev_close) * 100
            color = "#26a69a" if change >= 0 else "#ef5350"
            sign = "+" if change >= 0 else ""
            self._labels["Day Change"].setText(
                f"<span style='color:{color}'>{sign}{change:,.2f} ({sign}{pct:,.2f}%)</span>"
            )

        self._labels["Market Cap"].setText(_fmt_money(info.get("marketCap")))
        self._labels["P/E (trailing)"].setText(_fmt_num(info.get("trailingPE")))
        self._labels["52w High"].setText(_fmt_num(info.get("fiftyTwoWeekHigh")))
        self._labels["52w Low"].setText(_fmt_num(info.get("fiftyTwoWeekLow")))
        self._labels["Volume"].setText(_fmt_money(info.get("volume")))
