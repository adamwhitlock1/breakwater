"""Perf attacks: find input families where the "faster" change is slower, and prove it with Ir.

  1. Plan     Ultra (medium effort) names input families where head may be slower than base (and the
              family the change is meant to speed up), each with a `make(n)` size-ladder generator.
  2. Search   Lightning writes Hypothesis strategies per family; the sandbox hill-climbs on the
              head/base CPU-time ratio (cheap and noisy; only used to rank candidates).
  3. Confirm  cachegrind instruction counts (Ir), which were deterministic to 0.0000% on day 1:
              - top search inputs: Ir per call, base vs head
              - each family's ladder (n = 16 .. 4096): Ir per call per size and a log-log slope, so a
                complexity change shows up as different slopes, not just a constant factor.

Ir per call is measured as (Ir at 2R reps - Ir at R reps) / (R * inputs): interpreter start-up,
imports and JSON parsing cancel exactly.
"""

from __future__ import annotations

import concurrent.futures as cf
import hashlib
import json
import math
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from breakwater.adversary import LLM, PLAN_REASONING, _parse_args, extract_code, extract_json, validate_strategy
from breakwater.backends import Backend
from breakwater.events import NULL, Events
from breakwater.images import PairImage
from breakwater.models import Tier
from breakwater.probes import Target
from breakwater.repo import Context

LADDER_SIZES = (2, 4, 16, 64, 256, 1024, 4096)
REVERSAL_RATIO = 1.05  # head/base Ir per call above this counts as a slowdown
SLOPE_DELTA = 0.15  # head slope this much above base slope counts as a complexity change

PERF_SYSTEM = """\
You review performance-motivated code changes for performance regressions.

The change claims to make code faster. Find the input families where the new version (head) is \
SLOWER than the old version (base), and identify the family the change is meant to speed up.

Work from the diff:
1. Find the condition that routes inputs into the new or changed code, and what each path costs.
2. Look for inputs that pay for the new check but still take the old path; inputs that hit the \
worst case of new data structures or algorithms (tuple or list membership instead of set, sorting, \
repeated scans or concatenation, regex backtracking, recursion); large or many-part inputs; inputs \
that defeat new caches or fast paths.
3. Families must be VALID inputs that the old version accepts and real users produce (for a parser: \
well-formed values of each syntax variant, e.g. each optional component or marker). Slowness on \
invalid inputs matters much less; include at most one such family and say "invalid" in its \
description. For each family write a generator.

The generator is Python source defining `make(n)`, which returns a list of 1 to 8 argument lists \
for the target, whose cost should grow with n (for example a string with n segments, or n \
specifiers). Use only builtins and the provided `string`, `random` (already seeded), `math` and \
`itertools` modules. No imports. It must be deterministic and fast to run."""

PERF_USER = """\
Target under test: `{target}` (called with positional arguments).

## Full head version of {module_path} (context)
```python
{source}
```

## The change under review (base -> head, tests and docs excluded)
```diff
{diff}
```

Return JSON with up to {n} families: at least one `claimed_speedup` family and the rest \
`suspected_slowdown`, most likely first."""

PERF_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "perf_plan",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "families": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "description": "short id, e.g. F1"},
                            "kind": {"type": "string", "enum": ["claimed_speedup", "suspected_slowdown"]},
                            "family": {"type": "string",
                                       "description": "one sentence describing the inputs, e.g. 'numeric versions with a pre-release tag'"},
                            "why": {"type": "string", "description": "why head is slower (or faster) on these inputs"},
                            "size_meaning": {"type": "string", "description": "what n controls, e.g. 'number of release segments'"},
                            "make_source": {"type": "string",
                                            "description": "Python source code: def make(n): return a list of argument lists"},
                            "example_args_json": {"type": "array", "items": {"type": "string"},
                                                  "description": "JSON arrays of positional arguments"},
                        },
                        "required": ["id", "kind", "family", "why", "size_meaning", "make_source",
                                     "example_args_json"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["families"],
            "additionalProperties": False,
        },
    },
}

PERF_STRATEGY_SYSTEM = """\
You write Hypothesis strategies that search for slow inputs to a Python function.

Output exactly one Python code block that assigns `strategy`. Available names: `st` \
(hypothesis.strategies) and `string`. No imports. The strategy generates positional arguments for \
the target (a single value, or a tuple). Values must be JSON-serializable. Generate inputs from the \
family described, with sizes from small to large (up to a few thousand characters or items) so a \
targeted search can climb toward the slowest cases. At most 25 lines."""

