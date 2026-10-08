"""Day-1 Sandboxes (ConTree) checks. Run once beta access is granted.

    uv sync --extra sandboxes
    uv run python scripts/day1/check_contree.py

Needs NEBIUS_API_KEY and NEBIUS_PROJECT_ID. Answers:
  * does auth work (a 403 means access is not granted yet)?
  * can we pull python:3.12-slim and install valgrind + packaging into a kept image?
  * branch fidelity: two branches from the same snapshot see identical files
  * branch latency, per-run cost, and what units the resource fields use
  * A/A noise of user CPU time inside a microVM, and whether cachegrind runs there
Writes artifacts/day1/contree.json.
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from breakwater.backends.contree import ContreeBackend  # noqa: E402

OUT = Path("artifacts/day1/contree.json")
WORKLOAD = (
    "from packaging.version import Version\n"
    "for i in range(20000): Version(f'{i%13}.{i%7}.{i%31}')\n"
)


def sh(cmd: str) -> list[str]:
    return ["sh", "-c", cmd]


def main() -> int:
    load_dotenv()
    be = ContreeBackend()
    report: dict = {}

    t0 = time.perf_counter()
    hello = be.run("python:3.12-slim", ["python", "-V"])
    report["hello"] = {"stdout": hello.stdout.strip(), "exit": hello.exit_code, "ms": hello.duration_ms,
                       "resources": vars(hello.resources)}
    print(f"hello: {hello.stdout.strip()} in {hello.duration_ms} ms, resources={vars(hello.resources)}")

    print("building kept image: valgrind + packaging 26.3 (one-time)")
    built = be.run("python:3.12-slim", sh(
        "apt-get update -qq && apt-get install -y -qq valgrind >/dev/null && pip install -q packaging==26.3"
    ), keep=True, timeout_s=900, tag="breakwater-day1")
    report["build"] = {"exit": built.exit_code, "image": built.image_ref, "ms": built.duration_ms,
                       "stderr_tail": built.stderr[-300:]}
    print(f"  exit={built.exit_code} image={built.image_ref} {built.duration_ms} ms")
    if built.exit_code != 0:
        print(built.stderr[-800:])
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(report, indent=2, default=str))
        return 1

    print("branch fidelity: write a file, branch twice, compare hashes")
    step = be.run(built.image_ref, sh("mkdir -p /w && echo state-$RANDOM > /w/f"), keep=True)
    hashes = [be.run(step.image_ref, sh("sha256sum /w/f && python -c 'import packaging;print(packaging.__version__)'"))
              for _ in range(2)]
    report["branch"] = {"image": step.image_ref, "outputs": [h.stdout for h in hashes],
                        "identical": hashes[0].stdout == hashes[1].stdout,
                        "branch_ms": [h.duration_ms for h in hashes]}
    print(f"  identical={report['branch']['identical']} latency={report['branch']['branch_ms']} ms")

    print("A/A: 10 runs of the same workload")
    runs = [be.run(built.image_ref, ["python", "-c", WORKLOAD]) for _ in range(10)]
    user = [r.resources.user_cpu_s for r in runs if r.resources.user_cpu_s is not None]
    report["aa"] = {
        "user_cpu": user,
        "user_cpu_cv": statistics.pstdev(user) / statistics.mean(user) if len(user) > 1 else None,
        "wall_ms": [r.duration_ms for r in runs],
        "cost_usd": [r.resources.cost_usd for r in runs],
        "involuntary_switches": [r.resources.involuntary_switches for r in runs],
    }
    print(f"  user CPU CV={report['aa']['user_cpu_cv']}, cost per run={report['aa']['cost_usd'][:3]}")

    print("cachegrind inside the microVM")
    cg = be.run(built.image_ref, sh("valgrind --tool=cachegrind --cache-sim=no --cachegrind-out-file=/tmp/cg "
                                     f"python -c \"{WORKLOAD}\" 2>&1 | grep 'I *refs'"), timeout_s=600)
    report["cachegrind"] = {"exit": cg.exit_code, "out": cg.stdout.strip(), "ms": cg.duration_ms}
    print(f"  {cg.stdout.strip() or cg.stderr[-300:]} ({cg.duration_ms} ms)")

    report["total_s"] = round(time.perf_counter() - t0, 1)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, default=str))
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
