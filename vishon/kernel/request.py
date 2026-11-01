"""The assistant surface: a question in, whatever the program authored out.

This module does not answer anything. It is the *port* through which the
father puts a question and reads back what the program produced. What to do
with a question is not written here, in ``spark.py``, or anywhere else in the
repository (I6). A freshly ignited program has no answer behaviour at all --
it has ``propose``, ``encode`` and ``core`` and nothing else -- so a question
asked of it is answered by nothing, and ``Answer.authored`` is False. That is
the honest result, and it is the point: the behaviour has to be invented by
the program, through mu, and sealed by V_P before it exists.

Two names are fixed, and only two:

    _question   the father's binding, holding the question he is asking
    answer      the operator the program must author to respond

``_question`` is a fact, and the boundary protects it so no change can write
it (I9). ``answer`` is an interface port, like ``propose``: the name and the
call signature are the contract, and nothing about the content is. The program
decides how to produce a value, and may produce it however it can -- by
encoding, by reaching reality, by deriving from what it has. This module never
inspects how.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class RequestError(RuntimeError):
    """A question was put or read incorrectly."""


@dataclass(frozen=True)
class Question:
    """What the father is asking. A fact, not an instruction."""

    text: str
    asked_at_generation: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.text, str) or not self.text.strip():
            raise RequestError("a question must be a non-empty string")


@dataclass(frozen=True)
class Answer:
    """What the program produced, with the record of how it came to exist."""

    question: Question
    value: str
    authored: bool
    generation: int
    turns: int = 0
    trace: tuple[str, ...] = field(default_factory=tuple)
    error: str = ""

    def __bool__(self) -> bool:
        return self.authored

    def explain(self) -> str:
        if self.authored:
            return (
                f"authored at generation {self.generation} over {self.turns} turn(s); "
                f"produced by the program's own operator"
            )
        if self.error:
            return (
                f"an answer operator exists but did not produce a value: {self.error}. "
                f"This is the program's own failure, not the port's."
            )
        return (
            "no answer behaviour exists in this program. Nothing in the repository "
            "supplies one: the founding program proposes contact and nothing more. "
            "An answer must be invented by the program itself, through mu, and "
            "sealed by V_P before it can be read back."
        )


class RequestChannel:
    """The father's way of putting a question. Writes a fact, nothing else.

    It holds no gateway and no boundary, so it cannot be used to smuggle an
    answer in (I4, I9). It writes exactly one binding -- ``_question`` -- and
    that binding is protected against the program.
    """

    def __init__(self, substrate: Any, *, protected: bool = True) -> None:
        self._substrate = substrate
        self._protected = protected
        self._current: Question | None = None

    def put(self, text: str, *, generation: int = 0) -> Question:
        """Pin the question the program will be asked to answer."""

        if not self._protected:
            raise RequestError("the question binding must be protected (I9)")
        question = Question(text=text.strip(), asked_at_generation=generation)
        self._substrate.pin("_question", question)
        self._current = question
        return question

    @property
    def current(self) -> Question | None:
        return self._current

    def clear(self) -> None:
        self._current = None