PERF_STRATEGY_USER = """\
Target: `{target}`. Call it exactly like these examples (same number and types of arguments): {examples}
Family {id} ({kind}): {family}
Why it may be slow on the new version: {why}
Size parameter: {size_meaning}
Reference generator:
```python
{make}
```"""


@dataclass
class Family:
    id: str
    kind: str
    family: str
    why: str
    size_meaning: str
    make_source: str
    example_args: list[list[Any]]
    origin: str = "plan"  # "plan", "expand:<parent id>" or "archive"
    screen_ratio: float | None = None  # head/base Ir per call at the screening size
    valid_fraction: float | None = None  # share of screening inputs the base version accepts
    error: str | None = None

    @property
    def realistic(self) -> bool:
        return (self.valid_fraction or 0) >= 0.5


@dataclass
class LadderPoint:
    n: int
    base_ir: float | None
    head_ir: float | None
    input_chars: float = 0.0  # mean JSON size of one input at this n; the slope's x axis
    valid_fraction: float | None = None  # share of this size's inputs the base version accepts

    @property
    def ratio(self) -> float | None:
        if self.base_ir and self.head_ir:
            return self.head_ir / self.base_ir
        return None

    @property
    def valid(self) -> bool:
        """Unknown validity (ladders measured before it was recorded) counts as valid."""
        return self.valid_fraction is None or self.valid_fraction >= VALID_POINT


@dataclass
class PerfFinding:
    family_id: str
    kind: str
    family: str
    why: str
    origin: str = "plan"
    screen_ratio: float | None = None
    valid_fraction: float | None = None
    ladder: list[LadderPoint] = field(default_factory=list)
    slope_base: float | None = None
    slope_head: float | None = None
    top_inputs: list[dict] = field(default_factory=list)  # {"args", "cpu_ratio", "ir_ratio", "base_ir", "head_ir"}
    error: str | None = None

    @property
    def ladder_ratios(self) -> list[float]:
        return [p.ratio for p in self.ladder if p.ratio]

    @property
    def judged_points(self) -> list[LadderPoint]:
        """The points the verdict and slopes use: sizes where most inputs are valid. A family whose
        every size is mostly invalid is judged on all points (it is flagged as an error-path family).
        Before this, one invalid input at one size could flip a claimed speedup to "slower"."""
        measured = [p for p in self.ladder if p.ratio]
        valid = [p for p in measured if p.valid]
        return valid or measured

    @property
    def judged_ratios(self) -> list[float]:
        return [p.ratio for p in self.judged_points if p.ratio]

    @property
    def excluded_points(self) -> list[LadderPoint]:
        judged = {id(p) for p in self.judged_points}
        return [p for p in self.ladder if p.ratio and id(p) not in judged]

    @property
    def worst_search(self) -> dict | None:
        """Search inputs can drift outside the family, so they are reported separately from the ladder."""
        measured = [t for t in self.top_inputs if t.get("ir_ratio")]
        return max(measured, key=lambda t: t["ir_ratio"]) if measured else None

    @property
    def worst_ratio(self) -> float | None:
        ratios = self.judged_ratios + ([self.worst_search["ir_ratio"]] if self.worst_search else [])
        return max(ratios) if ratios else None

    @property
    def verdict(self) -> str:
        """Family verdict from the deterministic ladder (judged points only):
        complexity-regression > slower > faster > neutral."""
        ratios = self.judged_ratios
        if not ratios:
            return "unmeasured"
        # A steeper head slope only matters if head ends up slower: a fast path whose advantage
        # shrinks with size (head still faster at the largest size) is not a regression.
        if (self.slope_base is not None and self.slope_head is not None
                and self.slope_head - self.slope_base > SLOPE_DELTA and ratios[-1] > 1.0):
            return "complexity-regression"
        if max(ratios) > REVERSAL_RATIO:
            return "slower"
        if max(ratios) < 1 / REVERSAL_RATIO:
            return "faster"
        return "neutral"


@dataclass
class PerfReport:
    run_id: str
    target: str
    image: str
    backend: str
    families: list[Family]
    findings: list[PerfFinding]
    seconds: dict[str, float]

    def to_json(self) -> dict:
        d = asdict(self)
        for f, fd in zip(self.findings, d["findings"], strict=True):
            fd["verdict"], fd["worst_ratio"], fd["worst_search"] = f.verdict, f.worst_ratio, f.worst_search
            for p, pd in zip(f.ladder, fd["ladder"], strict=True):
                pd["ratio"], pd["judged"] = p.ratio, p in f.judged_points
        return d


