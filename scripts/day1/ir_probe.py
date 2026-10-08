"""Day-1 measurement check: is cachegrind instruction count (Ir) a usable search metric?

Runs inside the harness container (needs valgrind). For each packaging ref it measures
Ir for parsing two workload families, subtracting an import-only null run:

  * A/A noise: the same ref and workload repeated, so we get the coefficient of variation.
  * Per-family ratio: base vs candidate on "simple" vs "non-simple" versions. This is the
    #1082 trade-off maintainers argued by hand (faster on simple, slower on the rest).

    docker run --rm -v "$PWD":/work -v bw-cache:/cache breakwater-harness \
        python scripts/day1/ir_probe.py --repeats 5
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path

REPO = "https://github.com/pypa/packaging"
REFS = {"base": "59f183fe90da", "pr1082": "ee13ba2c1c9a"}  # parent and merge of PR #1082
ENVS = Path("/cache/envs")

WORKLOAD = r"""
import sys
from packaging.version import Version
family, n = sys.argv[1], int(sys.argv[2])
if family == "null":
    sys.exit(0)
if family == "simple":
    items = [f"{i % 13}.{i % 7}.{i % 31}" for i in range(n)]
else:
    suffixes = ["rc1", ".post2", ".dev3", "a4", "b1", "+local.7", ".post1.dev2"]
    items = [f"{i % 5}!{i % 13}.{i % 7}{suffixes[i % len(suffixes)]}" if i % 3 == 0
             else f"{i % 13}.{i % 7}{suffixes[i % len(suffixes)]}" for i in range(n)]
for s in items:
    Version(s)
"""


def ensure_env(name: str, sha: str) -> Path:
    env = ENVS / name
    py = env / "bin" / "python"
    if not py.exists():
        subprocess.run(["uv", "venv", "--quiet", "--python", sys.executable, str(env)], check=True)
        subprocess.run(
            ["uv", "pip", "install", "--quiet", "--python", str(py), f"packaging @ git+{REPO}@{sha}"], check=True
        )
    return py


def cachegrind_ir(py: Path, family: str, n: int) -> int:
    out = Path("/tmp/cg.out")
    proc = subprocess.run(
        ["valgrind", "--tool=cachegrind", "--cache-sim=no", f"--cachegrind-out-file={out}",
         str(py), "-c", WORKLOAD, family, str(n)],
        capture_output=True, text=True, check=True,
    )
    m = re.search(r"I\s+refs:\s+([\d,]+)", proc.stderr)
    if not m:
        raise RuntimeError(proc.stderr[-500:])
    return int(m.group(1).replace(",", ""))


def wall(py: Path, family: str, n: int) -> float:
    t = time.perf_counter()
    subprocess.run([str(py), "-c", WORKLOAD, family, str(n)], check=True)
    return time.perf_counter() - t


def cv(xs: list[float]) -> float:
    return statistics.pstdev(xs) / statistics.mean(xs) if len(xs) > 1 else 0.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeats", type=int, default=5)
    ap.add_argument("--n", type=int, default=3000)
    args = ap.parse_args()

    pys = {name: ensure_env(name, sha) for name, sha in REFS.items()}
    report: dict = {"n": args.n, "repeats": args.repeats, "refs": REFS, "families": {}}

    for name, py in pys.items():
        null = statistics.median(cachegrind_ir(py, "null", 0) for _ in range(3))
        for family in ("simple", "nonsimple"):
            t0 = time.perf_counter()
            irs = [cachegrind_ir(py, family, args.n) - null for _ in range(args.repeats)]
            secs = (time.perf_counter() - t0) / args.repeats
            walls = [wall(py, family, args.n) for _ in range(args.repeats)]
            report["families"].setdefault(family, {})[name] = {
                "ir_median": statistics.median(irs),
                "ir_cv": cv(irs),
                "wall_cv": cv(walls),
                "cachegrind_secs_per_run": round(secs, 2),
            }
            print(f"{name:7s} {family:9s} Ir={statistics.median(irs):>13,.0f}  Ir CV={cv(irs):.4%}  "
                  f"wall CV={cv(walls):.2%}  cachegrind {secs:.1f}s/run", flush=True)

    for family, by_ref in report["families"].items():
        ratio = by_ref["base"]["ir_median"] / by_ref["pr1082"]["ir_median"]
        by_ref["speedup_base_over_pr1082"] = round(ratio, 3)
        print(f"#1082 Ir speedup on {family}: {ratio:.2f}x")

    out = Path("artifacts/day1/ir_probe.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
