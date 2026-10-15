"""Immutable, interface-independent construction inputs for the V3 workbench.

A panel is a stack of co-moving, unbonded isotropic layers. Its bending
stiffness is the sum of individual stiffnesses, not the stiffness of a bonded
laminate. A cavity can describe an unsupported connection for editing and
persistence; the prediction service must explicitly refuse unsupported physics.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from noiz_transmission.application.materials import finite_number, nonempty_string
from noiz_transmission.catalog import CatalogEntry, entry_from_dict, entry_to_dict
from noiz_transmission.core.ratings import legacy_stc

ELEMENT_TYPES = frozenset({"wall", "ceiling", "floor", "roof", "glazing", "door", "porous"})
ELEMENT_PANEL_LIMITS = {"wall": 4, "ceiling": 4, "floor": 3, "roof": 2,
                        "glazing": 4, "door": 4, "porous": 1}


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


def _bool(value: bool, name: str) -> None:
    if type(value) is not bool:
        raise ValueError(f"{name} debe ser booleano.")


def _count(value: int, name: str, minimum: int = 0) -> None:
    if type(value) is not int or not minimum <= value <= 10:
        raise ValueError(f"{name} debe ser un entero entre {minimum} y 10.")


@dataclass(frozen=True)
class Facing:
    enabled: bool = False
    material: CatalogEntry | None = None
    thickness_mm: float = 0
    flow_resistivity_pa_s_m2: float | None = None
    count: int = 1

    def __post_init__(self) -> None:
        _bool(self.enabled, "enabled")
        _count(self.count, "count")
        _nonnegative(self.thickness_mm, "thickness_mm")
        if self.flow_resistivity_pa_s_m2 is not None:
            finite_number(self.flow_resistivity_pa_s_m2, "flow_resistivity_pa_s_m2", positive=True)
        object.__setattr__(self, "material", _catalog_snapshot(self.material, "material", "absorption"))


@dataclass(frozen=True)
class LeakSettings:
    enabled: bool = False
    kind: str = "slit"
    method: str = "gomperts"
    position: str = "middle"
    height_mm: float = 1
    length_mm: float = 1000
    depth_mm: float = 100
    radius_mm: float = 1
    mechel_sealed: bool = False
    mass_side1_kg_m2: float = 0
    mass_side2_kg_m2: float = 0
    mechel_absorption: bool = False
    cavity_empty: bool = True
    cavity_absorption: CatalogEntry | None = None

    def __post_init__(self) -> None:
        for name in ("enabled", "mechel_sealed", "mechel_absorption", "cavity_empty"):
            _bool(getattr(self, name), name)
        if self.kind not in ("slit", "aperture"):
            raise ValueError("kind debe ser slit o aperture.")
        if self.method not in ("gomperts", "mechel", "open_area"):
            raise ValueError("Método de fuga desconocido.")
        if self.position not in ("middle", "edge", "corner"):
            raise ValueError("Posición de fuga desconocida.")
        if self.kind == "slit" and self.position == "corner":
            raise ValueError("Una rendija admite posición middle o edge.")
        for name in ("height_mm", "length_mm", "radius_mm"):
            finite_number(getattr(self, name), name, positive=True)
        for name in ("depth_mm", "mass_side1_kg_m2", "mass_side2_kg_m2"):
            _nonnegative(getattr(self, name), name)
        object.__setattr__(self, "cavity_absorption", _catalog_snapshot(
            self.cavity_absorption, "cavity_absorption", "absorption",
        ))

    @property
    def area_m2(self) -> float:
        import math

        return (self.height_mm * self.length_mm if self.kind == "slit"
                else math.pi * self.radius_mm * self.radius_mm) / 1_000_000


@dataclass(frozen=True)
class RainfallSettings:
    rain_type: str = "laboratory"
    laboratory_class: str = "heavy"
    natural_mm_h: float = 40
    rainfall_area_m2: float = 1

    def __post_init__(self) -> None:
        if self.rain_type not in ("laboratory", "natural"):
            raise ValueError("rain_type debe ser laboratory o natural.")
        if self.laboratory_class not in ("moderate", "intense", "heavy", "cloudburst"):
            raise ValueError("Clase de lluvia de laboratorio desconocida.")
        for name in ("natural_mm_h", "rainfall_area_m2"):
            finite_number(getattr(self, name), name, positive=True)


@dataclass(frozen=True)
class FloorSettings:
    mode: str = "measured"
    base_floor: str = "lightweight"

    def __post_init__(self) -> None:
        if self.mode not in ("measured", "predicted"):
            raise ValueError("FloorSettings.mode debe ser measured o predicted.")
        if self.base_floor not in ("lightweight", "clt", "heavyweight"):
            raise ValueError("Tipo de suelo base desconocido.")


@dataclass(frozen=True)
class PorousSettings:
    material: CatalogEntry | None = None
    thickness_mm: float = 50
    flow_resistivity_pa_s_m2: float | None = None

    def __post_init__(self) -> None:
        finite_number(self.thickness_mm, "thickness_mm", positive=True)
        if self.flow_resistivity_pa_s_m2 is not None:
            finite_number(self.flow_resistivity_pa_s_m2, "flow_resistivity_pa_s_m2", positive=True)
        object.__setattr__(self, "material", _catalog_snapshot(self.material, "material", "absorption"))


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
    enabled: bool = True

    def __post_init__(self) -> None:
        nonempty_string(self.name, "name")
        for name in ("thickness_mm", "density_kg_m3", "young_modulus_pa"):
            finite_number(getattr(self, name), name, positive=True)
        _nonnegative(self.loss_factor, "loss_factor")
        poisson = finite_number(self.poisson_ratio, "poisson_ratio")
        if not -1 < poisson < 0.5:
            raise ValueError("poisson_ratio debe estar entre -1 y 0.5 (excluidos).")
        _count(self.count, "count", minimum=1)
        _bool(self.enabled, "enabled")
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
    absorber_count: int = 1
    stud: CatalogEntry | None = None
    gas: str = "air"

    def __post_init__(self) -> None:
        for name in ("depth_mm", "stud_width_mm", "stud_depth_mm", "stud_spacing_mm"):
            finite_number(getattr(self, name), name, positive=True)
        thickness = _nonnegative(self.absorber_thickness_mm, "absorber_thickness_mm")
        _count(self.absorber_count, "absorber_count")
        if thickness * self.absorber_count > self.depth_mm:
            raise ValueError("El espesor absorbente no puede superar la profundidad de cámara.")
        if self.flow_resistivity_pa_s_m2 is not None:
            finite_number(self.flow_resistivity_pa_s_m2, "flow_resistivity_pa_s_m2", positive=True)
        nonempty_string(self.frame_type, "frame_type")
        if self.gas not in ("air", "argon", "krypton", "xenon"):
            raise ValueError("Gas de cámara desconocido.")
        object.__setattr__(self, "absorber", _catalog_snapshot(
            self.absorber, "absorber", "absorption",
        ))
        object.__setattr__(self, "stud", _catalog_snapshot(self.stud, "stud", "stud"))


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
    facing: Facing = field(default_factory=Facing)
    leak: LeakSettings = field(default_factory=LeakSettings)
    rainfall: RainfallSettings = field(default_factory=RainfallSettings)
    porous: PorousSettings = field(default_factory=PorousSettings)
    floor: FloorSettings = field(default_factory=FloorSettings)
    excitation: str = "airborne"

    def __post_init__(self) -> None:
        nonempty_string(self.name, "name")
        if (not isinstance(self.panels, tuple) or not 1 <= len(self.panels) <= 4
                or any(not isinstance(panel, Panel) for panel in self.panels)):
            raise ValueError("El elemento requiere una tupla de uno a cuatro paneles Panel.")
        if (not isinstance(self.cavities, tuple) or len(self.cavities) != len(self.panels) - 1
                or any(not isinstance(cavity, Cavity) for cavity in self.cavities)):
            raise ValueError("Se requiere exactamente una cámara entre cada par de paneles.")
        if not isinstance(self.element_type, str) or self.element_type not in ELEMENT_TYPES:
            raise ValueError("Tipo de elemento constructivo desconocido.")
        if len(self.panels) > ELEMENT_PANEL_LIMITS[self.element_type]:
            raise ValueError(f"{self.element_type} admite como máximo "
                             f"{ELEMENT_PANEL_LIMITS[self.element_type]} paneles.")
        if self.excitation not in ("airborne", "impact", "rainfall"):
            raise ValueError("Excitación desconocida.")
        for name, cls in (("facing", Facing), ("leak", LeakSettings),
                          ("rainfall", RainfallSettings), ("porous", PorousSettings),
                          ("floor", FloorSettings)):
            if not isinstance(getattr(self, name), cls):
                raise ValueError(f"{name} requiere {cls.__name__}.")
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

    @property
    def stc_db(self) -> int | None:
        """Indicative legacy 32/8 STC, calculated from TL independently of Rw.

        This computed property keeps old result constructors and project
        schema 3 compatible. STC is a classification number, not a dB unit;
        the suffix follows the existing ``rw_db`` API convention only.
        Neither normal-incidence TL nor an impact spectrum yields STC here.
        """
        if self.project.incidence != "diffuse" or self.project.excitation != "airborne":
            return None
        return legacy_stc(self.frequencies_hz, self.tl_db).stc
