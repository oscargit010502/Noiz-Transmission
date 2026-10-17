"""Searchable local libraries and explicit, user-owned isotropic material records."""

from __future__ import annotations

import hashlib
import html
import json
import uuid
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from noiz_transmission.catalog import (
    CATALOG_KINDS,
    CatalogEntry,
    catalog_references,
    default_catalog_path,
    import_xml,
    merge_catalog,
    safe_reference_url,
    save_catalog,
    search_entries,
)

KIND_NAMES = {
    "material": "Materiales", "profile": "Perfiles", "glazing": "Vidrios",
    "floor_cover": "Revestimientos", "absorption": "Absorbentes", "core": "Núcleos",
    "stud": "Montantes", "connection": "Conexiones / sistemas de montaje",
}


def _cell(value: object) -> QTableWidgetItem:
    item = QTableWidgetItem(str(value))
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    item.setToolTip(str(value))
    return item


def _label(text: str) -> QLabel:
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(True)
    return widget


def _number(minimum: float, maximum: float, decimals: int, value: float) -> QDoubleSpinBox:
    widget = QDoubleSpinBox()
    widget.setRange(minimum, maximum)
    widget.setDecimals(decimals)
    widget.setValue(value)
    widget.setKeyboardTracking(False)
    return widget


class MaterialEditor(QDialog):
    """Create a new record; an imported record is never modified in place."""

    def __init__(self, original: CatalogEntry | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.original = original
        self.setWindowTitle("Material propio · placa isótropa")
        self.setMinimumWidth(500)
        layout = QVBoxLayout(self)
        layout.addWidget(_label(
            "Define las propiedades de una placa homogénea. La copia conserva la referencia "
            "de origen y se guarda como un nuevo material; verifica los valores antes de calcular."
        ))
        form = QFormLayout()
        props = original.properties if original else {}

        def value(key: str, fallback: float) -> float:
            found = props.get(key)
            return float(found) if type(found) in (int, float) else fallback

        self.name_edit = QLineEdit(f"{original.name} · copia" if original else "Mi material")
        self.category_edit = QLineEdit(original.category if original else "Propios")
        self.manufacturer_edit = QLineEdit(original.manufacturer if original else "Definido por usuario")
        self.source_edit = QLineEdit()
        self.source_edit.setPlaceholderText("Referencia, ficha técnica o hipótesis utilizada")
        self.thickness = _number(0.001, 5000, 3, value("thickness_m", 0.0125) * 1000)
        self.density = _number(0.001, 100000, 3, value("density_kg_m3", 800))
        self.modulus = _number(0.000001, 100000, 6, value("young_modulus_pa", 2.5e9) / 1e9)
        self.loss = _number(0, 10, 5, value("loss_factor", 0.02))
        self.poisson = _number(-0.999, 0.499, 4, value("poisson_ratio", 0.3))
        self.kind_combo = QComboBox()
        self.kind_combo.addItem("Material", "material")
        self.kind_combo.addItem("Vidrio monolítico", "glazing")
        if original and original.kind == "glazing":
            self.kind_combo.setCurrentIndex(1)
        for label, widget in (
            ("Nombre", self.name_edit), ("Familia", self.kind_combo),
            ("Categoría", self.category_edit), ("Fabricante / autor", self.manufacturer_edit),
            ("Espesor [mm]", self.thickness), ("Densidad [kg/m³]", self.density),
            ("Módulo de Young [GPa]", self.modulus), ("Factor de pérdidas η [−]", self.loss),
            ("Coeficiente de Poisson ν [−]", self.poisson), ("Procedencia", self.source_edit),
        ):
            form.addRow(label, widget)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Guardar material propio")
        buttons.accepted.connect(self._accept_valid)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _accept_valid(self) -> None:
        if not self.name_edit.text().strip() or not self.source_edit.text().strip():
            QMessageBox.information(self, "Material incompleto", "Indica un nombre y la procedencia.")
            return
        self.accept()

    def build_entry(self) -> CatalogEntry:
        name = self.name_edit.text().strip()
        source = self.source_edit.text().strip()
        if not name or not source:
            raise ValueError("Nombre y procedencia son obligatorios.")
        props = {
            "thickness_m": self.thickness.value() / 1000,
            "density_kg_m3": self.density.value(),
            "young_modulus_pa": self.modulus.value() * 1e9,
            "loss_factor": self.loss.value(), "poisson_ratio": self.poisson.value(),
            "anisotropic_ratio": 1.0, "orthotropic_ratio": 1.0,
            "material_type": "Isotropic", "solid_model_eligible": True,
            "units_schema_verified": True, "user_defined": True,
            "measurement_verified": False,
        }
        raw = {"Name": name, "UserSource": source}
        if self.original:
            raw["Parent/ID"] = self.original.id
            raw["Parent/SourceFile"] = self.original.source_file
            raw["Parent/SHA256"] = self.original.source_sha256
        digest = hashlib.sha256(json.dumps(
            {"name": name, "properties": props, "raw": raw}, sort_keys=True,
        ).encode()).hexdigest()
        identifier = f"custom-{uuid.uuid4()}"
        return CatalogEntry(
            id=identifier, kind=self.kind_combo.currentData(), name=name,
            category=self.category_edit.text().strip() or "Propios",
            manufacturer=self.manufacturer_edit.text().strip() or "Usuario",
            countries=self.original.countries if self.original else (),
            properties=props, raw_fields=raw, source_file="user-defined",
            source_sha256=digest, original_id=identifier,
            warnings=("Propiedades definidas por el usuario; sin validación experimental.",),
        )


class CatalogDialog(QDialog):
    """Filter all local families, inspect raw fields and import without mutating originals."""

    def __init__(self, entries, parent=None, kind=None, selection_enabled=True):
        super().__init__(parent)
        self.entries = tuple(entries)
        self.selected_entry: CatalogEntry | None = None
        self.selection_enabled = selection_enabled
        self.allowed_kinds = tuple(CATALOG_KINDS if kind is None else (
            (kind,) if isinstance(kind, str) else kind
        ))
        self._visible: tuple[CatalogEntry, ...] = ()
        self.setWindowTitle("Noiz Transmission · Biblioteca de materiales")
        self.resize(1180, 730)
        self.setMinimumSize(820, 540)
        root = QVBoxLayout(self)
        heading = QHBoxLayout()
        heading.addWidget(_label("BIBLIOTECA LOCAL · Propiedades y procedencia"), 1)
        self.import_button = QPushButton("Importar XML…")
        self.new_button = QPushButton("Nuevo material…")
        self.copy_button = QPushButton("Crear copia editable…")
        heading.addWidget(self.import_button)
        heading.addWidget(self.new_button)
        heading.addWidget(self.copy_button)
        root.addLayout(heading)
        filters = QHBoxLayout()
        self.kind_combo = QComboBox()
        if len(self.allowed_kinds) > 1:
            self.kind_combo.addItem("Todas las familias", None)
        for item in self.allowed_kinds:
            self.kind_combo.addItem(KIND_NAMES[item], item)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Buscar producto, categoría, fabricante…")
        self.category_combo, self.manufacturer_combo, self.country_combo = (
            QComboBox(), QComboBox(), QComboBox()
        )
        self.origin_combo = QComboBox()
        self.origin_combo.addItem("Todos los orígenes", None)
        self.origin_combo.addItem("Importados", "imported")
        self.origin_combo.addItem("Propios", "custom")
        for widget in (self.kind_combo, self.search_edit, self.category_combo,
                       self.manufacturer_combo, self.country_combo, self.origin_combo):
            filters.addWidget(widget)
        filters.setStretch(1, 2)
        root.addLayout(filters)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Producto", "Categoría", "Fabricante", "Espesor [mm]"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(False)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for index in (1, 2, 3):
            self.table.horizontalHeader().setSectionResizeMode(index, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(1, 110)
        self.table.setColumnWidth(2, 130)
        self.table.setColumnWidth(3, 90)
        splitter.addWidget(self.table)
        detail = QWidget()
        layout = QVBoxLayout(detail)
        self.title = _label("Selecciona un registro")
        self.title.setStyleSheet("font-weight: 600; font-size: 15px")
        layout.addWidget(self.title)
        self.detail_tabs = QTabWidget()
        self.property_table = QTableWidget(0, 2)
        self.property_table.setHorizontalHeaderLabels(["Propiedad", "Valor"])
        self.property_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.property_table.verticalHeader().hide()
        self.raw_table = QTableWidget(0, 2)
        self.raw_table.setHorizontalHeaderLabels(["Campo de origen", "Valor original"])
        self.raw_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.raw_table.verticalHeader().hide()
        self.provenance = QTextEdit()
        self.provenance.setReadOnly(True)
        self.reference_browser = QTextBrowser()
        self.reference_browser.setOpenLinks(False)
        self.reference_browser.setOpenExternalLinks(False)
        self.reference_browser.anchorClicked.connect(self._open_reference)
        self.detail_tabs.addTab(self.property_table, "Propiedades")
        self.detail_tabs.addTab(self.provenance, "Procedencia")
        self.detail_tabs.addTab(self.reference_browser, "Referencias")
        self.detail_tabs.addTab(self.raw_table, "Campos XML")
        layout.addWidget(self.detail_tabs, 1)
        splitter.addWidget(detail)
        splitter.setSizes([730, 420])
        root.addWidget(splitter, 1)
        self.count_label = _label("")
        root.addWidget(self.count_label)
        self.notice = _label(
            "Los registros importados conservan sus parámetros de origen. "
            "La importación no convierte sus curvas en ensayos verificados."
        )
        root.addWidget(self.notice)
        bottom = QHBoxLayout()
        bottom.addStretch()
        self.use_button = QPushButton("Usar selección")
        self.use_button.setEnabled(False)
        self.use_button.setVisible(selection_enabled)
        self.close_button = QPushButton("Cerrar")
        bottom.addWidget(self.use_button)
        bottom.addWidget(self.close_button)
        root.addLayout(bottom)
        self.import_button.clicked.connect(self.import_files)
        self.new_button.clicked.connect(self.new_material)
        self.copy_button.clicked.connect(self.copy_material)
        self.close_button.clicked.connect(self.reject)
        self.use_button.clicked.connect(self._accept_selection)
        self.table.itemSelectionChanged.connect(self._show_selection)
        self.table.itemDoubleClicked.connect(self._accept_selection)
        self.kind_combo.currentIndexChanged.connect(self._family_changed)
        for combo in (self.category_combo, self.manufacturer_combo,
                      self.country_combo, self.origin_combo):
            combo.currentIndexChanged.connect(self._refresh)
        self.search_edit.textChanged.connect(self._refresh)
        self._family_changed()

    def _family_changed(self) -> None:
        family = self.kind_combo.currentData()
        entries = [entry for entry in self.entries if entry.kind in self.allowed_kinds
                   and (family is None or entry.kind == family)]
        for combo, label, values in (
            (self.category_combo, "Todas las categorías", {e.category for e in entries}),
            (self.manufacturer_combo, "Todos los fabricantes", {e.manufacturer for e in entries}),
            (self.country_combo, "Todos los países", {c for e in entries for c in e.countries}),
        ):
            current = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(label, None)
            for value in sorted(filter(None, values), key=str.casefold):
                combo.addItem(value, value)
            index = combo.findData(current)
            combo.setCurrentIndex(max(0, index))
            combo.blockSignals(False)
        self._refresh()

    def _refresh(self) -> None:
        entries = tuple(e for e in self.entries if e.kind in self.allowed_kinds)
        entries = search_entries(
            entries, query=self.search_edit.text(), kind=self.kind_combo.currentData(),
            category=self.category_combo.currentData(),
            manufacturer=self.manufacturer_combo.currentData(),
            country=self.country_combo.currentData(),
        )
        origin = self.origin_combo.currentData()
        if origin:
            entries = tuple(e for e in entries if bool(e.properties.get("user_defined"))
                            == (origin == "custom"))
        self._visible = entries
        self.table.blockSignals(True)
        self.table.clearSelection()
        self.table.setCurrentCell(-1, -1)
        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            thickness = entry.properties.get("thickness_m")
            display = f"{float(thickness) * 1000:g}" if type(thickness) in (int, float) else "—"
            for col, value in enumerate((entry.name, entry.category, entry.manufacturer, display)):
                self.table.setItem(row, col, _cell(value))
        self.table.setUpdatesEnabled(True)
        self.table.blockSignals(False)
        self.count_label.setText(f"{len(entries):,} resultados · {len(self.entries):,} registros locales")
        self.selected_entry = None
        self.use_button.setEnabled(False)
        self.copy_button.setEnabled(False)
        self.title.setText("Selecciona un registro")
        self.property_table.setRowCount(0)
        self.raw_table.setRowCount(0)
        self.provenance.clear()
        self.reference_browser.clear()

    def _show_selection(self) -> None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self._visible):
            return
        entry = self._visible[row]
        self.selected_entry = entry
        self.title.setText(entry.name)
        props = entry.properties
        rows: list[tuple[str, object]] = [
            ("Familia", KIND_NAMES[entry.kind]), ("Tipo", props.get("material_type", "—")),
            ("Categoría", entry.category), ("Fabricante", entry.manufacturer),
        ]
        for key, label, factor in (
            ("thickness_m", "Espesor [mm]", 1000),
            ("density_kg_m3", "Densidad [kg/m³]", 1),
            ("young_modulus_pa", "Módulo de Young [GPa]", 1e-9),
            ("loss_factor", "Factor de pérdidas η [−]", 1),
            ("poisson_ratio", "Poisson ν [−]", 1),
            ("anisotropic_ratio", "Relación anisótropa [−]", 1),
            ("damping_raw", "Damping XML (sin interpretar)", 1),
            ("flow_resistivity_pa_s_m2", "Resistividad [Pa·s/m²]", 1),
            ("stud_depth_m", "Profundidad de montante [mm]", 1000),
            ("stud_width_m", "Ancho de montante [mm]", 1000),
            ("material_thickness_m", "Espesor de material del montante [mm]", 1000),
            ("stud_spacing_m", "Separación de montantes [mm]", 1000),
            ("cavity_width_m", "Ancho de cámara [mm]", 1000),
            ("defined_stud_spacing_m", "Separación declarada [mm]", 1000),
            ("brace_spacing_m", "Separación de arriostramiento [mm]", 1000),
        ):
            value = props.get(key)
            if type(value) in (int, float):
                rows.append((label, f"{value * factor:.8g}"))
        rows.append(("Placa isótropa calculable", "Sí" if props.get("solid_model_eligible") else "No"))
        self._fill(self.property_table, rows)
        self._fill(self.raw_table, sorted(entry.raw_fields.items()))
        source_version = props.get("source_version", "Propio")
        self.provenance.setPlainText(
            f"Archivo: {entry.source_file}\nVersión de origen: {source_version} "
            f"{props.get('source_release', '')}\nRegistro: {entry.original_id}\n"
            f"SHA-256: {entry.source_sha256}\nPaíses: {', '.join(entry.countries) or 'Sin especificar'}\n\n"
            + "\n\n".join(entry.warnings)
        )
        references = catalog_references(entry)
        if references:
            self.reference_browser.setHtml(
                "<p>Enlaces declarados en el registro de origen. Abrir un enlace no "
                "verifica sus dimensiones ni incorpora un modelo BIM.</p>"
                + "".join(
                    f"<p><b>{html.escape(reference.field)}</b><br>"
                    f'<a href="{html.escape(reference.url, quote=True)}">'
                    f"{html.escape(reference.url)}</a></p>"
                    for reference in references
                )
            )
        else:
            self.reference_browser.setPlainText(
                "Este registro no contiene enlaces web utilizables a planos, fichas técnicas "
                "u objetos BIM. El nombre y el fabricante se conservan como referencia; "
                "no se infiere geometría de herrajes a partir del nombre del producto."
            )
        self.use_button.setEnabled(self.selection_enabled)
        self.copy_button.setEnabled(entry.kind in ("material", "glazing")
                                    and bool(props.get("solid_model_eligible")))

    @staticmethod
    def _fill(table: QTableWidget, pairs) -> None:
        table.setRowCount(len(pairs))
        for row, pair in enumerate(pairs):
            for col, value in enumerate(pair):
                table.setItem(row, col, _cell(value))

    def _open_reference(self, url: QUrl) -> None:
        """Only an explicit click on a reference belonging to the selected record opens a browser."""
        candidate = url.toString(QUrl.ComponentFormattingOption.FullyEncoded)
        if (self.selected_entry is not None and safe_reference_url(candidate)
                and any(url == QUrl(reference.url) for reference in
                        catalog_references(self.selected_entry))):
            QDesktopServices.openUrl(url)

    def _accept_selection(self, *_args) -> None:
        if self.selection_enabled and self.selected_entry is not None:
            self.accept()

    def import_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Importar bibliotecas", "", "Biblioteca XML (*.xml)")
        if not paths:
            return
        try:
            results = [import_xml(Path(path)) for path in paths]
            combined = merge_catalog(self.entries, tuple(e for r in results for e in r.entries))
            save_catalog(combined, default_catalog_path())
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "No se pudo importar", str(exc))
            return
        self.entries = combined
        self._family_changed()
        imported = sum(len(result.entries) for result in results)
        self.notice.setText(
            f"Importados {imported:,} registros de {len(results)} archivo(s). "
            "Consulta sus observaciones en Procedencia."
        )

    def new_material(self) -> None:
        self._edit_material(None)

    def copy_material(self) -> None:
        if self.selected_entry is not None:
            self._edit_material(self.selected_entry)

    def _edit_material(self, original: CatalogEntry | None) -> None:
        editor = MaterialEditor(original, self)
        if editor.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            entry = editor.build_entry()
            combined = merge_catalog(self.entries, (entry,))
            save_catalog(combined, default_catalog_path())
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "No se pudo guardar", str(exc))
            return
        self.entries = combined
        self.search_edit.clear()
        index = self.kind_combo.findData(entry.kind)
        if index >= 0:
            self.kind_combo.setCurrentIndex(index)
        self.origin_combo.setCurrentIndex(0)
        for combo in (self.category_combo, self.manufacturer_combo, self.country_combo):
            combo.setCurrentIndex(0)
        self._family_changed()
        for row, found in enumerate(self._visible):
            if found.id == entry.id:
                self.table.selectRow(row)
                break
