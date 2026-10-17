"""Connection selection preserves documented units and original catalogue data."""

import os
from dataclasses import replace

import pytest

from noiz_transmission.application.assemblies import Cavity
from noiz_transmission.application.assembly_services import (
    cavity_from_entry,
    default_project,
    load_workspace,
    predict_assembly,
    save_workspace,
)
from noiz_transmission.catalog import CatalogEntry


def connection(**properties):
    data = dict(units_schema_verified=True, frame_material="metal", stud_depth_m=.095,
                stud_width_m=.045, material_thickness_m=.00055, cavity_width_m=.13,
                stud_spacing_defined=False, stud_spacing_fixed=False,
                defined_stud_spacing_m=.4, connection_code=99, geometry_verified=False)
    data.update(properties)
    return CatalogEntry("synthetic-connection", "connection", "Synthetic connection", "MetalFrame",
                        "Synthetic", (), data, {}, "synthetic.xml", "0" * 64, "99")


def test_connection_uses_declared_cavity_but_not_disabled_spacing():
    original = Cavity(stud_spacing_mm=575)
    entry = connection()
    cavity = cavity_from_entry(original, entry)
    assert (cavity.depth_mm, cavity.stud_depth_mm, cavity.stud_width_mm) == (130, 95, 45)
    assert cavity.stud_spacing_mm == 575
    assert cavity.stud == entry
    assert cavity.stud.kind == "connection"
    assert cavity.frame_type == "steel"
    assert original.depth_mm == 100


def test_defined_spacing_is_applied_only_when_explicitly_enabled():
    result = cavity_from_entry(Cavity(), connection(stud_spacing_defined=True))
    assert result.stud_spacing_mm == 400


@pytest.mark.parametrize("material,kind", [("masonry", "masonry"), ("unknown", "unknown"),
                                           ("timber", "timber")])
def test_frame_category_is_not_inferred_as_steel(material, kind):
    assert cavity_from_entry(Cavity(), connection(frame_material=material)).frame_type == kind


def test_unverified_units_and_wrong_families_cannot_change_geometry():
    with pytest.raises(ValueError, match="unidades"):
        cavity_from_entry(Cavity(), connection(units_schema_verified=False))
    with pytest.raises(ValueError, match="Stud"):
        cavity_from_entry(Cavity(), replace(connection(), kind="material"))


def test_unknown_or_invalid_dimension_keeps_existing_user_value():
    cavity = cavity_from_entry(Cavity(depth_mm=120), connection(cavity_width_m=0,
                                                               stud_depth_m=None))
    assert cavity.depth_mm == 120
    assert cavity.stud_depth_mm == 90


def test_selecting_shallow_connection_cannot_silently_trim_infill():
    original = Cavity(absorber_thickness_mm=80)
    with pytest.raises(ValueError, match="absorbente"):
        cavity_from_entry(original, connection(cavity_width_m=.064))
    assert original.absorber_thickness_mm == 80
    assert original.stud is None


def test_connection_snapshot_roundtrip_and_unsupported_physics(tmp_path):
    cavity = cavity_from_entry(Cavity(), connection())
    project = replace(default_project(), cavities=(cavity,))
    path = tmp_path / "connection.noiz.json"
    save_workspace(project, (), path)
    restored, variants = load_workspace(path)
    assert restored == project
    assert variants == ()
    assert restored.cavities[0].stud.kind == "connection"
    with pytest.raises(ValueError, match="puentes estructurales"):
        predict_assembly(restored)


def test_connection_picker_fixed_spacing_and_view_controls(tmp_path, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    pytest.importorskip("pyqtgraph")
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QApplication

    from noiz_transmission.ui.main_window import MainWindow

    monkeypatch.setenv("NOIZ_CATALOG_PATH", str(tmp_path / "missing.json"))
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    try:
        window.show()
        window.topology_tabs.setCurrentIndex(1)
        window.part_tabs.setCurrentIndex(1)
        entry = connection(stud_spacing_defined=True, stud_spacing_fixed=True)
        window.stud_picker.set_entries((entry,))
        assert window.stud_picker.products_list.count() == 1
        window.stud_picker.products_list.setCurrentRow(0)
        assert window.project.cavities[0].stud == entry
        assert window.cavity_fields["depth_mm"].value() == 130
        assert window.cavity_fields["stud_spacing_mm"].value() == 400
        assert not window.cavity_fields["stud_spacing_mm"].isEnabled()
        assert "fija" in window.cavity_fields["stud_spacing_mm"].toolTip()
        original = window.project
        window.depth_detail_check.setChecked(True)
        window.cutaway_check.setChecked(False)
        assert window.section_view.depth_exaggeration
        assert not window.section_view.cutaway
        assert window.project == original
        window.frame_combo.setCurrentIndex(window.frame_combo.findData("independent"))
        assert window.project.cavities[0].stud is None
        assert window.cavity_fields["stud_spacing_mm"].isEnabled()
        assert "fija" not in window.cavity_fields["stud_spacing_mm"].toolTip()
    finally:
        window._confirm_discard = lambda: True
        window.close()
        window.deleteLater()
        app.sendPostedEvents(window, QEvent.Type.DeferredDelete)
