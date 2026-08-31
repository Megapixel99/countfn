"""Measure how a function's cost scales by COUNTING what it does, not by timing it.

    from countfn import measure, describe

    report = measure(lambda data: binary_search(data, 7),
                     sizes=[64, 128, 256, 512, 1024, 2048],
                     make_input=lambda n, rng: rng.sample(n * 10, n))
    print(describe(report))

WHAT THIS PACKAGE IS, IN ONE SENTENCE: `undetermined`'s ladder, pointed at an operation
count, with an explicit refusal wherever the count is not the kind of thing a plateau can
be fitted to.

THE MACHINERY IS `undetermined`'S AND IS NOT REIMPLEMENTED HERE. `fit` turns a size and a
sample of counts into a constant and the standard error that constant was decided by;
`plateau` finds the earliest rung from which every later rung agrees within two combined
errors, and returns `UNDETERMINED` with a reason when none does. Both are imported. What
is here is the instrument that produces the counts, the candidate classes, and three
refusals that are specific to counting.

    Compare against the NOISE, never against the SIZE.

That is `undetermined`'s rule and it is the reason this package exists at all: the
incumbents fit a curve to timings and always return a class. This returns a class or says
why it cannot.

THE PRECONDITION IS CHECKED HERE RATHER THAN DELEGATED, and that is deliberate.
`undetermined.characterize` runs its own reproducibility check, but it would run it
against the count CACHE this module builds -- calling the same closure twice and getting
the same cached integer proves nothing about the function that filled it. So the real
function is called twice with the same `(size, seed)` and the counts compared, in
`_reproducible` below. A dependency that looks like a guarantee and is not is worse than
no dependency, which is the argument `undetermined` itself used when it rejected an edge
to `nondet`.
"""

from __future__ import annotations

import inspect
import math

from undetermined.core import PLATEAU_K, PLATEAU_RUN, UNDETERMINED, fit, plateau

from . import classes as klass
from .counters import CHANNELS, Counter, instrument
from .rng import Rng

# The three regimes a channel can be in. A verdict is only meaningful beside the regime
# it was reached in, so the regime is always reported.
UNEXERCISED = "unexercised"
EXACT = "exact"
MEASURED = "measured"


def measure(fn, sizes, make_input, trials=25, seed0=17, tolerance=None, classes=None):
    """Run `fn` over a ladder of input sizes and report how its operation count scales.

    `fn` is called with ONE argument: whatever `make_input(n, rng)` returned, wrapped so
    that its subscripts are counted. Everything else your function needs, close over.

    A function that declares a SECOND parameter is handed a `probe` instead, and may wrap
    its own working structures on the same counter: `probe(list)` returns a counted list.
    That is how an out-of-place algorithm gets measured at all -- see `_one` below.

    `make_input(n, rng)` must build an input of size `n` using ONLY `rng` for its
    randomness — a `countfn.Rng`, whose stream is identical in both halves of this
    package. That is not a style note. `fit` averages over `trials` different seeds,
    so an input built from the clock or from an unseeded generator makes every count a
    sample from a distribution nobody declared -- and the standard error computed from it
    is real arithmetic about nothing. `_reproducible` below refuses that case rather than
    reporting it.

    `tolerance` is a DECLARED floor under the error bar, in fractions of the constant. It
    is `None` by default and this will not choose one for you: with a count that depends
    only on `n`, there is no noise for a plateau to be compared against, and any threshold
    is a decision about your problem. Supplying one is how you say how close is close
    enough; wherever it is doing the work, the report says so.
    """
    sizes = [int(n) for n in sizes]
    if len(sizes) < PLATEAU_RUN:
        raise ValueError(
            f"a ladder of {len(sizes)} rung(s) cannot show a constant has settled; "
            f"`plateau` needs a run of {PLATEAU_RUN} agreeing rungs, so give at least "
            f"that many sizes -- and more is what separates `n` from `n log n`"
        )
    if sorted(set(sizes)) != sizes:
        raise ValueError("sizes must be increasing and distinct")
    if sizes[0] < 1:
        raise ValueError("sizes must be at least 1")
    if trials < 2:
        raise ValueError("trials must be at least 2, or there is no spread to measure "
                         "and every rung is exact by construction rather than by fact")
    if tolerance is not None and tolerance <= 0:
        raise ValueError("a tolerance of 0 admits no difference at all; leave it None to "
                         "have the refusal reported instead")
    names = list(classes) if classes else list(klass.NAMES)
    for name in names:
        if name not in klass.BY_NAME:
            raise ValueError(f"no candidate class named {name!r}; "
                             f"known: {', '.join(klass.NAMES)}")

    cache = _collect(fn, sizes, make_input, trials, seed0)
    _reproducible(fn, sizes, make_input, seed0, cache)

    per_channel = {}
    for channel in CHANNELS:
        per_channel[channel] = _classify(cache, sizes, channel, trials, seed0,
                                         names, tolerance)

    undetermined = sorted(c for c in CHANNELS if per_channel[c]["verdict"] is UNDETERMINED)
    return {
        "sizes": sizes,
        "trials": trials,
        "tolerance": tolerance,
        "candidates": names,
        "per_channel": per_channel,
        "undetermined": undetermined,
        "notes": [f"`{c}`: {per_channel[c]['why']}" for c in undetermined],
    }


