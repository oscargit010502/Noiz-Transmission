"""Original procedural 2D sections and rotatable 3D construction meshes.

Coordinates are formed from the construction, not from stored product images.
V5 uses a pinhole camera, a labelled partial view to expose the cavity, and an
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
    "unknown": ("#c1c4c5", "#7a8285"),
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
        self.cutaway = True
        self.depth_exaggeration = False
        self._parts_project = None
        self._parts_cache = ()
        self._mesh_key = None
        self._mesh_cache = ()
        self._image_key = None
        self._image_cache = None
        self._texture_arrays = {}
        self.render_count = 0
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

    def set_cutaway(self, checked: bool) -> None:
        """Reveal the cavity without altering the saved construction."""
        self.cutaway = bool(checked)
        self.update()

    def set_depth_exaggeration(self, checked: bool) -> None:
        """Opt into magnified depths; real geometric proportions are the default."""
        self.depth_exaggeration = bool(checked)
        self.update()

    def depth_scale(self) -> float:
        if not self.depth_exaggeration or self.project is None:
            return 1.0
        return max(1, min(4, self.project.width_m * 150 / max(self.rendered_envelope_mm(), .001)))

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
        """Cache the pieces of the immutable input snapshot."""
        if self._parts_project is not self.project:
            self._parts_cache = self._build_parts()
            self._parts_project = self.project
        return self._parts_cache

    def _build_parts(self) -> tuple[RenderPart, ...]:
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
                if (cavity.frame_type != "independent" and
                        cavity.stud_depth_mm <= cavity.depth_mm and
                        cavity.stud_width_mm / 1000 <= project.width_m):
                    # An incompatible stud is omitted, not silently shortened.
                    # geometry_notes explains the conflict without changing inputs.
                    stud_depth = cavity.stud_depth_mm
                    stud_width = cavity.stud_width_mm / 1000
                    stud_name = cavity.stud.name if cavity.stud else cavity.frame_type
                    style = material_style(stud_name, cavity.stud.category if cavity.stud else "")
                    if cavity.stud is not None:
                        frame_material = cavity.stud.properties.get("frame_material")
                        style = {"metal": "metal", "timber": "wood", "masonry": "masonry",
                                 "unknown": "unknown"}.get(frame_material, style)
                    gauge = (cavity.stud.properties.get("material_thickness_m")
                             if cavity.stud is not None else None)
                    gauge_mm = gauge * 1000 if type(gauge) in (int, float) and gauge > 0 else None
                    if gauge_mm and gauge_mm * 2 >= min(stud_depth, stud_width * 1000):
                        gauge_mm = None
                    if style == "gypsum":
                        style = {"timber": "wood", "steel": "metal"}.get(cavity.frame_type, "unknown")
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
        elif style == "glass":
            for x in range(-64, 129, 22):
                painter.drawLine(x, 0, x + 64, 64)
        elif style != "metal":
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
        if self.exploded and self.cutaway and len(self.project.panels) > 1:
            notes.append("Vista parcial: cara exterior recortada")
        studs = [part for part in self.visible_parts() if part.kind == "stud" and part.style == "metal"]
        if studs:
            notes.append("Montante U esquemático; sin labios ni radios")
            if any(part.metal_thickness_mm is None for part in studs):
                notes.append("Espesor de metal desconocido: superficie sin espesor")
        if any(part.kind == "stud" and part.style in ("unknown", "masonry")
               for part in self.visible_parts()):
            notes.append("Geometría de montante no identificada: sólo envolvente")
        for index, cavity in enumerate(self.project.cavities):
            if cavity.frame_type != "independent":
                if cavity.stud_depth_mm > cavity.depth_mm:
                    notes.insert(0, f"Frame {index + 1}: montante omitido; profundidad "
                                 f"{cavity.stud_depth_mm:g} mm supera cámara {cavity.depth_mm:g} mm")
                if cavity.stud_width_mm / 1000 > self.project.width_m:
                    notes.insert(0, f"Frame {index + 1}: montante omitido; ancho "
                                 f"{cavity.stud_width_mm:g} mm supera elemento "
                                 f"{self.project.width_m * 1000:g} mm")
            if cavity.stud is not None and cavity.stud.kind == "connection":
                notes.append("Conexión: dimensiones declaradas; herrajes y posición no definidos")
        if any(part.profile is not None for part in self.visible_parts()):
            notes.append("Perfil paramétrico: dimensiones XML; sin detalles de fabricación")
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
        label += (f" · profundidad ×{self.depth_scale():g}" if self.depth_exaggeration
                  else " · proporciones reales")
        painter.setPen(QColor("#315e75"))
        painter.drawText(QRectF(6, self.height() - 46, self.width() - 12, 20),
                         Qt.AlignmentFlag.AlignCenter, label)
        note = " · ".join(self.geometry_notes())
        self.setToolTip(note or "Proporciones reales. Arrastra para girar; rueda para zoom.")
        painter.setPen(QColor("#738895"))
        painter.drawText(QRectF(6, self.height() - 24, self.width() - 12, 20),
                         Qt.AlignmentFlag.AlignCenter,
                         painter.fontMetrics().elidedText(note, Qt.TextElideMode.ElideRight,
                                                         max(1, self.width() - 12)))

    def section_bounds(self, viewport: QRectF) -> QRectF:
        """A tall narrow wall section; a floor section spans horizontally."""
        if self.project is None:
            return QRectF()
        total = max(self.rendered_envelope_mm() / 1000, 1e-9) * self.depth_scale()
        span = self.project.width_m
        physical_width, physical_height = ((span, total) if self.horizontal else (total, span))
        if viewport.width() / physical_width <= viewport.height() / physical_height:
            width, height = viewport.width(), viewport.width() * physical_height / physical_width
        else:
            width, height = viewport.height() * physical_width / physical_height, viewport.height()
        return QRectF(viewport.center().x() - width / 2, viewport.center().y() - height / 2,
                      width, height)

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
            elif part.kind == "stud" and part.style in ("unknown", "masonry"):
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(QColor(PALETTES[part.style][1]), .8, Qt.PenStyle.DashLine))
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
        """Reuse projected geometry while only unrelated widgets repaint."""
        key = (id(self.project), self.yaw_deg, self.pitch_deg, self.cutaway, self.depth_exaggeration)
        if key != self._mesh_key:
            self._mesh_cache = self._build_mesh()
            self._mesh_key = key
        return self._mesh_cache

    def _build_mesh(self) -> tuple[tuple[RenderPart, tuple[tuple[float, float, float], ...]], ...]:
        """Perspective-projected prisms. U studs have three sheet prisms, not bars."""
        if self.project is None:
            return ()
        project = self.project
        parts = self.visible_parts()
        total = max(self.rendered_envelope_mm(), .001)
        depth_enlargement = self.depth_scale()
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
            if (self.cutaway and len(project.panels) > 1 and part.kind == "layer"
                    and part.panel_index == nearer_panel):
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
        # Qt requests repaints for exposure, focus and unrelated controls. Keep
        # the final image until camera, physical input, opacity, size or DPI changes.
        key = (self._mesh_key, viewport.width(), viewport.height(), self.devicePixelRatioF(),
               self.zoom, self.opacity, self._drag_position is not None)
        if key != self._image_key:
            self._image_cache = self._raster_image(viewport, mesh)
            self._image_key = key
            self.render_count += 1
        painter.drawImage(viewport, self._image_cache)

    def _raster_image(self, viewport: QRectF, mesh) -> QImage:
        all_points = [point for _, vertices in mesh for point in vertices]
        xmin, xmax = min(p[0] for p in all_points), max(p[0] for p in all_points)
        ymin, ymax = min(p[1] for p in all_points), max(p[1] for p in all_points)
        scale = min(viewport.width() / max(xmax - xmin, .001),
                    viewport.height() / max(ymax - ymin, .001)) * .94 * self.zoom
        cx, cy = (xmin + xmax) / 2, (ymin + ymax) / 2
        distance = self._camera_distance()
        face_indices = ((0, 3, 2, 1), (4, 5, 6, 7), (0, 4, 7, 3),
                        (1, 2, 6, 5), (0, 1, 5, 4), (3, 7, 6, 2))
        faces = []
        transparent_area = 0.0
        for part, vertices in mesh:
            for indices in face_indices:
                face = [vertices[i] for i in indices]
                a, b, c = face[:3]
                nz = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
                if nz >= 0:
                    continue
                camera = [(x * (distance + z) / distance,
                           y * (distance + z) / distance, z) for x, y, z in face]
                u = [camera[1][i] - camera[0][i] for i in range(3)]
                v = [camera[2][i] - camera[0][i] for i in range(3)]
                nx, ny, nz = (u[1] * v[2] - u[2] * v[1],
                              u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
                length = math.sqrt(nx * nx + ny * ny + nz * nz)
                if length < 1e-14:
                    continue
                light_norm = math.sqrt(.35 ** 2 + .5 ** 2 + .79 ** 2)
                shade = .42 + .58 * max(0, (-.35 * nx - .5 * ny - .79 * nz) / (length * light_norm))
                visual_alpha = (.22 if part.kind == "stud" and part.style in ("unknown", "masonry")
                                else .55 if part.style == "glass" else 1)
                alpha = self.opacity * visual_alpha
                if alpha <= 0:
                    continue
                if alpha < 1:
                    # Area estimate bounds the transparent fragment allocation.
                    # Geometric vertices remain unchanged if resolution is reduced.
                    transparent_area += abs(sum(face[i][0] * face[(i + 1) % 4][1] -
                                                face[(i + 1) % 4][0] * face[i][1]
                                                for i in range(4))) / 2 * scale ** 2
                faces.append((part, face, shade, alpha))
        resolution = (.45 if self._drag_position is not None else self.devicePixelRatioF())
        resolution = min(resolution, math.sqrt(2_000_000 / max(1, viewport.width() * viewport.height())),
                         math.sqrt(2_000_000 / max(1, transparent_area)))
        self._render_resolution = resolution
        scale *= resolution
        width = max(1, int(viewport.width() * resolution))
        height = max(1, int(viewport.height() * resolution))
        pixels = np.full((height, width, 4), 255, dtype=np.uint8)
        depths = np.full((height, width), np.inf, dtype=np.float32)
        for style in {part.style for part, _ in mesh}:
            if style not in self._texture_arrays:
                texture = self._texture(style).texture().toImage().convertToFormat(QImage.Format.Format_RGBA8888)
                self._texture_arrays[style] = np.frombuffer(texture.constBits(), np.uint8).reshape(64, 64, 4).copy()
        # Finish all opaque surfaces first. Transparent fragments behind any
        # opaque surface are rejected even when their mean face depth is nearer.
        fragments = []
        for part, face, shade, alpha in sorted(faces, key=lambda item: item[3] < 1):
            screen = [(width / 2 + (x - cx) * scale, height / 2 + (y - cy) * scale, z)
                      for x, y, z in face]
            for triangle in ((0, 1, 2), (0, 2, 3)):
                a, b, c = (screen[i] for i in triangle)
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
                candidate = np.full_like(inverse_depth, np.inf)
                np.divide(1, inverse_depth, out=candidate, where=inside & (inverse_depth > 0))
                target_depths = depths[top:bottom, left:right]
                visible = inside & (candidate < target_depths - 1e-8)
                if not np.any(visible):
                    continue
                vy, vx = np.nonzero(visible)
                gy, gx = vy + top, vx + left
                texture = self._texture_arrays[part.style][(gy / resolution).astype(int) % 64,
                                                           (gx / resolution).astype(int) % 64, :3]
                colors = texture.astype(np.float32) * shade
                if alpha == 1:
                    target_depths[visible] = candidate[visible]
                    pixels[gy, gx, :3] = colors.astype(np.uint8)
                else:
                    fragments.append((gy * width + gx, candidate[visible], colors, alpha))
        if fragments:
            self._composite_fragments(pixels, fragments)
        # Own the memory after the NumPy local leaves scope, including cached images.
        return QImage(pixels.data, width, height, width * 4, QImage.Format.Format_RGBA8888).copy()

    @staticmethod
    def _composite_fragments(pixels: np.ndarray, fragments: list) -> None:
        """Exact front-to-back alpha per pixel, independent of mesh/face order.

        This is visual alpha compositing, not a model of optical glass. Backface
        culling draws the visible boundary of each prism. Coincident triangle
        edges are deduplicated so diagonal seams are not double-darkened.
        """
        indexes = np.concatenate([item[0] for item in fragments])
        distances = np.concatenate([item[1] for item in fragments])
        colors = np.concatenate([item[2] for item in fragments])
        alphas = np.concatenate([np.full(len(item[0]), item[3], dtype=np.float64) for item in fragments])
        order = np.lexsort((distances, indexes))
        indexes, distances, colors, alphas = indexes[order], distances[order], colors[order], alphas[order]
        distinct = np.ones(len(indexes), dtype=bool)
        distinct[1:] = ((indexes[1:] != indexes[:-1]) |
                        (np.abs(distances[1:] - distances[:-1]) > 1e-6))
        indexes, colors, alphas = indexes[distinct], colors[distinct], alphas[distinct]
        starts = np.r_[0, np.flatnonzero(indexes[1:] != indexes[:-1]) + 1]
        counts = np.diff(np.r_[starts, len(indexes)])
        log_transmission = np.log1p(-alphas)
        exclusive = np.cumsum(log_transmission) - log_transmission
        before = np.exp(exclusive - np.repeat(exclusive[starts], counts))
        weights = alphas * before
        combined = np.add.reduceat(colors * weights[:, None], starts, axis=0)
        remaining = np.exp(np.add.reduceat(log_transmission, starts))
        target = pixels.reshape(-1, 4)
        selected = indexes[starts]
        target[selected, :3] = np.clip(combined + target[selected, :3] * remaining[:, None], 0, 255).astype(np.uint8)
