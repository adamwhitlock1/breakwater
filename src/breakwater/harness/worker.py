"""In-sandbox worker. Runs under ONE side's interpreter (base or head) and reports observations.

Stdlib only: it is copied into target images and must not import breakwater. The orchestrator
sends a JSON request on stdin and reads a JSON response from stdout; it never executes target
code itself. Each input gets a per-call timeout so a pathological input cannot hang the batch.

Request:  {"target": "pkg.mod:Callable", "observe": ["str", "repr", "len", "attr:release"],
           "ops": [{"op": "construct" | "relations" | "pickle_dump", "inputs": [[arg, ...], ...],
                    "warm": bool}, {"op": "pickle_load", "blobs": [...], "inputs": [...]},
                   {"op": "time", "inputs": [...]}, {"op": "loop", "inputs": [...], "reps": R}],
           "timeout_s": 5}

`time` reports calibrated CPU ns per call (for the perf search). `loop` just calls the target
reps x len(inputs) times and reports nothing, so cachegrind can count instructions for that work.
Response: {"results": [<per-op result>], "python": "3.12.x"}

`--serve` reads one request per line and answers one line each, for the Hypothesis search.
"""

from __future__ import annotations

import base64
import importlib
import itertools
import json
import pickle
import re
import signal
import sys
import time

# Default reprs embed memory addresses, which differ between processes and are not behavior.
_ADDR = re.compile(r" at 0x[0-9a-fA-F]+")


def _norm_repr(v) -> str:
    return _ADDR.sub(" at 0x?", repr(v))


class _Timeout(Exception):
    pass


def _on_alarm(signum, frame):
    raise _Timeout()


def _exc_name(e: BaseException) -> str:
    t = type(e)
    return f"{t.__module__}.{t.__qualname__}"


def _jsonable(v):
    if v is None or isinstance(v, (bool, int, float, str)):
        if isinstance(v, int) and not isinstance(v, bool) and abs(v) > 10**18:
            return f"<int {len(str(abs(v)))} digits>"
        return v
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    if isinstance(v, (set, frozenset)):  # iteration order is not behavior
        return sorted((_jsonable(x) for x in v), key=lambda x: json.dumps(x, sort_keys=True, default=str))
    if isinstance(v, dict):
        return {str(k): _jsonable(x) for k, x in sorted(v.items(), key=lambda kv: str(kv[0]))}
    return _norm_repr(v)


def _guard(fn, timeout_s):
    """Run fn() with an alarm. Returns ("ok", value) | ("exc", name) | ("timeout", None)."""
    signal.setitimer(signal.ITIMER_REAL, timeout_s)
    try:
        return "ok", fn()
    except _Timeout:
        return "timeout", None
    except BaseException as e:  # noqa: BLE001 - every exception type is an observation
        if isinstance(e, (KeyboardInterrupt, SystemExit)):
            raise
        return "exc", _exc_name(e)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)


def _observe(obj, observe, timeout_s):
    out = {}
    for spec in observe:
        if spec == "str":
            fn = lambda: str(obj)  # noqa: E731
        elif spec == "repr":
            fn = lambda: _norm_repr(obj)  # noqa: E731
        elif spec == "value":  # structural, order-independent for sets; best for function results
            fn = lambda: _jsonable(obj)  # noqa: E731
        elif spec == "len":
            fn = lambda: len(obj)  # noqa: E731
        elif spec.startswith("attr:"):
            name = spec[5:]
            fn = lambda name=name: getattr(obj, name)  # noqa: E731
        else:
            raise ValueError(f"unknown observation {spec!r}")
        kind, val = _guard(fn, timeout_s)
        out[spec] = _jsonable(val) if kind == "ok" else f"<{kind}{':' + val if val else ''}>"
    return out


def _construct(target, args, observe, timeout_s):
    t0 = time.process_time_ns()
    kind, val = _guard(lambda: target(*args), timeout_s)
    t_ns = time.process_time_ns() - t0  # CPU time of the call itself; a cheap signal for perf search
    if kind == "ok":
        return val, {"status": "ok", "obs": _observe(val, observe, timeout_s), "t_ns": t_ns}
    return None, {"status": kind, "exc": val, "t_ns": t_ns}


TIME_MIN_NS = 2_000_000  # measure at least 2 ms of calls per round
TIME_MAX_REPS = 20_000
TIME_ROUNDS = 3


def _time_call(target, args, timeout_s):
    """Min-of-rounds CPU ns per call, with reps calibrated so each round lasts >= TIME_MIN_NS."""
    kind, val = _guard(lambda: target(*args), timeout_s)
    status = {"status": kind} if kind == "ok" else {"status": kind, "exc": val}
    if kind == "timeout":
        return dict(status, ns=None, reps=0)

    def once():
        try:
            target(*args)
        except Exception:  # noqa: BLE001 - failing calls still cost time; same on both sides
            pass

    once()  # warm-up: first calls pay for lazy imports, regex compilation and cache fills
    once()
    reps = 1
    while True:  # calibrate: double reps until one round lasts at least TIME_MIN_NS
        t0 = time.process_time_ns()
        for _ in range(reps):
            once()
        if time.process_time_ns() - t0 >= TIME_MIN_NS or reps >= TIME_MAX_REPS:
            break
        reps *= 2
    best = None
    for _ in range(TIME_ROUNDS):
        t0 = time.process_time_ns()
        for _ in range(reps):
            once()
        per = (time.process_time_ns() - t0) / reps
        best = per if best is None else min(best, per)
    return dict(status, ns=best, reps=reps)


