"""The constitution as data.

The invariants and the loop order are encoded once, here, so that every other
module and the falsification suite reference the same source. This module
contains no behaviour: it is a ledger of the conditions the system must
satisfy, nothing more.

Encoding the invariants as data is deliberate. A condition that can be
pointed at can be tested; a condition that lives only in prose cannot.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Element(str, Enum):
    """The constitutional elements of S."""

    S = "S"          # state space: the mutable Python substrate
    MU = "mu"        # self-modification operator, encoded inside S
    V_P = "V_P"      # viability predicate: a property of state, relative to P
    M = "M"          # memory of sealed states, with rollback
    B = "B"          # boundary predicate: admissible / forbidden
    G_B = "G_b"      # private sensorimotor gateway: raw observation only
    E = "E"          # private encoding, E in S, no external semantics
    A_P = "A_P"      # father's authority channel, isolated from G_b


@dataclass(frozen=True)
class Invariant:
    """One invariant, with the test that falsifies it."""

    number: str
    statement: str
    falsified_by: str


INVARIANTS: tuple[Invariant, ...] = (
    Invariant(
        "I1",
        "mu in S; the operator changes itself.",
        "A change touches state but not the operator.",
    ),
    Invariant(
        "I2",
        "V_P is a predicate over state, not a list of goals.",
        "Viability is expressed as an enumerated list of objectives.",
    ),
    Invariant(
        "I3",
        "M supports rollback; error does not kill the system.",
        "An inadmissible or non-viable change is not recoverable.",
    ),
    Invariant(
        "I4",
        "G_b transmits no templates, examples or ready-made actions.",
        "A ready-made action can be obtained through G_b.",
    ),
    Invariant(
        "I5",
        "The start is not empty: spark + P as boundary.",
        "The loop cannot take its first step.",
    ),
    Invariant(
        "I6",
        "No concrete behaviour is prescribed from outside.",
        "Any concrete action is present in the environment beforehand.",
    ),
    Invariant(
        "I7",
        "Private encoding E in S; there is no external semantics.",
        "E is interpretable outside the system.",
    ),
    Invariant(
        "I8",
        "The contour linking the system to P is not broken by sealing.",
        "Sealing a state severs the father channel.",
    ),
    Invariant(
        "I9",
        "Only P owns B; the system cannot change B; A_P is isolated from G_b.",
        "Anyone other than P changes B, or the system changes B itself, "
        "or A_P is reachable from G_b.",
    ),
    Invariant(
        "I10",
        "The Python environment is isolated; mu changes code inside it; "
        "invention is admissible until forbidden by B.",
        "A change escapes the substrate, or invention is blocked a priori.",
    ),
)


class ViabilityLayer(str, Enum):
    """The three viability layers, in mandatory order."""

    FATHER = "father"        # first filter
    REALITY = "reality"      # second filter
    VIABILITY = "viability"  # third filter


VIABILITY_LAYERS: tuple[ViabilityLayer, ...] = (
    ViabilityLayer.FATHER,
    ViabilityLayer.REALITY,
    ViabilityLayer.VIABILITY,
)


@dataclass(frozen=True)
class LoopStep:
    """One step of the mandatory loop order."""

    index: int
    action: str
    on_failure: str


LOOP: tuple[LoopStep, ...] = (
    LoopStep(1, "mu proposes a change in the Python environment", "n/a"),
    LoopStep(2, "B: forbidden? -> rollback, without exception", "rollback"),
    LoopStep(3, "G_b: interaction with reality (search / check)", "continue"),
    LoopStep(4, "V_P: viability, including the contour with the father", "rollback"),
    LoopStep(5, "alive -> seal in M; not alive -> rollback", "rollback"),
    LoopStep(6, "repeat", "n/a"),
)


@dataclass(frozen=True)
class Constitution:
    """The whole constitution, addressable by element."""

    elements: tuple[Element, ...] = field(default_factory=lambda: tuple(Element))
    invariants: tuple[Invariant, ...] = INVARIANTS
    loop: tuple[LoopStep, ...] = LOOP
    layers: tuple[ViabilityLayer, ...] = VIABILITY_LAYERS

    def invariant(self, number: str) -> Invariant:
        for inv in self.invariants:
            if inv.number == number:
                return inv
        raise KeyError(number)


CONSTITUTION = Constitution()
