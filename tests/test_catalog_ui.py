"""Actual catalogue selection, unit display and user-copy workflows in Qt."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from noiz_transmission.catalog import import_xml, load_catalog
from noiz_transmission.ui.catalog_dialog import CatalogDialog, MaterialEditor


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def xml_path(tmp_path):
    path = tmp_path / "sample.xml"
    path.write_text('''<InsulMaterials xmlns="http://www.insul.co.nz" Version="9.0" Release="22">
    <Material><Name>Panel de prueba</Name><Type>Isotropic</Type><Category>Gypsum</Category>
    <Manufacturer>Ejemplo A</Manufacturer><Region><Spain>-1</Spain></Region><SideA>
    <Density>820</Density><YoungsModulus>2100000000</YoungsModulus><Thickness>0.013</Thickness>
    <Damping>0.02</Damping><PoissonsRatio>0.3</PoissonsRatio><AnisotropicRatio>1</AnisotropicRatio>
    </SideA></Material>
    <Material><Name>Otra placa</Name><Type>Isotropic</Type><Category>Wood</Category>
    <Manufacturer>Ejemplo B</Manufacturer><Region><France>-1</France></Region><SideA>
    <Density>600</Density><YoungsModulus>3000000000</YoungsModulus><Thickness>0.02</Thickness>
    <Damping>0.03</Damping><PoissonsRatio>0.25</PoissonsRatio><AnisotropicRatio>1</AnisotropicRatio>
    </SideA></Material></InsulMaterials>''', encoding="utf-8")
    return path


def test_catalog_search_filter_display_units_and_select(app, xml_path):
    entries = import_xml(xml_path).entries
    dialog = CatalogDialog(entries)
    assert dialog.table.rowCount() == 2
    dialog.search_edit.setText("panel")
    assert dialog.table.rowCount() == 1
    dialog.table.selectRow(0)
    assert dialog.selected_entry == entries[0]
    values = {dialog.property_table.item(i, 0).text(): dialog.property_table.item(i, 1).text()
              for i in range(dialog.property_table.rowCount())}
    assert float(values["Espesor [mm]"]) == 13
    assert float(values["Módulo de Young [GPa]"]) == 2.1
    dialog.search_edit.clear()
    dialog.manufacturer_combo.setCurrentIndex(dialog.manufacturer_combo.findData("Ejemplo B"))
    assert dialog.table.rowCount() == 1
    dialog.table.selectRow(0)
    dialog.use_button.click()
    assert dialog.result() == dialog.DialogCode.Accepted
    assert dialog.selected_entry.name == "Otra placa"
    dialog.close()


def test_custom_copy_preserves_import_and_converts_display_units(app, xml_path):
    source = import_xml(xml_path).entries[0]
    editor = MaterialEditor(source)
    editor.name_edit.setText("Mi placa revisada")
    editor.source_edit.setText("Hipótesis definida para prueba numérica")
    editor.thickness.setValue(18)
    editor.modulus.setValue(3.4)
    copy = editor.build_entry()
    assert copy.properties["thickness_m"] == 0.018
    assert copy.properties["young_modulus_pa"] == 3.4e9
    assert copy.id != source.id
    assert copy.raw_fields["Parent/SHA256"] == source.source_sha256
    assert copy.properties["user_defined"] is True
    assert source.properties["thickness_m"] == 0.013
    assert source.properties["young_modulus_pa"] == 2.1e9
    editor.close()


def test_import_persists_and_duplicate_import_is_idempotent(app, xml_path, tmp_path, monkeypatch):
    target = tmp_path / "catalog.json"
    monkeypatch.setenv("NOIZ_CATALOG_PATH", str(target))
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *args: ([str(xml_path)], ""))
    dialog = CatalogDialog(())
    dialog.import_files()
    assert len(dialog.entries) == 2
    assert load_catalog(target) == dialog.entries
    dialog.import_files()
    assert len(dialog.entries) == 2
    assert load_catalog(target) == dialog.entries
    dialog.close()


def test_bad_xml_batch_does_not_partially_update_library(app, xml_path, tmp_path, monkeypatch):
    broken = tmp_path / "broken.xml"
    broken.write_text("<bad", encoding="utf-8")
    target = tmp_path / "catalog.json"
    monkeypatch.setenv("NOIZ_CATALOG_PATH", str(target))
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *args: ([str(xml_path), str(broken)], ""))
    errors = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: errors.append(args))
    dialog = CatalogDialog(())
    dialog.import_files()
    assert errors
    assert not dialog.entries
    assert not target.exists()
    dialog.close()
