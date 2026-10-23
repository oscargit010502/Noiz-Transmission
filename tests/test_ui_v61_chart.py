"""A read-only chart keeps its calculated scale through real Qt input events."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QPen, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from noiz_transmission.ui.main_window import MainWindow
from noiz_transmission.ui.spectrum_chart import SquareSpectrumChart


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def chart(app):
    widget = SquareSpectrumChart()
    widget.resize(700, 420)
    widget.show()
    app.processEvents()
    yield widget
    widget.close()
    widget.deleteLater()
    app.sendPostedEvents(widget, QEvent.Type.DeferredDelete)
    app.processEvents()


def assert_user_cannot_change_range(plot_widget, app, target):
    plot = plot_widget.getPlotItem()
    item = plot.getViewBox() if target == "plot" else plot.getAxis(target)
    position = plot_widget.mapFromScene(item.sceneBoundingRect().center())
    viewport = plot_widget.viewport()
    initial_range = plot.viewRange()
    for delta in (120, -120):
        wheel = QWheelEvent(
            QPointF(position), QPointF(viewport.mapToGlobal(position)),
            QPoint(), QPoint(0, delta), Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False,
        )
        app.sendEvent(viewport, wheel)
        app.processEvents()
        assert plot.viewRange() == initial_range

    for button in (Qt.MouseButton.LeftButton, Qt.MouseButton.MiddleButton,
                   Qt.MouseButton.RightButton):
        QTest.mousePress(viewport, button, pos=position)
        QTest.mouseMove(viewport, position + QPoint(18, 8), delay=20)
        QTest.mouseMove(viewport, position + QPoint(35, 15), delay=20)
        QTest.mouseRelease(viewport, button, pos=position + QPoint(35, 15))
        app.processEvents()
        assert plot.viewRange() == initial_range

    QTest.mouseClick(viewport, Qt.MouseButton.RightButton, pos=position)
    QTest.mouseDClick(viewport, Qt.MouseButton.LeftButton, pos=position)
    for key in (Qt.Key.Key_Plus, Qt.Key.Key_Minus, Qt.Key.Key_Backspace):
        QTest.keyClick(viewport, key, Qt.KeyboardModifier.ControlModifier)
    app.processEvents()
    assert app.activePopupWidget() is None
    assert plot.viewRange() == initial_range


@pytest.mark.parametrize("target", ["plot", "left", "bottom"])
def test_wheel_drag_and_context_menu_cannot_edit_axes(chart, app, target):
    assert_user_cannot_change_range(chart.plot_widget, app, target)


def test_floor_covering_uses_the_same_read_only_chart(app, monkeypatch, tmp_path):
    monkeypatch.setenv("NOIZ_CATALOG_PATH", str(tmp_path / "missing.json"))
    window = MainWindow()
    try:
        window._change_element("floor")
        window.result_tabs.setCurrentWidget(window.floor_covering_page)
        window.show()
        window.floor_chart.plot([100, 250, 500, 1000], [10, 18, 24, 28])
        window.floor_chart.setRange(xRange=(2, 3), yRange=(0, 30), padding=0)
        app.processEvents()
        assert window.floor_chart.isVisible()
        for target in ("plot", "left", "bottom"):
            assert_user_cannot_change_range(window.floor_chart, app, target)
        window.floor_chart.setYRange(0, 40, padding=0)
        app.processEvents()
        assert window.floor_chart.viewRange()[1] == [0, 40]
    finally:
        window._saved_project = window.project
        window._saved_variants = dict(window._variants)
        window._comparison_dirty = False
        window.close()
        window.deleteLater()
        app.sendPostedEvents(window, QEvent.Type.DeferredDelete)
        app.processEvents()


def test_locked_chart_still_updates_ranges_and_toggles_curves(chart, app):
    initial_range = chart.plot.viewRange()
    trace = chart.plot.plot([63, 125, 250, 500, 1000], [12, 18, 29, 35, 42],
                            pen=QPen(Qt.GlobalColor.blue), symbol="o")
    chart.legend.addItem(trace, "TL actual", key="current")
    chart.plot.setYRange(0, 110, padding=0)
    app.processEvents()
    assert chart.plot.viewRange()[0] == initial_range[0]
    assert chart.plot.viewRange()[1] == [0, 110]
    checkbox = chart.legend.checkboxes["current"]
    QTest.mouseClick(checkbox, Qt.MouseButton.LeftButton)
    app.processEvents()
    assert not trace.isVisible()
    QTest.mouseClick(checkbox, Qt.MouseButton.LeftButton)
    assert trace.isVisible()
    assert chart.plot.viewRange()[1] == [0, 110]
    chart.plot.autoRange()
    app.processEvents()
    assert chart.plot.viewRange()[1][1] < 110
    assert abs(chart.plot.getViewBox().width() - chart.plot.getViewBox().height()) <= 2
