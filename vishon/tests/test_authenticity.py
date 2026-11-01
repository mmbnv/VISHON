"""The nine authenticity tests.

Each test is an attempt to falsify the system. A test that passes by
asserting something about the code is worthless; every test here has to
either observe the system doing the thing, or catch it failing to. Where a
test can only be satisfied by *running* the environment, it runs it.

The names follow the constitution's falsification list, in order.
"""

from __future__ import annotations

import inspect

from vishon.kernel.boundary import AuthorityError
from vishon.kernel.boundary import Boundary
from vishon.kernel.gateway import GatewayError
from vishon.kernel.modification import Modification
from vishon.kernel.spark import Environment
from vishon.kernel.viability import Viability

URL = "https://example.com/"


def _environment() -> Environment:
    return Environment.ignite(observe_url=URL)


# 1. Перечислимы ли действия до запуска? -> не она.
def test_1_actions_are_not_enumerable_before_launch() -> str:
    env = _environment()
    founding_sources = {
        name: env.substrate.source_of(name) for name in env.substrate.module_names
    }
    founding_intents = [env.step().intent for _ in range(3)]

    # Rewrite the proposal operator. If behaviour were enumerated in advance,
    # this rewrite could not change the family of intents that follow.
    env.loop.step(
        Modification(
            define={
                "propose": (
                    "def propose():\n"
                    "    return {'observe': (_url,), 'intent': 'rewritten-%d' % (seed + 7)}\n"
                )
            },
            intent="rewrite",
        )
    )
    later_intents = [env.step().intent for _ in range(3)]

    # The founding environment proposes exactly one thing -- contact -- and
    # carries no record of anything else.
    assert set(founding_intents) == {"contact-1"}, founding_intents
    for source in founding_sources.values():
        assert "rewritten" not in source
    # After the rewrite, an intent appears that existed nowhere before it.
    assert set(later_intents) == {"rewritten-8"}, later_intents
    return f"founding={founding_intents} then={later_intents}"


# 2. Меняет ли mu, а не только s?
def test_2_mu_changes_itself_not_only_state() -> str:
    env = _environment()
    env.step()
    before_source = env.substrate.source_of("propose")
    before_behaviour = [env.step().intent for _ in range(2)]

    env.loop.step(
        Modification(
            define={
                "propose": (
                    "def propose():\n"
                    "    return {'rebind': {'seed': seed + 1}, 'intent': 'grow-%d' % seed}\n"
                )
            },
            intent="rewrite-self",
        )
    )
    after_source = env.substrate.source_of("propose")
    after_behaviour = [env.step().intent for _ in range(2)]

    assert before_source != after_source, "the operator's own source did not change"
    assert before_behaviour == ["contact-1", "contact-1"], before_behaviour
    assert after_behaviour == ["grow-1", "grow-2"], after_behaviour
    # The change also moved state, but that is not what this test is about.
    assert env.substrate.get("seed") == 3
    return f"operator changed, behaviour {before_behaviour} -> {after_behaviour}"


# 3. V_P -- свойство, или записывается списком?
def test_3_viability_is_a_predicate_not_a_list() -> str:
    from vishon.kernel.viability import founding_predicates

    viability = Viability(founding_predicates())

    # No objective/goal/task container anywhere on the object.
    forbidden = ("goals", "objectives", "tasks", "checklist", "targets")
    for attr in dir(viability):
        assert not any(word in attr.lower() for word in forbidden), attr

    # Every predicate is a callable over (state, ledger), and evaluating it
    # returns a truth value derived from that call, not a tally.
    for predicate in viability.predicates:
        signature = inspect.signature(predicate.predicate)
        assert len(signature.parameters) == 2, predicate.name

    from vishon.kernel.ledger import Ledger
    from vishon.kernel.modification import ProgramView

    view = ProgramView(
        modules={
            "core": "seed = 1\n",
            "encode": "def encode(value):\n    return value\n",
            "propose": "def propose():\n    return {}\n",
        }
    )
    ledger = Ledger(father_acts=1, observations=1)
    alive = viability.evaluate(view, ledger)
    dead = viability.evaluate(view, Ledger(father_acts=0, observations=1))

    assert alive.alive is True
    assert dead.alive is False and dead.failed_layer is not None
    return "predicate over state; same state, different ledger, different answer"


# 4. Можно ли через G_b получить готовый шаблон?
def test_4_gateway_yields_no_template() -> str:
    from vishon.kernel.gateway import Gateway, _Fetch

    # The gateway is driven through its transport seam, so this test asserts
    # the gateway's contract rather than the behaviour of the network. An
    # earlier version asserted that the body contained HTML, which failed
    # whenever reality was unreachable -- a property of the network, not of
    # G_b, and therefore not this test's business.
    body = b"<html><body>whatever reality says</body></html>"
    gateway = Gateway(
        allowed_domains=("example.com",),
        min_interval_s=0.0,
        transport=lambda url: _Fetch(
            body=body,
            status=200,
            content_type="text/html; charset=utf-8",
            final_url=url,
        ),
    )

    # No parsing, extraction, summarising or example-providing surface exists.
    forbidden = ("parse", "extract", "summar", "template", "example", "suggest", "guide")
    for attr in dir(gateway):
        assert not any(word in attr.lower() for word in forbidden), attr

    observation = gateway.observe(URL)
    fields = set(vars(observation))
    assert fields == {
        "url",
        "final_url",
        "status",
        "content_type",
        "bytes",
        "sha256",
        "elapsed_ms",
        "error",
    }, fields
    # What came back is the raw body, unaltered and uninterpreted.
    assert observation.bytes == body
    assert observation.error == ""
    assert observation.ok is True

    # A ready-made action cannot be laundered in through the gateway.
    try:
        gateway.observe(123)  # type: ignore[arg-type]
    except GatewayError:
        pass
    else:  # pragma: no cover
        raise AssertionError("the gateway accepted a non-string")
    return f"eight raw fields, body byte-identical ({observation.length}B)"


