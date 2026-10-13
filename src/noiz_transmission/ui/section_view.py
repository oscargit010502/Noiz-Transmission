"""Original vector section drawings. No model-specific or proprietary assets."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QSizePolicy, QWidget

from noiz_transmission.application.assemblies import AssemblyProject

LAYER_COLORS = ("#b8cbd7", "#d8bd92", "#9bbec6", "#c6c1d5", "#aeb6b9", "#cba993")


class SectionView(QWidget):
    """Scale-aware thickness section with optional exploded axonometric view."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project: AssemblyProject | None = None
        self.exploded = True
        self.selected_panel = 0
        self.setMinimumSize(160, 140)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAccessibleName("Sección constructiva del elemento")
        self.setToolTip("Sección esquemática. Espesores finos ampliados para su lectura; no es un plano a escala.")

    def set_project(self, project: AssemblyProject, selected_panel: int = 0) -> None:
        self.project = project
        self.selected_panel = selected_panel
        self.update()

    def set_exploded(self, checked: bool) -> None:
        self.exploded = checked
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#f8fbfc"))
        if self.project is None:
            return
        project = self.project
        width, height = self.width(), self.height()
        painter.setFont(QFont("Segoe UI", 9))
        painter.setPen(QColor("#6b8392"))
        painter.drawText(QRectF(12, 8, width - 24, 20), Qt.AlignmentFlag.AlignLeft,
                         "EXTERIOR  →  INTERIOR" if project.element_type not in ("floor", "roof", "ceiling")
                         else "CARA SUPERIOR  →  INFERIOR")
        segments = []
        for panel_index, panel in enumerate(project.panels):
            for layer_index, layer in enumerate(panel.layers):
                segments.append((max(7, layer.thickness_mm * layer.count), "layer", panel_index, layer_index))
            if panel_index < len(project.cavities):
                cavity = project.cavities[panel_index]
                segments.append((max(15, cavity.depth_mm), "cavity", panel_index, 0))
        total = sum(segment[0] for segment in segments)
        depth_x = min(47, width * .15) if self.exploded else 0
        depth_y = min(28, height * .1) if self.exploded else 0
        drawing_width = max(40, width - 60 - depth_x)
        segment_scale = drawing_width / total
        y = max(48, height * .17)
        drawing_height = max(55, height - y - 71 - depth_y)
        x = 28.0
        for raw, kind, panel_index, layer_index in segments:
            w = raw * segment_scale
            rect = QRectF(x, y + depth_y, w, drawing_height)
            if kind == "cavity":
                cavity = project.cavities[panel_index]
                painter.fillRect(rect, QColor("#edf5f8"))
                painter.setPen(QPen(QColor("#c4dce6"), 1, Qt.PenStyle.DashLine))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(rect)
                if cavity.absorber_thickness_mm > 0:
                    fill_w = w * cavity.absorber_thickness_mm / cavity.depth_mm
                    filled = QRectF(x + (w - fill_w) / 2, y + depth_y + 1, fill_w, drawing_height - 2)
                    painter.fillRect(filled, QColor("#d6d9ad"))
                    painter.save()
                    painter.setClipRect(filled)
                    painter.setPen(QPen(QColor("#9da976"), .8))
                    for line in range(-int(drawing_height), int(fill_w) + 20, 8):
                        painter.drawLine(QPointF(x + line, y + depth_y),
                                         QPointF(x + line + drawing_height, y + depth_y + drawing_height))
                    painter.restore()
                if cavity.frame_type != "independent":
                    painter.fillRect(QRectF(x, y + depth_y + drawing_height * .4,
                                            w, max(8, drawing_height * .07)), QColor("#b39874"))
                painter.setPen(QColor("#617c8d"))
                if w > 25:
                    painter.drawText(QRectF(x, y + depth_y + drawing_height + 8, w, 16),
                                     Qt.AlignmentFlag.AlignCenter, f"{cavity.depth_mm:g}")
            else:
                color = QColor(LAYER_COLORS[layer_index % len(LAYER_COLORS)])
                if self.exploded:
                    painter.setPen(QPen(color.darker(125), 1))
                    painter.setBrush(color.lighter(118))
                    painter.drawPolygon(QPolygonF([QPointF(x, y + depth_y), QPointF(x + depth_x, y),
                                                   QPointF(x + w + depth_x, y), QPointF(x + w, y + depth_y)]))
                    painter.setBrush(color.darker(110))
                    painter.drawPolygon(QPolygonF([QPointF(x + w, y + depth_y), QPointF(x + w + depth_x, y),
                                                   QPointF(x + w + depth_x, y + drawing_height),
                                                   QPointF(x + w, y + depth_y + drawing_height)]))
                painter.setPen(QPen(QColor("#1d7893") if panel_index == self.selected_panel else color.darker(130),
                                    1.8 if panel_index == self.selected_panel else 1))
                painter.setBrush(color)
                painter.drawRect(rect)
                if w >= 16:
                    painter.save()
                    painter.translate(x + w / 2, y + depth_y + drawing_height / 2)
                    painter.rotate(-90)
                    painter.setPen(QColor("#314f62"))
                    painter.drawText(QRectF(-drawing_height / 2, -8, drawing_height, 16),
                                     Qt.AlignmentFlag.AlignCenter, f"P{panel_index + 1} · C{layer_index + 1}")
                    painter.restore()
            x += w
        actual = sum(layer.thickness_mm * layer.count for panel in project.panels for layer in panel.layers)
        actual += sum(cavity.depth_mm for cavity in project.cavities)
        painter.setPen(QPen(QColor("#8ca7b7"), 1))
        dim_y = y + depth_y + drawing_height + 33
        painter.drawLine(QPointF(28, dim_y), QPointF(x, dim_y))
        for tick in (28, x):
            painter.drawLine(QPointF(tick, dim_y - 4), QPointF(tick, dim_y + 4))
        painter.setPen(QColor("#2f596f"))
        painter.drawText(QRectF(15, dim_y + 5, width - 30, 20), Qt.AlignmentFlag.AlignCenter,
                         f"{actual:g} mm · {len(project.panels)} {'panel' if len(project.panels) == 1 else 'paneles'}")
