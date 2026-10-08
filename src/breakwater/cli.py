"""`breakwater` command line: doctor, probe (deterministic), audit (Nemotron adversary) and bill."""

from __future__ import annotations

import argparse
import importlib.util
import json
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


def _short(v, n: int = 70) -> str:
    s = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
    return s if len(s) <= n else s[: n - 15] + f"...({len(s)} chars)"


def probe(args: argparse.Namespace) -> int:
    from breakwater.backends import get_backend
    from breakwater.images import build_pair, git_req
    from breakwater.probes import ALL_PROBES, Runner, Target, run_probes

    if args.repo:
        base_req, head_req = git_req(args.repo, args.base), git_req(args.repo, args.head)
    elif args.base_req and args.head_req:
        base_req, head_req = args.base_req, args.head_req
    else:
        print("give --repo/--base/--head or --base-req/--head-req")
        return 2
    inputs: list[list] = [[s] for s in args.input or []]
    if args.inputs_file:
        inputs += json.loads(open(args.inputs_file).read())
    if not inputs:
        print("no inputs: use --input or --inputs-file")
        return 2

    image = build_pair(base_req, head_req)
    target = Target(args.target, tuple(args.observe.split(",")))
    probes = tuple(args.probes.split(",")) if args.probes else ALL_PROBES
    report = run_probes(Runner(get_backend(args.backend), image, target), inputs, probes)

    classes = report.classes()
    print(f"{args.target}: {len(inputs)} inputs, {len(report.divergences)} divergences in {len(classes)} classes "
          f"(backend={report.backend}, image={report.image})")
    for ds in classes.values():
        d = ds[0]
        print(f"  [{d.probe}] {d.detail} x{len(ds)}")
        print(f"      input: {_short(d.inputs)}")
        print(f"      base:  {_short(d.base)}")
        print(f"      head:  {_short(d.head)}")
    if args.json:
        with open(args.json, "w") as f:
            json.dump(report.to_json(), f, indent=2, ensure_ascii=False)
    return 1 if classes else 0


def audit(args: argparse.Namespace) -> int:
    import uuid
    from pathlib import Path

    from breakwater.adversary import audit as run_audit
    from breakwater.adversary import render_markdown
    from breakwater.backends import get_backend
    from breakwater.images import build_pair, git_req
    from breakwater.llm import Nemotron
    from breakwater.probes import Target
    from breakwater.repo import gather

    run_id = uuid.uuid4().hex[:12]
    llm = Nemotron(run_id=run_id)
    ctx = gather(args.repo, args.base, args.head, args.target)
    image = build_pair(git_req(args.repo, args.base), git_req(args.repo, args.head))
    target = Target(args.target, tuple(args.observe.split(",")))
    report = run_audit(ctx, image, llm, get_backend(args.backend), target, n_attacks=args.attacks,
                       strategies_per_attack=args.strategies, max_examples=args.max_examples,
                       seed=args.seed, run_id=run_id)
    out = Path(args.out or f"artifacts/runs/{run_id}")
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(report.to_json(), indent=2, ensure_ascii=False))
    md = render_markdown(report)
    (out / "report.md").write_text(md)
    print("\n" + md + f"\n\nwrote {out}/report.json and report.md")
    return 1 if report.findings else 0


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
    p = sub.add_parser("probe", help="run deterministic differential probes on base vs head")
    p.add_argument("--target", required=True, help="callable under test, e.g. packaging.version:Version")
    p.add_argument("--repo", help="git URL; use with --base and --head commit/ref")
    p.add_argument("--base")
    p.add_argument("--head")
    p.add_argument("--base-req", help="pip requirement for base, e.g. packaging==26.0")
    p.add_argument("--head-req")
    p.add_argument("--input", action="append", help="single string argument; repeatable")
    p.add_argument("--inputs-file", help="JSON list of argument lists")
    p.add_argument("--observe", default="str,repr", help="comma list: str,repr,len,attr:<name>")
    p.add_argument("--probes", help="comma list, default P1,P2,P3,P4 (P4down is opt-in)")
    p.add_argument("--backend", default=os.environ.get("BREAKWATER_BACKEND", "docker"))
    p.add_argument("--json", help="write the full report here")
    p.set_defaults(fn=probe)
    a = sub.add_parser("audit", help="Nemotron adversary: plan attacks, write strategies, search, probe")
    a.add_argument("--repo", required=True)
    a.add_argument("--base", required=True)
    a.add_argument("--head", required=True)
    a.add_argument("--target", required=True)
    a.add_argument("--observe", default="str,repr")
    a.add_argument("--attacks", type=int, default=5)
    a.add_argument("--strategies", type=int, default=4, help="strategies per attack")
    a.add_argument("--max-examples", type=int, default=300)
    a.add_argument("--seed", type=int, default=0)
    a.add_argument("--backend", default=os.environ.get("BREAKWATER_BACKEND", "docker"))
    a.add_argument("--out", help="output dir (default artifacts/runs/<run_id>)")
    a.set_defaults(fn=audit)
    b = sub.add_parser("bill", help="Token Factory spend by tier, from the ledger")
    b.add_argument("--run-id")
    b.set_defaults(fn=bill)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
