/**
 * What the instrument counts, and what the report refuses to say about it.
 *
 * The parity suite proves the two halves agree; agreement is not correctness, and two
 * halves can be wrong in the same way. THIS suite is the oracle for the JavaScript half:
 * the expected counts are written down beside algorithms whose loop structure a person can
 * read.
 */
import test from "node:test";
import assert from "node:assert/strict";

import { UNDETERMINED, describe, measure } from "../src/index.js";
import { closestPair, halfUp, oneDp } from "../src/core.js";
import { Counter, instrument } from "../src/counters.js";
import { Rng } from "../src/rng.js";
import {
  binarySearch, comparisonSort, insertionSort, linearScan, mergeSort,
} from "./scenarios.mjs";

const counted = (data) => {
  const counter = new Counter();
  return [instrument(data, counter), counter];
};

const LADDER = { sizes: [16, 32, 64, 128], trials: 8 };
const ints = (n, rng) => rng.ints(n, 10000);

// ------------------------------------------------------------------ the generator

test("the same seed is the same stream", () => {
  const a = [...Array(4)].map(((r) => () => r.random())(new Rng(9)));
  const b = [...Array(4)].map(((r) => () => r.random())(new Rng(9)));
  assert.deepEqual(a, b);
  assert.notEqual(new Rng(9).random(), new Rng(10).random());
});

test("int stays in range", () => {
  const r = new Rng(3);
  for (let i = 0; i < 200; i += 1) {
    const v = r.int(7);
    assert.ok(v >= 0 && v < 7);
  }
});

test("sample is distinct, sorted and the right length", () => {
  const drawn = new Rng(5).sample(100, 12);
  assert.equal(drawn.length, 12);
  assert.equal(new Set(drawn).size, 12);
  assert.deepEqual(drawn, [...drawn].sort((x, y) => x - y));
  assert.ok(drawn.every((v) => v >= 0 && v < 100));
});

test("sample refuses to draw more than there is", () => {
  assert.throws(() => new Rng(5).sample(4, 9), RangeError);
});

test("shuffle is a permutation", () => {
  const out = new Rng(1).shuffle([...Array(20).keys()]);
  assert.deepEqual([...out].sort((a, b) => a - b), [...Array(20).keys()]);
});

// ----------------------------------------------------------------- the instrument

test("iteration is one read per element", () => {
  // n, not n+1 — the Python half defines __iter__ to match this.
  const [data, counter] = counted([...Array(10).keys()]);
  let total = 0;
  for (const v of data) total += v;
  assert.equal(total, 45);
  assert.equal(counter.reads, 10);
});

test("a subscript is one read and an assignment is one write", () => {
  const [data, counter] = counted([1, 2, 3]);
  void data[1];
  data[2] = 9;
  assert.deepEqual(counter.snapshot(), { reads: 1, writes: 1, calls: 0 });
});

test("push is one write", () => {
  // `length` is set too and is deliberately not counted, so a push costs one write in
  // both halves — the same as Python's `append`.
  const [data, counter] = counted([]);
  data.push(4);
  assert.deepEqual(counter.snapshot(), { reads: 0, writes: 1, calls: 0 });
});

test("length is not counted", () => {
  const [data, counter] = counted([1, 2, 3]);
  assert.equal(data.length, 3);
  assert.equal(counter.reads, 0);
});

test("a mapping counts lookups and stores", () => {
  const [data, counter] = counted({ a: 1 });
  void data.a;
  data.b = 2;
  assert.ok("a" in data);
  assert.deepEqual(counter.snapshot(), { reads: 2, writes: 1, calls: 0 });
});

test("a callable is counted as calls", () => {
  // The channel that exists because comparisons could not be one. `a < b` calls
  // `Symbol.toPrimitive` on BOTH operands here and one dunder in Python, so counting the
  // operator would mean two events there and one here. Wrapping the callable is exact.
  const counter = new Counter();
  const less = instrument((a, b) => a < b, counter);
  assert.equal(less(1, 2), true);
  assert.equal(less(2, 1), false);
  assert.deepEqual(counter.snapshot(), { reads: 0, writes: 0, calls: 2 });
});