def _loop(target, inputs, reps):
    for _ in range(reps):
        for args in inputs:
            try:
                target(*args)
            except Exception:  # noqa: BLE001
                pass


def _warm(obj):
    """Exercise lazy state (caches populated by comparison/hashing) before pickling."""
    for fn in (lambda: obj == obj, lambda: hash(obj), lambda: obj < obj):
        try:
            fn()
        except Exception:  # noqa: BLE001
            pass


def _relations(objs, timeout_s):
    rel = {}
    for i, j in itertools.combinations(range(len(objs)), 2):
        a, b = objs[i], objs[j]
        if a is None or b is None:
            continue
        r = {}
        for name, fn in (("eq", lambda a=a, b=b: a == b), ("lt", lambda a=a, b=b: a < b),
                         ("gt", lambda a=a, b=b: a > b), ("hash_eq", lambda a=a, b=b: hash(a) == hash(b))):
            kind, val = _guard(fn, timeout_s)
            r[name] = val if kind == "ok" else f"<{kind}{':' + val if val else ''}>"
        rel[f"{i},{j}"] = r
    return rel


def resolve(spec):
    """"pkg.mod:Callable" calls Callable(*args). "pkg.mod:Class#method" builds Class(args[0]) and
    calls .method(*args[1:]); iterator results are listed so they can be observed and compared."""
    mod_name, _, attr = spec.partition(":")
    attr, _, method = attr.partition("#")
    obj = importlib.import_module(mod_name)
    for part in attr.split("."):
        obj = getattr(obj, part)
    if not method:
        return obj
    cls = obj

    def call(first, *rest):
        result = getattr(cls(first), method)(*rest)
        if hasattr(result, "__next__") and not isinstance(result, (str, bytes)):
            result = list(result)
        return result

    return call


def run(req):
    signal.signal(signal.SIGALRM, _on_alarm)
    target = resolve(req["target"])
    observe = req.get("observe", ["str", "repr"])
    timeout_s = float(req.get("timeout_s", 5))
    results = []
    for op in req["ops"]:
        kind = op["op"]
        if kind in ("construct", "relations", "pickle_dump"):
            built = [_construct(target, args, observe, timeout_s) for args in op["inputs"]]
            objs = [o for o, _ in built]
            res = {"outcomes": [r for _, r in built]}
            if kind == "relations":
                res["relations"] = _relations(objs, timeout_s)
            if kind == "pickle_dump":
                blobs = []
                for o in objs:
                    if o is None:
                        blobs.append(None)
                        continue
                    if op.get("warm"):
                        _warm(o)
                    k, v = _guard(lambda o=o: base64.b64encode(pickle.dumps(o)).decode(), timeout_s)
                    blobs.append(v if k == "ok" else None)
                res["blobs"] = blobs
            results.append(res)
        elif kind == "time":
            results.append({"timings": [_time_call(target, args, timeout_s) for args in op["inputs"]]})
        elif kind == "loop":
            _loop(target, op["inputs"], int(op["reps"]))
            results.append({"done": True})
        elif kind == "pickle_load":
            loads = []
            for blob, args in zip(op["blobs"], op["inputs"], strict=True):
                if blob is None:
                    loads.append({"status": "skipped"})
                    continue
                k, obj = _guard(lambda blob=blob: pickle.loads(base64.b64decode(blob)), timeout_s)
                if k != "ok":
                    loads.append({"status": k, "exc": obj})
                    continue
                fresh, _ = _construct(target, args, observe, timeout_s)
                entry = {"status": "ok", "obs": _observe(obj, observe, timeout_s)}
                if fresh is not None:
                    kk, eq = _guard(lambda obj=obj, fresh=fresh: obj == fresh, timeout_s)
                    entry["eq_fresh"] = eq if kk == "ok" else f"<{kk}{':' + eq if eq else ''}>"
                    kk, lt = _guard(lambda obj=obj, fresh=fresh: obj < fresh or obj > fresh, timeout_s)
                    entry["cmp_fresh"] = lt if kk == "ok" else f"<{kk}{':' + lt if lt else ''}>"
                loads.append(entry)
            results.append({"loads": loads})
        else:
            raise ValueError(f"unknown op {kind!r}")
    return {"results": results, "python": sys.version.split()[0]}


def main():
    if "--serve" in sys.argv:
        # One JSON request per line, one JSON response per line. Used by diffrun.py so Hypothesis can
        # query both sides per example without paying interpreter start-up each time.
        for line in sys.stdin:
            try:
                resp = run(json.loads(line))
            except Exception as e:  # noqa: BLE001
                resp = {"error": f"{_exc_name(e)}: {e}"}
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()
        return
    req = json.loads(sys.stdin.read())
    json.dump(run(req), sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
