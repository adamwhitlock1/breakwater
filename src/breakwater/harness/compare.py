"""Outcome comparison shared by the orchestrator (probes.py) and the in-sandbox search (diffrun.py).

Stdlib only, because it is copied into target images. Keeping one implementation means a finding
the Hypothesis search shrinks inside the sandbox has the same signature the probes report outside.
"""

from __future__ import annotations


def shape(outcome) -> str:
    if isinstance(outcome, dict):
        if outcome.get("status") in ("exc", "timeout"):
            return f"{outcome['status']}:{outcome.get('exc')}"
        if outcome.get("status") == "ok":
            return "ok"
    return type(outcome).__name__ if not isinstance(outcome, (str, bool, int)) else str(outcome)


def traits(args) -> str:
    """Generic input traits that tend to separate distinct root causes with the same outcome shape
    (e.g. "accepts non-ASCII digits" vs "accepts inner whitespace"). Library-agnostic on purpose."""
    tags = set()
    for a in args if isinstance(args, list) else [args]:
        if isinstance(a, list):
            tags.add("nested")
            continue
        if not isinstance(a, str):
            tags.add(type(a).__name__)
            continue
        if a == "":
            tags.add("empty")
        if any(ord(c) > 127 for c in a):
            tags.add("non-ascii")
        if any(c.isspace() for c in a):
            tags.add("whitespace")
        if any(ord(c) < 32 and not c.isspace() for c in a):
            tags.add("control")
        run = longest = 0
        for c in a:
            run = run + 1 if c.isdigit() else 0
            longest = max(longest, run)
        if longest > 1000:
            tags.add("long-digits")
    return "+".join(sorted(tags)) or "plain"


def signature(probe: str, detail: str, base, head, args=None) -> str:
    """Dedup key: same probe, detail, outcome shapes and input traits are one finding class."""
    # Traits separate root causes for input-driven findings (P1/P2). Relation and pickle findings
    # (P3/P4) share one cause regardless of the input's characters, so no suffix there.
    suffix = f"|{traits(args)}" if args is not None and probe in ("P1", "P2") else ""
    if probe == "P1":  # the differing values themselves vary per input
        return f"P1|{detail}|differs{suffix}"
    return f"{probe}|{detail}|{shape(base)}|{shape(head)}{suffix}"


def compare_outcomes(base: dict, head: dict, observe, probes=("P1", "P2")) -> list[tuple[str, str, object, object]]:
    """P1/P2 for one input. Returns (probe, detail, base_value, head_value) tuples."""
    out = []
    if base["status"] == "ok" and head["status"] == "ok":
        if "P1" in probes:
            for key in observe:
                if base["obs"].get(key) != head["obs"].get(key):
                    out.append(("P1", key, base["obs"].get(key), head["obs"].get(key)))
    elif "P2" in probes and (base["status"], base.get("exc")) != (head["status"], head.get("exc")):
        out.append(("P2", "outcome", strip_timing(base), strip_timing(head)))
    return out


def strip_timing(outcome: dict) -> dict:
    return {k: v for k, v in outcome.items() if k != "t_ns"}