test("a container that is also callable is read as a container", () => {
  // A class is a function here too. Guessing the other way would be silent.
  const counter = new Counter();
  const arrayish = Object.assign([1, 2, 3]);
  const wrapped = instrument(arrayish, counter);
  void wrapped[0];
  assert.equal(counter.reads, 1);
});

test("a value with no subscript is refused rather than measured as zero", () => {
  // Handing it through untouched would report `no operations` — a confident answer to a
  // question that was never asked.
  assert.throws(() => instrument(42, new Counter()), TypeError);
});

// ------------------------------------------------------------------- the verdicts

test("three different answers from three different functions", () => {
  // THE DIVERGENCE GATE, and it is the most important test here. A tool that always said
  // `n^2` would pass a suite containing only insertion sort; a tool that always said
  // UNDETERMINED would pass a suite containing only the refusals, and would be useless.
  const quadratic = measure(insertionSort, { ...LADDER, makeInput: ints });
  const logarithmic = measure(binarySearch, {
    sizes: [64, 128, 256, 512], trials: 30, makeInput: (n, r) => r.sample(n * 10, n),
  });
  const refused = measure(linearScan, {
    ...LADDER, makeInput: (n, r) => r.ints(n, 1000),
  });
  assert.equal(quadratic.per_channel.reads.verdict, "n^2");
  assert.equal(logarithmic.per_channel.reads.verdict, "log n");
  assert.equal(refused.per_channel.reads.verdict, UNDETERMINED);
  assert.equal(refused.per_channel.reads.regime, "exact");
});

test("the coefficient is the count over the class", () => {
  const report = measure(insertionSort, { ...LADDER, makeInput: ints });
  const { reads, writes } = report.per_channel;
  assert.ok(Math.abs(reads.coefficient - 1.0) < 0.15, `${reads.coefficient}`);
  assert.ok(Math.abs(writes.coefficient - 0.5) < 0.1, `${writes.coefficient}`);
  assert.ok(writes.coefficient < reads.coefficient);
});

test("a count that depends only on n is refused and the counts are printed", () => {
  // Every rung of an exact count has a standard error of zero, and `ladderFor` drops such
  // rungs — so an unguarded call would report "ladder shorter than the required run of 3"
  // about a ladder that was full.
  const report = measure(linearScan, { ...LADDER, makeInput: (n, r) => r.ints(n, 1000) });
  const reads = report.per_channel.reads;
  assert.equal(reads.verdict, UNDETERMINED);
  assert.equal(reads.regime, "exact");
  assert.match(reads.why, /depends only on the size/);
  assert.doesNotMatch(reads.why, /ladder shorter/);
  assert.deepEqual(reads.mean_counts, { 16: 16, 32: 32, 64: 64, 128: 128 });
});

test("a declared tolerance opens the exact case and says that it did", () => {
  // The control for the test above: the tolerance, not the function, is what changed.
  const report = measure(linearScan, {
    ...LADDER, tolerance: 0.05, makeInput: (n, r) => r.ints(n, 1000),
  });
  const reads = report.per_channel.reads;
  assert.equal(reads.verdict, "n");
  assert.ok(Math.abs(reads.coefficient - 1.0) < 0.01);
  assert.ok(reads.declared_error_bars > 0,
    "the report must say the error bars were declared, not measured");
});

test("a channel nothing touched says so rather than fitting a class to zero", () => {
  const report = measure(linearScan, { ...LADDER, makeInput: (n, r) => r.ints(n, 1000) });
  const writes = report.per_channel.writes;
  assert.equal(writes.verdict, UNDETERMINED);
  assert.equal(writes.regime, "unexercised");
  assert.match(writes.why, /never subscripts/);
});

