"""Reproducible assembly prediction, strict V2 projects and offline reports."""

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
    Layer,
    Panel,
)
from noiz_transmission.application.materials import (
    Material,
    finite_number,
    list_materials,
    strict_json_loads,
)
from noiz_transmission.application.services import Project, load_project
from noiz_transmission.catalog import CatalogEntry, entry_from_dict, entry_to_dict
from noiz_transmission.core.ratings import ISO717_FREQUENCIES_HZ, iso717_rw
from noiz_transmission.core.transfer import (
    MODEL_ID,
    NOMINAL_BANDS_HZ,
    Gap,
    MikiExtrapolationWarning,
    Plate,
    predict_multilayer,
)

PROJECT_SCHEMA_VERSION = 2
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
        spring = project.air_density_kg_m3 * project.sound_speed_m_s**2 / (cavity.depth_mm / 1000)
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


def predict_assembly(project: AssemblyProject, *, cancel_event: Event | None = None
                     ) -> AssemblyPrediction:
    """Calculate only supported physics; preserve unsupported configurations for editing."""
    if not isinstance(project, AssemblyProject):
        raise ValueError("Se requiere un AssemblyProject válido.")
    if cancel_event is not None:
        if not isinstance(cancel_event, Event):
            raise ValueError("cancel_event debe ser un threading.Event.")
        if cancel_event.is_set():
            raise ValueError("Cálculo cancelado.")
    # Revalidate and detach mutable catalogue dictionaries before calculating or recording inputs.
    project = project_from_dict(project_to_dict(project))
    if project.floor_cover is not None:
        raise ValueError("El revestimiento de suelo requiere un modelo validado de impacto; "
                         "retírelo para calcular únicamente transmisión aérea.")
    if project.element_type == "porous":
        raise ValueError("El panel poroso independiente aún no tiene modelo validado; "
                         "el absorbente Miki solo se admite dentro de una cámara.")
    for panel in project.panels:
        for layer in panel.layers:
            if layer.profile is not None:
                raise ValueError("La rigidez de perfiles no está modelada; retire el perfil para "
                                 "calcular una placa isotrópica plana.")
            if layer.catalog_entry is not None:
                _eligible_entry(layer.catalog_entry)
    warnings = [
        "Modelo exploratorio de placas isotrópicas delgadas e infinitas y cámaras selladas; "
        "no equivale al algoritmo INSUL ni dispone de validación experimental completa.",
        "Capas de cada panel solidarias en desplazamiento pero sin unión compuesta: "
        "masas y rigideces de flexión individuales se suman. No modela laminados adheridos.",
        "Anchura y altura se conservan como geometría de proyecto; no modifican la curva "
        "del modelo infinito ni incluyen modos finitos o condiciones de borde.",
        "Se calcula transmisión aérea del elemento; se excluyen flancos, uniones "
        "y aislamiento entre recintos (ISO 12354).",
        "Integración energética dentro de tercios de octava y, en campo difuso, "
        "sobre los ángulos de incidencia. La convergencia numérica no es exactitud experimental.",
        "Masa superficial indicada: suma de las hojas sólidas; no incluye estructura "
        "ni masa del absorbente de cámara.",
    ]
    gaps = []
    for index, cavity in enumerate(project.cavities, start=1):
        if cavity.frame_type != "independent":
            raise ValueError(f"Cámara {index}: el modelo de puentes estructurales para "
                             f"{cavity.frame_type!r} no está disponible. Seleccione hojas "
                             "independientes solo si corresponde al sistema real.")
        thickness = cavity.absorber_thickness_mm
        sigma = cavity.flow_resistivity_pa_s_m2
        if cavity.absorber is not None and thickness == 0:
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
        gaps.append(Gap(cavity.depth_mm / 1000, sigma, thickness / 1000))
    if project.cavities:
        warnings.append("Las dimensiones de montantes son metadatos: las hojas se consideran "
                        "mecánicamente independientes. f₀ es un diagnóstico de masas/muelles "
                        "de aire, sin rigidez de placa ni corrección del relleno.")
    if project.element_type in ("floor", "ceiling", "roof"):
        warnings.append("La orientación es una etiqueta geométrica para transmisión aérea; "
                        "no se predice impacto, IIC, Ln,w, L'nT,w ni lluvia.")
    plates = tuple(_plate(panel) for panel in project.panels)
    frequencies = tuple(float(value) for value in NOMINAL_BANDS_HZ)
    with python_warnings.catch_warnings(record=True) as emitted:
        python_warnings.simplefilter("always", MikiExtrapolationWarning)
        cancellation = {} if cancel_event is None else {"cancel_event": cancel_event}
        tl = predict_multilayer(
            plates, tuple(gaps), frequencies_hz=frequencies,
            air_density=project.air_density_kg_m3, sound_speed=project.sound_speed_m_s,
            incidence=project.incidence, angle_limit_deg=project.limiting_angle_deg,
            **cancellation,
        )
    # The solver checks exact band edges, including the open empirical limits;
    # persist the warning in reports instead of losing it to console output.
    for warning in emitted:
        if issubclass(warning.category, MikiExtrapolationWarning):
            warnings.append(f"Extrapolación Miki (0.01 < f/σ < 1): {warning.message}")
        else:
            python_warnings.warn(str(warning.message), warning.category, stacklevel=2)
    leak = project.leak_percentage / 100
    if leak:
        tl = -10 * np.log10((1 - leak) * np.power(10.0, -tl / 10) + leak)
        warnings.append("Fuga ideal de área abierta: mezcla energética con transmisión unitaria; "
                        "no incluye difracción, geometría de rendija ni resonancias de abertura.")
    rw = None
    if project.incidence == "diffuse":
        selected = [float(value) for frequency, value in zip(frequencies, tl, strict=True)
                    if frequency in ISO717_FREQUENCIES_HZ]
        rw = iso717_rw(ISO717_FREQUENCIES_HZ, selected).rw_db
        warnings.append("Rw orientativo calculado con 100–3150 Hz mediante ISO 717-1; "
                        "procedimiento provisional pendiente de revisión normativa. "
                        "No constituye un ensayo ni una certificación.")
    else:
        warnings.append("Incidencia normal: no se asigna Rw a esta curva.")
    warnings.extend(_source_warnings(project))
    critical = tuple(project.sound_speed_m_s**2 / (2 * math.pi)
                     * math.sqrt(plate.mass_kg_m2 / plate.bending_stiffness_nm) for plate in plates)
    total_thickness = sum(layer.count * layer.thickness_mm for panel in project.panels
                          for layer in panel.layers) + sum(gap.depth_mm for gap in project.cavities)
    return AssemblyPrediction(
        project, frequencies, tuple(float(value) for value in tl), rw,
        sum(plate.mass_kg_m2 for plate in plates), total_thickness,
        critical, _resonances(plates, project), tuple(dict.fromkeys(warnings)), MODEL_ID,
    )


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
        data["absorber"] = None if cavity.absorber is None else entry_to_dict(cavity.absorber)
        result["cavities"].append(data)
    result["floor_cover"] = None if project.floor_cover is None else entry_to_dict(project.floor_cover)
    return result


