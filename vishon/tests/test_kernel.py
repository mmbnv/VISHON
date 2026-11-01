"""Per-stage tests for the machinery.

The authenticity suite asks whether the whole thing is what it claims to be.
This suite asks whether each piece behaves under abuse. Both are needed: a
piece that fails under abuse will eventually be abused.
"""

from __future__ import annotations

from vishon.kernel.authority import FatherAuthority
from vishon.kernel.boundary import Boundary
from vishon.kernel.gateway import Gateway, GatewayError
from vishon.kernel.ledger import Ledger
from vishon.kernel.memory import Memory
from vishon.kernel.modification import Modification, ProgramView
from vishon.kernel.spark import Environment
from vishon.kernel.substrate import Module, Substrate
from vishon.kernel.viability import (
    LayeredPredicate,
    Viability,
    founding_predicates,
)
from vishon.constitution import ViabilityLayer

URL = "https://example.com/"


# -- Stage 1: substrate -------------------------------------------------


def test_substrate_reexecutes_deterministically() -> str:
    substrate = Substrate(
        [
            Module("a", "x = 1\n"),
            Module("b", "y = x + 1\n"),
        ]
    )
    assert substrate.get("y") == 2
    substrate.apply(define={"c": "z = y * 10\n"})
    assert substrate.get("z") == 20
    substrate.execute()
    assert substrate.get("z") == 20
    return "re-execution reproduces the same bindings"


def test_substrate_rolls_back_on_failed_execution() -> str:
    substrate = Substrate([Module("a", "x = 1\n")])
    before = substrate.snapshot()
    try:
        substrate.apply(define={"bad": "raise ValueError('no')\n"})
    except ValueError:
        pass
    else:  # pragma: no cover
        raise AssertionError("the failing change was accepted")
    assert substrate.snapshot().content_digest == before.content_digest
    assert substrate.get("x") == 1
    return "substrate returned to its previous configuration"


def test_substrate_isolation_blocks_escape() -> str:
    substrate = Substrate([Module("a", "x = 1\n")])
    blocked = []
    for source in (
        "import os\n",
        "import subprocess\n",
        "q = open('/etc/passwd')\n",
        "q = eval('1+1')\n",
        "q = __import__('os')\n",
    ):
        try:
            substrate.apply(define={"probe": source})
        except BaseException as exc:
            blocked.append(type(exc).__name__)
        else:  # pragma: no cover
            raise AssertionError(f"escape not blocked: {source!r}")
    assert substrate.get("x") == 1
    return f"blocked: {sorted(set(blocked))}"


def test_substrate_separates_state_from_code() -> str:
    substrate = Substrate([Module("core", "seed = 1\n")])
    substrate.pin("_key", b"secret")
    # Re-execution keeps the pin.
    substrate.apply(define={"more": "epoch = seed + 1\n"})
    assert substrate.get("_key") == b"secret"
    assert substrate.get("epoch") == 2
    # A failing change leaves the pin alone.
    try:
        substrate.apply(define={"bad": "raise RuntimeError()\n"})
    except RuntimeError:
        pass
    assert substrate.get("_key") == b"secret"
    return "pins survive re-execution and failed changes"


# -- Stage 2: mu --------------------------------------------------------


def test_mu_is_encoded_in_s_and_reaches_itself() -> str:
    env = Environment.ignite(observe_url=URL)
    assert "propose" in env.substrate.module_names
    # The operator's own source is readable from inside the program.
    source = env.substrate.root["_sources"]["propose"]
    assert "def propose" in source
    # Reality contact is the mandatory third step, so a run starts by taking
    # one; after that a change with no observation is still viable.
    env.step()
    # A change may replace the operator, and the replacement is what runs next.
    turn = env.loop.step(
        Modification(
            define={"propose": "def propose():\n    return {'intent': 'from-inside'}\n"},
            intent="self",
        )
    )
    assert turn.verdict == "sealed", turn
    assert env.substrate.source_of("propose").count("from-inside") == 1
    assert env.step().intent == "from-inside"
    return "operator read and rewrote itself; the rewrite governs the next step"


# -- Stage 3: boundary --------------------------------------------------


def test_boundary_structural_rules_cannot_be_changed_by_father() -> str:
    boundary = Boundary()
    father = FatherAuthority(boundary)
    father.forbid(boundary, "FRAGMENT")
    # Policy changed; structural rules did not, and cannot.
    assert boundary.structural_rule_names == (
        "parseable",
        "imports_inside_S",
        "no_escape_attributes",
        "size_bound",
    )
    verdict = boundary.check(
        Modification(define={"m": "import os\n"}),
        ProgramView(modules={"m": "import os\n"}),
    )
    assert not verdict.allowed
    return "father owns policy, not structure"


