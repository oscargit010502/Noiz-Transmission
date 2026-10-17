"""Build a deterministic bundled catalogue from explicitly supplied XML files.

Run with the project installed: python tools/build_catalog.py --output DIR XML...
Original source files are read only. The imported snapshots retain raw fields.
"""

import argparse
import gzip
import hashlib
import json
import tempfile
from collections import Counter
from pathlib import Path

from noiz_transmission.catalog import import_xml, merge_catalog, save_catalog


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("files", type=Path, nargs="+")
    args = parser.parse_args()
    entries = ()
    sources = []
    for path in sorted(args.files, key=lambda path: path.name):
        result = import_xml(path)
        entries = merge_catalog(entries, result.entries)
        sources.append({"filename": path.name, "sha256": result.source_sha256,
                        "entry_count": len(result.entries)})
    with tempfile.TemporaryDirectory() as temporary:
        destination = Path(temporary) / "catalog.json"
        save_catalog(entries, destination)
        data = destination.read_bytes()
    manifest = {"format_version": 1, "entry_count": len(entries),
                "catalog_sha256": hashlib.sha256(data).hexdigest(),
                "kinds": dict(sorted(Counter(entry.kind for entry in entries).items())),
                "sources": sources}
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "catalog-v5.json.gz").write_bytes(gzip.compress(data, mtime=0))
    (args.output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"entries": len(entries), "kinds": manifest["kinds"]}))


if __name__ == "__main__":
    main()
