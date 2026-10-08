"""Backtest: run Breakwater and no-LLM baselines over a corpus of merged perf PRs.

Arms per target (all share one image and the same deterministic probes):
  hypothesis   plain Hypothesis `st.text()` search (no LLM): the free baseline
  mutations    string literals harvested from the PR's own test file at base, plus mutate.py
               mutations of them, through probes P1-P4 (no LLM)
  llm-plan     Ultra's planned example inputs only, through the probes (no search, no mutations)
  breakwater   the full semantic audit: plan + Lightning strategies + search + mutations + probes
Perf (optional) runs the full perf audit per target.

A known issue counts as caught by an arm if any finding class matches its probe, detail and input
traits. The PR's own tests and benchmarks catch 0 by construction (these PRs merged green).
"""

from __future__ import annotations

import ast
import concurrent.futures as cf
import json
import random
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from breakwater import adversary, ledger, perf
from breakwater.backends import Backend
from breakwater.images import build_pair, git_req
from breakwater.llm import Nemotron
from breakwater.mutate import mutate_args
from breakwater.probes import ALL_PROBES, Runner, Target, run_probes
from breakwater.repo import _git, checkout, gather

ARMS = ("hypothesis", "mutations", "llm-plan", "breakwater")
HARVEST_LIMIT = 80


def parse_signature(sig: str) -> dict[str, Any]:
    parts = sig.split("|")
    return {"probe": parts[0], "detail": parts[1], "traits": set(parts[-1].split("+"))}


def matches(sig: str, rule: dict) -> bool:
    s = parse_signature(sig)
    if s["probe"] != rule["probe"]:
        return False
    if "detail" in rule and s["detail"] != rule["detail"]:
        return False
    return "traits" not in rule or rule["traits"] in s["traits"]


