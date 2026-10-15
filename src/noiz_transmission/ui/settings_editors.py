"""Compact native editors with explicit physical-model availability."""

from __future__ import annotations

import math
from dataclasses import replace

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from noiz_transmission.application.assemblies import (
    Facing,
    LeakSettings,
    PorousSettings,
    RainfallSettings,
)
from noiz_transmission.ui.product_picker import ProductPicker


def _label(text: str) -> QLabel:
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(True)
    return widget


def _number(minimum=0.0, maximum=1e9, decimals=3) -> QDoubleSpinBox:
    widget = QDoubleSpinBox()
    widget.setDecimals(decimals)
    widget.setRange(minimum, maximum)
    widget.setKeyboardTracking(False)
    return widget


def _display(widget: QDoubleSpinBox | QSpinBox, value: float | int) -> None:
    # Imported inputs remain exact in the immutable settings; display ranges must
    # not suggest a different value from the one that is saved and calculated.
    if isinstance(widget, QDoubleSpinBox) and 0 < abs(value) < 10 ** -widget.decimals():
        widget.setDecimals(min(323, math.ceil(-math.log10(abs(value))) + 2))
    if value < widget.minimum():
        widget.setMinimum(value)
    if value > widget.maximum():
        widget.setMaximum(value)
    widget.setValue(value)
    widget.setToolTip(f"Valor guardado: {value!r}")


class _Editor(QWidget):
    changed = Signal(object)
    validityChanged = Signal(str)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._loading = False
        self.validation_error = ""
        self._field_errors: dict[str, str] = {}

    @property
    def settings(self):
        return self._settings

    def _set(self, **fields) -> None:
        if self._loading:
            return
        try:
            candidate = replace(self._settings, **fields)
        except ValueError as exc:
            for name in fields:
                self._field_errors[name] = str(exc)
            self.validation_error = "\n".join(dict.fromkeys(self._field_errors.values()))
            self.validityChanged.emit(self.validation_error)
            return
        self._settings = candidate
        for name in fields:
            self._field_errors.pop(name, None)
        self.validation_error = "\n".join(dict.fromkeys(self._field_errors.values()))
        self._update_availability()
        self.validityChanged.emit(self.validation_error)
        self.changed.emit(candidate)

    def _update_availability(self) -> None:
        pass


