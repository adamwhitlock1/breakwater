"""Adversary v1: Nemotron plans attacks, writes Hypothesis strategies, and the sandbox searches.

  1. Plan       Ultra (reasoning on) reads the diff + module white-box and names the assumptions the
                change makes, with an input family and example arguments for each.
  2. Generate   Lightning (reasoning off) writes several Hypothesis strategies per attack.
  3. Search     each strategy runs in the sandbox (harness/diffrun.py): Hypothesis looks for inputs
                where base and head disagree, then shrinks them to minimal counterexamples.
  4. Batch      the planner's example args plus inputs sampled during search go through all probes
                (P1-P4), which covers relations and pickling that per-example search does not.
  5. Dedupe     findings are grouped by signature; each class keeps its smallest input.

The planner never sees tests, PR discussion or which bug (if any) is known to exist.
Adjudication (likely-bug / intended / needs-human) and perf attacks come in v2.
"""

from __future__ import annotations

import ast
import concurrent.futures as cf
import json
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

from breakwater import ledger
from breakwater.backends import Backend
from breakwater.images import PairImage
from breakwater.models import Tier
from breakwater.probes import ALL_PROBES, Runner, Target, run_probes
from breakwater.repo import Context

# ---------------------------------------------------------------------------------------------------
# Prompts

PLAN_SYSTEM = """\
You review performance-motivated code changes for unintended behavior changes.

The change claims to make code faster WITHOUT changing behavior. Your job is to find inputs for \
which the new version (head) and the old version (base) give different results: a different return \
value or string form, a different exception type, different equality / ordering / hashing between \
objects, or objects that no longer survive pickling from the old version.

Work from the diff. Only inputs that reach changed code can behave differently, so:
1. Find the condition that routes an input into the new or changed code (e.g. a fast-path guard).
2. For inputs that satisfy it, compare what the new code does with what the old code (the unchanged \
   path elsewhere in the module) did for the same input. Look for every input the new path accepts, \
   rejects or transforms differently: character classes the guard lets through (Unicode digits, \
   whitespace, signs, underscores), Python builtins that behave differently from the old parser \
   (int() and float() accept Unicode digits, surrounding whitespace and underscores; int() raises \
   ValueError for strings over 4,300 digits; str.split, str.strip), normalization, cached or \
   lazily computed state, container types, ordering and de-duplication.
3. Invalid inputs count: raising a different exception, or accepting what was rejected, is a \
   behavior change.

Only list hypotheses where you expect base and head to DIFFER; if you find fewer, list fewer. Do \
not report slowness or resource exhaustion; that is analysed separately. Be concrete and brief."""

PLAN_USER = """\
Target under test: `{target}` (called with positional arguments).
Observed for each result: {observe}.

## Full head version of {module_path} (context)
```python
{source}
```

## The change under review (base -> head, tests and docs excluded)
```diff
{diff}
```

Return JSON with up to {n} hypotheses, most likely first. For each: the routing condition that \
sends inputs into the changed code, the base behavior and head behavior you expect, the input \
family, and `example_args_json`: 2-5 strings, each a JSON array of positional arguments for \
`{target}`, for example "[\\"1.0\\"]"."""

PLAN_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "attack_plan",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "attacks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "routing_condition": {"type": "string"},
                            "assumption": {"type": "string"},
                            "why_it_breaks": {"type": "string", "description": "base behavior vs head behavior"},
                            "input_family": {"type": "string"},
                            "example_args_json": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["id", "routing_condition", "assumption", "why_it_breaks", "input_family",
                                         "example_args_json"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["attacks"],
            "additionalProperties": False,
        },
    },
}

STRATEGY_SYSTEM = """\
You write Hypothesis strategies for differential testing of two versions of a Python function.

Output exactly one Python code block that assigns `strategy`. Available names: `st` \
(hypothesis.strategies) and `string` (the stdlib module). No imports and no other names. The \
strategy generates the positional arguments for the target: a single value for one argument, or a \
tuple for several. Values must be JSON-serializable (str, int, float, bool, None, lists). Aim \
squarely at the attack's input family but include variety (lengths, positions, combinations with \
otherwise-valid input) so the search can explore. At most 25 lines."""

