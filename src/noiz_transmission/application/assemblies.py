"""Immutable, interface-independent construction inputs for the V2 workbench.

A panel is a stack of co-moving, unbonded isotropic layers. Its bending
stiffness is the sum of individual stiffnesses, not the stiffness of a bonded
laminate. A cavity can describe an unsupported connection for editing and
persistence; the prediction service must explicitly refuse unsupported physics.
"""

from __future__ import annotations

from dataclasses import dataclass

from noiz_transmission.application.materials import finite_number, nonempty_string
from noiz_transmission.catalog import CatalogEntry, entry_from_dict, entry_to_dict

ELEMENT_TYPES = frozenset({"wall", "ceiling", "floor", "roof", "glazing", "door", "porous"})


def _catalog_snapshot(value: CatalogEntry | None, name: str, kind: str | None = None
                      ) -> CatalogEntry | None:
    if value is None:
        return None
    if not isinstance(value, CatalogEntry):
        raise ValueError(f"{name}: se requiere un registro CatalogEntry.")
    if kind is not None and value.kind != kind:
        raise ValueError(f"{name}: se requiere la familia {kind}.")
    return entry_from_dict(entry_to_dict(value))


def _nonnegative(value: float, name: str) -> float:
    number = finite_number(value, name)
    if number < 0:
        raise ValueError(f"{name} no puede ser negativo.")
    return number


@dataclass(frozen=True)
class Layer:
    name: str
    thickness_mm: float
    density_kg_m3: float
    young_modulus_pa: float
    loss_factor: float = 0.01
    poisson_ratio: float = 0.3
    count: int = 1
    catalog_entry: CatalogEntry | None = None
    profile: CatalogEntry | None = None

    def __post_init__(self) -> None:
        nonempty_string(self.name, "name")
        for name in ("thickness_mm", "density_kg_m3", "young_modulus_pa"):
            finite_number(getattr(self, name), name, positive=True)
        _nonnegative(self.loss_factor, "loss_factor")
        poisson = finite_number(self.poisson_ratio, "poisson_ratio")
        if not -1 < poisson < 0.5:
            raise ValueError("poisson_ratio debe estar entre -1 y 0.5 (excluidos).")
        if type(self.count) is not int or self.count < 1:
            raise ValueError("count debe ser un entero positivo.")
        object.__setattr__(self, "catalog_entry", _catalog_snapshot(
            self.catalog_entry, "catalog_entry",
        ))
        object.__setattr__(self, "profile", _catalog_snapshot(self.profile, "profile", "profile"))


@dataclass(frozen=True)
class Panel:
    layers: tuple[Layer, ...]
    name: str = "Panel"

    def __post_init__(self) -> None:
        nonempty_string(self.name, "name")
        if (not isinstance(self.layers, tuple) or not 1 <= len(self.layers) <= 6
                or any(not isinstance(layer, Layer) for layer in self.layers)):
            raise ValueError("Cada panel requiere una tupla de una a seis capas Layer.")


@dataclass(frozen=True)
class Cavity:
    depth_mm: float = 100
    absorber: CatalogEntry | None = None
    absorber_thickness_mm: float = 0
    flow_resistivity_pa_s_m2: float | None = None
    frame_type: str = "independent"
    stud_width_mm: float = 40
    stud_depth_mm: float = 90
    stud_spacing_mm: float = 600

    def __post_init__(self) -> None:
        for name in ("depth_mm", "stud_width_mm", "stud_depth_mm", "stud_spacing_mm"):
            finite_number(getattr(self, name), name, positive=True)
        thickness = _nonnegative(self.absorber_thickness_mm, "absorber_thickness_mm")
        if thickness > self.depth_mm:
            raise ValueError("El espesor absorbente no puede superar la profundidad de cámara.")
        if self.flow_resistivity_pa_s_m2 is not None:
            finite_number(self.flow_resistivity_pa_s_m2, "flow_resistivity_pa_s_m2", positive=True)
        nonempty_string(self.frame_type, "frame_type")
        object.__setattr__(self, "absorber", _catalog_snapshot(
            self.absorber, "absorber", "absorption",
        ))


@dataclass(frozen=True)
class AssemblyProject:
    name: str
    panels: tuple[Panel, ...]
    cavities: tuple[Cavity, ...] = ()
    element_type: str = "wall"
    width_m: float = 2.4
    height_m: float = 2.7
    incidence: str = "diffuse"
    air_density_kg_m3: float = 1.21
    sound_speed_m_s: float = 343
    limiting_angle_deg: float = 78
    leak_percentage: float = 0
    floor_cover: CatalogEntry | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        nonempty_string(self.name, "name")
        if (not isinstance(self.panels, tuple) or not 1 <= len(self.panels) <= 3
                or any(not isinstance(panel, Panel) for panel in self.panels)):
            raise ValueError("El elemento requiere una tupla de uno a tres paneles Panel.")
        if (not isinstance(self.cavities, tuple) or len(self.cavities) != len(self.panels) - 1
                or any(not isinstance(cavity, Cavity) for cavity in self.cavities)):
            raise ValueError("Se requiere exactamente una cámara entre cada par de paneles.")
        if not isinstance(self.element_type, str) or self.element_type not in ELEMENT_TYPES:
            raise ValueError("Tipo de elemento constructivo desconocido.")
        if self.incidence not in ("diffuse", "normal"):
            raise ValueError("incidence debe ser diffuse o normal.")
        for name in ("width_m", "height_m", "air_density_kg_m3", "sound_speed_m_s"):
            finite_number(getattr(self, name), name, positive=True)
        angle = finite_number(self.limiting_angle_deg, "limiting_angle_deg", positive=True)
        if angle > 90:
            raise ValueError("limiting_angle_deg debe estar en (0, 90].")
        leak = _nonnegative(self.leak_percentage, "leak_percentage")
        if leak > 100:
            raise ValueError("leak_percentage debe estar entre 0 y 100.")
        if not isinstance(self.notes, str):
            raise ValueError("notes debe ser texto.")
        object.__setattr__(self, "floor_cover", _catalog_snapshot(
            self.floor_cover, "floor_cover", "floor_cover",
        ))


@dataclass(frozen=True)
class AssemblyPrediction:
    project: AssemblyProject
    frequencies_hz: tuple[float, ...]
    tl_db: tuple[float, ...]
    rw_db: int | None
    total_mass_kg_m2: float
    total_thickness_mm: float
    critical_frequencies_hz: tuple[float, ...]
    resonance_frequencies_hz: tuple[float, ...]
    warnings: tuple[str, ...]
    model_name: str = "transfer-matrix-plate-1"
