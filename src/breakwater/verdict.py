"""The verdict on a change: BLOCK, REVIEW or PASS, the stricter of behaviour and performance.

  behaviour    BLOCK on any class adjudicated likely-bug; REVIEW if a class is needs-human or was never
               labelled; PASS otherwise (including classes adjudicated intended)
  performance  BLOCK on a complexity regression in a family of mostly valid inputs; REVIEW on a valid
               family at least SLOWER_REVIEW times slower; PASS otherwise

Used by the audit (report.json, exit code, PR comment) and the site, so they always agree.
"""

from __future__ import annotations

from collections.abc import Iterable

SLOWER_REVIEW = 1.25
RANK = {"PASS": 0, "REVIEW": 1, "BLOCK": 2}


def behaviour(labels: Iterable[str | None]) -> str:
    labels = list(labels)
    if "likely-bug" in labels:
        return "BLOCK"
    if "needs-human" in labels or None in labels:
        return "REVIEW"
    return "PASS"


def performance(summary: dict | None) -> tuple[str, str]:
    """(verdict, reason) from a perf summary (perf.summarize)."""
    p = summary or {}
    worst = p.get("worst_valid_ratio")
    if not worst:
        return "PASS", ""
    fam = next((f for f in (p.get("report") or {}).get("findings", []) if f.get("family") == p.get("worst_family")), {})
    if fam.get("verdict") == "complexity-regression":
        return "BLOCK", (f"The “faster” code does up to {worst:.0f}× the work on valid inputs, growing with "
                         "input size (complexity regression).")
    if worst >= SLOWER_REVIEW:
        return "REVIEW", f"A valid input family runs {worst:.2f}× the instructions of the old code."
    return "PASS", ""


def combine(*verdicts: str) -> str:
    return max(verdicts, key=RANK.__getitem__, default="PASS")


def of_report(report: dict) -> dict:
    """Verdict for an audit report (report.json): {"verdict", "behaviour", "performance", "reasons"}."""
    from breakwater.perf import summarize

    labels = {v["signature"]: v["label"] for v in (report.get("adjudication") or {}).get("verdicts", [])}
    findings = (report.get("semantic") or {}).get("findings", [])
    b = behaviour(labels.get(f["signature"]) for f in findings)
    p, reason = performance(summarize(report["perf"])) if report.get("perf") else ("PASS", "")
    counts = {k: sum(labels.get(f["signature"]) == k for f in findings) for k in ("likely-bug", "needs-human")}
    reasons = []
    if counts["likely-bug"]:
        reasons.append(f"{counts['likely-bug']} behaviour change(s) look like unintended regressions.")
    elif b == "REVIEW":
        reasons.append("Behaviour changed; the evidence does not settle whether it was intended.")
    if reason:
        reasons.append(reason)
    return {"verdict": combine(b, p), "behaviour": b, "performance": p, "reasons": reasons}


def fails(verdict: str, fail_on: str) -> bool:
    """`fail_on`: "block", "review" or "never"."""
    if fail_on == "never":
        return False
    return RANK[verdict] >= RANK[fail_on.upper()]
