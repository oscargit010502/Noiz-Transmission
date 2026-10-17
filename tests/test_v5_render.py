"""V5 geometry proportions, cached DPI rendering and per-pixel transparency."""

import os
from dataclasses import replace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest

pytest.importorskip("PySide6", reason="Desktop extra required")

from PySide6.QtCore import QRectF
from PySide6.QtWidgets import QApplication

from noiz_transmission.application.assembly_services import default_project
from noiz_transmission.ui.section_view import SectionView


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def view(app):
    widget = SectionView()
    widget.resize(500, 600)
    widget.set_project(default_project())
    widget.show()
    app.processEvents()
    yield widget
    widget.close()
    app.processEvents()


def unproject(view, vertex):
    x, y, z = vertex
    distance = view._camera_distance()
    return x * (distance + z) / distance, y * (distance + z) / distance, z


def depth_extent(view):
    return max(p[2] for _, vertices in view.projected_mesh() for p in vertices) - min(
        p[2] for _, vertices in view.projected_mesh() for p in vertices)


def test_proportional_depth_default_and_explicit_magnification_preserve_input(view):
    project = view.project
    view.yaw_deg = view.pitch_deg = 0
    real_depth = depth_extent(view)
    assert real_depth == pytest.approx(view.physical_thickness_mm() / 1000)
    view.set_depth_exaggeration(True)
    assert depth_extent(view) == pytest.approx(real_depth * view.depth_scale())
    assert view.depth_scale() > 1
    view.set_depth_exaggeration(False)
    assert depth_extent(view) == pytest.approx(real_depth)
    assert view.project == project


def test_cutaway_can_be_disabled_without_changing_panel_dimensions(view):
    project = view.project
    view.yaw_deg = view.pitch_deg = 0
    view.set_cutaway(False)
    for part, vertices in view.projected_mesh():
        if part.kind == "layer":
            points = [unproject(view, point) for point in vertices]
            assert max(p[0] for p in points) - min(p[0] for p in points) == pytest.approx(project.width_m)
    assert not any("recortada" in text for text in view.geometry_notes())
    view.set_cutaway(True)
    assert any("recortada" in text for text in view.geometry_notes())
    assert view.project == project


def test_repaint_reuses_raster_and_camera_opacity_resize_inputs_invalidate(view, app):
    initial = view.grab().toImage()
    count = view.render_count
    for _ in range(3):
        view.repaint()
        assert view.grab().toImage() == initial
    assert view.render_count == count
    for change in (lambda: setattr(view, "yaw_deg", view.yaw_deg + 8),
                   lambda: view.set_opacity(.45),
                   lambda: view.resize(520, 610),
                   lambda: view.set_project(replace(view.project, width_m=3.2))):
        before = view.render_count
        change()
        app.processEvents()
        view.grab()
        assert view.render_count == before + 1


def test_static_raster_uses_physical_pixels_and_dpi_change_invalidates(view, monkeypatch):
    monkeypatch.setattr(view, "devicePixelRatioF", lambda: 1.5)
    view.grab()
    assert view._image_cache.width() == int((view.width() - 48) * 1.5)
    assert view._image_cache.height() == int((view.height() - 82) * 1.5)
    before = view.render_count
    monkeypatch.setattr(view, "devicePixelRatioF", lambda: 1.0)
    view.grab()
    assert view.render_count == before + 1
    assert view._image_cache.width() == view.width() - 48


def test_alpha_is_sorted_by_each_pixel_depth_and_independent_of_face_order():
    # Two intersecting surfaces: red is nearer at pixel 0, blue at pixel 1.
    red = (np.array([0, 1]), np.array([1., 3.]), np.array([[255., 0., 0.]] * 2), .5)
    blue = (np.array([0, 1]), np.array([3., 1.]), np.array([[0., 0., 255.]] * 2), .5)
    image = np.full((1, 2, 4), 255, dtype=np.uint8)
    reversed_image = image.copy()
    SectionView._composite_fragments(image, [red, blue])
    SectionView._composite_fragments(reversed_image, [blue, red])
    assert np.array_equal(image, reversed_image)
    assert image[0, 0, :3].tolist() == [191, 63, 127]
    assert image[0, 1, :3].tolist() == [127, 63, 191]


def test_shared_translucent_triangle_edge_does_not_double_alpha():
    surface = (np.array([0]), np.array([2.]), np.array([[255., 0., 0.]]), .5)
    image = np.full((1, 1, 4), 255, dtype=np.uint8)
    SectionView._composite_fragments(image, [surface, surface])
    assert image[0, 0, :3].tolist() == [255, 127, 127]


