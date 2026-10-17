"""Square physical plot area with a separate, accessible right-hand legend.

The frequency axis is logarithmic and TL is linear; locking their numeric
aspect ratio would be meaningless. This widget instead sizes the two physical
axes equally, independently of the data limits and of the containing splitter.
"""

from __future__ import annotations

import math

import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from noiz_transmission.application.assemblies import AssemblyPrediction
from noiz_transmission.core.ratings import (
    ISO717_FREQUENCIES_HZ,
    STC_FREQUENCIES_HZ,
    iso717_rw,
    legacy_stc,
)


def fitted_reference(prediction: AssemblyPrediction, rating: str):
    """Return the actual fitted contour on its own required frequency bands.

    A partial spectrum or a non-diffuse/non-airborne prediction cannot produce
    a reference. No interpolation or extrapolation beyond normative bands is
    used, and the STC convention is the same provisional 32/8 procedure as the
    main rating selector.
    """
    if prediction.project.incidence != "diffuse" or prediction.project.excitation != "airborne":
        return None
    try:
        if rating == "rw":
            selected = [(frequency, value) for frequency, value in
                        zip(prediction.frequencies_hz, prediction.tl_db, strict=True)
                        if frequency in ISO717_FREQUENCIES_HZ]
            result = iso717_rw([item[0] for item in selected], [item[1] for item in selected])
            return (ISO717_FREQUENCIES_HZ, result.reference_curve_db,
                    f"Rw {result.rw_db} dB · referencia", "ISO 717-1 · 100–3150 Hz")
        if rating == "stc":
            result = legacy_stc(prediction.frequencies_hz, prediction.tl_db)
            return (STC_FREQUENCIES_HZ, result.reference_curve_db,
                    f"STC {result.stc} · referencia", "STC orientativo · método legado 32/8 · 125–4000 Hz")
    except ValueError:
        return None
    return None


class _LineSample(QWidget):
    def __init__(self, trace: pg.PlotDataItem):
        super().__init__()
        self.trace = trace
        self.setFixedSize(26, 16)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(self.trace.opts["pen"]))
        painter.drawLine(1, 8, 25, 8)
        if self.trace.opts["symbol"]:
            painter.setBrush(pg.mkBrush(self.trace.opts["symbolBrush"]))
            painter.drawEllipse(10, 5, 6, 6)


