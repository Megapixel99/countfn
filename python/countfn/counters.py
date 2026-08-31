"""The instrument: a sequence that counts what is done to it.

WHY COUNTS AND NOT A CLOCK. Every empirical complexity tool on either registry measures
elapsed time — `big-O` on PyPI ("empirical estimation of time complexity from execution
time"), `big-o-calculator` on npm ("measuring each test case run time"). A timing is a
mean over noise that reads the clock, and `undetermined` — the package this one is built
on — REFUSES such an observable outright, because a mean over noise still has a standard
error, still forms a ladder, and can still plateau. A broken adapter of that shape does
not produce a wrong-looking answer; it produces a confident one.

An operation count has none of that. For a given input it is the same number on a
loaded laptop and an idle server, in a container and on metal, this year and next.

WHAT IS COUNTED, AND WHY IT IS ONLY THESE THREE. `reads` and `writes` are element access
through the subscript operator: `__getitem__`/`__setitem__` here, a `Proxy` `get`/`set`
trap on an integer key in JavaScript. `calls` is an invocation of a callable the caller
handed to `probe`. All three mean the same thing in both halves, which is the bar a
channel has to clear -- a channel whose two halves count different events is a channel
whose number means two things.

COMPARISONS ARE NOT A CHANNEL, and that is why `calls` exists. Counting `a < b` directly
would mean intercepting rich comparisons here and coercions in JavaScript, where `a < b`
calls `Symbol.toPrimitive` on BOTH operands and a comparison costs two events. Dividing by
two is a guess about how the operands were spelled. So the caller wraps the comparator
instead -- `probe(cmp)` -- and both halves count one call per call.

Reads carry the shape on their own for anything in-place: a linear scan is n, a binary
search is log n, a bubble sort is n squared, a merge sort is n log n.

ITERATION IS COUNTED AS ONE READ PER ELEMENT, deliberately and in both halves. Python's
fallback iteration protocol would call `__getitem__` until it raised, giving n+1; the
JavaScript array iterator reads n. `__iter__` is defined here to make it n in both, so
the two halves have a chance of producing the same number for the same algorithm --
which `python/tests/test_parity.py` checks on two functions whose count is fixed by their
loop structure rather than assuming it.
"""

from __future__ import annotations


class Counter:
    """Three integers, and nothing that can go wrong."""

    __slots__ = ("reads", "writes", "calls")

    def __init__(self):
        self.reads = 0
        self.writes = 0
        self.calls = 0

    def snapshot(self):
        return {"reads": self.reads, "writes": self.writes, "calls": self.calls}


CHANNELS = ("reads", "writes", "calls")


class CountedSequence:
    """A list that reports every subscript. Not a `list` subclass, on purpose.

    Subclassing `list` would leave every C-level path -- `sorted()`, slicing, `in`,
    `len()`-driven loops in the standard library -- reading the underlying storage
    without going through `__getitem__`, and the counts would silently be a fraction of
    the truth. A tool whose instrument under-reports by an unknown factor is worse than
    no tool, because the SHAPE still looks plausible.
    """

    __slots__ = ("_data", "_counter")

    def __init__(self, data, counter):
        self._data = list(data)
        self._counter = counter

    def __len__(self):
        return len(self._data)

    def __getitem__(self, index):
        if isinstance(index, slice):
            # A slice reads every element it takes. Counting it as one would let a
            # quadratic algorithm written with slices look linear.
            #
            # It returns a PLAIN list, not a counted one, and that matches JavaScript --
            # where `proxy.slice(a, b)` reads through the traps and hands back an ordinary
            # array. Returning a counted slice here would make the two halves count
            # different things for the same algorithm, which is the one thing a shared
            # generator and a shared iteration rule were adopted to prevent. Use `probe`
            # if you want the result counted.
            chunk = self._data[index]
            self._counter.reads += len(chunk)
            return chunk
        self._counter.reads += 1
        return self._data[index]

    def __setitem__(self, index, value):
        if isinstance(index, slice):
            values = list(value)
            self._counter.writes += len(values)
            self._data[index] = values
            return
        self._counter.writes += 1
        self._data[index] = value

    def __iter__(self):
        for i in range(len(self._data)):
            self._counter.reads += 1
            yield self._data[i]

    def append(self, value):
        """One write, matching what `arr.push(x)` costs the JavaScript half.

        There is a growing output in almost every out-of-place algorithm, and without
        this the only way to fill one was to reach past the wrapper -- which counts
        nothing and looks like it counts something.
        """
        self._counter.writes += 1
        self._data.append(value)

    def extend(self, values):
        for value in values:
            self.append(value)

    def __contains__(self, value):
        # `in` is a linear scan and is counted as one, rather than falling through to
        # `__iter__` and counting the same reads by a different route.
        for i in range(len(self._data)):
            self._counter.reads += 1
            if self._data[i] == value:
                return True
        return False

    def __repr__(self):
        return f"CountedSequence({self._data!r})"

    def unwrap(self):
        return list(self._data)


class CountedMapping:
    """A dict that reports every lookup and every store."""

    __slots__ = ("_data", "_counter")

    def __init__(self, data, counter):
        self._data = dict(data)
        self._counter = counter

    def __len__(self):
        return len(self._data)

    def __getitem__(self, key):
        self._counter.reads += 1
        return self._data[key]

    def __setitem__(self, key, value):
        self._counter.writes += 1
        self._data[key] = value

    def __contains__(self, key):
        self._counter.reads += 1
        return key in self._data

    def get(self, key, default=None):
        self._counter.reads += 1
        return self._data.get(key, default)

    def __iter__(self):
        for key in list(self._data):
            self._counter.reads += 1
            yield key

    def keys(self):
        return list(self._data.keys())

    def __repr__(self):
        return f"CountedMapping({self._data!r})"

    def unwrap(self):
        return dict(self._data)


class CountedCallable:
    """A callable that reports every invocation.

    The answer to "how many comparisons did that sort do?" -- wrap the comparator and
    read `calls`. One call is one call in both halves, which is exactly what counting
    `a < b` directly could not promise.
    """

    __slots__ = ("_fn", "_counter", "__dict__")

    def __init__(self, fn, counter):
        self._fn = fn
        self._counter = counter
        self.__name__ = getattr(fn, "__name__", "callable")

    def __call__(self, *args, **kwargs):
        self._counter.calls += 1
        return self._fn(*args, **kwargs)

    def __repr__(self):
        return f"CountedCallable({self._fn!r})"

    def unwrap(self):
        return self._fn


def instrument(value, counter):
    """Wrap what can be counted; refuse what cannot.

    REFUSING IS THE POINT. A value this cannot instrument would be handed to the
    function untouched, every count would be zero, and the report would say the
    function performs no operations -- which is a confident answer to a question that
    was never asked.
    """
    if isinstance(value, (CountedSequence, CountedMapping, CountedCallable)):
        return value
    if isinstance(value, (list, tuple)):
        return CountedSequence(value, counter)
    if isinstance(value, dict):
        return CountedMapping(value, counter)
    # CALLABLE IS CHECKED AFTER THE CONTAINERS, not before. A class is callable and a
    # dict subclass with `__call__` is both; the container reading is the one a caller
    # who passed a container meant, and guessing the other way is silent.
    if callable(value):
        return CountedCallable(value, counter)
    raise TypeError(
        f"make_input returned a {type(value).__name__}, which has nothing to count. "
        f"Return a list, tuple, dict or callable -- or wrap the part that is indexed "
        f"and close over the rest, e.g. `lambda n, rng: rng.sample(n * 10, n)` "
        f"with `fn = lambda data: search(data, target)`"
    )
