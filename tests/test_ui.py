"""User-workflow regressions for saved V2 projects in the V3 workbench, with offscreen Qt rendering."""

import os
import threading
import time
from dataclasses import replace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6", reason="Install desktop extra to test the GUI")
pytest.importorskip("pyqtgraph", reason="Install desktop extra to test the plot")

from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from noiz_transmission.application.assemblies import AssemblyPrediction
from noiz_transmission.application.assembly_services import (
    default_project,
    default_project_v3,
    load_assembly,
    save_assembly,
)
from noiz_transmission.application.services import Project, list_materials, save_project
from noiz_transmission.ui import main_window
from noiz_transmission.ui.main_window import MainWindow


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def window(qt_app, monkeypatch, tmp_path):
    monkeypatch.setenv("NOIZ_CATALOG_PATH", str(tmp_path / "catalog.json"))
    instance = MainWindow()
    instance._load_into_editor(default_project())
    instance.show()
    qt_app.processEvents()
    yield instance
    instance._saved_project = instance.project
    instance._saved_variants = dict(instance._variants)
    instance._input_error = ""
    instance._field_errors.clear()
    instance._comparison_dirty = False
    instance.close()
    qt_app.processEvents()


def fake_prediction(project, *, cancel_event=None):
    mass = sum(layer.density_kg_m3 * layer.thickness_mm / 1000 * layer.count
               for panel in project.panels for layer in panel.layers)
    return AssemblyPrediction(project, (100., 500., 3150.), (18., 32., 47.),
                              35 if project.incidence == "diffuse" else None, mass, 125,
                              (2500.,), (85.,), ("Resultado de prueba.",))


def wait_for_result(app, window, timeout=8):
    deadline = time.monotonic() + timeout
    while window._busy and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.005)
    app.processEvents()
    assert not window._busy


def test_layout_editor_is_primary_and_results_can_collapse(window, qt_app):
    assert window.part_tabs.count() == 4
    assert window.layer_table.rowCount() == 1
    assert window.right_splitter.sizes()[0] > window.right_splitter.sizes()[1]
    window.resize(1024, 680)
    qt_app.processEvents()
    assert window.size().width() == 1024
    assert window.size().height() == 680
    window.toggle_results_button.click()
    qt_app.processEvents()
    assert not window.results_panel.isVisible()
    assert window.layer_fields["thickness_mm"].isVisible()
    window.restore_layout()
    assert window.results_panel.isVisible()


def test_multilayer_edits_reorder_and_preserve_each_panel(window):
    first = window.project.panels[0].layers[0]
    second = window.project.panels[1]
    window.duplicate_layer()
    window.layer_name_edit.setText("Segunda capa")
    window.layer_fields["thickness_mm"].setValue(18)
    window.count_spin.setValue(2)
    assert window.project.panels[0].layers[0] == first
    assert window.project.panels[0].layers[1].count == 2
    assert window.project.panels[1] == second
    window.move_layer(-1)
    assert window.project.panels[0].layers[0].name == "Segunda capa"
    window.remove_layer()
    assert not window.project.panels[0].layers[0].enabled
    assert window.project.panels[0].layers[1] == first
    for _ in range(8):
        window.add_layer()
    assert len(window.project.panels[0].layers) == 6
    assert not window.layer_buttons["add"].isEnabled()


def test_topology_variants_restore_previous_edits_without_destructive_confirmation(window):
    original = window.project
    window.assembly_combo.setCurrentIndex(2)
    assert len(window.project.panels) == 3
    assert window.project.panels[:2] == original.panels
    window.layer_fields["thickness_mm"].setValue(27)
    triple = window.project
    window.assembly_combo.setCurrentIndex(0)
    assert len(window.project.panels) == 1
    assert window.part_tabs.count() == 3
    window.assembly_combo.setCurrentIndex(2)
    assert window.project == triple
    window.assembly_combo.setCurrentIndex(1)
    assert window.project == original


def test_invalid_cavity_remains_blocked_when_another_field_changes(window):
    window.part_tabs.setCurrentIndex(1)
    window.absorber_spin.setValue(75)
    window.cavity_fields["depth_mm"].setValue(50)
    window.resistivity_spin.setValue(10000)
    with pytest.raises(ValueError, match="espesor absorbente"):
        window.current_project()
    assert window.project.cavities[0].depth_mm == 100
    window.cavity_fields["depth_mm"].setValue(120)
    assert window.current_project().cavities[0].depth_mm == 120
    assert window.current_project().cavities[0].flow_resistivity_pa_s_m2 == 10000


