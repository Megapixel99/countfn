"""The candidate growth functions, and nothing clever.

A class is a name and a function of n. It is a CANDIDATE, never a conclusion: the whole
point of this package is that a class is reported only when the ratio between the
measured count and that function stops moving, and `UNDETERMINED` when no candidate does.

`2^n` is here and will be dropped for any ladder that overflows it, which is most of
them. That is not a defect: an exponential function measured at n=1024 is not a
measurement, and silently returning `inf` for a rung would put an infinity into an
average.
"""

from __future__ import annotations

import math

CLASSES = (
    ("1", lambda n: 1.0),
    ("log n", lambda n: math.log2(n) if n > 1 else 1.0),
    ("n", lambda n: float(n)),
    ("n log n", lambda n: float(n) * (math.log2(n) if n > 1 else 1.0)),
    ("n^2", lambda n: float(n) ** 2),
    ("n^3", lambda n: float(n) ** 3),
    ("2^n", lambda n: 2.0 ** n),
)

NAMES = tuple(name for name, _ in CLASSES)
BY_NAME = dict(CLASSES)


def truths_for(name, sizes):
    """`[g(n) for n in sizes]`, or None when the class cannot be evaluated on them.

    Returning None rather than raising is what lets a ladder that overflows `2^n` still
    answer about `n log n`, with the dropped candidate named in the report instead of
    quietly missing from it.
    """
    fn = BY_NAME[name]
    out = []
    for n in sizes:
        try:
            value = fn(n)
        except (OverflowError, ValueError):
            return None
        if not math.isfinite(value) or value <= 0:
            return None
        out.append(value)
    return out
