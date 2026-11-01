"""The loop, in the mandatory order.

    1. mu proposes a change in the Python environment
    2. B: forbidden? -> rollback, without exception
    3. G_b: interaction with reality (search / check)
    4. V_P: viability, including the contour with the father
    5. alive -> seal in M; not alive -> rollback
    6. repeat

The order is not a convention that could be reordered for convenience. Step 2
runs before step 3 because the boundary is the first filter and reality is the
second: a forbidden change must not be allowed to touch the network before it
is refused. Step 4 runs after step 3 because viability is judged on the state
*as it is after contact with reality*, not on the proposal.

The loop holds no behaviour of its own beyond the order. Every decision it
makes is delegated: to ``mu`` for what to propose, to B for admissibility, to
G_b for contact, to V_P for life, to M for sealing and rollback.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from vishon.kernel.boundary import Boundary
from vishon.kernel.gateway import Gateway, GatewayError
from vishon.kernel.ledger import Ledger
from vishon.kernel.memory import Attempt, Memory
from vishon.kernel.modification import Modification, ProgramView
from vishon.kernel.substrate import Substrate
from vishon.kernel.viability import Viability


class LoopError(RuntimeError):
    """The loop could not take a step."""


@dataclass(frozen=True)
class Turn:
    """The record of one trip around the loop."""

    index: int
    intent: str
    change: str
    verdict: str            # "sealed" | "forbidden" | "not_viable" | "error"
    reasons: tuple[str, ...] = ()
    observations: int = 0
    observation_failures: int = 0
    generation: int = 0

    @property
    def advanced(self) -> bool:
        return self.verdict == "sealed"

    @property
    def observed_ok(self) -> bool:
        return self.observations > 0 and self.observation_failures == 0


class Loop:
    """The ordered loop over the substrate."""

    def __init__(
        self,
        *,
        substrate: Substrate,
        boundary: Boundary,
        viability: Viability,
        gateway: Gateway,
        memory: Memory,
        ledger: Ledger | None = None,
    ) -> None:
        self.substrate = substrate
        self.boundary = boundary
        self.viability = viability
        self.gateway = gateway
        self.memory = memory
        self.ledger = ledger or Ledger()
        self._index = 0
        self._history: list[Turn] = []

    # -- the step --------------------------------------------------------

    def step(self, proposal: Mapping[str, Any] | Modification | None = None) -> Turn:
        """One trip around the loop. Returns what happened."""

        self._index += 1
        self.ledger.proposals += 1

        # 1. mu proposes. The loop does not decide what; it only asks.
        if proposal is None:
            proposal = self._ask_mu()
        modification = (
            proposal
            if isinstance(proposal, Modification)
            else Modification.from_mapping(proposal)
        )

        # 2. B: forbidden? -> rollback, without exception.
        candidate = self._candidate_view(modification)
        verdict = self.boundary.check(modification, candidate)
        if not verdict.allowed:
            rollback = self.memory.rollback(reason="forbidden by B")
            turn = Turn(
                index=self._index,
                intent=modification.intent,
                change=modification.describe(),
                verdict="forbidden",
                reasons=verdict.reasons,
                generation=self.memory.generation,
            )
            self._record(turn, rollback.detail)
            return turn

        # Apply the change. A change that cannot execute is an error, and an
        # error is handled exactly like a forbidden change: rollback (I3).
        try:
            self.substrate.apply(
                define=modification.define,
                remove=modification.remove,
                rebind=modification.rebind,
            )
        except BaseException as exc:
            rollback = self.memory.rollback(reason="change failed to execute")
            turn = Turn(
                index=self._index,
                intent=modification.intent,
                change=modification.describe(),
                verdict="error",
                reasons=(f"{type(exc).__name__}: {exc}",),
                generation=self.memory.generation,
            )
            self._record(turn, rollback.detail)
            return turn

        # 3. G_b: interaction with reality.
        observations, observation_failures = self._observe(modification.observe)

        # 4. V_P: viability, including the contour with the father.
        self.ledger.generations = self.memory.generation
        snapshot = self.substrate.snapshot()
        state_view = ProgramView(
            modules=dict(snapshot.modules),
            pins=dict(snapshot.state),
        )
        result = self.viability.evaluate(state_view, self.ledger)
        if not result.alive:
            rollback = self.memory.rollback(reason="not viable")
            turn = Turn(
                index=self._index,
                intent=modification.intent,
                change=modification.describe(),
                verdict="not_viable",
                reasons=(result.reason,),
                observations=observations,
                observation_failures=observation_failures,
                generation=self.memory.generation,
            )
            self._record(turn, rollback.detail)
            return turn

        # 5. alive -> seal in M.
        self.memory.seal(
            self.substrate.snapshot(label=f"gen-{self.memory.generation + 1}"),
            note=f"turn {self._index}: {modification.describe()}",
        )
        self.ledger.sealed += 1
        self.ledger.generations = self.memory.generation
        turn = Turn(
            index=self._index,
            intent=modification.intent,
            change=modification.describe(),
            verdict="sealed",
            reasons=(result.reason,) if result.reason else (),
            observations=observations,
            observation_failures=observation_failures,
            generation=self.memory.generation,
        )
        self._record(turn)
        return turn

    def run(self, turns: int) -> tuple[Turn, ...]:
        """Take up to ``turns`` steps. 6. repeat."""

        produced = []
        for _ in range(turns):
            produced.append(self.step())
        return tuple(produced)

    # -- internals -------------------------------------------------------

    def _ask_mu(self) -> Modification:
        """Ask the program's own proposal operator what to change."""

        if not self.substrate.exposes("propose"):
            raise LoopError(
                "the program no longer exposes a proposal operator; the loop "
                "cannot take a step (I6: the loop does not carry one itself)"
            )
        raw = self.substrate.call("propose")
        return Modification.from_mapping(raw)

    def _observe(self, urls: tuple[str, ...]) -> tuple[int, int]:
        """Attempt contact. Returns (observations, failures).

        A failed fetch still produces an observation, because that is the raw
        fact, but it is recorded as a failure so that the reality layer is not
        satisfied by a run that never arrived anywhere.
        """

        observations = 0
        failures = 0
        for url in urls:
            try:
                observation = self.gateway.observe(url)
            except GatewayError:
                continue
            self.substrate.pin("_observation", observation)
            self.substrate.pin("_last_observation", observation)
            self.ledger.note_observation(
                observation.content_type or "unknown", ok=observation.ok
            )
            observations += 1
            if not observation.ok:
                failures += 1
        return observations, failures

    def _candidate_view(self, modification: Modification) -> ProgramView:
        current = self.substrate.snapshot()
        modules = dict(current.modules)
        for name in modification.remove:
            modules.pop(name, None)
        modules.update(modification.define)
        pins = dict(current.state)
        pins.update(modification.rebind)
        return ProgramView(modules=modules, pins=pins)

    def _record(self, turn: Turn, detail: str = "") -> None:
        self._history.append(turn)
        self.memory.record(
            Attempt(
                index=turn.index,
                intent=turn.intent,
                change=turn.change,
                outcome=turn.verdict,
                detail=detail or " ".join(turn.reasons),
                generation=turn.generation,
            )
        )
        if turn.verdict in {"forbidden", "error", "not_viable"}:
            self.ledger.rolled_back += 1

    @property
    def history(self) -> tuple[Turn, ...]:
        return tuple(self._history)
