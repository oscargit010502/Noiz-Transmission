"""Actual nested controls and inline products preserve intentional user inputs."""

import os
from dataclasses import replace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from noiz_transmission.application.assemblies import Facing, LeakSettings, RainfallSettings
from noiz_transmission.catalog import CatalogEntry
from noiz_transmission.ui.product_picker import ProductPicker
from noiz_transmission.ui.settings_editors import (
    FacingEditor,
    LeakEditor,
    PorousEditor,
    RainfallEditor,
)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def entries():
    def entry(key, name, kind, category, manufacturer, thickness):
        return CatalogEntry(key, kind, name, category, manufacturer, (),
                            {"thickness_m": thickness, "damping_raw": 9900}, {},
                            "synthetic.xml", "a" * 64, key)
    return (entry("one", "10 mm placa de ejemplo", "material", "Gypsum", "Fabricante A", .010),
            entry("two", "20 mm madera de ejemplo", "material", "Wood", "Fabricante B", .020),
            entry("three", "60 mm fibra sintética", "absorption", "Fibre", "Fabricante A", .060))


def test_filtering_does_not_assign_material_and_explicit_selection_emits_snapshot(app, entries):
    picker = ProductPicker(entries, "material")
    events = []
    picker.entrySelected.connect(events.append)
    picker.select_entry("one")
    picker.search_edit.setText("madera")
    assert picker.products_list.count() == 1
    assert not events
    assert picker.selected_entry == entries[0]
    picker.products_list.setCurrentRow(0)
    assert events == [entries[1]]
    assert picker.selected_entry.properties["thickness_m"] == .020
    picker.search_edit.clear()
    picker.category_list.setCurrentRow(1)  # Gypsum, sorted after All
    assert picker.products_list.count() == 1
    assert len(events) == 1
    picker.close()


def test_kind_filter_does_not_replace_current_project_product(app, entries):
    picker = ProductPicker(entries, "material")
    events = []
    picker.entrySelected.connect(events.append)
    picker.select_entry("one")
    picker.set_kind("absorption")
    assert picker.products_list.count() == 1
    assert picker.selected_entry == entries[0]
    assert not events
    picker.close()


def test_leak_restores_all_settings_without_emitting_or_losing_corner(app, entries):
    editor = LeakEditor()
    editor.set_entries(entries)
    events = []
    editor.changed.connect(events.append)
    settings = LeakSettings(enabled=True, kind="aperture", method="mechel", position="corner",
                            radius_mm=3.456789, depth_mm=170,
                            cavity_empty=False, cavity_absorption=entries[2],
                            mass_side1_kg_m2=10, mass_side2_kg_m2=20, mechel_sealed=True)
    editor.set_settings(settings)
    assert not events
    assert editor.settings == settings
    assert editor.aperture_radio.isChecked()
    assert editor.position_combo.currentData() == "corner"
    assert editor.absorption_combo.currentData() == "three"
    editor.slit_radio.click()
    assert editor.settings.kind == "slit"
    assert editor.settings.position == "middle"
    assert editor.settings.radius_mm == settings.radius_mm
    editor.enabled_check.click()
    assert not editor.settings.enabled
    assert editor.settings.cavity_absorption == entries[2]
    editor.close()


def test_open_area_distinguishes_ignored_dimensions_from_gomperts(app):
    editor = LeakEditor()
    editor.enabled_check.click()
    editor.method_combo.setCurrentIndex(editor.method_combo.findData("open_area"))
    editor.height_spin.setValue(2)
    editor.length_spin.setValue(1000)
    assert editor.settings.area_m2 == pytest.approx(.002)
    assert not editor.depth_spin.isEnabled()
    assert not editor.position_combo.isEnabled()
    assert "unitaria" in editor.notice.text()
    editor.method_combo.setCurrentIndex(editor.method_combo.findData("gomperts"))
    assert editor.depth_spin.isEnabled()
    assert "no implementada" in editor.notice.text()
    editor.close()


def test_tiny_imported_leak_dimension_remains_visible_and_exact(app):
    editor = LeakEditor()
    settings = LeakSettings(enabled=True, height_mm=1e-6)
    editor.set_settings(settings)
    assert editor.height_spin.value() == settings.height_mm
    assert float(editor.height_spin.text()) == settings.height_mm
    editor.method_combo.setCurrentIndex(editor.method_combo.findData("open_area"))
    assert editor.settings.area_m2 == pytest.approx(1e-9)
    editor.close()


def test_switching_leak_kind_notifies_parent_when_invalid_input_is_restored(app):
    editor = LeakEditor()
    errors = []
    editor.validityChanged.connect(errors.append)
    editor.enabled_check.click()
    editor.height_spin.setValue(0)
    assert errors[-1]
    editor.aperture_radio.click()
    assert editor.height_spin.value() == editor.settings.height_mm == 1
    assert editor.validation_error == errors[-1] == ""
    editor.close()


@pytest.mark.parametrize("editor_type", [FacingEditor, PorousEditor])
def test_porous_selection_sets_thickness_and_clears_unrelated_sigma(app, entries, editor_type):
    editor = editor_type(entries)
    events = []
    editor.changed.connect(events.append)
    if isinstance(editor, FacingEditor):
        editor.enabled_check.click()
    editor.sigma_spin.setValue(20000)
    editor.picker.products_list.setCurrentRow(0)
    assert editor.settings.material == entries[2]
    assert editor.settings.thickness_mm == 60
    assert editor.settings.flow_resistivity_pa_s_m2 is None
    assert editor.sigma_spin.value() == 0
    assert events[-1].material.properties["damping_raw"] == 9900
    editor.thickness_spin.setValue(75)
    assert editor.settings.thickness_mm == 75
    editor.close()


def test_facing_quantity_zero_preserves_material_for_reactivation(app, entries):
    editor = FacingEditor(entries)
    settings = Facing(True, entries[2], 75, 10000, 2)
    editor.set_settings(settings)
    editor.count_spin.setValue(0)
    assert editor.settings == replace(settings, count=0)
    editor.count_spin.setValue(1)
    assert editor.settings.material == entries[2]
    assert editor.settings.flow_resistivity_pa_s_m2 == 10000
    editor.close()


def test_rainfall_modes_keep_independent_inputs_and_disable_inapplicable_control(app):
    editor = RainfallEditor()
    events = []
    editor.changed.connect(events.append)
    settings = RainfallSettings("natural", "cloudburst", 21.234567, 3.5)
    editor.set_settings(settings)
    assert not events
    assert editor.settings == settings
    assert editor.intensity_spin.isEnabled()
    assert not editor.class_combo.isEnabled()
    editor.laboratory_radio.click()
    assert editor.settings.natural_mm_h == 21.234567
    assert editor.settings.laboratory_class == "cloudburst"
    assert not editor.intensity_spin.isEnabled()
    assert editor.class_combo.isEnabled()
    editor.close()
