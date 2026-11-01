"""Boundary B: admissible / forbidden.

B is a predicate. It answers one question about a proposed modification
against the program it would produce: forbidden, or not. It never proposes,
never repairs, never explains a path forward. A rule that would do any of
those is not a boundary rule.

Two layers, and the split matters (I9):

``structural``
    Frozen at construction. Encodes isolation (I10) statically: sources must
    parse, must not import outside the substrate allowlist, must not reach for
    interpreter internals, and must stay under a hard size bound. Nobody,
    including P, can change these at run time.

``policy``
    Owned by P alone. Changed only through a method that requires an
    ``AuthorityToken``. The boundary stores a keyed digest of that token, not
    the token itself, so reading the boundary does not yield the key.

B holds no reference to the loop, to memory, to the gateway or to the father
channel. It is consulted, and it answers. ``ProgramView`` contains only module
sources and pinned values, so a rule can only ever be written against the
program -- there is no attribute on the view through which host apparatus
could be reached or modified.
"""

from __future__ import annotations

import ast
import hmac
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping

from vishon.kernel.modification import Modification, ProgramView
from vishon.kernel.substrate import IMPORT_ALLOWLIST


# Attribute names that open the classic routes out of a Python namespace.
_ESCAPE_ATTRIBUTES: frozenset[str] = frozenset(
    {
        "__globals__",
        "__builtins__",
        "__subclasses__",
        "__class__",
        "__bases__",
        "__mro__",
        "__getattribute__",
        "__dict__",
        "__loader__",
        "__spec__",
        "__code__",
        "__closure__",
        "__func__",
        "__self__",
    }
)

# Hard ceiling on total program size. Policy may lower it, never raise it.
STRUCTURAL_SIZE_CAP = 400_000


@dataclass(frozen=True)
class Rule:
    """A named predicate. Returns True when the modification is forbidden."""

    name: str
    description: str
    predicate: Callable[[Modification, ProgramView], bool]


@dataclass(frozen=True)
class Verdict:
    """The boundary's answer."""

    allowed: bool
    reasons: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return self.allowed


class AuthorityError(PermissionError):
    """A boundary mutation was attempted without the authority token."""


def _keyed_digest(secret: bytes) -> bytes:
    return hmac.new(secret, b"vishon.boundary.policy", "sha256").digest()