STRATEGY_USER = """\
Target: `{target}`
Attack {id}: {assumption}
Why it may break: {why}
Input family to generate: {family}
Example arguments: {examples}

Relevant diff:
```diff
{diff}
```"""

# ---------------------------------------------------------------------------------------------------
# Data


@dataclass
class Attack:
    id: str
    routing_condition: str
    assumption: str
    why_it_breaks: str
    input_family: str
    example_args: list[list[Any]]


@dataclass
class Finding:
    signature: str
    probe: str
    detail: str
    args: list[Any]  # smallest input seen for this class (P3: a pair of argument lists)
    base: Any
    head: Any
    found_by: list[str] = field(default_factory=list)  # "A1/s2" strategy ids, "seed", "batch"


@dataclass
class StrategyRun:
    id: str
    attack: str
    valid: bool
    error: str | None = None
    examples: int = 0
    findings: int = 0
    source: str = ""


@dataclass
class AuditReport:
    run_id: str
    repo: str
    base: str
    head: str
    target: str
    image: str
    backend: str
    attacks: list[Attack]
    strategies: list[StrategyRun]
    findings: list[Finding]
    usd_by_tier: dict[str, float]
    seconds: dict[str, float]

    def to_json(self) -> dict:
        return asdict(self)


class LLM(Protocol):
    def complete(self, tier: Tier, messages: list[dict[str, str]], **kw: Any) -> Any: ...


# ---------------------------------------------------------------------------------------------------
# Helpers