# ---------------------------------------------------------------------------------------------------
# Measurement

_IREFS = re.compile(r"I\s+refs:\s+([\d,]+)")


def _ir(backend: Backend, image: PairImage, side: str, target: Target, inputs: list, reps: int) -> int:
    py = image.BASE_PY if side == "base" else image.HEAD_PY
    req = {"target": target.callable, "observe": [], "ops": [{"op": "loop", "inputs": inputs, "reps": reps}]}
    cmd = ["valgrind", "--tool=cachegrind", "--cache-sim=no", "--cachegrind-out-file=/dev/null", py, image.WORKER]
    res = backend.run(image.ref, cmd, stdin=json.dumps(req), timeout_s=600)
    m = _IREFS.search(res.stderr)
    if res.exit_code != 0 or not m:
        raise RuntimeError(f"cachegrind failed on {side} (exit {res.exit_code}): {res.stderr[-400:]}")
    return int(m.group(1).replace(",", ""))


def ir_per_call(backend: Backend, image: PairImage, side: str, target: Target, inputs: list, reps: int) -> float:
    """(Ir at 2R - Ir at R) / (R * len(inputs)): start-up, imports and input parsing cancel."""
    lo = _ir(backend, image, side, target, inputs, reps)
    hi = _ir(backend, image, side, target, inputs, 2 * reps)
    return (hi - lo) / (reps * len(inputs))


def slope(points: list[tuple[float, float]]) -> float | None:
    """Least-squares slope of log(Ir per call) vs log(input size): ~1 linear, ~2 quadratic.
    None when inputs don't actually grow (some generators scale the number of inputs instead)."""
    pts = [(math.log(x), math.log(v)) for x, v in points if x and x > 0 and v and v > 0]
    if len(pts) < 3 or max(x for x, _ in pts) - min(x for x, _ in pts) < math.log(4):
        return None
    mx = sum(x for x, _ in pts) / len(pts)
    my = sum(y for _, y in pts) / len(pts)
    den = sum((x - mx) ** 2 for x, _ in pts)
    return sum((x - mx) * (y - my) for x, y in pts) / den if den else None


