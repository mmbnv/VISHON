# AGENTS.md

Repository-specific knowledge for agents working in VISHON.

## What this repository is

VISHON implements a constitution: `𝒮 = ⟨S, μ, V_P, M, B, G_b, E, A_P⟩`. The
project's purpose is to build *conditions* under which behaviour can arise, not
to write behaviour. Read `README.md` before changing anything; it maps each
constitutional element to its module.

## Non-negotiable rules for changes

These are the constitution's prohibitions, and they apply to you as much as to
the system:

1. Do not write behaviour, patterns, examples or scenarios into the system.
2. Do not hand the system ready-made actions through `G_b`.
3. Do not let anyone but P change `B`, and never let the system change it.
4. Do not bypass `B`, `V_P` or rollback "for the sake of a demonstration".
5. Do not substitute lists for conditions. If you find yourself adding an
   `objectives` or `actions` container, stop: `V_P` is a predicate (I2) and the
   loop delegates rather than decides.

## Layout

```
vishon/constitution.py       the invariants, loop order and layers, as data
vishon/kernel/substrate.py   S: modules + persistent state, guarded execution
vishon/kernel/snapshot.py    immutable snapshots of S
vishon/kernel/modification.py Modification and ProgramView
vishon/kernel/boundary.py    B: structural rules + P-owned policy
vishon/kernel/authority.py   A_P: the father's token and journalled acts
vishon/kernel/viability.py   V_P: layered predicates over (state, ledger)
vishon/kernel/ledger.py      host-side history that predicates need
vishon/kernel/memory.py      M: sealed states, attempts, rollback
vishon/kernel/gateway.py     G_b: raw observation, nothing else
vishon/kernel/loop.py        the ordered loop
vishon/kernel/spark.py       the spark + Environment.ignite()
vishon/tests/                the falsification and machinery suites
```

## Commands

```bash
python -m vishon run --turns 10     # ignite and turn the loop
python -m vishon test               # all 27 tests
python -m vishon.tests.test_authenticity
python -m vishon.tests.test_kernel
```

No third-party dependencies. The test harness is in `vishon/tests/harness.py`
and is also pytest-compatible.

## Things that will bite you

**Code and persistent state are separate, on purpose.** Module source is
re-executed from a clean root on every change; persistent bindings
(`substrate.pin`) survive. A change that assigns a persistent variable at
module top level will fail with `NameError` on the next re-execution, because
the clean root does not have it yet. That failure is handled as an error and
rolled back — but it is a signal you are using the wrong mechanism. Use
`rebind` in a proposal, not a top-level assignment.

**The reality layer requires at least one *arriving* observation.** A state with
`ledger.contacts == 0` is not viable. A failed fetch counts as an observation
but not as contact, so a run whose every fetch fails stays not viable and rolls
back. Any test that expects a change to be sealed must take the contact step
first, or include `observe` in the modification. This catches people writing
tests.

**The gateway has a transport seam.** `Gateway(transport=...)` substitutes the
network call without changing anything about how the result is handled. Use it
in tests so they do not depend on reality being reachable. The default
transport is `Gateway._fetch_over_network`.

**`ProgramView` is the only thing `B` and `V_P` may see.** If a rule needs to
know something, add it to the view or the ledger. Do not pass the environment
in. That would break I9 structurally.

**The structural boundary rules are frozen.** `Boundary._structural` is set in
`__init__` and has no mutation path. `size_cap` in the policy layer is clamped
to `STRUCTURAL_SIZE_CAP`.

**`Environment.ignite()` does not take a step.** It seals the genesis state
and stops. Whether the loop runs is the caller's decision.

## When adding an invariant test

Add it to `vishon/tests/test_authenticity.py` if it falsifies the *system*,
and to `test_kernel.py` if it exercises a *piece* under abuse. The authenticity
tests should observe behaviour, not assert properties of source code, wherever
that is possible.
