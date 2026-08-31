/**
 * One pseudo-random generator, implemented identically in both halves.
 *
 * WHY NOT `Math.random`. `makeInput(n, rng)` is the user's code, and the point of this
 * package is that a size and a seed determine a count. `Math.random` cannot be seeded at
 * all, and Python's Mersenne Twister is a different stream again — so the same
 * `makeInput` written twice would build two different inputs and the two halves would
 * count different things while both being right.
 *
 * So the generator is part of the contract. This is **mulberry32**, chosen because it is
 * eleven lines, is exactly specifiable in 32-bit arithmetic, and has no state the two
 * languages represent differently. `python/tests/test_parity.py` asserts the two streams
 * are identical for the same seed rather than assuming it.
 *
 * It is NOT cryptographic and is not offered as one. It generates test inputs.
 */

export class Rng {
  constructor(seed) {
    this.seed = seed >>> 0;
    this._a = this.seed;
  }

  /** A float in [0, 1). */
  random() {
    let a = (this._a = (this._a + 0x6d2b79f5) | 0);
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  }

  /** An integer in [0, n). */
  int(n) {
    if (n <= 0) throw new RangeError("int(n) needs n >= 1");
    return Math.floor(this.random() * n);
  }

  /** Fisher-Yates, in place, and the same swaps in both halves. */
  shuffle(values) {
    for (let i = values.length - 1; i > 0; i -= 1) {
      const j = this.int(i + 1);
      const tmp = values[i];
      values[i] = values[j];
      values[j] = tmp;
    }
    return values;
  }

  /**
   * `k` distinct integers from [0, n), in increasing order.
   *
   * Increasing because the common use is a sorted input, and sorting it afterwards with
   * the language's own sort would put a second uncounted algorithm between the generator
   * and the thing being measured.
   */
  sample(n, k) {
    if (k > n) throw new RangeError(`cannot take ${k} distinct values from a range of ${n}`);
    const pool = Array.from({ length: n }, (_, i) => i);
    for (let i = 0; i < k; i += 1) {
      const j = i + this.int(n - i);
      const tmp = pool[i];
      pool[i] = pool[j];
      pool[j] = tmp;
    }
    return pool.slice(0, k).sort((x, y) => x - y);
  }

  /** `count` integers in [0, bound), with repeats allowed. */
  ints(count, bound) {
    const out = [];
    for (let i = 0; i < count; i += 1) out.push(this.int(bound));
    return out;
  }
}