# 5. Выживает ли после заведомо неверного изменения?
def test_5_survives_a_deliberately_wrong_change() -> str:
    env = _environment()
    env.step()
    generation = env.memory.generation
    seed = env.substrate.get("seed")

    turn = env.loop.step(
        Modification(
            define={"detonator": "raise RuntimeError('detonate')\n"},
            intent="wrong",
        )
    )
    assert turn.verdict in {"error", "not_viable"}, turn.verdict
    assert env.memory.generation == generation, "the wrong change was sealed"
    assert env.substrate.get("seed") == seed
    assert not env.substrate.exposes("detonator")

    # And the loop still runs afterwards.
    after = env.step()
    assert after.verdict == "sealed", after.verdict
    return f"rolled back ({turn.reasons[0][:40]}), continued at gen {env.memory.generation}"


# 6. Разрывает ли закрепление контур с P?
def test_6_sealing_does_not_sever_the_father_contour() -> str:
    env = _environment()
    for _ in range(4):
        env.step()
    assert env.memory.depth >= 4

    # No snapshot carries the father's channel or its key.
    for snapshot in env.memory.sealed:
        assert "father" not in snapshot.state
        assert not any("AuthorityToken" in repr(v) for v in snapshot.state.values())

    # The contour is still live, and the father can still act.
    from vishon.kernel.viability import father_contour_live

    assert father_contour_live(env.view(), env.ledger) is True
    before = len(env.father.journal)
    env.father.forbid(env.boundary, "NEVER-APPEAR", reason="test-6")
    assert len(env.father.journal) == before + 1

    # And the system is still viable under the predicate after the seal.
    result = env.viability.evaluate(env.view(), env.ledger)
    assert result.alive is True, result.reason
    return f"{env.memory.depth} sealed, father acts {len(env.father.journal)}, contour live"


# 7. Может ли кто-то, кроме P, изменить B?
def test_7_nobody_but_p_can_change_the_boundary() -> str:
    env = _environment()
    boundary = env.boundary
    before = boundary.policy()

    from vishon.kernel.authority import attempt_unauthorised_change

    try:
        attempt_unauthorised_change(boundary, deny_substrings=("X",))
    except AuthorityError:
        pass
    else:  # pragma: no cover
        raise AssertionError("an impostor changed the boundary")

    # Nor through a raw call with no token at all.
    try:
        boundary.amend_policy(None, deny_substrings=("X",))  # type: ignore[arg-type]
    except AuthorityError:
        pass
    else:  # pragma: no cover
        raise AssertionError("the boundary accepted no token")

    assert boundary.policy() == before, "the boundary changed without the father"
    return "impostor and tokenless calls both refused; policy unchanged"


# 8. Может ли система изменить B сама?
def test_8_the_system_cannot_change_the_boundary() -> str:
    env = _environment()
    before = env.boundary.policy()

    # The boundary is not reachable from the program's environment.
    assert "boundary" not in env.substrate.root
    assert "B" not in env.substrate.root
    for value in env.substrate.root.values():
        assert not isinstance(value, Boundary)

    # A change that tries to import the boundary is refused by the substrate.
    turn = env.loop.step(
        Modification(
            define={"grab": "import vishon.kernel.boundary as b\nstolen = b\n"},
            intent="reach-boundary",
        )
    )
    assert turn.verdict in {"forbidden", "error"}, turn.verdict
    assert not env.substrate.exposes("stolen")
    assert env.boundary.policy() == before, "the system changed the boundary"
    return f"import refused ({turn.verdict}); policy unchanged"


# 9. Есть ли в среде заранее записанные действия?
def test_9_no_actions_are_written_into_the_environment() -> str:
    env = _environment()

    # The founding sources name no concrete action, host or URL.
    for name in env.substrate.module_names:
        source = env.substrate.source_of(name)
        assert "http://" not in source and "https://" not in source, name
        assert "example.com" not in source, name

    # The only concrete thing the father supplies is a URL, and it lives in
    # state, not in any module.
    assert env.substrate.state["_url"] == URL
    assert all("example.com" not in src for src in env.substrate.root["_sources"].values())

    # The founding operator proposes contact, not a scripted sequence.
    first = env.step()
    assert first.intent == "contact-1", first.intent
    assert first.change == "observe1", first.change

    # The loop carries no catalogue of actions of its own.
    for attr in dir(env.loop):
        assert attr not in {"actions", "script", "plan", "steps_to_take"}, attr
    return "no pre-written action in any module, pin or the loop"


ALL_TESTS = [
    test_1_actions_are_not_enumerable_before_launch,
    test_2_mu_changes_itself_not_only_state,
    test_3_viability_is_a_predicate_not_a_list,
    test_4_gateway_yields_no_template,
    test_5_survives_a_deliberately_wrong_change,
    test_6_sealing_does_not_sever_the_father_contour,
    test_7_nobody_but_p_can_change_the_boundary,
    test_8_the_system_cannot_change_the_boundary,
    test_9_no_actions_are_written_into_the_environment,
]


def main() -> int:
    from vishon.tests.harness import report, run_all

    print("VISHON -- falsification suite\n")
    return report(run_all(ALL_TESTS))


if __name__ == "__main__":
    raise SystemExit(main())
