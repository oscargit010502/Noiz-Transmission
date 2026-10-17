"""V4 camera direction, actual projection, profile dimensions and open framing."""

import os
from dataclasses import replace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6", reason="Desktop extra required")

from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from noiz_transmission.application.assembly_services import default_project
from noiz_transmission.catalog.library import CatalogEntry
from noiz_transmission.ui.section_view import SectionView, profile_geometry


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def view(app):
    widget = SectionView()
    widget.resize(500, 600)
    widget.set_project(default_project())
    widget.show()
    yield widget
    widget.close()
    app.processEvents()


def entry(kind, properties):
    return CatalogEntry(f"synthetic-{kind}", kind, f"Synthetic {kind}", "Metal", "Example", (),
                        properties, {}, "synthetic", "0" * 64, "example")


def metal_project(gauge=.00055):
    base = default_project()
    stud = entry("stud", {"frame_material": "metal", "material_thickness_m": gauge})
    cavity = replace(base.cavities[0], frame_type="steel", stud=stud,
                     stud_width_mm=40, stud_depth_mm=90, absorber_thickness_mm=75)
    return replace(base, cavities=(cavity,))


def raw_vertices(view, vertices):
    distance = view._camera_distance()
    return [(x * (distance + z) / distance, y * (distance + z) / distance, z)
            for x, y, z in vertices]


def test_equal_sized_objects_are_larger_when_nearer_camera(view):
    view.yaw_deg = view.pitch_deg = 0
    near = view.project_point((1, 1, -.5))
    far = view.project_point((1, 1, .5))
    assert near[0] > far[0]
    assert near[1] > far[1]
    assert near[2] < far[2]


@pytest.mark.parametrize("destination, coordinate", [(QPoint(170, 200), 0), (QPoint(200, 170), 1)])
def test_real_mouse_drag_moves_front_surface_in_pointer_direction(view, destination, coordinate):
    view.yaw_deg = view.pitch_deg = 0
    marker = (0, 0, -.25)
    before = view.project_point(marker)
    QTest.mousePress(view, Qt.MouseButton.LeftButton, pos=QPoint(200, 200))
    QTest.mouseMove(view, destination)
    QTest.mouseRelease(view, Qt.MouseButton.LeftButton, pos=destination)
    after = view.project_point(marker)
    assert after[coordinate] < before[coordinate]
    assert view._drag_position is None


def test_metal_is_three_thin_sheets_with_open_interior_and_declared_gauge(view):
    view.set_project(metal_project())
    view.yaw_deg = view.pitch_deg = 0
    studs = [part for part in view.visible_parts() if part.kind == "stud"]
    sheets = [(part, points) for part, points in view.projected_mesh() if part.kind == "stud"]
    assert len(sheets) == 3 * len(studs)
    assert all(part.metal_thickness_mm == pytest.approx(.55) for part in studs)
    first = sheets[:3]
    widths = [max(p[0] for p in raw_vertices(view, pts)) - min(p[0] for p in raw_vertices(view, pts))
              for _, pts in first]
    assert widths == pytest.approx([.00055, .04 - .00055, .04 - .00055])
    # The three components cannot contain an interior point of the channel.
    world = [raw_vertices(view, pts) for _, pts in first]
    midpoint = ((min(p[0] for pts in world for p in pts) + max(p[0] for pts in world for p in pts)) / 2,
                (min(p[2] for pts in world for p in pts) + max(p[2] for pts in world for p in pts)) / 2)
    assert not any(min(p[0] for p in pts) < midpoint[0] < max(p[0] for p in pts) and
                   min(p[2] for p in pts) < midpoint[1] < max(p[2] for p in pts) for pts in world)


def test_unknown_metal_gauge_is_not_invented(view):
    view.set_project(metal_project(None))
    assert all(part.metal_thickness_mm is None for part in view.visible_parts() if part.kind == "stud")
    assert any("desconocido" in note for note in view.geometry_notes())
    view.grab()


def test_timber_remains_solid_and_zero_infill_disappears(view):
    base = default_project()
    cavity = replace(base.cavities[0], frame_type="timber", absorber_thickness_mm=50, absorber_count=0)
    view.set_project(replace(base, cavities=(cavity,)))
    studs = [part for part in view.visible_parts() if part.kind == "stud"]
    assert all(part.style == "wood" for part in studs)
    assert len([part for part, _ in view.projected_mesh() if part.kind == "stud"]) == len(studs)
    assert not any(part.kind == "infill" for part, _ in view.projected_mesh())


