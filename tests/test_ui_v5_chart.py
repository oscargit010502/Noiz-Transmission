"""V5 reference fidelity, physical square axes and responsive compact summaries."""

import json
import math
import os
import subprocess
import sys
from dataclasses import replace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")

from PySide6.QtCore import QEvent, QPoint
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QApplication, QCheckBox, QStyleOptionViewItem

from noiz_transmission.application.assembly_services import predict_assembly
from noiz_transmission.core.ratings import (
    ISO717_FREQUENCIES_HZ,
    STC_FREQUENCIES_HZ,
    iso717_rw,
    legacy_stc,
)
from noiz_transmission.ui.main_window import MainWindow
from noiz_transmission.ui.spectrum_chart import fitted_reference


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app, monkeypatch, tmp_path):
    monkeypatch.setenv("NOIZ_CATALOG_PATH", str(tmp_path / "missing.json"))
    widget = MainWindow()
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


def assert_square_and_external_legend(window):
    box = window.plot_item.getViewBox()
    assert abs(box.width() - box.height()) <= 2
    assert box.width() > 30
    chart = window.chart_view
    legend = window.legend
    assert legend.x() >= chart.x() + chart.width()
    assert window.spectrum_chart.rect().contains(legend.geometry())
    assert legend.horizontalScrollBar().maximum() == 0


@pytest.mark.parametrize("width,height", [(1366, 768), (1280, 720), (1024, 680)])
def test_axes_are_physically_square_through_resize_splitter_and_collapse(window, app, width, height):
    window.resize(width, height)
    app.processEvents()
    assert_square_and_external_legend(window)
    tick_font = window.plot_item.getAxis("bottom").style["tickFont"]
    low, high = window.plot_item.viewRange()[0]
    octave_gap = window.plot_item.getViewBox().width() * math.log10(2) / (high - low)
    assert QFontMetrics(tick_font).horizontalAdvance("250") + 2 <= octave_gap
    # Deliberately change available height in both directions. Numeric limits
    # must not change merely to enforce equal physical axis length.
    limits = window.plot_item.viewRange()
    for sizes in ([260, 420], [500, 180]):
        window.right_splitter.setSizes(sizes)
        app.processEvents()
        assert_square_and_external_legend(window)
        assert window.plot_item.viewRange() == limits
    window.toggle_results()
    app.processEvents()
    assert not window.results_panel.isVisible()
    window.toggle_results()
    app.processEvents()
    assert_square_and_external_legend(window)


def test_reference_switch_matches_rating_procedures_without_recalculation(window):
    result = predict_assembly(window.project)
    window.current_result = result
    window._refresh_results()
    reference = window.reference_trace
    frequencies, levels = reference.getOriginalDataset()
    selected = [level for frequency, level in zip(result.frequencies_hz, result.tl_db, strict=True)
                if frequency in ISO717_FREQUENCIES_HZ]
    rw = iso717_rw(ISO717_FREQUENCIES_HZ, selected)
    assert tuple(frequencies) == ISO717_FREQUENCIES_HZ
    assert tuple(levels) == rw.reference_curve_db
    assert levels[list(frequencies).index(500)] == result.rw_db
    assert window.rw_value.text() == f"{rw.rw_db} dB"
    before = window.project
    window.rating_combo.setCurrentIndex(window.rating_combo.findData("stc"))
    assert window.project is before
    assert window.current_result is result
    frequencies, levels = window.reference_trace.getOriginalDataset()
    stc = legacy_stc(result.frequencies_hz, result.tl_db)
    assert tuple(frequencies) == STC_FREQUENCIES_HZ
    assert tuple(levels) == stc.reference_curve_db
    assert levels[list(frequencies).index(500)] == stc.stc
    assert "32/8" in window.legend.items[-1][1].toolTip()
    assert len(window.plot_item.listDataItems()) == 2
    assert all("flanking" not in label.text().lower() and "10140" not in label.text()
               for _, label in window.legend.items)


def test_unrated_or_missing_spectrum_has_no_reference(window):
    assert window.reference_trace is None
    result = predict_assembly(window.project)
    partial = replace(result, frequencies_hz=(100., 500.), tl_db=(10., 20.), rw_db=None)
    assert fitted_reference(partial, "rw") is None
    assert fitted_reference(partial, "stc") is None
    normal = replace(result, project=replace(result.project, incidence="normal"), rw_db=None)
    assert fitted_reference(normal, "rw") is None
    assert fitted_reference(normal, "stc") is None
    assert fitted_reference(result, "iic") is None


def test_comparison_legend_wraps_outside_plot_and_controls_visibility(window, app):
    result = predict_assembly(window.project)
    window.current_result = result
    window.predictions = [replace(result, project=replace(result.project, name=("Alternativa acústica " * 15)))
                          for _ in range(6)]
    window._refresh_results()
    app.processEvents()
    assert len(window.traces) == 7
    assert len(window.legend.items) == 8  # Six alternatives, actual TL, actual reference.
    assert_square_and_external_legend(window)
    assert window.legend.verticalScrollBar().maximum() > 0
    checks = window.legend.findChildren(QCheckBox)
    checks[0].setChecked(False)
    assert not window.traces[0].isVisible()
    checks[0].setChecked(True)
    assert window.traces[0].isVisible()
    assert window.reference_trace.isVisible()