def harvest_literals(repo: str, ref: str, module: str, limit: int = HARVEST_LIMIT) -> list[str]:
    """String constants from the tests for `module` at `ref` (tests/test_<name>.py): the inputs the
    project already thought of. No LLM involved."""
    path = checkout(repo)
    name = module.rsplit(".", 1)[-1]
    files = [f for f in _git(path, "ls-tree", "-r", "--name-only", ref).splitlines()
             if f.startswith("tests/") and f.endswith(f"test_{name}.py")]
    seen: dict[str, None] = {}
    for f in files:
        try:
            tree = ast.parse(_git(path, "show", f"{ref}:{f}"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and 0 < len(node.value) <= 60:
                seen.setdefault(node.value, None)
    lits = list(seen)
    random.Random(0).shuffle(lits)
    return lits[:limit]


def literal_args(lits: list[str], arg_kinds: list[str]) -> list[list[Any]]:
    """Deterministic argument lists for any arity from a pool of literals."""
    if not lits:
        return []
    out = []
    for i, first in enumerate(lits):
        args: list[Any] = [first]
        for j, kind in enumerate(arg_kinds[1:], start=1):
            other = lits[(i * 7 + j * 13) % len(lits)]
            args.append([other, lits[(i * 3 + j) % len(lits)]] if kind.startswith("list") else other)
        out.append(args)
    return out


def generic_strategy(arg_kinds: list[str]) -> str:
    parts = ["st.lists(st.text(max_size=20), max_size=4)" if k.startswith("list") else "st.text(max_size=30)"
             for k in arg_kinds]
    return f"strategy = {parts[0]}" if len(parts) == 1 else f"strategy = st.tuples({', '.join(parts)})"


@dataclass
class ArmResult:
    classes: list[str] = field(default_factory=list)
    known: list[str] = field(default_factory=list)
    seconds: float = 0.0
    error: str | None = None


def _classes_from_probes(report) -> list[str]:
    return sorted(report.classes())


def run_target(item: dict, tgt: dict, repo: str, backend: Backend, *, arms: tuple[str, ...], do_perf: bool,
               seed: int, log) -> dict:
    run_id = f"bt-{item['id'].strip('#').replace('@', '-')}-{uuid.uuid4().hex[:6]}"
    llm = Nemotron(run_id=run_id)
    target = Target(tgt["callable"], tuple(tgt["observe"]))
    arg_kinds = tgt.get("arg_kinds", ["str"])
    ctx = gather(repo, item["base"], item["head"], tgt["callable"])
    image = build_pair(git_req(repo, item["base"]), git_req(repo, item["head"]))
    results: dict[str, ArmResult] = {}

    def timed(name: str, fn) -> None:
        if name not in arms:
            return
        t0 = time.perf_counter()
        try:
            results[name] = ArmResult(classes=fn())
        except Exception as e:  # noqa: BLE001 - one broken arm must not sink the item
            results[name] = ArmResult(error=f"{type(e).__name__}: {str(e)[:300]}")
        results[name].seconds = round(time.perf_counter() - t0, 1)

    def arm_hypothesis() -> list[str]:
        res = adversary.run_strategy(backend, image, target, generic_strategy(arg_kinds), seed=seed, max_examples=600)
        if res.get("error"):
            raise RuntimeError(res["error"])
        cls = {f["signature"] for f in res["findings"]}
        if res.get("samples"):
            cls |= set(run_probes(Runner(backend, image, target), res["samples"][:120], ALL_PROBES).classes())
        return sorted(cls)

    lits = harvest_literals(repo, item["base"], tgt["callable"].split(":")[0])

    def arm_mutations() -> list[str]:
        seeds = literal_args(lits, arg_kinds)
        batch = seeds + [a for _, a in mutate_args(seeds, limit=adversary.MUTATION_LIMIT)]
        return _classes_from_probes(run_probes(Runner(backend, image, target), batch[: adversary.BATCH_LIMIT], ALL_PROBES))

    full: dict[str, Any] = {}

    def arm_breakwater() -> list[str]:
        rep = adversary.audit(ctx, image, llm, backend, target, seed=seed, run_id=run_id,
                              extra_seeds=literal_args(lits, arg_kinds), log=lambda *_: None)
        full["report"] = rep
        return sorted(f.signature for f in rep.findings)

    def arm_llm_plan() -> list[str]:
        rep = full.get("report")
        seeds = [a for att in rep.attacks for a in att.example_args] if rep else []
        if not seeds:
            return []
        return _classes_from_probes(run_probes(Runner(backend, image, target), seeds, ALL_PROBES))

    timed("hypothesis", arm_hypothesis)
    timed("mutations", arm_mutations)
    timed("breakwater", arm_breakwater)
    timed("llm-plan", arm_llm_plan)  # reuses the full audit's plan: no extra model calls

    for res in results.values():
        res.known = [k["id"] for k in item["known"] if any(matches(c, k["match"]) for c in res.classes)]

    perf_summary = None
    if do_perf:
        try:
            pr = perf.perf_audit(ctx, image, llm, backend, target, run_id=run_id, seed=seed, log=lambda *_: None)
            realistic = [f for f in pr.findings if (f.valid_fraction or 0) >= 0.5]
            slower = [f for f in realistic if f.verdict in ("slower", "complexity-regression")]
            worst = max(slower, key=lambda f: max(f.ladder_ratios or [0]), default=None)
            speed = [f for f in realistic if f.kind == "claimed_speedup" and f.ladder_ratios]
            perf_summary = {
                "slower_families": [{"id": f.family_id, "family": f.family, "verdict": f.verdict,
                                     "ladder": f.ladder_ratios, "origin": f.origin} for f in slower],
                "worst_valid_ratio": max(worst.ladder_ratios) if worst else None,
                "worst_family": worst.family if worst else None,
                "speedup_ratio_small": min(speed[0].ladder_ratios) if speed else None,
                "report": pr.to_json(),
            }
        except Exception as e:  # noqa: BLE001
            perf_summary = {"error": f"{type(e).__name__}: {str(e)[:300]}"}

    usd = sum(t["usd"] for t in ledger.summarize(run_id=run_id).values())
    full_rep = full.get("report")
    out = {
        "target": tgt["callable"], "run_id": run_id, "image": image.ref, "usd": round(usd, 4), "harvested": len(lits),
        "arms": {k: vars(v) for k, v in results.items()},
        "findings": [vars(f) for f in full_rep.findings] if full_rep else [],
        "perf": perf_summary,
    }
    known = {a: v.known for a, v in results.items()}
    log(f"{item['id']:>15s} {tgt['callable'].split(':')[1]:28s} classes "
        + " ".join(f"{a}={len(v.classes)}" for a, v in results.items())
        + f" known {known} ${usd:.3f}"
        + (f" perf worst {perf_summary.get('worst_valid_ratio')}" if perf_summary else ""))
    return out


def run(corpus_path: str, backend: Backend, *, only: list[str] | None, arms: tuple[str, ...], do_perf: bool,
        seed: int, workers: int, out_dir: Path, log=print) -> dict:
    corpus = json.loads(Path(corpus_path).read_text())
    items = [it for it in corpus["items"] if not only or it["id"] in only or str(it["pr"]) in only]
    out_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []

    def one(item: dict) -> dict:
        targets = [run_target(item, t, corpus["repo"], backend, arms=arms, do_perf=do_perf, seed=seed, log=log)
                   for t in item["targets"]]
        res = {**{k: item[k] for k in ("id", "pr", "title", "base", "head", "merged", "after_ultra_release", "known")},
               "targets": targets}
        (out_dir / f"{item['id'].strip('#').replace('@', '-')}.json").write_text(
            json.dumps(res, indent=2, ensure_ascii=False, default=str))
        return res

    with cf.ThreadPoolExecutor(max_workers=workers) as pool:
        for fut in cf.as_completed([pool.submit(one, it) for it in items]):
            results.append(fut.result())
    results.sort(key=lambda r: (r["pr"], r["id"]))
    summary = summarize(results, arms)
    (out_dir / "results.json").write_text(json.dumps({"corpus": corpus_path, "arms": arms, "items": results,
                                                       "summary": summary}, indent=2, ensure_ascii=False, default=str))
    (out_dir / "table.md").write_text(render(results, arms, summary))
    return summary


def summarize(results: list[dict], arms: tuple[str, ...]) -> dict:
    known = [(r["id"], k) for r in results for k in r["known"]]
    verified = [(i, k) for i, k in known if k["status"] == "verified"]

    def caught(arm: str, subset) -> int:
        n = 0
        for item_id, k in subset:
            r = next(x for x in results if x["id"] == item_id)
            if any(k["id"] in t["arms"].get(arm, {}).get("known", []) for t in r["targets"]):
                n += 1
        return n

    return {
        "items": len(results),
        "known_verified": len(verified),
        "known_candidate": len(known) - len(verified),
        "caught_verified": {a: caught(a, verified) for a in arms},
        "caught_candidate": {a: caught(a, [x for x in known if x[1]["status"] != "verified"]) for a in arms},
        "items_with_classes": {a: sum(any(t["arms"].get(a, {}).get("classes") for t in r["targets"]) for r in results)
                               for a in arms},
        "usd": round(sum(t["usd"] for r in results for t in r["targets"]), 4),
        "perf_items_slower": sum(any((t.get("perf") or {}).get("worst_valid_ratio") for t in r["targets"]) for r in results),
    }


def render(results: list[dict], arms: tuple[str, ...], s: dict) -> str:
    lines = [
        "# Breakwater backtest", "",
        f"{s['items']} items · verified known issues {s['known_verified']} · candidates {s['known_candidate']} · "
        f"total Nemotron cost ${s['usd']:.2f}", "",
        "| arm | verified known caught | candidate known caught | items with any divergence |",
        "|---|---|---|---|",
        f"| PR's own tests + benchmarks | 0/{s['known_verified']} (by construction) | 0 | 0 |",
    ]
    for a in arms:
        lines.append(f"| {a} | {s['caught_verified'][a]}/{s['known_verified']} | "
                     f"{s['caught_candidate'][a]}/{s['known_candidate']} | {s['items_with_classes'][a]}/{s['items']} |")
    lines += ["", "| item | merged | target | " + " | ".join(arms) + " | known caught (breakwater) | perf: worst valid family | $ |",
              "|---|---|---|" + "---|" * len(arms) + "---|---|---|"]
    for r in results:
        for t in r["targets"]:
            cells = " | ".join(str(len(t["arms"].get(a, {}).get("classes", []))) if not t["arms"].get(a, {}).get("error")
                               else "err" for a in arms)
            known = ", ".join(t["arms"].get("breakwater", {}).get("known", [])) or ("–" if not r["known"] else "none")
            p = t.get("perf") or {}
            worst = (f"{p['worst_valid_ratio']:.2f}x {p['worst_family'][:40]}" if p.get("worst_valid_ratio")
                     else ("err" if p.get("error") else "–"))
            late = " †" if r["after_ultra_release"] else ""
            lines.append(f"| {r['id']}{late} | {r['merged']} | `{t['target'].split(':')[1]}` | {cells} | {known} | {worst} | "
                         f"{t['usd']:.3f} |")
    lines += ["", "Cells are distinct divergence classes per arm. † merged after Nemotron 3 Ultra's release (2026-06-04)."]
    return "\n".join(lines)
