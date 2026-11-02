"""Automatic results use the latest valid editor snapshot without blocking Qt."""

import os
import threading
import time
from dataclasses import replace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")

from PySide6.QtCore import QEvent, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QMessageBox,
    QTextEdit,
)

from noiz_transmission.application.assemblies import AssemblyPrediction, Cavity
from noiz_transmission.application.assembly_services import (
    default_project_v7,
    model_name_for_project,
    save_assembly,
)
from noiz_transmission.catalog import CatalogEntry
from noiz_transmission.ui import main_window
from noiz_transmission.ui.main_window import MainWindow


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def create_window(app, monkeypatch, tmp_path):
    monkeypatch.setenv("NOIZ_CATALOG_PATH", str(tmp_path / "catalog.json"))
    windows = []

    def create(predict=None):
        if predict is not None:
            monkeypatch.setattr(main_window, "predict_assembly", predict)
        window = MainWindow()
        windows.append(window)
        window.show()
        app.processEvents()
        return window

    yield create
    for window in windows:
        window._saved_project = window.project
        window._saved_variants = dict(window._variants)
        window._input_error = ""
        window._field_errors.clear()
        window._comparison_dirty = False
        window.close()
        window.deleteLater()
        app.sendPostedEvents(window, QEvent.Type.DeferredDelete)
    app.processEvents()


def wait_until(app, condition, timeout=5):
    deadline = time.monotonic() + timeout
    while not condition() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.005)
    app.processEvents()
    assert condition()


def fake_prediction(project, *, cancel_event=None):
    mass = sum(layer.density_kg_m3 * layer.thickness_mm / 1000 * layer.count
               for panel in project.panels for layer in panel.layers if layer.enabled)
    return AssemblyPrediction(project, (100., 500., 3150.), (mass, mass + 10, mass + 20),
                              35, mass, 125, (2500.,), (), ("Prueba de interacción.",))


def recording_solver(calls):
    def predict(project, *, cancel_event=None):
        calls.append(project)
        return fake_prediction(project, cancel_event=cancel_event)
    return predict


def ready(app, window):
    wait_until(app, lambda: window.current_result is not None and not window._busy)


def test_default_single_populates_results_without_calculate(create_window, app):
    window = create_window()
    ready(app, window)
    assert window.current_result.project == window.project
    assert window.current_result.model_name == model_name_for_project(window.project)
    assert window.spectrum_table.rowCount() == 21
    assert window.current_result.rw_db is not None
    assert window.chart_view.isVisible() and window.spectrum_table.isVisible()
    assert not window._editor_has_changes()


def test_rapid_edits_are_coalesced_and_preserve_saved_comparisons(create_window, app):
    calls = []
    window = create_window(recording_solver(calls))
    ready(app, window)
    window.add_comparison()
    previous = window.predictions[0]
    calls.clear()
    for thickness in (14, 18, 22):
        window.layer_fields["thickness_mm"].setValue(thickness)
    assert window.current_result is None
    ready(app, window)
    assert len(calls) == 1
    assert calls[0].panels[0].layers[0].thickness_mm == 22
    assert window.current_result.project == window.project
    assert window.predictions == [previous]


