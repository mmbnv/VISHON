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
vishon/kernel/request.py     the question/answer port: Question, Answer
vishon/kernel/session.py     AssistantSession: ask() and provenance()
vishon/tests/                the falsification and machinery suites
```

## Commands

```bash
python -m vishon run --turns 10     # ignite and turn the loop
python -m vishon test               # all 28 tests
python -m vishon ask "..."          # put a question, read back the authored answer
python -m vishon.tests.test_authenticity
python -m vishon.tests.test_kernel
```

No third-party dependencies. The test harness is in `vishon/tests/harness.py`
and is also pytest-compatible.

## The assistant surface

`ask()` is a **port, not a behaviour**. It puts `_question` (the father's fact,
protected by `B`) and reads back `answer` (the program's operator, if it has
authored one). It never supplies an answer itself.

If you are tempted to "make the assistant work" by writing an answerer into the
kernel: that is the one thing this project forbids. It would violate I6 and I10
and the prohibition on pre-written behaviour. The empty answer is the product.
Author it through μ, in a change, or do not have one.

**Task completion is deliberately not a viability predicate.** Do not add one.
`V_P` answers "is this state alive"; making it answer "has it finished the job"
means a program that has not yet answered *dies*, and loses the exploratory
turns it needs in order to author anything at all.

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

**The father's bindings are protected by policy.** `protect_names` refuses any
change that rebinds `_key`, `_url` or `_question`. Before this
existed, a change could steal the encoding key and redirect the gateway URL —
verified, not theoretical. If you add another father-owned binding, add it to
`protect_names` in `Environment.ignite`, or the program can write it.

**Attribute access is checked two ways, and both are needed.** The boundary
refuses `__class__`-style attribute *syntax* and also any string constant
containing a dunder, because `"{0.__class__}".format(x)` hides an escape in a
string. `getattr`, `setattr` and `delattr` are removed from builtins outright:
a name can be assembled at runtime, and no static check can see that. This
matters because `answer(question)` hands a *host object* into the sandbox —
reaching its class reaches every class. Verified: `_SSLSocket` and
`_TemporaryFileWrapper` were reachable before this was closed.

**`Environment.ignite()` does not take a step.** It seals the genesis state
and stops. Whether the loop runs is the caller's decision.

**`status()["sealed"]` is not "did anything happen".** It is M's depth, which
already counts the genesis state, so it is never 0. `ledger.sealed` counts
turns that sealed in this run, and that is what a diagnostic should key on.
Keying on the wrong one silently disables the diagnostic — which is exactly
how the offline case came to print `not_viable` with no explanation.

**A transport that raises must not escape the gateway.** The default
`_fetch_over_network` returns an errored observation rather than raising, and
a substituted transport now gets the same treatment. Anything else lets a
network failure take the whole loop down.

## When adding an invariant test

Add it to `vishon/tests/test_authenticity.py` if it falsifies the *system*,
and to `test_kernel.py` if it exercises a *piece* under abuse. The authenticity
tests should observe behaviour, not assert properties of source code, wherever
that is possible.
