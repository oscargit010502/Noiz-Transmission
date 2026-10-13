"""Original procedural 2D sections and rotatable 3D construction meshes.

Coordinates are formed from the construction, not from stored product images.
Thin dimensions are enlarged consistently for legibility; the dimension annotation
always reports the physical thickness. This renderer does not calculate acoustics.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import QSizePolicy, QWidget

from noiz_transmission.application.assemblies import AssemblyProject

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
class RenderPart:
    """One physical solid or porous piece, with thickness-coordinate placement."""

    kind: str
    name: str
    style: str
    depth_mm: float
    thickness_mm: float
    panel_index: int = -1
    layer_index: int = -1
    repeat_index: int = 0
    # Optional stud placement across the panel width, in metres.
    x_m: float | None = None
    width_m: float | None = None


class SectionView(QWidget):
    """2D cut or 3D mesh: drag to orbit, wheel to zoom, double click to reset."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project: AssemblyProject | None = None
        self.exploded = True  # Retains the V2 API: True selects the 3D representation.
        self.selected_panel = 0
        self.opacity = .92
        self.yaw_deg = -32.0
        self.pitch_deg = 16.0
        self.zoom = 1.0
        self._drag_position: QPointF | None = None
        self._textures: dict[str, QBrush] = {}
        self.setMinimumSize(160, 140)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAccessibleName("Vista del elemento: arrastrar para rotar, rueda para acercar")
        self.setToolTip("3D: arrastra para girar, rueda para zoom, doble clic para restablecer. "
                        "2D: corte detallado. Espesores ampliados para su lectura.")

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
        self.yaw_deg = -32.0
        self.pitch_deg = 35.0 if self.horizontal else 16.0
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
                                             layer.thickness_mm, panel_index, layer_index, number))
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
                                                 width_m=stud_width))
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
            self.yaw_deg = (self.yaw_deg + delta.x() * .55) % 360
            self.pitch_deg = max(-85, min(85, self.pitch_deg + delta.y() * .4))
            self._drag_position = event.position()
            self.update()
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._drag_position is not None:
            self._drag_position = None
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

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#f8fafc"))
        if self.project is None:
            return
        painter.setFont(QFont("Segoe UI", 9))
        painter.setPen(QColor("#587182"))
        header = "3D · arrastra para rotar · rueda para zoom" if self.exploded else "2D · corte detallado"
        painter.drawText(QRectF(12, 7, self.width() - 24, 22),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, header)
        parts = self.visible_parts()
        viewport = QRectF(22, 38, max(30, self.width() - 44), max(30, self.height() - 96))
        painter.save()
        painter.setClipRect(viewport.adjusted(-10, -5, 10, 5))
        if parts:
            if self.exploded:
                self._paint_3d(painter, viewport, parts)
            else:
                self._paint_2d(painter, viewport, parts)
        painter.restore()
        thickness = self.physical_thickness_mm()
        label = f"{thickness:g} mm · "
        label += ("material poroso" if self.project.element_type == "porous" else
                  f"{len(self.project.panels)} {'panel' if len(self.project.panels) == 1 else 'paneles'}")
        painter.setPen(QColor("#315e75"))
        painter.drawText(QRectF(10, self.height() - 49, self.width() - 20, 22),
                         Qt.AlignmentFlag.AlignCenter, label)
        painter.setFont(QFont("Segoe UI", 8))
        painter.setPen(QColor("#738895"))
        painter.drawText(QRectF(10, self.height() - 27, self.width() - 20, 18),
                         Qt.AlignmentFlag.AlignCenter, "Espesores ampliados · geometría esquemática")

    def _paint_2d(self, painter: QPainter, viewport: QRectF, parts: tuple[RenderPart, ...]) -> None:
        project = self.project
        total = max(self.physical_thickness_mm(), .001)
        # The screen axes form a transverse cut: depth against physical panel width.
        if self.horizontal:
            area = QRectF(viewport.left(), viewport.center().y() - viewport.height() * .22,
                          viewport.width(), viewport.height() * .44)
        else:
            area = QRectF(viewport.center().x() - viewport.width() * .3, viewport.top(),
                          viewport.width() * .6, viewport.height())
        for part in parts:
            start, end = part.depth_mm / total, (part.depth_mm + part.thickness_mm) / total
            span_start = 0 if part.x_m is None else part.x_m / project.width_m
            span_length = 1 if part.width_m is None else part.width_m / project.width_m
            if self.horizontal:
                rect = QRectF(area.left() + span_start * area.width(),
                              area.top() + start * area.height(),
                              span_length * area.width(), (end - start) * area.height())
            else:
                rect = QRectF(area.left() + start * area.width(),
                              area.top() + span_start * area.height(),
                              (end - start) * area.width(), span_length * area.height())
            if part.kind == "cavity":
                painter.setOpacity(1)
                painter.setBrush(QColor("#eef4f8"))
                painter.setPen(QPen(QColor("#afc4d0"), .8, Qt.PenStyle.DashLine))
            else:
                painter.setOpacity(self.opacity)
                painter.setBrush(self._texture(part.style))
                selected = part.kind == "layer" and part.panel_index == self.selected_panel
                painter.setPen(QPen(QColor("#0a7698") if selected else QColor(PALETTES[part.style][1]),
                                    1.5 if selected else .7))
            painter.drawRect(rect)
        painter.setOpacity(1)
        painter.setPen(QColor("#45687b"))
        if self.horizontal:
            painter.drawText(QRectF(area.left(), area.top() - 24, area.width(), 20),
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

    def projected_mesh(self) -> tuple[tuple[RenderPart, tuple[tuple[float, float, float], ...]], ...]:
        """Expose rotated box vertices for deterministic geometric verification."""
        if self.project is None:
            return ()
        project = self.project
        total = max(self.physical_thickness_mm(), .001)
        depth_enlargement = max(1, min(6, project.width_m * 220 / total))
        result = []
        for part in self.visible_parts():
            if part.kind == "cavity":
                continue
            x1 = -.5 * project.width_m + (part.x_m or 0)
            x2 = x1 + (part.width_m if part.width_m is not None else project.width_m)
            z1 = (part.depth_mm - total / 2) / 1000 * depth_enlargement
            z2 = z1 + part.thickness_mm / 1000 * depth_enlargement
            y1, y2 = -.5 * project.height_m, .5 * project.height_m
            points = ((x1, y1, z1), (x2, y1, z1), (x2, y2, z1), (x1, y2, z1),
                      (x1, y1, z2), (x2, y1, z2), (x2, y2, z2), (x1, y2, z2))
            result.append((part, tuple(self._rotate(point) for point in points)))
        return tuple(result)

    def _paint_3d(self, painter: QPainter, viewport: QRectF, parts: tuple[RenderPart, ...]) -> None:
        mesh = self.projected_mesh()
        if not mesh:
            return
        all_points = [p for _, vertices in mesh for p in vertices]
        xmin, xmax = min(p[0] for p in all_points), max(p[0] for p in all_points)
        ymin, ymax = min(p[1] for p in all_points), max(p[1] for p in all_points)
        scale = min(viewport.width() / max(xmax - xmin, .001),
                    viewport.height() / max(ymax - ymin, .001)) * .9 * self.zoom
        cx, cy = (xmin + xmax) / 2, (ymin + ymax) / 2

        def screen(point):
            return QPointF(viewport.center().x() + (point[0] - cx) * scale,
                           viewport.center().y() + (point[1] - cy) * scale)

        # Vertex winding is outward; only camera-facing faces are painted.
        face_indices = ((0, 3, 2, 1), (4, 5, 6, 7), (0, 4, 7, 3),
                        (1, 2, 6, 5), (0, 1, 5, 4), (3, 7, 6, 2))
        faces = []
        # The construction is a stack of non-intersecting depth slabs. Sorting
        # first by slab depth prevents a short stud from being painted in front
        # of a nearer whole-board face merely because its centroid is nearer.
        slab_direction = self._rotate((0, 0, 1))[2]
        for part, vertices in mesh:
            for indices in face_indices:
                face = [vertices[i] for i in indices]
                a, b, c = face[:3]
                nz = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
                if nz >= 0:
                    continue
                depth = sum(p[2] for p in face) / 4
                slab_depth = (part.depth_mm + part.thickness_mm / 2) * slab_direction
                faces.append((slab_depth, depth, part, QPolygonF([screen(p) for p in face]), indices))
        for _, _, part, polygon, indices in sorted(faces, key=lambda face: face[:2], reverse=True):
            alpha = self.opacity * (.55 if part.style == "glass" else 1)
            painter.setOpacity(alpha)
            painter.setBrush(self._texture(part.style))
            selected = part.kind == "layer" and part.panel_index == self.selected_panel
            painter.setPen(QPen(QColor("#137e9d") if selected else QColor(PALETTES[part.style][1]),
                                1.3 if selected else .7))
            painter.drawPolygon(polygon)
            if indices != face_indices[0]:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(18, 41, 55, 28 if indices in face_indices[2:4] else 12))
                painter.drawPolygon(polygon)
        painter.setOpacity(1)
