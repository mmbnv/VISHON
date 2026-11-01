"""Substrate: the state space S.

S is a program plus the persistent state that program carries. The two are
kept apart on purpose.

``modules``
    Source. Executed in a fixed order into one shared environment. Module
    globals are that environment, so a module reads names defined by modules
    that ran before it with no import machinery. Re-executing the whole
    program is the only way code-derived bindings are produced, and it always
    starts from a clean environment. A redefinition therefore cannot leave a
    stale name behind.

``state``
    Persistent bindings that survive re-execution: the private encoding key,
    the last observation, anything a change pinned. Re-execution does not
    clear them and does not recompute them. They are applied *after* the
    program runs, so a change that fails to execute leaves them untouched.

Keeping them apart is what makes rollback sound. Without the split, a change
that redefines a module while a later module still reads the old binding
would leave the program in a state no run could have produced.

Isolation
---------
Executed code receives a guarded ``builtins`` mapping. Dangerous names
(``open``, ``exec``, ``eval``, ``compile``, ``__import__``, ``input``,
``breakpoint``, ``exit``, ``quit``, ``globals``, ``locals``, ``vars``,
``memoryview``) are removed, and the substrate supplies its own
``__import__`` that refuses anything outside an explicit allowlist. The
filesystem is not reachable through the guarded namespace.

This is a containment boundary against accident, not a security sandbox
against a determined adversary. The constitution asks for isolation of the
Python environment (I10); it does not ask for resistance to a hostile
process, and claiming otherwise would be dishonest.
"""

from __future__ import annotations

import builtins as _builtins
import hashlib
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from vishon.kernel.snapshot import Snapshot


# Names removed from the builtins handed to executed code.
_STRIPPED_BUILTINS: frozenset[str] = frozenset(
    {
        "open",
        "exec",
        "eval",
        "compile",
        "input",
        "breakpoint",
        "exit",
        "quit",
        "globals",
        "locals",
        "vars",
        "memoryview",
        "__import__",
        # These turn a *string* into an attribute access, which the boundary's
        # AST rule cannot see. A name can be assembled at runtime, so the only
        # sound answer is to remove the capability. Normal attribute syntax
        # (q.text) still works and is still checked by the boundary.
        "getattr",
        "setattr",
        "delattr",
    }
)

# Modules an executed change may import. Everything else is refused by the
# substrate's own __import__, which keeps the change inside S.
IMPORT_ALLOWLIST: frozenset[str] = frozenset(
    {
        "math",
        "cmath",
        "statistics",
        "itertools",
        "functools",
        "collections",
        "heapq",
        "bisect",
        "array",
        "copy",
        "random",
        "json",
        "re",
        "textwrap",
        "difflib",
        "hashlib",
        "hmac",
        "secrets",
        "base64",
        "binascii",
        "struct",
        "codecs",
        "unicodedata",
        "string",
        "datetime",
        "time",
        "zoneinfo",
        "decimal",
        "fractions",
        "numbers",
        "enum",
        "dataclasses",
        "typing",
        "abc",
        "ast",
        "operator",
        "contextlib",
        "graphlib",
        "uuid",
        "zlib",
        "bz2",
        "lzma",
    }
)


class SubstrateError(RuntimeError):
    """A change could not be applied to the substrate."""


def _guarded_import(name: str, globals=None, locals=None, fromlist=(), level=0):
    root = name.split(".")[0]
    if level != 0 or root not in IMPORT_ALLOWLIST:
        raise ImportError(
            f"substrate isolation: import of {name!r} is not allowed "
            f"(I10: changes stay inside S)"
        )
    return _builtins.__import__(name, globals, locals, fromlist, level)


def guarded_builtins() -> dict[str, Any]:
    """A fresh builtins mapping for one unit of executed code."""

    namespace = {
        name: value
        for name, value in vars(_builtins).items()
        if name not in _STRIPPED_BUILTINS and not name.startswith("__")
    }
    namespace["__import__"] = _guarded_import
    namespace["__build_class__"] = _builtins.__build_class__
    namespace["__name__"] = "__vishon_module__"
    return namespace


@dataclass(frozen=True)
class Module:
    """One addressable unit of the program."""

    name: str
    source: str