class LeakEditor(_Editor):
    """Store Gomperts/Mechel requests without disguising an open-area calculation."""

    def __init__(self, parent=None):
        super().__init__(LeakSettings(), parent)
        self.entries = ()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(3)
        self.enabled_check = QCheckBox("Enable Leak · incluir fuga")
        layout.addWidget(self.enabled_check)
        self.controls = QWidget()
        body = QVBoxLayout(self.controls)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(3)
        kind_row = QHBoxLayout()
        self.kind_group = QButtonGroup(self)
        self.slit_radio = QRadioButton("Slit · rendija")
        self.aperture_radio = QRadioButton("Aperture · abertura circular")
        for button in (self.slit_radio, self.aperture_radio):
            self.kind_group.addButton(button)
            kind_row.addWidget(button)
        body.addLayout(kind_row)
        self.form = QFormLayout()
        self.form.setVerticalSpacing(2)
        self.height_spin = _number(.000001)
        self.length_spin = _number(.000001)
        self.radius_spin = _number(.000001)
        self.depth_spin = _number()
        self.method_combo = QComboBox()
        for title, key in (("Gomperts solution", "gomperts"),
                           ("Mechel solution", "mechel"),
                           ("Área abierta ideal · transmisión unitaria", "open_area")):
            self.method_combo.addItem(title, key)
        self.position_combo = QComboBox()
        for title, key in (("Middle", "middle"), ("Edge", "edge"), ("Corner", "corner")):
            self.position_combo.addItem(title, key)
        for title, widget in (("Altura [mm]", self.height_spin),
                              ("Longitud [mm]", self.length_spin),
                              ("Radio [mm]", self.radius_spin),
                              ("Profundidad [mm]", self.depth_spin),
                              ("Solución", self.method_combo),
                              ("Posición", self.position_combo)):
            self.form.addRow(title, widget)
        body.addLayout(self.form)
        self.mechel_controls = QWidget()
        mechel = QFormLayout(self.mechel_controls)
        mechel.setContentsMargins(0, 0, 0, 0)
        mechel.setVerticalSpacing(2)
        seal_row = QWidget()
        seal_layout = QHBoxLayout(seal_row)
        seal_layout.setContentsMargins(0, 0, 0, 0)
        self.seal_group = QButtonGroup(self)
        self.unsealed_radio = QRadioButton("Unsealed")
        self.sealed_radio = QRadioButton("Sealed")
        for button in (self.unsealed_radio, self.sealed_radio):
            self.seal_group.addButton(button)
            seal_layout.addWidget(button)
        self.mass1_spin = _number()
        self.mass2_spin = _number()
        self.empty_check = QCheckBox("Cavity is empty · cámara vacía")
        self.absorption_combo = QComboBox()
        for title, widget in (("Mechel", seal_row),
                              ("Mass Side 1 [kg/m²]", self.mass1_spin),
                              ("Mass Side 2 [kg/m²]", self.mass2_spin),
                              ("", self.empty_check),
                              ("Cavity Absorption", self.absorption_combo)):
            mechel.addRow(title, widget)
        body.addWidget(self.mechel_controls)
        self.area_label = _label("")
        self.notice = _label("")
        body.addWidget(self.area_label)
        body.addWidget(self.notice)
        body.addStretch(1)
        layout.addWidget(self.controls)
        self.enabled_check.toggled.connect(lambda v: self._set(enabled=v))
        self.slit_radio.toggled.connect(lambda on: self._change_kind("slit") if on else None)
        self.aperture_radio.toggled.connect(lambda on: self._change_kind("aperture") if on else None)
        for widget, key in ((self.height_spin, "height_mm"), (self.length_spin, "length_mm"),
                            (self.radius_spin, "radius_mm"), (self.depth_spin, "depth_mm"),
                            (self.mass1_spin, "mass_side1_kg_m2"),
                            (self.mass2_spin, "mass_side2_kg_m2")):
            widget.valueChanged.connect(lambda value, key=key: self._set(**{key: value}))
        self.method_combo.currentIndexChanged.connect(
            lambda _: self._set(method=self.method_combo.currentData()))
        self.position_combo.currentIndexChanged.connect(
            lambda _: self._set(position=self.position_combo.currentData()))
        self.sealed_radio.toggled.connect(lambda on: self._set(mechel_sealed=on))
        self.empty_check.toggled.connect(
            lambda on: self._set(cavity_empty=on, mechel_absorption=not on))
        self.absorption_combo.currentIndexChanged.connect(self._absorption_selected)
        self.set_entries(())
        self.set_settings(self._settings)

    def _change_kind(self, kind: str) -> None:
        if self._loading:
            return
        position = self._settings.position
        if kind == "slit" and position == "corner":
            position = "middle"
        self._set(kind=kind, position=position)
        self.set_settings(self._settings)

    def set_entries(self, entries) -> None:
        self.entries = tuple(e for e in entries if e.kind == "absorption")
        self.absorption_combo.blockSignals(True)
        self.absorption_combo.clear()
        self.absorption_combo.addItem("Sin material seleccionado", None)
        for entry in self.entries:
            self.absorption_combo.addItem(entry.name, entry.id)
        selected = self._settings.cavity_absorption
        if selected is not None and not any(e.id == selected.id for e in self.entries):
            self.absorption_combo.addItem(selected.name + " · proyecto", selected.id)
        self.absorption_combo.setCurrentIndex(max(0, self.absorption_combo.findData(
            selected.id if selected else None)))
        self.absorption_combo.blockSignals(False)

    def _absorption_selected(self, _index) -> None:
        key = self.absorption_combo.currentData()
        entry = next((e for e in self.entries if e.id == key), None)
        if entry is None and self._settings.cavity_absorption is not None:
            if self._settings.cavity_absorption.id == key:
                entry = self._settings.cavity_absorption
        self._set(cavity_absorption=entry)

    def set_settings(self, settings: LeakSettings) -> None:
        self._loading = True
        try:
            self._settings = settings
            self.enabled_check.setChecked(settings.enabled)
            self.slit_radio.setChecked(settings.kind == "slit")
            self.aperture_radio.setChecked(settings.kind == "aperture")
            for widget, key in ((self.height_spin, "height_mm"), (self.length_spin, "length_mm"),
                                (self.radius_spin, "radius_mm"), (self.depth_spin, "depth_mm"),
                                (self.mass1_spin, "mass_side1_kg_m2"),
                                (self.mass2_spin, "mass_side2_kg_m2")):
                _display(widget, getattr(settings, key))
            self.method_combo.setCurrentIndex(self.method_combo.findData(settings.method))
            self.position_combo.setCurrentIndex(self.position_combo.findData(settings.position))
            self.sealed_radio.setChecked(settings.mechel_sealed)
            self.unsealed_radio.setChecked(not settings.mechel_sealed)
            self.empty_check.setChecked(settings.cavity_empty)
            self.set_entries(self.entries)
            self.validation_error = ""
            self._field_errors.clear()
            self._update_availability()
        finally:
            self._loading = False
        self.validityChanged.emit(self.validation_error)

    def _update_availability(self) -> None:
        s = self._settings
        self.controls.setEnabled(s.enabled)
        self.form.setRowVisible(self.height_spin, s.kind == "slit")
        self.form.setRowVisible(self.length_spin, s.kind == "slit")
        self.form.setRowVisible(self.radius_spin, s.kind == "aperture")
        self.position_combo.model().item(2).setEnabled(s.kind == "aperture")
        self.mechel_controls.setVisible(s.method == "mechel")
        self.absorption_combo.setEnabled(not s.cavity_empty)
        self.depth_spin.setEnabled(s.method != "open_area")
        self.position_combo.setEnabled(s.method != "open_area")
        self.area_label.setText(f"Área geométrica de la fuga: {s.area_m2:g} m²")
        self.notice.setText(
            "Área abierta ideal: combina áreas con transmisión unitaria por el hueco. "
            "La profundidad y posición no intervienen en esta aproximación."
            if s.method == "open_area" else
            f"{s.method.title()}: parámetros conservados; solución acústica aún no implementada. "
            "El cálculo de esta configuración permanecerá bloqueado."
        )