test("a constant that is still moving is not a class", () => {
  const report = measure(mergeSort, {
    sizes: [16, 32, 64, 128, 256], trials: 6, makeInput: (n, r) => r.ints(n, 10 ** 6),
  });
  const reads = report.per_channel.reads;
  assert.equal(reads.verdict, UNDETERMINED);
  assert.equal(reads.regime, "measured");
  assert.match(reads.why, /no candidate class settles/);
});

test("two classes that both settle are reported as undetermined", () => {
  // NOT A TIE TO BE BROKEN. Both settling means the ladder cannot tell them apart.
  const report = measure(binarySearch, {
    sizes: [64, 128, 256], trials: 10, tolerance: 5.0,
    makeInput: (n, r) => r.sample(n * 10, n),
  });
  const reads = report.per_channel.reads;
  assert.equal(reads.verdict, UNDETERMINED);
  assert.ok(reads.settled.length > 1);
  assert.match(reads.why, /cannot tell them apart/);
});

test("probe is what makes an out-of-place algorithm measurable", () => {
  const withProbe = measure(mergeSort, {
    sizes: [16, 32, 64, 128], trials: 4, makeInput: (n, r) => r.ints(n, 10 ** 6),
  });
  const blind = measure((data) => mergeSort(data, (x) => x), {
    sizes: [16, 32, 64, 128], trials: 4, makeInput: (n, r) => r.ints(n, 10 ** 6),
  });
  assert.equal(blind.per_channel.reads.mean_counts[128], 128);
  assert.ok(withProbe.per_channel.reads.mean_counts[128] > 128);
});

test("a class that overflows the ladder is named as skipped", () => {
  const report = measure(linearScan, {
    sizes: [128, 256, 512, 1024], trials: 3, tolerance: 0.05,
    makeInput: (n, r) => r.ints(n, 1000),
  });
  const ladders = report.per_channel.reads.ladders;
  assert.ok("skipped" in ladders["2^n"]);
  assert.ok(!("skipped" in ladders.n));
});

test("a probed comparator gives the calls channel a class of its own", () => {
  // An insertion sort compares about n^2/4 times, and that is the number people quote for
  // a sort. Without the `calls` channel it was not measurable at all.
  const report = measure(comparisonSort, { ...LADDER, makeInput: ints });
  const calls = report.per_channel.calls;
  assert.equal(calls.verdict, "n^2");
  assert.ok(Math.abs(calls.coefficient - 0.25) < 0.06, `${calls.coefficient}`);
  assert.ok(calls.coefficient < report.per_channel.reads.coefficient);
});

test("the reason is given in sizes rather than in the ladder truths", () => {
  // `from size 128 up` is the fact a reader can act on. It is also this package's own
  // sentence rather than its dependency's, which is what stops `undetermined`'s two halves
  // formatting a large integer differently from reaching this report.
  const report = measure(insertionSort, {
    sizes: [64, 128, 256], trials: 6, makeInput: ints,
  });
  const why = report.per_channel.reads.why;
  assert.match(why, /from size/);
  assert.doesNotMatch(why, /truth=/);
});

test("describe collapses the channels nothing touched", () => {
  const text = describe(measure(linearScan, {
    ...LADDER, makeInput: (n, r) => r.ints(n, 1000),
  }));
  assert.match(text, /writes, calls: unexercised/);
  assert.equal(text.split("unexercised").length - 1, 1);
});

test("describe can name every candidate and why it did not settle", () => {
  const report = measure(mergeSort, {
    sizes: [16, 32, 64, 128, 256], trials: 6, makeInput: (n, r) => r.ints(n, 10 ** 6),
  });
  const brief = describe(report);
  const full = describe(report, { candidates: true });
  assert.doesNotMatch(brief, /n log n   no run of/);
  for (const name of report.candidates) assert.ok(full.includes(name));
  assert.ok(full.split("\n").length > brief.split("\n").length);
});

