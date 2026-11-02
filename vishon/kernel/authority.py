"""A_P: the father's authority channel.

The father holds the only key to the boundary's policy layer. This module
provides that key and the small, explicit set of operations the father may
perform with it. It is the system's only route to B, and it is one-way: the
channel can change B, and B never calls back into the channel.

Isolation from the gateway (I9) is enforced three ways:

* ``FatherAuthority`` holds no reference to any gateway. It is constructed
  with a boundary and nothing else.
* Its methods accept only a ``Boundary``. Passing a gateway raises.
* ``Gateway`` (see ``gateway.py``) refuses to accept an ``AuthorityToken`` as
  an observation request, so the two objects cannot be laundered through each
  other.

Every act of the father is journalled. The journal is the father's, not the
system's: it is not a module of S and no modification can reach it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Iterable

from vishon.kernel.boundary import Boundary


class ChannelError(RuntimeError):
    """An attempt to use the father channel incorrectly."""


@dataclass(frozen=True)
class AuthorityToken:
    """P's key. Opaque; carries only a secret the boundary can digest."""

    _secret: bytes

    def __repr__(self) -> str:  # pragma: no cover - never reveal the secret
        return "AuthorityToken(<hidden>)"


@dataclass(frozen=True)
class Act:
    """One journalled act of the father."""

    kind: str
    detail: dict[str, Any] = field(default_factory=dict)


class FatherAuthority:
    """A_P: the father's channel into the boundary."""

    def __init__(self, boundary: Boundary) -> None:
        if not isinstance(boundary, Boundary):
            raise ChannelError("A_P binds to a Boundary and nothing else (I9)")
        self._boundary = boundary
        self._token = AuthorityToken(_secret=os.urandom(32))
        self._journal: list[Act] = []
        boundary.bind_authority(self._token)

    # -- introspection ---------------------------------------------------

    @property
    def journal(self) -> tuple[Act, ...]:
        return tuple(self._journal)

    def token(self) -> AuthorityToken:
        """The key. Handing it out is the father's decision alone."""

        return self._token

    # -- acts ------------------------------------------------------------

    def _record(self, kind: str, **detail: Any) -> None:
        self._journal.append(Act(kind=kind, detail=detail))

    def amend_boundary(self, boundary: Boundary, **changes: Any) -> None:
        """Change the boundary's policy layer."""

        self._guard(boundary)
        boundary.amend_policy(self._token, **changes)
        self._record("amend_boundary", changes={k: repr(v) for k, v in changes.items()})

    def forbid(self, boundary: Boundary, fragment: str, *, reason: str = "") -> None:
        """Add one forbidden fragment to the boundary policy."""

        self._guard(boundary)
        current = list(boundary.policy()["deny_substrings"])
        if fragment not in current:
            current.append(fragment)
        boundary.amend_policy(self._token, deny_substrings=tuple(current))
        self._record("forbid", fragment=fragment, reason=reason)

    def permit(self, boundary: Boundary, fragment: str) -> None:
        """Remove one forbidden fragment from the boundary policy."""

        self._guard(boundary)
        current = [f for f in boundary.policy()["deny_substrings"] if f != fragment]
        boundary.amend_policy(self._token, deny_substrings=tuple(current))
        self._record("permit", fragment=fragment)

    def require(self, boundary: Boundary, modules: Iterable[str]) -> None:
        """Declare modules that must remain present in S."""

        self._guard(boundary)
        boundary.amend_policy(self._token, require_modules=frozenset(modules))
        self._record("require", modules=tuple(sorted(modules)))

    def configure_gateway(self, gateway: "Any", **changes: Any) -> None:
        """Set the network policy. The gateway is not stored, only used."""

        gateway.configure(self._token, **changes)
        self._record("configure_gateway", changes={k: repr(v) for k, v in changes.items()})

    def refine_viability(self, viability: "Any", *predicates: Any) -> None:
        """Add predicates to V_P. The predicate set is P's to refine."""

        viability.refine(self._token, *predicates)
        self._record("refine_viability", count=len(predicates))

    def _guard(self, boundary: Boundary) -> None:
        if boundary is not self._boundary:
            raise ChannelError("A_P acts on the boundary it was bound to (I9)")


def attempt_unauthorised_change(boundary: Boundary, **changes: Any) -> None:
    """Try to change B without P's token. Always raises.

    This exists so the falsification suite can demonstrate that the route the
    system would have to take is closed, rather than asserting it in prose.
    """

    boundary.amend_policy(_ImpostorToken(), **changes)


@dataclass(frozen=True)
class _ImpostorToken:
    _secret: bytes = b"not-the-father-token-000000000000"