class _PorousEditor(_Editor):
    def __init__(self, settings, entries=(), parent=None, facing=False):
        super().__init__(settings, parent)
        self._is_facing = facing
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(3)
        self.enabled_check = QCheckBox("Facing · incluir revestimiento poroso")
        self.enabled_check.setVisible(facing)
        layout.addWidget(self.enabled_check)
        self.controls = QWidget()
        body = QVBoxLayout(self.controls)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(3)
        self.thickness_spin = _number(0 if facing else .001)
        self.sigma_spin = _number(0, 1e12, 2)
        self.sigma_spin.setSpecialValueText("Sin definir")
        self.count_spin = QSpinBox()
        self.count_spin.setRange(0, 10)
        self.picker = ProductPicker(entries, kind="absorption")
        self.thickness_spin.setMaximumWidth(100)
        self.count_spin.setMaximumWidth(55)
        self.count_spin.setToolTip("Cantidad; 0 excluye el revestimiento")
        self.picker.search_row.addWidget(_label("Thickness [mm]"))
        self.picker.search_row.addWidget(self.thickness_spin)
        if facing:
            self.picker.search_row.addWidget(_label("Qty"))
            self.picker.search_row.addWidget(self.count_spin)
        body.addWidget(self.picker, 1)
        details = QHBoxLayout()
        self.material_label = _label("Material manual")
        details.addWidget(self.material_label, 1)
        details.addWidget(_label("σ [Pa·s/m²]"))
        self.sigma_spin.setMaximumWidth(125)
        details.addWidget(self.sigma_spin)
        body.addLayout(details)
        note = _label("Miki · introduce la resistividad con su propia fuente.")
        note.setToolTip("Fluido equivalente de esqueleto rígido. El campo Damping del catálogo "
                        "no se interpreta como resistividad al flujo.")
        body.addWidget(note)
        layout.addWidget(self.controls)
        self.enabled_check.toggled.connect(lambda value: self._set(enabled=value))
        self.thickness_spin.valueChanged.connect(lambda value: self._set(thickness_mm=value))
        self.sigma_spin.valueChanged.connect(
            lambda value: self._set(flow_resistivity_pa_s_m2=value or None))
        self.count_spin.valueChanged.connect(lambda value: self._set(count=value))
        self.picker.entrySelected.connect(self._material_selected)
        self.set_settings(settings)

    def set_entries(self, entries) -> None:
        self.picker.set_entries(entries)

    def _material_selected(self, entry) -> None:
        thickness = entry.properties.get("thickness_m")
        fields = {"material": entry, "flow_resistivity_pa_s_m2": None}
        if isinstance(thickness, (int, float)) and thickness > 0:
            fields["thickness_mm"] = thickness * 1000
        self._set(**fields)
        self.set_settings(self._settings)

    def set_settings(self, settings: Facing | PorousSettings) -> None:
        self._loading = True
        try:
            self._settings = settings
            if self._is_facing:
                self.enabled_check.setChecked(settings.enabled)
                self.count_spin.setValue(settings.count)
            _display(self.thickness_spin, settings.thickness_mm)
            _display(self.sigma_spin, settings.flow_resistivity_pa_s_m2 or 0)
            material = settings.material
            self.material_label.setText(material.name if material else "Material manual")
            self.picker.select_entry(material.id if material else None)
            self.validation_error = ""
            self._field_errors.clear()
            self._update_availability()
        finally:
            self._loading = False
        self.validityChanged.emit(self.validation_error)

    def _update_availability(self) -> None:
        self.controls.setEnabled(not self._is_facing or self._settings.enabled)


