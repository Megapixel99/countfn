"""What the instrument counts, and what the report refuses to say about it.

The parity suite proves the two halves agree; agreement is not correctness, and two halves
can be wrong in the same way. THIS suite is the oracle: the expected counts are written
down beside algorithms whose loop structure a person can read.
"""

from __future__ import annotations

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "python"))
sys.path.insert(0, HERE)

from countfn import UNDETERMINED, describe, measure                     # noqa: E402
from countfn.counters import Counter, instrument                        # noqa: E402
from countfn.rng import Rng                                             # noqa: E402

from _scenarios import (binary_search, comparison_sort, insertion_sort,  # noqa: E402
                        linear_scan, merge_sort)


class TheGenerator(unittest.TestCase):
    def test_the_same_seed_is_the_same_stream(self):
        self.assertEqual([Rng(9).random() for _ in range(4)],
                         [Rng(9).random() for _ in range(4)])
        self.assertNotEqual(Rng(9).random(), Rng(10).random())

    def test_int_stays_in_range(self):
        r = Rng(3)
        self.assertTrue(all(0 <= r.int(7) < 7 for _ in range(200)))

    def test_sample_is_distinct_sorted_and_the_right_length(self):
        drawn = Rng(5).sample(100, 12)
        self.assertEqual(len(drawn), 12)
        self.assertEqual(len(set(drawn)), 12)
        self.assertEqual(drawn, sorted(drawn))
        self.assertTrue(all(0 <= v < 100 for v in drawn))

    def test_sample_refuses_to_draw_more_than_there_is(self):
        with self.assertRaises(ValueError):
            Rng(5).sample(4, 9)

    def test_shuffle_is_a_permutation(self):
        self.assertEqual(sorted(Rng(1).shuffle(list(range(20)))), list(range(20)))


class TheInstrument(unittest.TestCase):
    def _counted(self, data):
        counter = Counter()
        return instrument(data, counter), counter

    def test_iteration_is_one_read_per_element(self):
        """n, not n+1. Python's fallback protocol would call __getitem__ until it raised."""
        data, counter = self._counted(list(range(10)))
        self.assertEqual(sum(data), 45)
        self.assertEqual(counter.reads, 10)

    def test_a_subscript_is_one_read_and_an_assignment_is_one_write(self):
        data, counter = self._counted([1, 2, 3])
        _ = data[1]
        data[2] = 9
        self.assertEqual(counter.snapshot(), {"reads": 1, "writes": 1, "calls": 0})

    def test_append_is_one_write(self):
        """The same as `arr.push(x)` costs the JavaScript half."""
        data, counter = self._counted([])
        data.append(4)
        self.assertEqual(counter.snapshot(), {"reads": 0, "writes": 1, "calls": 0})

    def test_a_slice_reads_every_element_it_takes_and_returns_a_plain_list(self):
        """Counting a slice as one read would let a quadratic written with slices
        look linear; returning a counted slice would make the two halves disagree."""
        data, counter = self._counted(list(range(10)))
        chunk = data[2:7]
        self.assertEqual(counter.reads, 5)
        self.assertIsInstance(chunk, list)

    def test_membership_is_a_linear_scan_and_is_counted_as_one(self):
        data, counter = self._counted(list(range(10)))
        self.assertIn(7, data)
        self.assertEqual(counter.reads, 8)

    def test_length_is_not_counted(self):
        """It is O(1) in both languages, and counting it makes every loop header work."""
        data, counter = self._counted([1, 2, 3])
        self.assertEqual(len(data), 3)
        self.assertEqual(counter.reads, 0)

    def test_a_mapping_counts_lookups_and_stores(self):
        data, counter = self._counted({"a": 1})
        _ = data["a"]
        data["b"] = 2
        self.assertIn("a", data)
        self.assertEqual(counter.snapshot(), {"reads": 2, "writes": 1, "calls": 0})

    def test_a_callable_is_counted_as_calls(self):
        """The channel that exists because comparisons could not be one.

        `a < b` calls `Symbol.toPrimitive` on both operands in JavaScript and one dunder
        here, so counting the operator would mean two events there and one here. Wrapping
        the callable is exact in both.
        """
        counter = Counter()
        less = instrument(lambda a, b: a < b, counter)
        self.assertTrue(less(1, 2))
        self.assertFalse(less(2, 1))
        self.assertEqual(counter.snapshot(), {"reads": 0, "writes": 0, "calls": 2})

    def test_a_container_that_is_also_callable_is_read_as_a_container(self):
        """A class is callable. Guessing the other way would be silent."""
        class CallableList(list):
            def __call__(self):
                return "called"

        counter = Counter()
        wrapped = instrument(CallableList([1, 2, 3]), counter)
        _ = wrapped[0]
        self.assertEqual(counter.reads, 1)

    def test_a_value_with_no_subscript_is_refused_rather_than_measured_as_zero(self):
        """Handing it through untouched would report `no operations` — a confident
        answer to a question that was never asked."""
        with self.assertRaises(TypeError):
            instrument(42, Counter())


