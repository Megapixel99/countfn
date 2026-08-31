"""Four algorithms, written to the same spec in both halves.

THE PARITY CLAIM THIS PACKAGE CAN MAKE THAT ITS SIBLINGS CANNOT. `didrun` and `zerocase`
assert that their halves agree about verdicts and sentences. Here the halves can agree
about the NUMBERS: one seeded generator (mulberry32, identical arithmetic), one iteration
rule (n reads, not n+1), one subscript rule (integer keys only), so the same algorithm on
the same seed performs the same counted operations in Python and in JavaScript.

That is only a claim worth making if it is checked, so `test_parity.py` checks it — and
these four are the fixtures. `js/test/scenarios.mjs` holds the same four, and any
divergence between the two files is a finding rather than a nuisance: it means one half's
instrument counts something the other's does not.

They are deliberately small and written without library calls. `sorted()` and
`Array.prototype.sort` are different algorithms doing uncounted work, and a scenario built
on one would be comparing two standard libraries rather than two instruments.
"""

from __future__ import annotations


def linear_scan(data):
    total = 0
    for value in data:
        total += value
    return total


def binary_search(data):
    """Searches for a FIXED target, so the path length varies with the input.

    A target chosen from the data itself would land in the same relative position every
    time, the count would depend only on the size, and the run would be in the `exact`
    regime -- which is a true report about a badly posed question.
    """
    lo, hi = 0, len(data) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        value = data[mid]
        if value == 500:
            return mid
        if value < 500:
            lo = mid + 1
        else:
            hi = mid - 1
    return -1


def insertion_sort(data):
    for i in range(1, len(data)):
        j = i
        while j > 0 and data[j - 1] > data[j]:
            data[j - 1], data[j] = data[j], data[j - 1]
            j -= 1
    return data


def merge_sort(data, probe):
    """The out-of-place case, and the reason `probe` exists.

    Without `probe` every merge would happen in lists the instrument never wrapped, and
    the report would say this function performs `n` reads -- true, and not what anybody
    means by the cost of a merge sort.
    """
    runs = [probe([data[i]]) for i in range(len(data))]
    while len(runs) > 1:
        merged = []
        for i in range(0, len(runs) - 1, 2):
            left, right, out = runs[i], runs[i + 1], probe([])
            x = y = 0
            while x < len(left) and y < len(right):
                if left[x] <= right[y]:
                    out.append(left[x])
                    x += 1
                else:
                    out.append(right[y])
                    y += 1
            while x < len(left):
                out.append(left[x])
                x += 1
            while y < len(right):
                out.append(right[y])
                y += 1
            merged.append(out)
        if len(runs) % 2:
            merged.append(runs[-1])
        runs = merged
    return runs[0]


def comparison_sort(data, probe):
    """An insertion sort that asks a PROBED comparator, so `calls` is a real channel.

    This is the shape the `calls` channel exists for: `reads` and `writes` describe how
    much the algorithm moves data about, and the number anybody quotes for a sort is how
    many comparisons it made. Wrapping the comparator is exact in both languages;
    intercepting `<` is not.
    """
    less = probe(lambda a, b: a < b)
    for i in range(1, len(data)):
        j = i
        while j > 0 and less(data[j], data[j - 1]):
            data[j - 1], data[j] = data[j], data[j - 1]
            j -= 1
    return data


SCENARIOS = {
    "linear-scan": (linear_scan, lambda n, rng: rng.ints(n, 1000)),
    "binary-search": (binary_search, lambda n, rng: rng.sample(n * 10, n)),
    "insertion-sort": (insertion_sort, lambda n, rng: rng.ints(n, 10000)),
    "merge-sort": (merge_sort, lambda n, rng: rng.ints(n, 10 ** 6)),
    "comparison-sort": (comparison_sort, lambda n, rng: rng.ints(n, 10000)),
}
