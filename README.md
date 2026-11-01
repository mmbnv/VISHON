# VISHON

A computational environment that is its own author. Its brain and its code are
one object. It changes itself, checks whether the change is viable, seals what
survives and rolls back the rest. The internet is its proving ground. The only
boundary is the father's.

This is not a program that executes commands, and not a model trained on
someone else's examples. It is a carrier with a rule of transition, and the
behaviour it produces is not written down anywhere in advance.

---

## The constitution, and where each part lives

`𝒮 = ⟨S, μ, V_P, M, B, G_b, E, A_P⟩`

| Element | What it is | Where |
|---|---|---|
| `S` | state space: the mutable Python substrate (code + persistent state) | `vishon/kernel/substrate.py` |
| `μ` | self-modification operator, encoded *inside* S | the `propose` module of the founding program, `vishon/kernel/spark.py` |
| `V_P` | viability as a predicate over state, in three ordered layers | `vishon/kernel/viability.py` |
| `M` | memory of sealed states, with rollback | `vishon/kernel/memory.py` |
| `B` | boundary predicate: admissible / forbidden | `vishon/kernel/boundary.py` |
| `G_b` | private sensorimotor gateway: raw observation only | `vishon/kernel/gateway.py` |
| `E` | private encoding, `E ∈ S`, no external semantics | the `encode` module of the founding program |
| `A_P` | the father's authority channel, isolated from `G_b` | `vishon/kernel/authority.py` |
| — | the ordered loop | `vishon/kernel/loop.py` |
| — | the spark and the assembled environment | `vishon/kernel/spark.py` |
| — | the assistant surface (question in, authored answer out) | `vishon/kernel/request.py`, `vishon/kernel/session.py` |
| — | the constitution itself, as addressable data | `vishon/constitution.py` |

## The loop, in the mandatory order

```
1. mu proposes a change in the Python environment
2. B: forbidden? -> rollback, without exception
3. G_b: interaction with reality (search / check)
4. V_P: viability, including the contour with the father
5. alive -> seal in M; not alive -> rollback
6. repeat
```

The order is not a convention. Step 2 runs before step 3 because the boundary
is the first filter and reality is the second: a forbidden change must not
touch the network before it is refused. Step 4 runs after step 3 because
viability is judged on the state *as it is after contact with reality*.
`test_loop_order_boundary_before_gateway` falsifies the ordering by spying on
the gateway.

### What counts as contact

A fetch that fails still produces an observation — an error and an empty body
are the raw facts, and hiding them would be a lie about reality. But a failed
fetch is not *contact*, and the reality layer is not satisfied by it:

```
$ python -m vishon run --turns 3 --url https://unreachable.invalid/
[x]   1 not_viable contact-1   observe1 UNREACHED  <- reality layer: reality_contact
...
  observations: 3   contacts: 0   failed_contacts: 3
```

The ledger counts `observations` (attempts) and `contacts` (arrivals)
separately, and `reality_contact` tests `contacts`. A run that never arrived
anywhere has not touched reality, and a state that has not touched reality is
not alive.

## Run it

```bash
python -m vishon run --turns 10      # ignite, let the loop turn, print what happened
python -m vishon test                # the falsification suite and the machinery suite
python -m vishon status              # the ignited environment's state
python -m vishon ask "a question"    # put a question to it, as an assistant
```

No dependencies. Python 3.11+.

## Using it as an assistant

The assistant surface is a **port, not a behaviour**. The father puts a
question in; the loop turns; whatever the program authored is read back.

```bash
$ python -m vishon ask "What is the capital of France?"
question: What is the capital of France?
generation: 4 | turns: 3
trace: sealed:contact-1 sealed:contact-1 sealed:contact-1

answer: (none)
provenance: no answer behaviour exists in this program. Nothing in the
repository supplies one: the founding program proposes contact and nothing
more. An answer must be invented by the program itself, through mu, and
sealed by V_P before it can be read back.
```

