"""An external document opens only after a user activates a safe source link."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication

from noiz_transmission.catalog import import_xml
from noiz_transmission.ui.catalog_dialog import CatalogDialog


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_connection_library_links_wait_for_explicit_click(app, tmp_path, monkeypatch):
    path = tmp_path / "connections.xml"
    path.write_text('''<InsulConnections Version="10.0" Release="8"><Connection>
    <Name>Synthetic connection</Name><Remarks><Technical>
    https://manufacturer.example/plano.pdf
    </Technical></Remarks></Connection></InsulConnections>''')
    calls = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: calls.append(url.toString()))
    dialog = CatalogDialog(import_xml(path).entries)
    dialog.table.selectRow(0)
    assert dialog.selected_entry.kind == "connection"
    assert dialog.kind_combo.findData("connection") >= 0
    assert calls == []
    assert "https://manufacturer.example/plano.pdf" in dialog.reference_browser.toPlainText()
    dialog.reference_browser.anchorClicked.emit(QUrl("file:///C:/not-a-link.ifc"))
    dialog.reference_browser.anchorClicked.emit(QUrl("https://unlisted.example/other"))
    assert calls == []
    dialog.reference_browser.anchorClicked.emit(QUrl("https://manufacturer.example/plano.pdf"))
    assert calls == ["https://manufacturer.example/plano.pdf"]
    dialog.search_edit.setText("nothing")
    dialog.reference_browser.anchorClicked.emit(QUrl("https://manufacturer.example/plano.pdf"))
    assert len(calls) == 1
    dialog.close()


def test_no_source_links_explains_missing_drawings(app, tmp_path):
    path = tmp_path / "connections.xml"
    path.write_text('<InsulConnections><Connection><Name>Example</Name>'
                    '</Connection></InsulConnections>')
    dialog = CatalogDialog(import_xml(path).entries)
    dialog.table.selectRow(0)
    assert "no contiene enlaces" in dialog.reference_browser.toPlainText()
    assert "href" not in dialog.reference_browser.toHtml()
    dialog.close()


@pytest.mark.parametrize("address", [
    "https://fabricación.example/plano.pdf",
    "https://example.com/a%20b.pdf?x=a%26b",
    "HTTPS://manufacturer.example/plano.pdf",
])
def test_reference_click_accepts_qt_url_normalization(app, tmp_path, monkeypatch, address):
    path = tmp_path / "references.xml"
    path.write_text(f'<InsulConnections><Connection><Name>Example</Name><Document>'
                    f'{address}</Document></Connection></InsulConnections>', encoding="utf-8")
    calls = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: calls.append(url))
    dialog = CatalogDialog(import_xml(path).entries)
    dialog.table.selectRow(0)
    dialog.reference_browser.anchorClicked.emit(QUrl(address))
    assert calls == [QUrl(address)]
    dialog.close()
