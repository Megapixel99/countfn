/**
 * A pure function, for the parity suite to compare against.
 *
 * Reads `{scenarios: [[name, options]], streams: [seed]}` from stdin and prints what the
 * JavaScript half makes of each. THE TABLE IS NOT HERE ON PURPOSE: `test_parity.py` owns
 * it and sends it over, so the two halves cannot drift by being asked different questions
 * — the failure mode of a parity suite that keeps a copy of the inputs on each side.
 *
 * Not published: `files` in package.json lists `js/src`.
 */
import fs from "node:fs";
import { describe, measure } from "../src/core.js";
import { Rng } from "../src/rng.js";
import { SCENARIOS } from "./scenarios.mjs";

const input = JSON.parse(fs.readFileSync(0, "utf8"));

const scenarios = (input.scenarios || []).map(([name, options]) => {
  const [fn, makeInput] = SCENARIOS[name];
  try {
    const report = measure(fn, { ...options, makeInput });
    const out = { name, per_channel: {} };
    for (const [channel, entry] of Object.entries(report.per_channel)) {
      out.per_channel[channel] = {
        regime: entry.regime,
        verdict: entry.verdict,
        why: entry.why,
        mean_counts: entry.mean_counts,
        declared_error_bars: entry.declared_error_bars,
      };
    }
    out.undetermined = report.undetermined;
    // THE RENDERED REPORT, not only the numbers it was rendered from. Two halves agreed
    // on a mean of 1966.5 and printed 1966 and 1967, and a parity suite comparing only
    // the means could not see it.
    out.text = describe(report, { candidates: true });
    return out;
  } catch (err) {
    return { name, error: err.message };
  }
});

const streams = (input.streams || []).map((seed) => {
  const r = new Rng(seed);
  return {
    seed,
    random: [...Array(5)].map(() => r.random()),
    sample: new Rng(seed).sample(50, 8),
    ints: new Rng(seed).ints(8, 1000),
    shuffle: new Rng(seed).shuffle([0, 1, 2, 3, 4, 5, 6, 7]),
  };
});

process.stdout.write(JSON.stringify({ scenarios, streams }, null, 2) + "\n");
