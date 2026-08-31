/**
 * The candidate growth functions, and nothing clever.
 *
 * A class is a name and a function of n. It is a CANDIDATE, never a conclusion: the whole
 * point of this package is that a class is reported only when the ratio between the
 * measured count and that function stops moving, and `UNDETERMINED` when no candidate
 * does.
 *
 * `2^n` is here and will be dropped for any ladder that overflows it, which is most of
 * them. That is not a defect: an exponential function measured at n=1024 is not a
 * measurement, and silently returning `Infinity` for a rung would put an infinity into an
 * average.
 */

const log2 = (n) => (n > 1 ? Math.log2(n) : 1.0);

export const CLASSES = [
  ["1", () => 1.0],
  ["log n", (n) => log2(n)],
  ["n", (n) => n],
  ["n log n", (n) => n * log2(n)],
  ["n^2", (n) => n ** 2],
  ["n^3", (n) => n ** 3],
  ["2^n", (n) => 2 ** n],
];

export const NAMES = CLASSES.map(([name]) => name);
export const BY_NAME = Object.fromEntries(CLASSES);

/**
 * `sizes.map(g)`, or null when the class cannot be evaluated on them.
 *
 * Returning null rather than throwing is what lets a ladder that overflows `2^n` still
 * answer about `n log n`, with the dropped candidate named in the report instead of
 * quietly missing from it.
 */
export function truthsFor(name, sizes) {
  const fn = BY_NAME[name];
  const out = [];
  for (const n of sizes) {
    const value = fn(n);
    if (!Number.isFinite(value) || value <= 0) return null;
    out.push(value);
  }
  return out;
}
