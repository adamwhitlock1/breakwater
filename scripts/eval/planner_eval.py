"""Planner quality on one PR: how many of Ultra's attacks predict a difference, and how many have
example inputs that actually expose one (deterministic probes, no search, no mutations).

    BREAKWATER_PROVIDER=tokenfactory uv run python scripts/eval/planner_eval.py --runs 3 --label v2

Each run is one `plan_attacks` call (PLAN_SAMPLES samples, interleaved, as in an audit). An attack is
"productive" if probing its own example arguments yields at least one divergence class. Results are
appended to artifacts/eval/planner.jsonl with the label, so prompt versions can be compared.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from breakwater import adversary, ledger  # noqa: E402
from breakwater.backends.docker import DockerBackend  # noqa: E402
from breakwater.images import build_pair, git_req  # noqa: E402
from breakwater.llm import Nemotron  # noqa: E402
from breakwater.probes import ALL_PROBES, Runner, Target, run_probes  # noqa: E402
from breakwater.repo import gather  # noqa: E402

REPO = "https://github.com/pypa/packaging"
BASE, HEAD = "59f183fe90da403e41eef339ce9088bda0fe4cd3", "61967cca278dc51389b8973ba65bbbf23eaa3eda"
TARGET = Target("packaging.version:Version", ("str", "repr", "attr:release", "attr:public"))
SAME = re.compile(r"\b(identical|unchanged|same (behaviou?r|result|object)|no (observable )?(behaviou?r )?difference)\b", re.I)


def main() -> int:
    load_dotenv(".env")
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--label", required=True)
    args = ap.parse_args()
    ctx = gather(REPO, BASE, HEAD, TARGET.callable)
    image = build_pair(git_req(REPO, BASE), git_req(REPO, HEAD))
    backend = DockerBackend()
    out = Path("artifacts/eval/planner.jsonl")
    out.parent.mkdir(parents=True, exist_ok=True)
    for i in range(args.runs):
        run_id = f"planner-eval-{args.label}-{i}-{int(time.time())}"
        llm = Nemotron(run_id=run_id)
        attacks = adversary.plan_attacks(llm, ctx, TARGET.observe, 5)
        rows = []
        for a in attacks:
            classes = sorted(run_probes(Runner(backend, image, TARGET), a.example_args, ALL_PROBES).classes()) \
                if a.example_args else []
            no_diff = getattr(a, "difference", "") == "no difference expected" or bool(SAME.search(a.why_it_breaks))
            rows.append({"id": a.id, "assumption": a.assumption[:160], "no_diff_text": no_diff,
                         "examples": len(a.example_args), "classes": classes})
        usd = sum(t["usd"] for t in ledger.summarize(run_id=run_id).values())
        rec = {"label": args.label, "run": i, "provider": llm.provider.value, "usd": round(usd, 4),
               "attacks": len(rows), "predict_difference": sum(not r["no_diff_text"] for r in rows),
               "productive": sum(bool(r["classes"]) for r in rows),
               "classes": sorted({c for r in rows for c in r["classes"]}), "rows": rows}
        with out.open("a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"{args.label} run {i}: {rec['attacks']} attacks, {rec['predict_difference']} predict a difference, "
              f"{rec['productive']} productive, {len(rec['classes'])} classes, ${usd:.3f}")
        for r in rows:
            print(f"   {r['id']} {'SAME' if r['no_diff_text'] else 'diff'} {len(r['classes'])} cls | {r['assumption'][:100]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
