"""Reproducible prediction, strict V3 workspaces and offline reports."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import platform
import tempfile
import warnings as python_warnings
from collections.abc import Sequence
from dataclasses import asdict, fields
from html import escape
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from threading import Event
from typing import Any

import numpy as np

from noiz_transmission import __version__
from noiz_transmission.application.assemblies import (
    AssemblyPrediction,
    AssemblyProject,
    Cavity,
    Facing,
    FloorSettings,
    Layer,
    LeakSettings,
    Panel,
    PorousSettings,
    RainfallSettings,
)
from noiz_transmission.application.materials import (
    Material,
    finite_number,
    list_materials,
    strict_json_loads,
)
from noiz_transmission.application.services import Project, load_project
from noiz_transmission.catalog import CatalogEntry, entry_from_dict, entry_to_dict
from noiz_transmission.core.ratings import ISO717_FREQUENCIES_HZ, STC_PROCEDURE, iso717_rw
from noiz_transmission.core.transfer import (
    MODEL_ID,
    NOMINAL_BANDS_HZ,
    Gap,
    MikiExtrapolationWarning,
    Plate,
    predict_multilayer,
)

PROJECT_SCHEMA_VERSION = 3
_MAX_BYTES = 32 * 1024 * 1024


def _material_entry(material: Material, thickness_mm: float, loss_factor: float) -> CatalogEntry:
    """Carry the entire legacy provenance forward without claiming XML origin."""
    original = asdict(material)
    encoded = json.dumps(original, sort_keys=True, ensure_ascii=False, allow_nan=False)
    return CatalogEntry(
        id=f"noiz:{material.id}", kind="material", name=material.name,
        category="Referencia sintética" if material.data_status == "synthetic" else "Referencia",
        manufacturer="Sin fabricante", countries=(material.region,),
        properties={
            "density_kg_m3": material.density_kg_m3, "thickness_m": thickness_mm / 1000,
            "young_modulus_pa": material.young_modulus_pa, "poisson_ratio": material.poisson_ratio,
            "loss_factor": loss_factor, "material_type": "Isotropic", "solid_model_eligible": True,
            "measurement_verified": False, "data_status": material.data_status,
            "loss_factor_source": "Hipótesis del usuario; V1 no contiene amortiguamiento",
        },
        raw_fields={key: json.dumps(value, ensure_ascii=False) for key, value in original.items()},
        source_file="noiz-v1-material-snapshot", source_sha256=hashlib.sha256(encoded.encode()).hexdigest(),
        original_id=material.id,
        warnings=(f"Procedencia: {material.source}", f"Incertidumbre: {material.uncertainty}"),
    )


def default_project() -> AssemblyProject:
    """A declared synthetic, mechanically independent two-leaf worked example."""
    entry = _material_entry(list_materials()[0], 12.5, 0.03)
    layer = layer_from_entry(entry)
    return AssemblyProject(
        "Tabique doble · ejemplo sintético",
        (Panel((layer,), "Panel 1"), Panel((layer,), "Panel 2")), (Cavity(),),
        notes="Ejemplo sintético: dos placas independientes, sin puentes estructurales; "
        "factor de pérdidas supuesto 0.03. No representa un sistema comercial ensayado.",
    )


def default_project_v3(element_type: str = "wall") -> AssemblyProject:
    """One enabled synthetic layer; every new calculation starts explicitly."""
    reference = default_project()
    if element_type == "glazing":
        layer = Layer("Vidrio isotrópico · referencia sintética", 6, 2500, 70e9, 0.01, 0.22)
        panel = Panel((layer,), "Panel 1")
    else:
        panel = reference.panels[0]
    return AssemblyProject(
        name="Nuevo elemento", panels=(panel,), element_type=element_type,
        excitation="impact" if element_type == "floor" else (
            "rainfall" if element_type == "roof" else "airborne"
        ),
        notes="Ejemplo sintético editable; las propiedades no acreditan un sistema comercial.",
    )


default_single_project = default_project_v3


def _eligible_entry(entry: CatalogEntry) -> None:
    props = entry.properties
    if (entry.kind not in ("material", "glazing") or props.get("solid_model_eligible") is not True
            or props.get("material_type") != "Isotropic"):
        raise ValueError(
            f"{entry.name}: solo placas isotrópicas con propiedades completas son calculables; "
            "materiales compuestos, núcleos, perfiles y anisótropos requieren otro modelo.",
        )
    for key in ("anisotropic_ratio", "orthotropic_ratio", "orthotropic_ratio_zy"):
        if key in props and (type(props[key]) not in (int, float) or props[key] != 1):
            raise ValueError(f"{entry.name}: anisotropía no compatible con placa isotrópica.")


def layer_from_entry(entry: CatalogEntry) -> Layer:
    """Read explicit SI properties; no Poisson ratio, damping or units are guessed."""
    if not isinstance(entry, CatalogEntry):
        raise ValueError("Se requiere un registro CatalogEntry.")
    entry = entry_from_dict(entry_to_dict(entry))
    _eligible_entry(entry)
    props = entry.properties
    thickness = finite_number(props.get("thickness_m"), "thickness_m", positive=True)
    return Layer(
        name=entry.name, thickness_mm=thickness * 1000,
        density_kg_m3=props.get("density_kg_m3"), young_modulus_pa=props.get("young_modulus_pa"),
        loss_factor=props.get("loss_factor"), poisson_ratio=props.get("poisson_ratio"),
        catalog_entry=entry,
    )


def _plate(panel: Panel) -> Plate:
    mass, stiffness, damped_stiffness = 0.0, 0.0, 0.0
    try:
        for layer in panel.layers:
            if not layer.enabled:
                continue
            thickness = layer.thickness_mm / 1000
            mass += layer.count * layer.density_kg_m3 * thickness
            rigidity = layer.count * layer.young_modulus_pa * thickness**3 / (
                12 * (1 - layer.poisson_ratio**2)
            )
            stiffness += rigidity
            damped_stiffness += rigidity * layer.loss_factor
        return Plate(mass, stiffness, damped_stiffness / stiffness)
    except (OverflowError, ZeroDivisionError) as exc:
        raise ValueError("Propiedades de placa fuera del intervalo numérico representable.") from exc


def _resonances(plates: tuple[Plate, ...], project: AssemblyProject) -> tuple[float, ...]:
    """Nonzero modes of the coupled mass/air-spring chain, ignoring bending/losses."""
    if len(plates) == 1:
        return ()
    stiffness = np.zeros((len(plates), len(plates)), dtype=float)
    for index, cavity in enumerate(project.cavities):
        density, speed = _cavity_gas(cavity, project)
        spring = density * speed**2 / (cavity.depth_mm / 1000)
        stiffness[index, index] += spring
        stiffness[index + 1, index + 1] += spring
        stiffness[index, index + 1] -= spring
        stiffness[index + 1, index] -= spring
    root_mass = np.sqrt([plate.mass_kg_m2 for plate in plates])
    eigenvalues = np.linalg.eigvalsh(stiffness / root_mass[:, None] / root_mass[None, :])
    return tuple(float(math.sqrt(max(0, value)) / (2 * math.pi)) for value in eigenvalues[1:])


def _source_warnings(project: AssemblyProject) -> list[str]:
    warnings: list[str] = []
    for panel in project.panels:
        for layer in panel.layers:
            if not layer.enabled:
                continue
            entry = layer.catalog_entry
            if entry is None:
                warnings.append(f"{layer.name}: propiedades manuales sin referencia documental adjunta.")
                continue
            if entry.properties.get("data_status") == "synthetic":
                warnings.append(f"{layer.name}: datos sintéticos; no es un producto comercial.")
            elif entry.id.startswith("xml:"):
                warnings.append(
                    f"{layer.name}: registro XML importado de {entry.source_file}, "
                    f"versión {entry.properties.get('source_version', 'desconocida')}/"
                    f"{entry.properties.get('source_release', '?')}; no es un ensayo verificado.",
                )
            warnings.extend(entry.warnings)
            compared = {
                "thickness_m": layer.thickness_mm / 1000, "density_kg_m3": layer.density_kg_m3,
                "young_modulus_pa": layer.young_modulus_pa, "loss_factor": layer.loss_factor,
                "poisson_ratio": layer.poisson_ratio,
            }
            changed = [key for key, value in compared.items() if entry.properties.get(key) != value]
            if changed:
                warnings.append(f"{layer.name}: valores editados respecto al catálogo: {', '.join(changed)}.")
    return warnings


def _cavity_gas(cavity: Cavity, project: AssemblyProject) -> tuple[float, float]:
    if cavity.gas == "air":
        return project.air_density_kg_m3, project.sound_speed_m_s
    from noiz_transmission.core.transfer import ideal_gas_properties

    return ideal_gas_properties(cavity.gas)


def _porous_layer(thickness_mm: float, sigma: float | None, name: str):
    from noiz_transmission.core.transfer import PorousLayer

    if thickness_mm <= 0 or sigma is None:
        raise ValueError(f"{name}: indique espesor positivo y resistividad al flujo explícita; "
                         "Damping del XML no es resistividad.")
    return PorousLayer(thickness_mm / 1000, sigma)


def _leak_fraction(project: AssemblyProject) -> float:
    if not project.leak.enabled:
        return project.leak_percentage / 100
    if project.leak_percentage:
        raise ValueError("Desactive la fuga porcentual heredada antes de configurar una fuga geométrica.")
    if project.leak.method != "open_area":
        raise ValueError(f"Fuga {project.leak.method}: la solución aún no dispone de implementación "
                         "verificada. Seleccione explícitamente Área abierta ideal para esa aproximación.")
    fraction = project.leak.area_m2 / (project.width_m * project.height_m)
    if not math.isfinite(fraction) or not 0 < fraction <= 1:
        raise ValueError("El área de fuga debe ser positiva y no superar el área del elemento.")
    return fraction


def predict_assembly(project: AssemblyProject, *, cancel_event: Event | None = None
                     ) -> AssemblyPrediction:
    """Calculate selected physics; unsupported excitation never yields an airborne substitute."""
    if not isinstance(project, AssemblyProject):
        raise ValueError("Se requiere un AssemblyProject válido.")
    if cancel_event is not None:
        if not isinstance(cancel_event, Event):
            raise ValueError("cancel_event debe ser un threading.Event.")
        if cancel_event.is_set():
            raise ValueError("Cálculo cancelado.")
    project = project_from_dict(project_to_dict(project))
    if project.excitation != "airborne":
        mode = "impacto (Ln,w/IIC)" if project.excitation == "impact" else "lluvia"
        raise ValueError(f"Predicción de {mode}: modelo específico aún no implementado. "
                         "Los ajustes se conservan; no se genera una curva de transmisión aérea.")
    if project.floor_cover is not None:
        raise ValueError("El revestimiento de suelo requiere un modelo validado de impacto; "
                         "retírelo para calcular únicamente transmisión aérea.")
    warnings = [
        "Modelo exploratorio de placas isotrópicas delgadas e infinitas y cámaras selladas; "
        "no equivale al algoritmo INSUL ni dispone de validación experimental completa.",
        "Capas de cada panel solidarias en desplazamiento pero sin unión compuesta: "
        "masas y rigideces de flexión individuales se suman. No modela laminados adheridos.",
        "Anchura y altura se conservan como geometría de proyecto; no modifican la curva "
        "del modelo infinito ni incluyen modos finitos o condiciones de borde. "
        "Con fuga geométrica sí determinan la fracción de área abierta.",
        "Se calcula transmisión aérea del elemento; se excluyen flancos, uniones "
        "y aislamiento entre recintos (ISO 12354).",
        "Integración energética dentro de tercios de octava y, en campo difuso, "
        "sobre los ángulos de incidencia. La convergencia numérica no es exactitud experimental.",
        "Masa superficial indicada: suma de las hojas sólidas; no incluye estructura "
        "ni masa del absorbente de cámara o Facing.",
    ]
    porous_mode = project.element_type == "porous"
    plates, gaps = (), []
    facing = None
    active_facing = project.facing.enabled and project.facing.count > 0
    if active_facing:
        if porous_mode or len(project.panels) != 1:
            raise ValueError("Facing se admite solo para un panel sólido Single.")
        facing = _porous_layer(project.facing.thickness_mm * project.facing.count,
                               project.facing.flow_resistivity_pa_s_m2, "Facing")
        warnings.append("Facing: revestimiento poroso Miki en la cara incidente, con marco rígido; "
                        "no representa unión elástica ni añade rigidez a la placa.")
        if project.facing.material is not None:
            warnings.extend(project.facing.material.warnings)
    if porous_mode:
        porous = _porous_layer(project.porous.thickness_mm,
                               project.porous.flow_resistivity_pa_s_m2, "Panel poroso independiente")
        warnings = [warning for warning in warnings if not warning.startswith((
            "Modelo exploratorio de placas", "Capas de cada panel", "Masa superficial",
        ))]
        warnings.append("Lámina porosa independiente: transmisión aérea Miki con marco rígido, "
                        "sin placa ni respaldo; no es un coeficiente de absorción ni un ensayo. "
                        "Las capas sólidas guardadas no participan en el modo Porous.")
        if project.porous.material is not None:
            warnings.extend(project.porous.material.warnings)
        warnings.append("La masa del material poroso no se infiere de la resistividad al flujo.")
    else:
        for panel in project.panels:
            if not any(layer.enabled for layer in panel.layers):
                raise ValueError(f"{panel.name}: active al menos una capa antes de calcular.")
            for layer in panel.layers:
                if not layer.enabled:
                    continue
                if layer.profile is not None:
                    raise ValueError("La rigidez de perfiles no está modelada; retire el perfil para "
                                     "calcular una placa isotrópica plana.")
                if layer.catalog_entry is not None:
                    _eligible_entry(layer.catalog_entry)
        for index, cavity in enumerate(project.cavities, start=1):
            if cavity.frame_type != "independent" or cavity.stud is not None:
                raise ValueError(f"Cámara {index}: el modelo de puentes estructurales para "
                                 f"{cavity.frame_type!r} no está disponible. Seleccione hojas "
                                 "independientes sin montante solo si corresponde al sistema real.")
            thickness = cavity.absorber_thickness_mm * cavity.absorber_count
            sigma = cavity.flow_resistivity_pa_s_m2 if cavity.absorber_count else None
            if cavity.absorber_count and cavity.absorber is not None and thickness == 0:
                raise ValueError(f"Cámara {index}: indique un espesor positivo para el absorbente seleccionado.")
            if (thickness > 0) != (sigma is not None):
                raise ValueError(f"Cámara {index}: el absorbente requiere espesor y resistividad "
                                 "al flujo explícitos; Damping del XML no es resistividad.")
            if thickness:
                warnings.append(f"Cámara {index}: absorbente como fluido equivalente Miki rígido; "
                                "resistividad introducida explícitamente por el usuario, "
                                "sin deducirla del Damping XML.")
                if cavity.absorber:
                    warnings.extend(cavity.absorber.warnings)
                    warnings.append(f"Absorbente importado: {cavity.absorber.name}; "
                                    "el registro no acredita un ensayo verificado.")
            gas_kwargs = {}
            if cavity.gas != "air":
                density, speed = _cavity_gas(cavity, project)
                gas_kwargs = {"gas_density_kg_m3": density, "gas_sound_speed_m_s": speed}
                warnings.append(f"Cámara {index}: {cavity.gas} ideal puro a 20 °C y 101325 Pa; "
                                "no se consideran mezclas ni pérdidas térmicas en paredes.")
            gaps.append(Gap(cavity.depth_mm / 1000, sigma, thickness / 1000, **gas_kwargs))
        plates = tuple(_plate(panel) for panel in project.panels)
    if project.cavities:
        warnings.append("Las dimensiones de montantes son metadatos: las hojas se consideran "
                        "mecánicamente independientes. f₀ es un diagnóstico de masas/muelles "
                        "del gas, sin rigidez de placa ni corrección del relleno.")
    if project.element_type in ("floor", "ceiling", "roof"):
        warnings.append("La orientación es una etiqueta geométrica para transmisión aérea; "
                        "no se predice impacto, IIC, Ln,w, L'nT,w ni lluvia.")
    leak = _leak_fraction(project)
    frequencies = tuple(float(value) for value in NOMINAL_BANDS_HZ)
    with python_warnings.catch_warnings(record=True) as emitted:
        python_warnings.simplefilter("always", MikiExtrapolationWarning)
        kwargs = {"frequencies_hz": frequencies, "air_density": project.air_density_kg_m3,
                  "sound_speed": project.sound_speed_m_s, "incidence": project.incidence,
                  "angle_limit_deg": project.limiting_angle_deg}
        if cancel_event is not None:
            kwargs["cancel_event"] = cancel_event
        if porous_mode:
            from noiz_transmission.core.transfer import predict_porous_layer

            tl = predict_porous_layer(porous, **kwargs)
        else:
            if facing is not None:
                kwargs["facing"] = facing
            tl = predict_multilayer(plates, tuple(gaps), **kwargs)
    for warning in emitted:
        if issubclass(warning.category, MikiExtrapolationWarning):
            warnings.append(f"Extrapolación Miki (0.01 < f/σ < 1): {warning.message}")
        else:
            python_warnings.warn(str(warning.message), warning.category, stacklevel=2)
    if leak:
        tl = -10 * np.log10((1 - leak) * np.power(10.0, -tl / 10) + leak)
        warnings.append("Fuga ideal de área abierta: mezcla energética con transmisión unitaria; "
                        "no incluye profundidad, posición, difracción ni resonancias de abertura. "
                        "Esta aproximación no es Gomperts ni Mechel.")
    rw = None
    if project.incidence == "diffuse":
        selected = [float(value) for frequency, value in zip(frequencies, tl, strict=True)
                    if frequency in ISO717_FREQUENCIES_HZ]
        rw = iso717_rw(ISO717_FREQUENCIES_HZ, selected).rw_db
        warnings.append("Rw orientativo calculado con 100–3150 Hz mediante ISO 717-1; "
                        "procedimiento provisional pendiente de revisión normativa. "
                        "No constituye un ensayo ni una certificación.")
        warnings.append("STC orientativo: procedimiento legado 32/8, 125–4000 Hz, "
                        "TL redondeado a dB enteros (mitades alejadas de cero). "
                        "No declara conformidad con una edición de ASTM E413; "
                        "no constituye un ensayo ni una certificación.")
    else:
        warnings.append("Incidencia normal: no se asigna Rw ni STC a esta curva.")
    if not porous_mode:
        warnings.extend(_source_warnings(project))
    critical = tuple(project.sound_speed_m_s**2 / (2 * math.pi)
                     * math.sqrt(plate.mass_kg_m2 / plate.bending_stiffness_nm) for plate in plates)
    total_thickness = (project.porous.thickness_mm if porous_mode else sum(
        layer.count * layer.thickness_mm for panel in project.panels
        for layer in panel.layers if layer.enabled
    ) + sum(gap.depth_mm for gap in project.cavities))
    if active_facing:
        total_thickness += project.facing.thickness_mm * project.facing.count
    return AssemblyPrediction(
        project, frequencies, tuple(float(value) for value in tl), rw,
        sum(plate.mass_kg_m2 for plate in plates), total_thickness,
        critical, () if porous_mode else _resonances(plates, project),
        tuple(dict.fromkeys(warnings)), MODEL_ID,
    )


def octave_summary(prediction: AssemblyPrediction) -> tuple[tuple[float, float], ...]:
    """Seven octave TL values, averaging transmission with exact bandwidth weights.

    This assumes the same incident power per Hz used by the third-octave solver;
    it is not an arithmetic average of decibels or a single-frequency sample.
    """
    from noiz_transmission.core.transfer import EXACT_BAND_CENTRES_HZ

    if tuple(prediction.frequencies_hz) != tuple(NOMINAL_BANDS_HZ):
        raise ValueError("La tabla de octavas requiere los 21 tercios de octava de 50 a 5000 Hz.")
    values = np.asarray(prediction.tl_db, dtype=float)
    if values.shape != (21,) or np.any(~np.isfinite(values)):
        raise ValueError("El espectro TL debe contener 21 valores finitos.")
    weights = EXACT_BAND_CENTRES_HZ * (10**0.05 - 10**-0.05)
    result = []
    for index in range(1, 21, 3):
        losses, widths = values[index - 1:index + 2], weights[index - 1:index + 2]
        tau = np.dot(np.power(10.0, -losses / 10), widths) / np.sum(widths)
        result.append((float(NOMINAL_BANDS_HZ[index]), float(-10 * np.log10(tau))))
    return tuple(result)


def describe_assembly(project: AssemblyProject) -> str:
    """Describe active construction inputs, including assumptions visible in the editor."""
    if project.element_type == "porous":
        product = project.porous.material.name if project.porous.material else "Poroso manual"
        return f"Porous · {product}, {project.porous.thickness_mm:g} mm"
    parts = []
    if project.floor_cover is not None:
        parts.append(f"Floor cover: {project.floor_cover.name}")
    for index, panel in enumerate(project.panels):
        layers = [f"{layer.count} × {layer.thickness_mm:g} mm {layer.name}"
                  for layer in panel.layers if layer.enabled]
        parts.append(f"Panel {index + 1}: " + (" + ".join(layers) or "sin capas activas"))
        if index < len(project.cavities):
            cavity = project.cavities[index]
            frame = cavity.stud.name if cavity.stud else cavity.frame_type
            description = f"Frame {index + 1}: {frame}, {cavity.depth_mm:g} mm, {cavity.gas}"
            if cavity.absorber_count and cavity.absorber_thickness_mm:
                name = cavity.absorber.name if cavity.absorber else "absorbente manual"
                description += (f", {cavity.absorber_count} × "
                                f"{cavity.absorber_thickness_mm:g} mm {name}")
            parts.append(description)
    if project.facing.enabled and project.facing.count:
        name = project.facing.material.name if project.facing.material else "poroso manual"
        parts.append(f"Facing: {project.facing.count} × {project.facing.thickness_mm:g} mm {name}")
    if project.leak.enabled:
        parts.append(f"Leak: {project.leak.kind} · {project.leak.method} · {project.leak.area_m2:g} m²")
    elif project.leak_percentage:
        parts.append(f"Leak: área abierta ideal {project.leak_percentage:g} %")
    return " | ".join(parts)


def project_to_dict(project: AssemblyProject) -> dict[str, Any]:
    """Independent snapshots keep source records and edited physical values separately."""
    if not isinstance(project, AssemblyProject):
        raise ValueError("Se requiere un AssemblyProject válido.")
    result = {field.name: getattr(project, field.name) for field in fields(AssemblyProject)}
    result["panels"] = []
    for panel in project.panels:
        layers = []
        for layer in panel.layers:
            data = {field.name: getattr(layer, field.name) for field in fields(Layer)}
            for name in ("catalog_entry", "profile"):
                data[name] = None if data[name] is None else entry_to_dict(data[name])
            layers.append(data)
        result["panels"].append({"layers": layers, "name": panel.name})
    result["cavities"] = []
    for cavity in project.cavities:
        data = {field.name: getattr(cavity, field.name) for field in fields(Cavity)}
        for name in ("absorber", "stud"):
            data[name] = None if data[name] is None else entry_to_dict(data[name])
        result["cavities"].append(data)
    result["floor_cover"] = None if project.floor_cover is None else entry_to_dict(project.floor_cover)
    for name in ("facing", "leak", "rainfall", "porous", "floor"):
        settings = getattr(project, name)
        data = {field.name: getattr(settings, field.name) for field in fields(settings)}
        for key in ("material", "cavity_absorption"):
            if key in data and data[key] is not None:
                data[key] = entry_to_dict(data[key])
        result[name] = data
    return result


def _object(data: Any, cls: type) -> dict:
    if not isinstance(data, dict) or set(data) != {field.name for field in fields(cls)}:
        raise ValueError(f"{cls.__name__}: campos faltantes o desconocidos en el proyecto.")
    return dict(data)


def _list(data: Any, name: str) -> list:
    if not isinstance(data, list):
        raise ValueError(f"{name}: se requiere una lista JSON.")
    return data


def _project_from_dict(data: dict) -> AssemblyProject:
    """Decode a single project, without accepting nested workspace metadata."""
    result = _object(data, AssemblyProject)
    panels = []
    for item in _list(result["panels"], "panels"):
        panel = _object(item, Panel)
        layers = []
        for record in _list(panel["layers"], "layers"):
            layer = _object(record, Layer)
            for name in ("catalog_entry", "profile"):
                if layer[name] is not None:
                    layer[name] = entry_from_dict(layer[name])
            layers.append(Layer(**layer))
        panels.append(Panel(tuple(layers), panel["name"]))
    result["panels"] = tuple(panels)
    cavities = []
    for item in _list(result["cavities"], "cavities"):
        cavity = _object(item, Cavity)
        for name in ("absorber", "stud"):
            if cavity[name] is not None:
                cavity[name] = entry_from_dict(cavity[name])
        cavities.append(Cavity(**cavity))
    result["cavities"] = tuple(cavities)
    if result["floor_cover"] is not None:
        result["floor_cover"] = entry_from_dict(result["floor_cover"])
    for name, cls in (("facing", Facing), ("leak", LeakSettings), ("rainfall", RainfallSettings),
                      ("porous", PorousSettings), ("floor", FloorSettings)):
        data = _object(result[name], cls)
        for key in ("material", "cavity_absorption"):
            if key in data and data[key] is not None:
                data[key] = entry_from_dict(data[key])
        result[name] = cls(**data)
    return AssemblyProject(**result)


def _variant_key(project: AssemblyProject) -> tuple[str, int]:
    return project.element_type, len(project.panels)


def _variants_from_dicts(data: Any, active: AssemblyProject) -> tuple[AssemblyProject, ...]:
    """Every stored variant must have its own unambiguous mode/topology key."""
    variants = []
    keys = {_variant_key(active)}
    for item in _list(data, "variants"):
        variant = _project_from_dict(item)
        key = _variant_key(variant)
        if key in keys:
            raise ValueError(f"Variante duplicada para {key[0]} / {key[1]} paneles.")
        keys.add(key)
        variants.append(variant)
    return tuple(variants)


def project_from_dict(data: dict) -> AssemblyProject:
    """Decode the active project and validate any optional sibling variants.

    Direct callers may supply ``variants`` alongside project fields. The file
    format keeps that list exclusively in its header; nesting it in a saved
    project or another variant is rejected rather than guessed or ignored.
    """
    if not isinstance(data, dict):
        raise ValueError("AssemblyProject: se requiere un objeto JSON.")
    result = dict(data)
    variants = result.pop("variants", [])
    active = _project_from_dict(result)
    _variants_from_dicts(variants, active)
    return active


def _migrate_v2_dict(data: Any) -> AssemblyProject:
    """Accept only the exact old schema, then explicitly add each new default."""
    import copy

    data = copy.deepcopy(data)
    added_project = {"facing", "leak", "rainfall", "porous", "floor", "excitation"}
    old_project = {field.name for field in fields(AssemblyProject)} - added_project
    if not isinstance(data, dict) or set(data) != old_project:
        raise ValueError("AssemblyProject V2: campos faltantes o desconocidos.")
    for panel in _list(data["panels"], "panels"):
        panel = _object(panel, Panel)
        for layer in _list(panel["layers"], "layers"):
            if not isinstance(layer, dict) or set(layer) != {f.name for f in fields(Layer)} - {"enabled"}:
                raise ValueError("Layer V2: campos faltantes o desconocidos.")
            layer["enabled"] = True
    for cavity in _list(data["cavities"], "cavities"):
        added = {"absorber_count", "stud", "gas"}
        if not isinstance(cavity, dict) or set(cavity) != {f.name for f in fields(Cavity)} - added:
            raise ValueError("Cavity V2: campos faltantes o desconocidos.")
        cavity.update(absorber_count=1, stud=None, gas="air")
    for name, cls in (("facing", Facing), ("leak", LeakSettings), ("rainfall", RainfallSettings),
                      ("porous", PorousSettings), ("floor", FloorSettings)):
        data[name] = asdict(cls())
    data["excitation"] = "airborne"
    return project_from_dict(data)


def _atomic_write(path: str | Path, data: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="", dir=path.parent,
                                         prefix=f".{path.name}.", delete=False) as stream:
            temp_path = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()


def save_assembly(project: AssemblyProject, path: str | Path) -> None:
    """Save only the supplied active project; use save_workspace for all tabs."""
    save_workspace(project, (), path)


def save_workspace(active: AssemblyProject, variants: Sequence[AssemblyProject],
                   path: str | Path) -> None:
    """Atomically persist active inputs and every distinct cached editor variant.

    The active argument is authoritative for its mode/topology. Any cache entry
    with that key is validated but omitted, so an old cached copy cannot replace
    the current edits. Other duplicate keys are an error, never last-write-wins.
    """
    snapshot = project_to_dict(active)
    detached_active = _project_from_dict(snapshot)
    if not isinstance(variants, Sequence) or isinstance(variants, (str, bytes)):
        raise ValueError("variants requiere una secuencia de proyectos AssemblyProject.")
    variant_snapshots = []
    keys = set()
    for variant in variants:
        data = project_to_dict(variant)
        detached = _project_from_dict(data)
        key = _variant_key(detached)
        if key == _variant_key(detached_active):
            continue
        if key in keys:
            raise ValueError(f"Variante duplicada para {key[0]} / {key[1]} paneles.")
        keys.add(key)
        variant_snapshots.append(data)
    payload = {"schema_version": PROJECT_SCHEMA_VERSION, "model_name": MODEL_ID, "project": snapshot}
    if variant_snapshots:
        payload["variants"] = variant_snapshots
    encoded = json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    if len(encoded.encode("utf-8")) > _MAX_BYTES:
        raise ValueError("El proyecto supera el límite de 32 MiB.")
    _atomic_write(path, encoded)


def load_assembly(path: str | Path) -> AssemblyProject:
    """Validate a complete workspace and return its active project for CLI use."""
    return load_workspace(path)[0]


def load_workspace(path: str | Path) -> tuple[AssemblyProject, tuple[AssemblyProject, ...]]:
    """Load all V3 editor variants, or an active project from V1/V2/simple V3."""
    with Path(path).open("rb") as stream:
        raw = stream.read(_MAX_BYTES + 1)
    if len(raw) > _MAX_BYTES:
        raise ValueError("El proyecto supera el límite de 32 MiB.")
    try:
        payload = strict_json_loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("El proyecto no contiene JSON UTF-8 válido.") from exc
    if not isinstance(payload, dict) or type(payload.get("schema_version")) is not int:
        raise ValueError("El archivo no cumple el esquema de proyecto.")
    if payload["schema_version"] == 1:
        return migrate_legacy_project(load_project(path)), ()
    if payload["schema_version"] == 2:
        if (set(payload) != {"schema_version", "model_name", "project"}
                or payload["model_name"] != "transfer-matrix-plate-1"):
            raise ValueError("Versión de modelo V2 o campos desconocidos.")
        return _migrate_v2_dict(payload["project"]), ()
    if (set(payload) not in ({"schema_version", "model_name", "project"},
                            {"schema_version", "model_name", "project", "variants"})
            or payload["schema_version"] != PROJECT_SCHEMA_VERSION or payload["model_name"] != MODEL_ID):
        raise ValueError("Versión de esquema o modelo no compatible, o campos desconocidos.")
    active = _project_from_dict(payload["project"])
    variants = _variants_from_dicts(payload.get("variants", []), active)
    return active, variants


def migrate_legacy_project(project: Project) -> AssemblyProject:
    if not isinstance(project, Project):
        raise ValueError("Se requiere un Project V1 válido.")
    material = project.material_snapshot
    if material is None:
        material = next((item for item in list_materials() if item.id == project.material_id), None)
    if material is None:
        raise ValueError(f"Material V1 desconocido: {project.material_id}.")
    entry = _material_entry(material, project.thickness_mm, 0.01)
    original = json.dumps(asdict(project), ensure_ascii=False, allow_nan=False, sort_keys=True)
    return AssemblyProject(
        project.name, (Panel((layer_from_entry(entry),), "Panel 1"),),
        incidence="normal" if project.model == "normal_mass_law" else "diffuse",
        air_density_kg_m3=project.air_density_kg_m3, sound_speed_m_s=project.sound_speed_m_s,
        limiting_angle_deg=project.limiting_angle_deg,
        notes="Migrado desde V1. La curva actual usa rigidez/coincidencia e integración por banda "
        "y no reproduce la ley de masas V1. Factor de pérdidas supuesto 0.01 "
        "(V1 no lo almacena); revisar antes de usar. Proyecto original: " + original,
    )


def _versions() -> dict[str, str]:
    result = {"noiz-transmission": __version__, "python": platform.python_version()}
    for package in ("numpy", "scipy"):
        try:
            result[package] = version(package)
        except PackageNotFoundError:
            result[package] = "not-installed"
    return result


def _predictions(predictions: Sequence[AssemblyPrediction]) -> tuple[AssemblyPrediction, ...]:
    items = tuple(predictions)
    if not items:
        raise ValueError("Se requiere al menos una predicción para exportar.")
    for item in items:
        if not isinstance(item, AssemblyPrediction) or not isinstance(item.project, AssemblyProject):
            raise ValueError("Se requieren resultados AssemblyPrediction.")
        if not item.frequencies_hz or len(item.frequencies_hz) != len(item.tl_db):
            raise ValueError("Frecuencias y TL deben tener la misma longitud no vacía.")
        for frequency, loss in zip(item.frequencies_hz, item.tl_db, strict=True):
            finite_number(frequency, "frequency_hz", positive=True)
            finite_number(loss, "tl_db")
        finite_number(item.total_thickness_mm, "total_thickness_mm", positive=True)
        mass = finite_number(item.total_mass_kg_m2, "total_mass_kg_m2")
        if mass < 0 or (mass == 0 and item.project.element_type != "porous"):
            raise ValueError("Masa superficial no válida para este tipo de elemento.")
        if item.rw_db is not None and type(item.rw_db) is not int:
            raise ValueError("Rw debe ser entero o nulo.")
        if not isinstance(item.warnings, tuple) or any(not isinstance(w, str) for w in item.warnings):
            raise ValueError("Las advertencias deben ser una tupla de textos.")
        if item.model_name != MODEL_ID:
            raise ValueError("Versión de modelo desconocida.")
        project_from_dict(project_to_dict(item.project))
    return items


def _metadata(item: AssemblyPrediction, index: int) -> dict[str, Any]:
    return {
        "prediction_index": index, "project_name": item.project.name, "model_name": item.model_name,
        "total_mass_kg_m2": item.total_mass_kg_m2, "total_thickness_mm": item.total_thickness_mm,
        "rw_db_illustrative": item.rw_db,
        "stc_illustrative": item.stc_db,
        "stc_procedure": STC_PROCEDURE if item.stc_db is not None else None,
        "critical_frequencies_hz": json.dumps(item.critical_frequencies_hz, allow_nan=False),
        "resonance_frequencies_hz": json.dumps(item.resonance_frequencies_hz, allow_nan=False),
        "project_json": json.dumps(project_to_dict(item.project), ensure_ascii=False, allow_nan=False),
        "software_versions": json.dumps(_versions(), sort_keys=True),
        "warnings": " | ".join(item.warnings),
    }


def _csv_safe(value: Any) -> Any:
    if isinstance(value, str):
        stripped = value.lstrip()
        if (stripped and stripped[0] in "=+-@") or value.startswith(("\t", "\n", "\r")):
            return "'" + value
    return value


def export_assembly_csv(predictions: Sequence[AssemblyPrediction], path: str | Path) -> None:
    import io

    items = _predictions(predictions)
    metadata = [_metadata(item, index) for index, item in enumerate(items, 1)]
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=[*metadata[0], "frequency_hz", "tl_db"])
    writer.writeheader()
    for item, attributes in zip(items, metadata, strict=True):
        for frequency, loss in zip(item.frequencies_hz, item.tl_db, strict=True):
            row = {**attributes, "frequency_hz": frequency, "tl_db": loss}
            writer.writerow({key: _csv_safe(value) for key, value in row.items()})
    _atomic_write(path, stream.getvalue())


def export_assembly_html(predictions: Sequence[AssemblyPrediction], path: str | Path) -> None:
    items = _predictions(predictions)
    parts = [
        "<!doctype html><html lang='es'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width,initial-scale=1'>",
        "<title>Noiz Transmission · Informe de elemento</title>",
        "<style>body{font:15px system-ui,sans-serif;color:#173444;max-width:1120px;"
        "margin:40px auto;padding:0 24px}h1,h2{color:#087b89}table{border-collapse:collapse;"
        "width:100%;margin:18px 0}td,th{border:1px solid #ccdce3;padding:8px;text-align:left}"
        "th{background:#edf5f7}pre{white-space:pre-wrap;overflow-wrap:anywhere}"
        "li{margin:8px 0}@media print{details>*{display:block}section{break-before:page}"
        "section:first-of-type{break-before:auto}}</style></head><body>",
        "<h1>Noiz Transmission</h1><p>Predicción exploratoria de transmisión aérea de elementos. "
        "Resultados orientativos; no sustituyen ensayos ni constituyen certificación.</p>",
    ]
    for index, item in enumerate(items, 1):
        parts.append(f"<section><h2>{index}. {escape(item.project.name)}</h2>")
        rw = "No aplicable" if item.rw_db is None else f"{item.rw_db} dB (orientativo)"
        stc = ("No aplicable" if item.stc_db is None else
               f"{item.stc_db} (orientativo; legado 32/8, TL redondeado a dB enteros)")
        mass = ("Masa porosa: no inferida" if item.project.element_type == "porous" else
                f"Masa de hojas: {item.total_mass_kg_m2:g} kg/m²")
        parts.append(f"<p>Rw: {rw} · STC: {stc} · {mass} · "
                     f"Espesor total: {item.total_thickness_mm:g} mm</p>")
        parts.append(f"<p>{escape(describe_assembly(item.project))}</p>")
        parts.append("<table><thead><tr><th>Panel / capa</th><th>Producto</th><th>Cantidad</th>"
                     "<th>Espesor unitario (mm)</th><th>Densidad (kg/m³)</th></tr></thead><tbody>")
        for panel in item.project.panels:
            for layer in panel.layers:
                if not layer.enabled or item.project.element_type == "porous":
                    continue
                parts.append(f"<tr><td>{escape(panel.name)}</td><td>{escape(layer.name)}</td>"
                             f"<td>{layer.count}</td><td>{layer.thickness_mm:g}</td>"
                             f"<td>{layer.density_kg_m3:g}</td></tr>")
        if item.project.element_type == "porous":
            porous = item.project.porous
            product = porous.material.name if porous.material else "Poroso manual"
            parts.append(f"<tr><td>Porous</td><td>{escape(product)}</td><td>1</td>"
                         f"<td>{porous.thickness_mm:g}</td><td>No utilizada</td></tr>")
        parts.append("</tbody></table>")
        if item.project.element_type == "porous":
            parts.append("<p>Resistividad al flujo: "
                         f"{item.project.porous.flow_resistivity_pa_s_m2:g} Pa·s/m²</p>")
        parts.append("<h3>Alcance y limitaciones</h3><ul>")
        parts.extend(f"<li>{escape(warning)}</li>" for warning in item.warnings)
        parts.append("</ul><h3>Espectro de transmisión aérea</h3><table><thead><tr>"
                     "<th>Frecuencia nominal (Hz)</th><th>TL integrado en banda (dB)</th>"
                     "</tr></thead><tbody>")
        for frequency, loss in zip(item.frequencies_hz, item.tl_db, strict=True):
            parts.append(f"<tr><td>{frequency:.17g}</td><td>{loss:.17g}</td></tr>")
        metadata = json.dumps(_metadata(item, index), ensure_ascii=False, indent=2, allow_nan=False)
        parts.append("</tbody></table><details><summary>Entradas completas, procedencia y versiones"
                     f"</summary><pre>{escape(metadata)}</pre></details></section>")
    parts.append("</body></html>\n")
    _atomic_write(path, "\n".join(parts))
