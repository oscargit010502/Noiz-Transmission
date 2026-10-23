"""Bounded per-window result cache; every input and its provenance is part of the key.

Only successful results are stored. Copies on insertion and retrieval isolate the
mutable dictionaries inside catalog snapshots from the displayed result. This is
an in-memory optimization, never a substitute for persisted project inputs.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections import OrderedDict
from dataclasses import asdict
from threading import Lock

from noiz_transmission import __version__
from noiz_transmission.application.assemblies import AssemblyPrediction, AssemblyProject
from noiz_transmission.application.assembly_services import project_to_dict


class PredictionCache:
    """LRU bounded by entry count and serialized payload size, local to one window."""

    def __init__(self, capacity: int = 8, max_bytes: int = 16 * 1024 * 1024) -> None:
        if type(capacity) is not int or capacity <= 0:
            raise ValueError("capacity must be a positive integer")
        if type(max_bytes) is not int or max_bytes <= 0:
            raise ValueError("max_bytes must be a positive integer")
        self.capacity = capacity
        self.max_bytes = max_bytes
        self._entries: OrderedDict[str, tuple[AssemblyPrediction, int]] = OrderedDict()
        self._bytes = 0
        self._lock = Lock()

    @staticmethod
    def _key(project: AssemblyProject) -> str:
        encoded = json.dumps(
            {"software": __version__, "project": project_to_dict(project)},
            sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def get(self, project: AssemblyProject) -> AssemblyPrediction | None:
        key = self._key(project)
        with self._lock:
            if key not in self._entries:
                return None
            result, _ = self._entries[key]
            self._entries.move_to_end(key)
            return copy.deepcopy(result)

    def put(self, result: AssemblyPrediction) -> None:
        if not isinstance(result, AssemblyPrediction):
            raise TypeError("Only successful AssemblyPrediction results can be cached")
        key = self._key(result.project)
        detached = copy.deepcopy(result)
        size = len(json.dumps(asdict(detached), ensure_ascii=False, allow_nan=False).encode("utf-8"))
        if size > self.max_bytes:
            return
        with self._lock:
            old = self._entries.pop(key, None)
            if old is not None:
                self._bytes -= old[1]
            self._entries[key] = detached, size
            self._bytes += size
            while len(self._entries) > self.capacity or self._bytes > self.max_bytes:
                _, (_, removed_size) = self._entries.popitem(last=False)
                self._bytes -= removed_size
