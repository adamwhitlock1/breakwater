"""In-sandbox worker. Runs under ONE side's interpreter (base or head) and reports observations.

Stdlib only: it is copied into target images and must not import breakwater. The orchestrator
sends a JSON request on stdin and reads a JSON response from stdout; it never executes target
code itself. Each input gets a per-call timeout so a pathological input cannot hang the batch.

Request:  {"target": "pkg.mod:Callable", "observe": ["str", "repr", "len", "attr:release"],
           "ops": [{"op": "construct" | "relations" | "pickle_dump", "inputs": [[arg, ...], ...],
                    "warm": bool}, {"op": "pickle_load", "blobs": [...], "inputs": [...]}],
           "timeout_s": 5}
Response: {"results": [<per-op result>], "python": "3.12.x"}
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
    kind, val = _guard(lambda: target(*args), timeout_s)
    if kind == "ok":
        return val, {"status": "ok", "obs": _observe(val, observe, timeout_s)}
    return None, {"status": kind, "exc": val}


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


def run(req):
    signal.signal(signal.SIGALRM, _on_alarm)
    mod_name, _, attr = req["target"].partition(":")
    target = importlib.import_module(mod_name)
    for part in attr.split("."):
        target = getattr(target, part)
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
    req = json.loads(sys.stdin.read())
    json.dump(run(req), sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