# --------------------------------------------------------------------- collecting

def _collect(fn, sizes, make_input, trials, seed0):
    """{(size, seed): {"reads": n, "writes": n}} — every run, kept."""
    cache = {}
    for size in sizes:
        for i in range(trials):
            seed = seed0 + i
            cache[(size, seed)] = _one(fn, size, make_input, seed)
    return cache


def _one(fn, size, make_input, seed):
    counter = Counter()
    value = make_input(size, Rng(seed))
    wrapped = instrument(value, counter)
    if _wants_probe(fn):
        # THE INSTRUMENT ONLY SEES THE OBJECT IT WRAPPED. A function that copies its
        # input into working structures of its own -- which is most out-of-place
        # algorithms, merge sort first among them -- does the rest of its work where
        # nothing is counting, and the honest report of that is a small number rather
        # than a wrong one.
        #
        # So a function may declare a SECOND parameter and be handed a `probe` that wraps
        # anything else on the same counter. Opt-in, and visible in the signature of the
        # code under test rather than in a global somewhere.
        fn(wrapped, lambda obj: instrument(obj, counter))
    else:
        fn(wrapped)
    return counter.snapshot()


def _wants_probe(fn):
    """True when `fn` declares a second positional parameter.

    Read from the signature rather than guessed by calling and catching `TypeError`: a
    genuine arity error inside the function under test would be swallowed by the guess,
    and the run would silently measure a different code path.
    """
    try:
        params = inspect.signature(fn).parameters.values()
    except (TypeError, ValueError):
        return False
    positional = [p for p in params
                  if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
    return len(positional) >= 2


def _reproducible(fn, sizes, make_input, seed0, cache):
    """The same `(size, seed)` must produce the same counts, or nothing below means anything.

    Checked at the cheapest place it can fail -- the first and last rung -- because a
    function whose count is stable at one size and not at another is stable at neither.

    A raise, not a `look`. The refusals elsewhere in this module describe what the
    function would not reveal; this one says the instrument was wired up wrong, and
    continuing would report a standard error about nothing.
    """
    for size in {sizes[0], sizes[-1]}:
        again = _one(fn, size, make_input, seed0)
        first = cache[(size, seed0)]
        if again != first:
            raise ValueError(
                f"the run is not reproducible: at size={size} and seed={seed0} the counts "
                f"were {first} and then {again}. Every constant below is fitted from a "
                f"mean over seeds, so a function or an input builder that reads the clock, "
                f"the environment or an unseeded generator yields a mean over noise -- "
                f"which still plateaus, and would be reported as an answer"
            )


# ------------------------------------------------------------------- classifying

def _classify(cache, sizes, channel, trials, seed0, names, tolerance):
    raw = {size: [cache[(size, seed0 + i)][channel] for i in range(trials)]
           for size in sizes}
    means = {size: sum(raw[size]) / len(raw[size]) for size in sizes}

    if all(v == 0 for size in sizes for v in raw[size]):
        return _channel(UNEXERCISED, UNDETERMINED,
                        f"no {channel} were recorded at any size — this function never "
                        f"subscripts the input it was given, so there is nothing here to "
                        f"fit a class to",
                        means, {}, [])

    spread = {size: len(set(raw[size])) > 1 for size in sizes}
    varying = sum(1 for size in sizes if spread[size])
    regime = MEASURED if varying else EXACT

    if regime is EXACT and tolerance is None:
        # THE REFUSAL THAT COST THE MOST TO GET RIGHT. With a count that depends only on
        # n, every rung has a standard error of exactly zero -- and `undetermined`'s
        # `ladder_for` drops such rungs, so an unguarded call reports "ladder shorter than
        # the required run of 3" about a ladder that was full. That message describes the
        # ladder and the truth is about the function, and the two send you to different
        # places.
        return _channel(
            EXACT, UNDETERMINED,
            f"the {channel} count depends only on the size, not on the input: every "
            f"trial at every size returned the same number. There is no noise for a "
            f"plateau to be compared against, and comparing against the SIZE instead is "
            f"the one mistake this line of tools is shaped around not making. Pass "
            f"`tolerance` to declare how close is close enough, or read the counts "
            f"below and name the class yourself",
            means, {}, [])

    ladders = {}
    settled = []
    floored_total = 0
    for name in names:
        truths = klass.truths_for(name, sizes)
        if truths is None:
            ladders[name] = {"skipped": "the class overflows on this ladder"}
            continue
        rungs, dropped, floored = [], 0, 0
        for size, truth in zip(sizes, truths):
            sample = _sampler(cache, size, channel)
            c, se = fit(sample, truth, trials, seed0)
            if c is None:
                dropped += 1
                continue
            if tolerance is not None:
                floor = tolerance * abs(c)
                if floor > (se or 0.0):
                    floored += 1
                    se = floor
            if not se:
                dropped += 1
                continue
            rungs.append({"truth": truth, "c": c, "se": se})
        floored_total += floored
        found = plateau(rungs) if len(rungs) >= PLATEAU_RUN else {
            "value": UNDETERMINED, "se": None, "from_truth": None,
            "why": f"only {len(rungs)} of {len(sizes)} rungs carried an error bar; "
                   f"{dropped} had none and were dropped",
        }
        found = dict(found, why=plateau_why(found, truths, sizes, rungs))
        ladders[name] = {"rungs": rungs, "dropped": dropped, "floored": floored,
                         "plateau": found}
        if found["value"] is not UNDETERMINED:
            settled.append(name)

    if not settled:
        # ONE SENTENCE, NOT SIX. The first version joined every candidate's own reason
        # into a single line and produced five hundred characters of prose that nobody
        # read to the end. The per-class reasons are still in `ladders[name]["plateau"]`
        # and `describe` prints them one to a line, which is where a reader looks anyway.
        tried = [n for n in names if "plateau" in ladders[n]]
        return _channel(regime, UNDETERMINED,
                        f"no candidate class settles over sizes {sizes[0]}..{sizes[-1]}; "
                        f"{len(tried)} candidate(s) tried and every one of them is still "
                        f"moving where the ladder ends",
                        means, ladders, settled, floored_total)
    if len(settled) > 1:
        # NOT A TIE TO BE BROKEN. Two classes agreeing means the ladder is too short or
        # too noisy to tell them apart, and picking the better-looking one would be
        # exactly the confident answer this package exists not to give.
        #
        # "Widen it" is advice nobody can act on without doing the arithmetic, so the
        # arithmetic is done here: how far apart the two candidates grow across THIS
        # ladder, and how far apart they would grow across one reaching eight times
        # higher. A reader can then decide whether the answer is worth the run.
        which = (f"`{settled[0]}` and `{settled[1]}` both settle" if len(settled) == 2
                 else f"{len(settled)} candidates all settle "
                      f"({', '.join(settled)})")
        return _channel(regime, UNDETERMINED,
                        f"{which} over sizes {sizes[0]}..{sizes[-1]}, so the ladder "
                        f"cannot tell them apart — "
                        + separation_advice(settled, sizes),
                        means, ladders, settled, floored_total)

    name = settled[0]
    found = ladders[name]["plateau"]
    return _channel(regime, name, found["why"], means, ladders, settled, floored_total,
                    constant=found["value"], constant_se=found["se"],
                    from_truth=found["from_truth"])


def plateau_why(found, truths, sizes, rungs):
    """`undetermined`'s verdict, restated in SIZES and rendered by this package.

    Two reasons, and the second is the one that made this necessary.

    A reader thinks in input sizes. `4 rungs from truth=1.67772e+07` is a true statement
    about an internal quantity — the value of `n^3` at n=256 — and it tells nobody
    anything. `from size 256 up` is the same fact in the units the ladder was written in.

    AND A DEPENDENCY'S MESSAGE IS NOT THIS PACKAGE'S CONTRACT. `undetermined`'s two halves
    format that truth differently for any integer at or above 1e6: the Python half uses
    `%g` and prints `1e+06`, the JavaScript half's `fmt` returns `String(x)` and prints
    `1000000`. Their own parity suite asserts these strings agree, on a ladder whose
    truths top out at 512. This package's parity suite compares the RENDERED REPORT, so it
    saw it — and the fix here is not to reformat somebody else's sentence but to stop
    quoting it where it carries a number.

    The refusals are quoted verbatim, because they carry no numbers either half formats.
    """
    if found["value"] is UNDETERMINED:
        return found["why"]
    start = found["from_truth"]
    size = sizes[truths.index(start)] if start in truths else sizes[0]
    run = sum(1 for r in rungs if r["truth"] >= start) if start is not None else len(rungs)
    return (f"{run} rungs agree within {PLATEAU_K:.1f} sigma, from size {size} up")


def half_up(value):
    """Round half AWAY FROM ZERO to an integer. Shared with `js/src/core.js`.

    A mean count of 1966.5 renders as `1966` under Python's `%.0f` (half to even) and
    `1967` under JavaScript's `Math.round` (half away from zero). Both halves measured the
    same number and printed different ones, and the parity suite did not see it because it
    compared the numbers rather than the report. It compares the report now, and this is
    the one rule both halves round by.
    """
    rounded = math.floor(abs(value) + 0.5)
    return -rounded if value < 0 else rounded


def one_dp(value):
    """Round half-UP to one place and render it. Shared with `js/src/core.js`.

    Not `format(x, '.1f')`, and not `toFixed(1)`: Python rounds half to even and
    JavaScript rounds half away from zero, so `1.25` renders as `1.2` in one half and
    `1.3` in the other. The parity suite compares these strings, so the rounding is done
    the same way in both before anything is formatted.
    """
    rounded = math.floor(abs(value) * 10 + 0.5) / 10.0
    rounded = -rounded if value < 0 else rounded
    return f"{rounded:g}"


def spread_over(name, low, high):
    """How many times `g(high)` exceeds `g(low)` — a class's growth across a ladder."""
    fn = klass.BY_NAME[name]
    bottom = fn(low)
    return None if not bottom else fn(high) / bottom


def closest_pair(settled, sizes):
    """The two settled classes hardest to tell apart, and by how little they differ.

    THE BINDING CONSTRAINT IS THE NEAREST PAIR, not the first two. When six candidates
    settle at once, `1` and `2^n` are trivially far apart and say nothing about whether
    the ladder is adequate; the pair that grows most alike is the one that has to be
    separated, and it is the one a wider ladder has to reach past.
    """
    best = None
    for first, second in zip(settled, settled[1:]):
        a = spread_over(first, sizes[0], sizes[-1])
        b = spread_over(second, sizes[0], sizes[-1])
        if not a or not b:
            continue
        ratio = max(a, b) / min(a, b)
        if best is None or ratio < best[2]:
            best = (first, second, ratio)
    return best


def separation_advice(settled, sizes):
    """What widening the ladder would actually buy, in a number rather than a verb.

    Two classes are told apart by the ratio of their growths across the ladder: over
    16..128, `n` grows 8x and `n log n` grows 14x, so they differ by 1.8x and a constant
    that settles for one settles for the other. Over 16..1024 the same pair differ by
    2.5x. That is the sentence, and it is arithmetic rather than encouragement.
    """
    pair = closest_pair(settled, sizes)
    if pair is None:
        return "widen the ladder or raise `trials`"
    first, second, ratio = pair
    wider = sizes[-1] * 8
    a, b = spread_over(first, sizes[0], wider), spread_over(second, sizes[0], wider)
    head = ("their growth differs by only " if len(settled) == 2 else
            f"`{first}` and `{second}` are the hardest of them to separate, and their "
            f"growth differs by only ") + f"{one_dp(ratio)}x across this ladder"
    if not a or not b or not math.isfinite(a) or not math.isfinite(b):
        return (f"{head}; raise `trials`, or narrow `classes` to the candidates you are "
                f"actually choosing between")
    later = max(a, b) / min(a, b)
    return (f"{head}. A top rung of {wider} would make that {one_dp(later)}x; raising "
            f"`trials` shrinks the error bars instead, and either may be enough")


def _sampler(cache, size, channel):
    """`fit` calls this with (truth, seed); the truth is the CLASS's and the size is not.

    Closing over the size rather than looking it up by truth is what lets the constant
    class `1` be a candidate at all: it gives every rung the same truth, and a lookup
    keyed on truth would collapse the whole ladder onto one rung without saying so.
    """
    return lambda _truth, seed: float(cache[(size, seed)][channel])


def _channel(regime, verdict, why, means, ladders, settled, floored=0,
             constant=None, constant_se=None, from_truth=None):
    coefficient = coefficient_se = None
    if constant:
        # `undetermined` fits c such that c * E[count] == truth, so the number a reader
        # wants -- count ≈ k * g(n) -- is its reciprocal, with the error carried through.
        coefficient = 1.0 / constant
        if constant_se is not None:
            coefficient_se = constant_se / (constant ** 2)
    return {
        "regime": regime,
        "verdict": verdict,
        "why": why,
        "constant": constant,
        "constant_se": constant_se,
        "coefficient": coefficient,
        "coefficient_se": coefficient_se,
        "from_truth": from_truth,
        "settled": settled,
        "mean_counts": means,
        "ladders": ladders,
        "declared_error_bars": floored,
    }


# ---------------------------------------------------------------------- reporting

def describe(report, candidates=False):
    """The report as text. Every line says what it is and what decided it.

    UNEXERCISED CHANNELS ARE COLLAPSED ONTO ONE LINE. Three channels means a read-only
    function otherwise spends two thirds of its report saying nothing happened, and a
    reader who has to skip most of a report stops reading reports. They are still named --
    "nothing happened here" is a fact about the function -- just not three lines of it.

    `candidates=True` adds, under any UNDETERMINED channel, one line per candidate class
    saying why that class did not settle. That is the detail the summary deliberately
    leaves out, and it is where somebody deciding whether to widen the ladder looks.
    """
    lines = [f"sizes {report['sizes']}  trials {report['trials']}"
             + (f"  tolerance {report['tolerance']:g}" if report["tolerance"] else "")]
    quiet = [c for c in CHANNELS
             if report["per_channel"][c]["regime"] == UNEXERCISED]
    for channel in CHANNELS:
        entry = report["per_channel"][channel]
        if channel in quiet:
            continue
        counts = "  ".join(f"{n}:{half_up(entry['mean_counts'].get(n, 0))}"
                           for n in report["sizes"])
        if entry["verdict"] is UNDETERMINED:
            lines.append(f"{channel:8} UNDETERMINED  [{entry['regime']}]")
            lines.append(f"         {entry['why']}")
        else:
            k, kse = entry["coefficient"], entry["coefficient_se"]
            bar = f" +/- {kse:.4g}" if kse is not None else ""
            lines.append(f"{channel:8} {entry['verdict']:9} "
                         f"{channel} ≈ {k:.4g}{bar} · {entry['verdict']}   "
                         f"[{entry['regime']}]")
            lines.append(f"         {entry['why']}")
            if entry["declared_error_bars"]:
                lines.append(f"         {entry['declared_error_bars']} rung(s) used the "
                             f"DECLARED tolerance as their error bar rather than a "
                             f"measured one")
        lines.append(f"         mean counts: {counts}")
        # Only where a ladder was actually built. In the `exact` regime nothing was
        # fitted, so every line would read "not tried" — seven lines saying the same
        # thing the verdict already said.
        if candidates and entry["verdict"] is UNDETERMINED and entry["ladders"]:
            for name in report["candidates"]:
                ladder = entry["ladders"].get(name) or {}
                reason = (ladder.get("skipped") or
                          (ladder.get("plateau") or {}).get("why") or "not tried")
                lines.append(f"           {name:9} {reason}")
    if quiet:
        lines.append(f"{', '.join(quiet)}: unexercised — this function performed none of "
                     f"those on the input it was given, so there is nothing to fit a "
                     f"class to")
    return "\n".join(lines)
