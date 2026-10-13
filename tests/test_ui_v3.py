"""V3 interaction contracts: topology, inline selection and model-aware controls."""

import os
from dataclasses import replace
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog

from noiz_transmission.application.assemblies import Facing
from noiz_transmission.application.assembly_services import load_assembly, predict_assembly
from noiz_transmission.catalog import CatalogEntry
from noiz_transmission.ui.main_window import MainWindow


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app, monkeypatch, tmp_path):
    monkeypatch.setenv("NOIZ_CATALOG_PATH", str(tmp_path / "empty.json"))
    instance = MainWindow()
    instance.show()
    app.processEvents()
    yield instance
    instance._saved_project = instance.project
    instance._saved_variants = dict(instance._variants)
    instance._input_error = ""
    instance._field_errors.clear()
    instance._comparison_dirty = False
    instance.close()
    app.processEvents()


def entry(name="10mm Plasterboard", kind="material", category="Gypsum", manufacturer="Maker A", **props):
    properties = dict(thickness_m=.01, density_kg_m3=800, young_modulus_pa=2e9,
                      loss_factor=.03, poisson_ratio=.3, material_type="Isotropic",
                      solid_model_eligible=True, units_schema_verified=True,
                      anisotropic_ratio=1, orthotropic_ratio=1)
    properties.update(props)
    return CatalogEntry(name, kind, name, category, manufacturer, (), properties,
                        {}, "synthetic.xml", "0" * 64, "1", ())


def labels(tabs):
    return [tabs.tabText(index) for index in range(tabs.count())]


def select_part(window, text):
    window.part_tabs.setCurrentIndex(labels(window.part_tabs).index(text))


def test_v3_starts_wall_single_with_six_layer_slots(window):
    assert window.project.element_type == "wall"
    assert len(window.project.panels) == 1
    assert labels(window.topology_tabs) == ["Single", "Double", "Triple", "Quad"]
    assert labels(window.part_tabs) == ["Panel 1", "Facing", "Leak"]
    assert window.layer_tabs.count() == 6
    assert window.count_spin.minimum() == 1
    assert window.count_spin.maximum() == 10
    assert set(window.element_buttons) == {"wall", "ceiling", "floor", "roof", "glazing", "porous"}


@pytest.mark.parametrize("kind,limit,prefix,suffix", [
    ("wall", 4, [], ["Leak"]),
    ("ceiling", 4, [], ["Leak"]),
    ("floor", 3, ["Floor cover"], []),
    ("roof", 2, ["Rainfall"], []),
    ("glazing", 4, [], []),
])
def test_element_specific_multi_panel_tabs(window, kind, limit, prefix, suffix):
    window.element_buttons[kind].click()
    assert window.topology_tabs.count() == limit
    window.topology_tabs.setCurrentIndex(limit - 1)
    expected = list(prefix)
    for index in range(limit):
        expected.append(f"Panel {index + 1}")
        if index < limit - 1:
            expected.append(f"Frame {index + 1}")
    assert labels(window.part_tabs) == expected + suffix
    assert len(window.project.panels) == limit
    assert len(window.project.cavities) == limit - 1
    assert window.result_tabs.isTabVisible(3) == (kind == "floor")


def test_browsing_empty_layer_slot_never_adds_phantom_material(window):
    before = window.project
    window.layer_tabs.setCurrentIndex(5)
    assert not window.layer_enabled.isChecked()
    assert window.project == before
    window.layer_enabled.setChecked(True)
    assert len(window.project.panels[0].layers) == 6
    assert [layer.enabled for layer in window.project.panels[0].layers] == [True, False, False, False, False, True]
    window.layer_enabled.setChecked(False)
    assert window.project.panels[0].layers[5].enabled is False


def test_inline_product_filters_assignment_units_and_editable_thickness(window):
    a = entry()
    b = entry("Wood 20", category="Wood", manufacturer="Maker B", thickness_m=.02)
    window.entries = (a, b)
    window._refresh_pickers()
    picker = window.material_picker
    original = window.project
    picker.search_edit.setText("Plasterboard")
    assert picker.products_list.count() == 1
    assert window.project == original
    window.layer_tabs.setCurrentIndex(2)
    picker.products_list.setCurrentRow(0)
    selected = window.project.panels[0].layers[2]
    assert selected.catalog_entry == a
    assert selected.thickness_mm == 10
    assert window.layer_fields["thickness_mm"].value() == 10
    window.layer_fields["thickness_mm"].setValue(14)
    assert window.project.panels[0].layers[2].thickness_mm == 14
    assert window.project.panels[0].layers[2].catalog_entry.properties["thickness_m"] == .01
    picker.search_edit.clear()
    for row in range(picker.manufacturer_list.count()):
        if picker.manufacturer_list.item(row).data(Qt.ItemDataRole.UserRole) == "Maker B":
            picker.manufacturer_list.setCurrentRow(row)
    assert picker.products_list.count() == 1
    assert window.project.panels[0].layers[2].name == a.name


