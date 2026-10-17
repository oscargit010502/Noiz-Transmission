"""Lossless field import and strict local persistence for user-supplied XML.

In the inspected INSUL 9.0/22, 10.0/7 and 10.0/8 XML formats lengths are metres, density kg/m³,
and Young's modulus Pa (the desktop displays mm and GPa). SideA is the
physical panel only for Isotropic entries. Other material types may contain
several active constituents; their raw fields are retained without inventing
an equivalent homogeneous plate. Absorption/Properties/Damping has no
documented dimension here and is deliberately NOT a structural loss factor.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import math
import os
import re
import tempfile
import unicodedata
import xml.etree.ElementTree as ET
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, fields
from pathlib import Path
from urllib.parse import urlsplit

CATALOG_KINDS = (
    "material", "profile", "glazing", "floor_cover", "absorption", "core", "stud", "connection",
)
_ROOTS = {
    "InsulMaterials": ("material", "Material"),
    "InsulProfiles": ("profile", "Profile"),
    "InsulGlazing": ("glazing", "Glazing"),
    "InsulFloorCover": ("floor_cover", "FloorCover"),
    "InsulAbsorption": ("absorption", "Absorption"),
    "InsulCore": ("core", "Material"),
    "InsulStuds": ("stud", "Stud"),
    "InsulStud": ("stud", "Stud"),
    "InsulConnections": ("connection", "Connection"),
}
_MAX_BYTES = 32 * 1024 * 1024
_INSPECTED_SCHEMAS = frozenset({("9.0", "22"), ("10.0", "7"), ("10.0", "8")})
_INVALID_XML_CONTROLS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_NUMERIC_FIELDS = frozenset({
    "Density", "YoungsModulus", "Damping", "Thickness", "PoissonsRatio", "Plateau",
    "OrthotropicRatio", "OrthotropicRatioZY", "AnisotropicRatio", "RibL", "RibH",
    "RibW", "RibV", "ElasticModulus", "UnderlayDensity", "UnderlayThickness",
    "UnderlayElasticModulus", "UnderlayDamping", "UnderlayOrthotropicRatio",
    "UnderlayPoissonsRatio", "Colour", "Texture", "UnderlayColour", "UnderlayTexture",
    "StudDepth", "StudWidth", "StudSpacing", "MaterialThickness",
    "CavityWidth", "definedStudSpacing", "braceSpacing", "Connection",
})
_ALIASES = {
    "Density": "density_kg_m3", "Thickness": "thickness_m",
    "YoungsModulus": "young_modulus_pa", "Damping": "loss_factor",
    "PoissonsRatio": "poisson_ratio", "AnisotropicRatio": "anisotropic_ratio",
    "OrthotropicRatio": "orthotropic_ratio", "OrthotropicRatioZY": "orthotropic_ratio_zy",
}
PropertyValue = float | str | bool | None


@dataclass(frozen=True)
class CatalogEntry:
    id: str
    kind: str
    name: str
    category: str
    manufacturer: str
    countries: tuple[str, ...]
    properties: dict[str, PropertyValue]
    raw_fields: dict[str, str]
    source_file: str
    source_sha256: str
    original_id: str
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for key in ("id", "kind", "name", "category", "manufacturer", "source_file",
                    "source_sha256", "original_id"):
            if not isinstance(getattr(self, key), str):
                raise ValueError(f"{key}: se requiere texto.")
        if not self.id.strip() or not self.name.strip() or self.kind not in CATALOG_KINDS:
            raise ValueError("Identificador, nombre o familia de catálogo inválidos.")
        if not re.fullmatch(r"[0-9a-f]{64}", self.source_sha256):
            raise ValueError("La procedencia requiere un SHA-256 hexadecimal de 64 caracteres.")
        for key in ("countries", "warnings"):
            value = getattr(self, key)
            if not isinstance(value, tuple) or any(not isinstance(v, str) for v in value):
                raise ValueError(f"{key}: se requiere una tupla de textos.")
        if not isinstance(self.raw_fields, dict) or any(
            not isinstance(k, str) or not isinstance(v, str) for k, v in self.raw_fields.items()
        ):
            raise ValueError("raw_fields debe conservar claves y valores de texto.")
        if not isinstance(self.properties, dict):
            raise ValueError("properties debe ser un objeto.")
        for key, value in self.properties.items():
            if not isinstance(key, str) or type(value) not in (str, float, int, bool, type(None)):
                raise ValueError("Propiedad de catálogo inválida.")
            if type(value) in (int, float):
                try:
                    finite = math.isfinite(value)
                except OverflowError:
                    finite = False
                if not finite:
                    raise ValueError("Las propiedades numéricas deben ser finitas.")
        # Break references to caller-owned dictionaries at construction.
        object.__setattr__(self, "properties", dict(self.properties))
        object.__setattr__(self, "raw_fields", dict(self.raw_fields))


@dataclass(frozen=True)
class ImportResult:
    entries: tuple[CatalogEntry, ...]
    warnings: tuple[str, ...]
    source_file: str
    source_sha256: str


@dataclass(frozen=True)
class CatalogSpectrum:
    """Imported dB curve with its claim, never a verified laboratory result.

    ``impact_sound_reduction`` is the floor covering improvement ΔL, not the
    impact level Ln of a complete floor. Values retain the source band labels;
    no missing bands are interpolated and no weighting is applied here.
    """

    frequencies_hz: tuple[float, ...]
    values_db: tuple[float, ...]
    quantity: str
    unit: str
    source: str
    lab_claimed: bool
    verified: bool
    cover_type: str
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class CatalogReference:
    """A source-declared web address, not independently verified documentation."""

    field: str
    url: str


def safe_reference_url(value: str) -> str | None:
    """Accept explicit HTTP(S) addresses only; never execute source-supplied schemes."""
    if not isinstance(value, str) or not value or any(
        character.isspace() or ord(character) < 32 or ord(character) == 127
        or character in '\\<>"\''
        for character in value
    ):
        return None
    try:
        parts = urlsplit(value)
        if (parts.scheme.lower() not in ("http", "https") or not parts.hostname
                or parts.username is not None or parts.password is not None):
            return None
        # Accessing port also rejects malformed/out-of-range numeric ports.
        if parts.port is not None and not 1 <= parts.port <= 65535:
            return None
        hostname = parts.hostname.encode("idna").decode("ascii")
        if ":" in hostname:
            ipaddress.IPv6Address(hostname)
        elif not all(re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?", label)
                     for label in hostname.rstrip(".").split(".")):
            return None
    except (ValueError, UnicodeError):
        return None
    return value


def catalog_references(entry: CatalogEntry) -> tuple[CatalogReference, ...]:
    """Expose addresses in source fields without fetching or inferring manufacturer URLs.

    The document namespace is metadata, not a product reference. Raw fields remain
    unchanged, including malformed URLs; only usable web addresses become links.
    """
    references = []
    seen: set[tuple[str, str]] = set()
    for field, value in entry.raw_fields.items():
        if field.startswith("$document/"):
            continue
        # Full-field URLs retain valid trailing punctuation in filenames. Embedded
        # prose links stop at whitespace/markup; sentence punctuation is trimmed.
        candidates = [value] if safe_reference_url(value) else [
            match.rstrip(".,;)") for match in re.findall(r"https?://[^\s<>\"']+", value)
        ]
        for candidate in candidates:
            if safe_reference_url(candidate) and (field, candidate) not in seen:
                references.append(CatalogReference(field, candidate))
                seen.add((field, candidate))
    return tuple(references)


class _SafeTreeBuilder(ET.TreeBuilder):
    def __init__(self) -> None:
        super().__init__()
        self.depth = 0
        self.nodes = 0

    def doctype(self, name: str, pubid: str | None, system: str | None) -> None:
        raise ValueError("XML con DTD o entidades no permitido.")

    def start(self, tag: str, attrs: dict[str, str]) -> ET.Element:
        self.depth += 1
        self.nodes += 1
        if self.depth > 64 or self.nodes > 500_000:
            raise ValueError("XML excede los límites de profundidad o número de elementos.")
        return super().start(tag, attrs)

    def end(self, tag: str) -> ET.Element:
        self.depth -= 1
        return super().end(tag)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _flatten(element: ET.Element, namespace: str) -> dict[str, str]:
    """Preserve leaves, attributes, repeated nodes and unexpected namespaced fields."""
    result: dict[str, str] = {}

    def name(tag: str) -> str:
        return tag.removeprefix(namespace) if tag.startswith(namespace) else tag

    def walk(node: ET.Element, path: str) -> None:
        for attr, value in node.attrib.items():
            result[f"{path}/@{name(attr)}".lstrip("/")] = value
        if not len(node):
            result[path] = node.text or ""
        elif node.text and node.text.strip():
            result[f"{path}/text()".lstrip("/")] = node.text
        totals = Counter(child.tag for child in node)
        counts: Counter[str] = Counter()
        for child in node:
            counts[child.tag] += 1
            suffix = f"[{counts[child.tag]}]" if totals[child.tag] > 1 else ""
            walk(child, f"{path}/{name(child.tag)}{suffix}".lstrip("/"))

    walk(element, "")
    return result


def _number(text: str, field: str, warnings: list[str]) -> float | None:
    try:
        value = float(text)
    except (ValueError, OverflowError):
        warnings.append(f"{field}: valor numérico vacío o inválido; se conserva el texto original.")
        return None
    if not math.isfinite(value):
        warnings.append(f"{field}: valor no finito; se conserva el texto original.")
        return None
    return value


def _properties(raw: dict[str, str], kind: str, warnings: list[str]) -> dict[str, PropertyValue]:
    props: dict[str, PropertyValue] = {
        "material_type": raw.get("Type", "").strip(),
        "source_version": raw.get("$document/@Version", ""),
        "source_release": raw.get("$document/@Release", ""),
        "measurement_verified": False,
        "source_guid": raw.get("GUID", "").strip(),
    }
    for path, text in raw.items():
        field = path.rsplit("/", 1)[-1]
        if field in _NUMERIC_FIELDS or re.fullmatch(r"Hz\d+(?:\.\d+)?", field):
            props[path] = _number(text, path, warnings)
    section = {"material": "SideA", "glazing": "SideA", "core": "Core",
               "floor_cover": "Properties", "absorption": "Properties"}.get(kind)
    if section:
        for original, target in _ALIASES.items():
            key = f"{section}/{original}"
            if key in raw:
                if kind == "absorption" and original == "Damping":
                    target = "damping_raw"
                props[target] = props.get(key)
        for key in ("density_kg_m3", "thickness_m", "young_modulus_pa"):
            value = props.get(key)
            if isinstance(value, (int, float)) and value <= 0:
                warnings.append(f"{key}: valor no positivo; no apto para una placa física.")
    props["archived"] = raw.get("Archived", "0").strip() in ("-1", "1", "True", "true")
    props["all_regions"] = raw.get("Region/AllRegions", "0").strip() in (
        "-1", "1", "True", "true",
    )
    source = raw.get("Measurement/Source", raw.get("IsolationGain/Source", "")).strip()
    props["measurement_source"] = source
    if any(p.startswith(("Measurement/", "IsolationGain/")) for p in raw):
        warnings.append(
            "Espectro importado sin verificación documental; no se considera un ensayo validado."
        )
        if source.casefold() in ("", "xxx"):
            warnings.append("La referencia de medición está vacía o contiene el marcador XXX.")
    if kind == "absorption":
        warnings.append(
            "Damping del absorbente se conserva sin asignar resistividad ni factor de pérdidas."
        )
    if kind in ("material", "glazing") and props["material_type"] != "Isotropic":
        warnings.append(
            "Tipo compuesto, perfilado o anisótropo: no sustituir por una placa homogénea SideA."
        )
    if kind in ("stud", "connection"):
        for original, target in (
            ("StudDepth", "stud_depth_m"), ("StudWidth", "stud_width_m"),
            ("StudSpacing", "stud_spacing_m"), ("MaterialThickness", "material_thickness_m"),
        ):
            if (path := f"Properties/{original}") in raw:
                props[target] = props.get(path)
                value = props[target]
                if type(value) in (int, float) and value <= 0:
                    warnings.append(f"{target}: dimensión no positiva; revisar antes de usar.")
        props["frame_material"] = {
            "MetalFrame": "metal", "TimberFrame": "timber", "MasonryFrame": "masonry",
        }.get(raw.get("Category", "").strip(), "unknown")
        props["structural_model_verified"] = False
        warnings.append(
            "Las dimensiones del montante no definen su transmisión estructural ni una unión."
        )
    if kind == "connection":
        for original, target in (
            ("CavityWidth", "cavity_width_m"),
            ("definedStudSpacing", "defined_stud_spacing_m"),
            ("braceSpacing", "brace_spacing_m"),
            ("Connection", "connection_code"),
        ):
            if (path := f"Properties/{original}") in raw:
                props[target] = props.get(path)
        for path, target in (
            ("Properties/useDefinedStudSpacing", "stud_spacing_defined"),
            ("Properties/useDefinedStudSpacing/@isSpacingFixed", "stud_spacing_fixed"),
            ("Properties/noAbsorption", "no_absorption_declared"),
        ):
            text = raw.get(path, "0").strip().casefold()
            props[target] = text in ("-1", "1", "true")
            if text not in ("-1", "0", "1", "true", "false", ""):
                warnings.append(f"{path}: bandera no reconocida; se conserva el original.")
        props["geometry_verified"] = False
        warnings.append(
            "La conexión conserva dimensiones y código de origen; el código no define "
            "la geometría de clips, rieles ni herrajes del fabricante."
        )
    if kind == "floor_cover":
        props["cover_type"] = raw.get("CoverType", "").strip()
        props["spectrum_quantity"] = "impact_sound_reduction"
        props["spectrum_unit"] = "dB"
    positive = all(type(props.get(k)) in (float, int) and props[k] > 0
                   for k in ("density_kg_m3", "thickness_m", "young_modulus_pa"))
    poisson = props.get("poisson_ratio")
    loss = props.get("loss_factor")
    if kind in ("material", "glazing"):
        if type(poisson) in (float, int) and not -1 < poisson < 0.5:
            warnings.append("Poisson fuera del intervalo físico (-1, 0.5).")
        if type(loss) in (float, int) and loss < 0:
            warnings.append("Factor de pérdidas negativo; no apto para cálculo.")
        if any(props.get(k, 1) != 1 for k in (
            "anisotropic_ratio", "orthotropic_ratio", "orthotropic_ratio_zy",
        )):
            warnings.append("Razón anisótropa distinta de 1; revisar antes del modelo isótropo.")
    props["units_schema_verified"] = (
        (props["source_version"], props["source_release"]) in _INSPECTED_SCHEMAS
        and (kind not in ("stud", "connection") or props["source_version"] == "10.0")
    )
    props["solid_model_eligible"] = bool(
        kind in ("material", "glazing") and props["material_type"] == "Isotropic"
        and raw.get("Name", "").strip() and props["units_schema_verified"]
        and positive and type(poisson) in (float, int) and -1 < poisson < 0.5
        and type(loss) in (float, int) and loss >= 0
        and all(props.get(k, 1) == 1 for k in (
            "anisotropic_ratio", "orthotropic_ratio", "orthotropic_ratio_zy",
        ))
    )
    return props


def _parse_xml(data: bytes, repair_invalid_controls: bool) -> tuple[ET.Element, bool]:
    """Audited recovery only for illegal control characters in record names.

    The supplied V10 absorption file contains U+0001 in one product name.
    Recovery preserves that original character in raw_fields, hashes the
    untouched input, and substitutes a visible replacement only in the display
    name. It cannot repair markup, numeric properties, entities or namespaces.
    """
    try:
        return ET.fromstring(data, parser=ET.XMLParser(target=_SafeTreeBuilder())), False
    except ET.ParseError:
        if not repair_invalid_controls:
            raise
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("La reparación de controles solo admite XML UTF-8.") from exc
    controls = _INVALID_XML_CONTROLS.findall(text)
    if not controls:
        raise ValueError("El XML es inválido y no contiene controles de nombre reparables.")
    prefix = "__NOIZ_CONTROL_"
    while prefix in text:
        prefix += "_"
    substitutions: dict[str, str] = {}

    def substitute(match: re.Match) -> str:
        token = f"{prefix}{len(substitutions)}__"
        substitutions[token] = match[0]
        return token

    repaired = _INVALID_XML_CONTROLS.sub(substitute, text)
    root = ET.fromstring(repaired, parser=ET.XMLParser(target=_SafeTreeBuilder()))
    name_nodes = {id(child) for record in root for child in record
                  if child.tag == f"{root.tag.removesuffix(_local(root.tag))}Name"
                  and not len(child)}
    restored = 0
    for node in root.iter():
        if any(prefix in item for item in (node.tag, node.tail or "", *node.attrib,
                                          *node.attrib.values())):
            raise ValueError("Solo se pueden reparar controles en el texto de Name.")
        if prefix in (node.text or ""):
            if id(node) not in name_nodes:
                raise ValueError("Solo se pueden reparar controles en el texto de Name.")
            for token, original in substitutions.items():
                if token in node.text:
                    node.text = node.text.replace(token, original)
                    restored += 1
    if restored != len(controls):
        raise ValueError("No se pudieron conservar todos los controles originales.")
    return root, True


def import_xml(path: str | Path, *, repair_invalid_controls: bool = True) -> ImportResult:
    """Import each record, including blank-name/duplicate rows, retaining provenance.

    Record IDs remain file-content hash + ordinal; explicit ID/GUID is retained
    separately. Neither its namespace nor Lab=True makes an entry verified.
    Name-control recovery is audited and does not change the file. Set
    repair_invalid_controls=False for strict XML 1.0 parsing instead.
    """
    path = Path(path)
    with path.open("rb") as stream:
        data = stream.read(_MAX_BYTES + 1)
    if len(data) > _MAX_BYTES:
        raise ValueError("El XML supera el límite de 32 MiB.")
    try:
        root, repaired_controls = _parse_xml(data, repair_invalid_controls)
    except ET.ParseError as exc:
        raise ValueError(f"XML inválido: {exc}") from exc
    root_name = _local(root.tag)
    if root_name not in _ROOTS:
        raise ValueError(f"Familia XML no reconocida: {root_name}.")
    kind, record_tag = _ROOTS[root_name]
    namespace = root.tag.removesuffix(root_name)
    if namespace not in ("", "{http://www.insul.co.nz}"):
        raise ValueError("Namespace XML no reconocido.")
    if any(child.tag != f"{namespace}{record_tag}" for child in root):
        raise ValueError(f"Se esperaba un registro {record_tag} dentro de {root_name}.")
    sha256 = hashlib.sha256(data).hexdigest()
    source_file = path.name
    entries = []
    names = Counter((child.findtext(f"{namespace}Name") or "").strip() for child in root)
    for index, node in enumerate(root, 1):
        raw = _flatten(node, namespace)
        raw.update({f"$document/@{k}": v for k, v in root.attrib.items()})
        raw["$document/root"] = root_name
        raw["$document/namespace"] = namespace.strip("{}")
        warnings: list[str] = []
        original_id = (raw.get("@ID") or raw.get("ID") or raw.get("GUID")
                       or f"{record_tag}[{index}]")
        original_label = raw.get("Name", "").strip()
        label = original_label
        if _INVALID_XML_CONTROLS.search(raw.get("Name", "")):
            warnings.append(
                "Name contenía un control XML ilegal: se muestra como �; "
                "el texto original se conserva en raw_fields y el archivo no se modifica."
            )
            raw["$import/repaired_fields"] = "Name"
            label = _INVALID_XML_CONTROLS.sub("�", label)
        if not label:
            warnings.append("Nombre vacío en el origen; registro conservado con su ordinal.")
        if names[original_label] > 1:
            warnings.append("Nombre repetido en el archivo; se conserva como registro independiente.")
        name = label or f"Sin nombre · {record_tag} {index}"
        countries = []
        for key, text in raw.items():
            if key.startswith("Region/") and key not in ("Region/Custom", "Region/AllRegions"):
                if text.strip() in ("-1", "1", "True", "true"):
                    countries.append(key.removeprefix("Region/"))
                elif text.strip() not in ("0", "False", "false", ""):
                    warnings.append(f"{key}: bandera regional desconocida {text!r}.")
        properties = _properties(raw, kind, warnings)
        entries.append(CatalogEntry(
            id=f"xml:{sha256}:{index}", kind=kind, name=name,
            category=raw.get("Category", "").strip(),
            manufacturer=raw.get("Manufacturer", "").strip(), countries=tuple(countries),
            properties=properties, raw_fields=raw, source_file=source_file,
            source_sha256=sha256, original_id=original_id, warnings=tuple(warnings),
        ))
    summary = [
        "Datos del usuario; importación no equivale a validación científica ni licencia de redistribución."
    ]
    if repaired_controls:
        summary.append("Se repararon controles ilegales únicamente para mostrar nombres; "
                       "SHA-256 y campos originales conservados.")
    if (root.attrib.get("Version"), root.attrib.get("Release")) not in _INSPECTED_SCHEMAS:
        summary.append("Versión XML distinta de los esquemas inspeccionados 9.0/22, 10.0/7 y 10.0/8; "
                       "revisar unidades.")
    if not entries:
        summary.append("Archivo válido sin registros.")
    summary.append(f"{sum(bool(entry.warnings) for entry in entries)} registros con observaciones.")
    return ImportResult(tuple(entries), tuple(summary), source_file, sha256)


def catalog_spectrum(entry: CatalogEntry) -> CatalogSpectrum | None:
    """Read the imported curve without promoting source flags to evidence.

    Floor-cover curves describe ΔL on the stated base floor. Material/glazing
    ``Measurement`` curves are R/TL; other record families have no interpreted
    dB spectrum. Malformed or duplicate frequency values are omitted with an
    observation, retaining the original fields in the entry.
    """
    if entry.kind == "floor_cover":
        section, quantity = "IsolationGain", "impact_sound_reduction"
    elif entry.kind in ("material", "glazing"):
        section, quantity = "Measurement", "sound_reduction_index"
    else:
        return None
    raw = entry.raw_fields
    prefix = f"{section}/Data/"
    if not any(path.startswith(prefix) for path in raw):
        return None
    observations = [
        "Curva importada sin informe de ensayo verificado; no usar como validación experimental."
    ]
    points: dict[float, float] = {}
    seen_frequencies: set[float] = set()
    for path, value in raw.items():
        if not path.startswith(prefix):
            continue
        match = re.fullmatch(r"Hz(\d+(?:\.\d+)?)(?:\[\d+\])?", path.removeprefix(prefix))
        if match is None:
            observations.append(f"{path}: etiqueta de banda no reconocida; se omite.")
            continue
        frequency = float(match[1])
        if frequency in seen_frequencies:
            points.pop(frequency, None)
            observations.append(f"{frequency:g} Hz: banda repetida; se omite por ambigüedad.")
            continue
        seen_frequencies.add(frequency)
        level = _number(value, path, observations)
        if frequency <= 0 or not math.isfinite(frequency) or level is None:
            observations.append(f"{path}: punto inválido; se omite.")
            continue
        points[frequency] = level
    source = raw.get(f"{section}/Source", "").strip()
    if source.casefold() in ("", "xxx", "measured"):
        observations.append("La etiqueta de origen no identifica un informe de laboratorio.")
    if points and len(set(points.values())) == 1:
        observations.append("Curva constante; comprobar si contiene valores de relleno.")
    if not entry.properties.get("units_schema_verified", False):
        observations.append("Versión XML sin unidades verificadas; revisar la interpretación dB.")
    frequencies = tuple(sorted(points))
    return CatalogSpectrum(
        frequencies_hz=frequencies, values_db=tuple(points[f] for f in frequencies),
        quantity=quantity, unit="dB", source=source,
        lab_claimed=raw.get(f"{section}/Lab", "").strip().casefold() in ("true", "1", "-1"),
        verified=False, cover_type=raw.get("CoverType", "").strip(), warnings=tuple(observations),
    )


def entry_to_dict(entry: CatalogEntry) -> dict:
    """JSON snapshot with independent mutable containers."""
    return {
        field.name: (dict(value) if isinstance(value, dict)
                     else list(value) if isinstance(value, tuple) else value)
        for field in fields(CatalogEntry)
        for value in (getattr(entry, field.name),)
    }


def entry_from_dict(data: dict) -> CatalogEntry:
    if not isinstance(data, dict) or set(data) != {f.name for f in fields(CatalogEntry)}:
        raise ValueError("Esquema de registro de catálogo inválido.")
    copied = dict(data)
    for key in ("countries", "warnings"):
        if not isinstance(data[key], list):
            raise ValueError(f"{key}: se requiere una lista JSON.")
        copied[key] = tuple(data[key])
    return CatalogEntry(**copied)


def _strict_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Clave JSON repetida: {key}.")
        result[key] = value
    return result


def _invalid_constant(value: str) -> None:
    raise ValueError(f"Número JSON no finito: {value}.")


def load_catalog(path: str | Path) -> tuple[CatalogEntry, ...]:
    path = Path(path)
    if not path.exists():
        return ()
    with path.open("rb") as stream:
        data = stream.read(_MAX_BYTES + 1)
    if len(data) > _MAX_BYTES:
        raise ValueError("El catálogo supera el límite de 32 MiB.")
    try:
        content = json.loads(data, object_pairs_hook=_strict_object, parse_constant=_invalid_constant)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(f"Catálogo JSON inválido: {exc}") from exc
    if (not isinstance(content, dict) or set(content) != {"schema_version", "entries"}
            or type(content["schema_version"]) is not int or content["schema_version"] != 1
            or not isinstance(content["entries"], list)):
        raise ValueError("Esquema o versión del catálogo no admitidos.")
    entries = tuple(entry_from_dict(value) for value in content["entries"])
    if len({e.id for e in entries}) != len(entries):
        raise ValueError("El catálogo contiene identificadores repetidos.")
    return entries


def save_catalog(entries: Iterable[CatalogEntry], path: str | Path) -> None:
    """Replace atomically: failed serialization leaves the existing library intact."""
    entries = tuple(entries)
    if any(not isinstance(entry, CatalogEntry) for entry in entries):
        raise ValueError("Todos los elementos deben ser registros del catálogo.")
    if len({entry.id for entry in entries}) != len(entries):
        raise ValueError("El catálogo contiene identificadores repetidos.")
    # Revalidate snapshots because the frozen dataclass contains mutable dictionaries.
    snapshots = [entry_to_dict(entry) for entry in entries]
    for snapshot in snapshots:
        entry_from_dict(snapshot)
    data = json.dumps({"schema_version": 1, "entries": snapshots}, ensure_ascii=False,
                      allow_nan=False, separators=(",", ":")).encode("utf-8")
    if len(data) > _MAX_BYTES:
        raise ValueError("El catálogo supera el límite de 32 MiB.")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.",
                                         delete=False) as stream:
            temp_path = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()


def merge_catalog(existing: Iterable[CatalogEntry], incoming: Iterable[CatalogEntry]
                  ) -> tuple[CatalogEntry, ...]:
    """Idempotent file reimport; preserve different rows even if names coincide."""
    merged = {entry.id: entry for entry in existing}
    for entry in incoming:
        merged[entry.id] = entry
    return tuple(merged.values())


def _fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text.casefold())
                   if not unicodedata.combining(c))


def search_entries(entries: Iterable[CatalogEntry], query: str = "", kind: str | None = None,
                   category: str | None = None, manufacturer: str | None = None,
                   country: str | None = None) -> tuple[CatalogEntry, ...]:
    words = _fold(query).split()
    result = []
    for entry in entries:
        if any(value is not None and _fold(value) != _fold(getattr(entry, key))
               for key, value in (("kind", kind), ("category", category),
                                  ("manufacturer", manufacturer))):
            continue
        if country is not None and not entry.properties.get("all_regions", False):
            if _fold(country) not in {_fold(c) for c in entry.countries}:
                continue
        haystack = _fold(" ".join((entry.name, entry.category, entry.manufacturer,
                                    *entry.countries)))
        if all(word in haystack for word in words):
            result.append(entry)
    return tuple(result)


def default_catalog_path() -> Path:
    """User library location, overridable for portable installations and tests."""
    if configured := os.environ.get("NOIZ_CATALOG_PATH"):
        return Path(configured).expanduser()
    for filename in ("catalog-v5.json", "catalog-v3.json", "catalog.json"):
        portable = Path.cwd() / "local_data" / filename
        if portable.is_file():
            return portable
    # A source checkout can be launched from elsewhere. Never search above an
    # installed site-packages location: that might capture another environment's data.
    module = Path(__file__).resolve()
    if module.parent.name == "catalog" and module.parents[1].name == "noiz_transmission":
        source = module.parents[2]
        checkout = source.parent
        if source.name == "src" and (checkout / "pyproject.toml").is_file():
            for filename in ("catalog-v5.json", "catalog-v3.json", "catalog.json"):
                portable = checkout / "local_data" / filename
                if portable.is_file():
                    return portable
    if os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
        return root / "NoizTransmission" / "catalog.json"
    root = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))
    return root / "noiz-transmission" / "catalog.json"
