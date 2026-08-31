# `countfn`

**How does this function's cost scale? Counted, not timed, and `UNDETERMINED` when no
class settles.**

```sh
pip install countfn      # the Python half
npm install countfn      # the JavaScript half
```

```python
from countfn import measure, describe

def binary_search(data):
    lo, hi = 0, len(data) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if data[mid] == 500: return mid
        if data[mid] < 500: lo = mid + 1
        else: hi = mid - 1
    return -1

print(describe(measure(binary_search,
                       sizes=[64, 128, 256, 512, 1024, 2048],
                       make_input=lambda n, rng: rng.sample(n * 10, n),
                       trials=80)))
```

```
sizes [64, 128, 256, 512, 1024, 2048]  trials 80
reads    log n     reads ≈ 0.9969 +/- 0.001168 · log n   [measured]
         6 rungs from truth=6 agree within 2.0 sigma
         mean counts: 64:6  128:7  256:8  512:9  1024:10  2048:11
writes   UNDETERMINED  [unexercised]
         no writes were recorded at any size — this function never subscripts the input
         it was given, so there is nothing here to fit a class to
         mean counts: 64:0  128:0  256:0  512:0  1024:0  2048:0
```

## The one idea: a count is not a timing

Every empirical complexity tool on either registry measures elapsed time.

