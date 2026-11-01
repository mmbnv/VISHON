"""Modifications: the shape of a proposed change.

A ``Modification`` is a delta over the program: modules to define, modules to
remove, bindings to pin. It is plain data. It carries no semantics, only a
private label (``intent``) that the system may use for itself.

``ProgramView`` is the read-only projection of a program that boundary B and
the viability predicate are allowed to inspect. It deliberately exposes
sources and pinned values only. Host apparatus -- B, A_P, G_b, M -- is not
part of any view, so no rule and no predicate can be talked into reaching it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping


@dataclass(frozen=True)
class Modification:
    """A proposed change to S."""

    define: Mapping[str, str] = field(default_factory=dict)
    remove: tuple[str, ...] = ()
    rebind: Mapping[str, Any] = field(default_factory=dict)
    observe: tuple[str, ...] = ()
    intent: str = ""

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any], *, intent: str = "") -> "Modification":
        """Build from plain data, as returned by a proposal operator in S."""

        if not isinstance(raw, Mapping):
            raise TypeError("a proposal must be a mapping")
        define = raw.get("define") or {}
        remove = raw.get("remove") or ()
        rebind = raw.get("rebind") or {}
        observe = raw.get("observe") or ()
        if not isinstance(define, Mapping):
            raise TypeError("'define' must be a mapping of name -> source")
        if not isinstance(rebind, Mapping):
            raise TypeError("'rebind' must be a mapping of name -> value")
        if isinstance(observe, str):
            observe = (observe,)
        return cls(
            define={str(k): str(v) for k, v in define.items()},
            remove=tuple(str(r) for r in remove),
            rebind=dict(rebind),
            observe=tuple(str(o) for o in observe),
            intent=intent or str(raw.get("intent", "")),
        )

    def touched_modules(self) -> frozenset[str]:
        return frozenset(self.define) | frozenset(self.remove)

    def describe(self) -> str:
        bits = []
        if self.define:
            bits.append(f"define{tuple(sorted(self.define))}")
        if self.remove:
            bits.append(f"remove{tuple(sorted(self.remove))}")
        if self.rebind:
            bits.append(f"rebind{tuple(sorted(self.rebind))}")
        if self.observe:
            bits.append(f"observe{len(self.observe)}")
        return " ".join(bits) or "noop"


@dataclass(frozen=True)
class ProgramView:
    """A read-only projection of a candidate program."""

    modules: Mapping[str, str]
    pins: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "modules", MappingProxyType(dict(self.modules)))
        object.__setattr__(self, "pins", MappingProxyType(dict(self.pins)))

    @property
    def module_names(self) -> tuple[str, ...]:
        return tuple(self.modules)

    def source_of(self, name: str) -> str:
        return self.modules[name]

    def all_source(self) -> str:
        return "\n".join(f"# {name}\n{src}" for name, src in self.modules.items())

    def total_source_size(self) -> int:
        return sum(len(src) for src in self.modules.values())
