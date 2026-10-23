"""V6 model selection, explicit boundary losses and safe repeated calculations."""

import copy
import math
import os
import time
from dataclasses import replace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication, QComboBox, QDialog, QDoubleSpinBox

from noiz_transmission.application.assemblies import AssemblyPrediction
from noiz_transmission.application.assembly_services import default_project, default_project_v6
from noiz_transmission.core.transfer import NOMINAL_BANDS_HZ
from noiz_transmission.ui import main_window
from noiz_transmission.ui.main_window import MainWindow, _PredictionWorker
from noiz_transmission.ui.prediction_cache import PredictionCache
from noiz_transmission.ui.spectrum_chart import fitted_reference


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app, monkeypatch, tmp_path):
    monkeypatch.setenv("NOIZ_CATALOG_PATH", str(tmp_path / "empty.json"))
    instance = MainWindow()
    yield instance
    instance._saved_project = instance.project
    instance._saved_variants = dict(instance._variants)
    instance._input_error = ""
    instance._field_errors.clear()
    instance._comparison_dirty = False
    instance.close()
    instance.deleteLater()
    app.sendPostedEvents(instance, QEvent.Type.DeferredDelete)
    app.processEvents()


def fake_prediction(project):
    return AssemblyPrediction(project, (100., 500., 3150.), (18., 32., 47.), 35,
                              10., 12.5, (2500.,), (), ("Test result",))


def test_new_projects_select_finite_without_converting_opened_legacy_project(window):
    assert window.project.calculation_model == "finite"
    legacy = default_project()
    window._load_into_editor(legacy)
    assert window.project.calculation_model == "infinite"
    window.topology_tabs.setCurrentIndex(3)
    assert window.project.calculation_model == "infinite"
    assert len(window.project.panels) == 4


def test_settings_persist_geometry_model_and_each_panel_edge_loss(window, monkeypatch):
    window.topology_tabs.setCurrentIndex(3)
    def accept(dialog):
        model = dialog.findChild(QComboBox, "calculationModel")
        assert model.currentData() == "finite"
        dialog.findChild(QDoubleSpinBox, "width_m").setValue(3.125)
        for index, value in enumerate((0, .003, .015, .004), 1):
            dialog.findChild(QDoubleSpinBox, f"edgeLossPanel{index}").setValue(value)
        return QDialog.DialogCode.Accepted
    monkeypatch.setattr(QDialog, "exec", accept)
    window.show_settings()
    assert window.project.width_m == 3.125
    assert [p.edge_loss_factor for p in window.project.panels] == [0, .003, .015, .004]
    assert window.project.calculation_model == "finite"


def test_unchanged_settings_do_not_round_edge_loss(window, monkeypatch):
    panel = replace(window.project.panels[0], edge_loss_factor=.001234567891)
    original = replace(window.project, panels=(panel,), width_m=2.123456789)
    window._load_into_editor(original)
    monkeypatch.setattr(QDialog, "exec", lambda dialog: QDialog.DialogCode.Accepted)
    window.show_settings()
    assert window.project == original


@pytest.mark.parametrize("changed", [
    {"width_m": 3.}, {"height_m": 4.}, {"calculation_model": "infinite"},
    {"air_density_kg_m3": 1.1}, {"notes": "Different source"}, {"name": "Different report"},
])
def test_cache_includes_geometry_model_air_and_report_provenance(changed):
    project = default_project_v6()
    cache = PredictionCache()
    cache.put(fake_prediction(project))
    assert cache.get(project) is not None
    assert cache.get(replace(project, **changed)) is None


def test_cache_includes_panel_edge_losses_and_detaches_mutable_catalog_snapshots():
    project = default_project_v6()
    original = copy.deepcopy(project)
    result = fake_prediction(project)
    cache = PredictionCache()
    cache.put(result)
    panel = replace(project.panels[0], edge_loss_factor=.01)
    assert cache.get(replace(project, panels=(panel,))) is None
    project.panels[0].layers[0].catalog_entry.raw_fields["mutable"] = "changed after insertion"
    assert cache.get(project) is None
    retrieved = cache.get(original)
    assert "mutable" not in retrieved.project.panels[0].layers[0].catalog_entry.raw_fields
    retrieved.project.panels[0].layers[0].catalog_entry.raw_fields["mutable"] = "changed after retrieval"
    assert "mutable" not in cache.get(original).project.panels[0].layers[0].catalog_entry.raw_fields


def test_cache_evicts_lru_and_does_not_store_oversized_payloads():
    a = default_project_v6()
    b, c = replace(a, name="B"), replace(a, name="C")
    cache = PredictionCache(capacity=2)
    cache.put(fake_prediction(a))
    cache.put(fake_prediction(b))
    cache.get(a)
    cache.put(fake_prediction(c))
    assert cache.get(b) is None
    assert cache.get(a) is not None
    assert cache.get(c) is not None
    tiny_cache = PredictionCache(max_bytes=1)
    tiny_cache.put(fake_prediction(a))
    assert tiny_cache.get(a) is None


