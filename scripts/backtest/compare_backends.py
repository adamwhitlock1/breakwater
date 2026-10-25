"""Compare two backtests of the same corpus run on different backends, item by item: verdict (behaviour
+ performance, as the site computes it), classes and labels, known issues caught, and the Ir ratios of
the perf families both runs measured (archived families are shared, so their generators are identical;
planned families differ between runs and are listed, not matched).

    uv run python scripts/backtest/compare_backends.py artifacts/backtest/codeflash-v1 artifacts/backtest/codeflash-v2
    uv run python scripts/backtest/compare_backends.py artifacts/backtest/packaging-v3 \
        artifacts/backtest/packaging-v4-sandboxes --perf-from artifacts/backtest/packaging-v2

Adjudication and regression tests are read from artifacts/adjudication/<name> and artifacts/regress/<name>
when they exist. Prints Markdown; no model calls, no sandbox runs.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from breakwater.site.build import BACKEND_SHORT, ItemView, load  # noqa: E402


def sibling(bt: Path, kind: str) -> Path | None:
    p = bt.parents[1] / kind / bt.name
    return p if (p / ("adjudication.json" if kind == "adjudication" else "summary.json")).exists() else None


def views(bt: Path, perf_from: Path | None) -> tuple[dict, dict[str, ItemView]]:
    results, _, items = load(bt, sibling(bt, "adjudication"), perf_from, sibling(bt, "regress"))
    return results, {it.raw["id"]: it for it in items}


def labels(it: ItemView) -> str:
    counts = {}
    for c in it.cards:
        counts[c.label or "unlabelled"] = counts.get(c.label or "unlabelled", 0) + 1
    return ", ".join(f"{n} {k}" for k, n in sorted(counts.items())) or "–"


def tests(it: ItemView) -> str:
    n = sum(bool(c.test and c.test.get("verified")) for c in it.cards)
    return str(n) if it.cards else "–"


def worst(it: ItemView) -> str:
    p = it.perf_worst
    return f'{p["worst_valid_ratio"]:.2f}x {p.get("worst_family", "")[:36]}' if p.get("worst_valid_ratio") else "–"


def families(it: ItemView) -> dict[str, dict]:
    out = {}
    for t in it.targets:
        for f in ((t.perf or {}).get("report") or {}).get("findings", []):
            out[f["family"]] = f
    return out


def ladder(f: dict) -> str:
    return " ".join(f"{p['n']}:{p['ratio']:.2f}" for p in f.get("ladder", []) if p.get("ratio") and p.get("judged", True))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--perf-from", help="backtest whose perf fills A's targets without perf (packaging-v3 reused v2)")
    args = ap.parse_args()
    ra, va = views(Path(args.a), Path(args.perf_from) if args.perf_from else None)
    rb, vb = views(Path(args.b), None)
    be_a = BACKEND_SHORT.get(next(b for it in va.values() for b in it.backends), "?")
    be_b = BACKEND_SHORT.get(next(b for it in vb.values() for b in it.backends), "?")
    ids = [i for i in va if i in vb]
    print(f"| item | verdict {be_a} | verdict {be_b} | classes {be_a} | classes {be_b} | known {be_a} | known {be_b} | "
          f"tests {be_a} / {be_b} | perf worst {be_a} | perf worst {be_b} | image {be_b} |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    same = 0
    for i in ids:
        a, b = va[i], vb[i]
        mark = "" if a.verdict == b.verdict else " ✗"
        same += a.verdict == b.verdict
        print(f"| {i} | {a.verdict} | {b.verdict}{mark} | {len(a.cards)} ({labels(a)}) | {len(b.cards)} ({labels(b)}) | "
              f"{', '.join(a.caught) or '–'} | {', '.join(b.caught) or '–'} | {tests(a)} / {tests(b)} | {worst(a)} | {worst(b)} | "
              f"`{', '.join(t.image for t in b.targets)}` |")
    usd_a = sum(it.usd for it in va.values() if it.raw["id"] in ids)
    usd_b = sum(it.usd for it in vb.values() if it.raw["id"] in ids)
    print(f"\n{same}/{len(ids)} same verdict. Nemotron cost (backtest + adjudication) on these items: "
          f"{be_a} ${usd_a:.2f}, {be_b} ${usd_b:.2f}. Providers: {ra.get('provider') or ra['summary'].get('provider')} / {rb.get('provider') or rb['summary'].get('provider')}.")
    print("\nPerf families measured in full on both backends (same family text ⇒ same generator; head/base Ir per call):\n")
    print(f"| item | family | {be_a} | {be_b} | gap |\n|---|---|---|---|---|")
    gaps = []
    for i in ids:
        fa, fb = families(va[i]), families(vb[i])
        for name in sorted(set(fa) & set(fb)):
            x, y = fa[name], fb[name]
            wx, wy = x.get("worst_ratio"), y.get("worst_ratio")
            gap = abs(wx - wy) / wx if wx and wy else None
            if gap is not None:
                gaps.append(gap)
            print(f"| {i} | {name[:50]} | {x['verdict']} {wx:.3f}x · {ladder(x)} | {y['verdict']} {wy:.3f}x · {ladder(y)} | "
                  f"{f'{gap:.1%}' if gap is not None else '–'} |" if wx and wy else
                  f"| {i} | {name[:50]} | {x['verdict']} | {y['verdict']} | – |")
        only_a, only_b = sorted(set(fa) - set(fb)), sorted(set(fb) - set(fa))
        if only_a or only_b:
            print(f"| {i} | *(planned families only on one backend)* | {len(only_a)} | {len(only_b)} | – |")
    if gaps:
        print(f"\nShared families: {len(gaps)}; largest gap {max(gaps):.1%}, median {sorted(gaps)[len(gaps) // 2]:.1%}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
