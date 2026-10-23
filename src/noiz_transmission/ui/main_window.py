"""Construction-centred desktop workbench with immutable inputs and async prediction."""

from __future__ import annotations

import math
import sys
from dataclasses import replace
from pathlib import Path
from threading import Event
from time import perf_counter

import pyqtgraph as pg
from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal, Slot
from PySide6.QtGui import QAction, QCloseEvent, QColor, QFont, QKeySequence
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QStyleOptionViewItem,
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

from noiz_transmission import __version__
from noiz_transmission.application.assemblies import (
    ELEMENT_PANEL_LIMITS,
    AssemblyPrediction,
    AssemblyProject,
    Cavity,
    Layer,
    LeakSettings,
    Panel,
)
from noiz_transmission.application.assembly_services import (
    cavity_from_entry,
    default_project_v6,
    describe_assembly,
    export_assembly_csv,
    export_assembly_html,
    layer_from_entry,
    load_workspace,
    octave_summary,
    predict_assembly,
    save_workspace,
)
from noiz_transmission.catalog import (
    catalog_spectrum,
    default_catalog_path,
    import_xml,
    load_application_catalog,
    merge_catalog,
    save_catalog,
)
from noiz_transmission.ui.prediction_cache import PredictionCache
from noiz_transmission.ui.product_picker import ProductPicker
from noiz_transmission.ui.section_view import SectionView
from noiz_transmission.ui.settings_editors import (
    FacingEditor,
    LeakEditor,
    PorousEditor,
    RainfallEditor,
)
from noiz_transmission.ui.spectrum_chart import SquareSpectrumChart, fitted_reference
from noiz_transmission.ui.style import STYLESHEET

COLORS = ("#007c99", "#b87328", "#7868ac", "#48866f", "#b8596b", "#4d82bd")
ELEMENTS = (("Wall", "wall"), ("Ceiling", "ceiling"), ("Floor", "floor"),
            ("Roof", "roof"), ("Glazing", "glazing"), ("Porous", "porous"))
TOPOLOGIES = ("Single", "Double", "Triple", "Quad")


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
    def __init__(self, generation: int, project: AssemblyProject,
                 cache: PredictionCache | None = None):
        super().__init__()
        self.generation = generation
        self.project = project
        self.signals = _WorkerSignals()
        self.cancel_event = Event()
        self.cache = cache
        self.cache_hit = False
        self.elapsed_seconds = 0.0

    @Slot()
    def run(self) -> None:
        started = perf_counter()
        try:
            if self.cancel_event.is_set():
                raise ValueError("Cálculo cancelado.")
            result = self.cache.get(self.project) if self.cache is not None else None
            self.cache_hit = result is not None
            if result is None:
                result = predict_assembly(self.project, cancel_event=self.cancel_event)
                if self.cancel_event.is_set():
                    raise ValueError("Cálculo cancelado.")
                if self.cache is not None:
                    self.cache.put(result)
            if self.cancel_event.is_set():
                raise ValueError("Cálculo cancelado.")
            error = None
        except Exception as exc:  # Deliver domain / numerical errors without killing the Qt event loop.
            result, error = None, str(exc)
        self.elapsed_seconds = perf_counter() - started
        self.signals.finished.emit(self.generation, result, error)