LADDER = dict(sizes=[16, 32, 64, 128], trials=8)


class TheVerdicts(unittest.TestCase):
    def test_three_different_answers_from_three_different_functions(self):
        """THE DIVERGENCE GATE, and it is the most important test here.

        A tool that always said `n^2` would pass a suite containing only insertion sort.
        A tool that always said `UNDETERMINED` would pass a suite containing only the
        refusals below, and would be useless. Three functions, three answers, one test —
        so neither degenerate tool can survive it.
        """
        quadratic = measure(insertion_sort, make_input=lambda n, r: r.ints(n, 10000),
                            **LADDER)
        logarithmic = measure(binary_search, sizes=[64, 128, 256, 512], trials=30,
                              make_input=lambda n, r: r.sample(n * 10, n))
        refused = measure(linear_scan, make_input=lambda n, r: r.ints(n, 1000), **LADDER)

        self.assertEqual(quadratic["per_channel"]["reads"]["verdict"], "n^2")
        self.assertEqual(logarithmic["per_channel"]["reads"]["verdict"], "log n")
        self.assertIs(refused["per_channel"]["reads"]["verdict"], UNDETERMINED)
        self.assertEqual(refused["per_channel"]["reads"]["regime"], "exact")

    def test_the_coefficient_is_the_count_over_the_class(self):
        """Insertion sort does about n^2 reads and half that many writes, by construction."""
        report = measure(insertion_sort, make_input=lambda n, r: r.ints(n, 10000), **LADDER)
        reads = report["per_channel"]["reads"]
        writes = report["per_channel"]["writes"]
        self.assertAlmostEqual(reads["coefficient"], 1.0, delta=0.15)
        self.assertAlmostEqual(writes["coefficient"], 0.5, delta=0.10)
        self.assertLess(writes["coefficient"], reads["coefficient"])

    def test_a_count_that_depends_only_on_n_is_refused_and_the_counts_are_printed(self):
        """The refusal `undetermined` cannot make for itself.

        Every rung of an exact count has a standard error of zero, and `ladder_for` drops
        such rungs — so an unguarded call reports "ladder shorter than the required run of
        3" about a ladder that was full. That message describes the ladder; the truth is
        about the function.
        """
        report = measure(linear_scan, make_input=lambda n, r: r.ints(n, 1000), **LADDER)
        reads = report["per_channel"]["reads"]
        self.assertIs(reads["verdict"], UNDETERMINED)
        self.assertEqual(reads["regime"], "exact")
        self.assertIn("depends only on the size", reads["why"])
        self.assertNotIn("ladder shorter", reads["why"])
        self.assertEqual(reads["mean_counts"], {16: 16, 32: 32, 64: 64, 128: 128})

    def test_a_declared_tolerance_opens_the_exact_case_and_says_that_it_did(self):
        """The control for the test above: the tolerance, not the function, is what changed."""
        report = measure(linear_scan, make_input=lambda n, r: r.ints(n, 1000),
                         tolerance=0.05, **LADDER)
        reads = report["per_channel"]["reads"]
        self.assertEqual(reads["verdict"], "n")
        self.assertAlmostEqual(reads["coefficient"], 1.0, delta=0.01)
        self.assertGreater(reads["declared_error_bars"], 0,
                           "the report must say the error bars were declared, not measured")

    def test_a_channel_nothing_touched_says_so_rather_than_fitting_a_class_to_zero(self):
        report = measure(linear_scan, make_input=lambda n, r: r.ints(n, 1000), **LADDER)
        writes = report["per_channel"]["writes"]
        self.assertIs(writes["verdict"], UNDETERMINED)
        self.assertEqual(writes["regime"], "unexercised")
        self.assertIn("never subscripts", writes["why"])

    def test_a_constant_that_is_still_moving_is_not_a_class(self):
        """Merge sort's read count carries a lower-order term, so the ratio drifts.

        With no tolerance declared there is nothing to compare that drift against, and
        the honest answer is that no candidate settles — not the nearest-looking one.
        """
        report = measure(merge_sort, make_input=lambda n, r: r.ints(n, 10 ** 6),
                         sizes=[16, 32, 64, 128, 256], trials=6)
        reads = report["per_channel"]["reads"]
        self.assertIs(reads["verdict"], UNDETERMINED)
        self.assertEqual(reads["regime"], "measured")
        self.assertIn("no candidate class settles", reads["why"])

    def test_two_classes_that_both_settle_are_reported_as_undetermined(self):
        """NOT A TIE TO BE BROKEN. Both settling means the ladder cannot tell them apart."""
        report = measure(binary_search, sizes=[64, 128, 256], trials=10,
                         tolerance=5.0,
                         make_input=lambda n, r: r.sample(n * 10, n))
        reads = report["per_channel"]["reads"]
        self.assertIs(reads["verdict"], UNDETERMINED)
        self.assertGreater(len(reads["settled"]), 1)
        self.assertIn("cannot tell them apart", reads["why"])

    def test_probe_is_what_makes_an_out_of_place_algorithm_measurable(self):
        """Without it the instrument sees only the input, and merge sort reads it once."""
        with_probe = measure(merge_sort, make_input=lambda n, r: r.ints(n, 10 ** 6),
                             sizes=[16, 32, 64, 128], trials=4)
        blind = measure(lambda data: merge_sort(data, lambda x: x),
                        make_input=lambda n, r: r.ints(n, 10 ** 6),
                        sizes=[16, 32, 64, 128], trials=4)
        self.assertEqual(blind["per_channel"]["reads"]["mean_counts"][128], 128)
        self.assertGreater(with_probe["per_channel"]["reads"]["mean_counts"][128], 128)

    def test_a_class_that_overflows_the_ladder_is_named_as_skipped(self):
        """`2^1024` is not a number a double can hold, and an `inf` in an average is not
        a measurement. The candidate is dropped and SAID to be dropped, so a reader can
        tell a class that lost from one that was never in the running."""
        report = measure(linear_scan, sizes=[128, 256, 512, 1024], trials=3,
                         tolerance=0.05, make_input=lambda n, r: r.ints(n, 1000))
        ladders = report["per_channel"]["reads"]["ladders"]
        self.assertIn("skipped", ladders["2^n"])
        self.assertNotIn("skipped", ladders["n"])

    def test_a_probed_comparator_gives_the_calls_channel_a_class_of_its_own(self):
        """An insertion sort compares about n^2/4 times, and that is the number people
        quote for a sort. Without the `calls` channel it was not measurable at all."""
        report = measure(comparison_sort, make_input=lambda n, r: r.ints(n, 10000),
                         **LADDER)
        calls = report["per_channel"]["calls"]
        self.assertEqual(calls["verdict"], "n^2")
        self.assertAlmostEqual(calls["coefficient"], 0.25, delta=0.06)
        self.assertLess(calls["coefficient"], report["per_channel"]["reads"]["coefficient"])

    def test_describe_says_what_decided_each_line(self):
        text = describe(measure(insertion_sort, make_input=lambda n, r: r.ints(n, 10000),
                                **LADDER))
        self.assertIn("n^2", text)
        self.assertIn("agree within", text)
        self.assertIn("mean counts", text)

    def test_the_reason_is_given_in_sizes_rather_than_in_the_ladder_truths(self):
        """`from size 128 up` is the fact a reader can act on; `truth=16777216` is the
        value of n^3 at 256 and tells nobody anything.

        It is also this package's own sentence rather than its dependency's, which is
        what stops `undetermined`'s two halves formatting a large integer differently
        from reaching this report. See `plateau_why`.
        """
        report = measure(insertion_sort, sizes=[64, 128, 256], trials=6,
                         make_input=lambda n, r: r.ints(n, 10000))
        why = report["per_channel"]["reads"]["why"]
        self.assertIn("from size", why)
        self.assertNotIn("truth=", why)

    def test_describe_collapses_the_channels_nothing_touched(self):
        """Three channels means a read-only function would otherwise spend two thirds of
        its report saying nothing happened."""
        text = describe(measure(linear_scan, make_input=lambda n, r: r.ints(n, 1000),
                                **LADDER))
        self.assertIn("writes, calls: unexercised", text)
        self.assertEqual(text.count("unexercised"), 1)

    def test_describe_can_name_every_candidate_and_why_it_did_not_settle(self):
        report = measure(merge_sort, make_input=lambda n, r: r.ints(n, 10 ** 6),
                         sizes=[16, 32, 64, 128, 256], trials=6)
        brief = describe(report)
        full = describe(report, candidates=True)
        self.assertNotIn("n log n   no run of", brief)
        for name in report["candidates"]:
            self.assertIn(name, full)
        self.assertGreater(len(full.splitlines()), len(brief.splitlines()))

    def test_two_classes_settling_says_how_much_wider_the_ladder_must_be(self):
        """`widen it` is advice nobody can act on without doing the arithmetic."""
        report = measure(binary_search, sizes=[64, 128, 256], trials=10,
                         tolerance=0.4, classes=["n", "n log n"],
                         make_input=lambda n, r: r.sample(n * 10, n))
        why = report["per_channel"]["reads"]["why"]
        self.assertIn("differs by only", why)
        self.assertIn("A top rung of 2048", why)

    def test_the_binding_pair_is_the_nearest_one_not_the_first_two(self):
        """With six candidates settling, `1` and `2^n` are trivially far apart and say
        nothing about whether the ladder is adequate."""
        from countfn.core import closest_pair
        # Over 16..128: `log n` grows 1.75x, `n log n` 14x, `n^2` 64x. The FIRST pair
        # differs by 8x and the second by 4.6x, so a version that reported the first pair
        # would name the one that is easier to separate and advise on the wrong ladder.
        self.assertEqual(closest_pair(["log n", "n log n", "n^2"], [16, 128])[:2],
                         ("n log n", "n^2"))
        self.assertEqual(closest_pair(["n", "n log n", "n^3"], [16, 128])[:2],
                         ("n", "n log n"))

    def test_both_halves_round_halves_the_same_way(self):
        """Python rounds half to even and JavaScript rounds half away from zero, so a
        mean of 1966.5 printed as 1966 in one report and 1967 in the other."""
        from countfn.core import half_up, one_dp
        self.assertEqual(half_up(1966.5), 1967)
        self.assertEqual(half_up(2.5), 3)
        self.assertEqual(one_dp(1.25), "1.3")
        self.assertEqual(one_dp(2.0), "2")


