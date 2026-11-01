"""Command line entry point.

    python -m vishon run [--turns N] [--url URL]
    python -m vishon test
    python -m vishon status

``run`` ignites the environment and lets the loop turn. It prints what
happened, and it prints nothing that the environment did not produce.
"""

from __future__ import annotations

import argparse

from vishon.kernel.spark import Environment

DEFAULT_URL = "https://example.com/"


def _run(args: argparse.Namespace) -> int:
    env = Environment.ignite(observe_url=args.url, allow_all=args.allow_all)
    print("ignited. modules:", ", ".join(env.substrate.module_names))
    print("genesis sealed at generation", env.memory.generation)
    print()
    failures = 0
    for _ in range(args.turns):
        turn = env.step()
        mark = {"sealed": "+", "forbidden": "x", "not_viable": "x", "error": "!"}[turn.verdict]
        contact = ""
        if turn.observations:
            contact = " reached" if turn.observed_ok else " UNREACHED"
            failures += turn.observation_failures
        line = (
            f"[{mark}] {turn.index:>3} {turn.verdict:<10} "
            f"{turn.intent or '-':<18} {turn.change}{contact}"
        )
        if turn.reasons:
            line += f"  <- {turn.reasons[0]}"
        print(line)
    print()
    for key, value in env.status().items():
        print(f"  {key}: {value}")
    if failures:
        print()
        print(
            f"  note: {failures} of {env.gateway.stats['observations']} contacts did "
            f"not arrive. The gateway returned an error and an empty body, which "
            f"is the raw fact; whether that counts as contact is the reality "
            f"layer's call, and it does not."
        )
    return 0


def _test(_args: argparse.Namespace) -> int:
    from vishon.tests import test_authenticity, test_kernel
    from vishon.tests.harness import report, run_all

    print("=== falsification suite (the nine authenticity tests) ===\n")
    first = report(run_all(test_authenticity.ALL_TESTS))
    print("\n=== machinery suite (per-stage, under abuse) ===\n")
    second = report(run_all(test_kernel.ALL_TESTS))
    return first or second


def _status(args: argparse.Namespace) -> int:
    env = Environment.ignite(observe_url=args.url, allow_all=args.allow_all)
    for key, value in env.status().items():
        print(f"{key}: {value}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vishon", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="ignite and let the loop turn")
    run.add_argument("--turns", type=int, default=5)
    run.add_argument("--url", default=DEFAULT_URL)
    run.add_argument("--allow-all", action="store_true")
    run.set_defaults(func=_run)

    test = sub.add_parser("test", help="run the falsification and machinery suites")
    test.set_defaults(func=_test)

    status = sub.add_parser("status", help="show the ignited environment's status")
    status.add_argument("--url", default=DEFAULT_URL)
    status.add_argument("--allow-all", action="store_true")
    status.set_defaults(func=_status)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