def _reps_for(inputs: list) -> int:
    size = max(1, len(json.dumps(inputs)))
    return max(2, min(200, 20_000 // size))


# ---------------------------------------------------------------------------------------------------
# Steps


MAKE_SYSTEM = """\
Write a Python input generator. Output exactly one Python code block defining `make(n)`, which \
returns a list of 1 to 8 argument lists (each a list of positional arguments) for the target, \
whose cost grows with n. Only builtins plus the provided modules `string`, `random` (already \
seeded), `math` and `itertools`. No imports. Deterministic and fast."""


def _families_from(data: dict, n: int) -> list[Family]:
    fams = []
    for i, f in enumerate(data.get("families", [])[:n]):
        examples = _parse_args(f.get("example_args_json", []))
        fams.append(Family(f"F{i + 1}", f.get("kind", "suspected_slowdown"), f.get("family", ""), f.get("why", ""),
                           f.get("size_meaning", ""), strip_provided_imports(unescape_code(f.get("make_source", ""))),
                           examples))
    return fams


def repair_make(llm: LLM, ctx: Context, fam: Family) -> str:
    """Lightning writes make(n) from the family description when the planner's generator is unusable."""
    msg = (f"Target: `{ctx.target}`\nInputs: {fam.family or fam.why}\nWhy they matter: {fam.why}\n"
           f"n controls: {fam.size_meaning}\nExamples: {json.dumps(fam.example_args, ensure_ascii=False)}")
    texts = llm.complete(Tier.VOLUME, [{"role": "system", "content": MAKE_SYSTEM}, {"role": "user", "content": msg}],
                         purpose=f"perf-make:{fam.id}", thinking=False, max_tokens=800).texts
    return strip_provided_imports(unescape_code(extract_code(texts[0]))) if texts else ""


def plan_families(llm: LLM, ctx: Context, n: int = 4) -> list[Family]:
    """Ultra, medium effort, 2 samples merged (plan quality varies a lot per sample); usable generators first,
    then Lightning repairs the rest.
    Code inside structured output is fragile: one day-1 sample put a file path in make_source."""
    messages = [
        {"role": "system", "content": PERF_SYSTEM},
        {"role": "user", "content": PERF_USER.format(target=ctx.target, module_path=ctx.module_path,
                                                     source=ctx.module_source, diff=ctx.diff, n=n)},
    ]
    texts = llm.complete(Tier.REASONING, messages, purpose="perf-plan", thinking=True, template_kwargs=PLAN_REASONING,
                         max_tokens=32000, n=3, response_format=PERF_SCHEMA, fallback_no_think=False).texts
    plans = []
    for text in texts:
        try:
            plans.append(_families_from(extract_json(text), n))
        except (json.JSONDecodeError, AttributeError):
            continue
    # Merge both samples, interleaved; families with a usable generator first (sort is stable).
    merged: list[Family] = []
    for rank in range(max((len(p) for p in plans), default=0)):
        merged += [p[rank] for p in plans if rank < len(p)]
    merged.sort(key=lambda f: _validate_make(f.make_source) is not None)
    families = merged[:n]
    for i, f in enumerate(families):
        f.id = f"F{i + 1}"
        if f.family in ("", f.kind):
            f.family = f.why[:160]
        if _validate_make(f.make_source):
            f.make_source = repair_make(llm, ctx, f)
    return families


def write_perf_strategies(llm: LLM, ctx: Context, fam: Family, n: int) -> list[str]:
    messages = [
        {"role": "system", "content": PERF_STRATEGY_SYSTEM},
        {"role": "user", "content": PERF_STRATEGY_USER.format(target=ctx.target, examples=_examples(fam), id=fam.id,
                                                              kind=fam.kind,
                                                              family=fam.family, why=fam.why,
                                                              size_meaning=fam.size_meaning, make=fam.make_source)},
    ]
    texts = llm.complete(Tier.VOLUME, messages, purpose=f"perf-strategy:{fam.id}", thinking=False,
                         max_tokens=1200, n=n).texts
    return [extract_code(t) for t in texts]


def _examples(fam: Family) -> str:
    if fam.example_args:
        return json.dumps(fam.example_args[:3], ensure_ascii=False)
    return "(none given; infer from the generator)"


def _sandbox(backend: Backend, image: PairImage, req: dict) -> dict:
    res = backend.run(image.ref, [image.SYS_PY, image.DIFFRUN], stdin=json.dumps(req), timeout_s=900)
    if res.exit_code != 0:
        return {"error": f"exit {res.exit_code}: {res.stderr[-400:]}"}
    return json.loads(res.stdout)


PROVIDED_MODULES = {"string", "random", "math", "itertools"}
_IMPORT = re.compile(r"^(\s*)import\s+([\w, ]+?)\s*$")
_FROM = re.compile(r"^(\s*)from\s+(\w+)\s+import\s+(.+?)\s*$")


def unescape_code(src: str) -> str:
    """Code inside JSON is sometimes double-escaped: literal backslash-n instead of newlines. Only
    unescape when the source has no real newline, so legitimate escapes in one-liners survive."""
    if "\n" not in src and "\\n" in src:
        src = src.replace("\\n", "\n").replace("\\t", "\t").replace('\\"', '"').replace("\\'", "'")
    return src


def strip_provided_imports(src: str) -> str:
    """Models often write `import random` despite instructions. Those modules are already in scope
    (random is a seeded instance), so `import m` lines are dropped and `from m import x [as y]`
    becomes `y = m.x`. Imports of anything else are left for validation to reject."""
    out = []
    for line in src.splitlines():
        m = _IMPORT.match(line)
        if m and {x.strip() for x in m.group(2).split(",")} <= PROVIDED_MODULES:
            continue
        m = _FROM.match(line)
        if m and m.group(2) in PROVIDED_MODULES:
            indent, mod = m.group(1), m.group(2)
            for item in m.group(3).strip("()").split(","):
                name, _, alias = item.strip().partition(" as ")
                out.append(f"{indent}{(alias or name).strip()} = {mod}.{name.strip()}")
            continue
        out.append(line)
    return "\n".join(out)


def _validate_make(src: str) -> str | None:
    err = validate_strategy(src.replace("def make", "strategy = None\ndef make", 1))
    if err:
        return err
    return None if "def make" in src else "source must define make(n)"


SCREEN_SIZE = 16  # one mid size per family is enough to rank families before full ladders
VALID_POINT = 0.5  # a ladder point counts toward the verdict if base accepts at least this share
SCREEN_SLOWER = 1.02  # screened head/base ratio above this counts as "slower" for expansion / archive
EXPAND_TOP = 2  # expand this many of the slowest families
EXPAND_VARIANTS = 3
FULL_SLOWER = 4  # full ladders + search for at most this many slower families (plus one speedup family)
ARCHIVE = Path("artifacts/archive")

EXPAND_SYSTEM = """\
You refine performance attacks. A family of inputs measured slower on the new version of a \
function. Write variants that each change ONE meaningful aspect of the family to find where the \
slowdown is largest: if the family uses one syntax feature (a marker, suffix, separator or optional \
component), each variant uses a DIFFERENT one; or move it, repeat it, or combine it with another. \
Variants must be valid inputs that the old version accepts and that real users produce, and must \
not be copies of the original. Describe each variant in one sentence. Each variant needs its own \
`make(n)` generator: Python source defining make(n) that returns a list of 1 \
to 8 argument lists whose cost grows with n, using only builtins and the provided `string`, \
`random` (already seeded), `math` and `itertools` modules. No imports."""

EXPAND_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "variants",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {"variants": {"type": "array", "items": {
                "type": "object",
                "properties": {"family": {"type": "string", "description": "one sentence: what changed"},
                               "make_source": {"type": "string", "description": "Python source defining make(n)"}},
                "required": ["family", "make_source"], "additionalProperties": False}}},
            "required": ["variants"], "additionalProperties": False,
        },
    },
}


