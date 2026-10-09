"""How a divergence is shown to people. Shared by the static report (site/build.py) and the live
audit feed (events.py), so a counterexample reads the same in both. Standard library only."""

from __future__ import annotations

import json
from typing import Any

PROBE_TEXT = {"P1": "Output changed", "P2": "Exception behaviour changed", "P3": "Equality / ordering changed",
              "P4": "Old pickles break", "P4down": "New pickles break on old version"}
RELATION_TEXT = {"eq": "a == b", "lt": "a < b", "gt": "a > b", "hash_eq": "hash(a) == hash(b)"}


def short(s: str, limit: int = 64) -> str:
    """Long adversarial strings (4,300-digit versions) stay readable: head…tail."""
    if len(s) <= limit:
        return s
    return f"{s[:limit - 22]}…{s[-10:]}"


def show_args(args: list[Any], fn: str) -> str:
    """`Version("1. 0")`, with JSON escapes for control characters and long strings shortened."""
    parts = []
    for a in args:
        if isinstance(a, str):
            note = f" ({len(a):,} chars)" if len(a) > 64 else ""
            parts.append(json.dumps(short(a), ensure_ascii=False) + note)
        else:
            parts.append(short(json.dumps(a, ensure_ascii=False)))
    return f"{fn}({', '.join(parts)})"


def exc_name(qualified: str) -> str:
    """`packaging.version.InvalidVersion` -> `InvalidVersion`; pages show the full name on hover."""
    return qualified.rsplit(".", 1)[-1]


def full_exc(v: Any) -> str:
    if isinstance(v, dict) and v.get("status") == "exc":
        return v.get("exc", "")
    if isinstance(v, str) and v.startswith("<exc:"):
        return v[5:-1]
    return ""


def show_outcome(v: Any) -> str:
    if isinstance(v, dict):
        if v.get("status") == "ok":
            return "returns normally"
        if v.get("status") == "exc":
            return f"raises {exc_name(v.get('exc', ''))}"
        if v.get("status") == "timeout":
            return "times out"
    if isinstance(v, str) and v.startswith("<exc:"):
        return f"raises {exc_name(v[5:-1])}"
    if isinstance(v, str):
        return json.dumps(short(v), ensure_ascii=False)
    return short(json.dumps(v, ensure_ascii=False))


def card_text(probe: str, detail: str, args: list[Any], base: Any, head: Any, fn: str) -> dict[str, Any]:
    """Title, labelled inputs and the base/head lines for one finding class."""
    if probe == "P3" and len(args) == 2:
        rel = RELATION_TEXT.get(detail, detail)
        inputs = [("a", show_args(args[0], fn)), ("b", show_args(args[1], fn))]
        base_s, head_s = f"{rel} → {base}", f"{rel} → {head}"
    else:
        inputs = [("input", show_args(args[0], fn))]
        if probe in ("P4", "P4down"):
            base_s = "pickled object loads and compares equal" if probe == "P4" else show_outcome(base)
            head_s = f"load: {show_outcome(head)}" if detail.endswith("load") else \
                f"compare with fresh object: {show_outcome(head)}"
        else:
            base_s, head_s = show_outcome(base), show_outcome(head)
            if probe == "P1":
                base_s, head_s = f"{detail}: {base_s}", f"{detail}: {head_s}"
    return {"title": PROBE_TEXT.get(probe, probe), "inputs": inputs, "base": base_s, "head": head_s,
            "base_exc": full_exc(base), "head_exc": full_exc(head)}


def sources(found_by: list[str]) -> list[str]:
    """Collapse per-strategy credits into the kinds of search that found a class."""
    kinds = []
    for name, test in (("Nemotron strategy search", lambda s: s.startswith("A") and "/s" in s),
                       ("Ultra's planned example", lambda s: s == "seed"),
                       ("project's test strings", lambda s: s == "tests"),
                       ("hostile mutation", lambda s: s.startswith("mutation:")),
                       ("relations pass", lambda s: s == "focus"),
                       ("search sample", lambda s: s == "batch")):
        if any(test(s) for s in found_by):
            kinds.append(name)
    return kinds
