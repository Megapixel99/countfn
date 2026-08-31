/**
 * Four algorithms, written to the same spec in both halves.
 *
 * THE PARITY CLAIM THIS PACKAGE CAN MAKE THAT ITS SIBLINGS CANNOT. `didrun` and
 * `zerocase` assert that their halves agree about verdicts and sentences. Here the halves
 * can agree about the NUMBERS: one seeded generator (mulberry32, identical arithmetic),
 * one iteration rule (n reads, not n+1), one subscript rule (integer keys only), so the
 * same algorithm on the same seed performs the same counted operations in both languages.
 *
 * `python/tests/_scenarios.py` holds the same four, and any divergence between the two
 * files is a finding rather than a nuisance: it means one half's instrument counts
 * something the other's does not.
 *
 * They are deliberately small and written without library calls. `Array.prototype.sort`
 * and `sorted()` are different algorithms doing uncounted work.
 */

export function linearScan(data) {
  let total = 0;
  for (const value of data) total += value;
  return total;
}

/** Searches for a FIXED target, so the path length varies with the input. */
export function binarySearch(data) {
  let lo = 0;
  let hi = data.length - 1;
  while (lo <= hi) {
    const mid = Math.floor((lo + hi) / 2);
    const value = data[mid];
    if (value === 500) return mid;
    if (value < 500) lo = mid + 1;
    else hi = mid - 1;
  }
  return -1;
}

export function insertionSort(data) {
  for (let i = 1; i < data.length; i += 1) {
    let j = i;
    while (j > 0 && data[j - 1] > data[j]) {
      const tmp = data[j - 1];
      data[j - 1] = data[j];
      data[j] = tmp;
      j -= 1;
    }
  }
  return data;
}

/** The out-of-place case, and the reason `probe` exists. */
export function mergeSort(data, probe) {
  let runs = [];
  for (let i = 0; i < data.length; i += 1) runs.push(probe([data[i]]));
  while (runs.length > 1) {
    const merged = [];
    for (let i = 0; i + 1 < runs.length; i += 2) {
      const left = runs[i];
      const right = runs[i + 1];
      const out = probe([]);
      let x = 0;
      let y = 0;
      while (x < left.length && y < right.length) {
        if (left[x] <= right[y]) {
          out.push(left[x]);
          x += 1;
        } else {
          out.push(right[y]);
          y += 1;
        }
      }
      while (x < left.length) {
        out.push(left[x]);
        x += 1;
      }
      while (y < right.length) {
        out.push(right[y]);
        y += 1;
      }
      merged.push(out);
    }
    if (runs.length % 2) merged.push(runs[runs.length - 1]);
    runs = merged;
  }
  return runs[0];
}

/**
 * An insertion sort that asks a PROBED comparator, so `calls` is a real channel.
 *
 * This is the shape the `calls` channel exists for: `reads` and `writes` describe how much
 * the algorithm moves data about, and the number anybody quotes for a sort is how many
 * comparisons it made. Wrapping the comparator is exact in both languages; intercepting
 * `<` is not.
 */
export function comparisonSort(data, probe) {
  const less = probe((a, b) => a < b);
  for (let i = 1; i < data.length; i += 1) {
    let j = i;
    while (j > 0 && less(data[j], data[j - 1])) {
      const tmp = data[j - 1];
      data[j - 1] = data[j];
      data[j] = tmp;
      j -= 1;
    }
  }
  return data;
}

export const SCENARIOS = {
  "linear-scan": [linearScan, (n, rng) => rng.ints(n, 1000)],
  "binary-search": [binarySearch, (n, rng) => rng.sample(n * 10, n)],
  "insertion-sort": [insertionSort, (n, rng) => rng.ints(n, 10000)],
  "merge-sort": [mergeSort, (n, rng) => rng.ints(n, 10 ** 6)],
  "comparison-sort": [comparisonSort, (n, rng) => rng.ints(n, 10000)],
};
