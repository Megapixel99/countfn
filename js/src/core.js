/**
 * Measure how a function's cost scales by COUNTING what it does, not by timing it.
 *
 *     import { measure, describe } from "countfn";
 *
 *     const report = measure((data) => binarySearch(data, 500), {
 *       sizes: [64, 128, 256, 512, 1024, 2048],
 *       makeInput: (n, rng) => rng.sample(n * 10, n),
 *     });
 *     console.log(describe(report));
 *
 * WHAT THIS PACKAGE IS, IN ONE SENTENCE: `undetermined`'s ladder, pointed at an operation
 * count, with an explicit refusal wherever the count is not the kind of thing a plateau
 * can be fitted to.
 *
 * THE MACHINERY IS `undetermined`'S AND IS NOT REIMPLEMENTED HERE. `fit` turns a size and
 * a sample of counts into a constant and the standard error that constant was decided by;
 * `plateau` finds the earliest rung from which every later rung agrees within two combined
 * errors, and returns `UNDETERMINED` with a reason when none does. Both are imported.
 *
 *     Compare against the NOISE, never against the SIZE.
 *
 * THE PRECONDITION IS CHECKED HERE RATHER THAN DELEGATED. `undetermined.characterize` runs
 * its own reproducibility check, but it would run it against the count CACHE this module
 * builds — calling the same closure twice and getting the same cached integer proves
 * nothing about the function that filled it. A dependency that looks like a guarantee and
 * is not is worse than no dependency, which is the argument `undetermined` itself used
 * when it rejected an edge to `nondet`.
 */

import { PLATEAU_K, PLATEAU_RUN, UNDETERMINED, fit, plateau } from "undetermined";

import * as klass from "./classes.js";
import { CHANNELS, Counter, instrument } from "./counters.js";
import { Rng } from "./rng.js";

// The three regimes a channel can be in. A verdict is only meaningful beside the regime
// it was reached in, so the regime is always reported.
export const UNEXERCISED = "unexercised";
export const EXACT = "exact";
export const MEASURED = "measured";

/**
 * Run `fn` over a ladder of input sizes and report how its operation count scales.
 *
 * `fn` is called with ONE argument: whatever `makeInput(n, rng)` returned, wrapped so that
 * its subscripts are counted. Everything else your function needs, close over. A function
 * that declares a SECOND parameter is handed a `probe` and may wrap its own working
 * structures on the same counter: `probe(array)` returns a counted array.
 *
 * `tolerance` is a DECLARED floor under the error bar, in fractions of the constant. It is
 * null by default and this will not choose one for you: with a count that depends only on
 * `n`, there is no noise for a plateau to be compared against, and any threshold is a
 * decision about your problem.
 */
export function measure(fn, options = {}) {
  const {
    sizes: rawSizes,
    makeInput,
    trials = 25,
    seed0 = 17,
    tolerance = null,
    classes = null,
  } = options;

  if (typeof fn !== "function") throw new TypeError("measure() needs a function");
  if (typeof makeInput !== "function") {
    throw new TypeError("measure() needs a makeInput(n, rng)");
  }
  const sizes = (rawSizes || []).map((n) => Math.trunc(n));
  if (sizes.length < PLATEAU_RUN) {
    throw new RangeError(
      `a ladder of ${sizes.length} rung(s) cannot show a constant has settled; ` +
        `\`plateau\` needs a run of ${PLATEAU_RUN} agreeing rungs, so give at least that ` +
        `many sizes — and more is what separates \`n\` from \`n log n\``
    );
  }
  const sorted = [...new Set(sizes)].sort((a, b) => a - b);
  if (sorted.length !== sizes.length || sorted.some((n, i) => n !== sizes[i])) {
    throw new RangeError("sizes must be increasing and distinct");
  }
  if (sizes[0] < 1) throw new RangeError("sizes must be at least 1");
  if (trials < 2) {
    throw new RangeError(
      "trials must be at least 2, or there is no spread to measure and every rung is " +
        "exact by construction rather than by fact"
    );
  }
  if (tolerance !== null && tolerance <= 0) {
    throw new RangeError(
      "a tolerance of 0 admits no difference at all; leave it null to have the refusal " +
        "reported instead"
    );
  }
  const names = classes ? [...classes] : [...klass.NAMES];
  for (const name of names) {
    if (!(name in klass.BY_NAME)) {
      throw new RangeError(
        `no candidate class named '${name}'; known: ${klass.NAMES.join(", ")}`
      );
    }
  }

  const cache = collect(fn, sizes, makeInput, trials, seed0);
  reproducible(fn, sizes, makeInput, seed0, cache);

  const perChannel = {};
  for (const channel of CHANNELS) {
    perChannel[channel] = classify(cache, sizes, channel, trials, seed0, names, tolerance);
  }
  const undetermined = CHANNELS.filter(
    (c) => perChannel[c].verdict === UNDETERMINED
  ).sort();
  return {
    sizes,
    trials,
    tolerance,
    candidates: names,
    per_channel: perChannel,
    undetermined,
    notes: undetermined.map((c) => `\`${c}\`: ${perChannel[c].why}`),
  };
}

