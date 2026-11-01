"""The spark, and the assembled environment.

A start cannot be absolutely empty: a loop with nothing to execute has no
first step (I5). The spark is the smallest non-empty carrier that makes a
step possible, and it is exactly the five things the constitution's
impossibility boundary names -- carrier, transition rule, criterion, memory,
gateway -- with no behaviour attached to any of them:

    carrier            ``core``     three seed variables
    transition rule    ``propose``  reads the seed, returns a proposal
    criterion          V_P         supplied by the father, outside S
    memory             M           supplied by the father, outside S
    gateway            G_b         supplied by the father, outside S

The founding ``propose`` proposes *contact and no change*. It does not
propose a self-modification, because a prescribed self-modification would be
behaviour. A program that wants to become something else has to rewrite
``propose`` to say so, and that rewrite is the point (I1, I6).

The pinned names ``_key`` and ``_url`` are the only two facts the father
supplies at start: a random key for the private encoding E (I7), and one URL
for the first contact with reality (I4). Neither is behaviour.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Iterable

from vishon.kernel.authority import FatherAuthority
from vishon.kernel.boundary import Boundary
from vishon.kernel.gateway import Gateway
from vishon.kernel.ledger import Ledger
from vishon.kernel.loop import Loop
from vishon.kernel.memory import Memory
from vishon.kernel.substrate import Module, Substrate
from vishon.kernel.viability import Viability, founding_predicates


CORE_SOURCE = '''\
# The founding carrier. Three variables, no behaviour.
seed = 1
epoch = 0
trace = []
'''

ENCODE_SOURCE = '''\
# E: the private encoding. The key is pinned from outside and never appears
# in source. Nothing outside the program can decode what this produces,
# because the key exists only inside the program's state (I7).


def encode(value):
    return _scramble(repr(value))


def _scramble(text):
    payload = text.encode("utf-8")
    out = bytearray()
    for index, byte in enumerate(payload):
        out.append(byte ^ _key[index % len(_key)])
    return bytes(out)


def decode(blob):
    out = bytearray()
    for index, byte in enumerate(blob):
        out.append(byte ^ _key[index % len(_key)])
    return out.decode("utf-8")
'''

PROPOSE_SOURCE = '''\
# mu: the operator that proposes a change to the program. It reads the
# program's own seed and its own record, and returns a proposal. Nothing
# about *what* to propose is fixed here beyond the founding step; a program
# that wants to become something else rewrites this module, and rewriting it
# is the only way to change what gets proposed (I1, I6).


def propose():
    step = seed + epoch
    if step < 1:
        step = 1
    return _contact(step)


def _contact(step):
    # The founding proposal: touch reality, change nothing.
    return {
        "observe": (_url,),
        "intent": "contact-%d" % step,
    }
'''


def spark_modules() -> tuple[Module, ...]:
    """The founding program, as source."""

    return (
        Module("core", CORE_SOURCE),
        Module("encode", ENCODE_SOURCE),
        Module("propose", PROPOSE_SOURCE),
    )


@dataclass
class Environment:
    """Everything the constitution names, wired together.

    The host apparatus (B, A_P, V_P, M, G_b, the ledger) lives outside S. Only
    the program itself -- the substrate's modules -- is inside S, and only the
    program is rewritable by a change.
    """

    substrate: Substrate
    boundary: Boundary
    viability: Viability
    gateway: Gateway
    father: FatherAuthority
    memory: Memory
    loop: Loop
    ledger: Ledger
    config: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ignite(
        cls,
        *,
        observe_url: str = "https://example.com/",
        allow_domains: Iterable[str] | None = None,
        allow_all: bool = False,
        size_cap: int | None = None,
        gateway_kwargs: dict[str, Any] | None = None,
    ) -> "Environment":
        """Build the environment and take it to the edge of its first step.

        Igniting does not take a step. It seals the genesis state and stops.
        Whether the loop then runs is the caller's decision, not the spark's.
        """

        domain = (observe_url.split("//", 1)[-1].split("/", 1)[0] or "").lower()
        domains = tuple(allow_domains) if allow_domains is not None else (domain,)

        substrate = Substrate(spark_modules())

        boundary = Boundary(**({"size_cap": size_cap} if size_cap else {}))
        viability = Viability(founding_predicates())
        gateway = Gateway(
            allowed_domains=domains,
            allow_all=allow_all,
            **(gateway_kwargs or {}),
        )

        father = FatherAuthority(boundary)
        # The father binds the two things he owns and that the program must
        # not own: the criterion and the gateway policy.
        viability.bind_authority(father.token())
        gateway.bind_authority(father.token())

        memory = Memory(substrate)
        ledger = Ledger()
        loop = Loop(
            substrate=substrate,
            boundary=boundary,
            viability=viability,
            gateway=gateway,
            memory=memory,
            ledger=ledger,
        )

        # The two facts the father supplies at start.
        substrate.pin("_key", os.urandom(32))
        substrate.pin("_url", observe_url)

        # The father acts, so the contour is live from the first turn (I8).
        father.configure_gateway(gateway, allowed_domains=domains, allow_all=allow_all)
        ledger.father_acts = len(father.journal)

        memory.genesis(substrate.snapshot("genesis"))
        ledger.generations = memory.generation

        return cls(
            substrate=substrate,
            boundary=boundary,
            viability=viability,
            gateway=gateway,
            father=father,
            memory=memory,
            loop=loop,
            ledger=ledger,
            config={
                "observe_url": observe_url,
                "domains": domains,
                "allow_all": allow_all,
            },
        )

    # -- convenience -----------------------------------------------------

    def view(self) -> Any:
        """The current program as a read-only projection."""

        from vishon.kernel.modification import ProgramView

        snap = self.substrate.snapshot()
        return ProgramView(modules=dict(snap.modules), pins=dict(snap.state))

    def step(self) -> Any:
        return self.loop.step()

    def run(self, turns: int) -> tuple[Any, ...]:
        return self.loop.run(turns)

    def status(self) -> dict[str, Any]:
        return {
            "generation": self.memory.generation,
            "sealed": self.memory.depth,
            "attempts": self.memory.attempt_count(),
            "rolled_back": self.memory.attempt_count("forbidden")
            + self.memory.attempt_count("error")
            + self.memory.attempt_count("not_viable"),
            "modules": self.substrate.module_names,
            "observations": self.gateway.stats["observations"],
            "contacts": self.ledger.contacts,
            "failed_contacts": self.ledger.failed_observations,
            "father_acts": len(self.father.journal),
        }