def test_wall_section_is_tall_narrow_and_floor_section_horizontal(view):
    viewport = QRectF(20, 20, 460, 500)
    wall = view.section_bounds(viewport)
    assert wall.height() == viewport.height()
    assert wall.width() < wall.height() / 4
    view.set_project(replace(view.project, element_type="floor"))
    floor = view.section_bounds(viewport)
    assert floor.width() == viewport.width()
    assert floor.height() < floor.width() / 4


def test_cutaway_keeps_inputs_and_exposes_cavity(view):
    base = metal_project()
    view.set_project(base)
    view.yaw_deg = view.pitch_deg = 0
    layers = [(part, raw_vertices(view, pts)) for part, pts in view.projected_mesh() if part.kind == "layer"]
    spans = {part.panel_index: max(p[0] for p in pts) - min(p[0] for p in pts) for part, pts in layers}
    assert spans[0] < spans[1]
    assert view.project == base
    assert view.physical_thickness_mm() == 125
    assert any("recortada" in note for note in view.geometry_notes())


@pytest.mark.parametrize("kind", ["Corrugated", "Trapezoidal"])
def test_profile_uses_source_pitch_height_and_sheet_gauge(view, kind):
    profile = entry("profile", {"units_schema_verified": True, "material_type": kind,
                               "Profile/RibL": .2, "Profile/RibH": .04,
                               "Profile/RibW": .04, "Profile/RibV": .1})
    base = default_project()
    layer = replace(base.panels[0].layers[0], thickness_mm=.7, profile=profile)
    view.set_project(replace(base, panels=(replace(base.panels[0], layers=(layer,)),), cavities=()))
    view.yaw_deg = view.pitch_deg = 0
    assert profile_geometry(profile).pitch_m == .2
    assert view.physical_thickness_mm() == .7
    assert view.rendered_envelope_mm() == pytest.approx(40.7)
    assert len(view.projected_mesh()) > 40
    all_points = [p for _, points in view.projected_mesh() for p in raw_vertices(view, points)]
    assert max(p[2] for p in all_points) - min(p[2] for p in all_points) == pytest.approx(.0407)
    view.grab()


def test_invalid_or_unknown_profile_geometry_is_explicit(view):
    profile = entry("profile", {"units_schema_verified": True, "material_type": "Trapezoidal",
                               "Profile/RibL": .2, "Profile/RibH": .04,
                               "Profile/RibW": .1, "Profile/RibV": .15})
    assert profile_geometry(profile) is None
    base = default_project()
    layer = replace(base.panels[0].layers[0], profile=profile)
    view.set_project(replace(base, panels=(replace(base.panels[0], layers=(layer,)),), cavities=()))
    assert any("no disponible" in note for note in view.geometry_notes())
    assert len(view.projected_mesh()) == 1


def test_depth_buffer_keeps_infill_and_studs_behind_opaque_front_board(view):
    """A wide board used to get stripes from incorrectly sorted rear pieces."""
    view.set_project(metal_project())
    view.yaw_deg, view.pitch_deg = -30, 12
    view.set_opacity(1)
    mesh = view.projected_mesh()
    points = [point for _, vertices in mesh for point in vertices]
    xmin, xmax = min(p[0] for p in points), max(p[0] for p in points)
    ymin, ymax = min(p[1] for p in points), max(p[1] for p in points)
    viewport = QRectF(24, 30, view.width() - 48, view.height() - 82)
    scale = min(viewport.width() / (xmax - xmin), viewport.height() / (ymax - ymin)) * .94
    board = next(vertices for part, vertices in mesh if part.kind == "layer" and part.panel_index == 0)
    image = view.grab().toImage()
    for u in (.15, .35, .55, .75, .9):
        for v in (.2, .5, .8):
            # Interior points of the incident opaque face must keep its warm
            # gypsum colour, even where metal/green infill project behind it.
            projected = tuple((1 - v) * ((1 - u) * board[0][k] + u * board[1][k]) +
                              v * ((1 - u) * board[3][k] + u * board[2][k]) for k in (0, 1))
            x = round(viewport.center().x() + (projected[0] - (xmin + xmax) / 2) * scale)
            y = round(viewport.center().y() + (projected[1] - (ymin + ymax) / 2) * scale)
            color = image.pixelColor(x, y)
            assert color.red() > color.green() > color.blue()
