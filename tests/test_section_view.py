"""Construction-to-mesh and real Qt navigation checks for the V3 renderer."""

import os
from dataclasses import replace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6", reason="Install the desktop extra to verify rendering")

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from noiz_transmission.application.assemblies import Facing, PorousSettings
from noiz_transmission.application.assembly_services import default_project
from noiz_transmission.ui.section_view import SectionView


@pytest.fixture(scope="module")
def qt_app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def view(qt_app):
    widget = SectionView()
    widget.resize(520, 560)
    widget.show()
    yield widget
    widget.close()
    qt_app.processEvents()


def test_disabled_layers_and_zero_infill_are_absent_from_the_mesh(view):
    project = default_project()
    first = project.panels[0]
    board = first.layers[0]
    first = replace(first, layers=(replace(board, count=3), replace(board, enabled=False)))
    cavity = replace(project.cavities[0], absorber_thickness_mm=35, absorber_count=0)
    view.set_project(replace(project, panels=(first, project.panels[1]), cavities=(cavity,)))
    layers = [part for part in view.visible_parts() if part.kind == "layer"]
    assert len(layers) == 4
    assert [part.repeat_index for part in layers[:3]] == [0, 1, 2]
    assert not any(part.kind == "infill" for part in view.visible_parts())
    assert view.physical_thickness_mm() == pytest.approx(board.thickness_mm * 4 + cavity.depth_mm)
    assert len(view.projected_mesh()) == 4


def test_facing_on_incident_side_counts_and_porous_standalone(view):
    base = default_project()
    single = replace(base, panels=(base.panels[0],), cavities=(),
                     facing=Facing(enabled=True, thickness_mm=20, count=2))
    view.set_project(single)
    parts = view.visible_parts()
    assert [part.kind for part in parts] == ["facing", "facing", "layer"]
    assert parts[0].depth_mm == 0
    assert parts[2].depth_mm == 40
    view.set_project(replace(single, facing=replace(single.facing, count=0)))
    assert not any(part.kind == "facing" for part in view.visible_parts())
    view.set_project(replace(single, element_type="porous", porous=PorousSettings(thickness_mm=80)))
    assert [(part.kind, part.thickness_mm) for part in view.visible_parts()] == [("porous", 80)]


def test_stud_width_spacing_and_depth_generate_bounded_geometry(view):
    base = default_project()
    cavity = replace(base.cavities[0], frame_type="timber", stud_width_mm=45,
                     stud_depth_mm=90, stud_spacing_mm=600)
    view.set_project(replace(base, width_m=2.4, cavities=(cavity,)))
    studs = [part for part in view.visible_parts() if part.kind == "stud"]
    assert len(studs) == 5
    assert all(part.width_m == pytest.approx(.045) for part in studs)
    assert [part.x_m for part in studs] == pytest.approx([0, .6, 1.2, 1.8, 2.355])
    assert all(part.thickness_mm == 90 for part in studs)
    view.set_project(replace(base, cavities=(replace(cavity, frame_type="independent"),)))
    assert not any(part.kind == "stud" for part in view.visible_parts())


def test_mouse_orbit_changes_geometry_wheel_zoom_and_doubleclick_restore(view, qt_app):
    view.set_project(default_project())
    initial_mesh = view.projected_mesh()
    initial_angles = view.yaw_deg, view.pitch_deg
    initial_image = view.grab().toImage()
    QTest.mousePress(view, Qt.MouseButton.LeftButton, pos=QPoint(200, 200))
    QTest.mouseMove(view, QPoint(265, 230))
    QTest.mouseRelease(view, Qt.MouseButton.LeftButton, pos=QPoint(265, 230))
    assert (view.yaw_deg, view.pitch_deg) != initial_angles
    assert view.projected_mesh() != initial_mesh
    assert view.grab().toImage() != initial_image
    wheel = QWheelEvent(QPointF(250, 250), QPointF(250, 250), QPoint(), QPoint(0, 120),
                        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                        Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(view, wheel)
    assert view.zoom > 1
    QTest.mouseDClick(view, Qt.MouseButton.LeftButton, pos=QPoint(250, 250))
    assert view.zoom == 1
    assert (view.yaw_deg, view.pitch_deg) == initial_angles


def test_cut_and_horizontal_orientation_render_distinct_images(view):
    project = default_project()
    view.set_project(project)
    wall_mesh = view.projected_mesh()
    wall_image = view.grab().toImage()
    view.set_exploded(False)
    cut_image = view.grab().toImage()
    assert wall_image != cut_image
    angles = view.yaw_deg, view.pitch_deg
    QTest.mousePress(view, Qt.MouseButton.LeftButton, pos=QPoint(200, 200))
    QTest.mouseMove(view, QPoint(300, 300))
    QTest.mouseRelease(view, Qt.MouseButton.LeftButton, pos=QPoint(300, 300))
    assert (view.yaw_deg, view.pitch_deg) == angles
    view.set_exploded(True)
    view.set_project(replace(project, element_type="floor"))
    assert view.horizontal
    assert view.projected_mesh() != wall_mesh
    assert view.grab().toImage() != wall_image


def test_opacity_changes_render_without_changing_construction(view):
    view.set_project(default_project())
    mesh = view.projected_mesh()
    opaque = view.grab().toImage()
    view.set_opacity(.3)
    assert view.grab().toImage() != opaque
    assert view.projected_mesh() == mesh
    with pytest.raises(ValueError, match="opacidad"):
        view.set_opacity(float("nan"))
    with pytest.raises(ValueError, match="opacidad"):
        view.set_opacity(2)


def test_four_panel_mesh_and_active_thickness(view):
    base = default_project()
    view.set_project(replace(base, panels=base.panels * 2, cavities=base.cavities * 3))
    parts = view.visible_parts()
    assert len([part for part in parts if part.kind == "layer"]) == 4
    assert len([part for part in parts if part.kind == "cavity"]) == 3
    assert view.physical_thickness_mm() == pytest.approx(350)
    view.grab()  # Exercise QPainter for the complete four-panel construction.
