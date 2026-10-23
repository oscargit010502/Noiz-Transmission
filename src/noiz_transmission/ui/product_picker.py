"""Inline product selection with independent category and manufacturer filters."""

from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QSplitter,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)

from noiz_transmission.catalog import CatalogEntry, search_entries


class CompactProductDelegate(QStyledItemDelegate):
    """Keep native painting and selection with DPI-aware, single-line rows."""

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        return QSize(size.width(), option.fontMetrics.height() + 2)


class ProductPicker(QWidget):
    """Filtering never changes a material; selecting a product emits its snapshot."""

    entrySelected = Signal(object)

    def __init__(self, entries: Iterable[CatalogEntry] = (), kind=None, parent=None):
        super().__init__(parent)
        self.entries = tuple(entries)
        self._kind = kind
        self._selected_entry: CatalogEntry | None = None
        self._refreshing = False
        self._by_id: dict[str, CatalogEntry] = {}
        self.count_label = QLabel()
        self.count_label.setObjectName("muted")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search · nombre del producto, categoría o fabricante")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setAccessibleName("Buscar productos")
        self.search_row = QHBoxLayout()
        self.search_row.setContentsMargins(0, 0, 0, 0)
        self.search_row.setSpacing(4)
        self.search_row.addWidget(self.search_edit, 1)
        layout.addLayout(self.search_row)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.products_list = QListWidget()
        self.category_list = QListWidget()
        self.manufacturer_list = QListWidget()
        for title, widget in (("Products", self.products_list),
                              ("Category", self.category_list),
                              ("Manufacturer", self.manufacturer_list)):
            container = QWidget()
            column = QVBoxLayout(container)
            column.setContentsMargins(0, 0, 0, 0)
            column.setSpacing(1)
            heading = QLabel(title)
            heading.setObjectName("pickerHeading")
            headings = QHBoxLayout()
            headings.setContentsMargins(0, 0, 0, 0)
            headings.addWidget(heading)
            if widget is self.products_list:
                headings.addWidget(self.count_label, 1, Qt.AlignmentFlag.AlignRight)
            column.addLayout(headings)
            widget.setAccessibleName(title)
            widget.setMinimumHeight(100)
            widget.setMinimumWidth(80)
            widget.setAlternatingRowColors(True)
            widget.setUniformItemSizes(True)
            compact_font = QFont(widget.font())
            compact_font.setPointSizeF(8)
            widget.setFont(compact_font)
            widget.setItemDelegate(CompactProductDelegate(widget))
            widget.setSpacing(0)
            widget.setTextElideMode(Qt.TextElideMode.ElideRight)
            column.addWidget(widget)
            self.splitter.addWidget(container)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 1)
        self.splitter.setSizes([460, 160, 170])
        layout.addWidget(self.splitter, 1)
        self.search_edit.textChanged.connect(self._refresh_products)
        self.category_list.currentItemChanged.connect(self._refresh_products)
        self.manufacturer_list.currentItemChanged.connect(self._refresh_products)
        self.products_list.currentItemChanged.connect(self._product_selected)
        self.set_entries(self.entries)

    @property
    def selected_entry(self) -> CatalogEntry | None:
        return self._selected_entry

    def _family_entries(self) -> tuple[CatalogEntry, ...]:
        kinds = (self._kind,) if isinstance(self._kind, str) else self._kind
        return tuple(entry for entry in self.entries if kinds is None or entry.kind in kinds)

    @staticmethod
    def _filter_value(widget: QListWidget) -> str | None:
        item = widget.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    @staticmethod
    def _fill_filter(widget: QListWidget, values: Iterable[str], all_label: str) -> None:
        previous = ProductPicker._filter_value(widget)
        widget.blockSignals(True)
        widget.clear()
        first = QListWidgetItem(all_label)
        first.setData(Qt.ItemDataRole.UserRole, None)
        widget.addItem(first)
        restore = 0
        for index, value in enumerate(sorted(set(values), key=str.casefold), start=1):
            item = QListWidgetItem(value if value else "Sin indicar")
            item.setData(Qt.ItemDataRole.UserRole, value)
            widget.addItem(item)
            if previous == value:
                restore = index
        widget.setCurrentRow(restore)
        widget.blockSignals(False)

    def set_entries(self, entries: Iterable[CatalogEntry]) -> None:
        self.entries = tuple(entries)
        self._by_id = {entry.id: entry for entry in self.entries}
        family = self._family_entries()
        self._fill_filter(self.category_list, (e.category for e in family), "All Categories")
        self._fill_filter(self.manufacturer_list, (e.manufacturer for e in family),
                          "All Manufacturers")
        self._refresh_products()

    def set_kind(self, kind) -> None:
        self._kind = kind
        self.set_entries(self.entries)

    def select_entry(self, entry_id: str | None) -> None:
        """Restore a project selection without assigning a product to that project."""
        self._selected_entry = self._by_id.get(entry_id)
        self._refresh_products()

    def _refresh_products(self, *_args) -> None:
        if self._refreshing:
            return
        self._refreshing = True
        try:
            selected_id = self._selected_entry.id if self._selected_entry else None
            family = self._family_entries()
            category = self._filter_value(self.category_list)
            manufacturer = self._filter_value(self.manufacturer_list)
            matches = search_entries(family, query=self.search_edit.text(),
                                     category=category, manufacturer=manufacturer)
            self.products_list.blockSignals(True)
            self.products_list.clear()
            selected_row = -1
            for index, entry in enumerate(matches):
                item = QListWidgetItem(entry.name)
                item.setData(Qt.ItemDataRole.UserRole, entry.id)
                thickness = entry.properties.get("thickness_m")
                detail = f"{entry.manufacturer or 'Sin fabricante'} · {entry.category}"
                if isinstance(thickness, (float, int)):
                    detail += f" · {thickness * 1000:g} mm"
                item.setToolTip(f"{entry.name}\n{detail}\nFuente: {entry.source_file}")
                self.products_list.addItem(item)
                if entry.id == selected_id:
                    selected_row = index
            self.products_list.setCurrentRow(selected_row)
            self.products_list.blockSignals(False)
            note = " · selección actual fuera del filtro" if selected_id and selected_row < 0 else ""
            self.count_label.setText(f"{len(matches):,}" + (" · fuera del filtro" if note else ""))
            self.count_label.setToolTip(f"{len(matches):,} productos{note}")
        finally:
            self._refreshing = False

    def _product_selected(self, item: QListWidgetItem | None, _previous=None) -> None:
        if self._refreshing or item is None:
            return
        entry = self._by_id.get(item.data(Qt.ItemDataRole.UserRole))
        if entry is not None:
            self._selected_entry = entry
            self.entrySelected.emit(entry)
