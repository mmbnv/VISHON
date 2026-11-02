"""M: memory of sealed states, with rollback.

M keeps two things apart:

``sealed``
    Snapshots that passed the boundary and the viability predicate. Only
    these are restorable. Sealing is append-only; nothing is ever removed.

``attempts``
    A journal of every proposal, including the ones that were refused or
    rolled back. This is where errors live. An error is recorded and then
    forgotten by the program, but never by M.

Rollback is the whole point of M (I3). It is therefore written to be
*incapable of raising*: if restoring the latest sealed snapshot fails, M
walks backwards through earlier snapshots, and if every restore fails it
returns a failure result and leaves the substrate untouched. A broken change
must cost a state, never the system.

The contour with P is not part of a snapshot. Sealing a state therefore
cannot sever it (I8): there is nothing in M to overwrite.
"""

from __future__ import annotations

from dataclasses import dataclass

from vishon.kernel.snapshot import Snapshot
from vishon.kernel.substrate import Substrate


@dataclass(frozen=True)
class Attempt:
    """One turn of the loop, as M saw it."""

    index: int
    intent: str
    change: str
    outcome: str
    detail: str = ""
    generation: int = 0


@dataclass(frozen=True)
class RollbackResult:
    ok: bool
    generation: int
    detail: str = ""


class Memory:
    """M: sealed states plus a journal of attempts."""

    def __init__(self, substrate: Substrate) -> None:
        self._substrate = substrate
        self._sealed: list[Snapshot] = []
        self._attempts: list[Attempt] = []
        self._generation = 0

    # -- sealing ---------------------------------------------------------

    def genesis(self, snapshot: Snapshot | None = None) -> Snapshot:
        """Seal the founding state. Exactly once, at start."""

        if self._sealed:
            raise RuntimeError("genesis has already been sealed")
        snap = snapshot or self._substrate.snapshot(label="genesis")
        self._sealed.append(snap)
        self._generation = 1
        return snap

    def seal(self, snapshot: Snapshot | None = None, *, note: str = "") -> Snapshot:
        snap = snapshot or self._substrate.snapshot(label=note or f"gen-{self._generation}")
        self._sealed.append(snap)
        self._generation += 1
        return snap

    @property
    def generation(self) -> int:
        return self._generation

    @property
    def sealed(self) -> tuple[Snapshot, ...]:
        return tuple(self._sealed)

    @property
    def latest(self) -> Snapshot:
        if not self._sealed:
            raise RuntimeError("M has no sealed state")
        return self._sealed[-1]

    @property
    def depth(self) -> int:
        return len(self._sealed)

    # -- attempts --------------------------------------------------------

    def record(self, attempt: Attempt) -> None:
        self._attempts.append(attempt)

    @property
    def attempts(self) -> tuple[Attempt, ...]:
        return tuple(self._attempts)

    def attempt_count(self, outcome: str | None = None) -> int:
        if outcome is None:
            return len(self._attempts)
        return sum(1 for a in self._attempts if a.outcome == outcome)

    # -- rollback --------------------------------------------------------

    def rollback(self, *, reason: str = "") -> RollbackResult:
        """Restore the most recent sealed state that will restore.

        Never raises. Never removes a sealed snapshot.
        """

        if not self._sealed:
            return RollbackResult(False, self._generation, "no sealed state to restore")

        last_error = ""
        for depth, snap in enumerate(reversed(self._sealed)):
            try:
                self._substrate.restore(snap)
            except BaseException as exc:  # a sealed snapshot must never fail, but
                # if it somehow does, fall back rather than die (I3)
                last_error = f"{type(exc).__name__}: {exc}"
                continue
            self._generation = len(self._sealed) - depth
            note = f"restored {snap.short()}"
            if reason:
                note = f"{note} ({reason})"
            return RollbackResult(True, self._generation, note)

        detail = "no snapshot could be restored"
        if last_error:
            detail = f"{detail}; last error: {last_error}"
        return RollbackResult(False, self._generation, detail)
