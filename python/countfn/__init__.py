r"""countfn — how does this function's cost scale? Counted, not timed.

    from countfn import measure, describe
    print(describe(measure(fn, sizes=[64, 128, 256, 512, 1024, 2048],
                           make_input=lambda n, rng: rng.sample(n * 10, n))))

Built on `undetermined`: the ladder, the standard errors, the three-rung plateau and the
refusal are its machinery, imported rather than copied. What is here is an instrument that
counts operations instead of reading a clock — because a timing is a mean over noise, and
`undetermined` refuses such an observable outright.
"""

from undetermined.core import UNDETERMINED

from . import classes, counters
from .classes import NAMES as CLASS_NAMES
from .core import EXACT, MEASURED, UNEXERCISED, describe, measure
from .counters import (CHANNELS, CountedCallable, CountedMapping, CountedSequence,
                       Counter)
from .rng import Rng

__all__ = ["measure", "describe", "UNDETERMINED", "CHANNELS", "CLASS_NAMES",
           "Counter", "CountedSequence", "CountedMapping", "CountedCallable", "Rng",
           "classes", "counters", "rng",
           "EXACT", "MEASURED", "UNEXERCISED"]
__version__ = "0.1.2"
