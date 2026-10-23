"""V4 regressions for usable vertical space, complete summaries and rating selection."""

import json
import os
import subprocess
import sys
from dataclasses import replace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")

from PySide6.QtCore import QEvent, QPoint
from PySide6.QtWidgets import QApplication

from noiz_transmission.application.assemblies import AssemblyPrediction
from noiz_transmission.catalog import bundled_entries
from noiz_transmission.ui.main_window import MainWindow


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app, monkeypatch, tmp_path):
    monkeypatch.setenv("NOIZ_CATALOG_PATH", str(tmp_path / "missing.json"))
    widget = MainWindow()
    widget.resize(1366, 768)
    widget.show()
    app.processEvents()
    yield widget
    widget._saved_project = widget.project
    widget._saved_variants = dict(widget._variants)
    widget._comparison_dirty = False
    widget.close()
    widget.deleteLater()
    app.sendPostedEvents(widget, QEvent.Type.DeferredDelete)
    app.processEvents()


def test_single_prioritizes_products_and_aligns_search_thickness_quantity(window):
    picker = window.material_picker
    listing = picker.products_list
    assert listing.viewport().height() >= 12 * listing.sizeHintForRow(0)
    controls = (picker.search_edit, window.layer_fields["thickness_mm"], window.count_spin)
    tops = [widget.mapTo(window, QPoint(0, 0)).y() for widget in controls]
    assert max(tops) - min(tops) <= 4
    assert window.topology_tabs.mapTo(window, QPoint(0, 0)).y() < 90
    assert not window.layer_properties.isVisible()
    # V5 reserves a taller, physically square results plot; the editor remains
    # the larger pane and preserves the original minimum of 12 product rows.
    assert window.right_splitter.widget(0).height() > window.results_panel.height()
    window.properties_toggle.click()
    assert window.layer_name_edit.isVisible()
    window.properties_toggle.click()
    assert not window.layer_name_edit.isVisible()


@pytest.mark.parametrize("width", [1024, 1366])
def test_octave_header_and_value_row_are_fully_visible(window, app, width):
    window.resize(width, 768)
    app.processEvents()
    table = window.octave_table
    assert table.horizontalHeader().height() >= table.fontMetrics().height()
    for index in range(7):
        rectangle = table.visualRect(table.model().index(0, index))
        assert table.viewport().rect().contains(rectangle)
        assert table.item(0, index).text() == "—"
    right = table.mapTo(window, QPoint(table.width(), 0)).x()
    rating_left = window.rating_combo.mapTo(window, QPoint(0, 0)).x()
    assert rating_left >= right + 2
    page = window.editor_stack.currentWidget()
    assert page.horizontalScrollBar().maximum() == 0
    qty_right = window.count_spin.mapTo(window, QPoint(window.count_spin.width(), 0)).x()
    assert qty_right < window.width()


def test_frame_keeps_stud_and_infill_lists_on_screen(window, app):
    window.topology_tabs.setCurrentIndex(1)
    window.part_tabs.setCurrentIndex(1)
    # Use real populated lists: an empty list returns -1 as its row size.
    for picker in (window.stud_picker, window.absorber_picker):
        picker.set_entries(bundled_entries())
    app.processEvents()
    for picker in (window.stud_picker, window.absorber_picker):
        listing = picker.products_list
        assert listing.isVisible()
        # V6.1 groups the controls to retain at least five complete rows
        # in both lists at 1366 x 768, alongside the larger chart.
        assert listing.viewport().height() >= 5 * listing.sizeHintForRow(0)
        assert listing.sizeHintForRow(0) >= listing.fontMetrics().height()
    page = window.editor_stack.currentWidget()
    assert page.verticalScrollBar().maximum() == 0
    window.resize(1024, 680)
    app.processEvents()
    assert window.width() == 1024
    assert window.height() == 680
    assert window.layer_properties.isHidden()


def test_rating_switch_uses_same_prediction_without_editing_or_recalculating(window):
    frequencies = (50., 63., 80., 100., 125., 160., 200., 250., 315., 400., 500.,
                   630., 800., 1000., 1250., 1600., 2000., 2500., 3150., 4000., 5000.)
    prediction = AssemblyPrediction(window.project, frequencies, tuple(40. for _ in frequencies),
                                    40, 10, 12.5, (2000.,), (), ())
    before = window.project
    window.current_result = prediction
    window._refresh_results()
    assert window.rw_value.text() == "40 dB"
    window.add_comparison()
    window.rating_combo.setCurrentIndex(window.rating_combo.findData("stc"))
    assert window.current_result is prediction
    assert window.project == before
    assert window.rw_value.text() == str(prediction.stc_db)
    assert window.comparison_table.item(0, 4).text() == str(prediction.stc_db)
    assert "32/8" in window.rating_detail.toolTip()
    window.rating_combo.setCurrentIndex(window.rating_combo.findData("rw"))
    assert window.rw_value.text() == "40 dB"


def test_impact_selector_has_no_fabricated_rating_or_room_equivalence(window):
    window.element_buttons["floor"].click()
    assert [window.rating_combo.itemText(i) for i in range(window.rating_combo.count())] == ["IIC", "Ln,w"]
    assert window.rw_value.text() == "—"
    window.rating_combo.setCurrentIndex(1)
    assert window.rw_value.text() == "— dB"
    assert "pendiente" in window.rating_detail.text()
    assert "L’nT,w" in window.rating_detail.toolTip()
    window.excitation_combo.setCurrentIndex(window.excitation_combo.findData("airborne"))
    assert [window.rating_combo.itemText(i) for i in range(window.rating_combo.count())] == ["Rw", "STC"]


def test_normal_incidence_cannot_display_a_rating(window):
    project = replace(window.project, incidence="normal")
    window._load_into_editor(project)
    window.current_result = AssemblyPrediction(project, (100., 500., 3150.), (20., 30., 40.),
                                               None, 10, 12.5, (2000.,), (), ())
    window._refresh_results()
    assert window.rw_value.text() == "N/A"
    window.rating_combo.setCurrentIndex(window.rating_combo.findData("stc"))
    assert window.rw_value.text() == "N/A"


@pytest.mark.parametrize("scale", ["1.25", "1.5"])
def test_scaled_display_keeps_octave_values_and_product_rows_complete(scale, tmp_path):
    script = '''
import json
from PySide6.QtWidgets import QApplication
from noiz_transmission.ui.main_window import MainWindow
app=QApplication([])
w=MainWindow()
w.resize(1366,768)
w.show()
app.processEvents()
t=w.octave_table
listing=w.material_picker.products_list
print(json.dumps({"fits":all(t.viewport().rect().contains(t.visualRect(t.model().index(0,i))) for i in range(7)),
"rows":listing.viewport().height()/listing.sizeHintForRow(0),"size":[w.width(),w.height()]}))
'''
    environment = {**os.environ, "QT_SCALE_FACTOR": scale,
                   "NOIZ_CATALOG_PATH": str(tmp_path / "missing.json")}
    completed = subprocess.run([sys.executable, "-c", script], env=environment,
                               text=True, capture_output=True, check=True, timeout=30)
    result = json.loads(completed.stdout.strip().splitlines()[-1])
    assert result["fits"]
    assert result["rows"] >= 12
    assert result["size"] == [1366, 768]