def test_element_and_topology_switches_restore_each_draft(window):
    window.layer_fields["thickness_mm"].setValue(19)
    single = window.project
    window.topology_tabs.setCurrentIndex(3)
    select_part(window, "Panel 4")
    window.layer_fields["thickness_mm"].setValue(31)
    quad = window.project
    window.element_buttons["floor"].click()
    window.topology_tabs.setCurrentIndex(1)
    floor = window.project
    window.element_buttons["wall"].click()
    assert window.project == quad
    window.topology_tabs.setCurrentIndex(0)
    assert window.project == single
    window.element_buttons["floor"].click()
    assert window.project == floor


def test_facing_is_not_silently_active_when_multi_panel_hides_it(window):
    window._set_project_field("facing", Facing(enabled=True, thickness_mm=25, flow_resistivity_pa_s_m2=10000))
    single = window.project
    window.topology_tabs.setCurrentIndex(1)
    assert "Facing" not in labels(window.part_tabs)
    assert not window.project.facing.enabled
    window.topology_tabs.setCurrentIndex(0)
    assert window.project == single


def test_stud_selection_loads_dimensions_and_independent_clears_bridge(window):
    stud = entry("Timber 90x45", kind="stud", category="Timber", frame_material="timber",
                 stud_depth_m=.09, stud_width_m=.045, stud_spacing_m=.4)
    window.topology_tabs.setCurrentIndex(1)
    select_part(window, "Frame 1")
    window._select_stud_entry(stud)
    cavity = window.project.cavities[0]
    assert (cavity.stud_depth_mm, cavity.stud_width_mm, cavity.stud_spacing_mm) == (90, 45, 400)
    assert cavity.stud == stud
    window.frame_combo.setCurrentIndex(window.frame_combo.findData("independent"))
    assert window.project.cavities[0].stud is None
    assert window.project.cavities[0].frame_type == "independent"


def test_absorber_quantity_zero_retains_product_excludes_render_and_calculation(window):
    absorber = entry("Synthetic wool", kind="absorption", category="Mineral Wool", thickness_m=.05)
    window.topology_tabs.setCurrentIndex(1)
    select_part(window, "Frame 1")
    window._select_absorber_entry(absorber)
    window.resistivity_spin.setValue(12000)
    assert window.project.cavities[0].absorber_thickness_mm == 50
    window.absorber_count_spin.setValue(0)
    assert window.project.cavities[0].absorber == absorber
    assert window.project.cavities[0].flow_resistivity_pa_s_m2 == 12000
    assert window.project.cavities[0].absorber_count == 0
    assert "Synthetic wool" not in window.description_label.text()
    assert not window.resistivity_spin.isEnabled()
    window.absorber_count_spin.setValue(1)
    assert "Synthetic wool" in window.description_label.text()


def test_glazing_gas_is_preserved_in_project_and_changes_prediction(window):
    window.element_buttons["glazing"].click()
    window.topology_tabs.setCurrentIndex(1)
    select_part(window, "Frame 1")
    assert window.gas_combo.isVisible()
    window.gas_combo.setCurrentIndex(window.gas_combo.findData("argon"))
    assert window.project.cavities[0].gas == "argon"
    assert "Leak" not in labels(window.part_tabs)


def test_leak_controls_store_geometry_and_no_claim_for_unimplemented_solution(window):
    select_part(window, "Leak")
    editor = window.leak_editor
    editor.enabled_check.setChecked(True)
    editor.aperture_radio.setChecked(True)
    editor.radius_spin.setValue(2)
    editor.depth_spin.setValue(15)
    editor.position_combo.setCurrentIndex(editor.position_combo.findData("corner"))
    editor.method_combo.setCurrentIndex(editor.method_combo.findData("mechel"))
    assert window.project.leak.kind == "aperture"
    assert window.project.leak.radius_mm == 2
    assert window.project.leak.position == "corner"
    assert window.project.leak.method == "mechel"
    with pytest.raises(ValueError, match="Mechel|mechel|Gomperts"):
        predict_assembly(window.project)
    editor.enabled_check.setChecked(False)
    assert not window.project.leak.enabled