def test_hidden_curves_stay_hidden_across_rating_switch_renumbering_and_recalculation(window):
    result = predict_assembly(window.project)
    alternative = replace(result, project=replace(result.project, name="Alternativa conservada"))
    window.current_result = result
    window.predictions = [result, alternative]
    window._refresh_results()
    comparison_key = next(key for key, checkbox in window.legend.checkboxes.items()
                          if "Alternativa conservada" in checkbox.accessibleName())
    for key in (comparison_key, "current", "reference"):
        window.legend.checkboxes[key].click()
    for rating in ("stc", "rw"):
        window.rating_combo.setCurrentIndex(window.rating_combo.findData(rating))
        assert window.traces[0].isVisible()
        assert not window.traces[1].isVisible()
        assert not window.traces[2].isVisible()
        assert not window.reference_trace.isVisible()
        assert all(not window.legend.checkboxes[key].isChecked()
                   for key in (comparison_key, "current", "reference"))
    # Removing an earlier row changes the legend's display number but must
    # not transfer the hidden state to a different saved result.
    window.comparison_table.selectRow(0)
    window.remove_selected()
    assert not window.traces[0].isVisible()
    assert not window.legend.checkboxes[comparison_key].isChecked()
    window.current_result = None
    window._refresh_results()
    window.current_result = replace(result)
    window._refresh_results()
    assert not window.traces[-1].isVisible()
    assert not window.reference_trace.isVisible()
    # A newly saved alternative starts visible, independently of the current
    # curve's visibility preference and of alternatives that were removed.
    window.add_comparison()
    assert window.traces[-2].isVisible()
    assert not window.traces[0].isVisible()
    assert not window.traces[-1].isVisible()
    assert not window.reference_trace.isVisible()


def test_identical_saved_results_keep_independent_visibility_after_removal(window):
    window.current_result = predict_assembly(window.project)
    window.add_comparison()
    window.add_comparison()
    second_key = [key for key in window.legend.checkboxes if key.startswith("comparison:")][1]
    window.legend.checkboxes[second_key].click()
    assert window.traces[0].isVisible()
    assert not window.traces[1].isVisible()
    window.comparison_table.selectRow(0)
    window.remove_selected()
    assert not window.traces[0].isVisible()
    assert not window.legend.checkboxes[second_key].isChecked()
    window.rating_combo.setCurrentIndex(window.rating_combo.findData("stc"))
    assert not window.traces[0].isVisible()
    assert not window.legend.checkboxes[second_key].isChecked()


def test_octave_summary_has_complete_centered_header_and_data(window, app):
    window.current_result = predict_assembly(window.project)
    window._refresh_results()
    window.resize(1024, 680)
    app.processEvents()
    table = window.octave_table
    assert table.height() < 60
    for index in range(7):
        assert table.item(0, index).text() != "—"
        assert table.item(0, index).font().bold()
        assert "Hz" in table.horizontalHeaderItem(index).toolTip()
        model_index = table.model().index(0, index)
        rect = table.visualRect(model_index)
        assert table.viewport().rect().contains(rect)
        option = QStyleOptionViewItem()
        delegate = table.itemDelegateForIndex(model_index)
        delegate.initStyleOption(option, model_index)
        # A visible cell rectangle is insufficient: the native delegate must
        # also fit all glyphs and its text padding without an ellipsis.
        assert rect.width() >= delegate.sizeHint(option, model_index).width()
    assert table.mapTo(window, QPoint(table.width(), 0)).x() < window.rating_combo.mapTo(window, QPoint()).x()


@pytest.mark.parametrize("scale", ["1.25", "1.5"])
def test_high_dpi_axes_and_octave_summary(scale, tmp_path):
    script = '''
import json
from PySide6.QtWidgets import QApplication, QStyleOptionViewItem
from noiz_transmission.application.assembly_services import predict_assembly
from noiz_transmission.ui.main_window import MainWindow
app = QApplication([])
w = MainWindow()
w.show()
w.current_result = predict_assembly(w.project)
w._refresh_results()
measurements=[]
for width,height in ((1366,768),(1280,720),(1024,680)):
    w.resize(width,height)
    app.processEvents()
    t=w.octave_table
    b=w.plot_item.getViewBox()
    text_fits=True
    for i in range(7):
        index=t.model().index(0,i)
        option=QStyleOptionViewItem()
        delegate=t.itemDelegateForIndex(index)
        delegate.initStyleOption(option,index)
        text_fits &= t.visualRect(index).width() >= delegate.sizeHint(option,index).width()
    measurements.append({"width":b.width(),"height":b.height(),
        "legend_right":w.legend.x() >= w.chart_view.x()+w.chart_view.width(),
        "text_fits":text_fits,
        "table_fits":all(t.viewport().rect().contains(t.visualRect(t.model().index(0,i))) for i in range(7))})
print(json.dumps(measurements))
'''
    completed = subprocess.run([sys.executable, "-c", script], check=True, text=True,
                               capture_output=True, timeout=30,
                               env={**os.environ, "QT_SCALE_FACTOR": scale,
                                    "NOIZ_CATALOG_PATH": str(tmp_path / "missing.json")})
    for result in json.loads(completed.stdout.strip().splitlines()[-1]):
        assert abs(result["width"] - result["height"]) <= 2
        assert result["legend_right"]
        assert result["table_fits"]
        assert result["text_fits"]