def test_boundary_checks_candidate_not_current() -> str:
    boundary = Boundary()
    current = ProgramView(modules={"m": "a = 1\n"})
    candidate = ProgramView(modules={"m": "import socket\n"})
    assert boundary.check(Modification(), current).allowed
    assert not boundary.check(Modification(define={"m": "import socket\n"}), candidate).allowed
    return "the verdict is about the program that would result"


def test_boundary_size_cap_can_be_lowered_not_raised() -> str:
    boundary = Boundary(size_cap=500)
    father = FatherAuthority(boundary)
    father.amend_boundary(boundary, size_cap=10_000_000)
    assert boundary.policy()["size_cap"] == 500, "policy raised the hard cap"
    father.amend_boundary(boundary, size_cap=100)
    assert boundary.policy()["size_cap"] == 100
    return "hard cap is a ceiling, not a default"


# -- Stage 4: viability -------------------------------------------------


def test_viability_layers_short_circuit_in_order() -> str:
    order: list[str] = []

    def make(name: str, layer: ViabilityLayer, alive: bool):
        def predicate(_view, _ledger, _name=name, _alive=alive):
            order.append(_name)
            return _alive

        return LayeredPredicate(name, layer, "test", predicate)

    viability = Viability(
        [
            make("father", ViabilityLayer.FATHER, False),
            make("reality", ViabilityLayer.REALITY, True),
            make("viability", ViabilityLayer.VIABILITY, True),
        ]
    )
    result = viability.evaluate(ProgramView(modules={}), Ledger())
    assert not result.alive
    assert order == ["father"], f"layers did not short-circuit: {order}"
    assert result.failed_layer is ViabilityLayer.FATHER
    return "father layer dead ends the evaluation before reality is consulted"


def test_viability_predicates_are_refined_only_by_father() -> str:
    boundary = Boundary()
    father = FatherAuthority(boundary)
    viability = Viability(founding_predicates())
    viability.bind_authority(father.token())

    def extra(_view, _ledger):
        return True

    father.refine_viability(
        viability, LayeredPredicate("extra", ViabilityLayer.VIABILITY, "t", extra)
    )
    assert "extra" in {p.name for p in viability.predicates}

    from vishon.kernel.authority import _ImpostorToken

    try:
        viability.refine(  # type: ignore[arg-type]
            _ImpostorToken(),
            LayeredPredicate("sneak", ViabilityLayer.VIABILITY, "t", extra),
        )
    except Exception:
        pass
    else:  # pragma: no cover
        raise AssertionError("an impostor refined the predicate set")
    return "only the father's token refines the predicate set"


# -- Stage 5: memory ----------------------------------------------------


def test_memory_rollback_never_raises_and_never_loses_a_seal() -> str:
    substrate = Substrate([Module("a", "x = 1\n")])
    memory = Memory(substrate)
    memory.genesis(substrate.snapshot("g"))
    depth = memory.depth

    # A snapshot whose source cannot execute: rollback must fall back.
    substrate.define(Module("broken", "raise RuntimeError('boom')\n"))
    result = memory.rollback(reason="test")
    assert result.ok, result.detail
    assert memory.depth == depth, "a seal was lost"
    assert substrate.get("x") == 1
    return "rollback fell back to a restorable seal and lost nothing"


def test_memory_records_errors_without_dying() -> str:
    env = Environment.ignite(observe_url=URL)
    for _ in range(3):
        env.loop.step(Modification(define={"bad": "raise RuntimeError()\n"}, intent="bad"))
    assert env.memory.attempt_count("error") == 3
    assert env.memory.generation == 1
    return "three errors journalled, generation unchanged"


# -- Stage 6: gateway and E ---------------------------------------------


def test_gateway_refuses_non_url_and_off_allowlist() -> str:
    gateway = Gateway(allowed_domains=("example.com",))
    for bad in (123, None, b"bytes", {"url": URL}):
        try:
            gateway.observe(bad)
        except GatewayError:
            continue
        raise AssertionError(f"gateway accepted {bad!r}")
    try:
        gateway.observe("https://not-allowed.example.net/")
    except GatewayError:
        pass
    else:  # pragma: no cover
        raise AssertionError("gateway reached an off-allowlist host")
    assert gateway.stats["refused"] >= 5
    return "non-strings and off-allowlist hosts refused"