def test_floor_and_roof_show_excitation_without_fabricated_predictions(window):
    for kind, excitation in (("floor", "impact"), ("roof", "rainfall")):
        window.element_buttons[kind].click()
        assert window.project.excitation == excitation
        assert window.excitation_combo.currentData() == excitation
        assert window.excitation_combo.isVisible()
        with pytest.raises(ValueError):
            predict_assembly(window.project)
        window.excitation_combo.setCurrentIndex(window.excitation_combo.findData("airborne"))
        assert window.project.excitation == "airborne"


def test_porous_summary_uses_actual_porous_depth_not_placeholder_panel(window):
    window.element_buttons["porous"].click()
    assert labels(window.part_tabs) == ["Porous"]
    assert window.thickness_value.text() == "50 mm"
    assert window.mass_value.text() == "—"
    assert "no inferida" in window.physics_footer.text()


def test_save_v3_current_configuration_preserves_all_controls(window, tmp_path, monkeypatch):
    window.topology_tabs.setCurrentIndex(3)
    select_part(window, "Panel 4")
    window.count_spin.setValue(7)
    window.layer_fields["thickness_mm"].setValue(11.1234)
    select_part(window, "Frame 2")
    window.absorber_count_spin.setValue(0)
    window.cavity_fields["stud_spacing_mm"].setValue(425)
    select_part(window, "Leak")
    window.leak_editor.depth_spin.setValue(21)
    target = tmp_path / "quad.noiz.json"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(target), ""))
    before = window.project
    assert window.save_as()
    assert load_assembly(target) == before


def test_conditions_dialog_preserves_precision_when_apply_is_unchanged(window, monkeypatch):
    project = replace(window.project, width_m=2.123456789, sound_speed_m_s=343.123456789)
    window._load_into_editor(project)
    monkeypatch.setattr(QDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    window.show_settings()
    assert window.project == project


def test_workspace_save_reopen_restores_other_topologies_and_elements(window, tmp_path, monkeypatch):
    window.layer_fields["thickness_mm"].setValue(17)
    single = window.project
    window.topology_tabs.setCurrentIndex(3)
    select_part(window, "Panel 4")
    window.layer_fields["thickness_mm"].setValue(29)
    quad = window.project
    window.element_buttons["floor"].click()
    window.topology_tabs.setCurrentIndex(1)
    floor = window.project
    window.element_buttons["wall"].click()
    window.topology_tabs.setCurrentIndex(0)
    target = tmp_path / "workspace.noiz.json"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(target), ""))
    assert window.save_as()
    assert not window._editor_has_changes()
    window.new_project()
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: (str(target), ""))
    window.open_project()
    assert window.project == single
    window.topology_tabs.setCurrentIndex(3)
    assert window.project == quad
    window.element_buttons["floor"].click()
    assert window.project == floor


def test_editing_other_variant_stays_dirty_when_returning_to_saved_active(window, tmp_path, monkeypatch):
    target = tmp_path / "saved.json"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(target), ""))
    assert window.save_as()
    window.topology_tabs.setCurrentIndex(3)
    window.layer_fields["thickness_mm"].setValue(77)
    window.topology_tabs.setCurrentIndex(0)
    assert window.project == window._saved_project
    assert window._editor_has_changes()
    assert window.save_current_project()
    assert not window._editor_has_changes()


def test_legacy_area_leak_becomes_visible_checkbox_and_disable_removes_it(window):
    original = replace(window.project, leak_percentage=.1)
    window._load_into_editor(original)
    assert window.project.leak_percentage == 0
    assert window.project.leak.enabled
    assert window.project.leak.method == "open_area"
    assert window.project.leak.area_m2 == pytest.approx(original.width_m * original.height_m * .001)
    select_part(window, "Leak")
    assert window.leak_editor.enabled_check.isChecked()
    window.leak_editor.enabled_check.setChecked(False)
    assert not window.project.leak.enabled
    assert window.project.leak_percentage == 0