@pytest.mark.parametrize("kind", ["wall", "ceiling", "floor", "roof", "glazing", "porous"])
def test_each_element_has_finite_mesh_and_2d_and_3d_views(view, kind):
    project = view.project
    if kind == "porous":
        project = replace(project, panels=project.panels[:1], cavities=())
    view.set_project(replace(project, element_type=kind))
    assert all(np.isfinite(value) for _, vertices in view.projected_mesh()
               for vertex in vertices for value in vertex)
    perspective = view.grab().toImage()
    view.set_exploded(False)
    section = view.grab().toImage()
    assert perspective != section
    assert not perspective.isNull() and not section.isNull()


def test_dense_transparent_stack_bounds_raster_memory_without_changing_geometry(view):
    base = view.project
    layer = base.panels[0].layers[0]
    panel = replace(base.panels[0], layers=(replace(layer, count=10),) * 6)
    view.set_project(replace(base, panels=(panel,) * 4, cavities=base.cavities * 3))
    view.set_cutaway(False)
    view.set_opacity(.15)
    viewport = QRectF(0, 0, 452, 518)
    mesh = view.projected_mesh()
    image = view._raster_image(viewport, mesh)
    assert view._render_resolution < 1
    assert image.width() * image.height() < viewport.width() * viewport.height()
    assert len([part for part in view.visible_parts() if part.kind == "layer"]) == 240
    assert view.projected_mesh() == mesh


@pytest.mark.parametrize("material, expected_style", [("unknown", "unknown"), ("masonry", "masonry")])
def test_connections_without_section_metadata_do_not_invent_steel_channels(view, material, expected_style):
    from noiz_transmission.catalog.library import CatalogEntry

    entry = CatalogEntry("synthetic-connection", "connection", "Unknown construction", "AllFrames",
                         "Synthetic", (), {"frame_material": material, "geometry_verified": False},
                         {}, "synthetic", "0" * 64, "example")
    cavity = replace(view.project.cavities[0], frame_type="custom", stud=entry)
    view.set_project(replace(view.project, cavities=(cavity,)))
    studs = [part for part in view.visible_parts() if part.kind == "stud"]
    assert studs and all(part.style == expected_style for part in studs)
    assert len([part for part, _ in view.projected_mesh() if part.kind == "stud"]) == len(studs)
    assert any("herrajes y posición no definidos" in note for note in view.geometry_notes())
    assert any("sólo envolvente" in note for note in view.geometry_notes())
    view.grab()
    view.set_exploded(False)
    view.grab()


def test_invalid_metal_sheet_gauge_is_not_silently_scaled_from_source(view):
    from noiz_transmission.catalog.library import CatalogEntry

    entry = CatalogEntry("synthetic-connection", "connection", "Synthetic metal frame", "MetalFrame",
                         "Synthetic", (), {"frame_material": "metal", "material_thickness_m": .045},
                         {}, "synthetic", "0" * 64, "example")
    cavity = replace(view.project.cavities[0], frame_type="steel", stud=entry,
                     stud_width_mm=38, stud_depth_mm=90, depth_mm=125)
    view.set_project(replace(view.project, cavities=(cavity,)))
    studs = [part for part in view.visible_parts() if part.kind == "stud"]
    assert all(part.metal_thickness_mm is None for part in studs)
    assert all(part.thickness_mm == 90 for part in studs)
    assert view.project.cavities[0].stud.properties["material_thickness_m"] == .045
    assert any("desconocido" in note for note in view.geometry_notes())


def test_real_section_proportions_remain_correct_for_thick_assemblies(view):
    base = view.project
    panel = replace(base.panels[0], layers=(replace(base.panels[0].layers[0], thickness_mm=800),))
    view.set_project(replace(base, panels=(panel,), cavities=()))
    viewport = QRectF(20, 20, 120, 500)
    area = view.section_bounds(viewport)
    assert area.width() / area.height() == pytest.approx(.8 / base.width_m)
    assert viewport.contains(area)


@pytest.mark.parametrize("field, value, conflict", [("stud_depth_mm", 200, "profundidad"),
                                                      ("stud_width_mm", 3000, "ancho")])
def test_incompatible_stud_is_omitted_not_shortened_and_inputs_survive(view, field, value, conflict):
    base = view.project
    cavity = replace(base.cavities[0], frame_type="timber", depth_mm=100,
                     absorber_count=1, absorber_thickness_mm=50, **{field: value})
    project = replace(base, cavities=(cavity,))
    view.set_project(project)
    assert not any(part.kind == "stud" for part in view.visible_parts())
    assert not any(part.kind == "stud" for part, _ in view.projected_mesh())
    assert any("montante omitido" in note and conflict in note for note in view.geometry_notes())
    assert view.project == project
    assert getattr(view.project.cavities[0], field) == value
    assert any(part.kind == "infill" for part in view.visible_parts())
    view.grab()
    view.set_exploded(False)
    view.grab()
    corrected = replace(project, cavities=(replace(cavity, depth_mm=200),)) if field == "stud_depth_mm" else replace(project, width_m=3.2)
    view.set_project(corrected)
    assert any(part.kind == "stud" for part in view.visible_parts())
    assert not any("montante omitido" in note for note in view.geometry_notes())