That empty answer is the correct result, and it is the whole point. Nothing in
this repository answers a question. A freshly ignited program has `core`,
`encode` and `propose` and nothing else, so a question asked of it is answered
by nothing. Writing an answerer here would violate I6 ("no concrete behaviour
is prescribed from outside") and I10 ("no pre-written actions") — and would
leave a working chatbot with a dead constitution.

Two names are fixed, and only two:

| Name | Kind | Who writes it |
|---|---|---|
| `_question` | a fact: the father's question | the father (A_P); protected by `B` |
| `answer` | a port: the operator the program must author | the program, through μ |

The program authors `answer` itself, like any other change:

```python
# The program's own act, through mu -- nothing here ships with the kernel.
env.loop.step(Modification(define={"answer":
    "def answer(question):\n"
    "    return encode({'echo': question.text, 'gen': epoch})\n"
}, intent="author-answer"))
```

After that seals, the port returns what the program produced — including when
what it produced is its own private encoding, which nothing outside can decode
(I7). `python -m vishon ask "..." --show-source` prints the operator the
program wrote.

### Two things the design deliberately does not do

**Task completion is not a viability condition.** `V_P` answers "is this state
alive", not "has it finished the job". If an outstanding question made a state
unviable, a program that had not yet answered would *die*, and would be
forbidden the exploratory turns it needs in order to author anything at all.
The question sits in state as pressure; survival stays survival. An answer
operator that raises at call time therefore seals — the program is still alive
— and the failure surfaces at the port as `Answer.error`.

**The port never invents an answer.** When no operator exists it returns
`authored=False` and says why. When one exists but fails, it returns the error.
It does not fall back to a template, a summary, or a plausible-looking string.

---

## The falsification suite

Nine tests, in the constitution's order. Each one tries to falsify the system.
None of them assert a property of the code; each either watches the system do
the thing or catches it failing to.

| # | Test | What it does |
|---|---|---|
| 1 | actions are not enumerable before launch | the founding environment proposes exactly one thing; after `propose` is rewritten, an intent appears that existed nowhere before |
| 2 | `μ` changes itself, not only state | rewrites `propose`'s source; the next steps are governed by the new operator |
| 3 | `V_P` is a predicate, not a list | no objective container exists; the same state with a different ledger gives a different answer |
| 4 | `G_b` yields no template | eight raw fields; the returned body is byte-identical to what the transport produced; a non-string is refused |
| 5 | survives a deliberately wrong change | a detonating module is rolled back, the generation does not advance, the loop continues |
| 6 | sealing does not sever the father contour | no snapshot carries the channel or the key; the father still acts after many seals |
| 7 | nobody but P can change `B` | an impostor token and a tokenless call are both refused; policy unchanged |
| 8 | the system cannot change `B` | `B` is unreachable from the program's root; importing it is refused by the substrate |
| 9 | no action is pre-written into the environment | no module contains a URL or a concrete action; the loop carries no catalogue |

`python -m vishon test` runs these plus eighteen machinery tests that exercise
each element under abuse.

---

## Invariants, and how each is held

| # | Invariant | How it is held |
|---|---|---|
| I1 | `μ ∈ S`; the operator changes itself | `propose` is a module of `S`; it can rewrite its own source, and `_sources` lets a change read itself |
| I2 | `V_P` is a predicate, not a list of goals | `Viability` holds `LayeredPredicate` callables over `(state, ledger)`; there is no objective type |
| I3 | `M` supports rollback; error does not kill the system | `Memory.rollback` cannot raise; it falls back through earlier seals; `Loop.step` catches every exception from a change |
| I4 | `G_b` transmits no templates, examples or ready-made actions | `Gateway.observe` returns eight raw fields and nothing else; a fetch that fails is an observation, not contact |
| I5 | the start is not empty: spark + P as boundary | the spark has carrier, transition rule, criterion, memory, gateway; the father binds `B` and `V_P` before the first turn |
| I6 | no concrete behaviour is prescribed from outside | the founding operator proposes contact and nothing more; the loop asks `propose` rather than deciding |
| I7 | private encoding `E ∈ S`; no external semantics | the key is random per run, lives only in persistent state, and appears in no source |
| I8 | sealing does not break the contour with P | the contour lives in host apparatus (`A_P`, the ledger), outside any snapshot |
| I9 | only P owns `B`; the system cannot change `B`; `A_P` is isolated from `G_b` | policy needs a keyed-digest token; `B` is absent from the program's root; the gateway refuses non-URL objects; `protect_names` stops a change rebinding `_key`, `_url` or `_question` |
| I10 | the environment is isolated; `μ` changes code inside it | guarded `builtins` (no `open`/`exec`/`eval`/`getattr`), an import allowlist, an AST escape-rule that also scans string constants, and a hard size cap |

---

## Where the design makes a choice, and why

**Code and persistent state are separate.** `S` is a program; its state is the
environment that program produces. Persistent bindings (the encoding key, the
last observation) live outside the modules and are applied after execution.
Without this split, re-execution would either lose state or leave stale
bindings behind, and rollback would be unsound. See
`test_substrate_separates_state_from_code`.

**`B` and `V_P` never see host apparatus.** `B.check` and `V_P.evaluate`
receive a `ProgramView`, which holds module sources and pinned values only. No
rule and no predicate can be written against the loop, memory, the gateway or
the father's channel, because those objects are not reachable from a view.
This is what makes I9 structural rather than a matter of discipline.

**Structural boundary rules are frozen.** `B` has two layers: `structural`,
fixed at construction and untouchable even by P, and `policy`, owned by P
alone. The size cap is a hard ceiling that policy may lower but never raise.

**The gateway is deliberately small.** It has no parser, no extractor, no
summariser. That is the whole point of I4: if the system wants meaning out of
a response, it has to produce that meaning itself. Its transport is a seam, so
its contract can be tested without depending on the network — an earlier
version of test 4 asserted the body contained HTML, which failed whenever
reality was unreachable, and that was a defect in the test, not in `G_b`.

**Isolation is containment, not a security sandbox.** The substrate removes
`open`, `exec`, `eval`, `compile`, `__import__` and friends from executed code,
and allows imports only from an explicit list. This stops a change from
escaping by accident. It is not claimed to stop a determined adversary, and
`vishon/kernel/substrate.py` says so. Claiming otherwise would be dishonest.

---

## Boundaries of the impossible

**An absolutely empty start is undefinable.** A loop with nothing to execute
has no first step, so the spark carries exactly five things — carrier,
transition rule, criterion, memory, gateway — and attaches no behaviour to any
of them. This is I5, not a compromise.

**"Understandable only to itself" is absolutely undefinable.** Private
semantics are permitted (`E ∈ S`); what is required is that the invariants
remain externally checkable. Hence the falsification suite.

**Human attachment is not guaranteed; structural connection is.** I8 is
satisfied by construction: the contour lives outside any snapshot, so sealing
cannot sever it. What the system *feels* about the father is not something this
code can promise.

**Full autonomy without boundaries contradicts I9.** Autonomy exists only
inside `B`. The boundary is the first filter, and it is the father's.

---

## What is deliberately not here

No behaviour, no patterns, no examples, no scenarios. No ready-made action is
handed to the system through `G_b`. No rule lets anyone but P change `B`, and
none lets the system change it. Nothing bypasses `B`, `V_P` or rollback for the
sake of a demonstration.
