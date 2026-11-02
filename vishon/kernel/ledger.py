"""The ledger: what actually happened, as opposed to what is encoded.

V_P is a predicate over state. Some of what it must be able to see -- how
often the system has touched reality, whether the father's contour is live,
how many generations have been sealed -- is history, not source code. The
ledger carries that history to the predicate.

The ledger is host apparatus. It is not a module of S, so no modification
can read it or write it. It is passed to V_P for the duration of one
evaluation and nothing else holds it.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Ledger:
    """Accumulated, externally verifiable facts about the run."""

    generations: int = 0
    proposals: int = 0
    sealed: int = 0
    rolled_back: int = 0
    observations: int = 0
    failed_observations: int = 0
    father_acts: int = 0
    last_observation_kind: str = ""
    # The error text of the most recent failed observation, so a caller can
    # report *why* reality was not reached rather than only that it was not.
    last_observation_error: str = ""

    @property
    def contacts(self) -> int:
        """Observations that actually reached something.

        A transport failure produces an observation -- that is the raw fact --
        but it is not contact with reality, and the reality layer must not be
        satisfied by it. ``observations`` counts attempts; ``contacts`` counts
        the ones that arrived.
        """

        return self.observations - self.failed_observations

    def note_observation(self, kind: str, *, ok: bool = True, error: str = "") -> None:
        self.observations += 1
        if not ok:
            self.failed_observations += 1
            self.last_observation_error = error
        self.last_observation_kind = kind
