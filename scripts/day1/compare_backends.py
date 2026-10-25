"""Compare two audit runs of the same commit on different backends: verdict, behaviour classes, and
the perf families' Ir ratios (same instruction stream on different CPUs should agree closely).

    uv run python scripts/day1/compare_backends.py artifacts/demo/pr1082-61967cca artifacts/demo/<sandboxes run>

Prints a Markdown table; no model calls, no sandbox runs.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def load(d: str) -> dict:
    return json.loads((Path(d) / "report.json").read_text())


def verdict(rep: dict) -> str:
    adj = {v["signature"]: v["label"] for v in (rep.get("adjudication") or {}).get("verdicts", [])}
    sem = rep.get("semantic") or {}
    likely = [f for f in sem.get("findings", []) if adj.get(f["signature"]) == "likely-bug"]
    perf = rep.get("perf") or {}
    bad = [f for f in perf.get("findings", []) if f.get("verdict") in ("slower", "complexity-regression")]
    if likely or any(f.get("verdict") == "complexity-regression" for f in bad):
        return "BLOCK"
    if sem.get("findings") or bad:
        return "REVIEW"
    return "PASS"


def classes(rep: dict) -> dict[str, str]:
    adj = {v["signature"]: v["label"] for v in (rep.get("adjudication") or {}).get("verdicts", [])}
    return {f["signature"]: adj.get(f["signature"], "unadjudicated") for f in (rep.get("semantic") or {}).get("findings", [])}


def families(rep: dict) -> list[dict]:
    return (rep.get("perf") or {}).get("findings", [])


def worst(fam: dict) -> float | None:
    return fam.get("worst_ratio")


def ladder(fam: dict) -> str:
    pts = fam.get("ladder") or []
    pts = pts.values() if isinstance(pts, dict) else pts
    return " ".join(f"{p.get('n', '?')}:{p['ratio']:.2f}" for p in pts if p.get("ratio"))


def main(a: str, b: str) -> int:
    ra, rb = load(a), load(b)
    rows = [("run", ra["run_id"], rb["run_id"]), ("provider", ra.get("provider"), rb.get("provider"))]
    sa, sb = ra.get("sandbox") or {}, rb.get("sandbox") or {}
    rows += [("backend", (ra.get("semantic") or {}).get("backend"), (rb.get("semantic") or {}).get("backend")),
             ("image", (ra.get("semantic") or {}).get("image"), (rb.get("semantic") or {}).get("image")),
             ("verdict", verdict(ra), verdict(rb)),
             ("behaviour classes", len(classes(ra)), len(classes(rb))),
             ("likely-bug", sum(v == "likely-bug" for v in classes(ra).values()), sum(v == "likely-bug" for v in classes(rb).values())),
             ("perf families measured", len(families(ra)), len(families(rb))),
             ("sandbox runs", sa.get("runs", "n/a"), sb.get("runs", "n/a")),
             ("sandbox cost (USD, free in beta)", sa.get("cost_usd", "n/a"), sb.get("cost_usd", "n/a")),
             ("Nemotron cost (USD)", round(sum(ra.get("usd_by_tier", {}).values()), 4), round(sum(rb.get("usd_by_tier", {}).values()), 4))]
    print(f"| | {a} | {b} |\n|---|---|---|")
    for k, x, y in rows:
        print(f"| {k} | {x} | {y} |")
    only_a, only_b = set(classes(ra)) - set(classes(rb)), set(classes(rb)) - set(classes(ra))
    print(f"\nClasses only in {a}: {len(only_a)}; only in {b}: {len(only_b)}; shared: {len(set(classes(ra)) & set(classes(rb)))}")
    for sig in sorted(only_a | only_b):
        print(f"  {'A' if sig in only_a else 'B'} {sig[:110]}")
    print("\nPerf families (worst judged Ir ratio head/base; lower is faster):")
    print(f"| family | {a} | {b} |\n|---|---|---|")
    fa = {f["family"]: f for f in families(ra)}
    fb = {f["family"]: f for f in families(rb)}
    for name in sorted(set(fa) | set(fb)):
        x, y = fa.get(name), fb.get(name)
        fx = f"{x['verdict']} {worst(x):.3f}x · {ladder(x)}" if x and worst(x) else (x["verdict"] if x else "—")
        fy = f"{y['verdict']} {worst(y):.3f}x · {ladder(y)}" if y and worst(y) else (y["verdict"] if y else "—")
        print(f"| {name[:70]} | {fx} | {fy} |")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