class SpectrumLegend(QScrollArea):
    """Wrapped, scrollable legend; each checkbox controls one displayed trace."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setAccessibleName("Leyenda del gráfico; mostrar u ocultar curvas")
        self.content = QWidget()
        self.rows = QVBoxLayout(self.content)
        self.rows.setContentsMargins(2, 3, 2, 0)
        self.rows.setSpacing(5)
        self.rows.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        self.rows.addStretch()
        self.setWidget(self.content)
        self.items: list[tuple[pg.PlotDataItem, QLabel]] = []
        self.checkboxes: dict[str, QCheckBox] = {}
        self._visibility: dict[str, bool] = {}

    def clear(self):
        self.items.clear()
        self.checkboxes.clear()
        while self.rows.count() > 1:
            row = self.rows.takeAt(0).widget()
            row.hide()
            row.deleteLater()

    def retain_keys(self, keys: set[str]):
        """Forget removed alternatives without losing current/reference preferences."""
        self._visibility = {key: visible for key, visible in self._visibility.items() if key in keys}

    def addItem(self, trace: pg.PlotDataItem, text: str, tooltip: str = "", *, key: str):
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        checkbox = QCheckBox()
        visible = self._visibility.setdefault(key, True)
        checkbox.setChecked(visible)
        trace.setVisible(visible)
        checkbox.setAccessibleName(text)

        def set_visible(checked: bool):
            self._visibility[key] = checked
            trace.setVisible(checked)

        checkbox.toggled.connect(set_visible)
        self.checkboxes[key] = checkbox
        layout.addWidget(checkbox, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(_LineSample(trace), 0, Qt.AlignmentFlag.AlignTop)
        title = QLabel(text)
        title.setTextFormat(Qt.TextFormat.PlainText)
        title.setWordWrap(True)
        title.setMinimumWidth(0)
        title.setToolTip(tooltip or text)
        layout.addWidget(title, 1)
        self.rows.insertWidget(self.rows.count() - 1, row)
        self.items.append((trace, title))
        self._fit_rows()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_rows()

    def _fit_rows(self):
        # Reserve space for the native checkbox, line sample and a scrollbar.
        # QLabel's generic minimum height does not include wrapped lines, so
        # allow every line explicitly before QScrollArea calculates its range.
        text_width = max(30, self.width() - 76)
        for _, title in self.items:
            title.setMinimumHeight(max(title.fontMetrics().height(), title.heightForWidth(text_width)))
        self.rows.activate()


class SquareSpectrumChart(QWidget):
    """Lay out a square ViewBox and a legend outside the axes, on their right."""

    LEFT = 52
    BOTTOM = 38
    EDGE = 2
    GAP = 10

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(290, 100)
        self.plot_widget = pg.PlotWidget(self, background="#ffffff")
        self.plot = self.plot_widget.getPlotItem()
        self.plot.layout.setContentsMargins(0, 0, 0, 0)
        self.plot.layout.setSpacing(0)
        self.plot.hideButtons()
        self.plot.setLogMode(x=True, y=False)
        self.plot.setLabel("bottom", "Frecuencia [Hz]", color="#385769")
        self.plot.setLabel("left", "TL [dB]", color="#385769")
        self.plot.setMenuEnabled(False)
        self.plot.showGrid(x=True, y=True, alpha=.28)
        self.plot.getViewBox().setBorder(pg.mkPen("#7c929d"))
        self.plot.setRange(xRange=(math.log10(50), math.log10(5000)), yRange=(0, 80), padding=.02)
        ticks = (63, 125, 250, 500, 1000, 2000, 4000)
        self.plot.getAxis("bottom").setTicks([
            [(math.log10(frequency), f"{frequency // 1000}k" if frequency >= 1000 else str(frequency))
             for frequency in ticks],
        ])
        for key in ("bottom", "left"):
            axis = self.plot.getAxis(key)
            axis.setPen("#7c929d")
            axis.setTextPen("#385769")
            axis.setStyle(tickFont=self.font(), autoExpandTextSpace=False, autoReduceTextSpace=False)
        self.plot.getAxis("left").setWidth(self.LEFT)
        self.plot.getAxis("bottom").setHeight(self.BOTTOM)
        self.plot.showAxis("top")
        self.plot.showAxis("right")
        self.plot.getAxis("top").setStyle(showValues=False)
        self.plot.getAxis("right").setStyle(showValues=False)
        self.plot.getAxis("top").setHeight(self.EDGE)
        self.plot.getAxis("right").setWidth(self.EDGE)
        self.legend = SpectrumLegend(self)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.arrange()

    def showEvent(self, event):
        super().showEvent(event)
        self.arrange()

    def arrange(self):
        # Fixed axis margins make the ViewBox itself square (the complete
        # PlotWidget is deliberately a little wider to accommodate y labels).
        legend_width = min(220, max(135, self.width() // 3))
        side = max(20, min(self.height() - self.BOTTOM - self.EDGE,
                           self.width() - self.LEFT - self.EDGE - self.GAP - legend_width))
        # Adjacent 250/500 Hz labels need a small gap even at the minimum
        # window width; retain every octave label with a compact native font.
        tick_font = QFont(self.font())
        tick_font.setPointSizeF(8 if side < 185 else 9)
        self.plot.getAxis("bottom").setStyle(tickFont=tick_font)
        plot_width, plot_height = side + self.LEFT + self.EDGE, side + self.BOTTOM + self.EDGE
        left = max(0, (self.width() - plot_width - self.GAP - legend_width) // 2)
        top = max(0, (self.height() - plot_height) // 2)
        self.plot_widget.setGeometry(left, top, plot_width, plot_height)
        self.legend.setGeometry(left + plot_width + self.GAP, top, legend_width, plot_height)
