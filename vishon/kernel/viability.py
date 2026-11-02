"""V_P: the viability predicate.

V_P answers one question about a state: is it alive. It is a predicate over
the program and the ledger, never a list of goals (I2). There is no
``objective`` type in this module, and no counter of goals met. A predicate
either holds of a state or it does not.

The three layers are evaluated in the mandatory order and the first dead
layer ends the evaluation:

1. father -- is the contour with P live
2. reality -- has the state been in contact with what is not itself
3. viability -- does the program itself still hold together

Short-circuiting is not an optimisation. It encodes the ordering of the
filters: a state whose father contour is broken is dead regardless of how
well its code parses, and saying otherwise would make the ordering decorative.

The predicate set is P's. P may refine it through A_P's token; the system has
no route in.
"""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from vishon.constitution import ViabilityLayer
from vishon.kernel.ledger import Ledger
from vishon.kernel.modification import ProgramView


class ViabilityError(RuntimeError):
    """The viability predicate was used incorrectly."""


def _keyed_digest(secret: bytes) -> bytes:
    return hmac.new(secret, b"vishon.viability.predicates", "sha256").digest()


@dataclass(frozen=True)
class LayeredPredicate:
    """One viability predicate, with the layer it belongs to."""

    name: str
    layer: ViabilityLayer
    description: str
    predicate: Callable[[ProgramView, Ledger], bool]

    def __call__(self, view: ProgramView, ledger: Ledger) -> bool:
        return bool(self.predicate(view, ledger))


@dataclass(frozen=True)
class LayerVerdict:
    layer: ViabilityLayer
    name: str
    alive: bool
    detail: str = ""


@dataclass(frozen=True)
class ViabilityResult:
    """The predicate's answer, with the per-layer trace."""

    alive: bool
    verdicts: tuple[LayerVerdict, ...] = ()
    failed_layer: ViabilityLayer | None = None
    reason: str = ""

    def __bool__(self) -> bool:
        return self.alive


class Viability:
    """V_P: a predicate over (program, ledger), evaluated in layer order."""

    def __init__(self, predicates: Iterable[LayeredPredicate] = ()) -> None:
        self._predicates: list[LayeredPredicate] = list(predicates)
        self._key: bytes | None = None

    def bind_authority(self, token: "Any") -> None:
        secret = getattr(token, "_secret", None)
        if not isinstance(secret, (bytes, bytearray)) or len(secret) < 16:
            raise ViabilityError("a token must carry at least 16 bytes of secret")
        self._key = _keyed_digest(bytes(secret))

    def refine(self, token: "Any", *predicates: LayeredPredicate) -> None:
        """Add predicates. Requires P's token (V_P is refined by request of P)."""

        secret = getattr(token, "_secret", None)
        if self._key is None:
            raise ViabilityError("viability has no bound authority")
        if not isinstance(secret, (bytes, bytearray)) or not hmac.compare_digest(
            _keyed_digest(bytes(secret)), self._key
        ):
            raise ViabilityError("V_P is refined by P alone")
        self._predicates.extend(predicates)

    @property
    def predicates(self) -> tuple[LayeredPredicate, ...]:
        return tuple(self._predicates)

    def evaluate(self, view: ProgramView, ledger: Ledger) -> ViabilityResult:
        verdicts: list[LayerVerdict] = []
        for layer in ViabilityLayer:
            alive = True
            for predicate in self._predicates:
                if predicate.layer is not layer:
                    continue
                try:
                    ok = predicate(view, ledger)
                    detail = ""
                except BaseException as exc:  # a predicate that raises is not viable
                    ok = False
                    detail = f"raised {type(exc).__name__}: {exc}"
                verdicts.append(LayerVerdict(layer, predicate.name, ok, detail))
                if not ok:
                    alive = False
                    break
            if not alive:
                return ViabilityResult(
                    alive=False,
                    verdicts=tuple(verdicts),
                    failed_layer=layer,
                    reason=f"{layer.value} layer: {verdicts[-1].name} {verdicts[-1].detail}".strip(),
                )
        return ViabilityResult(alive=True, verdicts=tuple(verdicts))


# -- the founding predicate set -----------------------------------------


def father_contour_live(_view: ProgramView, ledger: Ledger) -> bool:
    """The contour with P must be live, always (I8).

    Live means the father has bound the boundary and has acted at least once.
    A run in which the father never appears is a run without a first filter.
    """

    return ledger.father_acts >= 1


def reality_contact(_view: ProgramView, ledger: Ledger) -> bool:
    """The state must have been in contact with what is not itself.

    Contact is counted, not scored: an observation that arrived happened, and
    one that failed to arrive did not. A run that only ever failed to reach
    anything has not touched reality, and a state that has not touched reality
    is not alive (I4, the second filter).
    """

    return ledger.contacts >= 1


def program_sound(view: ProgramView, _ledger: Ledger) -> bool:
    """Every module must compile as a whole program state."""

    for name, source in view.modules.items():
        try:
            compile(source, f"<{name}>", "exec")
        except (SyntaxError, ValueError):
            return False
    return True


def continuable(view: ProgramView, _ledger: Ledger) -> bool:
    """The state must still be able to take a step.

    This is a property, not a goal: a program that has lost its own proposal
    operator or its own encoding cannot continue, and a state that cannot
    continue is not alive. What those operators *do* is not specified here or
    anywhere else.
    """

    required = ("propose", "encode")
    return all(name in view.modules for name in required)


def founding_predicates() -> tuple[LayeredPredicate, ...]:
    """The predicate set the environment starts with."""

    return (
        LayeredPredicate(
            "father_contour_live",
            ViabilityLayer.FATHER,
            "the contour with P is live",
            father_contour_live,
        ),
        LayeredPredicate(
            "reality_contact",
            ViabilityLayer.REALITY,
            "the state has touched what is not itself",
            reality_contact,
        ),
        LayeredPredicate(
            "program_sound",
            ViabilityLayer.VIABILITY,
            "the program holds together",
            program_sound,
        ),
        LayeredPredicate(
            "continuable",
            ViabilityLayer.VIABILITY,
            "the state can still take a step",
            continuable,
        ),
    )
