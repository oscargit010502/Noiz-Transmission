"""Original procedural 2D sections and rotatable 3D construction meshes.

Coordinates are formed from the construction, not from stored product images.
V4 uses a pinhole camera, a labelled partial view to expose the cavity, and an
orthogonal transverse section. Metal studs are open U channels: the XML supplies
web depth, flange width and sheet gauge, but no lip or bend geometry. Unknown
gauge is drawn as a zero-thickness surface with an explicit notice, never as a
solid rectangular bar. Profile/RibL,H,W,V are SI metres in inspected catalogues:
Corrugated uses L/H; Trapezoidal uses L/H/W/V (pitch/height/crest/valley).
The profile's formed envelope is distinct from the nominal sheet thickness;
rendering never changes acoustic input data.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import QSizePolicy, QWidget

from noiz_transmission.application.assemblies import AssemblyProject
from noiz_transmission.catalog.library import CatalogEntry

PALETTES = {
    "gypsum": ("#e8dfcc", "#b3a68e"),
    "wood": ("#d9b078", "#936935"),
    "masonry": ("#be8372", "#875748"),
    "concrete": ("#aeb4b6", "#717d82"),
    "glass": ("#b8e3e7", "#4f9ba6"),
    "metal": ("#b5c6d0", "#708a9b"),
    "porous": ("#c5ce94", "#85945b"),
    "cover": ("#8fabb1", "#557a83"),
}
LAYER_COLORS = tuple(colors[0] for colors in PALETTES.values())


def material_style(name: str, category: str = "") -> str:
    """Choose a visual convention; these colours make no material-data claim."""
    text = f"{name} {category}".casefold()
    for style, words in (
        ("porous", ("wool", "fibre", "fiber", "lana", "absor", "fibra", "foam")),
        ("glass", ("glass", "glaz", "vidrio", "perspex", "plexi")),
        ("wood", ("wood", "timber", "madera", "plywood", "clt", "mdf", "chipboard")),
        ("concrete", ("concrete", "hormig", "cement", "beton")),
        ("masonry", ("brick", "masonry", "ladrillo", "block", "stone")),
        ("metal", ("metal", "steel", "alumin", "acero", "zinc")),
    ):
        if any(word in text for word in words):
            return style
    return "gypsum"


@dataclass(frozen=True)
class ProfileGeometry:
    kind: str
    pitch_m: float
    height_m: float
    crest_m: float = 0
    valley_m: float = 0


def profile_geometry(entry: CatalogEntry | None) -> ProfileGeometry | None:
    """Only interpret documented SI fields; reject missing/unknown geometry."""
    if entry is None or not entry.properties.get("units_schema_verified"):
        return None
    kind = entry.properties.get("material_type")
    if kind not in ("Corrugated", "Trapezoidal"):
        return None
    values = [entry.properties.get(f"Profile/Rib{key}") for key in "LHWV"]
    needed = values[:2] if kind == "Corrugated" else values
    if any(type(value) not in (int, float) or not math.isfinite(value) or value <= 0
           for value in needed):
        return None
    pitch, height = values[:2]
    crest, valley = (0, 0) if kind == "Corrugated" else values[2:]
    if crest + valley >= pitch:
        return None
    return ProfileGeometry(kind, pitch, height, crest, valley)


@dataclass(frozen=True)
class RenderPart:
    """Physical pieces; ``depth_mm`` and ``thickness_mm`` remain nominal inputs."""

    kind: str
    name: str
    style: str
    depth_mm: float
    thickness_mm: float
    panel_index: int = -1
    layer_index: int = -1
    repeat_index: int = 0
    x_m: float | None = None
    width_m: float | None = None
    metal_thickness_mm: float | None = None
    profile: ProfileGeometry | None = None




class SectionView(QWidget):
    """2D cut or 3D mesh: drag to orbit, wheel to zoom, double click to reset."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project: AssemblyProject | None = None
        self.exploded = True  # Retains the V2 API: True selects the 3D representation.
        self.selected_panel = 0
        self.opacity = 1.0
        self.yaw_deg = 65.0
        self.pitch_deg = 16.0
        self.zoom = 1.0
        self._drag_position: QPointF | None = None
        self._textures: dict[str, QBrush] = {}
        self.setMinimumSize(160, 140)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAccessibleName("Vista del elemento: arrastrar para rotar, rueda para acercar")
        self.setToolTip("3D: arrastra para girar, rueda para zoom, doble clic para restablecer. "
                        "2D: corte transversal. 3D: caras exteriores recortadas para ver la cámara. "
                        "Los espesores pueden ampliarse; el rótulo conserva las dimensiones reales.")

    @property
    def horizontal(self) -> bool:
        return self.project is not None and self.project.element_type in (
            "floor", "roof", "ceiling",
        )

    def set_project(self, project: AssemblyProject, selected_panel: int = 0) -> None:
        previous_type = self.project.element_type if self.project is not None else None
        self.project = project
        self.selected_panel = selected_panel
        if previous_type != project.element_type:
            self.reset_view()
        self.update()

    def set_exploded(self, checked: bool) -> None:
        self.exploded = bool(checked)
        self.setCursor(Qt.CursorShape.OpenHandCursor if checked else Qt.CursorShape.ArrowCursor)
        self.update()

    def set_opacity(self, opacity: float) -> None:
        if not math.isfinite(opacity) or not 0 <= opacity <= 1:
            raise ValueError("La opacidad debe estar entre 0 y 1.")
        self.opacity = float(opacity)
        self.update()

    def reset_view(self) -> None:
        self.yaw_deg = 65.0
        self.pitch_deg = 30.0 if self.horizontal else 16.0
        self.zoom = 1.0
        self.update()

    def visible_parts(self) -> tuple[RenderPart, ...]:
        """Return active physical pieces, preserving repeated boards separately."""
        project = self.project
        if project is None:
            return ()
        if project.element_type == "porous":
            porous = project.porous
            name = porous.material.name if porous.material else "Material poroso"
            return (RenderPart("porous", name, "porous", 0, porous.thickness_mm),)
        result = []
        depth = 0.0
        facing = project.facing
        if len(project.panels) == 1 and facing.enabled and facing.count > 0:
            for number in range(facing.count):
                if facing.thickness_mm > 0:
                    result.append(RenderPart("facing", facing.material.name if facing.material
                                             else "Facing", "porous", depth,
                                             facing.thickness_mm, repeat_index=number))
                    depth += facing.thickness_mm
        if project.element_type == "floor" and project.floor_cover is not None:
            cover = project.floor_cover
            thickness = cover.properties.get("thickness_m")
            # No artificial thickness is assigned when the source does not provide one.
            if isinstance(thickness, (int, float)) and math.isfinite(thickness) and thickness > 0:
                thickness_mm = thickness * 1000
                result.append(RenderPart("cover", cover.name, "cover", depth, thickness_mm))
                depth += thickness_mm
        for panel_index, panel in enumerate(project.panels):
            for layer_index, layer in enumerate(panel.layers):
                if not layer.enabled:
                    continue
                category = layer.catalog_entry.category if layer.catalog_entry else ""
                style = material_style(layer.name, category)
                for number in range(layer.count):
                    result.append(RenderPart("layer", layer.name, style, depth,
                                             layer.thickness_mm, panel_index, layer_index, number,
                                             profile=profile_geometry(layer.profile)))
                    depth += layer.thickness_mm
            if panel_index < len(project.cavities):
                cavity = project.cavities[panel_index]
                # Store the cavity itself for dimensions and the two-dimensional cut.
                result.append(RenderPart("cavity", "Cámara", "glass", depth,
                                         cavity.depth_mm, panel_index))
                fill_thickness = cavity.absorber_thickness_mm * cavity.absorber_count
                if fill_thickness > 0:
                    fill_depth = depth + (cavity.depth_mm - fill_thickness) / 2
                    for number in range(cavity.absorber_count):
                        result.append(RenderPart("infill", cavity.absorber.name if cavity.absorber
                                                 else "Absorbente", "porous", fill_depth,
                                                 cavity.absorber_thickness_mm, panel_index,
                                                 repeat_index=number))
                        fill_depth += cavity.absorber_thickness_mm
                if cavity.frame_type != "independent":
                    stud_depth = min(cavity.stud_depth_mm, cavity.depth_mm)
                    stud_width = min(cavity.stud_width_mm / 1000, project.width_m)
                    stud_name = cavity.stud.name if cavity.stud else cavity.frame_type
                    style = material_style(stud_name, cavity.stud.category if cavity.stud else "")
                    if cavity.stud is not None:
                        frame_material = cavity.stud.properties.get("frame_material")
                        if frame_material in ("metal", "timber"):
                            style = "metal" if frame_material == "metal" else "wood"
                    gauge = (cavity.stud.properties.get("material_thickness_m")
                             if cavity.stud is not None else None)
                    gauge_mm = gauge * 1000 if type(gauge) in (int, float) and gauge > 0 else None
                    if gauge_mm and gauge_mm * 2 >= min(stud_depth, stud_width * 1000):
                        gauge_mm = None
                    if style == "gypsum":
                        style = "wood"
                    spacing = cavity.stud_spacing_mm / 1000
                    # A bounded drawing avoids allocating millions of shapes for microscopic spacing.
                    n_studs = min(200, int(project.width_m / spacing) + 1)
                    positions = [min(number * spacing, project.width_m - stud_width)
                                 for number in range(n_studs)]
                    if not positions or positions[-1] < project.width_m - stud_width:
                        positions.append(project.width_m - stud_width)
                    for x in positions:
                        result.append(RenderPart("stud", stud_name, style,
                                                 depth + (cavity.depth_mm - stud_depth) / 2,
                                                 stud_depth, panel_index, x_m=x,
                                                 width_m=stud_width, metal_thickness_mm=gauge_mm))
                depth += cavity.depth_mm
        return tuple(result)

    def physical_thickness_mm(self) -> float:
        return max((part.depth_mm + part.thickness_mm for part in self.visible_parts()), default=0)

    def mousePressEvent(self, event) -> None:
        if self.exploded and event.button() == Qt.MouseButton.LeftButton:
            self._drag_position = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self.exploded and self._drag_position is not None:
            delta = event.position() - self._drag_position
            self.yaw_deg = (self.yaw_deg - delta.x() * .55) % 360
            self.pitch_deg = max(-85, min(85, self.pitch_deg + delta.y() * .4))
            self._drag_position = event.position()
            self.update()
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._drag_position is not None:
            self._drag_position = None
            self.update()  # Restore full-resolution rendering after the interactive preview.
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        self.reset_view()
        event.accept()

    def wheelEvent(self, event) -> None:
        if self.exploded:
            self.zoom = max(.45, min(2.8, self.zoom * 1.15 ** (event.angleDelta().y() / 120)))
            self.update()
            event.accept()
        else:
            super().wheelEvent(event)

    def _texture(self, style: str) -> QBrush:
        if style in self._textures:
            return self._textures[style]
        base, detail = PALETTES[style]
        tile = QPixmap(64, 64)
        tile.fill(QColor(base))
        painter = QPainter(tile)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(detail)
        color.setAlpha(95)
        painter.setPen(QPen(color, .7))
        if style == "wood":
            for line in range(3, 64, 9):
                polygon = QPolygonF([QPointF(line + 2 * math.sin(y / 11), y)
                                     for y in range(-2, 69, 4)])
                painter.drawPolyline(polygon)
        elif style == "masonry":
            for y in (0, 21, 42, 63):
                painter.drawLine(0, y, 64, y)
            for row in range(3):
                for x in (0, 32, 64):
                    shift = 16 if row % 2 else 0
                    painter.drawLine(x + shift, row * 21, x + shift, (row + 1) * 21)
        elif style == "porous":
            for x in range(0, 72, 9):
                polygon = QPolygonF([QPointF(x + 4 * math.sin(y / 5), y)
                                     for y in range(-4, 69, 2)])
                painter.drawPolyline(polygon)
        elif style in ("glass", "metal"):
            for x in range(-64, 129, 22):
                painter.drawLine(x, 0, x + 64, 64)
        else:
            # Fixed arithmetic pattern: the same construction has the same rendering.
            for i in range(80):
                painter.drawPoint((i * 37) % 64, (i * 23 + i * i) % 64)
        painter.end()
        brush = QBrush(tile)
        self._textures[style] = brush
        return brush

    def geometry_notes(self) -> tuple[str, ...]:
        """Human-readable limits of the visual model, independent of acoustics."""
        notes = []
        if self.project is None:
            return ()
        if self.exploded and len(self.project.panels) > 1:
            notes.append("Vista parcial: cara exterior recortada")
        studs = [part for part in self.visible_parts() if part.kind == "stud" and part.style == "metal"]
        if studs:
            notes.append("Montante U esquemático; sin labios ni radios")
            if any(part.metal_thickness_mm is None for part in studs):
                notes.append("Espesor de metal desconocido: superficie sin espesor")
        for panel in self.project.panels:
            for layer in panel.layers:
                if layer.enabled and layer.profile is not None:
                    kind = layer.profile.properties.get("material_type")
                    if kind != "Isotropic" and profile_geometry(layer.profile) is None:
                        notes.append(f"Geometría de perfil no disponible: {layer.profile.name}")
        if any(part.profile and self.project.width_m / part.profile.pitch_m > 300
               for part in self.visible_parts()):
            notes.append("Paso de perfil demasiado pequeño: se muestra sólo su envolvente")
        return tuple(dict.fromkeys(notes))

    def _visual_interval(self, part: RenderPart, parts: tuple[RenderPart, ...]) -> tuple[float, float]:
        extra = sum(item.profile.height_m * 1000 for item in parts
                    if item.profile and item.depth_mm < part.depth_mm)
        start = part.depth_mm + extra
        end = start + part.thickness_mm + (part.profile.height_m * 1000 if part.profile else 0)
        return start, end

    def rendered_envelope_mm(self) -> float:
        parts = self.visible_parts()
        return max((self._visual_interval(part, parts)[1] for part in parts), default=0)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#ffffff"))
        if self.project is None:
            return
        font = self.font()
        painter.setFont(font)
        painter.setPen(QColor("#587182"))
        header = "3D · perspectiva · arrastrar para girar" if self.exploded else "2D · corte transversal"
        painter.drawText(QRectF(8, 4, self.width() - 16, 20),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, header)
        parts = self.visible_parts()
        viewport = QRectF(24, 30, max(30, self.width() - 48), max(30, self.height() - 82))
        painter.save()
        painter.setClipRect(viewport.adjusted(-5, -3, 5, 3))
        if parts:
            if self.exploded:
                self._paint_3d(painter, viewport, parts)
            else:
                self._paint_2d(painter, viewport, parts)
        painter.restore()
        nominal, envelope = self.physical_thickness_mm(), self.rendered_envelope_mm()
        label = f"{nominal:g} mm nominales"
        if not math.isclose(nominal, envelope):
            label += f" · envolvente perfilada {envelope:g} mm"
        label += " · espesores ampliados"
        painter.setPen(QColor("#315e75"))
        painter.drawText(QRectF(6, self.height() - 46, self.width() - 12, 20),
                         Qt.AlignmentFlag.AlignCenter, label)
        note = " · ".join(self.geometry_notes())
        self.setToolTip(note or "Espesores ampliados para lectura. Arrastra para girar; rueda para zoom.")
        painter.setPen(QColor("#738895"))
        painter.drawText(QRectF(6, self.height() - 24, self.width() - 12, 20),
                         Qt.AlignmentFlag.AlignCenter,
                         painter.fontMetrics().elidedText(note, Qt.TextElideMode.ElideRight,
                                                         max(1, self.width() - 12)))

    def section_bounds(self, viewport: QRectF) -> QRectF:
        """A tall narrow wall section; a floor section spans horizontally."""
        if self.project is None:
            return QRectF()
        total = self.rendered_envelope_mm() / 1000
        if self.horizontal:
            extent = min(viewport.height() * .28, max(28, viewport.width() * total / self.project.width_m * 3))
            return QRectF(viewport.left(), viewport.center().y() - extent / 2,
                          viewport.width(), extent)
        extent = min(viewport.width() * .28, max(28, viewport.height() * total / self.project.width_m * 3))
        return QRectF(viewport.center().x() - extent / 2, viewport.top(), extent, viewport.height())

    def _paint_2d(self, painter: QPainter, viewport: QRectF, parts: tuple[RenderPart, ...]) -> None:
        project = self.project
        total = max(self.rendered_envelope_mm(), .001)
        area = self.section_bounds(viewport)

        def at(span_m, depth_mm):
            if self.horizontal:
                return QPointF(area.left() + span_m / project.width_m * area.width(),
                               area.top() + depth_mm / total * area.height())
            return QPointF(area.left() + depth_mm / total * area.width(),
                           area.top() + span_m / project.width_m * area.height())

        for part in parts:
            start, end = self._visual_interval(part, parts)
            span_start = part.x_m or 0
            span_end = span_start + (part.width_m if part.width_m is not None else project.width_m)
            rect = QRectF(at(span_start, start), at(span_end, end)).normalized()
            painter.setOpacity(self.opacity if part.kind != "cavity" else 1)
            painter.setPen(QPen(QColor(PALETTES[part.style][1]), .7))
            painter.setBrush(self._texture(part.style))
            if part.kind == "cavity":
                painter.setBrush(QColor("#f7f9fa"))
                painter.setPen(QPen(QColor("#b7c4c9"), .6, Qt.PenStyle.DashLine))
                painter.drawRect(rect)
            elif part.kind == "stud" and part.style == "metal":
                # Remove the infill behind the U: no solid-metal rectangle.
                painter.fillRect(rect, QColor("#ffffff"))
                gauge = part.metal_thickness_mm or 0
                strips = ((span_start, span_start + gauge / 1000, start, end),
                          (span_start, span_end, start, start + gauge),
                          (span_start, span_end, end - gauge, end))
                painter.setBrush(QColor(PALETTES["metal"][0]))
                painter.setPen(QPen(QColor(PALETTES["metal"][1]), .8))
                for x1, x2, z1, z2 in strips:
                    painter.drawRect(QRectF(at(x1, z1), at(x2, z2)).normalized())
            elif part.profile is not None:
                segments = self._profile_segments(part, 0, project.width_m)
                if not segments:
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.setPen(QPen(QColor("#708a9b"), 1, Qt.PenStyle.DashLine))
                    painter.drawRect(rect)
                for x1, x2, h1, h2 in segments:
                    polygon = QPolygonF([at(x1, start + h1 * 1000),
                                         at(x2, start + h2 * 1000),
                                         at(x2, start + h2 * 1000 + part.thickness_mm),
                                         at(x1, start + h1 * 1000 + part.thickness_mm)])
                    painter.drawPolygon(polygon)
            else:
                if part.kind == "layer" and part.panel_index == self.selected_panel:
                    painter.setPen(QPen(QColor("#587182"), 1))
                painter.drawRect(rect)
        painter.setOpacity(1)
        painter.setPen(QColor("#45687b"))
        if self.horizontal:
            painter.drawText(QRectF(area.left(), area.top() - 22, area.width(), 20),
                             Qt.AlignmentFlag.AlignCenter, "CARA SUPERIOR")
        else:
            painter.save()
            painter.translate(area.left() - 12, area.center().y())
            painter.rotate(-90)
            painter.drawText(QRectF(-area.height() / 2, -18, area.height(), 20),
                             Qt.AlignmentFlag.AlignCenter, "CARA INCIDENTE")
            painter.restore()

    def _rotate(self, point: tuple[float, float, float]) -> tuple[float, float, float]:
        x, y, z = point
        if self.horizontal:
            x, y, z = x, z, -y
        yaw, pitch = math.radians(self.yaw_deg), math.radians(self.pitch_deg)
        xr = x * math.cos(yaw) + z * math.sin(yaw)
        zr = -x * math.sin(yaw) + z * math.cos(yaw)
        return (xr, y * math.cos(pitch) - zr * math.sin(pitch),
                y * math.sin(pitch) + zr * math.cos(pitch))

    def _camera_distance(self) -> float:
        project = self.project
        if project is None:
            return 10
        return 2 * math.sqrt(project.width_m ** 2 + project.height_m ** 2 +
                             (self.rendered_envelope_mm() / 1000 * 6) ** 2)

    def project_point(self, point: tuple[float, float, float]) -> tuple[float, float, float]:
        """Pinhole projection. Negative camera-space z is nearer the viewer."""
        x, y, z = self._rotate(point)
        distance = self._camera_distance()
        factor = distance / (distance + z)
        return x * factor, y * factor, z

    @staticmethod
    def _profile_segments(part: RenderPart, left: float, right: float):
        profile = part.profile
        pitch = profile.pitch_m
        # Bound rendering work for malformed or microscopic source pitches.
        periods = int(math.ceil(right / pitch))
        if periods > 300:
            return ()
        points = []
        for n in range(int(left / pitch), periods):
            if profile.kind == "Corrugated":
                points.extend((n * pitch + i * pitch / 12,
                               profile.height_m * (1 - math.cos(i * math.tau / 12)) / 2)
                              for i in range(13))
            else:
                slope = (pitch - profile.crest_m - profile.valley_m) / 2
                points.extend(((n * pitch, 0), (n * pitch + profile.valley_m, 0),
                               (n * pitch + profile.valley_m + slope, profile.height_m),
                               (n * pitch + profile.valley_m + slope + profile.crest_m,
                                profile.height_m), ((n + 1) * pitch, 0)))
        result = []
        for (x1, h1), (x2, h2) in zip(points, points[1:]):
            if x2 <= x1 or x2 <= left or x1 >= right:
                continue
            clipped1, clipped2 = max(left, x1), min(right, x2)
            result.append((clipped1, clipped2, h1 + (h2 - h1) * (clipped1 - x1) / (x2 - x1),
                           h1 + (h2 - h1) * (clipped2 - x1) / (x2 - x1)))
        return tuple(result)

    def projected_mesh(self) -> tuple[tuple[RenderPart, tuple[tuple[float, float, float], ...]], ...]:
        """Perspective-projected prisms. U studs have three sheet prisms, not bars."""
        if self.project is None:
            return ()
        project = self.project
        parts = self.visible_parts()
        total = max(self.rendered_envelope_mm(), .001)
        depth_enlargement = max(1, min(4, project.width_m * 150 / total))
        result = []
        camera_distance = self._camera_distance()
        nearer_panel = 0 if self._rotate((0, 0, 1))[2] >= 0 else len(project.panels) - 1

        def add(part, x1, x2, start1, start2, end1, end2):
            x1 -= project.width_m / 2
            x2 -= project.width_m / 2
            z = [(value - total / 2) / 1000 * depth_enlargement
                 for value in (start1, start2, end1, end2)]
            y1, y2 = -project.height_m / 2, project.height_m / 2
            points = ((x1, y1, z[0]), (x2, y1, z[1]), (x2, y2, z[1]), (x1, y2, z[0]),
                      (x1, y1, z[2]), (x2, y1, z[3]), (x2, y2, z[3]), (x1, y2, z[2]))
            rotated = [self._rotate(point) for point in points]
            result.append((part, tuple((x * camera_distance / (camera_distance + z),
                                        y * camera_distance / (camera_distance + z), z)
                                       for x, y, z in rotated)))

        for part in parts:
            if part.kind == "cavity":
                continue
            start, end = self._visual_interval(part, parts)
            x1 = part.x_m or 0
            x2 = x1 + (part.width_m if part.width_m is not None else project.width_m)
            if len(project.panels) > 1 and part.kind == "layer" and part.panel_index == nearer_panel:
                # A deliberate cutaway, independent of actual panel dimensions.
                x2 = min(x2, project.width_m * .58)
            if part.kind == "stud" and part.style == "metal":
                gauge = part.metal_thickness_mm or 0
                add(part, x1, x1 + gauge / 1000, start, start, end, end)
                add(part, x1 + gauge / 1000, x2, start, start, start + gauge, start + gauge)
                add(part, x1 + gauge / 1000, x2, end - gauge, end - gauge, end, end)
            elif part.profile is not None:
                segments = self._profile_segments(part, x1, x2)
                if not segments:
                    add(part, x1, x2, start, start, end, end)
                for xa, xb, ha, hb in segments:
                    za, zb = start + ha * 1000, start + hb * 1000
                    add(part, xa, xb, za, zb, za + part.thickness_mm, zb + part.thickness_mm)
            elif part.kind == "infill":
                # Fill between framing envelopes; the open U remains legible.
                studs = sorted((item for item in parts if item.kind == "stud" and
                                item.panel_index == part.panel_index), key=lambda item: item.x_m)
                cursor = x1
                for stud in studs:
                    if stud.x_m > cursor:
                        add(part, cursor, stud.x_m, start, start, end, end)
                    cursor = max(cursor, stud.x_m + stud.width_m)
                if cursor < x2:
                    add(part, cursor, x2, start, start, end, end)
            else:
                add(part, x1, x2, start, start, end, end)
        return tuple(result)

    def _paint_3d(self, painter: QPainter, viewport: QRectF, parts: tuple[RenderPart, ...]) -> None:
        mesh = self.projected_mesh()
        if not mesh:
            return
        all_points = [point for _, vertices in mesh for point in vertices]
        xmin, xmax = min(p[0] for p in all_points), max(p[0] for p in all_points)
        ymin, ymax = min(p[1] for p in all_points), max(p[1] for p in all_points)
        scale = min(viewport.width() / max(xmax - xmin, .001),
                    viewport.height() / max(ymax - ymin, .001)) * .94 * self.zoom
        cx, cy = (xmin + xmax) / 2, (ymin + ymax) / 2

        # A per-pixel depth buffer avoids the incorrect whole-face ordering of
        # large boards against narrow studs and infill. No OpenGL is required.
        # Interactive preview keeps orbiting responsive, including high-DPI screens.
        # Release always repaints the full logical-pixel resolution.
        resolution = .45 if self._drag_position is not None else 1.0
        scale *= resolution
        width = max(1, int(viewport.width() * resolution))
        height = max(1, int(viewport.height() * resolution))
        pixels = np.full((height, width, 4), 255, dtype=np.uint8)
        depths = np.full((height, width), np.inf, dtype=np.float32)
        distance = self._camera_distance()
        face_indices = ((0, 3, 2, 1), (4, 5, 6, 7), (0, 4, 7, 3),
                        (1, 2, 6, 5), (0, 1, 5, 4), (3, 7, 6, 2))
        textures = {}
        for style in {part.style for part, _ in mesh}:
            image = self._texture(style).texture().toImage().convertToFormat(QImage.Format.Format_RGBA8888)
            textures[style] = np.frombuffer(image.constBits(), np.uint8).reshape(64, 64, 4).copy()
        faces = []
        for part, vertices in mesh:
            for indices in face_indices:
                face = [vertices[i] for i in indices]
                a, b, c = face[:3]
                nz = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
                if nz >= 0:
                    continue
                screen = [(width / 2 + (x - cx) * scale, height / 2 + (y - cy) * scale, z)
                          for x, y, z in face]
                camera = [(x * (distance + z) / distance,
                           y * (distance + z) / distance, z) for x, y, z in face]
                u = [camera[1][i] - camera[0][i] for i in range(3)]
                v = [camera[2][i] - camera[0][i] for i in range(3)]
                nx, ny, nz = (u[1] * v[2] - u[2] * v[1],
                              u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
                length = math.sqrt(nx * nx + ny * ny + nz * nz)
                light_norm = math.sqrt(.35 ** 2 + .5 ** 2 + .79 ** 2)
                shade = .42 + .58 * max(0, (-.35 * nx - .5 * ny - .79 * nz) / (length * light_norm))
                faces.append((sum(vertex[2] for vertex in face), part, screen, shade))
        for _, part, face, shade in sorted(faces, key=lambda item: item[0], reverse=True):
            alpha = self.opacity * (.55 if part.style == "glass" else 1)
            for triangle in ((0, 1, 2), (0, 2, 3)):
                a, b, c = (face[i] for i in triangle)
                left = max(0, int(math.floor(min(a[0], b[0], c[0]))))
                right = min(width, int(math.ceil(max(a[0], b[0], c[0]))))
                top = max(0, int(math.floor(min(a[1], b[1], c[1]))))
                bottom = min(height, int(math.ceil(max(a[1], b[1], c[1]))))
                if left >= right or top >= bottom:
                    continue
                denominator = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
                if abs(denominator) < 1e-10:
                    continue
                yy = np.arange(top, bottom, dtype=np.float32)[:, None]
                xx = np.arange(left, right, dtype=np.float32)[None, :]
                w1 = ((b[1] - c[1]) * (xx + .5 - c[0]) +
                      (c[0] - b[0]) * (yy + .5 - c[1])) / denominator
                w2 = ((c[1] - a[1]) * (xx + .5 - c[0]) +
                      (a[0] - c[0]) * (yy + .5 - c[1])) / denominator
                w3 = 1 - w1 - w2
                inside = (w1 >= -1e-9) & (w2 >= -1e-9) & (w3 >= -1e-9)
                inverse_depth = w1 / (distance + a[2]) + w2 / (distance + b[2]) + w3 / (distance + c[2])
                # Interpolate inverse distance, not camera z, under perspective.
                candidate = np.full_like(inverse_depth, np.inf)
                np.divide(1, inverse_depth, out=candidate, where=inside & (inverse_depth > 0))
                target_depths = depths[top:bottom, left:right]
                visible = inside & (candidate < target_depths - 1e-8)
                if not np.any(visible):
                    continue
                target_depths[visible] = candidate[visible]
                visible_y, visible_x = np.nonzero(visible)
                texture = textures[part.style][(visible_y + top) % 64,
                                               (visible_x + left) % 64, :3].astype(np.float32) * shade
                target = pixels[top:bottom, left:right, :3]
                target[visible] = (texture * alpha + target[visible] * (1 - alpha)).astype(np.uint8)
        image = QImage(pixels.data, width, height, width * 4, QImage.Format.Format_RGBA8888)
        painter.drawImage(viewport, image)
