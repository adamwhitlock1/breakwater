"""Re-score a finished backtest after the P4 control fix (2026-10-08). No model calls.

    uv run python scripts/backtest/rescore_p4.py artifacts/backtest/packaging-v2

P4 `eq-fresh` used to flag any base-pickled object that didn't equal a fresh head object. Two
cases were not pickle bugs: equality that raises even between two fresh objects (4,300-digit
inputs hit Python's int-digit limit on both sides), and builtin return values, where P4 restated
a P1 output difference. The worker now runs a fresh==fresh control and skips builtins.

For every item with a P4 eq-fresh class, on an image rebuilt with the fixed harness:
  * the no-LLM arms (hypothesis, mutations) are re-run in full: they are deterministic and cheap;
  * the LLM arms (llm-plan, breakwater) keep a P4 eq-fresh class only if its stored
    representative input still produces it.
Known-issue matches, results.json, table.md and the per-item files are rewritten in place;
results.json records each removed class under "corrections".
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from breakwater import backtest as bt  # noqa: E402
from breakwater.backends import get_backend  # noqa: E402
from breakwater.images import build_pair, git_req  # noqa: E402
from breakwater.probes import Runner, Target, run_probes  # noqa: E402

NO_LLM = ("hypothesis", "mutations")
NOTE = ("P4 control fix: a base-pickled object failing to equal a fresh head object only counts if two fresh "
        "head objects compare equal; builtin return values are skipped (P4 would restate P1)")


def main(src: Path) -> int:
    load_dotenv()
    backend = get_backend("docker")
    meta = json.loads((src / "results.json").read_text())
    corpus = json.loads(Path(meta["corpus"]).read_text())
    repo, by_id = corpus["repo"], {it["id"]: it for it in corpus["items"]}
    corrections: list[dict] = []
    items = []
    for item in meta["items"]:
        for t in item["targets"]:
            stale = {c for a in t["arms"].values() for c in a["classes"] if c.startswith("P4|base->head eq-fresh")}
            if not stale:
                continue
            image = build_pair(git_req(repo, item["base"]), git_req(repo, item["head"]))
            tgt = next(x for x in by_id[item["id"]]["targets"] if x["callable"] == t["target"])
            target = Target(tgt["callable"], tuple(tgt["observe"]))
            before = {arm: sorted(stale & set(a["classes"])) for arm, a in t["arms"].items()}
            # LLM arms: re-check each stale class on its stored representative input.
            gone: set[str] = set()
            for f in t["findings"]:
                if f["signature"] in stale:
                    rep = run_probes(Runner(backend, image, target), f["args"], ("P4",))
                    if f["signature"] not in rep.classes():
                        gone.add(f["signature"])
            t["findings"] = [f for f in t["findings"] if f["signature"] not in gone]
            for arm in ("llm-plan", "breakwater"):
                if arm in t["arms"]:
                    t["arms"][arm]["classes"] = [c for c in t["arms"][arm]["classes"] if c not in gone]
            # No-LLM arms: re-run in full with the fixed harness.
            fresh = bt.run_target({**by_id[item["id"]]}, tgt, repo, backend, arms=NO_LLM, do_perf=False,
                                  seed=0, log=lambda *_: None)
            for arm in NO_LLM:
                if arm in t["arms"]:
                    t["arms"][arm]["classes"] = fresh["arms"][arm]["classes"]
            for a in t["arms"].values():
                a["known"] = [k["id"] for k in item["known"] if any(bt.matches(c, k["match"]) for c in a["classes"])]
            removed = {arm: [c for c in cs if c not in t["arms"][arm]["classes"]] for arm, cs in before.items()}
            removed = {k: v for k, v in removed.items() if v}
            if removed:
                corrections.append({"item": item["id"], "target": t["target"], "image": image.ref, "removed": removed,
                                    "note": NOTE})
            t["image_rescored"] = image.ref
            print(item["id"], t["target"].split(":")[1], {k: len(v) for k, v in removed.items()}, flush=True)
        (src / f"{item['id'].strip('#').replace('@', '-')}.json").write_text(
            json.dumps(item, indent=2, ensure_ascii=False, default=str))
        items.append(item)

    arms = tuple(meta["arms"])
    summary = bt.summarize(items, arms)
    summary["provider"] = meta.get("provider", "tokenfactory")
    meta.update(items=items, summary=summary, corrections=meta.get("corrections", []) + corrections)
    (src / "results.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False, default=str))
    table = (src / "table.md").read_text()
    footer = table[table.index("Cells are distinct"):] if "Cells are distinct" in table else ""
    extra = ("\n\nRe-scored after the P4 control fix (`scripts/backtest/rescore_p4.py`): removed "
             + "; ".join(f"{c['item']} " + ", ".join(f"{arm} {len(v)}" for arm, v in c["removed"].items())
                         for c in corrections) + ".") if corrections else ""
    body = bt.render(items, arms, summary)
    body = body[: body.index("Cells are distinct")] + footer + extra
    (src / "table.md").write_text(body)
    print(json.dumps({k: v for k, v in summary.items() if k != "usd"}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1] if len(sys.argv) > 1 else "artifacts/backtest/packaging-v2")))