def test_blank_name_cannot_be_cleared_by_editing_thickness(window):
    window.name_edit.setText("")
    window.layer_fields["thickness_mm"].setValue(20)
    with pytest.raises(ValueError):
        window.current_project()
    window.name_edit.setText("Nueva alternativa")
    assert window.current_project().name == "Nueva alternativa"


def test_async_calculation_then_edit_invalidates_current_but_keeps_comparison(window, qt_app, monkeypatch):
    monkeypatch.setattr(main_window, "predict_assembly", fake_prediction)
    window.calculate()
    assert window._busy
    wait_for_result(qt_app, window)
    assert window.current_result is not None
    assert window.rw_value.text() == "35 dB"
    window.add_comparison()
    assert len(window.predictions) == 1
    window.layer_fields["thickness_mm"].setValue(18)
    assert window.current_result is None
    assert window.rw_value.text() == "— dB"
    assert window.spectrum_table.rowCount() == 0
    assert len(window.predictions) == 1
    assert len(window.traces) == 1
    assert not window.add_comparison_button.isEnabled()


def test_calculation_finishing_after_edit_is_never_displayed(window, qt_app, monkeypatch):
    release = threading.Event()
    def blocked_prediction(project, *, cancel_event=None):
        assert release.wait(timeout=3)
        return fake_prediction(project)
    monkeypatch.setattr(main_window, "predict_assembly", blocked_prediction)
    window.calculate()
    window.name_edit.setText("Edición durante cálculo")
    release.set()
    wait_for_result(qt_app, window)
    assert window.current_result is None
    assert "cambió durante" in window.message_label.text()
    assert window.rw_value.text() == "— dB"


def test_engine_error_does_not_leave_old_rating(window, qt_app, monkeypatch):
    monkeypatch.setattr(main_window, "predict_assembly", fake_prediction)
    window.calculate()
    wait_for_result(qt_app, window)
    window.part_tabs.setCurrentIndex(1)
    window.frame_combo.setCurrentIndex(window.frame_combo.findData("timber"))
    def unsupported(project, *, cancel_event=None):
        raise ValueError("Puentes estructurales no disponibles")
    monkeypatch.setattr(main_window, "predict_assembly", unsupported)
    window.calculate()
    wait_for_result(qt_app, window)
    assert window.current_result is None
    assert window.rw_value.text() == "— dB"
    assert "Puentes estructurales" in window.message_label.text()


def test_six_comparisons_and_current_are_distinct(window, qt_app, monkeypatch):
    monkeypatch.setattr(main_window, "predict_assembly", fake_prediction)
    for i in range(6):
        window.name_edit.setText(f"Alternativa {i + 1}")
        window.calculate()
        wait_for_result(qt_app, window)
        window.add_comparison()
    assert len(window.predictions) == 6
    assert len(window.traces) == 7
    assert window.comparison_table.rowCount() == 6
    window.add_comparison()
    assert len(window.predictions) == 6
    window.comparison_table.selectRow(2)
    window.remove_selected()
    assert len(window.predictions) == 5
    assert window.current_result.project.name == "Alternativa 6"


def test_round_trip_keeps_precise_snapshots_and_unedited_settings(window, tmp_path, monkeypatch):
    original = default_project()
    layer = replace(original.panels[0].layers[0], density_kg_m3=937.123456789, thickness_mm=12.3456789)
    original = replace(original, panels=(replace(original.panels[0], layers=(layer,)), original.panels[1]),
                       air_density_kg_m3=1.10345678, sound_speed_m_s=340.1234567,
                       limiting_angle_deg=61.23456789, width_m=3.456789, notes="Fuente externa")
    source, target = tmp_path / "source.json", tmp_path / "copy.json"
    save_assembly(original, source)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: (str(source), ""))
    window.open_project()
    assert window.current_project() == original
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(target), ""))
    assert window.save_as()
    assert load_assembly(target) == original
    window.layer_fields["loss_factor"].setValue(.075)
    assert window.current_project().panels[0].layers[0].density_kg_m3 == 937.123456789
    assert window.current_project().air_density_kg_m3 == original.air_density_kg_m3