class ThePrecondition(unittest.TestCase):
    def test_a_function_that_is_not_reproducible_raises_rather_than_being_measured(self):
        """A mean over noise still has a standard error, still plateaus, and would be
        reported as an answer. So this is a raise, not a refusal."""
        state = {"n": 0}

        def drifting(data):
            state["n"] += 1
            for i in range(min(state["n"], len(data))):
                _ = data[i]

        with self.assertRaises(ValueError) as caught:
            measure(drifting, make_input=lambda n, r: r.ints(n, 10), **LADDER)
        self.assertIn("not reproducible", str(caught.exception))

    def test_the_control_a_stable_function_is_not_refused(self):
        """If everything raised, the test above would pass on a broken precondition."""
        report = measure(linear_scan, make_input=lambda n, r: r.ints(n, 10), **LADDER)
        self.assertEqual(report["per_channel"]["reads"]["mean_counts"][128], 128)


class TheArguments(unittest.TestCase):
    def test_a_ladder_too_short_to_show_a_plateau_is_refused(self):
        with self.assertRaises(ValueError):
            measure(linear_scan, sizes=[16, 32], trials=4,
                    make_input=lambda n, r: r.ints(n, 10))

    def test_sizes_must_be_increasing_and_distinct(self):
        for sizes in ([64, 16, 32], [16, 16, 32]):
            with self.subTest(sizes=sizes), self.assertRaises(ValueError):
                measure(linear_scan, sizes=sizes, trials=4,
                        make_input=lambda n, r: r.ints(n, 10))

    def test_one_trial_has_no_spread_to_measure(self):
        with self.assertRaises(ValueError):
            measure(linear_scan, sizes=[16, 32, 64], trials=1,
                    make_input=lambda n, r: r.ints(n, 10))

    def test_a_tolerance_of_zero_is_refused_rather_than_silently_admitting_nothing(self):
        with self.assertRaises(ValueError):
            measure(linear_scan, tolerance=0, **LADDER,
                    make_input=lambda n, r: r.ints(n, 10))

    def test_an_unknown_candidate_class_is_named(self):
        with self.assertRaises(ValueError) as caught:
            measure(linear_scan, classes=["n log log n"], **LADDER,
                    make_input=lambda n, r: r.ints(n, 10))
        self.assertIn("n log log n", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