def extract_json(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise
        return json.loads(text[start : end + 1])


_CODE = re.compile(r"```(?:python)?\s*\n(.*?)```", re.DOTALL)
_BANNED_NAMES = {"eval", "exec", "open", "compile", "__import__", "getattr", "setattr", "delattr",
                 "globals", "locals", "vars", "input", "breakpoint", "exit", "quit"}


def extract_code(text: str) -> str:
    m = _CODE.search(text)
    return (m.group(1) if m else text).strip()


def validate_strategy(src: str) -> str | None:
    """Hygiene check before sending code to the sandbox. Returns an error string, or None if OK.
    This is not the security boundary (the sandbox is); it rejects obviously off-task code early."""
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return f"syntax error: {e.msg} (line {e.lineno})"
    assigns = False
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            return "imports are not allowed"
        if isinstance(node, ast.Name):
            if node.id.startswith("__") or node.id in _BANNED_NAMES:
                return f"name {node.id!r} is not allowed"
            if node.id == "strategy" and isinstance(node.ctx, ast.Store):
                assigns = True
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            return f"attribute {node.attr!r} is not allowed"
    return None if assigns else "code must assign `strategy`"


def _parse_args(items: list[str]) -> list[list[Any]]:
    out = []
    for s in items:
        try:
            v = json.loads(s)
        except (json.JSONDecodeError, TypeError):
            continue
        out.append(v if isinstance(v, list) else [v])
    return out


def _size(args: Any) -> int:
    return len(json.dumps(args, ensure_ascii=False))


# ---------------------------------------------------------------------------------------------------
# Steps


PLAN_SAMPLES = 2  # independent plans per call; their attacks are interleaved
PLAN_REASONING = {"medium_effort": True}  # day 1: ~2.3k reasoning tokens vs ~4.7k regular, and it found the bug


def plan_attacks(llm: LLM, ctx: Context, observe: tuple[str, ...], n: int = 5) -> list[Attack]:
    """Ultra, reasoning on (medium effort), structured output. Never falls back to reasoning off:
    on 2026-10-08 that fallback produced a plan that ignored the diff entirely."""
    messages = [
        {"role": "system", "content": PLAN_SYSTEM},
        {"role": "user", "content": PLAN_USER.format(
            target=ctx.target, observe=", ".join(observe), diff=ctx.diff, module_path=ctx.module_path,
            source=ctx.module_source, n=n)},
    ]
    common = dict(thinking=True, template_kwargs=PLAN_REASONING, max_tokens=32000, fallback_no_think=False)
    plans: list[list[dict]] = []
    for text in llm.complete(Tier.REASONING, messages, purpose="plan", n=PLAN_SAMPLES,
                             response_format=PLAN_SCHEMA, **common).texts:
        try:
            plans.append(extract_json(text).get("attacks", []))
        except (json.JSONDecodeError, AttributeError):
            continue
    if not plans:  # structured output failed or reasoning truncated: one plain-JSON retry, reasoning still on
        retry = messages + [{"role": "user", "content": 'Reply with only a JSON object {"attacks": [...]}.'}]
        for text in llm.complete(Tier.REASONING, retry, purpose="plan:retry", **common).texts:
            try:
                plans.append(extract_json(text).get("attacks", []))
            except (json.JSONDecodeError, AttributeError):
                continue

    # Interleave: first attack of each plan, then the second of each, and so on.
    merged: list[dict] = []
    for rank in range(max((len(p) for p in plans), default=0)):
        merged += [p[rank] for p in plans if rank < len(p)]
    attacks = []
    for i, a in enumerate(merged[:n]):
        attacks.append(Attack(f"A{i + 1}", a.get("routing_condition", ""), a.get("assumption", ""),
                              a.get("why_it_breaks", ""), a.get("input_family", ""),
                              _parse_args(a.get("example_args_json", []))))
    return attacks


def write_strategies(llm: LLM, ctx: Context, attack: Attack, n: int) -> list[str]:
    messages = [
        {"role": "system", "content": STRATEGY_SYSTEM},
        {"role": "user", "content": STRATEGY_USER.format(
            target=ctx.target, id=attack.id, assumption=attack.assumption, why=attack.why_it_breaks,
            family=attack.input_family, examples=json.dumps(attack.example_args, ensure_ascii=False),
            diff=ctx.diff[:6000])},
    ]
    texts = llm.complete(Tier.VOLUME, messages, purpose=f"strategy:{attack.id}", thinking=False,
                         max_tokens=1200, n=n).texts
    return [extract_code(t) for t in texts[:n]]


def run_strategy(backend: Backend, image: PairImage, target: Target, src: str, *, seed: int,
                 max_examples: int, max_classes: int = 3) -> dict:
    req = {"strategy": src, "target": target.callable, "observe": list(target.observe), "seed": seed,
           "max_examples": max_examples, "max_classes": max_classes,
           "base_py": image.BASE_PY, "head_py": image.HEAD_PY}
    res = backend.run(image.ref, [image.SYS_PY, image.DIFFRUN], stdin=json.dumps(req), timeout_s=900)
    if res.exit_code != 0:
        return {"findings": [], "samples": [], "examples": 0, "error": f"exit {res.exit_code}: {res.stderr[-400:]}"}
    return json.loads(res.stdout)


# ---------------------------------------------------------------------------------------------------
# Orchestration


def audit(ctx: Context, image: PairImage, llm: LLM, backend: Backend, target: Target, *,
          n_attacks: int = 5, strategies_per_attack: int = 4, max_examples: int = 300, seed: int = 0,
          run_id: str | None = None, workers: int = 4, log=print) -> AuditReport:
    run_id = run_id or uuid.uuid4().hex[:12]
    timings: dict[str, float] = {}
    t0 = time.perf_counter()

    attacks = plan_attacks(llm, ctx, target.observe, n_attacks)
    timings["plan"] = time.perf_counter() - t0
    log(f"plan: {len(attacks)} attacks ({timings['plan']:.1f}s)")
    for a in attacks:
        log(f"  {a.id}: {a.assumption[:110]}")

    t1 = time.perf_counter()
    jobs: list[StrategyRun] = []
    for a in attacks:
        for i, src in enumerate(write_strategies(llm, ctx, a, strategies_per_attack)):
            err = validate_strategy(src)
            jobs.append(StrategyRun(f"{a.id}/s{i + 1}", a.id, err is None, err, source=src))
    timings["generate"] = time.perf_counter() - t1
    log(f"generate: {sum(j.valid for j in jobs)}/{len(jobs)} strategies valid ({timings['generate']:.1f}s)")

    t2 = time.perf_counter()
    classes: dict[str, Finding] = {}
    samples: list[list[Any]] = []

    def record(sig: str, probe: str, detail: str, args: Any, base: Any, head: Any, by: str) -> None:
        f = classes.get(sig)
        if f is None:
            classes[sig] = Finding(sig, probe, detail, args, base, head, [by])
            return
        if by not in f.found_by:
            f.found_by.append(by)
        if _size(args) < _size(f.args):
            f.args, f.base, f.head = args, base, head

    valid = [j for j in jobs if j.valid]
    with cf.ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(run_strategy, backend, image, target, j.source, seed=seed + k,
                            max_examples=max_examples): j for k, j in enumerate(valid)}
        for fut in cf.as_completed(futs):
            j = futs[fut]
            res = fut.result()
            j.error, j.examples, j.findings = res.get("error"), res.get("examples", 0), len(res.get("findings", []))
            for f in res.get("findings", []):
                record(f["signature"], f["probe"], f["detail"], [f["args"]], f["base"], f["head"], j.id)
            samples.extend(res.get("samples", []))
    timings["search"] = time.perf_counter() - t2
    log(f"search: {sum(j.examples for j in valid)} examples, {len(classes)} classes ({timings['search']:.1f}s)")

    t3 = time.perf_counter()
    seeds = [args for a in attacks for args in a.example_args]
    seen: set[str] = set()
    batch: list[list[Any]] = []
    for args in seeds + samples:
        key = json.dumps(args, ensure_ascii=False, sort_keys=True)
        if key not in seen:
            seen.add(key)
            batch.append(args)
    batch = batch[:200]
    seed_keys = {json.dumps(a, ensure_ascii=False, sort_keys=True) for a in seeds}
    if batch:
        report = run_probes(Runner(backend, image, target), batch, ALL_PROBES)
        for d in report.divergences:
            by = "seed" if any(json.dumps(x, ensure_ascii=False, sort_keys=True) in seed_keys for x in d.inputs) else "batch"
            record(d.signature(), d.probe, d.detail, d.inputs, d.base, d.head, by)
    timings["batch"] = time.perf_counter() - t3
    timings["total"] = time.perf_counter() - t0
    log(f"batch probes: {len(batch)} inputs ({timings['batch']:.1f}s); total {len(classes)} classes")

    usd = {tier: t["usd"] for tier, t in ledger.summarize(run_id=run_id).items()}
    findings = sorted(classes.values(), key=lambda f: (f.probe, f.detail))
    return AuditReport(run_id, ctx.repo, ctx.base, ctx.head, ctx.target, image.ref, backend.name,
                       attacks, jobs, findings, usd, {k: round(v, 2) for k, v in timings.items()})


