"""A minimal test harness.

The project has no third-party dependencies, and the falsification suite is
part of the constitution rather than an accessory to it, so it ships with its
own runner. Test functions are plain callables named ``test_*``; they raise on
failure and return an optional detail string on success.

The suite is also pytest-compatible: if pytest is present it will discover the
``test_*`` functions directly.
"""

from __future__ import annotations

import traceback
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Result:
    name: str
    passed: bool
    detail: str = ""


def check(fn: Callable[[], str | None]) -> Result:
    try:
        detail = fn() or ""
        return Result(fn.__name__, True, detail)
    except BaseException as exc:
        return Result(
            fn.__name__,
            False,
            f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}",
        )


def run_all(tests: list[Callable[[], str | None]]) -> list[Result]:
    return [check(fn) for fn in tests]


def report(results: list[Result]) -> int:
    passed = sum(1 for r in results if r.passed)
    for result in results:
        mark = "PASS" if result.passed else "FAIL"
        line = f"[{mark}] {result.name}"
        if result.detail:
            line += f" -- {result.detail.splitlines()[0]}"
        print(line)
        if not result.passed:
            for extra in result.detail.splitlines()[1:]:
                print(f"       {extra}")
    print(f"\n{passed}/{len(results)} passed")
    return 0 if passed == len(results) else 1