test("two classes settling says how much wider the ladder must be", () => {
  // `widen it` is advice nobody can act on without doing the arithmetic.
  const report = measure(binarySearch, {
    sizes: [64, 128, 256], trials: 10, tolerance: 0.4, classes: ["n", "n log n"],
    makeInput: (n, r) => r.sample(n * 10, n),
  });
  const why = report.per_channel.reads.why;
  assert.match(why, /differs by only/);
  assert.match(why, /A top rung of 2048/);
});

test("the binding pair is the nearest one, not the first two", () => {
  // With six candidates settling, `1` and `2^n` are trivially far apart and say nothing
  // about whether the ladder is adequate.
  // Over 16..128: `log n` grows 1.75x, `n log n` 14x, `n^2` 64x. The FIRST pair differs by
  // 8x and the second by 4.6x, so a version that reported the first pair would name the
  // one that is easier to separate and advise on the wrong ladder.
  assert.deepEqual(closestPair(["log n", "n log n", "n^2"], [16, 128]).slice(0, 2),
    ["n log n", "n^2"]);
  assert.deepEqual(closestPair(["n", "n log n", "n^3"], [16, 128]).slice(0, 2),
    ["n", "n log n"]);
});

test("both halves round halves the same way", () => {
  // `Math.round` rounds half away from zero and Python rounds half to even, so a mean of
  // 1966.5 printed as 1967 in one report and 1966 in the other.
  assert.equal(halfUp(1966.5), 1967);
  assert.equal(halfUp(2.5), 3);
  assert.equal(oneDp(1.25), "1.3");
  assert.equal(oneDp(2.0), "2");
});

test("describe says what decided each line", () => {
  const text = describe(measure(insertionSort, { ...LADDER, makeInput: ints }));
  assert.match(text, /n\^2/);
  assert.match(text, /agree within/);
  assert.match(text, /mean counts/);
});

// ---------------------------------------------------------------- the precondition

test("a function that is not reproducible throws rather than being measured", () => {
  // A mean over noise still has a standard error, still plateaus, and would be reported
  // as an answer. So this is a throw, not a refusal.
  let calls = 0;
  const drifting = (data) => {
    calls += 1;
    for (let i = 0; i < Math.min(calls, data.length); i += 1) void data[i];
  };
  assert.throws(
    () => measure(drifting, { ...LADDER, makeInput: (n, r) => r.ints(n, 10) }),
    /not reproducible/
  );
});

test("the control: a stable function is not refused", () => {
  // If everything threw, the test above would pass on a broken precondition.
  const report = measure(linearScan, { ...LADDER, makeInput: (n, r) => r.ints(n, 10) });
  assert.equal(report.per_channel.reads.mean_counts[128], 128);
});

// ------------------------------------------------------------------ the arguments

test("a ladder too short to show a plateau is refused", () => {
  assert.throws(
    () => measure(linearScan, { sizes: [16, 32], trials: 4, makeInput: ints }),
    RangeError
  );
});

test("sizes must be increasing and distinct", () => {
  for (const sizes of [[64, 16, 32], [16, 16, 32]]) {
    assert.throws(() => measure(linearScan, { sizes, trials: 4, makeInput: ints }), RangeError);
  }
});

test("one trial has no spread to measure", () => {
  assert.throws(
    () => measure(linearScan, { sizes: [16, 32, 64], trials: 1, makeInput: ints }),
    RangeError
  );
});

test("a tolerance of zero is refused rather than silently admitting nothing", () => {
  assert.throws(() => measure(linearScan, { ...LADDER, tolerance: 0, makeInput: ints }), RangeError);
});

test("an unknown candidate class is named", () => {
  assert.throws(
    () => measure(linearScan, { ...LADDER, classes: ["n log log n"], makeInput: ints }),
    /n log log n/
  );
});