def _archive_path(ctx: Context) -> Path:
    return ARCHIVE / (hashlib.sha256(f"{ctx.repo}|{ctx.target}".encode()).hexdigest()[:12] + ".json")


def load_archive(ctx: Context, limit: int = 4, providers: set[str] | None = None) -> list[Family]:
    """Families that measured slower in earlier runs on this target are re-screened every run, so a
    good find is not lost to an unlucky plan. `providers`: only families first proposed through these
    providers (a Token Factory run must not re-screen families a dev run proposed). Entries without a
    recorded `proposed_by` count as unknown and are skipped whenever a filter is given."""
    path = _archive_path(ctx)
    if not path.exists():
        return []
    entries = [e for e in json.loads(path.read_text()).get("families", [])
               if providers is None or e.get("proposed_by") in providers]
    entries.sort(key=lambda e: -e.get("best_ratio", 0))
    return [Family(f"R{i + 1}", e["kind"], e["family"], e.get("why", ""), e.get("size_meaning", ""), e["make_source"],
                   e.get("example_args", []), origin="archive") for i, e in enumerate(entries[:limit])]


def save_archive(ctx: Context, families: list[Family], run_id: str, provider: str = "unknown") -> None:
    path = _archive_path(ctx)
    data = json.loads(path.read_text()) if path.exists() else {"repo": ctx.repo, "target": ctx.target, "families": []}
    by_src = {hashlib.sha256(e["make_source"].encode()).hexdigest(): e for e in data["families"]}
    for f in families:
        if f.screen_ratio is None or f.screen_ratio <= SCREEN_SLOWER:
            continue
        key = hashlib.sha256(f.make_source.encode()).hexdigest()
        e = by_src.setdefault(key, {"kind": f.kind, "family": f.family, "why": f.why, "size_meaning": f.size_meaning,
                                    "make_source": f.make_source, "example_args": f.example_args, "best_ratio": 0,
                                    "seen_in": [], "proposed_by": provider})
        e["best_ratio"] = max(e["best_ratio"], f.screen_ratio)
        e["last_ratio"] = f.screen_ratio
        e["seen_in"] = (e["seen_in"] + [f"{run_id}:{ctx.base[:10]}..{ctx.head[:10]}"])[-10:]
    data["families"] = list(by_src.values())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def make_ladder(backend: Backend, image: PairImage, fam: Family, seed: int) -> dict[str, list]:
    """Run the family's LLM-written generator in the sandbox. Records any error on the family."""
    err = _validate_make(fam.make_source)
    if err:
        fam.error = f"make(n) rejected: {err}"
        return {}
    made = _sandbox(backend, image, {"mode": "make", "make": fam.make_source, "sizes": list(LADDER_SIZES), "seed": seed})
    fam.error = made.get("error")
    return {n: v for n, v in made.get("ladder", {}).items() if v}


def validity(backend: Backend, image: PairImage, target: Target, inputs: list) -> float | None:
    """Share of inputs the base version accepts (constructs without raising). One plain worker call."""
    res = backend.run(image.ref, [image.BASE_PY, image.WORKER], timeout_s=120, stdin=json.dumps(
        {"target": target.callable, "observe": [], "ops": [{"op": "construct", "inputs": inputs}]}))
    outcomes = json.loads(res.stdout)["results"][0]["outcomes"] if res.exit_code == 0 else []
    return sum(o["status"] == "ok" for o in outcomes) / len(outcomes) if outcomes else None