// -------------------------------------------------------------------- collecting

const key = (size, seed) => `${size}:${seed}`;

function collect(fn, sizes, makeInput, trials, seed0) {
  const cache = new Map();
  for (const size of sizes) {
    for (let i = 0; i < trials; i += 1) {
      cache.set(key(size, seed0 + i), one(fn, size, makeInput, seed0 + i));
    }
  }
  return cache;
}

function one(fn, size, makeInput, seed) {
  const counter = new Counter();
  const value = makeInput(size, new Rng(seed));
  const wrapped = instrument(value, counter);
  if (fn.length >= 2) {
    // THE INSTRUMENT ONLY SEES THE OBJECT IT WRAPPED. A function that copies its input
    // into working structures of its own — which is most out-of-place algorithms, merge
    // sort first among them — does the rest of its work where nothing is counting, and
    // the honest report of that is a small number rather than a wrong one.
    fn(wrapped, (obj) => instrument(obj, counter));
  } else {
    fn(wrapped);
  }
  return counter.snapshot();
}

/**
 * The same `(size, seed)` must produce the same counts, or nothing below means anything.
 *
 * Checked at the cheapest place it can fail — the first and last rung — because a function
 * whose count is stable at one size and not at another is stable at neither.
 *
 * A throw, not a `look`. The refusals elsewhere describe what the function would not
 * reveal; this one says the instrument was wired up wrong.
 */
function reproducible(fn, sizes, makeInput, seed0, cache) {
  for (const size of new Set([sizes[0], sizes[sizes.length - 1]])) {
    const again = one(fn, size, makeInput, seed0);
    const first = cache.get(key(size, seed0));
    if (again.reads !== first.reads || again.writes !== first.writes) {
      throw new Error(
        `the run is not reproducible: at size=${size} and seed=${seed0} the counts were ` +
          `${JSON.stringify(first)} and then ${JSON.stringify(again)}. Every constant ` +
          `below is fitted from a mean over seeds, so a function or an input builder that ` +
          `reads the clock, the environment or an unseeded generator yields a mean over ` +
          `noise — which still plateaus, and would be reported as an answer`
      );
    }
  }
}

// ------------------------------------------------------------------ classifying

