"""Adversary v1: Nemotron plans attacks, writes Hypothesis strategies, and the sandbox searches.

  1. Plan       Ultra (reasoning on) reads the diff + module white-box and names the assumptions the
                change makes, with an input family and example arguments for each.
  2. Generate   Lightning (reasoning off) writes several Hypothesis strategies per attack.
  3. Search     each strategy runs in the sandbox (harness/diffrun.py): Hypothesis looks for inputs
                where base and head disagree, then shrinks them to minimal counterexamples.
  4. Batch      the planner's example args, deterministic hostile mutations of them (mutate.py) and
                inputs sampled during search go through all probes (P1-P4). Mutations give a floor of
                coverage when a plan is weak; probes cover relations and pickling.
  5. Dedupe     findings are grouped by signature; each class keeps its smallest input.

The planner never sees tests, PR discussion or which bug (if any) is known to exist.
Adjudication (likely-bug / intended / needs-human) is adjudicate.py; perf attacks are perf.py.
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
from breakwater.display import card_text, sources
from breakwater.events import NULL, Events
from breakwater.images import PairImage
from breakwater.models import Tier
from breakwater.mutate import equivalents, mutate_args
from breakwater.probes import ALL_PROBES, Runner, Target, run_probes
from breakwater.repo import Context

# ---------------------------------------------------------------------------------------------------
# Prompts

PLAN_SYSTEM = """\
You attack performance-motivated code changes. The change claims to make code faster WITHOUT \
changing behavior; your job is to find inputs where the new version (head) and the old version \
(base) behave differently: a different return value or string form, a different exception type, \
accepting what was rejected (or the reverse), different equality / ordering / hashing, or objects \
pickled by base that no longer load or compare on head.

Method:
1. Find the condition that routes an input into the new or changed code (e.g. a fast-path guard).
2. List the assumptions the new code makes about inputs that pass that condition, and check each \
   against what the old code did for the same input. Typical false assumptions: that a guard on a \
   few characters implies a well-formed input; that int() / float() / str.split / str.strip behave \
   like the old parser (int() accepts any Unicode decimal digit, surrounding whitespace and \
   underscores, and raises ValueError above 4,300 digits); that caching, normalization, container \
   types, ordering and de-duplication are unchanged.
3. For each assumption that is FALSE for some input, give that input.
4. Before you claim a difference, trace the OLD code on that exact input. The old code may already \
   accept, normalize or reject it the same way (e.g. a regex that allows surrounding whitespace or \
   leading zeros); if so, it is not a difference. Prefer inputs where you can name the line of old \
   code that behaves differently. Make the attacks cover different assumptions, not variants of one.

An attack is a concrete input for which you predict DIFFERENT behavior. Describing which code path \
an input takes, or explaining why some inputs behave the same, is not an attack: a plan that only \
maps the code paths is useless. If you conclude an idea gives identical behavior, mark it "no \
difference expected" (it will be discarded) and move on to inputs that break an assumption. Invalid \
inputs count: raising a different exception, or accepting what was rejected, is a behavior change. \
Do not report slowness; that is analysed separately. Be concrete and brief."""

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

Return JSON with up to {n} attacks, most likely to expose a difference first. For each: the false \
assumption (one sentence, e.g. "the fast path assumes int() only accepts ASCII digits"), how inputs \
reach the changed code, what base does and what head does for the example inputs, the kind of \
difference, the input family, and `example_args_json`: 2-5 strings, each a JSON array of positional \
arguments for `{target}`, for example "[\\"1.0\\"]". Examples must be inputs where you predict a \
difference, not ordinary inputs."""

DIFFERENCE_KINDS = ("accepts what base rejects", "rejects what base accepts", "different exception type",
                    "different value or string form", "different equality, ordering or hash",
                    "old pickles break", "no difference expected")
NO_DIFFERENCE = "no difference expected"

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
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "assumption": {"type": "string", "description": "the false assumption, one sentence"},
                            "routing_condition": {"type": "string", "description": "how inputs reach the changed code"},
                            "base_behavior": {"type": "string", "description": "what base does for the examples"},
                            "head_behavior": {"type": "string", "description": "what head does for the examples"},
                            "difference": {"type": "string", "enum": list(DIFFERENCE_KINDS)},
                            "input_family": {"type": "string"},
                            "example_args_json": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["id", "assumption", "routing_condition", "base_behavior", "head_behavior",
                                     "difference", "input_family", "example_args_json"],
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

MUTATION_LIMIT = 250
BATCH_LIMIT = 450
FOCUS_LIMIT = 60

# ---------------------------------------------------------------------------------------------------
# Data


@dataclass
class Attack:
    id: str
    routing_condition: str
    assumption: str
    why_it_breaks: str  # "base: ...; head: ..."
    input_family: str
    example_args: list[list[Any]]
    difference: str = ""  # one of DIFFERENCE_KINDS


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


