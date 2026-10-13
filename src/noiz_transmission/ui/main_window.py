"""Construction-centred desktop workbench with immutable inputs and async prediction."""

from __future__ import annotations

import math
import sys
from dataclasses import replace
from pathlib import Path
from threading import Event

import pyqtgraph as pg
from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal, Slot
from PySide6.QtGui import QAction, QCloseEvent, QFont, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTabBar,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QToolBar,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from noiz_transmission.application.assemblies import (
    AssemblyPrediction,
    AssemblyProject,
    Cavity,
    Layer,
    Panel,
)
from noiz_transmission.application.assembly_services import (
    default_project,
    export_assembly_csv,
    export_assembly_html,
    layer_from_entry,
    load_assembly,
    predict_assembly,
    save_assembly,
)
from noiz_transmission.catalog import (
    default_catalog_path,
    import_xml,
    load_catalog,
    merge_catalog,
    save_catalog,
)
from noiz_transmission.ui.section_view import SectionView
from noiz_transmission.ui.style import STYLESHEET

COLORS = ("#007c99", "#b87328", "#7868ac", "#48866f", "#b8596b", "#4d82bd")
ELEMENTS = (("Muro", "wall"), ("Cielorraso", "ceiling"), ("Suelo", "floor"),
            ("Cubierta", "roof"), ("Vidrio", "glazing"), ("Puerta", "door"))


def label(text: str, name: str = "", wrap: bool = False) -> QLabel:
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setObjectName(name)
    widget.setWordWrap(wrap)
    return widget


def cell(text: object) -> QTableWidgetItem:
    item = QTableWidgetItem(str(text))
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    item.setToolTip(str(text))
    return item


def table(headers: list[str]) -> QTableWidget:
    widget = QTableWidget(0, len(headers))
    widget.setHorizontalHeaderLabels(headers)
    widget.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    widget.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
    widget.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    widget.setAlternatingRowColors(True)
    widget.setWordWrap(False)
    widget.verticalHeader().hide()
    widget.verticalHeader().setDefaultSectionSize(29)
    widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    widget.horizontalHeader().setStretchLastSection(True)
    return widget


def spin(minimum: float, maximum: float, value: float = 0, decimals: int = 3) -> QDoubleSpinBox:
    widget = QDoubleSpinBox()
    widget.setRange(minimum, maximum)
    widget.setDecimals(decimals)
    widget.setValue(value)
    widget.setKeyboardTracking(False)
    widget.setMinimumWidth(88)
    return widget


def display_value(widget: QDoubleSpinBox | QSpinBox, value: float | int) -> None:
    """Show valid project inputs without silently clipping to a UI convenience range."""
    if isinstance(widget, QDoubleSpinBox) and 0 < abs(value) < 10 ** -widget.decimals():
        widget.setDecimals(min(323, math.ceil(-math.log10(abs(value))) + 2))
    if value < widget.minimum():
        widget.setMinimum(value)
    if value > widget.maximum():
        widget.setMaximum(value)
    widget.setValue(value)
    widget.setToolTip(f"Valor del proyecto: {value!r}")


class _WorkerSignals(QObject):
    finished = Signal(int, object, object)


class _PredictionWorker(QRunnable):
    def __init__(self, generation: int, project: AssemblyProject):
        super().__init__()
        self.generation = generation
        self.project = project
        self.signals = _WorkerSignals()
        self.cancel_event = Event()

    @Slot()
    def run(self) -> None:
        try:
            result, error = predict_assembly(self.project, cancel_event=self.cancel_event), None
        except Exception as exc:  # Deliver domain / numerical errors without killing the Qt event loop.
            result, error = None, str(exc)
        self.signals.finished.emit(self.generation, result, error)