def test_open_v1_project_migrates_without_resetting_properties(window, tmp_path, monkeypatch):
    material = replace(list_materials()[0], density_kg_m3=915.6789)
    legacy = Project("Anterior", material.id, 19.125, material_snapshot=material,
                     catalog_version="external", air_density_kg_m3=1.11, sound_speed_m_s=336)
    path = tmp_path / "v1.json"
    save_project(legacy, path)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: (str(path), ""))
    window.open_project()
    project = window.current_project()
    assert len(project.panels) == 1
    assert project.panels[0].layers[0].density_kg_m3 == 915.6789
    assert project.panels[0].layers[0].thickness_mm == 19.125
    assert project.air_density_kg_m3 == 1.11
    assert window.assembly_combo.currentIndex() == 0
    assert not window._editor_has_changes()


def test_cancel_close_and_new_preserve_unsaved_project(window, monkeypatch):
    window.name_edit.setText("No descartar")
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Cancel)
    window.new_project()
    assert window.project.name == "No descartar"
    window.close()
    assert window.isVisible()
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Discard)
    window.new_project()
    assert window.project == default_project_v3()


def test_real_engine_single_leaf_reaches_plot_and_band_table(window, qt_app):
    project = default_project()
    project = replace(project, panels=(project.panels[0],), cavities=(), incidence="normal")
    window._load_into_editor(project)
    window.calculate()
    wait_for_result(qt_app, window, timeout=15)
    assert window.current_result is not None
    assert window.current_result.rw_db is None
    assert window.rw_value.text() == "N/A"
    assert window.spectrum_table.rowCount() == len(window.current_result.frequencies_hz)
    assert window.spectrum_table.rowCount() > 15
    assert len(window.traces) == 1
    frequencies, levels = window.traces[0].getOriginalDataset()
    assert frequencies == pytest.approx(window.current_result.frequencies_hz)
    assert levels == pytest.approx(window.current_result.tl_db)


def test_close_cancels_active_worker_without_blocking(window, qt_app, monkeypatch):
    started, stopped = threading.Event(), threading.Event()
    def cancellable(project, *, cancel_event=None):
        started.set()
        assert cancel_event.wait(timeout=3)
        stopped.set()
        raise ValueError("Cálculo cancelado")
    monkeypatch.setattr(main_window, "predict_assembly", cancellable)
    window.calculate()
    assert started.wait(timeout=1)
    start = time.monotonic()
    window.close()
    assert time.monotonic() - start < .5
    assert not window.isVisible()
    assert stopped.wait(timeout=1)
    qt_app.processEvents()


def test_invalid_edit_cancels_work_and_preserves_validation_error(window, qt_app, monkeypatch):
    started = threading.Event()
    def cancellable(project, *, cancel_event=None):
        started.set()
        assert cancel_event.wait(timeout=3)
        raise ValueError("Cálculo cancelado")
    monkeypatch.setattr(main_window, "predict_assembly", cancellable)
    window.calculate()
    assert started.wait(timeout=1)
    window.name_edit.setText("")
    wait_for_result(qt_app, window)
    assert window.current_result is None
    assert window._input_error
    assert window.message_label.text() == window._input_error
    with pytest.raises(ValueError):
        window.current_project()


def test_loaded_values_expand_editor_ranges_without_clipping(window):
    project = default_project()
    layer = replace(project.panels[0].layers[0], thickness_mm=6500.125,
                    density_kg_m3=150000, loss_factor=12, count=10,
                    young_modulus_pa=100, poisson_ratio=-.9995)
    cavity = replace(project.cavities[0], depth_mm=12000, stud_spacing_mm=20000,
                     absorber_thickness_mm=11000, flow_resistivity_pa_s_m2=2e8)
    project = replace(project, panels=(replace(project.panels[0], layers=(layer,)), project.panels[1]),
                      cavities=(cavity,))
    window._load_into_editor(project)
    for key in ("thickness_mm", "density_kg_m3", "loss_factor", "poisson_ratio"):
        assert window.layer_fields[key].value() == pytest.approx(getattr(layer, key))
    assert window.count_spin.value() == 10
    assert window.layer_fields["young_modulus_pa"].value() == pytest.approx(1e-7)
    window.part_tabs.setCurrentIndex(1)
    assert window.cavity_fields["depth_mm"].value() == 12000
    assert window.cavity_fields["stud_spacing_mm"].value() == 20000
    assert window.absorber_spin.value() == 11000
    assert window.resistivity_spin.value() == 2e8
    assert window.current_project() == project