function classify(cache, sizes, channel, trials, seed0, names, tolerance) {
  const raw = {};
  const means = {};
  for (const size of sizes) {
    const values = [];
    for (let i = 0; i < trials; i += 1) values.push(cache.get(key(size, seed0 + i))[channel]);
    raw[size] = values;
    means[size] = values.reduce((a, b) => a + b, 0) / values.length;
  }

  if (sizes.every((size) => raw[size].every((v) => v === 0))) {
    return channelReport(UNEXERCISED, UNDETERMINED,
      `no ${channel} were recorded at any size — this function never subscripts the ` +
        `input it was given, so there is nothing here to fit a class to`,
      means, {}, []);
  }

  const varying = sizes.filter((size) => new Set(raw[size]).size > 1).length;
  const regime = varying ? MEASURED : EXACT;

  if (regime === EXACT && tolerance === null) {
    // THE REFUSAL THAT COST THE MOST TO GET RIGHT. With a count that depends only on n,
    // every rung has a standard error of exactly zero — and `undetermined`'s `ladderFor`
    // drops such rungs, so an unguarded call reports "ladder shorter than the required run
    // of 3" about a ladder that was full. That message describes the ladder and the truth
    // is about the function, and the two send you to different places.
    return channelReport(EXACT, UNDETERMINED,
      `the ${channel} count depends only on the size, not on the input: every trial at ` +
        `every size returned the same number. There is no noise for a plateau to be ` +
        `compared against, and comparing against the SIZE instead is the one mistake this ` +
        `line of tools is shaped around not making. Pass \`tolerance\` to declare how ` +
        `close is close enough, or read the counts below and name the class yourself`,
      means, {}, []);
  }

  const ladders = {};
  const settled = [];
  let flooredTotal = 0;
  for (const name of names) {
    const truths = klass.truthsFor(name, sizes);
    if (truths === null) {
      ladders[name] = { skipped: "the class overflows on this ladder" };
      continue;
    }
    const rungs = [];
    let dropped = 0;
    let floored = 0;
    sizes.forEach((size, i) => {
      const sample = sampler(cache, size, channel, seed0);
      const [c, se0] = fit(sample, truths[i], trials, seed0);
      if (c === null || c === undefined) {
        dropped += 1;
        return;
      }
      let se = se0;
      if (tolerance !== null) {
        const floor = tolerance * Math.abs(c);
        if (floor > (se || 0)) {
          floored += 1;
          se = floor;
        }
      }
      if (!se) {
        dropped += 1;
        return;
      }
      rungs.push({ truth: truths[i], c, se });
    });
    flooredTotal += floored;
    let found =
      rungs.length >= PLATEAU_RUN
        ? plateau(rungs)
        : {
            value: UNDETERMINED,
            se: null,
            from_truth: null,
            why:
              `only ${rungs.length} of ${sizes.length} rungs carried an error bar; ` +
              `${dropped} had none and were dropped`,
          };
    found = { ...found, why: plateauWhy(found, truths, sizes, rungs) };
    ladders[name] = { rungs, dropped, floored, plateau: found };
    if (found.value !== UNDETERMINED) settled.push(name);
  }

  if (settled.length === 0) {
    // ONE SENTENCE, NOT SIX. The first version joined every candidate's own reason into a
    // single line and produced five hundred characters of prose that nobody read to the
    // end. The per-class reasons are still in `ladders[name].plateau` and `describe`
    // prints them one to a line, which is where a reader looks anyway.
    const tried = names.filter((n) => ladders[n].plateau).length;
    return channelReport(regime, UNDETERMINED,
      `no candidate class settles over sizes ${sizes[0]}..${sizes[sizes.length - 1]}; ` +
        `${tried} candidate(s) tried and every one of them is still moving where the ` +
        `ladder ends`,
      means, ladders, settled, flooredTotal);
  }
  if (settled.length > 1) {
    // NOT A TIE TO BE BROKEN. Two classes agreeing means the ladder is too short or too
    // noisy to tell them apart, and picking the better-looking one would be exactly the
    // confident answer this package exists not to give.
    //
    // "Widen it" is advice nobody can act on without doing the arithmetic, so the
    // arithmetic is done here.
    const which =
      settled.length === 2
        ? `\`${settled[0]}\` and \`${settled[1]}\` both settle`
        : `${settled.length} candidates all settle (${settled.join(", ")})`;
    return channelReport(regime, UNDETERMINED,
      `${which} over sizes ${sizes[0]}..${sizes[sizes.length - 1]}, so the ladder cannot ` +
        `tell them apart — ${separationAdvice(settled, sizes)}`,
      means, ladders, settled, flooredTotal);
  }

  const name = settled[0];
  const found = ladders[name].plateau;
  return channelReport(regime, name, found.why, means, ladders, settled, flooredTotal, {
    constant: found.value,
    constant_se: found.se,
    from_truth: found.from_truth,
  });
}

/**
 * `undetermined`'s verdict, restated in SIZES and rendered by this package.
 *
 * Two reasons, and the second is the one that made this necessary.
 *
 * A reader thinks in input sizes. `4 rungs from truth=16777216` is a true statement about
 * an internal quantity — the value of `n^3` at n=256 — and it tells nobody anything.
 * `from size 256 up` is the same fact in the units the ladder was written in.
 *
 * AND A DEPENDENCY'S MESSAGE IS NOT THIS PACKAGE'S CONTRACT. `undetermined`'s two halves
 * format that truth differently for any integer at or above 1e6: the Python half uses
 * `%g` and prints `1e+06`, this half's `fmt` returns `String(x)` and prints `1000000`.
 * Their own parity suite asserts these strings agree, on a ladder whose truths top out at
 * 512. This package's parity suite compares the RENDERED REPORT, so it saw it — and the
 * fix is not to reformat somebody else's sentence but to stop quoting it where it carries
 * a number.
 *
 * The refusals are quoted verbatim, because they carry no numbers either half formats.
 */
