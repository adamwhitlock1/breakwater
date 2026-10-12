"""Add per-size validity to perf ladders measured before it was recorded, and re-judge them. No
model calls and no instruction counting: only the base version constructing each size's inputs.

    uv run python scripts/backtest/backfill_ladder_validity.py artifacts/backtest/packaging-v2
    uv run python scripts/backtest/backfill_ladder_validity.py --run artifacts/demo/pr1082-61967cca

Ladders come from LLM-written `make(n)` generators that run seeded in the sandbox, so they
regenerate exactly from the recorded source and seed. Each regenerated size is checked against the
recorded mean input size; a mismatch leaves that size's validity unknown (counted as valid, i.e.
the old behaviour) and is reported. Verdicts, slopes and the perf summary are then recomputed with
judged points only (perf.PerfFinding.judged_points).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from breakwater import backtest as bt  # noqa: E402
from breakwater import perf  # noqa: E402
from breakwater.backends import get_backend  # noqa: E402
from breakwater.images import build_pair, git_req  # noqa: E402
from breakwater.perf import Family, LadderPoint, PerfFinding, judge_slopes  # noqa: E402
from breakwater.probes import Target  # noqa: E402

FIELDS = ("id", "kind", "family", "why", "size_meaning", "make_source", "example_args", "origin")


def backfill(report: dict, image, target: Target, backend, seed: int = 0) -> list[str]:
    """Mutates a perf report (JSON) in place. Returns notes on anything that didn't reproduce."""
    fams = {f["id"]: f for f in report.get("families", [])}
    notes = []
    for fd in report.get("findings", []):
        fam = fams.get(fd["family_id"])
        if not fam:
            notes.append(f"{fd['family_id']}: family not recorded")
            continue
        ladder = perf.make_ladder(backend, image, Family(**{k: fam.get(k) for k in FIELDS}), seed)
        for pd in fd["ladder"]:
            inputs = ladder.get(str(pd["n"]))
            if not inputs:
                notes.append(f"{fd['family_id']} n={pd['n']}: size not regenerated")
                continue
            chars = sum(len(json.dumps(a, ensure_ascii=False)) for a in inputs) / len(inputs)
            if abs(chars - pd["input_chars"]) > 1e-6:
                notes.append(f"{fd['family_id']} n={pd['n']}: regenerated inputs differ ({chars:.1f} vs "
                             f"{pd['input_chars']:.1f} chars); validity left unknown")
                continue
            pd["valid_fraction"] = perf.validity(backend, image, target, inputs)
        f = PerfFinding(fd["family_id"], fd["kind"], fd["family"], fd["why"], fd.get("origin", "plan"),
                        fd.get("screen_ratio"), fd.get("valid_fraction"),
                        [LadderPoint(p["n"], p["base_ir"], p["head_ir"], p.get("input_chars", 0.0),
                                     p.get("valid_fraction")) for p in fd["ladder"]],
                        fd.get("slope_base"), fd.get("slope_head"), fd.get("top_inputs", []), fd.get("error"))
        judge_slopes(f)
        before = fd.get("verdict")
        fd.update(slope_base=f.slope_base, slope_head=f.slope_head, verdict=f.verdict, worst_ratio=f.worst_ratio)
        for p, pd in zip(f.ladder, fd["ladder"], strict=True):
            pd["judged"] = p in f.judged_points
        if f.excluded_points or before != f.verdict:
            notes.append(f"{fd['family_id']}: verdict {before} -> {f.verdict}; excluded sizes "
                         f"{[p.n for p in f.excluded_points]}")
    report["ladder_validity"] = "backfilled 2026-10-11 (scripts/backtest/backfill_ladder_validity.py)"
    return notes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("backtest", nargs="?")
    ap.add_argument("--run", help="an audit run dir (report.json) instead of a backtest")
    a = ap.parse_args()
    backend = get_backend("docker")
    if a.run:
        path = Path(a.run) / "report.json"
        r = json.loads(path.read_text())
        image = build_pair(git_req(r["repo"], r["base"]), git_req(r["repo"], r["head"]))
        target = Target(r["target"], ())
        for n in backfill(r["perf"], image, target, backend):
            print(" ", n)
        path.write_text(json.dumps(r, indent=2, ensure_ascii=False))
        from breakwater.site.build import write_run_page

        write_run_page(Path(a.run))
        return 0

    src = Path(a.backtest)
    meta = json.loads((src / "results.json").read_text())
    repo = json.loads(Path(meta["corpus"]).read_text())["repo"]
    for item in meta["items"]:
        for t in item["targets"]:
            rep = (t.get("perf") or {}).get("report")
            if not rep:
                continue
            image = build_pair(git_req(repo, item["base"]), git_req(repo, item["head"]))
            notes = backfill(rep, image, Target(t["target"], ()), backend)
            t["perf"] = perf.summarize(rep)
            print(item["id"], t["target"].split(":")[1], f"worst {t['perf']['worst_valid_ratio']}")
            for n in notes:
                print("   ", n)
        (src / f"{item['id'].strip('#').replace('@', '-')}.json").write_text(
            json.dumps(item, indent=2, ensure_ascii=False, default=str))
    summary = bt.summarize(meta["items"], tuple(meta["arms"]))
    summary["provider"] = meta["summary"].get("provider", "tokenfactory")
    meta["summary"] = summary
    (src / "results.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False, default=str))
    table = (src / "table.md").read_text()
    footer = table[table.index("Cells are distinct"):]
    body = bt.render(meta["items"], tuple(meta["arms"]), summary)
    (src / "table.md").write_text(body[: body.index("Cells are distinct")] + footer
                                  + "\n\nPerf ladders re-judged with per-size validity (`scripts/backtest/"
                                    "backfill_ladder_validity.py`, no model calls).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
