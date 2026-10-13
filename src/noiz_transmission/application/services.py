"""Headless prediction, immutable projects and reproducible report exports."""

import csv
import json
import platform
from collections.abc import Sequence
from dataclasses import asdict, dataclass, fields, replace
from html import escape
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from noiz_transmission import __version__
from noiz_transmission.application.materials import (
    Material,
    catalog_version,
    finite_number,
    list_materials,
    material_from_dict,
    nonempty_string,
    strict_json_loads,
)
from noiz_transmission.core.physics import (
    THIRD_OCTAVE_NOMINAL_HZ,
    critical_frequency,
    mass_law_diffuse_tl,
    mass_law_normal_tl,
    surface_density,
)
from noiz_transmission.core.ratings import iso717_rw

PROJECT_SCHEMA_VERSION = 1
MODEL_VERSION = "mass-law-1"
MODELS = frozenset({"diffuse_mass_law", "normal_mass_law"})


@dataclass(frozen=True)
class Project:
    name: str
    material_id: str
    thickness_mm: float
    model: str = "diffuse_mass_law"
    air_density_kg_m3: float = 1.21
    sound_speed_m_s: float = 343.0
    limiting_angle_deg: float = 78.0
    material_snapshot: Material | None = None
    model_version: str = MODEL_VERSION
    catalog_version: str | None = None

    def __post_init__(self) -> None:
        nonempty_string(self.name, "name")
        nonempty_string(self.material_id, "material_id")
        nonempty_string(self.model, "model")
        if self.model not in MODELS:
            raise ValueError(f"Modelo no compatible: {self.model}.")
        if self.model_version != MODEL_VERSION:
            raise ValueError(f"Versión de modelo no compatible: {self.model_version}.")
        for name in ("thickness_mm", "air_density_kg_m3", "sound_speed_m_s"):
            finite_number(getattr(self, name), name, positive=True)
        angle = finite_number(self.limiting_angle_deg, "limiting_angle_deg", positive=True)
        if angle > 90:
            raise ValueError("limiting_angle_deg debe ser mayor que 0 y menor o igual que 90.")
        if self.catalog_version is not None:
            nonempty_string(self.catalog_version, "catalog_version")
        if self.material_snapshot is not None:
            if not isinstance(self.material_snapshot, Material):
                raise ValueError("material_snapshot debe ser un Material.")
            if self.material_snapshot.id != self.material_id:
                raise ValueError("material_id no coincide con material_snapshot.id.")


@dataclass(frozen=True)
class Prediction:
    project: Project
    frequencies_hz: tuple[float, ...]
    tl_db: tuple[float, ...]
    surface_density_kg_m2: float
    critical_frequency_hz: float
    rw_db: int | None
    warnings: tuple[str, ...]


def _resolve_project(project: Project) -> Project:
    if not isinstance(project, Project):
        raise ValueError("Se requiere un Project válido.")
    if project.material_snapshot is not None:
        return replace(project, catalog_version=project.catalog_version or "user-supplied")
    material = next((item for item in list_materials() if item.id == project.material_id), None)
    if material is None:
        raise ValueError(f"Material desconocido: {project.material_id}.")
    return replace(project, material_snapshot=material, catalog_version=catalog_version())


