"""Adjudication: is each divergence class a likely bug, an intended change, or one for a human?

Facts come first and are never overridden. Each class arrives with its probe, minimal input and the
base and head outcomes, all from deterministic execution. For exception changes, the sandbox also
records how the two exception types relate (`exception_facts`), because "head raises a subclass
of what base raised" and "head raises something unrelated" call for different verdicts.

Ultra then labels every class of a target in one call (reasoning on, medium effort). It sees what a
reviewer would have at PR time: the PR title, the code diff, the PR's own test/doc/changelog
changes (`repo.intent_diff`) and the head module's source with its docstrings. It never sees later
fixes, issue threads or which classes are known bugs.

Deterministic guards on the model's output:
  * PLAN_SAMPLES independent samples; a label needs a strict majority, otherwise the class is
    needs-human (an abstention, not a guess).
  * a likely-bug or intended vote must quote evidence that occurs verbatim in the material it was
    given. A vote whose quotes are not found counts as needs-human.
  * the model only adds labels. It cannot drop, merge or edit a finding, and a needs-human class
    is reported exactly like an unlabelled one.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any

from breakwater.adversary import LLM, extract_json
from breakwater.backends import Backend
from breakwater.images import PairImage
from breakwater.models import Tier
from breakwater.repo import Context

LIKELY_BUG, INTENDED, NEEDS_HUMAN = "likely-bug", "intended", "needs-human"
LABELS = (LIKELY_BUG, INTENDED, NEEDS_HUMAN)
SAMPLES = 3
REASONING = {"medium_effort": True}
MAX_CLASSES_PER_CALL = 20
MAX_SOURCE_CHARS = 40_000
MIN_QUOTE_CHARS = 8
NO_INTENT = "None: this PR changes no tests, docs or changelog."

# ---------------------------------------------------------------------------------------------------
# Prompts

SYSTEM = """\
You adjudicate behavior differences between two versions of a Python library: base (before a \
change) and head (after it). Each difference is a fact: both versions were executed on the inputs \
shown and behaved as stated. Do not question whether it happens. Decide what a reviewer of the \
change should do about it:

- likely-bug: an unintended regression users could hit. Typical signs: the change presents itself \
as a refactor or performance change, nothing in the PR's tests, docs or changelog asks for the new \
behavior, and the old behavior is documented, conventional or something callers plausibly rely on \
(return values, string forms, which exception type is raised, equality, hashing, ordering, \
loading objects pickled by the previous version).
- intended: the new behavior is deliberate (the PR's tests, docs, changelog or title ask for it) \
or it is what the library's own documentation says should happen, so the old behavior was the bug.
- needs-human: the material does not settle it. Abstain rather than guess.

Judge only from the material given. For each verdict, quote 1-3 short snippets copied exactly \
from that material (one line each, at least a few words) that support it. Quotes are checked \
mechanically against the material, and a verdict whose quotes are not found is discarded. \
needs-human verdicts need no quotes. Be brief."""

# Context first, task last: with ~8k tokens of code before the question, Token Factory samples
# sometimes answered a different task ("compare the two snippets"). The facts and the question
# now come after all the code, and the code blocks say what they are.
USER = """\
Context for the task at the end of this message.

## Context 1 of 3: the full head version of {module_path}, including docstrings (not a diff)
```python
{source}
```

## Context 2 of 3: the code change under review (base -> head; tests and docs excluded)
PR title: {title}
```diff
{diff}
```

## Context 3 of 3: the PR's own changes to tests, docs and changelog
{intent}

## Task
Target under test: `{target}`. Executing base and head on the inputs below gave these behavior \
differences (facts):
{facts}

For each difference C1, C2, ... decide likely-bug, intended or needs-human, as instructed. Do not \
describe the code change itself; judge only the listed differences. Every likely-bug or intended \
verdict needs 1-3 evidence strings copied character for character from Context 1-3 above (e.g. a \
line of code, a docstring sentence, the PR title). Paraphrases and descriptions are discarded, and \
a verdict left without evidence becomes needs-human. Return JSON with one verdict per difference, \
using its id."""

SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "adjudication",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "verdicts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "label": {"type": "string", "enum": list(LABELS)},
                            "rationale": {"type": "string", "description": "one or two sentences"},
                            "evidence": {"type": "array", "items": {"type": "string"},
                                         "description": "verbatim quotes from the material"},
                        },
                        "required": ["id", "label", "rationale", "evidence"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["verdicts"],
            "additionalProperties": False,
        },
    },
}

def schema_for(ids: list[str]) -> dict:
    """SCHEMA pinned to this call's classes: exactly one verdict per id. Without the bounds Token
    Factory's constrained decoding sometimes returned `{"verdicts": []}`, which is valid JSON and
    silently cost the sample (2 of 3 on the 2026-10-09 demo run)."""
    import copy

    s = copy.deepcopy(SCHEMA)
    arr = s["json_schema"]["schema"]["properties"]["verdicts"]
    arr["minItems"] = arr["maxItems"] = len(ids)
    arr["items"]["properties"]["id"] = {"type": "string", "enum": list(ids)}
    return s


# ---------------------------------------------------------------------------------------------------
# Data


@dataclass
class Verdict:
    signature: str
    label: str
    votes: dict[str, int]
    rationale: str = ""
    evidence: list[str] = field(default_factory=list)  # quotes that were found in the material
    rejected: list[str] = field(default_factory=list)  # quotes that were not
    reason: str = ""  # why the label is needs-human, when the guards made it so


@dataclass
class Adjudication:
    target: str
    verdicts: list[Verdict]
    samples: int  # model samples that parsed
    usd: float = 0.0

    def by_signature(self) -> dict[str, Verdict]:
        return {v.signature: v for v in self.verdicts}

    def counts(self) -> dict[str, int]:
        c = Counter(v.label for v in self.verdicts)
        return {label: c.get(label, 0) for label in LABELS}

    def to_json(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------------------------------
# Facts


_EXC_FACTS = r"""
import importlib, json, sys

def resolve(name):
    parts = name.split(".")
    for i in range(len(parts) - 1, 0, -1):
        try:
            obj = importlib.import_module(".".join(parts[:i]))
        except ImportError:
            continue
        try:
            for attr in parts[i:]:
                obj = getattr(obj, attr)
            return obj
        except AttributeError:
            return None
    return None

out = {}
for name in json.load(sys.stdin):
    cls = resolve(name)
    out[name] = [f"{c.__module__}.{c.__qualname__}" for c in cls.__mro__] if isinstance(cls, type) else None
print(json.dumps(out))
"""


def _exc_names(outcome: Any) -> str | None:
    if isinstance(outcome, dict) and outcome.get("status") == "exc":
        return outcome.get("exc")
    return None


def exception_facts(backend: Backend, image: PairImage, findings: list[Any]) -> dict[str, dict[str, list[str]]]:
    """MROs of every exception type a P2 finding reports, resolved in the env that raised it.
    Runs in the sandbox: importing the target's modules executes repo code."""
    want: dict[str, set[str]] = {"base": set(), "head": set()}
    for f in findings:
        if f.probe != "P2":
            continue
        for side, outcome in (("base", f.base), ("head", f.head)):
            if name := _exc_names(outcome):
                want[side].add(name)
    out: dict[str, dict[str, list[str]]] = {"base": {}, "head": {}}
    for side, names in want.items():
        if not names:
            continue
        py = image.BASE_PY if side == "base" else image.HEAD_PY
        res = backend.run(image.ref, [py, "-c", _EXC_FACTS], stdin=json.dumps(sorted(names)), timeout_s=60)
        if res.exit_code == 0:
            out[side] = {k: v for k, v in json.loads(res.stdout).items() if v}
    return out


def _short(v: Any, n: int = 160) -> str:
    s = json.dumps(v, ensure_ascii=False)
    return s if len(s) <= n else s[: n - 20] + f"... ({len(s)} chars)"


def _relation(b: str, h: str, mros: dict[str, dict[str, list[str]]]) -> str:
    """The type relation only. Consequences cut both ways (a subclass is still caught by
    `except Base`, but `except Sub` handlers now also see it), so the model weighs them, not us."""
    head_mro, base_mro = mros.get("head", {}).get(h), mros.get("base", {}).get(b)
    if head_mro and b in head_mro[1:]:
        return f"{h} is a subclass of {b}"
    if base_mro and h in base_mro[1:]:
        return f"{h} is a base class of {b}"
    if head_mro and base_mro:
        return "neither exception type subclasses the other"
    return ""


def describe(f: Any, mros: dict[str, dict[str, list[str]]] | None = None) -> str:
    """One class as plain facts. `f` is an adversary.Finding (or anything with the same fields)."""
    mros = mros or {}
    if f.probe == "P1":
        return (f"Output `{f.detail}` differs. Input {_short(f.args[0])}: base gives {_short(f.base)}, "
                f"head gives {_short(f.head)}.")
    if f.probe == "P2":
        def outcome(o: Any) -> str:
            if not isinstance(o, dict):
                return _short(o)
            if o.get("status") == "ok":
                return "returns normally"
            if o.get("status") == "timeout":
                return "times out"
            return f"raises {o.get('exc')}"

        line = f"Outcome differs. Input {_short(f.args[0])}: base {outcome(f.base)}, head {outcome(f.head)}."
        b, h = _exc_names(f.base), _exc_names(f.head)
        if b and h and (rel := _relation(b, h, mros)):
            line += f" ({rel}.)"
        return line
    if f.probe == "P3":
        a, b = f.args[0], f.args[1]
        rel = {"eq": "a == b", "lt": "a < b", "gt": "a > b", "hash_eq": "hash(a) == hash(b)"}.get(f.detail)
        if rel:
            return (f"Relation `{rel}` differs for a = target(*{_short(a, 80)}), b = target(*{_short(b, 80)}): "
                    f"base {f.base}, head {f.head}.")
        return f"Relation check `{f.detail}` for a = {_short(a, 80)}, b = {_short(b, 80)}: base {f.base}, head {f.head}."
    if f.probe in ("P4", "P4down"):
        src, dst = ("base", "head") if f.probe == "P4" else ("head", "base")
        made = f"An object built by {src} from {_short(f.args[0])}, pickled, then unpickled by {dst}"
        if f.detail.endswith("load"):
            exc = f.head.get("exc") if isinstance(f.head, dict) else f.head
            return f"{made} fails to load: {exc}."
        if isinstance(f.head, str) and f.head.startswith("<"):
            return f"{made} loads, but comparing it with a freshly built {dst} object fails: {f.head}."
        return f"{made} loads, but no longer equals a freshly built {dst} object (== gives {f.head})."
    return f"{f.probe} {f.detail}: input {_short(f.args)}, base {_short(f.base)}, head {_short(f.head)}."


# ---------------------------------------------------------------------------------------------------
# Evidence check

_DIFF_MARK = re.compile(r"^[+\- ]", re.MULTILINE)
_WS = re.compile(r"\s+")
_ELLIPSIS = re.compile(r"\.\.\.|…")


def _norm(text: str, *, diff: bool = False) -> str:
    """Whitespace-free, case-folded, quote-unified. Models re-flow code across lines when quoting
    (`tuple(\n    map(` comes back as `tuple(map(`), so whitespace can't be part of the check."""
    if diff:
        text = _DIFF_MARK.sub("", text)
    return _WS.sub("", text.replace("`", "").replace('"', "'")).lower()


def material(title: str, ctx: Context, intent: str) -> str:
    """Everything the model may quote, normalized for substring checks. The facts are not quotable:
    they are what is being judged, not evidence about intent."""
    return "\n".join([_norm(title), _norm(ctx.diff, diff=True), _norm(intent, diff=True) if intent.strip()
                       else _norm(NO_INTENT), _norm(ctx.module_source)])


def quote_found(quote: str, haystack: str) -> bool:
    """Verbatim up to whitespace. A quote elided with "..." passes if every fragment is found
    (code can contain a literal "...", so the whole quote is tried first)."""
    def found(q: str) -> bool:
        q = _norm(q, diff=True).strip("'.…")
        return len(q) >= MIN_QUOTE_CHARS and q in haystack

    if found(quote):
        return True
    parts = [p for p in _ELLIPSIS.split(quote) if _norm(p).strip("'.…")]
    return len(parts) > 1 and all(found(p) or len(_norm(p)) < MIN_QUOTE_CHARS for p in parts) \
        and any(found(p) for p in parts)


# ---------------------------------------------------------------------------------------------------
# Adjudicate


def _vote(sig: str, samples: list[dict[str, dict]], haystack: str, n_requested: int) -> Verdict:
    votes: Counter[str] = Counter()
    kept: dict[str, list[tuple[str, list[str]]]] = {}  # label -> [(rationale, found quotes)]
    rejected: list[str] = []
    unsupported = 0  # likely-bug / intended votes demoted because no quote was found
    for sample in samples:
        v = sample.get(sig)
        if not v or v.get("label") not in LABELS:
            continue
        label = v["label"]
        quotes = [q for q in v.get("evidence", []) if isinstance(q, str)]
        found = [q for q in quotes if quote_found(q, haystack)]
        rejected += [q for q in quotes if q not in found]
        if label != NEEDS_HUMAN and not found:
            label, unsupported = NEEDS_HUMAN, unsupported + 1
        votes[label] += 1
        kept.setdefault(label, []).append((v.get("rationale", ""), found))
    # Strict majority of the samples requested, so a lost or unparseable sample is not a free win.
    top = votes.most_common(1)
    if top and top[0][1] >= n_requested // 2 + 1:
        label = top[0][0]
        rationale = kept[label][0][0]
        evidence = list(dict.fromkeys(q for _, qs in kept[label] for q in qs))
        reason = ""
        if label == NEEDS_HUMAN:
            reason = "evidence not found in the material" if unsupported * 2 > votes[label] else "model abstained"
        return Verdict(sig, label, dict(votes), rationale, evidence, rejected, reason)
    reason = "no majority" if votes else "no verdict returned"
    rationale = next((r for label in (LIKELY_BUG, INTENDED) for r, _ in kept.get(label, [])), "")
    return Verdict(sig, NEEDS_HUMAN, dict(votes), rationale, [], rejected, reason)


def adjudicate(llm: LLM, ctx: Context, findings: list[Any], *, title: str = "", intent: str = "",
               mros: dict[str, dict[str, list[str]]] | None = None, samples: int = SAMPLES) -> Adjudication:
    """Label every finding class of one target. `findings` are adversary.Finding objects."""
    haystack = material(title, ctx, intent)
    source = ctx.module_source
    if len(source) > MAX_SOURCE_CHARS:
        source = source[:MAX_SOURCE_CHARS] + "\n# ... [source truncated]"
    verdicts: list[Verdict] = []
    parsed = 0
    usd = 0.0
    for start in range(0, len(findings), MAX_CLASSES_PER_CALL):
        chunk = findings[start : start + MAX_CLASSES_PER_CALL]
        ids = {f"C{i + 1}": f.signature for i, f in enumerate(chunk)}
        facts = "\n".join(f"- C{i + 1} [{f.probe}] {describe(f, mros)}" for i, f in enumerate(chunk))
        messages = [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": USER.format(
                target=ctx.target, title=title or "(not given)", facts=facts, diff=ctx.diff,
                intent=f"```diff\n{intent}\n```" if intent.strip() else NO_INTENT,
                module_path=ctx.module_path, source=source)},
        ]
        per_sample: list[dict[str, dict]] = []
        # One top-up call for samples that came back empty or unparseable (free routes drop some),
        # so an abstention means disagreement, not a lost response.
        for attempt in range(2):
            missing = samples - len(per_sample)
            if missing <= 0:
                break
            res = llm.complete(Tier.REASONING, messages, purpose="adjudicate" + (":top-up" if attempt else ""),
                               thinking=True, template_kwargs=REASONING, max_tokens=24000, n=missing,
                               response_format=schema_for(list(ids)), fallback_no_think=False)
            usd += getattr(res, "usd", 0.0) or 0.0
            for text in res.texts:
                try:
                    rows = extract_json(text).get("verdicts", [])
                except (json.JSONDecodeError, AttributeError):
                    continue
                got = {ids[r["id"]]: r for r in rows if isinstance(r, dict) and r.get("id") in ids}
                # A sample that skips most classes is a lost sample (top it up), not a vote to abstain.
                if len(got) * 2 >= len(ids):
                    per_sample.append(got)
        parsed += len(per_sample)
        verdicts += [_vote(sig, per_sample, haystack, samples) for sig in ids.values()]
    return Adjudication(ctx.target, verdicts, parsed, round(usd, 6))
