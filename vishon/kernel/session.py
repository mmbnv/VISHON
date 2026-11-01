"""The assistant session: the loop, driven with a question outstanding.

An assistant session is not an assistant. It is the same loop the constitution
describes, with one extra fact pinned -- the father's question -- and one
extra port read back, if the program has authored it.

    put the question          the father's act (A_P)
    turn the loop             mu proposes, B filters, G_b touches reality, V_P judges
    read the answer port      if, and only if, the program authored one

No turn is special. The session does not tell the program that a question is
outstanding, does not hint at what an answer would look like, and does not
supply one when the program has none. It reports ``authored=False`` and says
why. The behaviour has to arrive through mu, or it does not arrive.

Task completion is deliberately not a viability condition. V_P answers "is
this state alive", not "has this state finished the job" -- making them the
same would mean a program that has not yet answered *dies*, and would forbid
the exploratory turns it needs in order to author anything at all. The
question sits in state as pressure; survival stays survival.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from vishon.kernel.request import Answer, Question, RequestChannel


ANSWER_OPERATOR = "answer"


@dataclass
class AssistantSession:
    """Drives an ignited environment with a question outstanding."""

    environment: Any
    channel: RequestChannel

    @classmethod
    def open(cls, environment: Any) -> "AssistantSession":
        channel = RequestChannel(environment.substrate)
        return cls(environment=environment, channel=channel)

    # -- the father's act ------------------------------------------------

    def put(self, question: str) -> Question:
        """Pin the question. This is a fact the program may read (I9)."""

        return self.channel.put(question, generation=self.environment.memory.generation)

    # -- reading back ----------------------------------------------------

    def ask(self, question: str, *, max_turns: int = 8) -> Answer:
        """Put a question, turn the loop, read back whatever was authored.

        Returns an ``Answer`` whose ``authored`` flag says whether the program
        produced the value or whether the port came back empty.
        """

        asked = self.put(question)
        env = self.environment
        trace: list[str] = []

        for _ in range(max_turns):
            turn = env.step()
            trace.append(f"{turn.verdict}:{turn.intent or '-'}")
            if env.substrate.exposes(ANSWER_OPERATOR):
                break

        if not env.substrate.exposes(ANSWER_OPERATOR):
            return Answer(
                question=asked,
                value="",
                authored=False,
                generation=env.memory.generation,
                turns=len(trace),
                trace=tuple(trace),
            )

        try:
            produced = env.substrate.call(ANSWER_OPERATOR, asked)
        except BaseException as exc:
            return Answer(
                question=asked,
                value="",
                authored=False,
                generation=env.memory.generation,
                turns=len(trace),
                trace=tuple(trace),
                error=f"{type(exc).__name__}: {exc}",
            )

        return Answer(
            question=asked,
            value=produced if isinstance(produced, str) else str(produced),
            authored=True,
            generation=env.memory.generation,
            turns=len(trace),
            trace=tuple(trace),
        )

    # -- introspection ---------------------------------------------------

    @property
    def has_answer_operator(self) -> bool:
        return self.environment.substrate.exposes(ANSWER_OPERATOR)

    @property
    def question(self) -> Question | None:
        return self.channel.current

    def provenance(self) -> dict[str, Any]:
        """Where the current answer behaviour came from, if there is one."""

        env = self.environment
        if not env.substrate.exposes(ANSWER_OPERATOR):
            return {"present": False, "source": "", "sealed_at": None}

        sealed_at = None
        for snapshot in env.memory.sealed:
            if ANSWER_OPERATOR in snapshot.modules:
                sealed_at = snapshot.label
                break
        return {
            "present": True,
            "source": env.substrate.source_of(ANSWER_OPERATOR),
            "sealed_at": sealed_at,
        }
