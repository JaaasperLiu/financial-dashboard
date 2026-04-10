"""Watchlist sidebar with add/remove + live quote refresh."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.data import db
from app.data.yahoo_client import Quote


class WatchlistPanel(QGroupBox):
    symbol_selected = pyqtSignal(str)

    def __init__(self, watchlist_id: int, parent: QWidget | None = None):
        super().__init__("Watchlist", parent)
        self._watchlist_id = watchlist_id

        layout = QVBoxLayout(self)

        add_row = QHBoxLayout()
        self._symbol_input = QLineEdit()
        self._symbol_input.setPlaceholderText("Symbol (e.g. AAPL, BTC-USD)")
        self._asset_type = QComboBox()
        self._asset_type.addItems(["stock", "crypto"])
        add_btn = QPushButton("Add")
        add_btn.clicked.connect(self._on_add_clicked)
        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(self._on_remove_clicked)
        add_row.addWidget(self._symbol_input, 2)
        add_row.addWidget(self._asset_type, 1)
        add_row.addWidget(add_btn)
        add_row.addWidget(remove_btn)
        layout.addLayout(add_row)

        self._list = QListWidget()
        self._list.setAlternatingRowColors(True)
        # Enable in-list drag-and-drop reordering.
        self._list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self._list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._list.setMovement(QListWidget.Movement.Snap)
        self._list.currentItemChanged.connect(self._on_current_changed)
        # Persist new order after a drag-drop move.
        self._list.model().rowsMoved.connect(self._on_rows_moved)
        layout.addWidget(self._list, 1)

        hint = QLabel(
            "<i>Tip: drag rows to reorder</i>"
        )
        hint.setStyleSheet("color: #9aa0a6; font-size: 9pt;")
        layout.addWidget(hint)

        self._symbol_input.returnPressed.connect(self._on_add_clicked)

        self.reload()

    # ---------- public API ----------

    def symbols(self) -> list[str]:
        return [
            self._list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self._list.count())
        ]

    def current_symbol(self) -> str | None:
        item = self._list.currentItem()
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def reload(self) -> None:
        self._list.clear()
        for row in db.list_watchlist(self._watchlist_id):
            item = QListWidgetItem(f"{row['symbol']}    —")
            item.setData(Qt.ItemDataRole.UserRole, row["symbol"])
            self._list.addItem(item)
        if self._list.count() > 0:
            self._list.setCurrentRow(0)

    def apply_quotes(self, quotes: dict[str, Quote]) -> None:
        for i in range(self._list.count()):
            item = self._list.item(i)
            sym = item.data(Qt.ItemDataRole.UserRole)
            q = quotes.get(sym)
            if q is None:
                continue
            arrow = "▲" if q.change >= 0 else "▼"
            item.setText(
                f"{sym:<10}  {q.last:>10,.2f}   {arrow} {q.change_pct:+.2f}%"
            )
            color = Qt.GlobalColor.green if q.change >= 0 else Qt.GlobalColor.red
            item.setForeground(color)

    # ---------- slots ----------

    def _on_add_clicked(self) -> None:
        sym = self._symbol_input.text().strip().upper()
        if not sym:
            return
        asset_type = self._asset_type.currentText()
        try:
            db.add_symbol(self._watchlist_id, sym, asset_type)
        except Exception as exc:
            QMessageBox.warning(self, "Add failed", str(exc))
            return
        self._symbol_input.clear()
        self.reload()
        # Select the newly added one if found.
        for i in range(self._list.count()):
            if self._list.item(i).data(Qt.ItemDataRole.UserRole) == sym:
                self._list.setCurrentRow(i)
                break

    def _on_remove_clicked(self) -> None:
        sym = self.current_symbol()
        if not sym:
            return
        db.remove_symbol(self._watchlist_id, sym)
        self.reload()

    def _on_current_changed(self, current: QListWidgetItem | None, _prev) -> None:
        if current is None:
            return
        sym = current.data(Qt.ItemDataRole.UserRole)
        if sym:
            self.symbol_selected.emit(sym)

    def _on_rows_moved(self, *_args) -> None:
        """Persist the new visual order to SQLite after a drag-drop."""
        try:
            db.set_watchlist_order(self._watchlist_id, self.symbols())
        except Exception as exc:
            QMessageBox.warning(self, "Reorder failed", str(exc))