export function plateauWhy(found, truths, sizes, rungs) {
  if (found.value === UNDETERMINED) return found.why;
  const start = found.from_truth;
  const at = truths.indexOf(start);
  const size = at >= 0 ? sizes[at] : sizes[0];
  const run =
    start === null || start === undefined
      ? rungs.length
      : rungs.filter((r) => r.truth >= start).length;
  return `${run} rungs agree within ${PLATEAU_K.toFixed(1)} sigma, from size ${size} up`;
}

/**
 * Round half AWAY FROM ZERO to an integer. Shared with `python/countfn/core.py`.
 *
 * A mean count of 1966.5 renders as `1967` under `Math.round` and `1966` under Python's
 * `%.0f` (half to even). Both halves measured the same number and printed different ones,
 * and the parity suite did not see it because it compared the numbers rather than the
 * report. It compares the report now, and this is the one rule both halves round by.
 */
export function halfUp(value) {
  const rounded = Math.floor(Math.abs(value) + 0.5);
  return value < 0 ? -rounded : rounded;
}

/**
 * Round half-UP to one place and render it. Shared with `python/countfn/core.py`.
 *
 * Not `toFixed(1)`, and not Python's `format(x, ".1f")`: JavaScript rounds half away from
 * zero and Python rounds half to even, so `1.25` renders as `1.3` in one half and `1.2` in
 * the other. The parity suite compares these strings, so the rounding is done the same way
 * in both before anything is formatted.
 */
export function oneDp(value) {
  let rounded = Math.floor(Math.abs(value) * 10 + 0.5) / 10;
  if (value < 0) rounded = -rounded;
  return String(rounded);
}

/** How many times `g(high)` exceeds `g(low)` — a class's growth across a ladder. */
export function spreadOver(name, low, high) {
  const fn = klass.BY_NAME[name];
  const bottom = fn(low);
  return bottom ? fn(high) / bottom : null;
}

/**
 * The two settled classes hardest to tell apart, and by how little they differ.
 *
 * THE BINDING CONSTRAINT IS THE NEAREST PAIR, not the first two. When six candidates settle
 * at once, `1` and `2^n` are trivially far apart and say nothing about whether the ladder
 * is adequate; the pair that grows most alike is the one that has to be separated.
 */
export function closestPair(settled, sizes) {
  let best = null;
  for (let i = 0; i + 1 < settled.length; i += 1) {
    const a = spreadOver(settled[i], sizes[0], sizes[sizes.length - 1]);
    const b = spreadOver(settled[i + 1], sizes[0], sizes[sizes.length - 1]);
    if (!a || !b) continue;
    const ratio = Math.max(a, b) / Math.min(a, b);
    if (best === null || ratio < best[2]) best = [settled[i], settled[i + 1], ratio];
  }
  return best;
}

/**
 * What widening the ladder would actually buy, in a number rather than a verb.
 *
 * Over 16..128, `n` grows 8x and `n log n` grows 14x, so they differ by 1.8x and a constant
 * that settles for one settles for the other. Over 16..1024 the same pair differ by 2.5x.
 */
export function separationAdvice(settled, sizes) {
  const pair = closestPair(settled, sizes);
  if (pair === null) return "widen the ladder or raise `trials`";
  const [first, second, ratio] = pair;
  const wider = sizes[sizes.length - 1] * 8;
  const a = spreadOver(first, sizes[0], wider);
  const b = spreadOver(second, sizes[0], wider);
  const head =
    (settled.length === 2
      ? "their growth differs by only "
      : `\`${first}\` and \`${second}\` are the hardest of them to separate, and their ` +
        `growth differs by only `) + `${oneDp(ratio)}x across this ladder`;
  if (!a || !b || !Number.isFinite(a) || !Number.isFinite(b)) {
    return (
      `${head}; raise \`trials\`, or narrow \`classes\` to the candidates you are ` +
      `actually choosing between`
    );
  }
  const later = Math.max(a, b) / Math.min(a, b);
  return (
    `${head}. A top rung of ${wider} would make that ${oneDp(later)}x; raising ` +
    `\`trials\` shrinks the error bars instead, and either may be enough`
  );
}

