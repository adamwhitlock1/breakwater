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
    from breakwater.models import PROVIDERS, active_provider

    provider = active_provider()
    note = "provider of record" if PROVIDERS[provider].publishable else "DEV ONLY: results are not publishable"
    checks.append(("BREAKWATER_PROVIDER", True, f"{provider.value} ({note})"))
    for var in ("NEBIUS_API_KEY", "NEBIUS_PROJECT_ID", "TAVILY_API_KEY", "OPENROUTER_API_KEY"):
        checks.append((var, bool(os.environ.get(var)), "set" if os.environ.get(var) else "missing (.env)"))
    docker = shutil.which("docker") is not None
    up = docker and subprocess.run(["docker", "info"], capture_output=True).returncode == 0
    checks.append(("docker daemon", up, "running" if up else "not running (needed for the local backend)"))
    image = up and subprocess.run(["docker", "image", "inspect", "breakwater-harness"],
                                  capture_output=True).returncode == 0
    checks.append(("breakwater-harness image", image, "built" if image else "docker build -f docker/harness.Dockerfile -t breakwater-harness ."))
    contree = importlib.util.find_spec("contree_sdk") is not None
    checks.append(("contree-sdk", contree, "installed" if contree else "uv sync --extra sandboxes"))
    checks += _sandboxes_checks(contree)
    for name, ok, detail in checks:
        print(f"{'ok ' if ok else 'XX '} {name:28s} {detail}")
    optional = {"TAVILY_API_KEY", "OPENROUTER_API_KEY", "NEBIUS_PROJECT_ID"} - {PROVIDERS[provider].key_env}
    return 0 if all(ok for name, ok, _ in checks if name not in optional) else 1


def _sandboxes_checks(sdk_installed: bool) -> list[tuple[str, bool, str]]:
    """Token Factory Sandboxes: whoami (auth), the effective limits and whether the harness image exists."""
    if not (sdk_installed and os.environ.get("NEBIUS_API_KEY") and os.environ.get("NEBIUS_PROJECT_ID")):
        return [("Sandboxes auth (whoami)", False, "skipped: needs contree-sdk, NEBIUS_API_KEY and NEBIUS_PROJECT_ID")]
    from breakwater.backends.contree import MAX_CONCURRENCY, MAX_TIMEOUT_S, OUTPUT_CAP, ContreeBackend
    from breakwater.images import harness_tag

    try:
        be = ContreeBackend()
        who = be.whoami()
    except Exception as e:  # auth failure, no access, network
        return [("Sandboxes auth (whoami)", False, f"{type(e).__name__}: {str(e)[:120]}")]
    limits, running = who["limits"], who["running"]
    perms = ", ".join(k for k, v in sorted(who["permissions"].items()) if v)
    checks = [("Sandboxes auth (whoami)", True, f"token {who['token']}…; can {perms}")]
    conc = limits.get("instance_max_concurrency")
    checks.append(("Sandboxes concurrency", not conc or MAX_CONCURRENCY <= conc,
                   f"limit {conc} instances; Breakwater runs at most {MAX_CONCURRENCY} "
                   f"({running.get('running_instances', 0)} running now)"))
    tmo = limits.get("instance_max_timeout")
    checks.append(("Sandboxes run timeout", not tmo or MAX_TIMEOUT_S <= tmo,
                   f"limit {tmo} s per run; Breakwater runs use up to 900 s (image builds 1800 s)"))
    checks.append(("Sandboxes output cap", True, f"{OUTPUT_CAP // (1024 * 1024)} MiB per stream requested on every run"))
    harness = be.find_tag(harness_tag())
    checks.append(("Sandboxes harness image", True, f"{harness} ({harness_tag()})" if harness
                   else f"not built yet; the first probe or audit builds {harness_tag()} (~1 min)"))
    return checks


DEV_BANNER = ("> **Development run (provider: {}).** Not from Nebius Token Factory; do not publish these numbers.")


def sandbox_line(sandbox: dict) -> str:
    """The receipt's sandbox line. Sandboxes report a per-run cost; it is free during the beta."""
    if sandbox.get("backend") == "contree":
        return (f"**Sandbox cost (free during beta):** ${sandbox.get('cost_usd') or 0:.4f} for {sandbox['runs']} "
                f"Token Factory Sandboxes runs ({sandbox['cpu_s']:.1f} s CPU), image `{sandbox.get('image')}`")
    return (f"**Sandbox runs:** {sandbox['runs']} on local Docker ({sandbox['cpu_s']:.1f} s CPU; no cost), "
            f"image `{sandbox.get('image')}`")


