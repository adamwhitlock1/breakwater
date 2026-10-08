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


def signature(probe: str, detail: str, base, head) -> str:
    """Dedup key: same probe, detail and outcome shapes are one finding class."""
    if probe == "P1":  # the differing values themselves vary per input
        return f"P1|{detail}|differs"
    return f"{probe}|{detail}|{shape(base)}|{shape(head)}"


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
