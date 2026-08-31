/**
 * countfn — how does this function's cost scale? Counted, not timed.
 *
 *     import { measure, describe } from "countfn";
 *     console.log(describe(measure(fn, {
 *       sizes: [64, 128, 256, 512, 1024, 2048],
 *       makeInput: (n, rng) => rng.sample(n * 10, n),
 *     })));
 *
 * Built on `undetermined`: the ladder, the standard errors, the three-rung plateau and the
 * refusal are its machinery, imported rather than copied. What is here is an instrument
 * that counts operations instead of reading a clock — because a timing is a mean over
 * noise, and `undetermined` refuses such an observable outright.
 */

export { UNDETERMINED } from "undetermined";
export { measure, describe, EXACT, MEASURED, UNEXERCISED } from "./core.js";
export { Counter, CHANNELS, countedArray, countedCallable, countedMapping, instrument }
  from "./counters.js";
export { Rng } from "./rng.js";
export { NAMES as CLASS_NAMES } from "./classes.js";
export const VERSION = "0.1.2";