def _parse_args(items: Any) -> list[list[Any]]:
    """Planner examples: a list of JSON-array strings, e.g. ['["1.0"]', '["1. 0"]']. Routes without
    structured output (schema in the prompt) sometimes return the whole list as ONE JSON string; it
    used to be iterated character by character, turning '["\\u0661"]' into the digits 0, 6, 6, 1."""
    loose = isinstance(items, str)
    if loose:
        try:
            items = json.loads(items)
        except json.JSONDecodeError:
            items = [items]
    if not isinstance(items, list):
        items = [items]
    out = []
    for s in items:
        if isinstance(s, list):
            out.append(s)
            continue
        if not isinstance(s, str):
            out.append([s])
            continue
        try:
            v = json.loads(s)
        except json.JSONDecodeError:
            if loose:  # a plain string inside a decoded list is the argument itself
                out.append([s])
            continue
        out.append(v if isinstance(v, list) else [v])
    return out


def _size(args: Any) -> int:
    return len(json.dumps(args, ensure_ascii=False))


# ---------------------------------------------------------------------------------------------------
# Steps


PLAN_SAMPLES = 3  # independent plans per call (the serverless n cap); attacks are interleaved
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

    # Attacks that predict no difference are path descriptions, not attacks: drop them before they
    # take a slot (on 2026-10-09 they were most of Ultra's plan for #1082).
    plans = [[a for a in p if isinstance(a, dict) and not _predicts_nothing(a)] for p in plans]
    # Interleave: first attack of each plan, then the second of each, and so on.
    merged: list[dict] = []
    for rank in range(max((len(p) for p in plans), default=0)):
        merged += [p[rank] for p in plans if rank < len(p)]
    attacks = []
    for i, a in enumerate(merged[:n]):
        why = a.get("why_it_breaks") or f"base: {a.get('base_behavior', '')}; head: {a.get('head_behavior', '')}"
        attacks.append(Attack(f"A{i + 1}", a.get("routing_condition", ""), a.get("assumption", ""), why,
                              a.get("input_family", ""), _parse_args(a.get("example_args_json", [])),
                              a.get("difference", "")))
    return attacks


def _predicts_nothing(a: dict) -> bool:
    if a.get("difference") == NO_DIFFERENCE:
        return True
    base, head = (" ".join(str(a.get(k, "")).lower().split()) for k in ("base_behavior", "head_behavior"))
    return bool(base) and base == head


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
          run_id: str | None = None, workers: int = 4, extra_seeds: list[list[Any]] | None = None,
          log=print, events: Events = NULL) -> AuditReport:
    """`extra_seeds`: inputs the project already has (e.g. string literals from its tests). They are
    mutated and probed alongside the planner's examples, so the full audit covers everything the
    no-LLM baseline does and the difference between them is what Nemotron adds."""
    run_id = run_id or uuid.uuid4().hex[:12]
    timings: dict[str, float] = {}
    t0 = time.perf_counter()

    fn = target.callable.split(":")[1].split("#")[0]
    events("phase", name="plan")
    attacks = plan_attacks(llm, ctx, target.observe, n_attacks)
    timings["plan"] = time.perf_counter() - t0
    events("plan", attacks=[{"id": a.id, "assumption": a.assumption, "why_it_breaks": a.why_it_breaks,
                             "input_family": a.input_family, "examples": a.example_args[:5]} for a in attacks])
    events("phase", name="generate")
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
    events("strategies", jobs=[{"id": j.id, "attack": j.attack, "valid": j.valid, "error": j.error,
                                "source": j.source[:1500]} for j in jobs])
    events("phase", name="search")
    log(f"generate: {sum(j.valid for j in jobs)}/{len(jobs)} strategies valid ({timings['generate']:.1f}s)")

    t2 = time.perf_counter()
    classes: dict[str, Finding] = {}
    samples: list[list[Any]] = []

    def record(sig: str, probe: str, detail: str, args: Any, base: Any, head: Any, by: str) -> None:
        f = classes.get(sig)
        if f is None:
            classes[sig] = Finding(sig, probe, detail, args, base, head, [by])
            events("finding", signature=sig, probe=probe, found_by=", ".join(sources([by])) or by,
                   **card_text(probe, detail, args, base, head, fn))
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
            events("strategy", id=j.id, examples=j.examples, findings=j.findings, error=j.error)
            samples.extend(res.get("samples", []))
    timings["search"] = time.perf_counter() - t2
    log(f"search: {sum(j.examples for j in valid)} examples, {len(classes)} classes ({timings['search']:.1f}s)")

    t3 = time.perf_counter()
    events("phase", name="batch")

    def key(args: Any) -> str:
        return json.dumps(args, ensure_ascii=False, sort_keys=True)

    planned = [args for a in attacks for args in a.example_args]
    origin: dict[str, str] = {key(a): "seed" for a in planned}
    for args in extra_seeds or []:
        origin.setdefault(key(args), "tests")
    seeds = planned + list(extra_seeds or [])
    mutants = mutate_args(seeds + samples[:20], limit=MUTATION_LIMIT)
    for name, args in mutants:
        origin.setdefault(key(args), f"mutation:{name}")
    batch: list[list[Any]] = []
    batch_keys: set[str] = set()
    for args in seeds + [a for _, a in mutants] + samples:
        if key(args) not in batch_keys:
            batch_keys.add(key(args))
            batch.append(args)
    batch = batch[:BATCH_LIMIT]
    if batch:
        report = run_probes(Runner(backend, image, target), batch, ALL_PROBES)
        for d in report.divergences:
            by = next((origin[key(x)] for x in d.inputs if key(x) in origin), "batch")
            record(d.signature(), d.probe, d.detail, d.inputs, d.base, d.head, by)
    # Focused relations pass: inputs already involved in a divergence, paired with the seeds. Relation
    # bugs (== / hash / ordering) need a specific partner, which the capped batch pass can miss.
    focus: list[list[Any]] = []
    focus_keys: set[str] = set()
    for f in list(classes.values()):
        for args in f.args:
            if isinstance(args, list) and key(args) not in focus_keys:
                focus_keys.add(key(args))
                focus.append(args)
    for args in seeds:
        for variant in [args] + [args[:i] + [e] + args[i + 1:] for i, a in enumerate(args) if isinstance(a, str)
                                 for e in equivalents(a)]:
            if key(variant) not in focus_keys:
                focus_keys.add(key(variant))
                focus.append(variant)
    focus = focus[:FOCUS_LIMIT]
    if len(focus) > 1:
        report = run_probes(Runner(backend, image, target), focus, ("P3",))
        for d in report.divergences:
            record(d.signature(), d.probe, d.detail, d.inputs, d.base, d.head, "focus")
    timings["batch"] = time.perf_counter() - t3
    timings["total"] = time.perf_counter() - t0
    log(f"batch probes: {len(batch)} inputs incl. {len(mutants)} mutations ({timings['batch']:.1f}s); "
        f"total {len(classes)} classes")
    events("batch", inputs=len(batch), mutations=len(mutants), focus=len(focus), classes=len(classes))

    usd = {tier: t["usd"] for tier, t in ledger.summarize(run_id=run_id).items()}
    findings = sorted(classes.values(), key=lambda f: (f.probe, f.detail))
    return AuditReport(run_id, ctx.repo, ctx.base, ctx.head, ctx.target, image.ref, backend.name,
                       attacks, jobs, findings, usd, {k: round(v, 2) for k, v in timings.items()})