def test_typing_valid_thickness_updates_without_enter_or_focus_out(create_window, app):
    window = create_window(fake_prediction)
    ready(app, window)
    field = window.layer_fields["thickness_mm"]
    field.setFocus()
    QTest.keyClick(field, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    QTest.keyClicks(field, "27.75")
    ready(app, window)
    assert field.hasFocus()
    assert window.current_result.project.panels[0].layers[0].thickness_mm == 27.75


def test_incomplete_number_waits_and_same_value_recovery_restores_result(create_window, app):
    calls = []
    window = create_window(recording_solver(calls))
    ready(app, window)
    calls.clear()
    field = window.layer_fields["thickness_mm"]
    original = field.value()
    field.setFocus()
    QTest.keyClick(field, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    QTest.keyClick(field, Qt.Key.Key_Backspace)
    assert not field.hasAcceptableInput()
    wait_until(app, lambda: bool(window._input_error))
    assert window.current_result is None and calls == []
    QTest.keyClicks(field, str(original))
    ready(app, window)
    # Returning to an already calculated snapshot may reuse its valid cache.
    assert calls == []
    assert window.current_result.project.panels[0].layers[0].thickness_mm == original
    assert not window._input_error


def test_edits_during_work_cancel_old_snapshot_and_only_run_latest(create_window, app):
    calls = []
    started, release = threading.Event(), threading.Event()

    def predict(project, *, cancel_event=None):
        calls.append(project)
        if len(calls) == 1:
            started.set()
            assert release.wait(3)
        return fake_prediction(project)

    window = create_window(predict)
    try:
        wait_until(app, started.is_set)
        worker = window._worker
        window.layer_fields["thickness_mm"].setValue(18)
        window.layer_fields["thickness_mm"].setValue(23)
        wait_until(app, lambda: not window._auto_timer.isActive())
        assert worker.cancel_event.is_set()
        assert len(calls) == 1 and window.current_result is None
        release.set()
        ready(app, window)
        assert len(calls) == 2
        assert calls[-1].panels[0].layers[0].thickness_mm == 23
        assert window.current_result.project == calls[-1]
    finally:
        release.set()


def test_invalid_model_cancels_pending_and_recovers_without_click(create_window, app):
    calls = []
    window = create_window(recording_solver(calls))
    ready(app, window)
    original_name = window.project.name
    calls.clear()
    window.name_edit.setText("")
    window.layer_fields["thickness_mm"].setValue(16)
    QTest.qWait(2 * window.AUTO_CALCULATE_DELAY_MS)
    assert window._input_error
    assert calls == [] and window.current_result is None
    window.name_edit.setText(original_name)
    ready(app, window)
    assert len(calls) == 1
    assert calls[0].panels[0].layers[0].thickness_mm == 16


def test_open_and_new_projects_calculate_the_loaded_snapshot(create_window, app, monkeypatch, tmp_path):
    window = create_window(fake_prediction)
    ready(app, window)
    original = window.project
    layer = replace(original.panels[0].layers[0], thickness_mm=19)
    loaded = replace(original, name="Proyecto abierto", panels=(replace(original.panels[0], layers=(layer,)),))
    path = tmp_path / "open.json"
    save_assembly(loaded, path)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: (str(path), ""))
    window.open_project()
    ready(app, window)
    assert window.current_result.project == loaded
    window.new_project()
    ready(app, window)
    assert window.current_result.project == original


def test_topology_and_cavity_controls_trigger_latest_model(create_window, app):
    calls = []
    window = create_window(recording_solver(calls))
    ready(app, window)
    calls.clear()
    window.topology_tabs.setCurrentIndex(1)
    window.part_tabs.setCurrentIndex(1)
    window.cavity_fields["depth_mm"].setValue(120)
    window.absorber_count_spin.setValue(0)
    ready(app, window)
    assert len(calls) == 1
    assert len(calls[0].panels) == 2
    assert calls[0].cavities[0].depth_mm == 120
    assert calls[0].cavities[0].absorber_count == 0


def test_product_selection_calculates_but_search_and_view_changes_do_not(create_window, app):
    calls = []
    window = create_window(recording_solver(calls))
    ready(app, window)
    entry = CatalogEntry("auto-test", "material", "Placa de prueba", "Gypsum", "Fabricante", (),
                         {"thickness_m": .01, "density_kg_m3": 800, "young_modulus_pa": 2e9,
                          "loss_factor": .03, "poisson_ratio": .3, "material_type": "Isotropic",
                          "solid_model_eligible": True, "units_schema_verified": True,
                          "anisotropic_ratio": 1, "orthotropic_ratio": 1},
                         {}, "synthetic.xml", "0" * 64, "1", ())
    window.material_picker.set_entries((entry,))
    calls.clear()
    window.material_picker.search_edit.setText("Placa")
    window.opacity_slider.setValue(50)
    window.rating_combo.setCurrentIndex(window.rating_combo.findData("stc"))
    QTest.qWait(2 * window.AUTO_CALCULATE_DELAY_MS)
    assert calls == []
    window.material_picker.products_list.setCurrentRow(0)
    ready(app, window)
    assert len(calls) == 1
    assert calls[0].panels[0].layers[0].name == entry.name
    assert calls[0].panels[0].layers[0].thickness_mm == 10


def test_solver_error_is_inline_and_not_retried_until_input_changes(create_window, app, monkeypatch):
    calls = []

    def predict(project, *, cancel_event=None):
        calls.append(project)
        if len(calls) == 1:
            raise ValueError("Parámetros no admitidos para este modelo")
        return fake_prediction(project)

    def unexpected_dialog(*args, **kwargs):
        pytest.fail("Automatic calculation must not interrupt editing with a dialog")

    monkeypatch.setattr(QMessageBox, "critical", unexpected_dialog)
    monkeypatch.setattr(QMessageBox, "warning", unexpected_dialog)
    window = create_window(predict)
    wait_until(app, lambda: "Parámetros no admitidos" in window.message_label.text())
    QTest.qWait(2 * window.AUTO_CALCULATE_DELAY_MS)
    assert len(calls) == 1 and not window._calculation_pending
    window.layer_fields["thickness_mm"].setValue(14)
    ready(app, window)
    assert len(calls) == 2


def test_close_before_debounce_does_not_start_background_work(create_window, app):
    calls = []
    window = create_window(recording_solver(calls))
    window.close()
    QTest.qWait(2 * window.AUTO_CALCULATE_DELAY_MS)
    assert calls == []
    assert not window._auto_timer.isActive()


def test_close_cancels_worker_and_discards_pending_restart(create_window, app):
    calls = []
    started, stopped = threading.Event(), threading.Event()

    def predict(project, *, cancel_event=None):
        calls.append(project)
        started.set()
        assert cancel_event.wait(3)
        stopped.set()
        raise ValueError("Cancelado")

    window = create_window(predict)
    wait_until(app, started.is_set)
    window.layer_fields["thickness_mm"].setValue(18)
    window._saved_project = window.project
    window._saved_variants = dict(window._variants)
    start = time.monotonic()
    window.close()
    assert time.monotonic() - start < .5
    wait_until(app, stopped.is_set)
    QTest.qWait(2 * window.AUTO_CALCULATE_DELAY_MS)
    assert len(calls) == 1
    assert not window._calculation_pending


def test_legacy_steel_wall_upgrades_and_calculates_without_bridge_inputs(create_window, app, monkeypatch):
    window = create_window()
    single = default_project_v7()
    panel = single.panels[0]
    legacy = replace(single, panels=(panel, replace(panel, name="Panel 2")),
                     cavities=(Cavity(depth_mm=90, frame_type="steel",
                                      absorber_thickness_mm=50),))
    window._load_into_editor(legacy)
    window.part_tabs.setCurrentIndex(1)
    wait_until(app, lambda: not window._busy and window.message_label.objectName() == "error")
    assert window.current_result is None
    assert window.project.calculation_model == "davy"
    assert window.automatic_model_button.isVisible()
    window.automatic_model_button.click()
    ready(app, window)
    assert window.project == replace(legacy, calculation_model="auto")
    assert window.current_result.project == window.project
    assert window.current_result.model_name == model_name_for_project(window.project)
    assert window.spectrum_table.rowCount() == 21
    cavity = window.project.cavities[0]
    assert cavity.point_compliance_m_n is None and cavity.line_compliance_m2_n is None
    assert cavity.flow_resistivity_pa_s_m2 is None
    assert not window.resistivity_spin.isVisible()
    assert not window.automatic_model_button.isVisible()
    assert window.bridge_button.text() == "Detalles del frame…"
    before = window.project
    inspected = []

    def inspect(dialog):
        info = dialog.findChild(QTextEdit, "automaticFrameDetails")
        assert info is not None and info.isReadOnly()
        assert not dialog.findChildren(QDoubleSpinBox)
        assert "No necesitas" in info.toPlainText()
        inspected.append(True)
        return QDialog.DialogCode.Rejected

    monkeypatch.setattr(QDialog, "exec", inspect)
    window.bridge_button.click()
    assert inspected and window.project == before
