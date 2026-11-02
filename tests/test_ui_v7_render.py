"""V7 visible outlines, framing and explicitly schematic isolator families."""

import os
from dataclasses import replace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from noiz_transmission.application.assembly_services import default_project
from noiz_transmission.catalog import CatalogEntry
from noiz_transmission.ui.section_view import SectionView, isolator_symbol


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def view(app):
    widget = SectionView()
    widget.resize(500, 600)
    yield widget
    widget.close()


def connection(name, material="metal"):
    return CatalogEntry("synthetic-support", "connection", name, "Example", "Synthetic", (),
                        {"frame_material": material, "material_thickness_m": .00055},
                        {}, "synthetic", "0" * 64, "example")


def test_visible_black_borders_have_no_triangle_diagonals_or_hidden_edges():
    pixels = np.full((22, 22, 4), 220, dtype=np.uint8)
    pixels[:, :, 3] = 255
    face = [(3., 3., 0.), (18., 3., 0.), (18., 18., 0.), (3., 18., 0.)]
    depths = np.full((22, 22), 10.)
    SectionView._draw_visible_edges(pixels, depths, [(face, 1.)], 10., 1.)
    assert pixels[3, 10, 0] < 100
    assert pixels[10, 10, :3].tolist() == [220] * 3
    # Exactly the same projected rear border must not penetrate the board.
    before = pixels.copy()
    rear = [(x, y, z + .0125) for x, y, z in face]
    SectionView._draw_visible_edges(pixels, depths, [(rear, 1.)], 10., 1.)
    assert np.array_equal(pixels, before)


def test_opacity_zero_also_hides_outlines():
    pixels = np.full((12, 12, 4), 255, dtype=np.uint8)
    face = [(2., 2., 0.), (9., 2., 0.), (9., 9., 0.), (2., 9., 0.)]
    SectionView._draw_visible_edges(pixels, np.full((12, 12), np.inf), [(face, 0.)], 10., 1.5)
    assert np.all(pixels == 255)


def test_tracks_are_open_and_infill_remains_between_studs_without_changing_inputs(view):
    base = default_project()
    cavity = replace(base.cavities[0], frame_type="steel", stud=connection("Steel stud"),
                     absorber_thickness_mm=75)
    project = replace(base, cavities=(cavity,))
    view.set_project(project)
    tracks = [part for part in view.visible_parts() if part.kind == "track"]
    assert len(tracks) == 2
    assert tracks[0].y_m == 0
    assert tracks[-1].y_m + tracks[-1].height_m == pytest.approx(project.height_m)
    assert len([part for part, _ in view.projected_mesh() if part.kind == "track"]) == 6
    assert any(part.kind == "infill" for part, _ in view.projected_mesh())
    assert view.project == project
    assert view.physical_thickness_mm() == 125


@pytest.mark.parametrize("name,kind,style", [
    ("Steel Spring Hanger with neoprene", "spring", "metal"),
    ("Neoprene isolation hanger", "neoprene", "rubber"),
    ("AMC Akustik+Sylomer 1 hangers", "sylomer", "sylomer"),
])
def test_named_discrete_supports_are_local_symbols_not_full_height_studs(view, name, kind, style):
    base = default_project()
    cavity = replace(base.cavities[0], frame_type="unknown", stud=connection(name, "unknown"),
                     stud_depth_mm=40, depth_mm=100)
    project = replace(base, cavities=(cavity,))
    view.set_project(project)
    assert isolator_symbol(cavity.stud) == kind
    supports = [part for part in view.visible_parts() if part.kind == "isolator"]
    assert supports and all(part.style == style for part in supports)
    assert not any(part.kind in ("stud", "track") for part in view.visible_parts())
    assert all(part.height_m < project.height_m / 8 for part in supports)
    assert all(12.5 <= part.depth_mm
               and part.depth_mm + part.thickness_mm <= 112.5
               for part in supports)
    assert any("no BIM" in note for note in view.geometry_notes())
    mesh = view.projected_mesh()
    assert all(np.isfinite(value) for _, vertices in mesh for point in vertices for value in point)
    pieces = [part for part, _ in mesh if part.kind == "isolator"]
    assert len(pieces) > 30 * len(supports) if kind == "spring" else len(pieces) == 3 * len(supports)
    view.grab()
    view.set_exploded(False)
    view.grab()
    assert view.project == project


def test_unidentified_connection_does_not_invent_spring_or_elastomer(view):
    base = default_project()
    source = connection("Unidentified resilient connection", "unknown")
    view.set_project(replace(base, cavities=(replace(base.cavities[0], frame_type="unknown", stud=source),)))
    assert isolator_symbol(source) is None
    assert not any(part.kind == "isolator" for part in view.visible_parts())
    assert any("herrajes y posición no definidos" in note for note in view.geometry_notes())


def test_separate_structural_frames_have_independent_tracks_and_free_gap(view):
    base = default_project()
    cavity = replace(base.cavities[0], frame_type="steel", stud=connection("Steel stud"),
                     stud_configuration="independent", depth_mm=220, stud_depth_mm=90)
    project = replace(base, cavities=(cavity,))
    view.set_project(project)
    tracks = [part for part in view.visible_parts() if part.kind == "track"]
    assert len(tracks) == 4
    assert sorted(set(part.depth_mm for part in tracks)) == [12.5, 142.5]
    assert any("sin soleras comunes" in note for note in view.geometry_notes())
    assert view.project == project
    # An impossible layout is called out, not silently resized or depicted
    # as a single shared frame while the calculation says independent.
    view.set_project(replace(base, cavities=(replace(cavity, depth_mm=180),)))
    assert not any(part.kind in ("stud", "track") for part in view.visible_parts())
    assert any("montantes omitidos" in note for note in view.geometry_notes())
