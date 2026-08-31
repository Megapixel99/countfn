"""One pseudo-random generator, implemented identically in both halves.

WHY NOT `random.Random`. `make_input(n, rng)` is the user's code, and the point of this
package is that a size and a seed determine a count. Python's Mersenne Twister and
whatever a JavaScript author reached for are two different streams, so the same
`make_input` written twice would build two different inputs and the two halves would count
different things while both being right.

So the generator is part of the contract. This is **mulberry32**, chosen because it is
eleven lines, is exactly specifiable in 32-bit arithmetic, and has no state that the two
languages represent differently. `python/tests/test_parity.py` asserts the two streams are
identical for the same seed rather than assuming it.

It is NOT cryptographic and is not offered as one. It generates test inputs.

`seed` is public so a Python-only caller who wants the standard library back can write
`random.Random(rng.seed)` and keep reproducibility -- at the cost of the parity above,
which is the caller's trade to make and is worth making on purpose.
"""

from __future__ import annotations

MASK = 0xFFFFFFFF


def _imul(a, b):
    """`Math.imul` on unsigned 32-bit halves: the low 32 bits, where sign does not reach."""
    return ((a & MASK) * (b & MASK)) & MASK


class Rng:
    """mulberry32. Same seed, same stream, in both languages."""

    __slots__ = ("seed", "_a")

    def __init__(self, seed):
        self.seed = int(seed) & MASK
        self._a = self.seed

    def random(self):
        """A float in [0, 1)."""
        self._a = (self._a + 0x6D2B79F5) & MASK
        a = self._a
        t = _imul(a ^ (a >> 15), 1 | a)
        t = ((t + _imul(t ^ (t >> 7), 61 | t)) & MASK) ^ t
        return ((t ^ (t >> 14)) & MASK) / 4294967296.0

    def int(self, n):
        """An integer in [0, n)."""
        if n <= 0:
            raise ValueError("int(n) needs n >= 1")
        return int(self.random() * n)

    def shuffle(self, values):
        """Fisher-Yates, in place, and the same swaps in both halves."""
        for i in range(len(values) - 1, 0, -1):
            j = self.int(i + 1)
            values[i], values[j] = values[j], values[i]
        return values

    def sample(self, n, k):
        """`k` distinct integers from [0, n), in increasing order.

        Increasing because the common use is a sorted input, and sorting it afterwards
        with the language's own sort would put a second uncounted algorithm between the
        generator and the thing being measured.
        """
        if k > n:
            raise ValueError(f"cannot take {k} distinct values from a range of {n}")
        pool = list(range(n))
        for i in range(k):
            j = i + self.int(n - i)
            pool[i], pool[j] = pool[j], pool[i]
        return sorted(pool[:k])

    def ints(self, count, bound):
        """`count` integers in [0, bound), with repeats allowed."""
        return [self.int(bound) for _ in range(count)]