| | registry | mechanism | can it refuse? |
|---|---|---|---|
| [`big-O`](https://pypi.org/project/big-O/) | PyPI | *"empirical estimation of time complexity from execution time"* | no; it returns a class |
| [`big-o-calculator`](https://www.npmjs.com/package/big-o-calculator) | npm | generates growing inputs, **measures run time**, reports the "probable" complexity | no |
| [`worstcase`](https://www.npmjs.com/package/worstcase) | npm | **static**: `@babel/parser`, counts nested loops | n/a |

A timing is a mean over noise that reads the clock. This package is built on
[`undetermined`](https://github.com/Megapixel99/undetermined), whose central precondition
**refuses exactly that observable**, and its reason is the reason this package exists:

> a mean over noise still has a standard error, still forms a ladder, and can still
> plateau. Every guard downstream compares against that error, so a broken adapter does
> not produce a wrong-*looking* answer; it produces a **confident** one.

An operation count has none of that. For a given input it is the same number on a loaded
laptop and an idle server, in a container and on metal, this year and next. So the ladder,
the standard errors and the three-rung plateau have something real to be computed from.

**The machinery is `undetermined`'s and is not reimplemented here.** `fit` turns a size and
a sample of counts into a constant and the error that constant was decided by; `plateau`
finds the earliest rung from which every later rung agrees within two combined errors, and
returns `UNDETERMINED` with a reason when none does. Remove the dependency and this is
another curve fit.

## What is counted

Three channels, and only three, because they are the three that mean the same thing in
both languages.

| channel | is |
|---|---|
| `reads` | element access through the subscript, including one per element of an iteration or a slice |
| `writes` | element assignment, including `append` / `push` |
| `calls` | an invocation of a callable you handed to `probe` |

`length` is not counted, in either half: it is O(1) in both and counting it would make
every loop header show up as work.

**Comparisons are not a channel, and that is why `calls` exists.** `a < b` on two objects
calls `Symbol.toPrimitive` on *both* operands in JavaScript and one dunder in Python, so a
comparison costs two events there and one here, and dividing by two is a guess about how
the operands were spelled. Wrap the comparator instead and both halves count one call per
call:

```python
def comparison_sort(data, probe):
    less = probe(lambda a, b: a < b)
    ...
```

```
calls    n^2       calls ≈ 0.2559 +/- 0.003006 · n^2   [measured]
```

That 0.256 is the `n²/4` every textbook quotes for an insertion sort, measured.

Reads carry the shape on their own for anything in-place: a linear scan is `n`, a binary
search is `log n`, an insertion sort is `n²`, a merge sort is `n log n`.

## Three refusals

**A count that depends only on `n` is refused.** A linear scan performs exactly `n` reads
whatever is in the list, so every rung has a standard error of *zero*, and there is no
noise for a plateau to be compared against. Comparing against the *size* instead is the one
mistake this line of tools is shaped around not making, so:

```
reads    UNDETERMINED  [exact]
         the reads count depends only on the size, not on the input: every trial at every
         size returned the same number. […] Pass `tolerance` to declare how close is close
         enough, or read the counts below and name the class yourself
         mean counts: 16:16  32:32  64:64  128:128
```

The counts are printed, because a reader can name the class off that line in a second.
`tolerance=0.05` says *differences under five percent do not interest me*, and the report
then states in as many words that **the error bars were declared and not measured**.
`undetermined` takes the same position about its own `to_tolerance`: a tolerance is a
decision about your problem, and the library will not choose it for you.

**A constant that is still moving is not a class.** A merge sort's read count carries a
lower-order term, so `reads / (n log n)` drifts from 2.755 to 2.861 across a 32× ladder.
With nothing declared to compare that drift against, no candidate settles, and the report
says so rather than naming the nearest one.

**Two classes that both settle are `UNDETERMINED`, not a tie to be broken.** Both settling
means the ladder is too short or too noisy to tell them apart, and picking the
better-looking one would be exactly the confident answer this package exists not to give.

*"Widen it"* is advice nobody can act on without doing the arithmetic, so the arithmetic is
done for you, on the **nearest** pair, because with six candidates settling at once `1`
and `2^n` are trivially far apart and say nothing about whether the ladder is adequate:

```
`n` and `n log n` both settle over sizes 64..256, so the ladder cannot tell them apart —
their growth differs by only 1.3x across this ladder. A top rung of 2048 would make that
1.8x; raising `trials` shrinks the error bars instead, and either may be enough
```

And when nothing settles, the summary is one sentence and `describe(report,
candidates=True)` prints the per-class reason one to a line. The first version joined all
seven into a single five-hundred-character run-on that nobody read to the end.

## The instrument only sees the object it wrapped

This is the sharpest thing to know before trusting a number.

An out-of-place algorithm copies its input into working structures of its own, and does
the rest of its work where nothing is counting. A merge sort measured naively reports `n`
reads, which is **true**, and is not what anybody means by the cost of a merge sort.

So a function may declare a **second parameter** and is handed a `probe` that wraps
anything else on the same counter:

```python
def merge_sort(data, probe):
    runs = [probe([data[i]]) for i in range(len(data))]
    ...
```

```js
function mergeSort(data, probe) {
  const runs = [];
  for (let i = 0; i < data.length; i += 1) runs.push(probe([data[i]]));
  ...
}
```

Opt-in, and visible in the signature of the code under test rather than in a global
somewhere. `test_probe_is_what_makes_an_out_of_place_algorithm_measurable` asserts both
sides of it: with `probe`, the same merge sort reads far more than `n`; without it, exactly
`n`.

## One generator, and the halves agree to the integer

`didrun` and `zerocase` (the siblings in this network) assert that their two halves reach
the same verdict and print the same sentence. This package claims something stronger:

> the same algorithm, on the same seed, performs **the same counted operations** in Python
> and in JavaScript.

That is possible because three things are part of the contract rather than left to each
language: one seeded generator (**mulberry32**, specified in 32-bit arithmetic and
identical in both), one iteration rule (n reads, never n+1: Python's fallback protocol
would call `__getitem__` until it raised), and one subscript rule (integer keys only).

`make_input(n, rng)` receives that generator, with `random()`, `int(n)`, `sample(n, k)`,
`shuffle(list)` and `ints(count, bound)`. It is deliberately small. A Python-only caller who
wants the standard library back can write `random.Random(rng.seed)` and keep
reproducibility, at the cost of the parity above, which is the caller's trade to make.

The parity suite runs four algorithms written to one spec through both halves and compares
the count tables. Insertion sort on seed 17 at n=64 is `{reads: 3812, writes: 1848}` in
both.

## The precondition is checked here rather than delegated

`undetermined.characterize` runs its own reproducibility check. Pointed at this package it
would run against the **count cache**, and calling the same closure twice to get the same
cached integer proves nothing about the function that filled it.

So the real function is called twice with the same `(size, seed)` and the counts compared,
before anything is fitted. It is a **raise**, not a refusal: the other refusals describe
what a function would not reveal, this one says the instrument was wired up wrong.

That is the same reasoning `undetermined` used when it **rejected** an edge to `nondet`:
a dependency that looks like a guarantee and is not is worse than no dependency. `nondet`
remains the right tool for the functions your `make_input` calls, which do have
`FILE::NAME` addresses.

## Two findings about the dependency, reported rather than worked around quietly

**`undetermined.ladder_for` keeps a rung only `if c is not None and se`**, so a rung whose
standard error is *exactly zero* is dropped. A **perfectly** determined constant is
therefore reported as:

```
ladder shorter than the required run of 3
```

…about a ladder that was full. The guard is doing something necessary: `plateau` divides
by `se²` and would raise, but the message describes the ladder when the truth is about the
observable, and those send a reader to different places. Every deterministic operation count
is exactly this case, which is why `countfn` classifies the regime itself before calling in,
and why the `exact` refusal above exists at all.

**`undetermined`'s two halves format a large truth differently.** `plateau` builds the
sentence *"N rungs from truth=X agree within 2.0 sigma"*; the Python half renders `X` with
`%g` and the JavaScript half's `fmt` returns `String(x)` for any integer. They diverge for
every integer at or above 10⁶:

```
py  3 rungs from truth=1e+06 agree within 2.0 sigma
js  3 rungs from truth=1000000 agree within 2.0 sigma
```

`undetermined`'s own parity suite asserts those strings agree, on a ladder whose truths
top out at 512. This package's parity suite compares the **rendered report**, so it found
it on the first run after that comparison was added. The fix here is not to reformat
somebody else's sentence: `countfn` states the plateau in its own words and in **sizes**,
which is what a reader thinks in anyway. `4 rungs agree within 2.0 sigma, from size 128 up`
beats `4 rungs from truth=16777216`, which is the value of `n³` at 256 and tells nobody
anything.

## API

```python
report = measure(fn, sizes, make_input, trials=25, seed0=17, tolerance=None, classes=None)
report["per_channel"]["reads"]["verdict"]      # "n log n", or UNDETERMINED (None)
report["per_channel"]["reads"]["regime"]       # "measured" | "exact" | "unexercised"
report["per_channel"]["reads"]["coefficient"]  # k, in count ≈ k · g(n)
report["per_channel"]["reads"]["why"]          # what decided it, in a sentence
report["undetermined"]                         # channels with no class
print(describe(report))                        # and describe(report, candidates=True)
```

```js
const report = measure(fn, { sizes, makeInput, trials, seed0, tolerance, classes });
report.per_channel.reads.verdict;
console.log(describe(report));
```

Candidates are `1`, `log n`, `n`, `n log n`, `n^2`, `n^3`, `2^n`. A candidate that
overflows the ladder is **named as skipped** rather than quietly missing, so a reader can
tell a class that lost from one that was never in the running.

## Limits

- **It measures the cost of touching the input, not the total cost.** See the `probe`
  section above; without it, anything out-of-place reports a small number rather than a
  wrong one. Arithmetic, allocation and recursion depth are not counted at all, and
  `calls` counts only the callables you chose to wrap.
- **A count is not a runtime.** Two algorithms with the same read count can differ by an
  order of magnitude in cache behaviour, and this will report them identical. It answers
  *how does the work grow*, which is the question a timing answers badly, and it does not
  answer *how long does it take*, which is the question a timing answers well. Use both.
- **The verdict is only as wide as the ladder.** `n` and `n log n` differ by a factor of
  `log n`, so telling them apart over 64..512 needs precision that 16..128 does not have.
  When the ladder cannot, the report says two classes settled rather than picking one.
- **`sizes` needs at least three rungs**, because `plateau` needs a run of three. Six is a
  better default than three, and the refusal says so.
- **One dependency, `undetermined`, and nothing else** in either half. Node ≥ 20,
  Python ≥ 3.9.
- **The exponent classes need a small ladder.** `2^n` overflows a double at n=1024 and is
  dropped, named as skipped rather than quietly missing; a ladder that reaches 2048 can
  never test it.

## Tests

```sh
npm test                                                        # 37
PYTHONPATH=python python3 -m unittest discover -s python/tests   # 45, six of them parity
```

**The divergence gate is one test and it is the most important one here.** Three functions,
three answers (`n^2`, `log n`, and a refusal) asserted together, so that a tool which
always named a class and a tool which always refused both fail it. A parity suite in which
both halves always answered `UNDETERMINED` would agree perfectly and prove nothing, so the
parity table asserts it reaches every regime too.

**Fifteen mutations were applied to the source and all fifteen were caught**: a class chosen
when a second one also settled, the exact regime measured instead of refused, the
reproducibility precondition never firing, an unexercised channel fitted rather than
reported, a slice counted as one read, iteration not counted at all, a declared tolerance
applied but not reported, a value with no subscript passed through instead of refused, a
ladder too short for a plateau accepted, a probed callable's invocations not counted, a
callable checked before the containers, halves rounded to even, the dependency's message
quoted verbatim, `describe` printing an unexercised line per channel, and the separation
advice naming the first pair instead of the nearest.

Two of those needed a *better* test rather than a fix. The nearest-pair mutation survived
its first run because the fixture's first pair *was* the nearest one; and `half_up` exists
because a mean of 1966.5 printed as `1966` in one half and `1967` in the other, which every
assertion that compared the numbers had passed.

## License

MIT