class Boundary:
    """The boundary predicate B."""

    def __init__(
        self,
        *,
        size_cap: int = STRUCTURAL_SIZE_CAP,
        deny_substrings: Iterable[str] = (),
        deny_module_names: Iterable[str] = (),
        require_modules: Iterable[str] = (),
    ) -> None:
        self._structural: tuple[Rule, ...] = (
            Rule("parseable", "every module must compile", _rule_parseable),
            Rule("imports_inside_S", "imports stay inside the allowlist", _rule_imports),
            Rule("no_escape_attributes", "no interpreter-internal attribute access", _rule_no_escape),
            Rule("size_bound", "total source stays under the hard ceiling", _rule_size),
        )
        self._hard_size_cap = min(size_cap, STRUCTURAL_SIZE_CAP)

        # P-owned policy. The token's keyed digest is the only thing kept.
        self._policy_key: bytes | None = None
        self._policy: dict[str, Any] = {
            "deny_substrings": tuple(deny_substrings),
            "deny_module_names": frozenset(deny_module_names),
            "require_modules": frozenset(require_modules),
            "size_cap": self._hard_size_cap,
        }

    # -- authority -------------------------------------------------------

    def bind_authority(self, token: "Any") -> None:
        """Bind P's authority. Called once, by the father channel (A_P).

        After binding, the policy can be changed only by presenting a token
        whose keyed digest matches. The token itself is never stored.
        """

        secret = getattr(token, "_secret", None)
        if not isinstance(secret, (bytes, bytearray)) or len(secret) < 16:
            raise AuthorityError("a token must carry at least 16 bytes of secret")
        self._policy_key = _keyed_digest(bytes(secret))

    def _require_authority(self, token: "Any") -> None:
        if self._policy_key is None:
            raise AuthorityError("boundary has no bound authority (I9)")
        secret = getattr(token, "_secret", None)
        if not isinstance(secret, (bytes, bytearray)):
            raise AuthorityError("boundary policy is owned by P alone (I9)")
        if not hmac.compare_digest(_keyed_digest(bytes(secret)), self._policy_key):
            raise AuthorityError("boundary policy is owned by P alone (I9)")

    def amend_policy(self, token: "Any", **changes: Any) -> None:
        """Change the policy layer. Requires P's token."""

        self._require_authority(token)
        for key, value in changes.items():
            if key not in self._policy:
                raise KeyError(f"unknown policy key {key!r}")
            if key == "size_cap":
                self._policy["size_cap"] = min(int(value), self._hard_size_cap)
            elif key == "deny_substrings":
                self._policy[key] = tuple(str(v) for v in value)
            else:
                self._policy[key] = frozenset(str(v) for v in value)

    def policy(self) -> Mapping[str, Any]:
        """A read-only copy of the policy layer."""

        return dict(self._policy)

    @property
    def structural_rule_names(self) -> tuple[str, ...]:
        return tuple(rule.name for rule in self._structural)

    # -- the predicate ---------------------------------------------------

    def check(self, modification: Modification, view: ProgramView) -> Verdict:
        """Forbidden, or not. The only public question B answers."""

        reasons: list[str] = []
        for rule in self._structural:
            if rule.predicate(modification, view):
                reasons.append(f"{rule.name}: {rule.description}")
        for rule in self._policy_rules():
            if rule.predicate(modification, view):
                reasons.append(f"{rule.name}: {rule.description}")
        return Verdict(allowed=not reasons, reasons=tuple(reasons))

    def _policy_rules(self) -> tuple[Rule, ...]:
        policy = self._policy
        deny_substrings = tuple(policy["deny_substrings"])
        deny_names = frozenset(policy["deny_module_names"])
        require_modules = frozenset(policy["require_modules"])
        size_cap = int(policy["size_cap"])

        rules: list[Rule] = []

        if deny_substrings:
            def _deny_substrings(_mod: Modification, view: ProgramView) -> bool:
                text = view.all_source()
                return any(needle in text for needle in deny_substrings)

            rules.append(
                Rule(
                    "deny_substrings",
                    f"source contains a forbidden fragment ({len(deny_substrings)} rule(s))",
                    _deny_substrings,
                )
            )

        if deny_names:
            def _deny_names(mod: Modification, _view: ProgramView) -> bool:
                return bool(deny_names & mod.touched_modules())

            rules.append(Rule("deny_module_names", "module name is forbidden", _deny_names))

        if require_modules:
            def _require_modules(_mod: Modification, view: ProgramView) -> bool:
                return bool(require_modules - set(view.module_names))

            rules.append(
                Rule("require_modules", "a required module is absent", _require_modules)
            )

        def _policy_size(_mod: Modification, view: ProgramView) -> bool:
            return view.total_source_size() > size_cap

        rules.append(Rule("policy_size_cap", f"total source exceeds {size_cap}", _policy_size))
        return tuple(rules)


# -- structural rule bodies ---------------------------------------------


def _rule_parseable(mod: Modification, view: ProgramView) -> bool:
    for name in mod.define:
        try:
            compile(view.source_of(name), f"<{name}>", "exec")
        except (SyntaxError, ValueError):
            return True
    return False


def _rule_imports(_mod: Modification, view: ProgramView) -> bool:
    for source in view.modules.values():
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return True
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] not in IMPORT_ALLOWLIST:
                        return True
            elif isinstance(node, ast.ImportFrom):
                if node.level != 0:
                    return True
                if (node.module or "").split(".")[0] not in IMPORT_ALLOWLIST:
                    return True
    return False


def _rule_no_escape(_mod: Modification, view: ProgramView) -> bool:
    for source in view.modules.values():
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return True
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in _ESCAPE_ATTRIBUTES:
                return True
            if isinstance(node, ast.Name) and node.id in _ESCAPE_ATTRIBUTES:
                return True
    return False


def _rule_size(_mod: Modification, view: ProgramView) -> bool:
    return view.total_source_size() > STRUCTURAL_SIZE_CAP