def judge_slopes(finding: PerfFinding) -> None:
    """Slopes over the judged points only, like the verdict."""
    pts = finding.judged_points
    finding.slope_base = slope([(p.input_chars, p.base_ir) for p in pts])
    finding.slope_head = slope([(p.input_chars, p.head_ir) for p in pts])


def screen(backend: Backend, image: PairImage, target: Target, fam: Family, ladder: dict[str, list]) -> None:
    """head/base Ir per call at one size (SCREEN_SIZE, or the closest smaller size the generator reached)."""
    sizes = sorted((int(n) for n in ladder), key=lambda n: (n > SCREEN_SIZE, abs(n - SCREEN_SIZE)))
    if not sizes:
        return
    inputs = ladder[str(sizes[0])]
    try:
        fam.valid_fraction = validity(backend, image, target, inputs)
        b = ir_per_call(backend, image, "base", target, inputs, _reps_for(inputs))
        h = ir_per_call(backend, image, "head", target, inputs, _reps_for(inputs))
        fam.screen_ratio = h / b if b > 0 else None
    except Exception as e:  # noqa: BLE001
        fam.error = fam.error or f"screen failed: {str(e)[:200]}"


def expand(llm: LLM, ctx: Context, fam: Family, k: int = EXPAND_VARIANTS) -> list[Family]:
    msg = (f"Target: `{ctx.target}`. Call it like: {_examples(fam)}\n"
           f"Family ({fam.screen_ratio:.2f}x head/base instructions per call): {fam.family}\n"
           f"Why it is slower: {fam.why}\nn controls: {fam.size_meaning}\n"
           f"Its generator:\n```python\n{fam.make_source}\n```\nWrite {k} variants.")
    try:
        # Super: better at code than Lightning, far cheaper than Ultra; variants need real code edits.
        texts = llm.complete(Tier.PROPOSER, [{"role": "system", "content": EXPAND_SYSTEM}, {"role": "user", "content": msg}],
                             purpose=f"perf-expand:{fam.id}", thinking=False, max_tokens=4000,
                             response_format=EXPAND_SCHEMA).texts
        variants = extract_json(texts[0]).get("variants", []) if texts else []
    except (json.JSONDecodeError, AttributeError, IndexError):
        return []
    out = []
    for i, v in enumerate(variants[:k]):
        out.append(Family(f"{fam.id}.{i + 1}", fam.kind, v.get("family", ""), fam.why, fam.size_meaning,
                          strip_provided_imports(unescape_code(v.get("make_source", ""))), fam.example_args,
                          origin=f"expand:{fam.id}"))
    return out


def full_measure(backend: Backend, image: PairImage, target: Target, fam: Family, ladder: dict[str, list], llm: LLM,
                 ctx: Context, *, strategies: int, max_examples: int, seed: int, top_k: int = 2) -> PerfFinding:
    finding = PerfFinding(fam.id, fam.kind, fam.family, fam.why, origin=fam.origin, screen_ratio=fam.screen_ratio,
                          valid_fraction=fam.valid_fraction, error=fam.error)

    # Targeted search with Lightning-written strategies.
    tops: list[dict] = []
    for i, src in enumerate(write_perf_strategies(llm, ctx, fam, strategies)):
        if validate_strategy(src):
            continue
        res = _sandbox(backend, image, {"mode": "perf", "strategy": src, "target": target.callable,
                                        "max_examples": max_examples, "seed": seed + i, "top": top_k,
                                        "base_py": image.BASE_PY, "head_py": image.HEAD_PY})
        tops += res.get("top", [])
    tops = sorted(tops, key=lambda t: -t["ratio"])[:top_k]

    # Confirm with Ir: every ladder size and the top search inputs, base and head, in parallel.
    jobs: dict[tuple[str, str], tuple[list, int]] = {("ladder", n): (inputs, _reps_for(inputs)) for n, inputs in ladder.items()}
    for i, t in enumerate(tops):
        jobs[("top", str(i))] = ([t["args"]], _reps_for([t["args"]]))
    results: dict[tuple[str, str, str], float | None] = {}
    valid: dict[str, float | None] = {}
    with cf.ThreadPoolExecutor(max_workers=6) as pool:
        vfuts = {pool.submit(validity, backend, image, target, inputs): n for n, inputs in ladder.items()}
        futs = {pool.submit(ir_per_call, backend, image, side, target, inputs, reps): (kind, key, side)
                for (kind, key), (inputs, reps) in jobs.items() for side in ("base", "head")}
        for fut in cf.as_completed(vfuts):
            try:
                valid[vfuts[fut]] = fut.result()
            except Exception:  # noqa: BLE001 - unknown validity is treated as valid
                valid[vfuts[fut]] = None
        for fut in cf.as_completed(futs):
            try:
                results[futs[fut]] = fut.result()
            except Exception as e:  # noqa: BLE001 - e.g. a ladder size that times out under valgrind
                results[futs[fut]] = None
                finding.error = finding.error or str(e)[:300]

    for n in sorted(ladder, key=int):
        chars = sum(len(json.dumps(a, ensure_ascii=False)) for a in ladder[n]) / len(ladder[n])
        finding.ladder.append(LadderPoint(int(n), results.get(("ladder", n, "base")), results.get(("ladder", n, "head")),
                                          chars, valid.get(n)))
    judge_slopes(finding)
    for i, t in enumerate(tops):
        b, h = results.get(("top", str(i), "base")), results.get(("top", str(i), "head"))
        finding.top_inputs.append({"args": t["args"], "cpu_ratio": round(t["ratio"], 3), "base_ir": b, "head_ir": h,
                                   "ir_ratio": (h / b) if b and h else None, "outcome": t.get("outcome", "ok")})
    return finding


