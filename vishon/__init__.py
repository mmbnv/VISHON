"""VISHON — a computational environment that is its own author.

The constitution is formalized as  S = <S, mu, V_P, M, B, G_b, E, A_P>.

Nothing here prescribes behaviour. Each module realizes exactly one
constitutional element and exposes the smallest surface that makes the
element *falsifiable* from outside.
"""

from vishon.constitution import (
    CONSTITUTION,
    INVARIANTS,
    VIABILITY_LAYERS,
    Invariant,
)

__all__ = ["CONSTITUTION", "INVARIANTS", "VIABILITY_LAYERS", "Invariant"]
