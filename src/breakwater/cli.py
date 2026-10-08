"""`breakwater` command line. `audit` lands in week 1; for now: environment doctor and the bill."""

from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import subprocess
import sys

from dotenv import load_dotenv

from breakwater import ledger


def doctor(_: argparse.Namespace) -> int:
    checks: list[tuple[str, bool, str]] = []
    for var in ("NEBIUS_API_KEY", "NEBIUS_PROJECT_ID", "TAVILY_API_KEY"):
        checks.append((var, bool(os.environ.get(var)), "set" if os.environ.get(var) else "missing (.env)"))
    docker = shutil.which("docker") is not None
    up = docker and subprocess.run(["docker", "info"], capture_output=True).returncode == 0
    checks.append(("docker daemon", up, "running" if up else "not running (needed for the local backend)"))
    image = up and subprocess.run(["docker", "image", "inspect", "breakwater-harness"],
                                  capture_output=True).returncode == 0
    checks.append(("breakwater-harness image", image, "built" if image else "docker build -f docker/harness.Dockerfile -t breakwater-harness ."))
    contree = importlib.util.find_spec("contree_sdk") is not None
    checks.append(("contree-sdk", contree, "installed" if contree else "uv sync --extra sandboxes"))
    for name, ok, detail in checks:
        print(f"{'ok ' if ok else 'XX '} {name:28s} {detail}")
    return 0 if all(ok for name, ok, _ in checks if name != "TAVILY_API_KEY") else 1


def bill(args: argparse.Namespace) -> int:
    totals = ledger.summarize(run_id=args.run_id)
    if not totals:
        print("ledger is empty")
        return 0
    grand = 0.0
    print(f"{'tier':10s} {'calls':>6s} {'tokens in':>12s} {'tokens out':>12s} {'usd':>10s}")
    for tier, t in sorted(totals.items()):
        grand += t["usd"]
        print(f"{tier:10s} {int(t['calls']):6d} {int(t['tokens_in']):12,d} {int(t['tokens_out']):12,d} {t['usd']:10.4f}")
    print(f"{'total':10s} {'':6s} {'':12s} {'':12s} {grand:10.4f}")
    return 0


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    ap = argparse.ArgumentParser(prog="breakwater", description=__doc__)
    sub = ap.add_subparsers(required=True)
    sub.add_parser("doctor", help="check keys, Docker and Sandboxes SDK").set_defaults(fn=doctor)
    b = sub.add_parser("bill", help="Token Factory spend by tier, from the ledger")
    b.add_argument("--run-id")
    b.set_defaults(fn=bill)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