class MainWindow(QMainWindow):
    """Nested construction editor with independent, recoverable topology drafts."""

    def __init__(self) -> None:
        super().__init__()
        self.project = default_project_v6()
        self._saved_project = self.project
        self._current_path: Path | None = None
        self._loading = False
        self._flushing_inputs = False
        self._generation = 0
        self._busy = False
        self._closing = False
        self._input_error = ""
        self._field_errors: dict[str, str] = {}
        self._selected_panel = 0
        self._selected_layer = 0
        self._selected_cavity = 0
        self._variants: dict[tuple[str, int], AssemblyProject] = {
            (self.project.element_type, len(self.project.panels)): self.project,
        }
        self._saved_variants = dict(self._variants)
        self._element_topology: dict[str, int] = {}
        self.current_result: AssemblyPrediction | None = None
        self.predictions: list[AssemblyPrediction] = []
        self._comparison_dirty = False
        self._worker: _PredictionWorker | None = None
        self._pool = QThreadPool.globalInstance()
        self._prediction_cache = PredictionCache()
        try:
            self.entries = load_application_catalog()
            catalog_error = ""
        except (OSError, ValueError) as exc:
            self.entries = ()
            catalog_error = str(exc)
        self.resize(1366, 768)
        self.setMinimumSize(1024, 620)
        compact_font = QFont(self.font())
        compact_font.setPointSizeF(9)
        self.setFont(compact_font)
        self.setStyleSheet(STYLESHEET)
        self._build_actions()
        content = QWidget()
        content.setObjectName("workspace")
        root = QVBoxLayout(content)
        root.setContentsMargins(4, 2, 4, 2)
        root.setSpacing(2)
        body = QHBoxLayout()
        body.setSpacing(4)
        body.addWidget(self._sidebar())
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.setHandleWidth(4)
        self.main_splitter.addWidget(self._construction())
        self.right_splitter = QSplitter(Qt.Orientation.Vertical)
        self.right_splitter.setChildrenCollapsible(False)
        self.right_splitter.setHandleWidth(4)
        self.right_splitter.addWidget(self._editor())
        self.results_panel = self._results()
        self.right_splitter.addWidget(self.results_panel)
        self.right_splitter.setStretchFactor(0, 3)
        self.right_splitter.setStretchFactor(1, 2)
        self.right_splitter.setSizes([420, 290])
        self.main_splitter.addWidget(self.right_splitter)
        self.main_splitter.setStretchFactor(0, 1)
        self.main_splitter.setStretchFactor(1, 3)
        self.main_splitter.setSizes([450, 820])
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
        toolbar.setObjectName("projectToolbar")
        self.name_edit = QLineEdit(self.project.name)
        self.name_edit.setAccessibleName("Nombre del proyecto")
        self.name_edit.setPlaceholderText("Nombre del proyecto")
        self.name_edit.setMaximumWidth(210)
        self.name_edit.setMinimumWidth(100)
        self.name_edit.textChanged.connect(self._name_changed)
        toolbar.addSeparator()
        toolbar.addWidget(self.name_edit)
        self.addToolBar(toolbar)

    def _header(self) -> QHBoxLayout:
        """Place the complete octave table and rating beside the construction view."""
        row = QHBoxLayout()
        row.setSpacing(6)
        self.octave_table = QTableWidget(1, 7)
        self.octave_table.setHorizontalHeaderLabels(["63", "125", "250", "500", "1k", "2k", "4k"])
        self.octave_table.setObjectName("octaveSummary")
        self.octave_table.setAccessibleName("TL [dB] · bandas de 1/1 octava [Hz]")
        self.octave_table.setStyleSheet("""
            QTableWidget#octaveSummary { border: 1px solid #7294a2; gridline-color: #d5e0e5; }
            QTableWidget#octaveSummary QHeaderView::section {
                background: #175f78; color: white; border: 0; border-right: 1px solid #6e96a6;
                padding: 2px 0; font-weight: 600;
            }
        """)
        for index, frequency in enumerate((63, 125, 250, 500, 1000, 2000, 4000)):
            self.octave_table.horizontalHeaderItem(index).setToolTip(f"{frequency} Hz · banda de 1/1 octava")
        self.octave_table.verticalHeader().hide()
        self.octave_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.octave_table.horizontalHeader().setMinimumSectionSize(25)
        self.octave_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.octave_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.octave_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.octave_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.octave_table.setToolTip("TL por octavas [dB]. Promedio energético de la transmisión de tres tercios de octava.")
        self.octave_table.setMinimumWidth(224)
        self.octave_table.setMaximumWidth(310)
        self._fit_octave_table()
        row.addWidget(self.octave_table, 3)
        rating = QVBoxLayout()
        rating.setSpacing(0)
        rating_row = QHBoxLayout()
        rating_row.setSpacing(3)
        self.rating_combo = QComboBox()
        self.rating_combo.setAccessibleName("Índice de clasificación acústica")
        self.rating_combo.setMinimumWidth(64)
        self.rating_combo.currentIndexChanged.connect(self._rating_changed)
        rating_row.addWidget(self.rating_combo)
        self.rw_value = label("— dB", "ratingValue")
        font = QFont(self.font())
        font.setPointSizeF(17)
        font.setBold(True)
        self.rw_value.setFont(font)
        rating_row.addWidget(self.rw_value, 1)
        rating.addLayout(rating_row)
        self.rating_detail = label("Predicción preliminar", "muted")
        self.rating_detail.setToolTip("Clasificación de una predicción; no equivale a un ensayo de laboratorio.")
        rating.addWidget(self.rating_detail)
        row.addLayout(rating, 2)
        # Mass and thickness live in the construction footer rather than a full-width banner.
        self.mass_value = label("— kg/m²", "muted")
        self.thickness_value = label("— mm", "muted")
        return row

    def _fit_octave_table(self) -> None:
        metrics = self.octave_table.fontMetrics()
        row_height = max(metrics.height() + 6, self.octave_table.verticalHeader().minimumSectionSize())
        header = self.octave_table.horizontalHeader()
        header_height = max(metrics.height() + 6, header.sizeHint().height())
        header.setFixedHeight(header_height)
        self.octave_table.setRowHeight(0, row_height)
        self.octave_table.setFixedHeight(header_height + row_height + 2 * self.octave_table.frameWidth())
        # Native item delegates reserve text margins in addition to glyph
        # width. Fit the actual bold one-decimal values, including those
        # margins and the grid, instead of merely making the cell rect visible.
        widths = []
        for column in range(self.octave_table.columnCount()):
            index = self.octave_table.model().index(0, column)
            if self.octave_table.item(0, column) is None:
                continue
            option = QStyleOptionViewItem()
            delegate = self.octave_table.itemDelegateForIndex(index)
            delegate.initStyleOption(option, index)
            widths.append(delegate.sizeHint(option, index).width() + 2)
        section_width = max(25, *widths) if widths else 25
        header.setMinimumSectionSize(section_width)
        minimum_width = max(224, section_width * self.octave_table.columnCount()
                            + 2 * self.octave_table.frameWidth())
        self.octave_table.setMaximumWidth(max(310, minimum_width))
        self.octave_table.setMinimumWidth(minimum_width)

    def _sidebar(self) -> QWidget:
        side = QWidget()
        side.setObjectName("elementSidebar")
        side.setFixedWidth(84)
        layout = QVBoxLayout(side)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(3)
        self.element_group = QButtonGroup(self)
        self.element_buttons = {}
        for title, key in ELEMENTS:
            button = QRadioButton(title)
            button.setObjectName("nav")
            button.clicked.connect(lambda checked=False, kind=key: self._change_element(kind))
            self.element_group.addButton(button)
            self.element_buttons[key] = button
            layout.addWidget(button)
        layout.addSpacing(14)
        self.view_combo = QComboBox()
        self.view_combo.addItems(["3D · rotar", "2D · corte"])
        self.view_combo.setAccessibleName("Vista del elemento")
        self.view_combo.currentIndexChanged.connect(lambda index: self.section_view.set_exploded(index == 0))
        layout.addWidget(self.view_combo)
        self.cutaway_check = QCheckBox("Recorte")
        self.cutaway_check.setChecked(True)
        self.cutaway_check.setToolTip("Vista parcial de las caras exteriores para inspeccionar la cámara.")
        self.cutaway_check.toggled.connect(lambda checked: self.section_view.set_cutaway(checked))
        layout.addWidget(self.cutaway_check)
        self.depth_detail_check = QCheckBox("Detalle")
        self.depth_detail_check.setToolTip("Amplía sólo los espesores en la vista. Desactivado: proporciones reales.")
        self.depth_detail_check.toggled.connect(lambda checked: self.section_view.set_depth_exaggeration(checked))
        layout.addWidget(self.depth_detail_check)
        layout.addWidget(label("Opacidad", "muted"))
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(10, 100)
        self.opacity_slider.setValue(100)
        self.opacity_slider.valueChanged.connect(self._opacity_changed)
        layout.addWidget(self.opacity_slider)
        reset = QPushButton("Restablecer")
        reset.setToolTip("Restablecer rotación y zoom")
        reset.clicked.connect(self._reset_view)
        layout.addWidget(reset)
        layout.addStretch()
        layout.addWidget(label("Noiz V6", "muted"))
        return side

    def _construction(self) -> QWidget:
        widget = QFrame()
        widget.setObjectName("sheet")
        widget.setMinimumWidth(380)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 3, 4, 3)
        layout.setSpacing(3)
        layout.addLayout(self._header())
        self.description_label = label("", wrap=True)
        self.description_label.setMaximumHeight(self.fontMetrics().height() * 3 + 4)
        layout.addWidget(self.description_label)
        # Optional accessibility navigator; editing lives in the nested tabs.
        self.composition_tree = QTreeWidget()
        self.composition_tree.setHeaderHidden(True)
        self.composition_tree.itemClicked.connect(self._tree_selected)
        self.composition_tree.hide()
        self.assembly_combo = QComboBox()
        self.assembly_combo.addItems(TOPOLOGIES)
        self.assembly_combo.currentIndexChanged.connect(self._change_topology)
        self.assembly_combo.hide()
        self.section_view = SectionView()
        layout.addWidget(self.section_view, 1)
        self.physics_footer = label("fc — Hz · masa superficial — kg/m²", "sectionTitle", True)
        layout.addWidget(self.physics_footer)
        footer = QHBoxLayout()
        footer.setSpacing(4)
        self.composition_summary = label("", "muted")
        footer.addWidget(self.composition_summary, 1)
        footer.addWidget(self.thickness_value)
        settings = QPushButton("Dimensiones…")
        settings.setToolTip("Dimensiones y condiciones de cálculo")
        settings.clicked.connect(self.show_settings)
        footer.addWidget(settings)
        layout.addLayout(footer)
        return widget

    def _opacity_changed(self, value: int) -> None:
        if hasattr(self.section_view, "set_opacity"):
            self.section_view.set_opacity(value / 100)

    def _reset_view(self) -> None:
        if hasattr(self.section_view, "reset_view"):
            self.section_view.reset_view()

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
        editor.setMinimumWidth(540)
        editor.setMinimumHeight(280)
        layout = QVBoxLayout(editor)
        layout.setContentsMargins(4, 3, 4, 3)
        layout.setSpacing(2)
        self.topology_tabs = QTabBar()
        self.topology_tabs.setObjectName("topologyTabs")
        self.topology_tabs.setExpanding(False)
        self.topology_tabs.setDrawBase(False)
        self.topology_tabs.currentChanged.connect(self._change_topology)
        layout.addWidget(self.topology_tabs)
        self.part_tabs = QTabBar()
        self.part_tabs.setObjectName("partTabs")
        self.part_tabs.setExpanding(False)
        self.part_tabs.setDrawBase(False)
        self.part_tabs.setUsesScrollButtons(True)
        self.part_tabs.currentChanged.connect(self._part_selected)
        layout.addWidget(self.part_tabs)
        self.excitation_combo = QComboBox()
        self.excitation_combo.setAccessibleName("Tipo de excitación")
        self.excitation_combo.currentIndexChanged.connect(self._excitation_changed)
        layout.addWidget(self.excitation_combo)
        self.editor_stack = QStackedWidget()
        self.editor_stack.addWidget(self._scroll(self._panel_editor()))
        self.editor_stack.addWidget(self._scroll(self._cavity_editor()))
        self.facing_editor = FacingEditor(self.entries)
        self.leak_editor = LeakEditor()
        self.leak_editor.set_entries(self.entries)
        self.rainfall_editor = RainfallEditor()
        self.porous_editor = PorousEditor(self.entries)
        self.settings_editors = {"facing": self.facing_editor, "leak": self.leak_editor,
                                "rainfall": self.rainfall_editor, "porous": self.porous_editor}
        self._extra_pages = {}
        for name, widget in self.settings_editors.items():
            self._extra_pages[name] = self.editor_stack.addWidget(self._scroll(widget))
            widget.changed.connect(lambda value, key=name: self._set_project_field(key, value))
            widget.validityChanged.connect(lambda error, key=name: self._extra_validity(key, error))
        self._extra_pages["floor_cover"] = self.editor_stack.addWidget(self._scroll(self._floor_editor()))
        layout.addWidget(self.editor_stack, 1)
        self.message_label = label("Configura el elemento y pulsa Calcular", "status")
        self.message_label.setMinimumWidth(0)
        self.message_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.message_label)
        controls = QHBoxLayout()
        self.library_label = label("", "muted")
        controls.addWidget(self.library_label, 1)
        self.toggle_results_button = QPushButton("Ocultar gráfica")
        self.toggle_results_button.clicked.connect(self.toggle_results)
        controls.addWidget(self.toggle_results_button)
        self.calculate_button = QPushButton("Calcular  ·  F5")
        self.calculate_button.setObjectName("primary")
        self.calculate_button.clicked.connect(self.calculate)
        controls.addWidget(self.calculate_button)
        layout.addLayout(controls)
        return editor

    def _excitation_changed(self) -> None:
        if not self._loading and self.excitation_combo.currentData():
            self._set_project_field("excitation", self.excitation_combo.currentData())
            self._configure_rating_choices()
            self._refresh_results()

    def _extra_validity(self, key: str, error: str) -> None:
        if self._loading:
            return
        if error:
            self._invalid(ValueError(error), f"extra:{key}")
        else:
            self._field_errors.pop(f"extra:{key}", None)
            self._input_error = next(iter(self._field_errors.values()), "")

    def _floor_editor(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        modes = QHBoxLayout()
        self.floor_mode_combo = QComboBox()
        self.floor_mode_combo.addItem("Measured · datos del catálogo", "measured")
        self.floor_mode_combo.addItem("Predicted · modelo pendiente", "predicted")
        self.floor_mode_combo.currentIndexChanged.connect(self._floor_settings_changed)
        modes.addWidget(self.floor_mode_combo)
        self.floor_base_combo = QComboBox()
        for title, value in (("Base ligera", "lightweight"), ("Base CLT", "clt"), ("Base pesada", "heavyweight")):
            self.floor_base_combo.addItem(title, value)
        self.floor_base_combo.currentIndexChanged.connect(self._floor_settings_changed)
        modes.addWidget(self.floor_base_combo)
        layout.addLayout(modes)
        self.floor_picker = ProductPicker(self.entries, kind="floor_cover")
        self.floor_picker.entrySelected.connect(self._select_floor_entry)
        layout.addWidget(self.floor_picker, 1)
        clear = QPushButton("Sin Floor cover")
        clear.clicked.connect(lambda: self._select_floor_entry(None))
        layout.addWidget(clear)
        self.floor_note = label("El catálogo contiene espectros declarados; su presencia no verifica un ensayo. La predicción de impacto está pendiente.", "muted", True)
        layout.addWidget(self.floor_note)
        return widget

    def _filter_floor_products(self) -> None:
        base = {"lightweight": "LightWeight", "heavyweight": "HeavyWeight", "clt": "CLT"}[self.project.floor.base_floor]
        self.floor_picker.set_entries(tuple(entry for entry in self.entries
                                           if entry.kind != "floor_cover" or entry.properties.get("cover_type") == base))
        self.floor_picker.select_entry(self.project.floor_cover.id if self.project.floor_cover else None)

    def _floor_settings_changed(self) -> None:
        if not self._loading:
            self._set_project_field("floor", replace(self.project.floor, mode=self.floor_mode_combo.currentData(),
                                                    base_floor=self.floor_base_combo.currentData()))
            self._filter_floor_products()
            self._refresh_floor_spectrum()

    def _select_floor_entry(self, entry) -> None:
        self._set_project_field("floor_cover", entry)
        self._refresh_floor_spectrum()

    def _panel_editor(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self.layer_tabs = QTabBar()
        self.layer_tabs.setObjectName("layerTabs")
        self.layer_tabs.setExpanding(False)
        for number in range(6):
            self.layer_tabs.addTab(f"Layer {number + 1}")
        self.layer_tabs.currentChanged.connect(self._select_layer_tab)
        layout.addWidget(self.layer_tabs)
        self.material_picker = ProductPicker(self.entries, kind=("material", "glazing", "core"))
        self.material_picker.entrySelected.connect(self._select_material_entry)
        self.material_picker.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored)
        self.material_picker.setMinimumHeight(190)
        controls = self.material_picker.search_row
        self.layer_enabled = QCheckBox("Activa")
        self.layer_enabled.setToolTip("Incluir esta capa en la composición y el cálculo")
        self.layer_enabled.toggled.connect(lambda value: self._set_layer_field("enabled", value))
        controls.addWidget(self.layer_enabled)
        controls.addWidget(label("mm"))
        thickness = spin(.001, 5000, decimals=4)
        thickness.setMaximumWidth(104)
        thickness.setAccessibleName("Thickness [mm]")
        thickness.valueChanged.connect(lambda value: self._set_layer_field("thickness_mm", value))
        self.layer_fields = {"thickness_mm": thickness}
        controls.addWidget(thickness)
        controls.addWidget(label("Qty"))
        self.count_spin = QSpinBox()
        self.count_spin.setRange(1, 10)
        self.count_spin.setMaximumWidth(48)
        self.count_spin.setKeyboardTracking(False)
        self.count_spin.setAccessibleName("Cantidad de capas")
        self.count_spin.valueChanged.connect(lambda value: self._set_layer_field("count", value))
        controls.addWidget(self.count_spin)
        layout.addWidget(self.material_picker, 1)
        self.layer_properties = QWidget()
        advanced = QVBoxLayout(self.layer_properties)
        advanced.setContentsMargins(0, 0, 0, 0)
        advanced.setSpacing(2)
        self.layer_name_edit = QLineEdit()
        self.layer_name_edit.setAccessibleName("Nombre del material de la capa")
        self.layer_name_edit.textChanged.connect(lambda text: self._set_layer_field("name", text))
        advanced.addWidget(self.layer_name_edit)
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(2)
        for index, (title, key, low, high, precision, factor) in enumerate([
            ("Densidad [kg/m³]", "density_kg_m3", .001, 100000, 3, 1),
            ("Young [GPa]", "young_modulus_pa", .000001, 10000, 6, 1e9),
            ("Pérdidas η", "loss_factor", 0, 10, 5, 1),
            ("Poisson ν", "poisson_ratio", -.999, .499, 4, 1),
        ]):
            field = spin(low, high, decimals=precision)
            field.setAccessibleName(title)
            field.valueChanged.connect(lambda value, k=key, f=factor: self._set_layer_field(k, value * f))
            self.layer_fields[key] = field
            grid.addWidget(label(title, "muted"), 0, index)
            grid.addWidget(field, 1, index)
        advanced.addLayout(grid)
        self.source_label = label("", "muted", True)
        advanced.addWidget(self.source_label)
        self.layer_properties.hide()
        layout.addWidget(self.layer_properties)
        buttons = QHBoxLayout()
        buttons.setSpacing(2)
        self.layer_buttons = {}
        for title, key, slot in (("+ Capa", "add", self.add_layer), ("Duplicar", "duplicate", self.duplicate_layer),
                                 ("Vaciar", "remove", self.remove_layer), ("←", "up", lambda: self.move_layer(-1)),
                                 ("→", "down", lambda: self.move_layer(1))):
            button = QPushButton(title)
            button.setMaximumWidth(max(30, button.fontMetrics().horizontalAdvance(title) + 22))
            button.clicked.connect(slot)
            buttons.addWidget(button)
            self.layer_buttons[key] = button
        buttons.addStretch(1)
        self.properties_toggle = QPushButton("Propiedades ▸")
        self.properties_toggle.setCheckable(True)
        self.properties_toggle.toggled.connect(self._toggle_layer_properties)
        buttons.addWidget(self.properties_toggle)
        profile = QPushButton("Perfil…")
        profile.setMaximumWidth(profile.fontMetrics().horizontalAdvance("Perfil…") + 22)
        profile.clicked.connect(self.select_profile)
        buttons.addWidget(profile)
        self.clear_profile_button = QPushButton("Quitar perfil")
        self.clear_profile_button.clicked.connect(lambda: (self._set_layer_field("profile", None), self._show_layer()))
        advanced.addWidget(self.clear_profile_button, alignment=Qt.AlignmentFlag.AlignRight)
        self.profile_label = label("", "muted")
        self.profile_label.hide()
        layout.addLayout(buttons)
        self.layer_table = table(["Capa", "N.º", "mm", "kg/m²"])
        self.layer_table.itemSelectionChanged.connect(self._layer_selected)
        self.layer_table.hide()
        return widget

    def _toggle_layer_properties(self, visible: bool) -> None:
        self.layer_properties.setVisible(visible)
        self.properties_toggle.setText("Propiedades ▾" if visible else "Propiedades ▸")

    def _select_layer_tab(self, index: int) -> None:
        if self._loading or index < 0:
            return
        self._flush_pending_inputs()
        self._selected_layer = index
        self._show_layer()
        self._refresh_layer_rows()

    def _current_layer(self) -> Layer:
        layers = self.project.panels[self._selected_panel].layers
        return (layers[self._selected_layer] if self._selected_layer < len(layers)
                else Layer("Capa sin asignar", 12.5, 800, 2.5e9, enabled=False))

    def _select_material_entry(self, entry) -> None:
        if self._loading or entry is None:
            return
        try:
            self._replace_layer(replace(layer_from_entry(entry), count=self.count_spin.value(), enabled=True))
            self._show_layer()
        except (ValueError, TypeError, KeyError) as exc:
            current = self._current_layer().catalog_entry
            self.material_picker.select_entry(current.id if current else None)
            self._error(str(exc))

    def _cavity_editor(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self.cavity_fields = {}
        controls = QHBoxLayout()
        controls.setSpacing(3)
        self.frame_combo = QComboBox()
        for title, key in (("Paneles independientes", "independent"), ("Timber stud", "timber"),
                           ("Steel stud", "steel"), ("Masonry frame", "masonry"),
                           ("Material no definido", "unknown")):
            self.frame_combo.addItem(title, key)
        self.frame_combo.currentIndexChanged.connect(lambda: self._set_cavity_field("frame_type", self.frame_combo.currentData()))
        controls.addWidget(self.frame_combo, 1)
        self.gas_combo = QComboBox()
        for title, gas in (("Air", "air"), ("Argon", "argon"), ("Krypton", "krypton"), ("Xenon", "xenon")):
            self.gas_combo.addItem(title, gas)
        self.gas_combo.currentIndexChanged.connect(lambda: self._set_cavity_field("gas", self.gas_combo.currentData()))
        controls.addWidget(self.gas_combo)
        for title, key in (("Cámara mm", "depth_mm"), ("Separación mm", "stud_spacing_mm")):
            field = spin(.01, 10000, decimals=3)
            field.setMaximumWidth(100)
            field.setAccessibleName(title)
            field.valueChanged.connect(lambda value, k=key: self._set_cavity_field(k, value))
            self.cavity_fields[key] = field
            controls.addWidget(label(title))
            controls.addWidget(field)
        layout.addLayout(controls)
        dimensions = QHBoxLayout()
        dimensions.setSpacing(3)
        for title, key in (("Stud ancho mm", "stud_width_mm"), ("Stud fondo mm", "stud_depth_mm")):
            field = spin(.01, 10000, decimals=3)
            field.setMaximumWidth(100)
            field.setAccessibleName(title)
            field.valueChanged.connect(lambda value, k=key: self._set_cavity_field(k, value))
            self.cavity_fields[key] = field
            dimensions.addWidget(label(title))
            dimensions.addWidget(field)
        dimensions.addStretch(1)
        layout.addLayout(dimensions)
        self.stud_picker = ProductPicker(self.entries, kind=("connection", "stud"))
        self.stud_picker.search_edit.setPlaceholderText("Buscar Connections / Studs · nombre, categoría o fabricante")
        self.stud_picker.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored)
        self.stud_picker.setMinimumHeight(95)
        self.stud_picker.count_label.hide()
        for listing in (self.stud_picker.products_list, self.stud_picker.category_list, self.stud_picker.manufacturer_list):
            listing.setMinimumHeight(45)
        self.stud_picker.entrySelected.connect(self._select_stud_entry)
        layout.addWidget(self.stud_picker, 1)
        self.frame_note = label("", "muted")
        self.frame_note.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.frame_note)
        self.absorber_picker = ProductPicker(self.entries, kind="absorption")
        self.absorber_picker.entrySelected.connect(self._select_absorber_entry)
        self.absorber_picker.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored)
        self.absorber_picker.setMinimumHeight(95)
        self.absorber_picker.count_label.hide()
        for listing in (self.absorber_picker.products_list, self.absorber_picker.category_list, self.absorber_picker.manufacturer_list):
            listing.setMinimumHeight(45)
        row = self.absorber_picker.search_row
        self.absorber_label = label("Infill", "sectionTitle")
        row.insertWidget(0, self.absorber_label)
        row.addWidget(label("mm"))
        self.absorber_spin = spin(0, 10000, decimals=3)
        self.absorber_spin.setMaximumWidth(100)
        self.absorber_spin.setAccessibleName("Espesor del absorbente [mm]")
        self.absorber_spin.valueChanged.connect(lambda value: self._set_cavity_field("absorber_thickness_mm", value))
        row.addWidget(self.absorber_spin)
        row.addWidget(label("Qty"))
        self.absorber_count_spin = QSpinBox()
        self.absorber_count_spin.setRange(0, 10)
        self.absorber_count_spin.setValue(1)
        self.absorber_count_spin.setMaximumWidth(48)
        self.absorber_count_spin.valueChanged.connect(lambda value: self._set_cavity_field("absorber_count", value))
        row.addWidget(self.absorber_count_spin)
        layout.addWidget(self.absorber_picker, 1)
        sigma = QHBoxLayout()
        sigma.setSpacing(3)
        sigma.addWidget(label("Resistividad σ [Pa·s/m²]", "muted"))
        self.resistivity_spin = spin(0, 1e8, decimals=2)
        self.resistivity_spin.setMaximumWidth(120)
        self.resistivity_spin.setSpecialValueText("Sin dato")
        self.resistivity_spin.valueChanged.connect(lambda value: self._set_cavity_field("flow_resistivity_pa_s_m2", value or None))
        sigma.addWidget(self.resistivity_spin)
        sigma.addWidget(label("Qty 0 excluye el relleno.", "muted"), 1)
        layout.addLayout(sigma)
        return widget

    def _select_stud_entry(self, entry) -> None:
        if self._loading or not self.project.cavities:
            return
        try:
            cavities = list(self.project.cavities)
            cavities[self._selected_cavity] = cavity_from_entry(cavities[self._selected_cavity], entry)
            self._commit(replace(self.project, cavities=tuple(cavities)))
            self._show_cavity()
        except (ValueError, TypeError) as exc:
            self._error(str(exc))

    def _select_absorber_entry(self, entry) -> None:
        if self._loading or not self.project.cavities:
            return
        cavity = self.project.cavities[self._selected_cavity]
        thickness = entry.properties.get("thickness_m")
        changes = {"absorber": entry, "flow_resistivity_pa_s_m2": None}
        if isinstance(thickness, (int, float)) and thickness > 0:
            changes["absorber_thickness_mm"] = thickness * 1000
        try:
            cavities = list(self.project.cavities)
            cavities[self._selected_cavity] = replace(cavity, **changes)
            self._commit(replace(self.project, cavities=tuple(cavities)))
            self._show_cavity()
        except (ValueError, TypeError) as exc:
            self._error(str(exc))

    def _results(self) -> QWidget:
        widget = QFrame()
        widget.setObjectName("sheet")
        widget.setMinimumHeight(165)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(5, 4, 5, 4)
        layout.setSpacing(2)
        self.result_tabs = QTabWidget()
        self.result_tabs.setDocumentMode(True)
        self.spectrum_chart = SquareSpectrumChart(widget)
        self.chart_view = self.spectrum_chart.plot_widget
        self.plot_item = self.spectrum_chart.plot
        self.legend = self.spectrum_chart.legend
        self.traces = []
        self.reference_trace = None
        self.result_tabs.addTab(self.spectrum_chart, "Chart")
        self.spectrum_table = table(["Frecuencia [Hz]", "R actual [dB]"])
        self.result_tabs.addTab(self.spectrum_table, "Tables")
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
        self.floor_covering_page = QWidget()
        floor_layout = QVBoxLayout(self.floor_covering_page)
        floor_layout.setContentsMargins(4, 4, 4, 4)
        self.floor_spectrum_note = label("Selecciona un Floor cover", "muted", True)
        floor_layout.addWidget(self.floor_spectrum_note)
        self.floor_chart = pg.PlotWidget(background="#ffffff")
        self.floor_chart.setLabel("bottom", "Frecuencia [Hz]")
        self.floor_chart.setLabel("left", "ΔL declarado [dB]")
        self.floor_chart.setLogMode(x=True)
        self.floor_chart.showGrid(x=True, y=True, alpha=.15)
        floor_layout.addWidget(self.floor_chart, 1)
        self.result_tabs.addTab(self.floor_covering_page, "Floor Covering")
        layout.addWidget(self.result_tabs, 1)
        self.result_status = label("Sin calcular · las comparaciones guardadas se conservan al editar", "muted")
        layout.addWidget(self.result_status)
        return widget

    def _flush_pending_inputs(self) -> None:
        """Commit keyboard edits before shortcuts capture an immutable snapshot."""
        if self._loading or self._flushing_inputs:
            return
        self._flushing_inputs = True
        try:
            for widget in self.editor_stack.findChildren(QAbstractSpinBox):
                if not widget.isVisibleTo(self.editor_stack) or not widget.isEnabled():
                    continue
                key = f"pending:{id(widget)}"
                if not widget.hasAcceptableInput():
                    self._invalid(ValueError("Completa el valor numérico antes de calcular o guardar: "
                                             + (widget.accessibleName() or widget.text())), key)
                    continue
                widget.interpretText()
                self._field_errors.pop(key, None)
            self._input_error = next(iter(self._field_errors.values()), "")
        finally:
            self._flushing_inputs = False

    def current_project(self) -> AssemblyProject:
        self._flush_pending_inputs()
        if self._input_error:
            raise ValueError(self._input_error)
        return self.project

    def _commit(self, project: AssemblyProject) -> None:
        changed = project != self.project
        self.project = project
        self._variants[(project.element_type, len(project.panels))] = project
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
        self.message_label.setToolTip(self.message_label.text())
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
            changes = {key: value}
            if key == "leak":
                changes["leak_percentage"] = 0
            project = replace(self.project, **changes)
            self._field_errors.pop(f"project:{key}", None)
            self._commit(project)
        except (ValueError, TypeError) as exc:
            self._invalid(exc, f"project:{key}")

    def _set_layer_field(self, key: str, value) -> None:
        if self._loading:
            return
        try:
            layer = replace(self._current_layer(), **{key: value})
            self._field_errors.pop(f"layer:{self._selected_panel}:{self._selected_layer}:{key}", None)
            self._replace_layer(layer)
        except (ValueError, TypeError) as exc:
            self._invalid(exc, f"layer:{self._selected_panel}:{self._selected_layer}:{key}")

    def _replace_layer(self, layer: Layer) -> None:
        panel = self.project.panels[self._selected_panel]
        layers = list(panel.layers)
        while len(layers) <= self._selected_layer:
            layers.append(Layer("Capa sin asignar", 12.5, 800, 2.5e9, enabled=False))
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
            changes = {key: value}
            if key == "frame_type" and (value == "independent" or value != cavities[self._selected_cavity].frame_type):
                changes["stud"] = None
            cavities[self._selected_cavity] = replace(cavities[self._selected_cavity], **changes)
            self._field_errors.pop(f"cavity:{self._selected_cavity}:{key}", None)
            self._commit(replace(self.project, cavities=tuple(cavities)))
            self._refresh_cavity_note()
            if key == "frame_type":
                self._show_cavity()
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
        self.message_label.setToolTip(text)
        self.message_label.setStyleSheet("color: #a52b37; background: #fff0f0;")
        self.statusBar().showMessage(text)

    def _refresh_summary(self) -> None:
        active = [layer for panel in self.project.panels for layer in panel.layers if layer.enabled]
        mass = sum(layer.thickness_mm / 1000 * layer.density_kg_m3 * layer.count for layer in active)
        thickness = sum(layer.thickness_mm * layer.count for layer in active)
        thickness += sum(cavity.depth_mm for cavity in self.project.cavities)
        cover = self.project.floor_cover
        if cover is not None:
            cover_thickness = cover.properties.get("thickness_m")
            if isinstance(cover_thickness, (int, float)) and math.isfinite(cover_thickness) and cover_thickness > 0:
                thickness += cover_thickness * 1000
        if self.project.facing.enabled:
            thickness += self.project.facing.thickness_mm * self.project.facing.count
        porous_mode = self.project.element_type == "porous"
        self.mass_value.setText("—" if porous_mode else f"{mass:.1f} kg/m²")
        if porous_mode:
            thickness = self.project.porous.thickness_mm
        self.thickness_value.setText(f"{thickness:g} mm")
        self.section_view.set_project(self.project, self._selected_panel)
        self.description_label.setText(describe_assembly(self.project))
        self.description_label.setToolTip(describe_assembly(self.project))
        model = "V6 · tamaño finito" if self.project.calculation_model == "finite" else "placas infinitas"
        if porous_mode:
            model = "Miki · medio poroso"
        self.composition_summary.setText(f"{self.project.width_m:g} × {self.project.height_m:g} m · "
                                         + ("campo difuso" if self.project.incidence == "diffuse" else "incidencia normal")
                                         + f" · {model}")
        self.library_label.setText(f"Biblioteca · {len(self.entries):,} registros")
        self.physics_footer.setText(("fc — Hz · masa superficial " if len(self.project.panels) == 1 else "f₀ — Hz · masa total ")
                                   + f"{mass:.1f} kg/m²")
        if porous_mode:
            self.physics_footer.setText("Medio poroso · masa superficial no inferida")
        old_loading = self._loading
        self._loading = True
        self.composition_tree.clear()
        for index, panel in enumerate(self.project.panels):
            item = QTreeWidgetItem([f"Panel {index + 1}"])
            item.setData(0, Qt.ItemDataRole.UserRole, ("panel", index, 0))
            self.composition_tree.addTopLevelItem(item)
            for j, layer in enumerate(panel.layers):
                if not layer.enabled:
                    continue
                child = QTreeWidgetItem([f"{layer.count} × {layer.thickness_mm:g} mm · {layer.name}"])
                child.setData(0, Qt.ItemDataRole.UserRole, ("panel", index, j))
                item.addChild(child)
            if index < len(self.project.cavities):
                cavity = self.project.cavities[index]
                item = QTreeWidgetItem([f"Frame {index + 1} · {cavity.depth_mm:g} mm"])
                item.setData(0, Qt.ItemDataRole.UserRole, ("cavity", index, 0))
                self.composition_tree.addTopLevelItem(item)
        if self.project.element_type in self.element_buttons:
            self.element_buttons[self.project.element_type].setChecked(True)
        self._loading = old_loading

    def _refresh_floor_spectrum(self) -> None:
        if not hasattr(self, "floor_chart"):
            return
        self.floor_chart.clear()
        entry = self.project.floor_cover
        spectrum = catalog_spectrum(entry) if entry else None
        if self.project.floor.mode == "predicted":
            self.floor_spectrum_note.setText("Predicted: el modelo de revestimientos de suelo aún no está implementado. No hay curva predicha.")
            return
        if spectrum is None:
            self.floor_spectrum_note.setText("Sin espectro ΔL en el producto seleccionado. La predicción de impacto aún no está disponible.")
            return
        expected_base = {"lightweight": "LightWeight", "heavyweight": "HeavyWeight", "clt": "CLT"}[self.project.floor.base_floor]
        if spectrum.cover_type != expected_base:
            self.floor_spectrum_note.setText(f"{entry.name}: base {spectrum.cover_type} incompatible con la base seleccionada {expected_base}. Selecciona un producto de esa base.")
            return
        self.floor_chart.plot(spectrum.frequencies_hz, spectrum.values_db, pen=pg.mkPen("#007c99", width=2),
                              symbol="o", symbolSize=4)
        self.floor_spectrum_note.setText(f"{entry.name} · ΔL declarado, no Ln,w · {spectrum.cover_type}\n"
                                        f"Fuente: {spectrum.source or 'sin fuente declarada'} · ensayo no verificado.")

    def _render_project(self) -> None:
        self._field_errors.clear()
        self._input_error = ""
        self._loading = True
        project = self.project
        self.name_edit.setText(project.name)
        self._selected_panel = min(self._selected_panel, len(project.panels) - 1)
        self._selected_layer = min(self._selected_layer, 5)
        self._selected_cavity = min(self._selected_cavity, max(0, len(project.cavities) - 1))
        while self.topology_tabs.count():
            self.topology_tabs.removeTab(0)
        for title in TOPOLOGIES[:ELEMENT_PANEL_LIMITS[project.element_type]]:
            self.topology_tabs.addTab(title)
        self.topology_tabs.setCurrentIndex(len(project.panels) - 1)
        self.assembly_combo.setCurrentIndex(len(project.panels) - 1)
        while self.part_tabs.count():
            self.part_tabs.removeTab(0)
        parts = []
        kind = project.element_type
        if kind == "porous":
            parts.append(("Porous", "porous", 0))
            if project.leak.enabled or project.leak_percentage:
                parts.append(("Leak heredada", "leak", 0))
        else:
            if kind == "floor":
                parts.append(("Floor cover", "floor_cover", 0))
            if kind == "roof":
                parts.append(("Rainfall", "rainfall", 0))
            for index in range(len(project.panels)):
                parts.append((f"Panel {index + 1}", "panel", index))
                if index < len(project.cavities):
                    parts.append((f"Frame {index + 1}", "cavity", index))
            if len(project.panels) == 1:
                parts.append(("Facing", "facing", 0))
            if kind in ("wall", "ceiling", "door"):
                parts.append(("Leak", "leak", 0))
            elif project.leak.enabled or project.leak_percentage:
                parts.append(("Leak heredada", "leak", 0))
        selected_index = 0
        for title, part_kind, index in parts:
            position = self.part_tabs.addTab(title)
            self.part_tabs.setTabData(position, (part_kind, index))
            if part_kind == "panel" and index == self._selected_panel:
                selected_index = position
        self.part_tabs.setCurrentIndex(selected_index)
        for name, editor in self.settings_editors.items():
            editor.set_settings(getattr(project, name))
        self.floor_mode_combo.setCurrentIndex(self.floor_mode_combo.findData(project.floor.mode))
        self.floor_base_combo.setCurrentIndex(self.floor_base_combo.findData(project.floor.base_floor))
        self._filter_floor_products()
        self.material_picker.set_kind("glazing" if kind == "glazing" else "material")
        self.gas_combo.setVisible(kind == "glazing")
        self.result_tabs.setTabVisible(3, kind == "floor")
        self.excitation_combo.clear()
        self.excitation_combo.addItem("Aislamiento aéreo · R [dB]", "airborne")
        if kind == "floor":
            self.excitation_combo.addItem("Impacto · modelo pendiente", "impact")
        elif kind == "roof":
            self.excitation_combo.addItem("Lluvia · modelo pendiente", "rainfall")
        self.excitation_combo.setCurrentIndex(self.excitation_combo.findData(project.excitation))
        self.excitation_combo.setVisible(kind in ("floor", "roof"))
        self._configure_rating_choices()
        self._loading = False
        self._part_selected(self.part_tabs.currentIndex())
        self._refresh_summary()
        self._refresh_results()
        self._refresh_floor_spectrum()
        self._set_title()

    def _tree_selected(self, item: QTreeWidgetItem, column: int) -> None:
        if self._loading:
            return
        kind, index, layer = item.data(0, Qt.ItemDataRole.UserRole)
        self._selected_layer = layer
        for tab in range(self.part_tabs.count()):
            if self.part_tabs.tabData(tab) == (kind, index):
                self.part_tabs.setCurrentIndex(tab)
                self._part_selected(tab)
                break

    def _part_selected(self, index: int) -> None:
        if self._loading or index < 0:
            return
        self._flush_pending_inputs()
        kind, number = self.part_tabs.tabData(index)
        if kind == "panel":
            self._selected_panel = number
            self.editor_stack.setCurrentIndex(0)
            self._refresh_layer_rows()
            self._show_layer()
        elif kind == "cavity":
            self._selected_cavity = number
            self.editor_stack.setCurrentIndex(1)
            self._show_cavity()
        else:
            self.editor_stack.setCurrentIndex(self._extra_pages[kind])
        self.section_view.set_project(self.project, self._selected_panel)

    def _refresh_layer_rows(self) -> None:
        previous_loading = self._loading
        self._loading = True
        layers = self.project.panels[self._selected_panel].layers
        self.layer_table.setRowCount(len(layers))
        for row, layer in enumerate(layers):
            for col, text in enumerate((layer.name, layer.count, f"{layer.thickness_mm:g}",
                                         f"{layer.thickness_mm / 1000 * layer.density_kg_m3 * layer.count:.2f}")):
                self.layer_table.setItem(row, col, cell(text))
        for index in range(6):
            active = index < len(layers) and layers[index].enabled
            self.layer_tabs.setTabText(index, f"Layer {index + 1}" + (" •" if active else ""))
            self.layer_tabs.setTabToolTip(index, layers[index].name if index < len(layers) else "Vacía: selecciona un producto para añadir una capa")
        self.layer_tabs.setCurrentIndex(self._selected_layer)
        if self._selected_layer < len(layers):
            self.layer_table.selectRow(self._selected_layer)
        available = any(index >= len(layers) or not layers[index].enabled for index in range(6))
        self.layer_buttons["add"].setEnabled(available)
        self.layer_buttons["duplicate"].setEnabled(available)
        self.layer_buttons["remove"].setEnabled(self._current_layer().enabled)
        self.layer_buttons["up"].setEnabled(self._selected_layer > 0 and self._selected_layer < len(layers))
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
        layer = self._current_layer()
        self.layer_enabled.setChecked(layer.enabled)
        self.material_picker.select_entry(layer.catalog_entry.id if layer.catalog_entry else None)
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
        self.clear_profile_button.setVisible(layer.profile is not None)
        if layer.profile:
            self.source_label.setText(self.source_label.text() + f"\nPerfil: {layer.profile.name} · modelo específico pendiente")
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
        self.gas_combo.setCurrentIndex(self.gas_combo.findData(cavity.gas))
        self.absorber_count_spin.setValue(cavity.absorber_count)
        self.stud_picker.select_entry(cavity.stud.id if cavity.stud else None)
        self.absorber_picker.select_entry(cavity.absorber.id if cavity.absorber else None)
        display_value(self.absorber_spin, cavity.absorber_thickness_mm)
        display_value(self.resistivity_spin, cavity.flow_resistivity_pa_s_m2 or 0)
        self.absorber_label.setText("Infill")
        props = cavity.stud.properties if cavity.stud else {}
        fixed_spacing = props.get("stud_spacing_defined") is True and props.get("stud_spacing_fixed") is True
        self.cavity_fields["stud_spacing_mm"].setEnabled(not fixed_spacing)
        if fixed_spacing:
            self.cavity_fields["stud_spacing_mm"].setToolTip("Separación fija declarada por la conexión del catálogo.")
        else:
            self.cavity_fields["stud_spacing_mm"].setToolTip("Separación entre montantes [mm].")
        self._loading = False
        self._refresh_cavity_note()

    def _refresh_cavity_note(self) -> None:
        cavity = self.project.cavities[self._selected_cavity]
        independent = cavity.frame_type == "independent"
        self.frame_note.setText("Sin puentes estructurales entre paneles." if independent else
                                "Montantes: modelo de acoplamiento estructural pendiente.")
        self.frame_note.setToolTip(self.frame_note.text())
        if cavity.stud and cavity.stud.kind == "connection":
            self.frame_note.setText("Connection · geometría de herrajes y cálculo de unión pendientes.")
            self.frame_note.setToolTip(f"{cavity.stud.name}\nDimensiones del XML; no contiene un modelo BIM de la conexión.")
        self.resistivity_spin.setEnabled(cavity.absorber_count > 0)

    def _change_topology(self, index: int) -> None:
        if self._loading or index < 0:
            return
        self._flush_pending_inputs()
        count = index + 1
        project = self.project
        if count > ELEMENT_PANEL_LIMITS[project.element_type] or count == len(project.panels):
            return
        self._variants[(project.element_type, len(project.panels))] = project
        target = self._variants.get((project.element_type, count))
        if target is None:
            panels = list(project.panels[:count])
            cavities = list(project.cavities[:count - 1])
            while len(panels) < count:
                panels.append(Panel((project.panels[-1].layers[0],), name=f"Panel {len(panels) + 1}"))
                cavities.append(Cavity())
            target = replace(project, panels=tuple(panels), cavities=tuple(cavities),
                             facing=replace(project.facing, enabled=False) if count > 1 else project.facing)
        self._element_topology[project.element_type] = count
        self._commit(target)
        self._render_project()

    def _change_element(self, kind: str) -> None:
        if self._loading or kind == self.project.element_type:
            return
        self._flush_pending_inputs()
        self._variants[(self.project.element_type, len(self.project.panels))] = self.project
        self._element_topology[self.project.element_type] = len(self.project.panels)
        count = self._element_topology.get(kind, 1)
        target = self._variants.get((kind, count)) or default_project_v6(element_type=kind)
        self._selected_panel = self._selected_layer = self._selected_cavity = 0
        self._commit(target)
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
        for index in range(6):
            if index >= len(layers) or not layers[index].enabled:
                self._selected_layer = index
                self._replace_layer(Layer("Nueva capa", 12.5, 800, 2.5e9))
                self._show_layer()
                break

    def duplicate_layer(self) -> None:
        original = self._current_layer()
        layers = self.project.panels[self._selected_panel].layers
        for index in range(self._selected_layer + 1, 6):
            if index >= len(layers) or not layers[index].enabled:
                self._selected_layer = index
                self._replace_layer(original)
                self._show_layer()
                break

    def remove_layer(self) -> None:
        self._replace_layer(replace(self._current_layer(), enabled=False))
        self._show_layer()

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
                self._refresh_pickers()
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
                self._select_material_entry(entry)
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
            self._select_absorber_entry(entry)

    def clear_absorber(self) -> None:
        cavities = list(self.project.cavities)
        cavities[self._selected_cavity] = replace(cavities[self._selected_cavity], absorber=None,
                                                 absorber_thickness_mm=0, flow_resistivity_pa_s_m2=None)
        self._commit(replace(self.project, cavities=tuple(cavities)))
        self._show_cavity()

    def _refresh_pickers(self) -> None:
        for picker in (self.material_picker, self.stud_picker, self.absorber_picker, self.floor_picker):
            picker.set_entries(self.entries)
        self.facing_editor.set_entries(self.entries)
        self.porous_editor.set_entries(self.entries)
        self.leak_editor.set_entries(self.entries)
        self._filter_floor_products()

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
            self._refresh_pickers()
            self._refresh_summary()
            self.statusBar().showMessage(f"{count} registros importados · {len(warnings)} avisos de procedencia. Consulta Biblioteca.")
        except (OSError, ValueError) as exc:
            self._error(f"No se pudo importar: {exc}")

    def show_settings(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Condiciones de cálculo — Noiz Transmission")
        dialog.resize(560, 610)
        layout = QVBoxLayout(dialog)
        layout.addWidget(label("Condiciones de cálculo", "sectionTitle"))
        layout.addWidget(label("Aislamiento aéreo del elemento. Sin impacto, lluvia ni transmisiones laterales.", "muted", True))
        form = QFormLayout()
        model = QComboBox()
        model.setObjectName("calculationModel")
        model.addItem("V6 · tamaño finito (Davy)", "finite")
        model.addItem("V2–V5 · placas infinitas", "infinite")
        model.setCurrentIndex(model.findData(self.project.calculation_model))
        form.addRow("Modelo", model)
        incidence = QComboBox()
        incidence.addItem("Campo difuso", "diffuse")
        incidence.addItem("Incidencia normal", "normal")
        incidence.setCurrentIndex(incidence.findData(self.project.incidence))
        form.addRow("Incidencia", incidence)
        settings = {}
        displayed_settings = {}
        for title, key, low, high, precision in (
            ("Ángulo límite [°]", "limiting_angle_deg", .01, 90, 2),
            ("Densidad del aire [kg/m³]", "air_density_kg_m3", .01, 100, 4),
            ("Velocidad del sonido [m/s]", "sound_speed_m_s", 1, 3000, 3),
            ("Ancho del panel [m]", "width_m", .001, 1000, 4),
            ("Alto del panel [m]", "height_m", .001, 1000, 4),
        ):
            control = spin(low, high, decimals=precision)
            control.setObjectName(key)
            display_value(control, getattr(self.project, key))
            if key in ("width_m", "height_m"):
                control.setToolTip("V6: dimensión usada en la corrección angular de tamaño finito. "
                                   "En el modelo infinito solo describe geometría y área de fugas.")
            settings[key] = control
            displayed_settings[key] = control.value()
            form.addRow(title, control)
        layout.addLayout(form)
        model_note = label("", "muted", True)
        def update_model_note():
            finite = model.currentData() == "finite"
            model_note.setText(
                ("Incidencia normal: el tamaño y las pérdidas de flexión de borde no modifican "
                 "la curva. El modo V6 no representa la rigidez de apoyo ni los modos propios."
                 if incidence.currentData() == "normal" else
                 "Davy: límite angular dependiente de tamaño y frecuencia. Aproximación por encima "
                 "de 1,5 f₁₁; no resuelve los modos propios de una placa finita.")
                if finite else
                "Placas infinitas: conserva las ecuaciones V2–V5. Las pérdidas de borde deben ser cero."
            )
        model.currentIndexChanged.connect(update_model_note)
        incidence.currentIndexChanged.connect(update_model_note)
        update_model_note()
        layout.addWidget(model_note)
        layout.addWidget(label("Pérdidas de borde adicionales η · por panel", "sectionTitle"))
        edge_grid = QGridLayout()
        edge_controls = []
        displayed_edge = []
        for index, panel in enumerate(self.project.panels):
            control = spin(0, 10, decimals=5)
            control.setObjectName(f"edgeLossPanel{index + 1}")
            control.setAccessibleName(f"Pérdidas de borde del panel {index + 1}")
            display_value(control, panel.edge_loss_factor)
            control.setToolTip("Factor de pérdidas adimensional adicional al del material. "
                               "Déjelo en cero si η del material ya incluye montaje. "
                               "Requiere el modelo V6; no es una corrección universal de laboratorio.")
            edge_grid.addWidget(label(f"Panel {index + 1}"), 0, index)
            edge_grid.addWidget(control, 1, index)
            edge_controls.append(control)
            displayed_edge.append(control.value())
        layout.addLayout(edge_grid)
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
            changes = {key: widget.value() for key, widget in settings.items()
                       if widget.value() != displayed_settings[key]}
            try:
                panels = tuple(
                    replace(panel, edge_loss_factor=control.value()) if control.value() != initial else panel
                    for panel, control, initial in zip(self.project.panels, edge_controls, displayed_edge, strict=True)
                )
                changes.update(incidence=incidence.currentData(), notes=notes.toPlainText(),
                               floor_cover=floor_cover[0], calculation_model=model.currentData(), panels=panels)
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
        worker = _PredictionWorker(self._generation, project, self._prediction_cache)
        worker.signals.finished.connect(self._prediction_finished)
        self._worker = worker
        self._pool.start(worker)

    @Slot(int, object, object)
    def _prediction_finished(self, generation: int, result, error) -> None:
        if self._closing:
            return
        worker = self._worker
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
        elapsed = worker.elapsed_seconds if worker is not None else 0.0
        source = "Resultado recuperado de caché" if worker is not None and worker.cache_hit else "Cálculo completado"
        self.statusBar().showMessage(f"{source} · {elapsed:.3f} s · Puedes guardar el resultado en Comparación.")

    def _configure_rating_choices(self) -> None:
        previous = self.rating_combo.currentData()
        self.rating_combo.blockSignals(True)
        self.rating_combo.clear()
        choices = (("IIC", "iic"), ("Ln,w", "lnw")) if self.project.excitation == "impact" else (
            (("LA", "rainfall"),) if self.project.excitation == "rainfall" else (("Rw", "rw"), ("STC", "stc")))
        for title, key in choices:
            self.rating_combo.addItem(title, key)
        index = self.rating_combo.findData(previous)
        self.rating_combo.setCurrentIndex(max(0, index))
        self.rating_combo.blockSignals(False)

    def _rating_changed(self) -> None:
        if not self._loading and hasattr(self, "plot_item"):
            self._refresh_results()

    def _selected_rating(self, prediction: AssemblyPrediction | None) -> int | None:
        if prediction is None:
            return None
        key = self.rating_combo.currentData()
        try:
            if key in ("rw", "stc") and prediction.rating_unavailable_reason(key):
                return None
            return prediction.rw_db if key == "rw" else (prediction.stc_db if key == "stc" else None)
        except ValueError:
            # Older imported comparisons may have only a partial spectrum.
            return None

    def _refresh_rating(self) -> None:
        key = self.rating_combo.currentData()
        value = self._selected_rating(self.current_result)
        unit = " dB" if key in ("rw", "lnw") else (" dBA" if key == "rainfall" else "")
        unavailable = self.current_result is not None and value is None and key in ("rw", "stc")
        self.rw_value.setText("N/A" if unavailable else ("—" if value is None else str(value)) + unit)
        if key in ("iic", "lnw"):
            detail = "Impacto: modelo pendiente"
            tooltip = ("IIC y Ln,w requieren un espectro de impacto que aún no se predice. "
                       "L’nT,w corresponde a recintos y depende del tiempo de reverberación; "
                       "no equivale a Ln,w de un elemento.")
        elif key == "rainfall":
            detail, tooltip = "Lluvia: modelo pendiente", "La predicción de ruido de lluvia todavía no está implementada."
        elif key == "stc":
            detail = "STC orientativo · 32/8"
            tooltip = "STC orientativo · método legado 32/8, 125–4000 Hz. No afirma conformidad con ASTM E413-16 o posterior."
        else:
            detail = "Predicción preliminar"
            tooltip = "Rw de la predicción en campo difuso; no equivale a un ensayo de laboratorio."
        if self.current_result is not None and value is None and key in ("rw", "stc"):
            detail = "No aplicable al espectro"
            reason = self.current_result.rating_unavailable_reason(key)
            if reason:
                tooltip = reason
            if (self.current_result.project.incidence == "diffuse"
                    and self.current_result.project.rating_extrapolated_bands(key)):
                detail = "Fuera del dominio V6"
        self.rating_detail.setText(detail)
        self.rating_detail.setToolTip(tooltip)
        self.rating_combo.setToolTip(tooltip)

    def _style_octave_cell(self, index: int) -> None:
        item = self.octave_table.item(0, index)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        font = QFont(self.octave_table.font())
        font.setBold(True)
        item.setFont(font)
        item.setForeground(QColor("#203f50"))
        item.setBackground(QColor("#f0f6f8" if index % 2 == 0 else "#ffffff"))
        item.setToolTip(f"TL {item.text()} dB · banda de 1/1 octava")

    def _refresh_results(self) -> None:
        self.plot_item.clear()
        self.legend.clear()
        self.traces = []
        self.reference_trace = None
        self._refresh_rating()
        result = self.current_result
        extrapolated = set(result.project.extrapolated_bands_hz(result.frequencies_hz)) if result else set()
        extrapolation_note = (
            f"Extrapolación V6: parte de la banda está por debajo de 1,5 f₁₁ "
            f"({result.project.finite_validity_floor_hz:.1f} Hz). "
            "El modelo angular no resuelve la rigidez de apoyo ni los modos propios."
            if extrapolated else ""
        )
        for index in range(7):
            self.octave_table.setItem(0, index, cell("—"))
            self._style_octave_cell(index)
        self._fit_octave_table()
        if result:
            try:
                for index, (_, value) in enumerate(octave_summary(result)):
                    self.octave_table.setItem(0, index, cell(f"{value:.1f}"))
                    self._style_octave_cell(index)
                    if any(frequency in extrapolated for frequency in
                           result.frequencies_hz[3 * index:3 * index + 3]):
                        item = self.octave_table.item(0, index)
                        item.setBackground(QColor("#fff0c2"))
                        item.setToolTip("Esta octava incluye tercios extrapolados. " + extrapolation_note)
            except ValueError:
                # A partial imported/comparison spectrum cannot claim a full octave summary.
                pass
            self._fit_octave_table()
            frequencies = (result.critical_frequencies_hz if len(result.project.panels) == 1
                           else result.resonance_frequencies_hz)
            prefix = "fc" if len(result.project.panels) == 1 else "f₀"
            frequency_text = ", ".join(f"{value:.0f}" for value in frequencies) or "—"
            mass_text = "masa superficial" if len(result.project.panels) == 1 else "masa total de placas"
            self.physics_footer.setText(f"{prefix} {frequency_text} Hz · {mass_text} {result.total_mass_kg_m2:.1f} kg/m²")
            if result.project.element_type == "porous":
                self.physics_footer.setText("Medio poroso · masa superficial no inferida")
        self.spectrum_table.setRowCount(len(result.frequencies_hz) if result else 0)
        if result:
            for row, (frequency, value) in enumerate(zip(result.frequencies_hz, result.tl_db, strict=True)):
                self.spectrum_table.setItem(row, 0, cell(f"{frequency:g}"))
                self.spectrum_table.setItem(row, 1, cell(f"{value:.2f}"))
                if frequency in extrapolated:
                    for column in (0, 1):
                        item = self.spectrum_table.item(row, column)
                        item.setBackground(QColor("#fff0c2"))
                        item.setToolTip(extrapolation_note)
        plotted = []
        occurrences: dict[int, int] = {}
        for i, prediction in enumerate(self.predictions):
            # Immutable prediction identities survive legend rebuilds and row
            # renumbering. Occurrences also distinguish repeated snapshots.
            identity = id(prediction)
            occurrence = occurrences.get(identity, 0)
            occurrences[identity] = occurrence + 1
            key = f"comparison:{identity}:{occurrence}"
            plotted.append((prediction, f"{i + 1}. {prediction.project.name}", COLORS[i], False, key))
        self.legend.retain_keys({"current", "reference", *(item[4] for item in plotted)})
        if result:
            plotted.append((result, "TL actual [dB]", "#268338", True, "current"))
        for prediction, title, color, current, key in plotted:
            trace = self.plot_item.plot(prediction.frequencies_hz, prediction.tl_db,
                                        pen=pg.mkPen(color, width=2.5 if current else 1.5,
                                                     style=Qt.PenStyle.SolidLine if current else Qt.PenStyle.DashLine),
                                        symbol="o" if current else None, symbolSize=4,
                                        symbolBrush=color, symbolPen=color, name=title)
            self.traces.append(trace)
            self.legend.addItem(trace, title, extrapolation_note if current else "", key=key)
        reference = (fitted_reference(result, self.rating_combo.currentData())
                     if result and self._selected_rating(result) is not None else None)
        if reference:
            frequencies, levels, title, tooltip = reference
            self.reference_trace = self.plot_item.plot(
                frequencies, levels, pen=pg.mkPen("#309cc0", width=1.8, style=Qt.PenStyle.DashLine))
            self.legend.addItem(self.reference_trace, title, tooltip, key="reference")
        if plotted:
            values = [level for prediction, _, _, _, _ in plotted for level in prediction.tl_db]
            if reference:
                values.extend(reference[1])
            self.plot_item.setYRange(min(0, min(values) - 5), max(30, max(values) + 5), padding=.02)
        self.comparison_table.horizontalHeaderItem(4).setText(self.rating_combo.currentText())
        self.comparison_table.setRowCount(len(self.predictions))
        for row, prediction in enumerate(self.predictions):
            for col, value in enumerate((prediction.project.name, len(prediction.project.panels),
                                         f"{prediction.total_thickness_mm:g}", f"{prediction.total_mass_kg_m2:.1f}",
                                         "—" if self._selected_rating(prediction) is None else str(self._selected_rating(prediction)))):
                self.comparison_table.setItem(row, col, cell(value))
        self.result_tabs.setTabText(2, f"Comparación · {len(self.predictions)}/6")
        self.add_comparison_button.setEnabled(result is not None and len(self.predictions) < 6)
        self.remove_button.setEnabled(bool(self.predictions))
        self.result_status.setText(("Actual actualizado · línea continua. Comparaciones guardadas · líneas discontinuas."
                                   if result else "Actual sin calcular · las comparaciones guardadas se conservan al editar"))
        if extrapolated:
            self.result_status.setText("Bandas en ámbar: extrapolación bajo 1,5 f₁₁. Consulta Modelo e hipótesis.")
            self.result_status.setToolTip(extrapolation_note)
        else:
            self.result_status.setToolTip("")

    def add_comparison(self) -> None:
        if self.current_result is None:
            self.statusBar().showMessage("Calcula el elemento antes de guardar una comparación.")
            return
        if len(self.predictions) >= 6:
            self.statusBar().showMessage("Límite de 6 alternativas. Quita una para añadir otra.")
            return
        # Each saved row has its own immutable identity, even when the same
        # result is saved twice; legend visibility follows that row on removal.
        self.predictions.append(replace(self.current_result))
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
        self.toggle_results_button.setText("Ocultar gráfica" if visible else "Mostrar gráfica")

    def restore_layout(self) -> None:
        self.results_panel.show()
        self.results_action.setChecked(True)
        self.toggle_results_button.setText("Ocultar gráfica")
        self.main_splitter.setSizes([450, 820])
        self.right_splitter.setSizes([420, 290])

    def _editor_has_changes(self) -> bool:
        return (bool(self._input_error) or self.project != self._saved_project
                or self._variants != self._saved_variants)

    def _confirm_discard(self) -> bool:
        self._flush_pending_inputs()
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

    @staticmethod
    def _migrate_legacy_leak(project: AssemblyProject) -> AssemblyProject:
        if project.leak_percentage and not project.leak.enabled:
            leak = LeakSettings(enabled=True, method="open_area", kind="slit",
                                height_mm=1000 * project.height_m * project.leak_percentage / 100,
                                length_mm=1000 * project.width_m, depth_mm=0)
            return replace(project, leak_percentage=0, leak=leak,
                           notes=project.notes + "\nFuga V2 convertida a área abierta ideal equivalente; geometría de rendija ilustrativa.")
        return project

    def _load_into_editor(self, project: AssemblyProject, path: Path | None = None,
                          variants=()) -> None:
        project = self._migrate_legacy_leak(project)
        variants = tuple(self._migrate_legacy_leak(variant) for variant in variants)
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
        self._variants = {(variant.element_type, len(variant.panels)): variant for variant in variants}
        self._variants[(project.element_type, len(project.panels))] = project
        self._saved_variants = dict(self._variants)
        self._element_topology = {variant.element_type: len(variant.panels) for variant in variants}
        self._element_topology[project.element_type] = len(project.panels)
        self._render_project()
        self.message_label.setStyleSheet("")
        self.message_label.setText("Proyecto cargado · calcula para actualizar el resultado")

    def new_project(self) -> None:
        if self._confirm_discard():
            self._load_into_editor(default_project_v6())

    def open_project(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(self, "Abrir proyecto", "", "Proyecto Noiz (*.json)")
        if not filename:
            return
        try:
            project, variants = load_workspace(filename)
        except (OSError, ValueError, TypeError, KeyError) as exc:
            self._error(f"No se pudo abrir: {exc}")
            return
        if self._confirm_discard():
            self._load_into_editor(project, Path(filename), variants)
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
            save_workspace(project, tuple(self._variants.values()), path)
        except (OSError, ValueError, TypeError) as exc:
            self._error(f"No se pudo guardar: {exc}")
            return False
        self._current_path = path
        self._saved_project = project
        self._saved_variants = dict(self._variants)
        self._set_title()
        self.statusBar().showMessage(f"Proyecto y {len(self._variants)} configuración(es) guardados: {path}.")
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
        finite = self.project.calculation_model == "finite"
        selected_model = "V6 · tamaño finito (Davy)" if finite else "V2–V5 · placas infinitas"
        edges = ", ".join(f"Panel {i + 1}: {panel.edge_loss_factor:g}"
                          for i, panel in enumerate(self.project.panels))
        text = (
            f"MODELO DE PREDICCIÓN\n\n{selected_model}\n"
            f"Dimensiones: {self.project.width_m:g} × {self.project.height_m:g} m\n"
            f"Pérdidas adicionales de borde η: {edges}\n\n"
            "Placas isotrópicas delgadas y cámaras mediante matrices de transferencia. "
            "Se consideran masa, rigidez de flexión y pérdidas de las placas. Las capas de un panel se tratan como "
            "placas que se mueven juntas, sin rigidez compuesta de laminado adherido.\n\n"
            "En V6, Davy corrige el límite angular con tamaño y frecuencia; las pérdidas de borde "
            "se suman explícitamente a las del material. Evite duplicar el amortiguamiento del montaje. "
            "Esta aproximación se recomienda por encima de 1,5 veces la primera frecuencia propia "
            "f₁₁ de placa simplemente apoyada. No constituye una solución modal de baja frecuencia. "
            "Su extensión a Double, Triple y Quad independientes requiere validación experimental. "
            "En el modo infinito las dimensiones no corrigen el espectro y no se admiten pérdidas de borde.\n\n"
            "Los paneles deben ser estructuralmente independientes. Los montantes, perfiles especiales y materiales "
            "anisótropos requieren modelos adicionales; no deben interpretarse como un sistema validado. "
            "El modelo poroso Miki necesita resistividad al flujo, no el campo Damping de un XML.\n\n"
            "Rw y STC se calculan únicamente para incidencia difusa. STC usa el método legado 32/8 y es orientativo. "
            "Es una clasificación de una predicción preliminar, "
            "no un valor certificado por ensayo. No se calculan IIC, Ln,w ni ruido de lluvia. No se incluye flanking "
            "ni aislamiento entre recintos.\n\n"
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
        QMessageBox.about(self, "Noiz Transmission", f"Noiz Transmission · {__version__}\nDiseño acústico de elementos constructivos.\nCódigo abierto · MIT\nModelos preliminares con procedencia explícita.")

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
    app.setFont(QFont("Segoe UI", 9))
    window = MainWindow()
    window.show()
    return app.exec()