class MainWindow(QMainWindow):
    """Three-leaf assembly editor; project snapshots never depend on the active library."""

    def __init__(self) -> None:
        super().__init__()
        self.project = default_project()
        self._saved_project = self.project
        self._current_path: Path | None = None
        self._loading = False
        self._generation = 0
        self._busy = False
        self._closing = False
        self._input_error = ""
        self._field_errors: dict[str, str] = {}
        self._selected_panel = 0
        self._selected_layer = 0
        self._selected_cavity = 0
        self.current_result: AssemblyPrediction | None = None
        self.predictions: list[AssemblyPrediction] = []
        self._comparison_dirty = False
        self._worker: _PredictionWorker | None = None
        self._pool = QThreadPool.globalInstance()
        try:
            self.entries = load_catalog(default_catalog_path())
            catalog_error = ""
        except (OSError, ValueError) as exc:
            self.entries = ()
            catalog_error = str(exc)
        self.resize(1380, 880)
        self.setMinimumSize(900, 650)
        self.setStyleSheet(STYLESHEET)
        self._build_actions()
        content = QWidget()
        content.setObjectName("workspace")
        root = QVBoxLayout(content)
        root.setContentsMargins(10, 8, 10, 5)
        root.setSpacing(8)
        root.addLayout(self._header())
        body = QHBoxLayout()
        body.setSpacing(9)
        body.addWidget(self._sidebar())
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.setHandleWidth(5)
        self.main_splitter.addWidget(self._construction())
        self.right_splitter = QSplitter(Qt.Orientation.Vertical)
        self.right_splitter.setChildrenCollapsible(False)
        self.right_splitter.setHandleWidth(5)
        self.right_splitter.addWidget(self._editor())
        self.results_panel = self._results()
        self.right_splitter.addWidget(self.results_panel)
        self.right_splitter.setStretchFactor(0, 3)
        self.right_splitter.setStretchFactor(1, 1)
        self.right_splitter.setSizes([470, 245])
        self.main_splitter.addWidget(self.right_splitter)
        self.main_splitter.setStretchFactor(0, 1)
        self.main_splitter.setStretchFactor(1, 3)
        self.main_splitter.setSizes([310, 930])
        body.addWidget(self.main_splitter, 1)
        root.addLayout(body, 1)
        self.setCentralWidget(content)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setMaximumWidth(120)
        self.progress.setMaximumHeight(4)
        self.progress.hide()
        self.statusBar().addPermanentWidget(self.progress)
        self._render_project()
        self.statusBar().showMessage("Listo · Edita la composición y calcula el aislamiento aéreo.")
        if catalog_error:
            self._error(f"No se pudo leer la biblioteca: {catalog_error}")

    def _action(self, text: str, slot, shortcut: str | None = None) -> QAction:
        action = QAction(text, self)
        action.triggered.connect(slot)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        return action

    def _build_actions(self) -> None:
        self.new_action = self._action("Nuevo", self.new_project, "Ctrl+N")
        self.open_action = self._action("Abrir…", self.open_project, "Ctrl+O")
        self.save_action = self._action("Guardar", self.save_current_project, "Ctrl+S")
        self.save_as_action = self._action("Guardar como…", self.save_as, "Ctrl+Shift+S")
        self.import_action = self._action("Importar XML…", self.import_catalog)
        self.catalog_action = self._action("Biblioteca…", self.browse_catalog, "Ctrl+M")
        self.calculate_action = self._action("Calcular", self.calculate, "F5")
        self.export_action = self._action("Informe HTML…", self.export_results_html)
        self.csv_action = self._action("Datos CSV…", self.export_results_csv)
        menu = self.menuBar().addMenu("Archivo")
        for action in (self.new_action, self.open_action, self.save_action, self.save_as_action):
            menu.addAction(action)
        menu.addSeparator()
        menu.addAction(self.import_action)
        export_menu = menu.addMenu("Exportar")
        export_menu.addAction(self.export_action)
        export_menu.addAction(self.csv_action)
        menu.addSeparator()
        menu.addAction(self._action("Salir", self.close, "Ctrl+Q"))
        edit = self.menuBar().addMenu("Editar")
        edit.addAction(self.catalog_action)
        edit.addAction(self._action("Añadir capa", self.add_layer))
        edit.addAction(self._action("Duplicar capa", self.duplicate_layer))
        self.results_action = self._action("Mostrar resultados", self.toggle_results)
        self.results_action.setCheckable(True)
        self.results_action.setChecked(True)
        view = self.menuBar().addMenu("Ver")
        view.addAction(self.results_action)
        view.addAction(self._action("Restaurar distribución", self.restore_layout))
        help_menu = self.menuBar().addMenu("Ayuda")
        help_menu.addAction(self._action("Modelo e hipótesis…", self.show_model_details))
        help_menu.addAction(self._action("Acerca de Noiz Transmission", self.about))
        toolbar = QToolBar("Proyecto", self)
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        for action in (self.new_action, self.open_action, self.save_action):
            toolbar.addAction(action)
        toolbar.addSeparator()
        toolbar.addAction(self.import_action)
        toolbar.addAction(self.catalog_action)
        toolbar.addSeparator()
        toolbar.addAction(self.calculate_action)
        toolbar.addAction(self.export_action)
        self.addToolBar(toolbar)

    def _header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(18)
        brand = QVBoxLayout()
        brand.setSpacing(2)
        brand.addWidget(label("Noiz Transmission", "brand"))
        brand.addWidget(label("WORKBENCH  /  AISLAMIENTO AÉREO", "muted"))
        row.addLayout(brand)
        self.name_edit = QLineEdit(self.project.name)
        self.name_edit.setAccessibleName("Nombre del proyecto")
        self.name_edit.setPlaceholderText("Nombre del proyecto")
        self.name_edit.setMinimumWidth(100)
        self.name_edit.textChanged.connect(self._name_changed)
        row.addWidget(self.name_edit, 1)
        self.rw_value = self._metric(row, "Rw estimado", "— dB")
        self.mass_value = self._metric(row, "Masa superficial", "— kg/m²")
        self.thickness_value = self._metric(row, "Espesor total", "— mm")
        return row

    @staticmethod
    def _metric(row: QHBoxLayout, title: str, text: str) -> QLabel:
        column = QVBoxLayout()
        column.setSpacing(0)
        column.addWidget(label(title, "muted"))
        value = label(text, "metric")
        column.addWidget(value)
        row.addLayout(column)
        return value

    def _sidebar(self) -> QWidget:
        side = QWidget()
        side.setFixedWidth(100)
        layout = QVBoxLayout(side)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(label("ELEMENTO", "muted"))
        self.element_group = QButtonGroup(self)
        self.element_buttons: dict[str, QPushButton] = {}
        for title, key in ELEMENTS:
            button = QPushButton(title)
            button.setObjectName("nav")
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, kind=key: self._set_project_field("element_type", kind))
            self.element_group.addButton(button)
            self.element_buttons[key] = button
            layout.addWidget(button)
        layout.addStretch()
        porous = QPushButton("Absorbentes…")
        porous.setToolTip("Abrir materiales porosos de la biblioteca; no cambia el modelo a un ensayo de absorción.")
        porous.clicked.connect(lambda: self.browse_catalog(kind="absorption"))
        layout.addWidget(porous)
        layout.addWidget(label("Elemento aislado\nSin flanking", "muted", True))
        return side

    def _construction(self) -> QWidget:
        widget = QFrame()
        widget.setObjectName("sheet")
        widget.setMinimumWidth(205)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        heading = QHBoxLayout()
        heading.addWidget(label("Composición", "sectionTitle"), 1)
        self.assembly_combo = QComboBox()
        self.assembly_combo.addItems(["Simple", "Doble", "Triple"])
        self.assembly_combo.setAccessibleName("Número de paneles del elemento")
        self.assembly_combo.currentIndexChanged.connect(self._change_topology)
        heading.addWidget(self.assembly_combo)
        layout.addLayout(heading)
        self.composition_tree = QTreeWidget()
        self.composition_tree.setHeaderHidden(True)
        self.composition_tree.setMinimumHeight(110)
        self.composition_tree.setMaximumHeight(210)
        self.composition_tree.setIndentation(13)
        self.composition_tree.itemClicked.connect(self._tree_selected)
        layout.addWidget(self.composition_tree, 1)
        section_header = QHBoxLayout()
        section_header.addWidget(label("Sección", "sectionTitle"), 1)
        self.view_combo = QComboBox()
        self.view_combo.addItems(["Axonométrica", "2D"])
        self.view_combo.setMaximumWidth(112)
        section_header.addWidget(self.view_combo)
        layout.addLayout(section_header)
        self.section_view = SectionView()
        self.view_combo.currentIndexChanged.connect(lambda index: self.section_view.set_exploded(index == 0))
        layout.addWidget(self.section_view, 2)
        layout.addWidget(label("Esquema ilustrativo · espesores mínimos ampliados", "muted", True))
        self.composition_summary = label("", "muted", True)
        layout.addWidget(self.composition_summary)
        settings = QPushButton("Condiciones de cálculo…")
        settings.clicked.connect(self.show_settings)
        layout.addWidget(settings)
        return widget

    @staticmethod
    def _scroll(widget: QWidget) -> QScrollArea:
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        area.setWidget(widget)
        return area

    def _editor(self) -> QWidget:
        editor = QFrame()
        editor.setObjectName("sheet")
        editor.setMinimumWidth(400)
        editor.setMinimumHeight(240)
        layout = QVBoxLayout(editor)
        layout.setContentsMargins(9, 8, 9, 8)
        layout.setSpacing(6)
        row = QHBoxLayout()
        row.addWidget(label("EDITOR DEL ELEMENTO", "sectionTitle"), 1)
        self.library_label = label("", "muted")
        row.addWidget(self.library_label)
        layout.addLayout(row)
        self.part_tabs = QTabBar()
        self.part_tabs.setExpanding(True)
        self.part_tabs.setDrawBase(False)
        self.part_tabs.currentChanged.connect(self._part_selected)
        layout.addWidget(self.part_tabs)
        self.editor_stack = QStackedWidget()
        self.editor_stack.addWidget(self._scroll(self._panel_editor()))
        self.editor_stack.addWidget(self._scroll(self._cavity_editor()))
        layout.addWidget(self.editor_stack, 1)
        self.message_label = label("Placas isotrópicas + cámaras · predicción preliminar", "status", True)
        layout.addWidget(self.message_label)
        controls = QHBoxLayout()
        details = QPushButton("Hipótesis…")
        details.clicked.connect(self.show_model_details)
        controls.addWidget(details)
        controls.addStretch()
        self.toggle_results_button = QPushButton("Ocultar resultados")
        self.toggle_results_button.clicked.connect(self.toggle_results)
        controls.addWidget(self.toggle_results_button)
        self.calculate_button = QPushButton("Calcular  ·  F5")
        self.calculate_button.setObjectName("primary")
        self.calculate_button.clicked.connect(self.calculate)
        controls.addWidget(self.calculate_button)
        layout.addLayout(controls)
        return editor

    def _panel_editor(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(1, 5, 1, 1)
        layout.setSpacing(6)
        self.layer_table = table(["Capa / material", "N.º", "mm", "kg/m²"])
        self.layer_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.layer_table.setMinimumHeight(82)
        self.layer_table.setMaximumHeight(138)
        self.layer_table.itemSelectionChanged.connect(self._layer_selected)
        layout.addWidget(self.layer_table)
        buttons = QHBoxLayout()
        self.layer_buttons = {}
        for title, key, slot in (("+ Capa", "add", self.add_layer), ("Duplicar", "duplicate", self.duplicate_layer),
                                 ("Eliminar", "remove", self.remove_layer), ("↑", "up", lambda: self.move_layer(-1)),
                                 ("↓", "down", lambda: self.move_layer(1))):
            button = QPushButton(title)
            button.setToolTip({"up": "Mover capa hacia exterior", "down": "Mover capa hacia interior"}.get(key, title))
            button.clicked.connect(slot)
            buttons.addWidget(button)
            self.layer_buttons[key] = button
        buttons.addStretch()
        layout.addLayout(buttons)
        material_row = QHBoxLayout()
        self.layer_name_edit = QLineEdit()
        self.layer_name_edit.setAccessibleName("Nombre del material de la capa")
        self.layer_name_edit.textChanged.connect(lambda text: self._set_layer_field("name", text))
        material_row.addWidget(self.layer_name_edit, 1)
        catalog_button = QPushButton("Elegir material…")
        catalog_button.clicked.connect(self.select_material)
        material_row.addWidget(catalog_button)
        layout.addLayout(material_row)
        self.layer_fields = {}
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(5)
        definitions = [
            ("Espesor [mm]", "thickness_mm", .001, 5000, 4, 1),
            ("Densidad [kg/m³]", "density_kg_m3", .001, 100000, 3, 1),
            ("Young [GPa]", "young_modulus_pa", .000001, 10000, 6, 1e9),
            ("Factor de pérdidas η", "loss_factor", 0, 10, 5, 1),
            ("Poisson ν", "poisson_ratio", -.999, .499, 4, 1),
        ]
        for index, (title, key, low, high, precision, factor) in enumerate(definitions):
            field = spin(low, high, decimals=precision)
            field.setAccessibleName(title)
            field.valueChanged.connect(lambda value, k=key, f=factor: self._set_layer_field(k, value * f))
            self.layer_fields[key] = field
            row, column = divmod(index, 3)
            grid.addWidget(label(title, "muted"), row * 2, column)
            grid.addWidget(field, row * 2 + 1, column)
        self.count_spin = QSpinBox()
        self.count_spin.setRange(1, 100)
        self.count_spin.setKeyboardTracking(False)
        self.count_spin.valueChanged.connect(lambda value: self._set_layer_field("count", value))
        grid.addWidget(label("Placas iguales [n.º]", "muted"), 2, 2)
        grid.addWidget(self.count_spin, 3, 2)
        layout.addLayout(grid)
        self.source_label = label("", "muted", True)
        layout.addWidget(self.source_label)
        attachment_row = QHBoxLayout()
        profile = QPushButton("Perfil…")
        profile.clicked.connect(self.select_profile)
        attachment_row.addWidget(profile)
        clear_profile = QPushButton("Quitar perfil")
        clear_profile.clicked.connect(lambda: self._set_layer_field("profile", None))
        attachment_row.addWidget(clear_profile)
        self.profile_label = label("Sin perfil", "muted", True)
        attachment_row.addWidget(self.profile_label, 1)
        layout.addLayout(attachment_row)
        layout.addStretch()
        return widget

    def _cavity_editor(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(2, 5, 2, 2)
        self.cavity_fields = {}
        upper = QGridLayout()
        self.frame_combo = QComboBox()
        for title, key in (("Paneles independientes", "independent"), ("Montante de madera", "timber"), ("Montante de acero", "steel")):
            self.frame_combo.addItem(title, key)
        self.frame_combo.currentIndexChanged.connect(lambda: self._set_cavity_field("frame_type", self.frame_combo.currentData()))
        upper.addWidget(label("Conexión estructural", "muted"), 0, 0, 1, 2)
        upper.addWidget(self.frame_combo, 1, 0, 1, 2)
        for index, (title, key) in enumerate((("Cámara [mm]", "depth_mm"), ("Ancho montante [mm]", "stud_width_mm"),
                                             ("Fondo montante [mm]", "stud_depth_mm"), ("Separación [mm]", "stud_spacing_mm"))):
            field = spin(.01, 10000, decimals=3)
            field.valueChanged.connect(lambda value, k=key: self._set_cavity_field(k, value))
            self.cavity_fields[key] = field
            row, col = divmod(index, 2)
            upper.addWidget(label(title, "muted"), 2 + row * 2, col)
            upper.addWidget(field, 3 + row * 2, col)
        layout.addLayout(upper)
        self.frame_note = label("", "muted", True)
        layout.addWidget(self.frame_note)
        absorb = QGroupBox("Relleno absorbente")
        absorb_layout = QVBoxLayout(absorb)
        row = QHBoxLayout()
        self.absorber_label = label("Cámara de aire", wrap=True)
        row.addWidget(self.absorber_label, 1)
        select = QPushButton("Elegir…")
        select.clicked.connect(self.select_absorber)
        row.addWidget(select)
        clear = QPushButton("Quitar")
        clear.clicked.connect(self.clear_absorber)
        row.addWidget(clear)
        absorb_layout.addLayout(row)
        fields = QGridLayout()
        self.absorber_spin = spin(0, 10000, decimals=3)
        self.absorber_spin.valueChanged.connect(lambda value: self._set_cavity_field("absorber_thickness_mm", value))
        self.resistivity_spin = spin(0, 1e8, decimals=2)
        self.resistivity_spin.setSpecialValueText("Sin dato")
        self.resistivity_spin.valueChanged.connect(lambda value: self._set_cavity_field("flow_resistivity_pa_s_m2", value or None))
        fields.addWidget(label("Espesor [mm]", "muted"), 0, 0)
        fields.addWidget(self.absorber_spin, 1, 0)
        fields.addWidget(label("Resistividad σ [Pa·s/m²]", "muted"), 0, 1)
        fields.addWidget(self.resistivity_spin, 1, 1)
        absorb_layout.addLayout(fields)
        absorb_layout.addWidget(label("Relleno centrado en la cámara. σ requiere fuente o medida propia; Damping XML no es resistividad.", "muted", True))
        layout.addWidget(absorb)
        layout.addStretch()
        return widget

    def _results(self) -> QWidget:
        widget = QFrame()
        widget.setObjectName("sheet")
        widget.setMinimumHeight(165)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(5, 4, 5, 4)
        layout.setSpacing(2)
        self.result_tabs = QTabWidget()
        self.result_tabs.setDocumentMode(True)
        self.chart_view = pg.PlotWidget(background="#ffffff")
        self.chart_view.setMinimumHeight(100)
        self.chart_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored)
        self.plot_item = self.chart_view.getPlotItem()
        self.plot_item.setLogMode(x=True, y=False)
        self.plot_item.setLabel("bottom", "Frecuencia [Hz]", color="#476476")
        self.plot_item.setLabel("left", "R [dB]", color="#476476")
        self.plot_item.setMenuEnabled(False)
        self.plot_item.showGrid(x=True, y=True, alpha=.18)
        self.plot_item.setRange(xRange=(math.log10(50), math.log10(5000)), yRange=(0, 80), padding=.02)
        self.plot_item.getAxis("bottom").setTicks([[(math.log10(f), str(f)) for f in (50, 100, 250, 500, 1000, 2000, 5000)]])
        for key in ("bottom", "left"):
            self.plot_item.getAxis(key).setPen("#94aeba")
            self.plot_item.getAxis(key).setTextPen("#506e80")
        self.legend = self.plot_item.addLegend(offset=(8, 3), labelTextColor="#345367", brush="#ffffffdd", pen=None)
        self.traces = []
        self.result_tabs.addTab(self.chart_view, "Curva")
        self.spectrum_table = table(["Frecuencia [Hz]", "R actual [dB]"])
        self.result_tabs.addTab(self.spectrum_table, "Tabla por bandas")
        comparisons = QWidget()
        comparison_layout = QVBoxLayout(comparisons)
        comparison_layout.setContentsMargins(0, 3, 0, 0)
        self.comparison_table = table(["Alternativa guardada", "Paneles", "mm", "kg/m²", "Rw [dB]"])
        self.comparison_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        comparison_layout.addWidget(self.comparison_table)
        row = QHBoxLayout()
        self.add_comparison_button = QPushButton("Guardar resultado actual")
        self.add_comparison_button.clicked.connect(self.add_comparison)
        row.addWidget(self.add_comparison_button)
        self.remove_button = QPushButton("Quitar seleccionada")
        self.remove_button.clicked.connect(self.remove_selected)
        row.addWidget(self.remove_button)
        row.addStretch()
        csv = QPushButton("CSV…")
        csv.clicked.connect(self.export_results_csv)
        row.addWidget(csv)
        comparison_layout.addLayout(row)
        self.result_tabs.addTab(comparisons, "Comparación · 0/6")
        layout.addWidget(self.result_tabs, 1)
        self.result_status = label("Sin calcular · las comparaciones guardadas se conservan al editar", "muted")
        layout.addWidget(self.result_status)
        return widget

    def current_project(self) -> AssemblyProject:
        if self._input_error:
            raise ValueError(self._input_error)
        return self.project

    def _commit(self, project: AssemblyProject) -> None:
        changed = project != self.project
        self.project = project
        self._input_error = next(iter(self._field_errors.values()), "")
        if changed:
            if self._worker is not None:
                self._worker.cancel_event.set()
            self._generation += 1
            self.current_result = None
            self._refresh_results()
        self._refresh_summary()
        self._set_title()
        self.message_label.setObjectName("status")
        self.message_label.setText("Cambios pendientes de cálculo" if changed else "Placas isotrópicas + cámaras · predicción preliminar")
        self.message_label.setStyleSheet("")
        if self._input_error:
            self._error(self._input_error)

    def _set_title(self) -> None:
        dirty = " *" if self._editor_has_changes() else ""
        self.setWindowTitle(f"{self.project.name}{dirty} — Noiz Transmission")

    def _name_changed(self, text: str) -> None:
        self._set_project_field("name", text)

    def _set_project_field(self, key: str, value) -> None:
        if self._loading:
            return
        try:
            project = replace(self.project, **{key: value})
            self._field_errors.pop(f"project:{key}", None)
            self._commit(project)
        except (ValueError, TypeError) as exc:
            self._invalid(exc, f"project:{key}")

    def _set_layer_field(self, key: str, value) -> None:
        if self._loading:
            return
        try:
            layer = replace(self.project.panels[self._selected_panel].layers[self._selected_layer], **{key: value})
            self._field_errors.pop(f"layer:{self._selected_panel}:{self._selected_layer}:{key}", None)
            self._replace_layer(layer)
        except (ValueError, TypeError) as exc:
            self._invalid(exc, f"layer:{self._selected_panel}:{self._selected_layer}:{key}")

    def _replace_layer(self, layer: Layer) -> None:
        panel = self.project.panels[self._selected_panel]
        layers = list(panel.layers)
        layers[self._selected_layer] = layer
        panels = list(self.project.panels)
        panels[self._selected_panel] = replace(panel, layers=tuple(layers))
        self._commit(replace(self.project, panels=tuple(panels)))
        self._refresh_layer_rows()

    def _set_cavity_field(self, key: str, value) -> None:
        if self._loading or not self.project.cavities:
            return
        try:
            cavities = list(self.project.cavities)
            cavities[self._selected_cavity] = replace(cavities[self._selected_cavity], **{key: value})
            self._field_errors.pop(f"cavity:{self._selected_cavity}:{key}", None)
            self._commit(replace(self.project, cavities=tuple(cavities)))
            self._refresh_cavity_note()
        except (ValueError, TypeError) as exc:
            self._invalid(exc, f"cavity:{self._selected_cavity}:{key}")

    def _invalid(self, error: Exception, key: str) -> None:
        if self._worker is not None:
            self._worker.cancel_event.set()
        self._field_errors[key] = str(error)
        self._input_error = next(iter(self._field_errors.values()), "")
        self._generation += 1
        self.current_result = None
        self._refresh_results()
        self._error(str(error))
        self._set_title()

    def _error(self, text: str) -> None:
        self.message_label.setText(text)
        self.message_label.setObjectName("error")
        self.message_label.setStyleSheet("color: #a52b37; background: #fff0f0; border: 1px solid #ebc6cb; padding: 5px;")
        self.statusBar().showMessage(text)

    def _refresh_summary(self) -> None:
        mass = sum(layer.thickness_mm / 1000 * layer.density_kg_m3 * layer.count
                   for panel in self.project.panels for layer in panel.layers)
        thickness = sum(layer.thickness_mm * layer.count for panel in self.project.panels for layer in panel.layers)
        thickness += sum(cavity.depth_mm for cavity in self.project.cavities)
        self.mass_value.setText(f"{mass:.1f} kg/m²")
        self.thickness_value.setText(f"{thickness:g} mm")
        self.section_view.set_project(self.project, self._selected_panel)
        self.composition_summary.setText(f"{self.project.width_m:g} × {self.project.height_m:g} m · dimensiones ilustrativas\n"
                                         "Incidencia " + ("difusa" if self.project.incidence == "diffuse" else "normal"))
        self.library_label.setText(f"Biblioteca · {len(self.entries):,} registros")
        old_loading = self._loading
        self._loading = True
        self.composition_tree.clear()
        for index, panel in enumerate(self.project.panels):
            item = QTreeWidgetItem([f"Panel {index + 1} · {len(panel.layers)} capa(s)"])
            item.setData(0, Qt.ItemDataRole.UserRole, ("panel", index, 0))
            self.composition_tree.addTopLevelItem(item)
            for j, layer in enumerate(panel.layers):
                child = QTreeWidgetItem([f"{layer.count} × {layer.thickness_mm:g} mm · {layer.name}"])
                child.setToolTip(0, child.text(0))
                child.setData(0, Qt.ItemDataRole.UserRole, ("panel", index, j))
                item.addChild(child)
            item.setExpanded(True)
            if index < len(self.project.cavities):
                cavity = self.project.cavities[index]
                item = QTreeWidgetItem([f"Cámara {index + 1} · {cavity.depth_mm:g} mm"])
                item.setData(0, Qt.ItemDataRole.UserRole, ("cavity", index, 0))
                self.composition_tree.addTopLevelItem(item)
        if self.project.element_type in self.element_buttons:
            self.element_buttons[self.project.element_type].setChecked(True)
        self._loading = old_loading

    def _render_project(self) -> None:
        self._field_errors.clear()
        self._input_error = ""
        self._loading = True
        self.name_edit.setText(self.project.name)
        self.assembly_combo.setCurrentIndex(len(self.project.panels) - 1)
        self._selected_panel = min(self._selected_panel, len(self.project.panels) - 1)
        self._selected_layer = min(self._selected_layer, len(self.project.panels[self._selected_panel].layers) - 1)
        while self.part_tabs.count():
            self.part_tabs.removeTab(0)
        for index in range(len(self.project.panels)):
            position = self.part_tabs.addTab(f"Panel {index + 1}")
            self.part_tabs.setTabData(position, ("panel", index))
            if index < len(self.project.cavities):
                position = self.part_tabs.addTab(f"Cámara {index + 1}")
                self.part_tabs.setTabData(position, ("cavity", index))
        self.part_tabs.setCurrentIndex(self._selected_panel * 2)
        self._loading = False
        self._part_selected(self.part_tabs.currentIndex())
        self._refresh_summary()
        self._refresh_results()
        self._set_title()

    def _tree_selected(self, item: QTreeWidgetItem, column: int) -> None:
        if self._loading:
            return
        kind, index, layer = item.data(0, Qt.ItemDataRole.UserRole)
        self._selected_layer = layer
        self.part_tabs.setCurrentIndex(index * 2 + (1 if kind == "cavity" else 0))
        self._part_selected(self.part_tabs.currentIndex())

    def _part_selected(self, index: int) -> None:
        if self._loading or index < 0:
            return
        kind, number = self.part_tabs.tabData(index)
        if kind == "panel":
            self._selected_panel = number
            self._selected_layer = min(self._selected_layer, len(self.project.panels[number].layers) - 1)
            self.editor_stack.setCurrentIndex(0)
            self._refresh_layer_rows()
            self._show_layer()
        else:
            self._selected_cavity = number
            self.editor_stack.setCurrentIndex(1)
            self._show_cavity()
        self.section_view.set_project(self.project, self._selected_panel)

    def _refresh_layer_rows(self) -> None:
        previous_loading = self._loading
        self._loading = True
        layers = self.project.panels[self._selected_panel].layers
        self.layer_table.setRowCount(len(layers))
        self.layer_table.setFixedHeight(min(168, 32 + 29 * len(layers)))
        for row, layer in enumerate(layers):
            for col, text in enumerate((layer.name, layer.count, f"{layer.thickness_mm:g}",
                                         f"{layer.thickness_mm / 1000 * layer.density_kg_m3 * layer.count:.2f}")):
                self.layer_table.setItem(row, col, cell(text))
        self.layer_table.selectRow(self._selected_layer)
        self.layer_buttons["add"].setEnabled(len(layers) < 6)
        self.layer_buttons["duplicate"].setEnabled(len(layers) < 6)
        self.layer_buttons["remove"].setEnabled(len(layers) > 1)
        self.layer_buttons["up"].setEnabled(self._selected_layer > 0)
        self.layer_buttons["down"].setEnabled(self._selected_layer < len(layers) - 1)
        self._loading = previous_loading

    def _layer_selected(self) -> None:
        if self._loading or self.layer_table.currentRow() < 0:
            return
        self._selected_layer = self.layer_table.currentRow()
        self._show_layer()
        self._refresh_layer_rows()

    def _show_layer(self) -> None:
        prefix = f"layer:{self._selected_panel}:{self._selected_layer}:"
        self._field_errors = {k: v for k, v in self._field_errors.items() if not k.startswith(prefix)}
        self._input_error = next(iter(self._field_errors.values()), "")
        self._loading = True
        layer = self.project.panels[self._selected_panel].layers[self._selected_layer]
        self.layer_name_edit.setText(layer.name)
        for key, widget in self.layer_fields.items():
            value = getattr(layer, key)
            display_value(widget, value / 1e9 if key == "young_modulus_pa" else value)
        display_value(self.count_spin, layer.count)
        source = layer.catalog_entry
        if source and source.properties.get("data_status") == "synthetic":
            source_text = "Ejemplo sintético · propiedades editables"
        elif source:
            version = source.properties.get("source_version", "")
            version_label = f" · XML {version}" if version else ""
            source_text = (f"{source.manufacturer or 'Fabricante no indicado'} · {source.source_file}{version_label}\n"
                           "Instantánea del catálogo · conserva procedencia al editar valores")
        else:
            source_text = "Material manual · documenta las fuentes en las notas del proyecto"
        self.source_label.setText(source_text)
        self.profile_label.setText(layer.profile.name if layer.profile else "Sin perfil geométrico asociado")
        self._loading = False

    def _show_cavity(self) -> None:
        prefix = f"cavity:{self._selected_cavity}:"
        self._field_errors = {k: v for k, v in self._field_errors.items() if not k.startswith(prefix)}
        self._input_error = next(iter(self._field_errors.values()), "")
        self._loading = True
        cavity = self.project.cavities[self._selected_cavity]
        for key, widget in self.cavity_fields.items():
            display_value(widget, getattr(cavity, key))
        self.frame_combo.setCurrentIndex(self.frame_combo.findData(cavity.frame_type))
        display_value(self.absorber_spin, cavity.absorber_thickness_mm)
        display_value(self.resistivity_spin, cavity.flow_resistivity_pa_s_m2 or 0)
        self.absorber_label.setText(cavity.absorber.name if cavity.absorber else "Cámara de aire / material manual")
        self._loading = False
        self._refresh_cavity_note()

    def _refresh_cavity_note(self) -> None:
        cavity = self.project.cavities[self._selected_cavity]
        independent = cavity.frame_type == "independent"
        self.frame_note.setText("Sin puentes estructurales entre paneles." if independent else
                                "La unión por montantes se conserva en el proyecto. Su transmisión estructural aún no está implementada: el cálculo queda bloqueado.")
        for key, field in self.cavity_fields.items():
            if key != "depth_mm":
                field.setEnabled(not independent)

    def _change_topology(self, index: int) -> None:
        if self._loading:
            return
        count = index + 1
        current = len(self.project.panels)
        if count < current:
            answer = QMessageBox.question(self, "Reducir composición",
                                           f"Se eliminarán los paneles posteriores al panel {count} y sus cámaras. ¿Continuar?",
                                           QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                           QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                self._loading = True
                self.assembly_combo.setCurrentIndex(current - 1)
                self._loading = False
                return
        panels = list(self.project.panels[:count])
        cavities = list(self.project.cavities[:count - 1])
        while len(panels) < count:
            panels.append(Panel((self.project.panels[-1].layers[0],), name=f"Panel {len(panels) + 1}"))
            cavities.append(Cavity())
        self._commit(replace(self.project, panels=tuple(panels), cavities=tuple(cavities)))
        self._render_project()

    def _replace_layers(self, layers: tuple[Layer, ...]) -> None:
        panels = list(self.project.panels)
        panels[self._selected_panel] = replace(panels[self._selected_panel], layers=layers)
        self._selected_layer = min(self._selected_layer, len(layers) - 1)
        self._commit(replace(self.project, panels=tuple(panels)))
        self._refresh_layer_rows()
        self._show_layer()

    def add_layer(self) -> None:
        layers = self.project.panels[self._selected_panel].layers
        if len(layers) < 6:
            self._selected_layer = len(layers)
            self._replace_layers((*layers, Layer("Nueva capa", 12.5, 800, 2.5e9)))

    def duplicate_layer(self) -> None:
        layers = list(self.project.panels[self._selected_panel].layers)
        if len(layers) < 6:
            layers.insert(self._selected_layer + 1, layers[self._selected_layer])
            self._selected_layer += 1
            self._replace_layers(tuple(layers))

    def remove_layer(self) -> None:
        layers = list(self.project.panels[self._selected_panel].layers)
        if len(layers) > 1:
            del layers[self._selected_layer]
            self._replace_layers(tuple(layers))

    def move_layer(self, direction: int) -> None:
        layers = list(self.project.panels[self._selected_panel].layers)
        target = self._selected_layer + direction
        if 0 <= target < len(layers):
            layers[self._selected_layer], layers[target] = layers[target], layers[self._selected_layer]
            self._selected_layer = target
            self._replace_layers(tuple(layers))

    def _catalog_dialog(self, kind=None, selection_enabled=True):
        from noiz_transmission.ui.catalog_dialog import CatalogDialog
        dialog = CatalogDialog(self.entries, parent=self, kind=kind, selection_enabled=selection_enabled)
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        if tuple(dialog.entries) != tuple(self.entries):
            try:
                save_catalog(dialog.entries, default_catalog_path())
                self.entries = tuple(dialog.entries)
                self._refresh_summary()
            except (ValueError, OSError) as exc:
                self._error(f"No se pudo guardar la biblioteca: {exc}")
                return None
        return dialog.selected_entry if accepted else None

    def browse_catalog(self, checked=False, kind=None) -> None:
        self._catalog_dialog(kind=kind, selection_enabled=False)

    def select_material(self) -> None:
        entry = self._catalog_dialog(kind=("material", "glazing", "core"))
        if entry:
            try:
                self._replace_layer(layer_from_entry(entry))
                self._show_layer()
            except (ValueError, TypeError, KeyError) as exc:
                self._error(str(exc))

    def select_profile(self) -> None:
        entry = self._catalog_dialog(kind="profile")
        if entry:
            self._set_layer_field("profile", entry)
            self._show_layer()

    def select_absorber(self) -> None:
        entry = self._catalog_dialog(kind="absorption")
        if entry:
            self._set_cavity_field("absorber", entry)
            self._show_cavity()

    def clear_absorber(self) -> None:
        cavities = list(self.project.cavities)
        cavities[self._selected_cavity] = replace(cavities[self._selected_cavity], absorber=None,
                                                 absorber_thickness_mm=0, flow_resistivity_pa_s_m2=None)
        self._commit(replace(self.project, cavities=tuple(cavities)))
        self._show_cavity()

    def import_catalog(self) -> None:
        filenames, _ = QFileDialog.getOpenFileNames(self, "Importar biblioteca XML", "", "Bibliotecas XML (*.xml)")
        if not filenames:
            return
        try:
            entries = self.entries
            count, warnings = 0, []
            for path in filenames:
                result = import_xml(path)
                entries = merge_catalog(entries, result.entries)
                count += len(result.entries)
                warnings.extend(result.warnings)
            save_catalog(entries, default_catalog_path())
            self.entries = entries
            self._refresh_summary()
            self.statusBar().showMessage(f"{count} registros importados · {len(warnings)} avisos de procedencia. Consulta Biblioteca.")
        except (OSError, ValueError) as exc:
            self._error(f"No se pudo importar: {exc}")

    def show_settings(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Condiciones de cálculo — Noiz Transmission")
        dialog.resize(510, 550)
        layout = QVBoxLayout(dialog)
        layout.addWidget(label("Condiciones de cálculo", "sectionTitle"))
        layout.addWidget(label("Aislamiento aéreo del elemento. Sin impacto, lluvia ni transmisiones laterales.", "muted", True))
        form = QFormLayout()
        incidence = QComboBox()
        incidence.addItem("Campo difuso", "diffuse")
        incidence.addItem("Incidencia normal", "normal")
        incidence.setCurrentIndex(incidence.findData(self.project.incidence))
        form.addRow("Incidencia", incidence)
        settings = {}
        for title, key, low, high, precision in (
            ("Ángulo límite [°]", "limiting_angle_deg", .01, 90, 2),
            ("Densidad del aire [kg/m³]", "air_density_kg_m3", .01, 100, 4),
            ("Velocidad del sonido [m/s]", "sound_speed_m_s", 1, 3000, 3),
            ("Área abierta / fuga [%]", "leak_percentage", 0, 100, 4),
            ("Ancho ilustrativo [m]", "width_m", .001, 1000, 4),
            ("Alto ilustrativo [m]", "height_m", .001, 1000, 4),
        ):
            control = spin(low, high, decimals=precision)
            display_value(control, getattr(self.project, key))
            if key in ("width_m", "height_m"):
                control.setToolTip("Dimensión documental del elemento; el modelo usa placas infinitas y no depende de esta medida.")
            settings[key] = control
            form.addRow(title, control)
        layout.addLayout(form)
        floor_cover = [self.project.floor_cover]
        cover_label = label(floor_cover[0].name if floor_cover[0] else "Sin revestimiento de suelo asociado", "muted", True)
        row = QHBoxLayout()
        select = QPushButton("Revestimiento de suelo…")
        def choose_cover():
            entry = self._catalog_dialog(kind="floor_cover")
            if entry:
                floor_cover[0] = entry
                cover_label.setText(entry.name)
        select.clicked.connect(choose_cover)
        row.addWidget(select)
        clear = QPushButton("Quitar")
        clear.clicked.connect(lambda: (floor_cover.__setitem__(0, None), cover_label.setText("Sin revestimiento asociado")))
        row.addWidget(clear)
        layout.addLayout(row)
        layout.addWidget(cover_label)
        layout.addWidget(label("El revestimiento conserva metadatos; no produce una clasificación de impacto.", "muted", True))
        notes = QTextEdit(self.project.notes)
        notes.setPlaceholderText("Notas y procedencia de los parámetros manuales…")
        notes.setMaximumHeight(85)
        layout.addWidget(notes)
        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("Cancelar")
        cancel.clicked.connect(dialog.reject)
        buttons.addWidget(cancel)
        apply_button = QPushButton("Aplicar")
        apply_button.setObjectName("primary")
        apply_button.clicked.connect(dialog.accept)
        buttons.addWidget(apply_button)
        layout.addLayout(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            changes = {key: widget.value() for key, widget in settings.items()}
            changes.update(incidence=incidence.currentData(), notes=notes.toPlainText(), floor_cover=floor_cover[0])
            try:
                self._commit(replace(self.project, **changes))
            except (ValueError, TypeError) as exc:
                self._error(str(exc))

    @Slot()
    def calculate(self) -> None:
        if self._busy:
            return
        try:
            project = self.current_project()
        except ValueError as exc:
            self._error(str(exc))
            return
        self._busy = True
        self.current_result = None
        self._refresh_results()
        self.calculate_button.setEnabled(False)
        self.calculate_action.setEnabled(False)
        self.calculate_button.setText("Calculando…")
        self.progress.show()
        self.message_label.setText("Calculando respuesta de placas y cámaras…")
        self.statusBar().showMessage("Cálculo en curso · puedes seguir editando el proyecto.")
        worker = _PredictionWorker(self._generation, project)
        worker.signals.finished.connect(self._prediction_finished)
        self._worker = worker
        self._pool.start(worker)

    @Slot(int, object, object)
    def _prediction_finished(self, generation: int, result, error) -> None:
        if self._closing:
            return
        self._busy = False
        self._worker = None
        self.calculate_button.setEnabled(True)
        self.calculate_action.setEnabled(True)
        self.calculate_button.setText("Calcular  ·  F5")
        self.progress.hide()
        if generation != self._generation:
            self.current_result = None
            self._refresh_results()
            self.message_label.setText("El elemento cambió durante el cálculo. Calcula de nuevo.")
            if self._input_error:
                self._error(self._input_error)
            return
        if error is not None:
            self.current_result = None
            self._refresh_results()
            self._error(error)
            return
        self.current_result = result
        self.message_label.setObjectName("status")
        self.message_label.setStyleSheet("")
        self.message_label.setText("Cálculo actualizado · modelo exploratorio. Consulta hipótesis y procedencia.")
        self.message_label.setToolTip("\n".join(result.warnings))
        self._refresh_results()
        self.statusBar().showMessage("Cálculo completado. Puedes guardar este resultado en Comparación.")

    def _refresh_results(self) -> None:
        self.plot_item.clear()
        self.legend.clear()
        self.traces = []
        self.rw_value.setText("— dB" if self.current_result is None else
                              ("N/A" if self.current_result.rw_db is None else f"{self.current_result.rw_db} dB"))
        result = self.current_result
        self.spectrum_table.setRowCount(len(result.frequencies_hz) if result else 0)
        if result:
            for row, (frequency, value) in enumerate(zip(result.frequencies_hz, result.tl_db, strict=True)):
                self.spectrum_table.setItem(row, 0, cell(f"{frequency:g}"))
                self.spectrum_table.setItem(row, 1, cell(f"{value:.2f}"))
        plotted = [(prediction, f"{i + 1}. {prediction.project.name}", COLORS[i], False)
                   for i, prediction in enumerate(self.predictions)]
        if result:
            plotted.append((result, "Actual", "#123d50", True))
        for prediction, title, color, current in plotted:
            trace = self.plot_item.plot(prediction.frequencies_hz, prediction.tl_db,
                                        pen=pg.mkPen(color, width=2.5 if current else 1.5,
                                                     style=Qt.PenStyle.SolidLine if current else Qt.PenStyle.DashLine),
                                        symbol="o" if current else None, symbolSize=4,
                                        symbolBrush=color, symbolPen=color, name=title)
            self.traces.append(trace)
        if plotted:
            values = [level for prediction, _, _, _ in plotted for level in prediction.tl_db]
            self.plot_item.setYRange(min(0, min(values) - 5), max(30, max(values) + 5), padding=.02)
        self.comparison_table.setRowCount(len(self.predictions))
        for row, prediction in enumerate(self.predictions):
            for col, value in enumerate((prediction.project.name, len(prediction.project.panels),
                                         f"{prediction.total_thickness_mm:g}", f"{prediction.total_mass_kg_m2:.1f}",
                                         "—" if prediction.rw_db is None else str(prediction.rw_db))):
                self.comparison_table.setItem(row, col, cell(value))
        self.result_tabs.setTabText(2, f"Comparación · {len(self.predictions)}/6")
        self.add_comparison_button.setEnabled(result is not None and len(self.predictions) < 6)
        self.remove_button.setEnabled(bool(self.predictions))
        self.result_status.setText(("Actual actualizado · línea continua. Comparaciones guardadas · líneas discontinuas."
                                   if result else "Actual sin calcular · las comparaciones guardadas se conservan al editar"))

    def add_comparison(self) -> None:
        if self.current_result is None:
            self.statusBar().showMessage("Calcula el elemento antes de guardar una comparación.")
            return
        if len(self.predictions) >= 6:
            self.statusBar().showMessage("Límite de 6 alternativas. Quita una para añadir otra.")
            return
        self.predictions.append(self.current_result)
        self._comparison_dirty = True
        self._refresh_results()
        self.comparison_table.selectRow(len(self.predictions) - 1)

    def remove_selected(self) -> None:
        row = self.comparison_table.currentRow()
        if 0 <= row < len(self.predictions):
            del self.predictions[row]
            self._comparison_dirty = bool(self.predictions)
            self._refresh_results()

    def toggle_results(self, checked=None) -> None:
        visible = not self.results_panel.isVisible()
        self.results_panel.setVisible(visible)
        self.results_action.setChecked(visible)
        self.toggle_results_button.setText("Ocultar resultados" if visible else "Mostrar resultados")

    def restore_layout(self) -> None:
        self.results_panel.show()
        self.results_action.setChecked(True)
        self.toggle_results_button.setText("Ocultar resultados")
        self.main_splitter.setSizes([310, 930])
        self.right_splitter.setSizes([470, 245])

    def _editor_has_changes(self) -> bool:
        return bool(self._input_error) or self.project != self._saved_project

    def _confirm_discard(self) -> bool:
        if self._editor_has_changes():
            answer = QMessageBox.question(self, "Cambios sin guardar", "El proyecto tiene cambios sin guardar.",
                                           QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                                           QMessageBox.StandardButton.Save)
            if answer == QMessageBox.StandardButton.Save:
                if not self.save_current_project():
                    return False
            elif answer != QMessageBox.StandardButton.Discard:
                return False
        if self._comparison_dirty:
            answer = QMessageBox.question(self, "Comparaciones sin exportar",
                                           "Las comparaciones se exportan por separado del proyecto. ¿Descartar las comparaciones sin exportar?",
                                           QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                                           QMessageBox.StandardButton.Cancel)
            return answer == QMessageBox.StandardButton.Discard
        return True

    def _load_into_editor(self, project: AssemblyProject, path: Path | None = None) -> None:
        self.project = project
        self._saved_project = project
        self._current_path = path
        self._input_error = ""
        self._generation += 1
        self.current_result = None
        self.predictions = []
        self._comparison_dirty = False
        if self._worker is not None:
            self._worker.cancel_event.set()
        self._selected_panel = self._selected_layer = self._selected_cavity = 0
        self._render_project()
        self.message_label.setStyleSheet("")
        self.message_label.setText("Proyecto cargado · calcula para actualizar el resultado")

    def new_project(self) -> None:
        if self._confirm_discard():
            self._load_into_editor(default_project())

    def open_project(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(self, "Abrir proyecto", "", "Proyecto Noiz (*.json)")
        if not filename:
            return
        try:
            project = load_assembly(filename)
        except (OSError, ValueError, TypeError, KeyError) as exc:
            self._error(f"No se pudo abrir: {exc}")
            return
        if self._confirm_discard():
            self._load_into_editor(project, Path(filename))
            self.statusBar().showMessage(f"Proyecto abierto: {filename}")

    @staticmethod
    def _with_suffix(filename: str, suffix: str) -> Path:
        path = Path(filename)
        return path if path.suffix.lower() == suffix else path.with_suffix(suffix)

    def save_as(self) -> bool:
        return self.save_current_project(force_dialog=True)

    def save_current_project(self, checked=False, *, force_dialog=False) -> bool:
        try:
            project = self.current_project()
        except ValueError as exc:
            self._error(f"Corrige los datos antes de guardar: {exc}")
            return False
        path = self._current_path
        if path is None or force_dialog:
            filename, _ = QFileDialog.getSaveFileName(self, "Guardar proyecto", str(path or "elemento.noiz.json"), "Proyecto Noiz (*.json)")
            if not filename:
                return False
            path = self._with_suffix(filename, ".json")
        try:
            save_assembly(project, path)
        except (OSError, ValueError, TypeError) as exc:
            self._error(f"No se pudo guardar: {exc}")
            return False
        self._current_path = path
        self._saved_project = project
        self._set_title()
        self.statusBar().showMessage(f"Proyecto guardado: {path} · exporta la comparación por separado.")
        return True

    def _export_results(self, suffix: str, exporter) -> None:
        results = list(self.predictions)
        if self.current_result is not None and self.current_result not in results:
            results.append(self.current_result)
        if not results:
            self.statusBar().showMessage("Calcula al menos un elemento antes de exportar.")
            return
        filename, _ = QFileDialog.getSaveFileName(self, "Exportar resultados", f"noiz-resultados{suffix}", f"Resultados (*{suffix})")
        if not filename:
            return
        try:
            exporter(results, self._with_suffix(filename, suffix))
            self._comparison_dirty = False
            self.statusBar().showMessage(f"Resultados exportados: {filename}")
        except (OSError, ValueError, TypeError) as exc:
            self._error(f"No se pudo exportar: {exc}")

    def export_results_csv(self) -> None:
        self._export_results(".csv", export_assembly_csv)

    def export_results_html(self) -> None:
        self._export_results(".html", export_assembly_html)

    def show_model_details(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Modelo, procedencia y alcance")
        dialog.resize(620, 470)
        layout = QVBoxLayout(dialog)
        info = QTextEdit()
        info.setReadOnly(True)
        text = (
            "MODELO DE PREDICCIÓN\n\nPlacas isotrópicas infinitas y cámaras mediante matrices de transferencia. "
            "Se consideran masa, rigidez de flexión y pérdidas de las placas. Las capas de un panel se tratan como "
            "placas que se mueven juntas, sin rigidez compuesta de laminado adherido.\n\n"
            "Los paneles deben ser estructuralmente independientes. Los montantes, perfiles especiales y materiales "
            "anisótropos requieren modelos adicionales; no deben interpretarse como un sistema validado. "
            "El modelo poroso Miki necesita resistividad al flujo, no el campo Damping de un XML.\n\n"
            "Rw se calcula únicamente para incidencia difusa. Es una clasificación de una predicción preliminar, "
            "no un valor certificado por ensayo. No se calculan IIC, Ln,w ni ruido de lluvia. No se incluye flanking "
            "ni aislamiento entre recintos. Las dimensiones finitas son descriptivas.\n\n"
            "PROCEDENCIA\nLas propiedades importadas conservan archivo, identificador y SHA-256. "
            "Un catálogo no demuestra validación experimental. Consulta cada ficha en Biblioteca. "
            "Noiz Transmission utiliza modelos documentados propios; no reproduce los algoritmos de INSUL."
        )
        if self.current_result:
            text += "\n\nRESULTADO ACTUAL\n" + self.current_result.model_name
            text += "\n" + "\n".join(self.current_result.warnings)
            text += "\nFrecuencias críticas [Hz]: " + ", ".join(f"{f:.1f}" for f in self.current_result.critical_frequencies_hz)
            text += "\nResonancias masa-aire-masa [Hz]: " + ", ".join(f"{f:.1f}" for f in self.current_result.resonance_frequencies_hz)
        info.setPlainText(text)
        layout.addWidget(info)
        close = QPushButton("Cerrar")
        close.clicked.connect(dialog.accept)
        layout.addWidget(close, alignment=Qt.AlignmentFlag.AlignRight)
        dialog.exec()

    def about(self) -> None:
        QMessageBox.about(self, "Noiz Transmission", "Noiz Transmission · Workbench V2\nDiseño acústico de elementos constructivos.\nCódigo abierto · MIT\nModelos preliminares con procedencia explícita.")

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._confirm_discard():
            self._closing = True
            if self._worker is not None:
                self._worker.cancel_event.set()
            # A global pool outlives this window. Closing does not wait for the solver;
            # late signals are ignored by _prediction_finished or disconnected by Qt.
            event.accept()
        else:
            event.ignore()


def run() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Noiz Transmission")
    app.setOrganizationName("Noiz Transmission")
    app.setFont(QFont("Segoe UI", 10))
    window = MainWindow()
    window.show()
    return app.exec()