class Substrate:
    """The mutable program that is S."""

    def __init__(self, modules: Iterable[Module] = ()) -> None:
        self._modules: dict[str, Module] = {}
        self._order: list[str] = []
        self._state: dict[str, Any] = {}
        self.root: dict[str, Any] = {"__name__": "S"}
        for module in modules:
            self.define(module)
        self.execute()

    # -- module graph ----------------------------------------------------

    @property
    def module_names(self) -> tuple[str, ...]:
        return tuple(self._order)

    def module(self, name: str) -> Module:
        try:
            return self._modules[name]
        except KeyError as exc:
            raise SubstrateError(f"no module named {name!r}") from exc

    def define(self, module: Module) -> None:
        """Add or replace a module. Replacement keeps its position."""

        if module.name not in self._modules:
            self._order.append(module.name)
        self._modules[module.name] = module

    def remove(self, name: str) -> None:
        if name not in self._modules:
            raise SubstrateError(f"no module named {name!r}")
        del self._modules[name]
        self._order.remove(name)

    # -- execution -------------------------------------------------------

    def _run(self, module: Module) -> None:
        code = compile(module.source, f"<S:{module.name}>", "exec")
        _builtins.exec(code, self.root)

    def execute(self) -> None:
        """Execute the whole program, then apply persistent state.

        This is the only way code-derived bindings are produced. There is no
        incremental path, because incremental execution would make rollback
        unsound.
        """

        self.root = {"__name__": "S", "__builtins__": guarded_builtins()}
        for name in list(self._order):
            self._run(self._modules[name])
        # Code-derived bindings come first; persistent state is applied after
        # so a change cannot shadow the key, the observation or the sources.
        self.root["_sources"] = {
            name: self._modules[name].source for name in self._order
        }
        self.root.update(self._state)

    def pin(self, name: str, value: Any) -> None:
        """Write a persistent binding, without re-executing."""

        self._state[name] = value
        self.root[name] = value

    # -- change ----------------------------------------------------------

    def apply(
        self,
        *,
        define: Mapping[str, str] | None = None,
        remove: Iterable[str] = (),
        rebind: Mapping[str, Any] | None = None,
    ) -> None:
        """Mutate the program, then re-execute it.

        ``define`` maps module names to source, ``remove`` drops modules,
        ``rebind`` writes persistent bindings. Rebinds are recorded and
        re-applied on every subsequent execution, so a pinned value survives
        later re-executions.

        If execution raises, the substrate returns to its previous state and
        the error propagates. The caller (M) decides what that means.
        """

        previous_modules = dict(self._modules)
        previous_order = list(self._order)
        previous_state = dict(self._state)
        previous_root = self.root

        try:
            for name in remove:
                self.remove(name)
            for name, source in (define or {}).items():
                self.define(Module(name=name, source=source))
            if rebind:
                self._state.update(rebind)
            self.execute()
        except BaseException:
            self._modules = previous_modules
            self._order = previous_order
            self._state = previous_state
            self.root = previous_root
            raise

    # -- snapshot / restore ---------------------------------------------

    def snapshot(self, label: str = "", **meta: Any) -> Snapshot:
        return Snapshot(
            label=label,
            modules={name: self._modules[name].source for name in self._order},
            state=dict(self._state),
            meta=dict(meta),
        )

    def restore(self, snapshot: Snapshot) -> None:
        """Re-adopt a snapshot by recompiling and re-executing it."""

        self._modules = {
            name: Module(name=name, source=source)
            for name, source in snapshot.modules.items()
        }
        self._order = list(snapshot.modules)
        self._state = dict(snapshot.state)
        self.execute()

    # -- inspection ------------------------------------------------------

    def exposes(self, name: str) -> bool:
        return name in self.root

    def get(self, name: str) -> Any:
        try:
            return self.root[name]
        except KeyError as exc:
            raise SubstrateError(f"root has no binding {name!r}") from exc

    def call(self, name: str, *args: Any, **kwargs: Any) -> Any:
        target = self.get(name)
        if not callable(target):
            raise SubstrateError(f"root binding {name!r} is not callable")
        return target(*args, **kwargs)

    def source_of(self, name: str) -> str:
        return self.module(name).source

    @property
    def state(self) -> Mapping[str, Any]:
        return dict(self._state)

    def digest(self) -> str:
        return hashlib.sha256(self.snapshot().content_digest.encode()).hexdigest()[:16]