def test_worker_reuses_success_only_and_honors_cancel_before_cache_lookup(app, monkeypatch):
    calls = []
    def predict(project, *, cancel_event=None):
        calls.append(project)
        return fake_prediction(project)
    monkeypatch.setattr(main_window, "predict_assembly", predict)
    project = default_project_v6()
    cache = PredictionCache()
    first = _PredictionWorker(0, project, cache)
    first.run()
    assert first.cache_hit is False
    second = _PredictionWorker(1, project, cache)
    results = []
    second.signals.finished.connect(lambda *args: results.append(args))
    second.run()
    assert second.cache_hit is True
    assert second.elapsed_seconds >= 0
    assert len(calls) == 1
    assert results[0][1].project == project
    cancelled = _PredictionWorker(2, project, cache)
    cancelled.signals.finished.connect(lambda *args: results.append(args))
    cancelled.cancel_event.set()
    cancelled.run()
    assert results[-1][1] is None
    assert "cancelado" in results[-1][2]
    assert len(calls) == 1


def test_worker_failures_and_cancelled_results_are_not_cached(app, monkeypatch):
    cache = PredictionCache()
    project = default_project_v6()
    worker = _PredictionWorker(0, project, cache)
    def cancelled_result(project, *, cancel_event=None):
        cancel_event.set()
        return fake_prediction(project)
    monkeypatch.setattr(main_window, "predict_assembly", cancelled_result)
    worker.run()
    assert cache.get(project) is None
    def failure(project, *, cancel_event=None):
        raise ValueError("No convergence")
    monkeypatch.setattr(main_window, "predict_assembly", failure)
    _PredictionWorker(1, project, cache).run()
    assert cache.get(project) is None


def test_desktop_reports_cached_run_and_recalculates_after_input_change(window, app, monkeypatch):
    calls = []
    def predict(project, *, cancel_event=None):
        calls.append(project)
        return fake_prediction(project)
    monkeypatch.setattr(main_window, "predict_assembly", predict)
    def calculate():
        window.calculate()
        deadline = time.monotonic() + 3
        while window._busy and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.002)
        app.processEvents()
        assert not window._busy
    calculate()
    assert "Cálculo completado" in window.statusBar().currentMessage()
    calculate()
    assert "recuperado de caché" in window.statusBar().currentMessage()
    assert len(calls) == 1
    window._commit(replace(window.project, width_m=3.0))
    assert window.current_result is None
    calculate()
    assert len(calls) == 2
    assert window.current_result.project.width_m == 3.0
    assert "Cálculo completado" in window.statusBar().currentMessage()


def test_extrapolated_bands_are_marked_and_have_no_principal_rating_or_reference(window):
    project = replace(window.project, width_m=.35, height_m=.4)
    result = replace(fake_prediction(project), frequencies_hz=tuple(NOMINAL_BANDS_HZ),
                     tl_db=tuple(20. + i for i in range(21)))
    # Even a manually supplied scalar may not bypass the validity domain.
    assert result.rw_db == 35
    assert fitted_reference(result, "rw") is None
    assert fitted_reference(result, "stc") is None
    window.current_result = result
    window._refresh_results()
    assert window.rw_value.text() == "N/A"
    assert window.rating_detail.text() == "Fuera del dominio V6"
    assert "1.5 f₁₁" in window.rating_detail.toolTip()
    assert window.reference_trace is None
    assert window.spectrum_table.item(0, 1).background().color().name() == "#fff0c2"
    assert "Extrapolación V6" in window.spectrum_table.item(0, 1).toolTip()
    assert window.octave_table.item(0, 0).background().color().name() == "#fff0c2"
    assert "ámbar" in window.result_status.text()
    window.current_result = replace(result, project=replace(project, calculation_model="infinite"))
    window._refresh_results()
    assert window.reference_trace is not None
    assert window.spectrum_table.item(0, 1).background().color().name() != "#fff0c2"
    assert window.octave_table.item(0, 0).background().color().name() != "#fff0c2"


def test_rw_and_stc_reference_domains_are_checked_independently():
    project = replace(default_project_v6(), width_m=1., height_m=1.)
    # Set 1.5*f11 to 100 Hz, inside the 100 Hz third but below the 125 Hz third.
    length = math.sqrt(project.finite_validity_floor_hz / 100.)
    project = replace(project, width_m=length, height_m=length)
    result = replace(fake_prediction(project), rw_db=None, frequencies_hz=tuple(NOMINAL_BANDS_HZ),
                     tl_db=tuple(20. + i for i in range(21)))
    assert project.rating_extrapolated_bands("rw") == (100,)
    assert project.rating_extrapolated_bands("stc") == ()
    assert fitted_reference(result, "rw") is None
    assert fitted_reference(result, "stc") is not None