def perf_audit(ctx: Context, image: PairImage, llm: LLM, backend: Backend, target: Target, *, run_id: str,
               n_families: int = 6, strategies_per_family: int = 2, max_examples: int = 120, seed: int = 0,
               use_archive: bool = True, log=print, events: Events = NULL) -> PerfReport:
    """plan (3 samples merged) + archive -> screen every family at one size -> expand the slowest ->
    screen the variants -> full ladders and search for the slowest few plus the main speedup family."""
    t0 = time.perf_counter()
    events("phase", name="perf-plan")
    families = plan_families(llm, ctx, n_families)
    provider = getattr(getattr(llm, "provider", None), "value", None) or "unknown"
    # Publishable (Token Factory) runs only re-screen families Token Factory proposed.
    archived = load_archive(ctx, providers={"tokenfactory"} if provider == "tokenfactory" else None) \
        if use_archive else []
    known = {f.make_source for f in families}
    families += [f for f in archived if f.make_source not in known]
    timings = {"plan": time.perf_counter() - t0}
    log(f"perf plan: {len(families) - len(archived)} planned + {len(archived)} from archive ({timings['plan']:.1f}s)")

    ladders: dict[str, dict[str, list]] = {}

    def prepare(f: Family) -> None:
        ladders[f.id] = make_ladder(backend, image, f, seed)
        screen(backend, image, target, f, ladders[f.id])
        events("family", id=f.id, family_kind=f.kind, family=f.family, origin=f.origin, screen_ratio=f.screen_ratio,
               valid_fraction=f.valid_fraction, error=(f.error or "")[:200] or None)

    t1 = time.perf_counter()
    events("phase", name="perf-screen")
    with cf.ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(prepare, families))
    def rank(fams: list[Family]) -> list[Family]:
        """Slower families, realistic (mostly valid inputs) before error-path ones, then by ratio."""
        return sorted((f for f in fams if f.screen_ratio and f.screen_ratio > SCREEN_SLOWER),
                      key=lambda f: (not f.realistic, -f.screen_ratio))

    events("phase", name="perf-expand")
    variants = [v for f in rank(families)[:EXPAND_TOP] for v in expand(llm, ctx, f)]
    with cf.ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(prepare, variants))
    families += variants
    timings["screen"] = time.perf_counter() - t1
    for f in families:
        ratio = f"{f.screen_ratio:.2f}x" if f.screen_ratio else "n/a"
        valid = f"{f.valid_fraction:.0%}" if f.valid_fraction is not None else "?"
        log(f"  {f.id:6s} {ratio:>6s} valid {valid:>4s} [{f.kind}] ({f.origin}) {f.family[:80]}"
            f"{'  ERROR ' + f.error[:80] if f.error else ''}")

    slower = rank(families)[:FULL_SLOWER]
    speedups = sorted((f for f in families if f.kind == "claimed_speedup" and f.screen_ratio and f.realistic),
                      key=lambda f: f.screen_ratio)[:1]
    selected = slower + [f for f in speedups if f not in slower]
    t2 = time.perf_counter()
    events("phase", name="perf-full")

    def measure(f: Family) -> PerfFinding:
        res = full_measure(backend, image, target, f, ladders[f.id], llm, ctx, strategies=strategies_per_family,
                           max_examples=max_examples, seed=seed)
        events("measured", family_id=res.family_id, family=res.family, family_kind=res.kind, verdict=res.verdict,
               valid_fraction=res.valid_fraction, slope_base=res.slope_base, slope_head=res.slope_head,
               ladder=[{"input_chars": p.input_chars, "ratio": p.ratio, "valid_fraction": p.valid_fraction,
                        "judged": p in res.judged_points} for p in res.ladder])
        return res

    with cf.ThreadPoolExecutor(max_workers=2) as pool:
        findings = list(pool.map(measure, selected))
    timings["full"] = time.perf_counter() - t2
    if use_archive:
        save_archive(ctx, families, run_id, provider)
    for f in findings:
        ladder = ", ".join(f"{r:.2f}" for r in f.ladder_ratios) or "n/a"
        log(f"  {f.family_id}: {f.verdict} (ladder head/base Ir {ladder}; slopes {_fmt(f.slope_base)} -> {_fmt(f.slope_head)})")
    timings["total"] = time.perf_counter() - t0
    return PerfReport(run_id, ctx.target, image.ref, backend.name, families, findings,
                      {k: round(v, 2) for k, v in timings.items()})