def predict(project: Project) -> Prediction:
    project = _resolve_project(project)
    material = project.material_snapshot
    assert material is not None
    thickness_m = project.thickness_mm / 1000.0
    mass = surface_density(material.density_kg_m3, thickness_m)
    frequencies = tuple(float(value) for value in THIRD_OCTAVE_NOMINAL_HZ)
    kwargs = {
        "air_density_kg_m3": project.air_density_kg_m3,
        "sound_speed_m_s": project.sound_speed_m_s,
    }
    if project.model == "diffuse_mass_law":
        curve = mass_law_diffuse_tl(
            frequencies, mass, **kwargs, limiting_angle_deg=project.limiting_angle_deg,
        )
    else:
        curve = mass_law_normal_tl(frequencies, mass, **kwargs)
    tl = tuple(float(value) for value in curve)
    critical = critical_frequency(
        material.density_kg_m3, thickness_m, material.young_modulus_pa,
        material.poisson_ratio, sound_speed_m_s=project.sound_speed_m_s,
    )
    warnings = [
        "Modelo exploratorio de ley de masas para una hoja simple, homogénea e infinita. "
        "No incluye rigidez, amortiguamiento, coincidencia, resonancias, puentes, fugas ni flancos.",
        "La frecuencia crítica es un diagnóstico de placa delgada; "
        "la curva no representa la pérdida por coincidencia.",
        "Predicción de un elemento constructivo; no calcula aislamiento entre recintos (ISO 12354).",
        "Valores evaluados en los centros nominales de tercio de octava; "
        "no representan una integración energética dentro de cada banda.",
    ]
    if material.data_status == "synthetic":
        warnings.append("Datos sintéticos de demostración; no caracterizan un producto comercial.")
    warnings.append(f"Incertidumbre de los datos: {material.uncertainty}")
    if project.model == "diffuse_mass_law":
        rw = iso717_rw(frequencies, tl).rw_db
        warnings.append(
            "Rw orientativo calculado sobre una curva teórica con el procedimiento de ISO 717-1; "
            "clasificación provisional pendiente de revisión con la norma primaria. "
            "El resultado no constituye un ensayo, certificación ni validación experimental del modelo."
        )
    else:
        rw = None
        warnings.append("Incidencia normal: no se asigna Rw a esta curva.")
    return Prediction(project, frequencies, tl, float(mass), float(critical), rw, tuple(warnings))


def save_project(project: Project, path: str | Path) -> None:
    """Save a deterministic snapshot containing every physical/model input."""
    resolved = _resolve_project(project)
    payload = {"schema_version": PROJECT_SCHEMA_VERSION, "project": asdict(resolved)}
    Path(path).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def load_project(path: str | Path) -> Project:
    payload = strict_json_loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or set(payload) != {"schema_version", "project"}:
        raise ValueError("El archivo no cumple el esquema de proyecto.")
    if type(payload["schema_version"]) is not int or payload["schema_version"] != 1:
        raise ValueError("Versión de esquema de proyecto no compatible.")
    data = payload["project"]
    if not isinstance(data, dict) or set(data) != {field.name for field in fields(Project)}:
        raise ValueError("El proyecto contiene campos desconocidos o faltantes.")
    data["material_snapshot"] = material_from_dict(data["material_snapshot"])
    nonempty_string(data["catalog_version"], "catalog_version")
    return Project(**data)


def _runtime_versions() -> dict[str, str]:
    versions = {"noiz-transmission": __version__, "python": platform.python_version()}
    for package in ("numpy", "scipy", "phonometry"):
        try:
            versions[package] = version(package)
        except PackageNotFoundError:
            versions[package] = "not-installed"
    return versions


def _report_metadata(prediction: Prediction, index: int) -> dict[str, Any]:
    project = prediction.project
    if project.material_snapshot is None:
        raise ValueError("El resultado no contiene la copia del material utilizado.")
    metadata: dict[str, Any] = {"prediction_index": index}
    metadata.update({
        f"project_{key}": value
        for key, value in asdict(project).items()
        if key != "material_snapshot"
    })
    metadata.update({f"material_{key}": value for key, value in asdict(
        project.material_snapshot,
    ).items()})
    metadata.update({
        "surface_density_kg_m2": prediction.surface_density_kg_m2,
        "critical_frequency_hz": prediction.critical_frequency_hz,
        "rw_db_illustrative": prediction.rw_db,
        "warnings": " | ".join(prediction.warnings),
        "software_versions": json.dumps(_runtime_versions(), sort_keys=True, ensure_ascii=False),
    })
    return metadata


def _checked_predictions(predictions: Sequence[Prediction]) -> tuple[Prediction, ...]:
    items = tuple(predictions)
    if not items:
        raise ValueError("Se requiere al menos una predicción para exportar.")
    for item in items:
        if not isinstance(item, Prediction):
            raise ValueError("Sólo se pueden exportar objetos Prediction.")
        if not item.frequencies_hz or len(item.frequencies_hz) != len(item.tl_db):
            raise ValueError("Frecuencias y valores TL deben tener la misma longitud no vacía.")
    return items


