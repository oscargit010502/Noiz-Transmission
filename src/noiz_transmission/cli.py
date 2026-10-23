"""Headless, reproducible workflows; never imports Qt."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import tempfile
from collections import Counter
from dataclasses import asdict
from importlib.metadata import version
from pathlib import Path

from noiz_transmission import __version__
from noiz_transmission.application.assembly_services import (
    PROJECT_SCHEMA_VERSION,
    export_assembly_csv,
    export_assembly_html,
    load_assembly,
    predict_assembly,
)
from noiz_transmission.application.services import (
    export_csv,
    export_html,
    list_materials,
    load_project,
    predict,
)
from noiz_transmission.catalog import (
    default_catalog_path,
    import_xml,
    load_application_catalog,
    load_catalog,
    merge_catalog,
    save_catalog,
)
from noiz_transmission.core.ratings import STC_PROCEDURE
from noiz_transmission.core.transfer import NumericalConvergenceError


def _software() -> dict[str, str]:
    return {
        "noiz_transmission": __version__, "python": platform.python_version(),
        "numpy": version("numpy"), "scipy": version("scipy"),
    }


def _write_result(path: Path, text: str) -> None:
    """An interrupted result write must not truncate an existing JSON report."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="", dir=path.parent,
                                         prefix=f".{path.name}.", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _assembly(args: argparse.Namespace) -> int:
    # Resolve all projects and calculate all curves before producing any output.
    predictions = tuple(predict_assembly(load_assembly(path)) for path in args.projects)
    payload = {
        "schema_version": PROJECT_SCHEMA_VERSION, "software": _software(),
        "predictions": [{**asdict(result), "stc_db": result.stc_db,
                         "stc_procedure": STC_PROCEDURE if result.stc_db is not None else None}
                        for result in predictions],
    }
    result_json = json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    _publish_assembly(predictions, args.output_dir, result_json)
    for result in predictions:
        rating = f"Rw orientativo {result.rw_db} dB" if result.rw_db is not None else "sin Rw"
        mass = ("masa no inferida" if result.project.element_type == "porous" else
                f"{result.total_mass_kg_m2:g} kg/m²")
        print(f"{result.project.name}: {mass} · "
              f"{result.total_thickness_mm:g} mm · {rating}")
    print(f"Resultados: {args.output_dir}")
    print("Modelo exploratorio de transmisión aérea. "
          "Consultar las hipótesis, procedencia y limitaciones del informe.")
    return 0


def _publish_assembly(predictions, output: Path, result_json: str) -> None:
    """Stage complete reports, then roll back replacements if publication fails.

    Only these three owned report paths are replaced; other user files survive.
    Recoverable write failures cannot leave reports from different calculations.
    """
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".noiz-reports-", dir=output.parent))
    cleanup = True
    created_output = not output.exists()
    names = ("spectra.csv", "report.html", "result.json")
    published, backed_up = [], []
    try:
        export_assembly_csv(predictions, staging / "spectra.csv")
        export_assembly_html(predictions, staging / "report.html")
        _write_result(staging / "result.json", result_json)
        output.mkdir(parents=True, exist_ok=True)
        for name in names:
            target = output / name
            if target.exists() and not target.is_file():
                raise OSError(f"El destino del informe no es un archivo: {target}")
        backup = staging / "previous"
        backup.mkdir()
        try:
            for name in names:
                target = output / name
                if target.exists() or target.is_symlink():
                    os.replace(target, backup / name)
                    backed_up.append(name)
                os.replace(staging / name, target)
                published.append(name)
        except BaseException as original:
            recovery_errors = []
            for name in reversed(published):
                try:
                    (output / name).unlink(missing_ok=True)
                except OSError as exc:
                    recovery_errors.append(str(exc))
            for name in backed_up:
                try:
                    os.replace(backup / name, output / name)
                except OSError as exc:
                    recovery_errors.append(str(exc))
            if recovery_errors:
                # Never erase the only remaining copy if the filesystem also
                # refuses recovery; tell the caller where backups are retained.
                cleanup = False
                raise OSError(f"Falló la recuperación de informes. Copias conservadas en "
                              f"{staging}: {'; '.join(recovery_errors)}") from original
            raise
    finally:
        if cleanup:
            shutil.rmtree(staging)
        if created_output and output.is_dir() and not any(output.iterdir()):
            output.rmdir()


