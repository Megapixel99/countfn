"""The two halves agree about the COUNTS, not only about the words.

`didrun` and `zerocase` assert that their halves reach the same verdict and print the same
sentence. This package can claim something stronger and does: one seeded generator
(mulberry32, identical 32-bit arithmetic), one iteration rule (n reads, never n+1), one
subscript rule (integer keys only) — so the same algorithm on the same seed performs the
same counted operations in Python and in JavaScript, to the integer.

A claim that strong is only worth making if it is checked, so four algorithms written to
one spec are run through both halves and their mean count tables compared. Anything else
would be two instruments agreeing about their own opinions.

THE TABLE LIVES HERE AND NOWHERE ELSE, sent to the JavaScript half over stdin — a parity
suite whose two sides maintain their own inputs drifts by being asked different questions,
and then reports agreement about that.

The suite SKIPS when `node` is absent so a Python-only contributor can run everything else.
CI asserts it was not skipped: a skip and a pass are identical in a tally.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DUMP = os.path.join(ROOT, "js", "test", "dump.mjs")
sys.path.insert(0, os.path.join(ROOT, "python"))
sys.path.insert(0, HERE)

from countfn import UNDETERMINED, describe, measure          # noqa: E402
from countfn.rng import Rng                                  # noqa: E402

from _scenarios import SCENARIOS                             # noqa: E402

# Small ladders on purpose. The point here is that two instruments agree, not that a
# constant is nailed down -- and a parity suite nobody waits for is a parity suite that
# gets an `@skip` the first time it is inconvenient.
TABLE = [
    ("linear-scan", {"sizes": [16, 32, 64, 128], "trials": 5}),
    ("linear-scan", {"sizes": [16, 32, 64, 128], "trials": 5, "tolerance": 0.05}),
    ("binary-search", {"sizes": [64, 128, 256, 512], "trials": 30}),
    ("insertion-sort", {"sizes": [16, 32, 64, 128], "trials": 8}),
    ("merge-sort", {"sizes": [16, 32, 64, 128], "trials": 5, "tolerance": 0.05}),
    ("comparison-sort", {"sizes": [16, 32, 64, 128], "trials": 8}),
    # Two classes settling is a message with arithmetic in it — a ratio rendered to one
    # decimal place — and the two languages round halves in opposite directions by
    # default. This row is here so the string is compared rather than the intention.
    ("binary-search", {"sizes": [64, 128, 256], "trials": 10, "tolerance": 5.0}),
]

STREAMS = [0, 1, 17, 4242]

node = shutil.which("node")


def _python_side():
    scenarios = []
    for name, options in TABLE:
        fn, make_input = SCENARIOS[name]
        report = measure(fn, make_input=make_input, **options)
        scenarios.append({
            "name": name,
            "per_channel": {
                channel: {
                    "regime": entry["regime"],
                    "verdict": entry["verdict"],
                    "why": entry["why"],
                    # JSON object keys are strings in JavaScript, so the size keys are
                    # normalised here rather than compared as two different types.
                    "mean_counts": {str(k): v for k, v in entry["mean_counts"].items()},
                    "declared_error_bars": entry["declared_error_bars"],
                }
                for channel, entry in report["per_channel"].items()
            },
            "undetermined": report["undetermined"],
            "text": describe(report, candidates=True),
        })
    streams = []
    for seed in STREAMS:
        r = Rng(seed)
        streams.append({
            "seed": seed,
            "random": [r.random() for _ in range(5)],
            "sample": Rng(seed).sample(50, 8),
            "ints": Rng(seed).ints(8, 1000),
            "shuffle": Rng(seed).shuffle([0, 1, 2, 3, 4, 5, 6, 7]),
        })
    return {"scenarios": scenarios, "streams": streams}


def _javascript_side():
    payload = {"scenarios": [[name, opts] for name, opts in TABLE], "streams": STREAMS}
    out = subprocess.run([node, DUMP], input=json.dumps(payload), text=True,
                         capture_output=True, cwd=ROOT)
    if out.returncode != 0:
        raise AssertionError(f"the JavaScript half exited {out.returncode}:\n{out.stderr}")
    return json.loads(out.stdout)


@unittest.skipUnless(node, "node is not on PATH")
class TheHalvesAgree(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.py = _python_side()
        cls.js = _javascript_side()

    def test_the_generators_produce_identical_streams(self):
        """The foundation. Different inputs would make every count below incomparable."""
        for mine, theirs in zip(self.py["streams"], self.js["streams"]):
            with self.subTest(seed=mine["seed"]):
                self.assertEqual(mine, theirs)

    def test_the_same_algorithm_performs_the_same_counted_operations(self):
        """The claim `didrun` and `zerocase` cannot make: agreement to the integer."""
        for (name, options), mine, theirs in zip(TABLE, self.py["scenarios"],
                                                 self.js["scenarios"]):
            for channel in ("reads", "writes", "calls"):
                with self.subTest(scenario=name, options=options, channel=channel):
                    self.assertEqual(mine["per_channel"][channel]["mean_counts"],
                                     theirs["per_channel"][channel]["mean_counts"])

    def test_the_rendered_report_is_identical_character_for_character(self):
        """Not only the numbers: the report is what a person actually reads.

        This was added because it found something. Both halves measured a mean count of
        1966.5 and printed it as 1966 and 1967 — Python's `%.0f` rounds half to even and
        `Math.round` rounds half away from zero — and every assertion that compared the
        means passed.
        """
        for (name, options), mine, theirs in zip(TABLE, self.py["scenarios"],
                                                 self.js["scenarios"]):
            with self.subTest(scenario=name, options=options):
                self.assertEqual(mine["text"], theirs["text"])

    def test_the_verdicts_and_the_reasons_are_identical(self):
        for (name, options), mine, theirs in zip(TABLE, self.py["scenarios"],
                                                 self.js["scenarios"]):
            with self.subTest(scenario=name, options=options):
                self.assertEqual(mine, theirs)

    def test_the_table_reaches_more_than_one_verdict(self):
        """The divergence gate, applied to the parity suite itself.

        Two halves that both always answered `UNDETERMINED` would agree perfectly and
        prove nothing. The table has to contain a scenario that yields a class, one that
        yields the `exact` refusal, and one channel that was never exercised — or
        agreement is agreement about a constant.
        """
        verdicts = {entry["per_channel"][ch]["verdict"]
                    for entry in self.py["scenarios"]
                    for ch in ("reads", "writes", "calls")}
        regimes = {entry["per_channel"][ch]["regime"]
                   for entry in self.py["scenarios"]
                   for ch in ("reads", "writes", "calls")}
        self.assertIn(UNDETERMINED, verdicts)
        self.assertGreaterEqual(len([v for v in verdicts if v is not UNDETERMINED]), 2,
                                f"only these classes were ever reported: {verdicts}")
        self.assertEqual(regimes, {"measured", "exact", "unexercised"},
                         f"the table never reaches every regime: {regimes}")

    def test_describe_renders_without_raising_on_every_row(self):
        """The printer is the part a person reads, and it is the part with no assertions."""
        for name, options in TABLE:
            fn, make_input = SCENARIOS[name]
            text = describe(measure(fn, make_input=make_input, **options))
            self.assertIn("mean counts", text)


if __name__ == "__main__":
    unittest.main()