def _csv_safe(value: Any) -> Any:
    # Spreadsheet applications may evaluate formulas even in quoted CSV fields.
    if isinstance(value, str):
        stripped = value.lstrip()
        if (stripped and stripped[0] in "=+-@") or value.startswith(("\t", "\r", "\n")):
            return "'" + value
    return value


def export_csv(predictions: Sequence[Prediction], path: str | Path) -> None:
    """Export one row per curve/band, repeating metadata for independent reuse."""
    items = _checked_predictions(predictions)
    metadata = [_report_metadata(item, index) for index, item in enumerate(items, start=1)]
    columns = [*metadata[0], "frequency_hz", "tl_db"]
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for item, attributes in zip(items, metadata, strict=True):
            for frequency, tl in zip(item.frequencies_hz, item.tl_db, strict=True):
                row = {**attributes, "frequency_hz": frequency, "tl_db": tl}
                writer.writerow({key: _csv_safe(value) for key, value in row.items()})


def export_html(predictions: Sequence[Prediction], path: str | Path) -> None:
    """Write an offline report with escaped labels, inputs and full numerical spectra."""
    items = _checked_predictions(predictions)
    parts = [
        "<!doctype html><html lang='es'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width, initial-scale=1'>",
        "<title>Noiz Transmission — informe exploratorio</title>",
        "<style>body{font:16px system-ui,sans-serif;max-width:1100px;margin:2rem auto;"
        "padding:0 1rem;color:#172b3a}table{border-collapse:collapse;width:100%;margin:1rem 0}"
        "th,td{border:1px solid #b8c6d0;text-align:left;padding:.5rem;overflow-wrap:anywhere}"
        "th{background:#edf3f7}h2{margin-top:2.5rem}li{margin:.5rem 0}"
        "@media print{section{break-before:page}section:first-of-type{break-before:auto}}"
        "</style></head><body><h1>Noiz Transmission</h1>",
        "<p>Informe exploratorio de aislamiento de elementos. "
        "Los valores no sustituyen ensayos ni constituyen una certificación.</p>",
    ]
    for index, item in enumerate(items, start=1):
        metadata = _report_metadata(item, index)
        material = item.project.material_snapshot
        assert material is not None
        model_label = (
            "Ley de masas, incidencia difusa"
            if item.project.model == "diffuse_mass_law"
            else "Ley de masas, incidencia normal"
        )
        summary = {
            "Material": material.name,
            "Espesor": f"{item.project.thickness_mm:g} mm",
            "Modelo": model_label,
            "Masa por unidad de superficie": f"{item.surface_density_kg_m2:g} kg/m²",
            "Frecuencia crítica (diagnóstico)": f"{item.critical_frequency_hz:.2f} Hz",
            "Rw orientativo": "No aplicable" if item.rw_db is None else f"{item.rw_db} dB",
        }
        parts.append(f"<section><h2>{index}. {escape(item.project.name)}</h2><table><tbody>")
        for key, value in summary.items():
            parts.append(f"<tr><th>{escape(key)}</th><td>{escape(value)}</td></tr>")
        parts.append("</tbody></table><h3>Alcance y limitaciones</h3><ul>")
        parts.extend(f"<li>{escape(warning)}</li>" for warning in item.warnings)
        parts.append(
            "</ul><details><summary>Entradas, procedencia y versiones para reproducibilidad</summary>"
            "<table><tbody>"
        )
        for key, value in metadata.items():
            if key == "warnings":
                continue
            display = "No aplicable" if value is None else str(value)
            parts.append(f"<tr><th>{escape(key)}</th><td>{escape(display)}</td></tr>")
        parts.append(
            "</tbody></table></details><h3>Espectro de pérdida de transmisión</h3>"
            "<table><thead><tr><th>Frecuencia (Hz)</th><th>TL (dB)</th></tr>"
            "</thead><tbody>"
        )
        for frequency, tl in zip(item.frequencies_hz, item.tl_db, strict=True):
            parts.append(f"<tr><td>{frequency:.17g}</td><td>{tl:.17g}</td></tr>")
        parts.append("</tbody></table></section>")
    parts.append("</body></html>\n")
    Path(path).write_text("\n".join(parts), encoding="utf-8")