def _catalog(args: argparse.Namespace) -> int:
    if args.catalog_command == "list":
        path = args.input or default_catalog_path()
        entries = load_catalog(path) if args.input else load_application_catalog()
        print(json.dumps({
            "path": str(path), "entry_count": len(entries),
            "kinds": dict(sorted(Counter(entry.kind for entry in entries).items())),
            "source_files": sorted({entry.source_file for entry in entries}),
        }, ensure_ascii=False, indent=2))
        return 0
    destination = args.output or default_catalog_path()
    # Parsing or validation failure in any file leaves the existing library intact.
    imports = tuple(import_xml(path) for path in args.files)
    existing = load_catalog(destination)
    merged = existing
    for result in imports:
        merged = merge_catalog(merged, result.entries)
    save_catalog(merged, destination)
    for result in imports:
        print(f"{result.source_file}: {len(result.entries)} registros · SHA-256 {result.source_sha256}")
        for warning in result.warnings:
            print(f"  Aviso: {warning}")
    print(f"Biblioteca: {destination} · {len(merged)} registros "
          f"({len(merged) - len(existing)} nuevos)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="noiz", description="Noiz Transmission · aislamiento de elementos constructivos"
    )
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("materials", help="Listar materiales y procedencia como JSON")
    calculation = commands.add_parser("predict", help="Calcular y comparar proyectos JSON")
    calculation.add_argument("projects", type=Path, nargs="+")
    calculation.add_argument("--output-dir", type=Path, required=True)
    assembly = commands.add_parser("assembly", help="Calcular y comparar elementos V3 (admite V1/V2)")
    assembly.add_argument("projects", type=Path, nargs="+")
    assembly.add_argument("--output-dir", type=Path, required=True)
    catalog = commands.add_parser("catalog", help="Importar y consultar la biblioteca local")
    catalog_commands = catalog.add_subparsers(dest="catalog_command", required=True)
    importer = catalog_commands.add_parser("import", help="Importar uno o varios XML como un lote")
    importer.add_argument("files", type=Path, nargs="+")
    importer.add_argument("--output", type=Path, help="Biblioteca JSON; por defecto, biblioteca del usuario")
    catalog_list = catalog_commands.add_parser("list", help="Mostrar resumen de la biblioteca como JSON")
    catalog_list.add_argument("--input", type=Path, help="Biblioteca JSON que se desea consultar")
    args = parser.parse_args(argv)
    try:
        if args.command == "materials":
            print(json.dumps([asdict(m) for m in list_materials()], indent=2, ensure_ascii=False))
            return 0
        if args.command == "assembly":
            return _assembly(args)
        if args.command == "catalog":
            return _catalog(args)
        predictions = tuple(predict(load_project(path)) for path in args.projects)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        export_csv(predictions, args.output_dir / "spectra.csv")
        export_html(predictions, args.output_dir / "report.html")
        payload = {
            "schema_version": 1,
            "software": _software(),
            "predictions": [asdict(result) for result in predictions],
        }
        (args.output_dir / "result.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        for result in predictions:
            rating = f"Rw orientativo {result.rw_db} dB" if result.rw_db is not None else "sin Rw"
            print(f"{result.project.name}: {result.surface_density_kg_m2:g} kg/m² · {rating}")
        print(f"Resultados: {args.output_dir}")
        print("Modelo de masa ideal. Sin validación experimental; consultar límites del informe.")
        return 0
    except (ValueError, TypeError, KeyError, OSError, NumericalConvergenceError) as exc:
        parser.exit(2, f"noiz: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
