/**
 * The instrument: a sequence that counts what is done to it.
 *
 * WHY COUNTS AND NOT A CLOCK. Every empirical complexity tool on either registry measures
 * elapsed time — `big-O` on PyPI ("empirical estimation of time complexity from execution
 * time"), `big-o-calculator` on npm ("measuring each test case run time"). A timing is a
 * mean over noise that reads the clock, and `undetermined` — the package this one is
 * built on — REFUSES such an observable outright, because a mean over noise still has a
 * standard error, still forms a ladder, and can still plateau. A broken adapter of that
 * shape does not produce a wrong-looking answer; it produces a confident one.
 *
 * WHAT IS COUNTED, AND WHY IT IS ONLY THESE THREE. `reads` and `writes` are element
 * access through the subscript operator: a `Proxy` `get`/`set` trap on an INTEGER key
 * here, `__getitem__`/`__setitem__` in Python. `calls` is an invocation of a callable the
 * caller handed to `probe`. All three mean the same thing in both halves, which is the bar
 * a channel has to clear.
 *
 * COMPARISONS ARE NOT A CHANNEL, and that is why `calls` exists. `a < b` on two objects
 * calls `Symbol.toPrimitive` on BOTH operands, so a comparison costs two events here and
 * one in Python, and dividing by two is a guess about how the operands were spelled. The
 * caller wraps the comparator instead — `probe(cmp)` — and both halves count one call per
 * call.
 *
 * `length` is deliberately not counted, in either half. It is O(1) in both languages and
 * counting it would make every loop header show up as work.
 */

/** Three integers, and nothing that can go wrong. */
export class Counter {
  constructor() {
    this.reads = 0;
    this.writes = 0;
    this.calls = 0;
  }

  snapshot() {
    return { reads: this.reads, writes: this.writes, calls: this.calls };
  }
}

export const CHANNELS = ["reads", "writes", "calls"];

const isIndex = (prop) =>
  typeof prop === "string" && /^(0|[1-9][0-9]*)$/.test(prop);

/**
 * An array whose integer subscripts are counted.
 *
 * `for (const x of proxied)` reads `length` once and then each index, which is n reads.
 * The Python half defines `__iter__` to make it n there too, rather than letting the
 * fallback protocol call `__getitem__` until it raises and count n+1.
 *
 * `push` reaches the `set` trap for the new index and again for `length`; only the index
 * is counted, so a push costs one write in both halves.
 */
export function countedArray(data, counter) {
  const target = Array.isArray(data) ? [...data] : Array.from(data);
  return new Proxy(target, {
    get(obj, prop, receiver) {
      if (isIndex(prop)) counter.reads += 1;
      return Reflect.get(obj, prop, receiver);
    },
    set(obj, prop, value, receiver) {
      if (isIndex(prop)) counter.writes += 1;
      return Reflect.set(obj, prop, value, receiver);
    },
  });
}

/** A plain object or Map whose keyed access is counted. */
export function countedMapping(data, counter) {
  if (data instanceof Map) {
    const inner = new Map(data);
    return {
      get size() {
        return inner.size;
      },
      get(key) {
        counter.reads += 1;
        return inner.get(key);
      },
      set(key, value) {
        counter.writes += 1;
        inner.set(key, value);
        return this;
      },
      has(key) {
        counter.reads += 1;
        return inner.has(key);
      },
      keys: () => inner.keys(),
      unwrap: () => new Map(inner),
    };
  }
  const target = { ...data };
  return new Proxy(target, {
    get(obj, prop, receiver) {
      if (typeof prop === "string") counter.reads += 1;
      return Reflect.get(obj, prop, receiver);
    },
    set(obj, prop, value, receiver) {
      if (typeof prop === "string") counter.writes += 1;
      return Reflect.set(obj, prop, value, receiver);
    },
    has(obj, prop) {
      counter.reads += 1;
      return Reflect.has(obj, prop);
    },
  });
}

/**
 * A callable that reports every invocation.
 *
 * The answer to "how many comparisons did that sort do?" — wrap the comparator and read
 * `calls`. A `Proxy` with an `apply` trap rather than a closure, so the result is still a
 * function: `fn.length` survives, and so does anything that reflects on it.
 */
export function countedCallable(fn, counter) {
  return new Proxy(fn, {
    apply(target, thisArg, args) {
      counter.calls += 1;
      return Reflect.apply(target, thisArg, args);
    },
  });
}

/**
 * Wrap what can be counted; refuse what cannot.
 *
 * REFUSING IS THE POINT. A value this cannot instrument would be handed to the function
 * untouched, every count would be zero, and the report would say the function performs no
 * operations — which is a confident answer to a question that was never asked.
 */
export function instrument(value, counter) {
  if (Array.isArray(value)) return countedArray(value, counter);
  if (value instanceof Map) return countedMapping(value, counter);
  if (value !== null && typeof value === "object" && !ArrayBuffer.isView(value)) {
    return countedMapping(value, counter);
  }
  // CALLABLE IS CHECKED AFTER THE CONTAINERS, not before. A class is a function here as
  // well, and the container reading is the one a caller who passed a container meant.
  if (typeof value === "function") return countedCallable(value, counter);
  throw new TypeError(
    `makeInput returned a ${value === null ? "null" : typeof value}, which has nothing ` +
      `to count. Return an array, a Map, a plain object or a callable — or wrap the ` +
      `part that is indexed and close over the rest, e.g. ` +
      `\`(n, rng) => rng.sample(n * 10, n)\` with \`fn = (data) => search(data, target)\``
  );
}
