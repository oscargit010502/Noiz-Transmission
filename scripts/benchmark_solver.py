#!/usr/bin/env python3
"""Reproducible synthetic 1–4 leaf benchmark; no experimental accuracy claim.

Run: uv run python scripts/benchmark_solver.py --timeout 60 --repeat 2
Use --legacy-module /tmp/transfer_v5.py to compare an exported V5 transfer.py
with the current solver in the same process and report maximum TL difference.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import sys
from pathlib import Path
from threading import Event, Timer
from time import perf_counter

# Small matrix/vector products do not benefit from a large BLAS thread pool.
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

from noiz_transmission.core import transfer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--panels", type=int, nargs="+", default=[1, 2, 3, 4], choices=[1, 2, 3, 4])
    parser.add_argument("--bands", type=float, nargs="+", default=transfer.NOMINAL_BANDS_HZ.tolist())
    parser.add_argument("--finite", action="store_true", help="Use 2.4 × 2.7 m Davy finite panels")
    parser.add_argument("--legacy-module", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.timeout <= 0 or args.repeat < 1:
        parser.error("--timeout and --repeat must be positive")
    if args.finite and args.legacy_module:
        parser.error("Compare legacy performance with identical infinite-panel physics")
    modules = [("current", transfer)]
    if args.legacy_module:
        spec = importlib.util.spec_from_file_location("noiz_benchmark_legacy", args.legacy_module)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        modules.insert(0, ("legacy", module))
    document = {"python": platform.python_version(), "platform": platform.platform(),
                "cpu_count": os.cpu_count(), "openblas_threads": os.environ["OPENBLAS_NUM_THREADS"],
                "model": "finite-davy" if args.finite else "infinite",
                "parameters": {"mass_kg_m2": 10, "D_nm": 2.5e9 * .0125**3 / (12 * (1 - .25**2)),
                               "loss_factor": .03, "gap_m": .1, "fill_m": .05,
                               "resistivity_pa_s_m2": 10000, "incidence": "diffuse",
                               "bands_hz": args.bands}, "measurements": []}
    references = {}
    for panels in args.panels:
        for version, module in modules:
            for repeat in range(args.repeat):
                from noiz_transmission.core.finite_panel import FinitePanel
                geometry = {"finite_size": FinitePanel(2.4, 2.7)} if args.finite else {}
                plates = (module.Plate(10, document["parameters"]["D_nm"], .03, **geometry),) * panels
                gaps = (module.Gap(.1, 10000, .05),) * (panels - 1)
                event = Event()
                timer = Timer(args.timeout, event.set)
                timer.daemon = True
                timer.start()
                start = perf_counter()
                result = {"version": version, "panels": panels, "repeat": repeat + 1}
                try:
                    values = module.predict_multilayer(plates, gaps, frequencies_hz=args.bands,
                                                       cancel_event=event)
                    result.update(seconds=perf_counter() - start, tl_db=values.tolist())
                    if version == "legacy":
                        references[panels] = values
                    elif panels in references:
                        result["maximum_delta_db"] = float(max(abs(values - references[panels])))
                except ValueError as exc:
                    result.update(seconds=perf_counter() - start, error=str(exc))
                finally:
                    timer.cancel()
                document["measurements"].append(result)
                print(json.dumps(result, ensure_ascii=False), flush=True)
                if args.output:
                    args.output.write_text(json.dumps(document, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
