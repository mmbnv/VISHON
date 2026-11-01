"""Snapshots of S.

A snapshot is the *source* of every module in the substrate, plus the
persistent bindings that live outside any module. It contains no live
objects, so it is safe to store, compare and restore.

Restoring a snapshot does not unpickle anything. It recompiles and
re-executes, which means a snapshot cannot smuggle in a state the code could
not have produced by running.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class Snapshot:
    """An immutable record of one configuration of S."""

    label: str = ""
    modules: Mapping[str, str] = field(default_factory=dict)
    state: Mapping[str, Any] = field(default_factory=dict)
    meta: Mapping[str, Any] = field(default_factory=dict)

    @property
    def content_digest(self) -> str:
        """A stable digest of the snapshot's content."""

        payload = json.dumps(
            {
                "modules": {k: self.modules[k] for k in sorted(self.modules)},
                "state": sorted(self.state),
            },
            sort_keys=True,
            default=repr,
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    def short(self) -> str:
        return self.content_digest[:12]

    def __str__(self) -> str:  # pragma: no cover - display only
        return f"Snapshot({self.label!r}, {self.short()})"