def render_markdown(r: AuditReport) -> str:
    lines = [
        f"## Breakwater audit: `{r.target}`",
        f"{r.repo} `{r.base[:10]}` → `{r.head[:10]}` · backend `{r.backend}` · image `{r.image}` · run `{r.run_id}`",
        "",
        f"**{len(r.findings)} behavior divergence class(es)** (unadjudicated).",
        "",
    ]
    for f in r.findings:
        args = json.dumps(f.args, ensure_ascii=False)
        args = args if len(args) <= 120 else args[:100] + f"… ({len(args)} chars)"
        lines += [
            f"- **[{f.probe}] {f.detail}**: input `{args}`",
            f"  - base: `{json.dumps(f.base, ensure_ascii=False)[:160]}`",
            f"  - head: `{json.dumps(f.head, ensure_ascii=False)[:160]}`",
            f"  - found by: {', '.join(f.found_by)}",
        ]
    lines += ["", "### Attacks planned"]
    for a in r.attacks:
        ran = [s for s in r.strategies if s.attack == a.id]
        hits = sum(s.findings for s in ran)
        lines.append(f"- **{a.id}** ({sum(s.valid for s in ran)}/{len(ran)} strategies valid, {hits} hits): {a.assumption}")
    total = sum(r.usd_by_tier.values())
    tiers = ", ".join(f"{k} ${v:.4f}" for k, v in sorted(r.usd_by_tier.items()))
    lines += ["", f"**Cost:** ${total:.4f} ({tiers or 'no model calls logged'}) · **Time:** {r.seconds.get('total', 0):.0f}s"]
    return "\n".join(lines)
