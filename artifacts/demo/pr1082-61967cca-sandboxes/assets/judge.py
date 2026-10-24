"""The judge box's Python: runs in the visitor's browser (Pyodide), and in tests under CPython.

Each packaging version from the bundle is written to its own directory and imported in turn, so
several versions of the same package live side by side as separate module objects. A visitor's input
goes through every version; differences from the base version are classified with Breakwater's own
harness/compare.py, so a divergence gets the same class signature the backtest reports.
"""

from __future__ import annotations

import importlib
import os
import sys

OBSERVE = ("str", "repr", "attr:release", "attr:public")  # what the backtest observed for this target
LOADED: dict[str, object] = {}  # version key -> packaging.version module


def load(versions: list[dict], root: str = "/tmp/judge") -> list[str]:
    """`versions`: [{"key": ..., "files": {"packaging/version.py": source, ...}}]."""
    for v in versions:
        base = os.path.join(root, v["key"])
        for name, src in v["files"].items():
            path = os.path.join(base, name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(src)
        for mod in [m for m in sys.modules if m == "packaging" or m.startswith("packaging.")]:
            del sys.modules[mod]
        sys.path.insert(0, base)
        try:
            LOADED[v["key"]] = importlib.import_module("packaging.version")
        finally:
            sys.path.remove(base)
    for mod in [m for m in sys.modules if m == "packaging" or m.startswith("packaging.")]:
        del sys.modules[mod]
    return list(LOADED)


def _jsonable(v):
    if isinstance(v, tuple):
        return [_jsonable(x) for x in v]
    if isinstance(v, int) and not isinstance(v, bool) and abs(v) > 10**18:
        return f"<int {len(str(abs(v)))} digits>"  # the worker summarises huge ints the same way
    return v


def outcome(module, text: str) -> dict:
    """The same shape the sandbox worker reports: {"status": "ok", "obs": {...}} or {"status": "exc", ...}."""
    try:
        v = module.Version(text)
    except Exception as e:  # noqa: BLE001 - the exception type is the observation
        t = type(e)
        return {"status": "exc", "exc": f"{t.__module__}.{t.__qualname__}", "message": str(e)[:300]}
    obs = {}
    for spec in OBSERVE:
        try:
            value = str(v) if spec == "str" else repr(v) if spec == "repr" else getattr(v, spec[5:])
            obs[spec] = _jsonable(value)
        except Exception as e:  # noqa: BLE001
            obs[spec] = f"<exc:{type(e).__module__}.{type(e).__qualname__}>"
    return {"status": "ok", "obs": obs}


def run(text: str) -> dict:
    """Every version's outcome, and each non-base version's divergences from base."""
    from compare import compare_outcomes, signature

    keys = list(LOADED)
    outs = {k: outcome(LOADED[k], text) for k in keys}
    base = outs[keys[0]]
    diffs = {}
    for k in keys[1:]:
        strip = {kk: vv for kk, vv in outs[k].items() if kk != "message"}
        b = {kk: vv for kk, vv in base.items() if kk != "message"}
        found = compare_outcomes(b, strip, OBSERVE)
        diffs[k] = [{"probe": p, "detail": d, "signature": signature(p, d, bv, hv, [text])} for p, d, bv, hv in found]
    return {"outcomes": outs, "diffs": diffs}
