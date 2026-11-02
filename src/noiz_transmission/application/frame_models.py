"""Versioned automatic frame assumptions, distinct from catalogue geometry.

The catalogue's connection codes identify arrangements, not acoustic fits.
The reviewed mapping below uses only the generic contact topology observed in
the supplied V10 records; it does not copy proprietary connection algorithms.
Unknown products retain a rigid line connection instead of silently losing
their structural transmission path. This is a generic estimate, not a proven
lower bound for every installed connector.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from noiz_transmission.application.assemblies import Cavity


FRAME_RESOLVER_VERSION = "sharp-contact-topology-1"
_INDEPENDENT_CODES = {0, 7, 8, 31, 32, 35, 36, 64}
_ORDINARY_LINE_CODES = {1, 4, 13, 20, 42, 47, 66, 67, 68, 69, 70, 71, 72, 73}
_POINT_CODES = {5, 87}


@dataclass(frozen=True)
class AutomaticFrame:
    """Resolved contact topology and its auditable engineering assumptions."""

    profile: str
    label: str
    stud_spacing_m: float
    point_spacing_m: float
    warnings: tuple[str, ...]
    source: str = FRAME_RESOLVER_VERSION
    catalogue_connection_code: int | None = None


@dataclass(frozen=True)
class AutomaticAbsorption:
    """Actual installed thickness plus the source of any acoustic assumption."""

    thickness_m: float
    flow_resistivity_pa_s_m2: float | None
    label: str
    warnings: tuple[str, ...]
    source: str


def resolve_absorption(cavity: Cavity) -> AutomaticAbsorption:
    """Use declared resistivity or a labelled reference fibre, never XML Damping.

    Hansen 6e Table 7.12, p.442 gives the reference value 20,000 Pa·s/m².
    This is an internal design assumption, not a lookup of manufacturer
    properties and not a density-to-resistivity conversion. Miki is evaluated
    at the actual selected total thickness, including thin and partial fills.
    """
    thickness = cavity.absorber_thickness_mm * cavity.absorber_count / 1000
    if not thickness:
        return AutomaticAbsorption(0.0, None, "Cámara sin relleno activo", (), "empty-cavity")
    sigma = cavity.flow_resistivity_pa_s_m2
    if sigma is not None:
        return AutomaticAbsorption(thickness, sigma, "Resistividad declarada",
                                   ("Relleno automático: se conserva la resistividad al flujo "
                                    "declarada explícitamente en el proyecto.",), "project-explicit")
    if cavity.absorber is not None:
        sigma = cavity.absorber.properties.get("flow_resistivity_pa_s_m2")
        if type(sigma) in (int, float) and math.isfinite(sigma) and sigma > 0:
            return AutomaticAbsorption(
                thickness, float(sigma), "Resistividad declarada en catálogo",
                ("Relleno automático: resistividad explícita en unidades SI del registro "
                 "seleccionado; su procedencia se conserva, sin acreditar ensayo por importación.",),
                f"catalog:{cavity.absorber.id}",
            )
    extra = ()
    if cavity.absorber is not None:
        category = "".join(char for char in cavity.absorber.category.casefold() if char.isalnum())
        if category not in {"fiberglass", "fibreglass", "glasswool", "mineralwool", "rockwool"}:
            extra = ("El relleno seleccionado no está identificado como fibra de vidrio/lana mineral. "
                     "A falta de resistividad declarada, se calcula una fibra de referencia como "
                     "sustitución explícita; no representa el comportamiento de esta espuma u otro medio.",)
    return AutomaticAbsorption(
        thickness, 20_000.0, "Fibra de referencia · σ 20.000 Pa·s/m²",
        ("Relleno automático: σ=20.000 Pa·s/m² de una fibra de referencia, Hansen 6.ª ed., "
         "tabla 7.12, p.442. Hipótesis de diseño para Miki al espesor realmente seleccionado; "
         "no es una propiedad medida del producto ni se infiere de su densidad o del Damping XML.", *extra),
        "hansen-6e-table-7.12-reference-fibre-20000",
    )


def resolve_frame(cavity: Cavity) -> AutomaticFrame:
    """Resolve generic topology from explicit selection or reviewed V10 codes.

    A screw does not turn continuous stud/flange contact into an isolated
    point support. Thin steel and timber shared studs both retain the line
    idealisation unless the selected arrangement explicitly declares otherwise.
    """
    spacing = cavity.stud_spacing_mm / 1000
    entry = cavity.stud
    warnings = []
    code = None
    if entry is not None:
        raw = entry.properties.get("connection_code")
        if (entry.kind == "connection"
                and entry.properties.get("units_schema_verified") is True
                and type(raw) in (int, float) and math.isfinite(raw) and float(raw).is_integer()):
            code = int(raw)
            warnings.append(f"Topología automática: código de catálogo {code} interpretado "
                            "por la política de modelos Noiz; no es el algoritmo acústico "
                            "del programa de origen ni un ensayo del fabricante.")
    # The frame selector's explicit no-connection option is authoritative.
    independent = (cavity.frame_type == "independent" or code in _INDEPENDENT_CODES
                   or (entry is None and cavity.stud_configuration == "independent"))
    if independent:
        label = "Hojas sin puentes comunes"
        warnings.append("Frame automático: hojas independientes; se omite la vía estructural "
                        "solo para una configuración declarada sin conexiones comunes. "
                        "No incluye puentes periféricos del montaje de laboratorio.")
        return AutomaticFrame("independent", label, spacing, spacing, tuple(warnings),
                              catalogue_connection_code=code)

    if code in _POINT_CODES:
        vertical = entry.properties.get("brace_spacing_m")
        if type(vertical) not in (int, float) or not math.isfinite(vertical) or vertical <= 0:
            vertical = spacing
            warnings.append("No hay separación vertical documentada para los puntos; "
                            "se supone una retícula cuadrada con la separación de montantes.")
        point_spacing = math.sqrt(spacing * vertical)
        warnings.append("Frame automático: conexión puntual rígida genérica; separación "
                        "equivalente e = sqrt(separación horizontal × vertical). "
                        "La geometría del catálogo no acredita flexibilidad dinámica.")
        return AutomaticFrame("point_pair", "Puentes puntuales entre ambas hojas · genérico",
                              spacing, point_spacing, tuple(warnings), catalogue_connection_code=code)

    ordinary = entry is None and cavity.frame_type in ("timber", "steel")
    ordinary = ordinary or (entry is not None and entry.kind == "stud"
                             and entry.properties.get("frame_material") in ("timber", "metal"))
    ordinary = ordinary or code in _ORDINARY_LINE_CODES
    if not ordinary:
        warnings.append("La conexión seleccionada no tiene una caracterización acústica "
                        "verificada en Noiz. Se representa por un puente lineal rígido genérico; "
                        "no se atribuye una mejora demostrada a clips, resortes, elastómeros, "
                        "montantes alternados ni perfiles comerciales especiales.")
    warnings.append("Frame automático: contacto lineal rígido Sharp. Los tornillos sobre una "
                    "ala continua no se convierten en apoyos puntuales. La flexibilidad de un "
                    "perfil metálico real puede modificar el resultado; no se infiere compliancia "
                    "ni un calibre de ajuste a partir del nombre comercial.")
    return AutomaticFrame("line", "Puente lineal rígido · genérico", spacing,
                          spacing, tuple(warnings), catalogue_connection_code=code)