def test_floor_base_filters_products_and_predicted_never_displays_measured_curve(window):
    raw = {"IsolationGain/Data/Hz100": "5", "IsolationGain/Data/Hz200": "7",
           "IsolationGain/Source": "Synthetic curve", "CoverType": "LightWeight"}
    light = replace(entry("Synthetic light", kind="floor_cover", cover_type="LightWeight", thickness_m=.005), raw_fields=raw)
    heavy = replace(entry("Synthetic heavy", kind="floor_cover", cover_type="HeavyWeight"),
                    raw_fields={**raw, "CoverType": "HeavyWeight"})
    window.entries = (light, heavy)
    window._refresh_pickers()
    window.element_buttons["floor"].click()
    select_part(window, "Floor cover")
    assert window.floor_picker.products_list.count() == 1
    assert window.floor_picker.products_list.item(0).text() == light.name
    window.floor_picker.products_list.setCurrentRow(0)
    assert window.project.floor_cover == light
    assert len(window.floor_chart.listDataItems()) == 1
    assert window.thickness_value.text() == "17.5 mm"
    window.floor_base_combo.setCurrentIndex(window.floor_base_combo.findData("heavyweight"))
    assert window.floor_picker.products_list.item(0).text() == heavy.name
    assert len(window.floor_chart.listDataItems()) == 0
    assert "incompatible" in window.floor_spectrum_note.text()
    window.floor_picker.products_list.setCurrentRow(0)
    assert len(window.floor_chart.listDataItems()) == 1
    window.floor_mode_combo.setCurrentIndex(window.floor_mode_combo.findData("predicted"))
    assert len(window.floor_chart.listDataItems()) == 0
    assert "no está implementado" in window.floor_spectrum_note.text()


def test_f5_flushes_typed_thickness_before_worker_snapshot(window, app):
    field = window.layer_fields["thickness_mm"]
    field.setFocus()
    QTest.keyClick(field, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    QTest.keyClicks(field, "25.5")
    assert window.project.panels[0].layers[0].thickness_mm == 12.5
    workers = []
    window._pool = SimpleNamespace(start=workers.append)
    window.calculate_action.trigger()
    assert workers[-1].project.panels[0].layers[0].thickness_mm == 25.5
    window._busy = False
    window._worker = None


def test_save_flushes_typed_cavity_depth_without_focus_out(window, tmp_path, monkeypatch):
    window.topology_tabs.setCurrentIndex(1)
    select_part(window, "Frame 1")
    field = window.cavity_fields["depth_mm"]
    field.setFocus()
    QTest.keyClick(field, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    QTest.keyClicks(field, "135.25")
    target = tmp_path / "pending.json"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(target), ""))
    assert window.save_current_project()
    assert load_assembly(target).cavities[0].depth_mm == 135.25


def test_rejected_material_does_not_remain_selected_in_inline_list(window):
    bad = entry("Unverified composite", material_type="Composite", solid_model_eligible=False)
    good = entry()
    window.entries = (good, bad)
    window._refresh_pickers()
    window.material_picker.products_list.setCurrentRow(0)
    before = window.project
    window.material_picker.products_list.setCurrentRow(1)
    assert window.project == before
    assert window.material_picker.selected_entry == good
    assert window.material_picker.products_list.currentItem().text() == good.name


@pytest.mark.parametrize("kind", ["glazing", "porous"])
def test_legacy_leak_has_visible_control_to_disable(window, kind):
    original = replace(window.project, element_type=kind, leak_percentage=.1)
    window._load_into_editor(original)
    assert "Leak heredada" in labels(window.part_tabs)
    select_part(window, "Leak heredada")
    window.leak_editor.enabled_check.setChecked(False)
    assert not window.project.leak.enabled
    assert window.project.leak_percentage == 0


def test_new_single_current_project_ignores_unvisited_cavity_inputs(window):
    assert window.current_project() == window.project
    assert not window._input_error


@pytest.mark.parametrize("mode,attribute,key,typed", [
    ("Leak", "height_spin", "height_mm", "2.75"),
    ("Porous", "thickness_spin", "thickness_mm", "73.25"),
])
def test_shortcut_flushes_active_specialized_editor(window, mode, attribute, key, typed):
    if mode == "Porous":
        window.element_buttons["porous"].click()
        editor = window.porous_editor
    else:
        select_part(window, "Leak")
        editor = window.leak_editor
        editor.enabled_check.setChecked(True)
    field = getattr(editor, attribute)
    field.setFocus()
    QTest.keyClick(field, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    QTest.keyClicks(field, typed)
    workers = []
    window._pool = SimpleNamespace(start=workers.append)
    window.calculate_action.trigger()
    settings = workers[-1].project.porous if mode == "Porous" else workers[-1].project.leak
    assert getattr(settings, key) == float(typed)
    window._busy = False
    window._worker = None
