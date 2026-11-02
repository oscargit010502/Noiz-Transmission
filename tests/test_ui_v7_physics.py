"""Explicit Davy settings are editable without consuming extra list rows."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication, QCheckBox, QDialog, QDoubleSpinBox

from noiz_transmission.ui.main_window import MainWindow


@pytest.fixture
def window(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setenv("NOIZ_CATALOG_PATH", str(tmp_path / "empty.json"))
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


def test_bridge_dialog_commits_explicit_compliance_and_fastener_spacing(window, monkeypatch):
    window.topology_tabs.setCurrentIndex(1)
    window.part_tabs.setCurrentIndex(1)
    window.frame_combo.setCurrentIndex(window.frame_combo.findData("steel"))
    assert window.project.cavities[0].steel_gauge is None

    def accept(dialog):
        dialog.findChild(QDoubleSpinBox, "fastener_spacing_mm").setValue(250)
        dialog.findChild(QCheckBox, "point_compliance_m_n_enabled").setChecked(True)
        dialog.findChild(QDoubleSpinBox, "point_compliance_m_n").setValue(10)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(QDialog, "exec", accept)
    window.bridge_button.click()
    cavity = window.project.cavities[0]
    assert cavity.fastener_spacing_mm == 250
    assert cavity.point_compliance_m_n == pytest.approx(1e-5)
    assert cavity.steel_gauge is None
    assert "Davy" in window.frame_note.text()
    snapshot = window.project
    monkeypatch.setattr(QDialog, "exec", lambda dialog: QDialog.DialogCode.Accepted)
    window.bridge_button.click()
    assert window.project == snapshot


def test_topology_switch_names_legacy_model_and_restores_davy_variant(window):
    assert window.project.calculation_model == "davy"
    window.topology_tabs.setCurrentIndex(3)
    assert window.project.calculation_model == "finite"
    assert "Triple/Quad usa V6" in window.statusBar().currentMessage()
    assert "V6" in window.composition_summary.text()
    window.topology_tabs.setCurrentIndex(0)
    assert window.project.calculation_model == "davy"