def test_gateway_unreachable_reality_is_not_contact() -> str:
    from vishon.kernel.gateway import _Fetch

    # A transport that cannot arrive.
    def unreachable(url):
        return (b"", 0, "", url, "URLError: connection refused")

    env = Environment.ignite(observe_url=URL)
    env.gateway._transport = unreachable  # type: ignore[assignment]

    turn = env.loop.step()
    assert turn.observations == 1, "a failed fetch is still an observation"
    assert turn.observation_failures == 1
    assert turn.observed_ok is False
    # It is not contact, so the reality layer refuses the state.
    assert turn.verdict == "not_viable", turn
    assert env.ledger.contacts == 0
    assert env.ledger.observations == 1

    # And once reality is reachable, the same state is viable.
    env.gateway._transport = lambda url: _Fetch(b"ok", 200, "text/plain", url)
    turn = env.loop.step()
    assert turn.verdict == "sealed", turn
    assert env.ledger.contacts == 1
    return "failed fetch counted as an observation, not as contact"


def test_encoding_key_lives_only_in_state() -> str:
    env = Environment.ignite(observe_url=URL)
    key = env.substrate.state["_key"]
    assert isinstance(key, bytes) and len(key) == 32
    for name in env.substrate.module_names:
        assert repr(key) not in env.substrate.source_of(name)
    # Two runs have different keys.
    other = Environment.ignite(observe_url=URL)
    assert other.substrate.state["_key"] != key
    return "key is random per run and appears in no source"


# -- Stage 7: loop ------------------------------------------------------


def test_loop_order_boundary_before_gateway() -> str:
    env = Environment.ignite(observe_url=URL)
    calls: list[str] = []
    real_observe = env.gateway.observe

    def spy_observe(url):
        calls.append("gateway")
        return real_observe(url)

    env.gateway.observe = spy_observe  # type: ignore[method-assign]

    # A forbidden change that also asks for contact must never reach G_b.
    turn = env.loop.step(
        Modification(
            define={"x": "import os\n"},
            observe=(URL,),
            intent="forbidden-with-contact",
        )
    )
    assert turn.verdict == "forbidden"
    assert calls == [], f"the gateway was reached before the boundary: {calls}"

    # An allowed change that asks for contact does reach G_b.
    turn = env.loop.step(Modification(observe=(URL,), intent="contact"))
    assert turn.verdict == "sealed"
    assert calls == ["gateway"], calls
    return "boundary consulted before the gateway, in that order"


def test_loop_delegates_every_decision() -> str:
    env = Environment.ignite(observe_url=URL)
    env.step()  # the mandatory contact step
    turn = env.loop.step(Modification(define={"x": "x = 1\n"}, intent="delegate"))
    assert turn.verdict == "sealed", turn
    assert env.memory.generation == 3
    # The loop holds no catalogue of its own.
    source = open("vishon/kernel/loop.py").read()
    for word in ("if intent ==", "actions =", "script ="):
        assert word not in source, word
    return "loop advanced by delegation, not by its own rules"


# -- invariants ---------------------------------------------------------


def test_invariants_are_encoded_and_addressable() -> str:
    from vishon.constitution import CONSTITUTION

    assert len(CONSTITUTION.invariants) == 10
    for number in [f"I{i}" for i in range(1, 11)]:
        assert CONSTITUTION.invariant(number).statement
    assert len(CONSTITUTION.loop) == 6
    assert len(CONSTITUTION.layers) == 3
    return "10 invariants, 6 loop steps, 3 layers, all addressable"


def test_environment_status_is_self_consistent() -> str:
    env = Environment.ignite(observe_url=URL)
    env.step()
    env.loop.step(Modification(define={"bad": "raise RuntimeError()\n"}, intent="bad"))
    env.step()
    status = env.status()
    assert status["generation"] == 3, status
    assert status["sealed"] == 3, status
    assert status["rolled_back"] == 1, status
    assert status["attempts"] == 3, status
    return f"generation {status['generation']}, {status['rolled_back']} rolled back"


ALL_TESTS = [
    test_substrate_reexecutes_deterministically,
    test_substrate_rolls_back_on_failed_execution,
    test_substrate_isolation_blocks_escape,
    test_substrate_separates_state_from_code,
    test_mu_is_encoded_in_s_and_reaches_itself,
    test_boundary_structural_rules_cannot_be_changed_by_father,
    test_boundary_checks_candidate_not_current,
    test_boundary_size_cap_can_be_lowered_not_raised,
    test_viability_layers_short_circuit_in_order,
    test_viability_predicates_are_refined_only_by_father,
    test_memory_rollback_never_raises_and_never_loses_a_seal,
    test_memory_records_errors_without_dying,
    test_gateway_refuses_non_url_and_off_allowlist,
    test_gateway_unreachable_reality_is_not_contact,
    test_encoding_key_lives_only_in_state,
    test_loop_order_boundary_before_gateway,
    test_loop_delegates_every_decision,
    test_invariants_are_encoded_and_addressable,
    test_environment_status_is_self_consistent,
]


def main() -> int:
    from vishon.tests.harness import report, run_all

    print("VISHON -- machinery suite\n")
    return report(run_all(ALL_TESTS))


if __name__ == "__main__":
    raise SystemExit(main())