_LABEL_ORDER = {"likely-bug": 0, "needs-human": 1, "intended": 2}


def render_markdown(r: AuditReport, verdicts: dict[str, Any] | None = None) -> str:
    """`verdicts`: adjudicate.Verdict by signature. Without them, findings are listed unadjudicated."""
    if verdicts:
        counts = {k: sum(v.label == k for v in verdicts.values()) for k in _LABEL_ORDER}
        status = "BLOCK" if counts["likely-bug"] else "REVIEW" if counts["needs-human"] else "PASS"
        summary = (f"**{status}: {len(r.findings)} behavior divergence class(es)**: "
                   + ", ".join(f"{n} {k}" for k, n in counts.items() if n) + ".")
    else:
        summary = f"**{len(r.findings)} behavior divergence class(es)** (unadjudicated)."
    lines = [
        f"## Breakwater audit: `{r.target}`",
        f"{r.repo} `{r.base[:10]}` → `{r.head[:10]}` · backend `{r.backend}` · image `{r.image}` · run `{r.run_id}`",
        "",
        summary,
        "",
    ]
    findings = sorted(r.findings, key=lambda f: _LABEL_ORDER.get(verdicts[f.signature].label, 1)
                      if verdicts and f.signature in verdicts else 1)
    for f in findings:
        args = json.dumps(f.args, ensure_ascii=False)
        args = args if len(args) <= 120 else args[:100] + f"… ({len(args)} chars)"
        v = (verdicts or {}).get(f.signature)
        lines += [
            f"- {f'**{v.label}** ' if v else ''}**[{f.probe}] {f.detail}**: input `{args}`",
            f"  - base: `{json.dumps(f.base, ensure_ascii=False)[:160]}`",
            f"  - head: `{json.dumps(f.head, ensure_ascii=False)[:160]}`",
            f"  - found by: {', '.join(f.found_by)}",
        ]
        if v and v.rationale:
            lines.append(f"  - why: {v.rationale}" + (f" ({v.reason})" if v.reason else ""))
    lines += ["", "### Attacks planned"]
    for a in r.attacks:
        ran = [s for s in r.strategies if s.attack == a.id]
        hits = sum(s.findings for s in ran)
        lines.append(f"- **{a.id}** ({sum(s.valid for s in ran)}/{len(ran)} strategies valid, {hits} hits): {a.assumption}")
    total = sum(r.usd_by_tier.values())
    tiers = ", ".join(f"{k} ${v:.4f}" for k, v in sorted(r.usd_by_tier.items()))
    lines += ["", f"**Cost:** ${total:.4f} ({tiers or 'no model calls logged'}) · **Time:** {r.seconds.get('total', 0):.0f}s"]
    return "\n".join(lines)
