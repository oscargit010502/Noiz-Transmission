"""Native arrow hit areas work in both directions, independent of app accents."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QDoubleSpinBox,
    QSpinBox,
    QStyle,
    QStyleFactory,
    QStyleOptionSpinBox,
    QVBoxLayout,
    QWidget,
)

from noiz_transmission.ui.style import STYLESHEET


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("style_name", QStyleFactory.keys())
@pytest.mark.parametrize("kind", [QDoubleSpinBox, QSpinBox])
def test_native_arrow_clicks_increment_and_decrement_without_overlapping(app, style_name, kind):
    previous = app.style().objectName()
    app.setStyle(style_name)
    window = QWidget()
    window.setStyleSheet(STYLESHEET)
    layout = QVBoxLayout(window)
    field = kind()
    field.setRange(1, 10)
    field.setValue(4)
    field.setKeyboardTracking(False)
    layout.addWidget(field)
    try:
        window.show()
        app.processEvents()
        option = QStyleOptionSpinBox()
        field.initStyleOption(option)
        rects = [field.style().subControlRect(QStyle.ComplexControl.CC_SpinBox, option, part,
                                             field) for part in
                 (QStyle.SubControl.SC_SpinBoxUp, QStyle.SubControl.SC_SpinBoxDown)]
        assert all(rect.isValid() and field.rect().contains(rect) for rect in rects)
        assert not rects[0].intersects(rects[1])
        QTest.mouseClick(field, Qt.MouseButton.LeftButton, pos=rects[0].center())
        assert field.value() == 5
        QTest.mouseClick(field, Qt.MouseButton.LeftButton, pos=rects[1].center())
        assert field.value() == 4
        field.setValue(10)
        QTest.mouseClick(field, Qt.MouseButton.LeftButton, pos=rects[0].center())
        assert field.value() == 10
        QTest.mouseClick(field, Qt.MouseButton.LeftButton, pos=rects[1].center())
        assert field.value() == 9
    finally:
        window.close()
        window.deleteLater()
        app.sendPostedEvents(window, QEvent.Type.DeferredDelete)
        app.setStyle(previous)


@pytest.mark.parametrize("style_name", QStyleFactory.keys())
def test_native_arrows_commit_layer_and_infill_changes_to_project(app, style_name, monkeypatch,
                                                                tmp_path):
    from noiz_transmission.ui.main_window import MainWindow

    monkeypatch.setenv("NOIZ_CATALOG_PATH", str(tmp_path / "empty.json"))
    previous = app.style().objectName()
    app.setStyle(style_name)
    window = MainWindow()

    def click_arrow(widget, up):
        assert widget.isVisible() and widget.isEnabled()
        option = QStyleOptionSpinBox()
        widget.initStyleOption(option)
        control = QStyle.SubControl.SC_SpinBoxUp if up else QStyle.SubControl.SC_SpinBoxDown
        rectangle = widget.style().subControlRect(QStyle.ComplexControl.CC_SpinBox, option,
                                                  control, widget)
        QTest.mouseClick(widget, Qt.MouseButton.LeftButton, pos=rectangle.center())
        app.processEvents()

    try:
        window.show()
        app.processEvents()
        thickness = window.layer_fields["thickness_mm"]
        before = window.project.panels[0].layers[0].thickness_mm
        click_arrow(thickness, True)
        assert window.project.panels[0].layers[0].thickness_mm == before + thickness.singleStep()
        click_arrow(thickness, False)
        assert window.project.panels[0].layers[0].thickness_mm == before
        click_arrow(window.count_spin, True)
        assert window.project.panels[0].layers[0].count == 2
        click_arrow(window.count_spin, False)
        assert window.project.panels[0].layers[0].count == 1
        window.topology_tabs.setCurrentIndex(1)
        window.part_tabs.setCurrentIndex(1)
        app.processEvents()
        click_arrow(window.absorber_count_spin, False)
        assert window.project.cavities[0].absorber_count == 0
        click_arrow(window.absorber_count_spin, True)
        assert window.project.cavities[0].absorber_count == 1
    finally:
        window._confirm_discard = lambda: True
        window.close()
        window.deleteLater()
        app.sendPostedEvents(window, QEvent.Type.DeferredDelete)
        app.setStyle(previous)