def _object(data: Any, cls: type) -> dict:
    if not isinstance(data, dict) or set(data) != {field.name for field in fields(cls)}:
        raise ValueError(f"{cls.__name__}: campos faltantes o desconocidos en el proyecto.")
    return dict(data)


def _list(data: Any, name: str) -> list:
    if not isinstance(data, list):
        raise ValueError(f"{name}: se requiere una lista JSON.")
    return data


def project_from_dict(data: dict) -> AssemblyProject:
    """Strict typed decoding, without applying defaults to missing saved fields."""
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
        if cavity["absorber"] is not None:
            cavity["absorber"] = entry_from_dict(cavity["absorber"])
        cavities.append(Cavity(**cavity))
    result["cavities"] = tuple(cavities)
    if result["floor_cover"] is not None:
        result["floor_cover"] = entry_from_dict(result["floor_cover"])
    return AssemblyProject(**result)


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
    snapshot = project_to_dict(project)
    project_from_dict(snapshot)
    payload = {"schema_version": PROJECT_SCHEMA_VERSION, "model_name": MODEL_ID, "project": snapshot}
    encoded = json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    if len(encoded.encode("utf-8")) > _MAX_BYTES:
        raise ValueError("El proyecto supera el límite de 32 MiB.")
    _atomic_write(path, encoded)


def load_assembly(path: str | Path) -> AssemblyProject:
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
        return migrate_legacy_project(load_project(path))
    if (set(payload) != {"schema_version", "model_name", "project"}
            or payload["schema_version"] != PROJECT_SCHEMA_VERSION or payload["model_name"] != MODEL_ID):
        raise ValueError("Versión de esquema o modelo no compatible, o campos desconocidos.")
    return project_from_dict(payload["project"])


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
        notes="Migrado desde V1. La curva V2 usa rigidez/coincidencia e integración por banda "
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
        for name in ("total_mass_kg_m2", "total_thickness_mm"):
            finite_number(getattr(item, name), name, positive=True)
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
        parts.append(f"<p>Rw: {rw} · Masa de hojas: {item.total_mass_kg_m2:g} kg/m² · "
                     f"Espesor total: {item.total_thickness_mm:g} mm</p>")
        parts.append("<table><thead><tr><th>Panel / capa</th><th>Producto</th><th>Cantidad</th>"
                     "<th>Espesor unitario (mm)</th><th>Densidad (kg/m³)</th></tr></thead><tbody>")
        for panel in item.project.panels:
            for layer in panel.layers:
                parts.append(f"<tr><td>{escape(panel.name)}</td><td>{escape(layer.name)}</td>"
                             f"<td>{layer.count}</td><td>{layer.thickness_mm:g}</td>"
                             f"<td>{layer.density_kg_m3:g}</td></tr>")
        parts.append("</tbody></table><h3>Alcance y limitaciones</h3><ul>")
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
