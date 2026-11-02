"""Reproduce end-to-end prediction timings; excludes GUI, disk export and cache."""

import argparse
import json
import platform
import statistics
from pathlib import Path
from time import perf_counter

from noiz_transmission import __version__
from noiz_transmission.application.assembly_services import load_workspace, predict_assembly


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    root = Path(__file__).resolve().parents[1]
    cases = []
    for name in ("single", "double_timber", "double_steel"):
        relative = f"examples/v7_{name}.noiz.json"
        project, _ = load_workspace(root / relative)
        times = []
        for _ in range(args.repeats):
            start = perf_counter()
            result = predict_assembly(project)
            times.append(perf_counter() - start)
        cases.append({"project": relative, "model": result.model_name,
                      "seconds": times, "median_seconds": statistics.median(times),
                      "rw_db": result.rw_db, "stc": result.stc_db,
                      "band_count": len(result.frequencies_hz)})
    payload = {"version": __version__, "platform": platform.platform(),
               "python": platform.python_version(), "repeats": args.repeats,
               "scope": "predict_assembly including validation; no GUI/cache/export; synthetic cases",
               "cases": cases}
    text = json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