class FacingEditor(_PorousEditor):
    def __init__(self, entries=(), parent=None):
        super().__init__(Facing(), entries, parent, facing=True)


class PorousEditor(_PorousEditor):
    def __init__(self, entries=(), parent=None):
        super().__init__(PorousSettings(), entries, parent)


class RainfallEditor(_Editor):
    def __init__(self, parent=None):
        super().__init__(RainfallSettings(), parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(3)
        row = QHBoxLayout()
        self.rain_group = QButtonGroup(self)
        self.laboratory_radio = QRadioButton("Laboratory Rain")
        self.natural_radio = QRadioButton("Natural Rain")
        for button in (self.laboratory_radio, self.natural_radio):
            self.rain_group.addButton(button)
            row.addWidget(button)
        layout.addLayout(row)
        self.form = QFormLayout()
        self.form.setVerticalSpacing(2)
        self.class_combo = QComboBox()
        for title in ("Moderate", "Intense", "Heavy", "Cloudburst"):
            self.class_combo.addItem(title, title.lower())
        self.intensity_spin = _number(.001)
        self.area_spin = _number(.001)
        self.form.addRow("Clase de lluvia de laboratorio", self.class_combo)
        self.form.addRow("Intensidad natural [mm/h]", self.intensity_spin)
        self.form.addRow("Área expuesta [m²]", self.area_spin)
        layout.addLayout(self.form)
        layout.addWidget(_label(
            "Los parámetros de lluvia se guardan en el proyecto. La predicción de ruido "
            "de lluvia LpA necesita un modelo de excitación por gotas y radiación que "
            "todavía no está implementado; no se sustituye por aislamiento aéreo."
        ))
        layout.addStretch(1)
        self.laboratory_radio.toggled.connect(
            lambda on: self._set(rain_type="laboratory") if on else None)
        self.natural_radio.toggled.connect(
            lambda on: self._set(rain_type="natural") if on else None)
        self.class_combo.currentIndexChanged.connect(
            lambda _: self._set(laboratory_class=self.class_combo.currentData()))
        self.intensity_spin.valueChanged.connect(lambda value: self._set(natural_mm_h=value))
        self.area_spin.valueChanged.connect(lambda value: self._set(rainfall_area_m2=value))
        self.set_settings(self._settings)

    def set_settings(self, settings: RainfallSettings) -> None:
        self._loading = True
        try:
            self._settings = settings
            self.laboratory_radio.setChecked(settings.rain_type == "laboratory")
            self.natural_radio.setChecked(settings.rain_type == "natural")
            self.class_combo.setCurrentIndex(self.class_combo.findData(settings.laboratory_class))
            _display(self.intensity_spin, settings.natural_mm_h)
            _display(self.area_spin, settings.rainfall_area_m2)
            self.validation_error = ""
            self._field_errors.clear()
            self._update_availability()
        finally:
            self._loading = False
        self.validityChanged.emit(self.validation_error)

    def _update_availability(self) -> None:
        self.class_combo.setEnabled(self._settings.rain_type == "laboratory")
        self.intensity_spin.setEnabled(self._settings.rain_type == "natural")
