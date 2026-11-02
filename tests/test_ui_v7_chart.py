"""V7 shows numeric TL and the locked square plot in the same results view."""

import os
import time
from dataclasses import replace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")

from PySide6.QtCore import QEvent, QPoint, QRect, Qt
from PySide6.QtWidgets import QApplication

from noiz_transmission.application.assemblies import Cavity
from noiz_transmission.application.assembly_services import default_project_v7, predict_assembly
from noiz_transmission.ui.main_window import MainWindow


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app, monkeypatch, tmp_path):
    monkeypatch.setenv("NOIZ_CATALOG_PATH", str(tmp_path / "missing.json"))
    widget = MainWindow()
    widget._load_into_editor(default_project_v7())
    widget.show()
    deadline = time.monotonic() + 5
    while widget.current_result is None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.005)
    assert widget.current_result is not None
    yield widget
    widget._saved_project = widget.project
    widget._saved_variants = dict(widget._variants)
    widget._comparison_dirty = False
    widget.close()
    widget.deleteLater()
    app.sendPostedEvents(widget, QEvent.Type.DeferredDelete)


@pytest.mark.parametrize("width,height", [(1024, 680), (1366, 768), (1366, 980)])
def test_plot_and_complete_spectrum_are_available_together(window, app, width, height):
    window.resize(width, height)
    app.processEvents()
    chart, table = window.spectrum_chart, window.spectrum_table
    assert window.result_tabs.currentWidget() is chart
    assert window.result_tabs.indexOf(table) == -1
    assert table.isVisible() and window.chart_view.isVisible()
    assert table.x() >= window.chart_view.geometry().right()
    assert table.y() > window.legend.geometry().bottom()
    assert chart.rect().contains(table.geometry())
    assert not table.geometry().intersects(window.chart_view.geometry())
    assert table.horizontalScrollBar().maximum() == 0
    assert window.legend.verticalScrollBar().maximum() == 0
    for _, title in window.legend.items:
        position = title.mapTo(window.legend.viewport(), QPoint(0, 0))
        assert window.legend.viewport().rect().contains(QRect(position, title.size()))
    box = window.plot_item.getViewBox()
    assert abs(box.width() - box.height()) <= 2
    result = window.current_result
    assert table.rowCount() == len(result.frequencies_hz) == 21
    for row, (frequency, value) in enumerate(zip(result.frequencies_hz, result.tl_db, strict=True)):
        assert table.item(row, 0).text() == f"{frequency:g}"
        assert table.item(row, 1).text() == f"{value:.2f}"
        assert table.item(row, 1).textAlignment() == Qt.AlignmentFlag.AlignCenter
    table.scrollToBottom()
    app.processEvents()
    assert table.viewport().rect().contains(table.visualRect(table.model().index(20, 1)))


def test_legend_switches_and_saved_comparisons_leave_table_current(window, app):
    values = [window.spectrum_table.item(row, 1).text() for row in range(21)]
    window.add_comparison()
    comparison_tab = window.result_tabs.indexOf(window.comparison_page)
    assert window.result_tabs.tabText(comparison_tab) == "Comparación · 1/6"
    window.rating_combo.setCurrentIndex(window.rating_combo.findData("stc"))
    window.legend.checkboxes["current"].click()
    app.processEvents()
    assert not window.traces[-1].isVisible()
    assert window.spectrum_table.isVisible()
    assert [window.spectrum_table.item(row, 1).text() for row in range(21)] == values
    window.current_result = None
    window._refresh_results()
    assert window.spectrum_table.rowCount() == 0
    assert window.spectrum_table.isVisible()
    assert len(window.traces) == 1


def test_shared_stud_extrapolation_uses_interstud_basis_in_table_and_status(window):
    panel = window.project.panels[0]
    project = replace(window.project, panels=(panel, replace(panel, name="Panel 2")),
                      cavities=(Cavity(100, frame_type="timber", stud_spacing_mm=400),))
    window._load_into_editor(project)
    window.current_result = predict_assembly(project)
    window._refresh_results()
    assert project.panel_mode_basis == "stud_bay"
    assert window.rw_value.text() == "N/A"
    assert window.rating_detail.text() == "Fuera del dominio del modelo"
    note = window.spectrum_table.item(0, 1).toolTip()
    assert "Extrapolación V7" in note and "fᵢ entre montantes" in note
    assert "mayor límite de las dos hojas" in note
    assert "f₁₁" not in note
    assert "fᵢ entre montantes" in window.result_status.text()
    window.rating_combo.setCurrentIndex(window.rating_combo.findData("stc"))
    assert window.rw_value.text() != "N/A"
    assert window.reference_trace is not None