/**
 * `fit` calls this with (truth, seed); the truth is the CLASS's and the size is not.
 *
 * Closing over the size rather than looking it up by truth is what lets the constant class
 * `1` be a candidate at all: it gives every rung the same truth, and a lookup keyed on
 * truth would collapse the whole ladder onto one rung without saying so.
 */
function sampler(cache, size, channel) {
  return (_truth, seed) => cache.get(key(size, seed))[channel];
}

function channelReport(regime, verdict, why, means, ladders, settled, floored = 0,
                       { constant = null, constant_se = null, from_truth = null } = {}) {
  let coefficient = null;
  let coefficientSe = null;
  if (constant) {
    // `undetermined` fits c such that c * E[count] == truth, so the number a reader wants
    // — count ≈ k * g(n) — is its reciprocal, with the error carried through.
    coefficient = 1.0 / constant;
    if (constant_se !== null) coefficientSe = constant_se / constant ** 2;
  }
  return {
    regime,
    verdict,
    why,
    constant,
    constant_se,
    coefficient,
    coefficient_se: coefficientSe,
    from_truth,
    settled,
    mean_counts: means,
    ladders,
    declared_error_bars: floored,
  };
}

// -------------------------------------------------------------------- reporting

/**
 * The report as text. Every line says what it is and what decided it.
 *
 * UNEXERCISED CHANNELS ARE COLLAPSED ONTO ONE LINE. Three channels means a read-only
 * function otherwise spends two thirds of its report saying nothing happened, and a reader
 * who has to skip most of a report stops reading reports.
 *
 * `{ candidates: true }` adds, under any UNDETERMINED channel, one line per candidate class
 * saying why that class did not settle.
 */
export function describe(report, { candidates = false } = {}) {
  const lines = [
    `sizes [${report.sizes.join(", ")}]  trials ${report.trials}` +
      (report.tolerance ? `  tolerance ${report.tolerance}` : ""),
  ];
  const g = (x, n) => Number(x.toPrecision(n));
  const quiet = CHANNELS.filter((c) => report.per_channel[c].regime === UNEXERCISED);
  for (const channel of CHANNELS) {
    if (quiet.includes(channel)) continue;
    const entry = report.per_channel[channel];
    const counts = report.sizes
      .map((n) => `${n}:${halfUp(entry.mean_counts[n] ?? 0)}`)
      .join("  ");
    if (entry.verdict === UNDETERMINED) {
      lines.push(`${channel.padEnd(8)} UNDETERMINED  [${entry.regime}]`);
      lines.push(`         ${entry.why}`);
    } else {
      const bar =
        entry.coefficient_se !== null ? ` +/- ${g(entry.coefficient_se, 4)}` : "";
      lines.push(
        `${channel.padEnd(8)} ${entry.verdict.padEnd(9)} ${channel} ≈ ` +
          `${g(entry.coefficient, 4)}${bar} · ${entry.verdict}   [${entry.regime}]`
      );
      lines.push(`         ${entry.why}`);
      if (entry.declared_error_bars) {
        lines.push(
          `         ${entry.declared_error_bars} rung(s) used the DECLARED tolerance as ` +
            `their error bar rather than a measured one`
        );
      }
    }
    lines.push(`         mean counts: ${counts}`);
    // Only where a ladder was actually built. In the `exact` regime nothing was fitted, so
    // every line would read "not tried".
    if (candidates && entry.verdict === UNDETERMINED &&
        Object.keys(entry.ladders).length) {
      for (const name of report.candidates) {
        const ladder = entry.ladders[name] || {};
        const reason = ladder.skipped || (ladder.plateau || {}).why || "not tried";
        lines.push(`           ${name.padEnd(9)} ${reason}`);
      }
    }
  }
  if (quiet.length) {
    lines.push(
      `${quiet.join(", ")}: unexercised — this function performed none of those on the ` +
        `input it was given, so there is nothing to fit a class to`
    );
  }
  return lines.join("\n");
}