def judged(f: dict) -> list[float]:
    """Judged ratios of a finding in report JSON (points recorded before validity was tracked count)."""
    return [pt["ratio"] for pt in f.get("ladder", []) if pt.get("ratio") and pt.get("judged", True)]


def summarize(report: dict) -> dict:
    """The perf summary the backtest stores and the site shows, from report JSON: the worst judged
    ratio among slower families with mostly valid inputs, and the claimed speedup at small sizes."""
    realistic = [f for f in report.get("findings", []) if (f.get("valid_fraction") or 0) >= 0.5]
    slower = [f for f in realistic if f.get("verdict") in ("slower", "complexity-regression") and judged(f)]
    worst = max(slower, key=lambda f: max(judged(f)), default=None)
    speed = [f for f in realistic if f.get("kind") == "claimed_speedup" and judged(f)]
    return {
        "slower_families": [{"id": f["family_id"], "family": f["family"], "verdict": f["verdict"],
                             "ladder": judged(f), "origin": f.get("origin")} for f in slower],
        "worst_valid_ratio": max(judged(worst)) if worst else None,
        "worst_family": worst["family"] if worst else None,
        "speedup_ratio_small": min(judged(speed[0])) if speed else None,
        "report": report,
    }


def _fmt(x: float | None) -> str:
    return f"{x:.2f}" if x is not None else "n/a"


def render_markdown(r: PerfReport) -> str:
    lines = ["### Performance", "", "Screened families (head/base Ir per call at one size; >1 means the change is slower):", ""]
    for f in sorted(r.families, key=lambda f: (not f.realistic, -(f.screen_ratio or 0))):
        ratio = f"{f.screen_ratio:.2f}x" if f.screen_ratio else "n/a"
        valid = f"{f.valid_fraction:.0%} valid" if f.valid_fraction is not None else "validity ?"
        lines.append(f"- `{ratio}` {f.id} [{f.kind}, {f.origin}, {valid}] {f.family[:110]}")
    lines += ["", "Measured in full:", ""]
    for f in r.findings:
        ratios = f.ladder_ratios
        span = f"{min(ratios):.2f}x–{max(ratios):.2f}x" if ratios else "n/a"
        valid = "" if (f.valid_fraction or 0) >= 0.5 else " (error path: inputs mostly invalid)"
        lines.append(f"- **{f.family_id} [{f.kind}, {f.origin}] {f.verdict}{valid}**: head/base Ir per call {span} across sizes; "
                     f"slope {_fmt(f.slope_base)} → {_fmt(f.slope_head)}. {f.family}")
        if f.ladder:
            cells = ", ".join(f"n={p.n} (~{p.input_chars:.0f} chars): {p.ratio:.2f}x" if p.ratio else f"n={p.n}: n/a"
                              for p in f.ladder)
            lines.append(f"  - ladder (head/base Ir): {cells}")
        for t in f.top_inputs:
            args = json.dumps(t["args"], ensure_ascii=False)
            args = args if len(args) <= 90 else args[:70] + f"… ({len(args)} chars)"
            ir = f"{t['ir_ratio']:.2f}x" if t.get("ir_ratio") else "n/a"
            note = "" if t.get("outcome", "ok") == "ok" else f" (both sides raise {t['outcome'].split(':', 1)[-1]})"
            lines.append(f"  - search input `{args}`: CPU {t['cpu_ratio']:.2f}x, Ir {ir}{note}")
        if f.error:
            lines.append(f"  - error: {f.error[:200]}")
    return "\n".join(lines)