def default_backend() -> str:
    """BREAKWATER_BACKEND, else Sandboxes when its credentials and SDK are present, else Docker."""
    if env := os.environ.get("BREAKWATER_BACKEND"):
        return env
    sandboxes = (os.environ.get("NEBIUS_API_KEY") and os.environ.get("NEBIUS_PROJECT_ID")
                 and importlib.util.find_spec("contree_sdk") is not None)
    return "contree" if sandboxes else "docker"


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

    backend = get_backend(args.backend)
    image = build_pair(base_req, head_req, backend=backend)
    target = Target(args.target, tuple(args.observe.split(",")))
    probes = tuple(args.probes.split(",")) if args.probes else ALL_PROBES
    report = run_probes(Runner(backend, image, target), inputs, probes)

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


def _serve(directory, port: int):
    """Serve the run directory on localhost for the live page. Returns the server (daemon thread)."""
    import functools
    import http.server
    import threading

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):  # the live page polls every 0.8 s; keep the terminal readable
            pass

        def end_headers(self):  # files change while the run goes on; never serve a cached copy
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

    handler = functools.partial(Quiet, directory=str(directory))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def audit(args: argparse.Namespace) -> int:
    import uuid
    from pathlib import Path

    from breakwater import adversary, ledger, perf
    from breakwater.backends import get_backend
    from breakwater.events import Events, ObservedBackend
    from breakwater.images import build_pair, git_req
    from breakwater.llm import Nemotron
    from breakwater.models import Provider
    from breakwater.probes import Target
    from breakwater.repo import gather
    from breakwater.site.build import run_cards, verdict_of, write_live_page, write_run_page

    run_id = uuid.uuid4().hex[:12]
    out = Path(args.out or f"artifacts/runs/{run_id}")
    out.mkdir(parents=True, exist_ok=True)
    events = Events(out / "events.jsonl")
    write_live_page(out)
    server = None
    if args.live:
        server = _serve(out, args.port)
        url = f"http://127.0.0.1:{args.port}/live.html"
        print(f"live view: {url}")
        if args.open:
            import webbrowser

            webbrowser.open(url)

    llm = Nemotron(run_id=run_id)
    llm.on_call = lambda e: events("llm", tier=e.tier, model=e.model, purpose=e.purpose, tokens_in=e.tokens_in,
                                   tokens_out=e.tokens_out, reasoning_tokens=e.reasoning_tokens, usd=e.usd,
                                   latency_ms=e.latency_ms, ok=e.ok)
    llm.on_start = lambda tier, purpose, requests: events("llm-start", tier=tier, purpose=purpose, requests=requests)
    backend = ObservedBackend(get_backend(args.backend), events)
    report: dict = {"run_id": run_id, "repo": args.repo, "base": args.base, "head": args.head, "target": args.target,
                    "title": args.title or "", "provider": llm.provider.value}
    events("run", **report)
    sections: list[str] = [] if llm.provider is Provider.TOKENFACTORY else [DEV_BANNER.format(llm.provider.value)]
    found = False
    try:
        events("phase", name="build")
        ctx = gather(args.repo, args.base, args.head, args.target)
        image = build_pair(git_req(args.repo, args.base), git_req(args.repo, args.head), backend=backend)
        events("image", backend=backend.name, image=image.ref, tag=image.tag)
        target = Target(args.target, tuple(args.observe.split(",")))

        if args.mode in ("semantic", "both"):
            sem = adversary.audit(ctx, image, llm, backend, target, n_attacks=args.attacks,
                                  strategies_per_attack=args.strategies, max_examples=args.max_examples,
                                  seed=args.seed, run_id=run_id, events=events)
            report["semantic"] = sem.to_json()
            verdicts = None
            if sem.findings and not args.no_adjudicate:
                from breakwater import adjudicate as adj
                from breakwater.repo import intent_diff

                events("phase", name="adjudicate")
                res = adj.adjudicate(llm, ctx, sem.findings, title=args.title or "",
                                     intent=intent_diff(args.repo, args.base, args.head),
                                     mros=adj.exception_facts(backend, image, sem.findings))
                report["adjudication"] = res.to_json()
                verdicts = res.by_signature()
                for v in res.verdicts:
                    events("verdict", signature=v.signature, label=v.label, votes=v.votes, rationale=v.rationale,
                           evidence=v.evidence[:2])
            if sem.findings:
                from breakwater import regress

                events("phase", name="tests")
                labels = {sig: v.label for sig, v in (verdicts or {}).items()}
                tests = regress.for_findings(backend, image, args.target, sem.findings, labels=labels)
                report["regression_tests"] = [t.to_json() for t in tests]
                if any(t.verified for t in tests):
                    (out / "test_regressions.py").write_text(regress.render_file(
                        tests, f"Regression tests for {args.repo} {args.base[:10]}..{args.head[:10]} ({args.target})"))
                events("tests", generated=sum(bool(t.source) for t in tests), verified=sum(t.verified for t in tests),
                       skipped=sum(bool(t.skipped) for t in tests))
            sections.append(adversary.render_markdown(sem, verdicts))
            # BLOCK on likely bugs only once adjudicated; unadjudicated, every divergence counts.
            found = found or (any(v.label == "likely-bug" for v in verdicts.values()) if verdicts
                              else bool(sem.findings))
        if args.mode in ("perf", "both"):
            pr = perf.perf_audit(ctx, image, llm, backend, target, run_id=run_id, n_families=args.families,
                                 seed=args.seed, use_archive=not args.no_archive, events=events)
            report["perf"] = pr.to_json()
            sections.append(perf.render_markdown(pr))
            found = found or any(f.verdict in ("slower", "complexity-regression") for f in pr.findings)
    except BaseException as e:
        events("error", message=f"{type(e).__name__}: {str(e)[:300]}")
        raise

    events("phase", name="report")
    usd = {tier: t["usd"] for tier, t in ledger.summarize(run_id=run_id).items()}
    report["usd_by_tier"] = usd
    report["sandbox"] = sandbox = backend.summary(image.ref)
    sections.append(f"**Total Nemotron cost:** ${sum(usd.values()):.4f} "
                    f"({', '.join(f'{k} ${v:.4f}' for k, v in sorted(usd.items()))})  \n"
                    + sandbox_line(sandbox))
    md = "\n\n".join(sections)
    (out / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    (out / "report.md").write_text(md)
    write_run_page(out)
    cards = run_cards(report)
    events("done", verdict=verdict_of(cards) if cards else "PASS", classes=len(cards), report="report.html",
           usd=round(sum(usd.values()), 6), usd_by_tier=usd, sandbox=sandbox)
    print("\n" + md + f"\n\nwrote {out}/report.json, report.md and report.html", flush=True)
    if server:
        print(f"still serving http://127.0.0.1:{args.port}/live.html (Ctrl-C to stop)", flush=True)  # even into a log file
        try:
            import time

            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            server.shutdown()
    return 1 if found else 0


def replay(args: argparse.Namespace) -> int:
    """Replay a recorded audit's events into the live page at a stated speed (for the demo video).
    Nothing is re-run: the page shows the recorded run, labelled as a replay."""
    import shutil
    import time
    from pathlib import Path

    from breakwater.site.build import write_live_page

    src = Path(args.run)
    lines = [json.loads(x) for x in (src / "events.jsonl").read_text().splitlines() if x.strip()]
    if not lines:
        print(f"{src}/events.jsonl is empty")
        return 2
    out = Path(args.out or src / "replay")
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    write_live_page(out)
    for name in ("report.html", "report.json"):
        if (src / name).exists():
            shutil.copy(src / name, out / name)
    log = out / "events.jsonl"
    log.write_text("")
    server = _serve(out, args.port)
    url = f"http://127.0.0.1:{args.port}/live.html"
    print(f"replaying {len(lines)} events at {args.speed:g}x: {url}")
    if args.open:
        import webbrowser

        webbrowser.open(url)
    time.sleep(args.delay)
    t0, seq = time.monotonic(), 0

    def emit(ev: dict) -> None:
        nonlocal seq
        seq += 1
        with log.open("a") as f:
            f.write(json.dumps({**ev, "seq": seq}, ensure_ascii=False) + "\n")

    emit({"t": 0, "kind": "replay", "speed": args.speed, "run_id": lines[0].get("run_id")})
    for ev in lines:
        wait = ev["t"] / args.speed - (time.monotonic() - t0)
        if wait > 0:
            time.sleep(wait)
        emit({**ev, "t": round(ev["t"] / args.speed, 2)})
    print(f"done; still serving {url} (Ctrl-C to stop)")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        server.shutdown()
    return 0


def backtest(args: argparse.Namespace) -> int:
    import time as _time
    from pathlib import Path

    from breakwater import backtest as bt
    from breakwater.backends import get_backend

    arms = tuple(args.arms.split(",")) if args.arms else bt.ARMS
    out = Path(args.out or f"artifacts/backtest/{_time.strftime('%Y%m%d-%H%M%S')}")
    only = args.only.split(",") if args.only else None
    summary = bt.run(args.corpus, get_backend(args.backend), only=only, arms=arms, do_perf=args.perf,
                     seed=args.seed, workers=args.workers, out_dir=out)
    print(json.dumps(summary, indent=2))
    print(f"wrote {out}/results.json and {out}/table.md")
    return 0


def adjudicate(args: argparse.Namespace) -> int:
    import time as _time
    from pathlib import Path

    from breakwater import backtest as bt
    from breakwater.backends import get_backend
    from breakwater.models import active_provider

    src = Path(args.backtest)
    out = Path(args.out or f"artifacts/adjudication/{_time.strftime('%Y%m%d-%H%M%S')}-{active_provider().value}")
    only = args.only.split(",") if args.only else None
    summary = bt.adjudicate_run(src, get_backend(args.backend), only=only, out_dir=out, workers=args.workers)
    print(json.dumps({k: v for k, v in summary.items() if k != "issues"}, indent=2))
    print(f"wrote {out}/adjudication.json and {out}/adjudication.md")
    return 0


# Default sub-sites, when their published artifacts exist: the Codeflash corpus, and the packaging items
# re-run on Token Factory Sandboxes compared item by item with the Docker backtest.
DEFAULT_CODEFLASH = "codeflash:artifacts/backtest/codeflash-v2:artifacts/adjudication/codeflash-v2:artifacts/regress/codeflash-v2"
DEFAULT_SANDBOXES = ("sandboxes:artifacts/backtest/packaging-v4-sandboxes:artifacts/adjudication/packaging-v4-sandboxes"
                     ":artifacts/regress/packaging-v4-sandboxes")


def site(args: argparse.Namespace) -> int:
    from pathlib import Path

    from breakwater.site.build import Corpus, build

    adj = Path(args.adjudication) if args.adjudication else None
    try:
        specs = args.extra if args.extra is not None else (
            [DEFAULT_CODEFLASH] if Path(DEFAULT_CODEFLASH.split(":")[1], "results.json").exists() else [])
        compares = args.compare if args.compare is not None else (
            [DEFAULT_SANDBOXES] if Path(DEFAULT_SANDBOXES.split(":")[1], "results.json").exists() else [])
        extras = []
        for spec, compare in [(x, False) for x in specs] + [(x, True) for x in compares]:
            name, bt_dir, *rest = spec.split(":")
            adj_dir, tests_dir = (rest + [None, None])[:2]
            extras.append(Corpus(name, Path(bt_dir), Path(adj_dir) if adj_dir and Path(adj_dir).exists() else None,
                                 Path(tests_dir) if tests_dir and Path(tests_dir).exists() else None, compare=compare))
        pages = build(Path(args.backtest), adj, Path(args.out), allow_dev=args.allow_dev,
                      runs=[Path(r) for r in args.run], perf_from=Path(args.perf_from) if args.perf_from else None,
                      tests=Path(args.tests) if args.tests and Path(args.tests).exists() else None, extras=extras,
                      judge=Path(args.judge) if args.judge and Path(args.judge).exists() else None)
    except ValueError as e:
        print(e)
        return 2
    print(f"wrote {len(pages)} pages to {args.out}/ (open {args.out}/index.html)")
    return 0


def regress(args: argparse.Namespace) -> int:
    from pathlib import Path

    from breakwater import backtest as bt
    from breakwater.backends import get_backend

    only = args.only.split(",") if args.only else None
    adj = Path(args.adjudication) if args.adjudication else None
    summary = bt.regress_run(Path(args.backtest), adj, get_backend(args.backend), only=only, out_dir=Path(args.out),
                             workers=args.workers)
    print(json.dumps({k: v for k, v in summary.items() if k != "unverified"}, indent=2))
    for u in summary["unverified"]:
        print(f"  unverified: {u['signature'][:70]} (base {u['base']}, head {u['head']})")
    print(f"wrote {args.out}/")
    return 0


def bill(args: argparse.Namespace) -> int:
    names = [args.provider] if args.provider else ledger.providers(run_id=args.run_id)
    if not names:
        print("ledger is empty")
        return 0
    for name in names:
        totals = ledger.summarize(run_id=args.run_id, provider=name)
        grand = 0.0
        print(f"[{name}]")
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
    sub.add_parser("doctor", help="check keys, Docker, Sandboxes auth and limits").set_defaults(fn=doctor)
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
    p.add_argument("--backend", default=default_backend())
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
    a.add_argument("--mode", choices=("semantic", "perf", "both"), default="both")
    a.add_argument("--families", type=int, default=6, help="perf families to plan")
    a.add_argument("--no-archive", action="store_true", help="ignore and do not update the perf family archive")
    a.add_argument("--no-adjudicate", action="store_true", help="skip labelling divergences (likely-bug/intended/...)")
    a.add_argument("--title", help="PR title, given to the adjudicator as a statement of intent")
    a.add_argument("--live", action="store_true", help="serve a live view of the run on localhost while it runs")
    a.add_argument("--open", action="store_true", help="with --live: open the live view in a browser")
    a.add_argument("--port", type=int, default=8766, help="with --live: port (default 8766)")
    a.add_argument("--backend", default=default_backend())
    a.add_argument("--out", help="output dir (default artifacts/runs/<run_id>)")
    a.set_defaults(fn=audit)
    r = sub.add_parser("replay", help="replay a recorded audit in the live page at a stated speed")
    r.add_argument("run", help="audit run dir (with events.jsonl)")
    r.add_argument("--speed", type=float, default=4.0, help="playback speed; shown on the page (default 4x)")
    r.add_argument("--delay", type=float, default=3.0, help="seconds before playback starts")
    r.add_argument("--port", type=int, default=8767)
    r.add_argument("--open", action="store_true")
    r.add_argument("--out", help="where to write the replay (default <run>/replay)")
    r.set_defaults(fn=replay)
    t = sub.add_parser("backtest", help="run arms (baselines + Breakwater) over a corpus of merged perf PRs")
    t.add_argument("corpus")
    t.add_argument("--only", help="comma list of item ids or PR numbers")
    t.add_argument("--arms", help="comma list, default hypothesis,mutations,llm-plan,breakwater")
    t.add_argument("--perf", action="store_true", help="also run the perf audit per target")
    t.add_argument("--workers", type=int, default=3, help="items in parallel")
    t.add_argument("--seed", type=int, default=0)
    t.add_argument("--backend", default=default_backend())
    t.add_argument("--out")
    t.set_defaults(fn=backtest)
    j = sub.add_parser("adjudicate", help="label a finished backtest's divergences and score them against known issues")
    j.add_argument("backtest", help="backtest output dir (with results.json)")
    j.add_argument("--only", help="comma list of item ids or PR numbers")
    j.add_argument("--workers", type=int, default=3)
    j.add_argument("--backend", default=default_backend())
    j.add_argument("--out", help="output dir (default artifacts/adjudication/<time>-<provider>)")
    j.set_defaults(fn=adjudicate)
    g = sub.add_parser("regress", help="one verified pytest per finding class of a finished backtest (no model calls)")
    g.add_argument("backtest", nargs="?", default="artifacts/backtest/packaging-v3")
    g.add_argument("--adjudication", default="artifacts/adjudication/packaging-v3",
                   help="labels; classes adjudicated intended get no test ('' to ignore)")
    g.add_argument("--only")
    g.add_argument("--workers", type=int, default=3)
    g.add_argument("--backend", default=default_backend())
    g.add_argument("--out", default="artifacts/regress/packaging-v3")
    g.set_defaults(fn=regress)
    w = sub.add_parser("site", help="build the static web report from backtest + adjudication JSON")
    w.add_argument("--backtest", default="artifacts/backtest/packaging-v3")
    w.add_argument("--adjudication", default="artifacts/adjudication/packaging-v3")
    w.add_argument("--perf-from", default="artifacts/backtest/packaging-v2",
                   help="backtest whose perf results fill targets without perf ('' to disable)")
    w.add_argument("--out", default="site")
    w.add_argument("--allow-dev", action="store_true", help="allow non-Token-Factory inputs (pages get a dev banner)")
    w.add_argument("--run", action="append", default=[], help="audit run dir to include (repeatable)")
    w.add_argument("--tests", default="artifacts/regress/packaging-v3",
                   help="`breakwater regress` output to show on cards ('' to disable)")
    w.add_argument("--judge", default="artifacts/judge/packaging-1082.json",
                   help="judge-box bundle (scripts/site/build_judge_bundle.py); '' to leave the page out")
    w.add_argument("--extra", action="append", default=None, metavar="NAME:BACKTEST[:ADJUDICATION[:TESTS]]",
                   help="another corpus as a sub-site (default: codeflash, if its results exist)")
    w.add_argument("--compare", action="append", default=None, metavar="NAME:BACKTEST[:ADJUDICATION[:TESTS]]",
                   help="items of --backtest re-run on another backend, as an item-by-item comparison sub-site "
                        "(default: sandboxes, if artifacts/backtest/packaging-v4-sandboxes exists)")
    w.set_defaults(fn=site)
    b = sub.add_parser("bill", help="Token Factory spend by tier, from the ledger")
    b.add_argument("--run-id")
    b.add_argument("--provider", help="tokenfactory or openrouter (default: each provider in the ledger)")
    b.set_defaults(fn=bill)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
