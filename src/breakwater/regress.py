"""Regression tests from findings: one pytest per divergence class that pins the BASE behaviour.

Generation is deterministic templating (no model calls). Each test is then executed in the sandbox
on both sides; only a test that passes on base and fails on head is `verified`, and only verified
tests are offered as ready to commit. Observations are normalised by the worker (tuples become
lists, long ints are summarised, object reprs lose addresses), so some assertions can't be written
exactly; verification catches those instead of trusting the template.

    P1  assert str(Version("1. 0")) == "1.0"            (str, repr, len, value, attr:<name>)
    P2  exact exception type (pytest.raises alone would accept a subclass), or "returns normally"
    P3  assert (a == b) is True, ordering, hash equality, or the eq/hash contract
    P4  an object pickled by base (bytes embedded in the test) must load and equal a fresh one

Classes adjudicated `intended` get no test: pinning the old behaviour would block a wanted change.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Any

from breakwater.backends import Backend
from breakwater.images import PairImage

LONG = 80


@dataclass
class RegressionTest:
    signature: str
    name: str
    source: str
    base: str = "not run"  # pass | fail | error:<type> | not run
    head: str = "not run"
    skipped: str = ""  # why no test was generated

    @property
    def verified(self) -> bool:
        return self.base == "pass" and self.head != "pass" and self.head != "not run"

    def to_json(self) -> dict:
        return {**asdict(self), "verified": self.verified}


# ---------------------------------------------------------------------------------------------------
# Literals and calls


def py_literal(v: Any) -> str:
    """A Python expression for a JSON value. Long strings made of a few runs become `"1" + "0" * 4304`."""
    if isinstance(v, str):
        if len(v) > LONG:
            runs = [(m.group(0)[0], len(m.group(0))) for m in re.finditer(r"(.)\1*", v, re.DOTALL)]
            if len(runs) <= 6:
                return " + ".join(repr(c) if n == 1 else f"{c!r} * {n}" for c, n in runs)
        return repr(v)
    if isinstance(v, list):
        return "[" + ", ".join(py_literal(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{" + ", ".join(f"{py_literal(k)}: {py_literal(x)}" for k, x in v.items()) + "}"
    return repr(v)


def split_target(target: str) -> tuple[str, str, str]:
    """"pkg.mod:Class#method" -> ("pkg.mod", "Class", "method"); "Class()#method" keeps the "()"."""
    mod, _, attr = target.partition(":")
    attr, _, method = attr.partition("#")
    return mod, attr, method


def call_expr(target: str, args: list[Any]) -> str:
    _, name, method = split_target(target)
    lits = [py_literal(a) for a in args]
    if method and name.endswith("()"):
        return f"{name}.{method}({', '.join(lits)})"
    if method:
        return f"{name}({lits[0]}).{method}({', '.join(lits[1:])})"
    return f"{name}({', '.join(lits)})"


def import_line(target: str) -> str:
    mod, name, _ = split_target(target)
    return f"from {mod} import {name.removesuffix('()').split('.')[0]}"


def _exc_import(qualified: str) -> tuple[str, str]:
    mod, _, name = qualified.rpartition(".")
    return ("", name) if mod in ("builtins", "") else (f"from {mod} import {name}", name)


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")[:40]


# ---------------------------------------------------------------------------------------------------
# Generation


def _observe_assert(obs: str, expr: str, value: Any) -> str | None:
    if obs == "str":
        return f"assert str({expr}) == {py_literal(value)}" if isinstance(value, str) else None
    if obs == "repr":
        if not isinstance(value, str) or "0x?" in value:
            return None
        return f"assert repr({expr}) == {py_literal(value)}"
    if obs == "len":
        return f"assert len({expr}) == {value!r}" if isinstance(value, int) else None
    if obs == "value" or obs.startswith("attr:"):
        target = expr if obs == "value" else f"{expr}.{obs[5:]}"
        if isinstance(value, str) and value.startswith("<int "):
            return None  # summarised by the worker; the exact value is not recorded
        if isinstance(value, list):  # tuples and iterators were recorded as lists
            return f"assert list({target}) == {py_literal(value)}"
        if value is None or isinstance(value, (str, int, float, bool)):
            return f"assert {target} == {py_literal(value)}" if value is not None else f"assert {target} is None"
    return None


def generate(f: Any, target: str, *, item: str = "", label: str | None = None, index: int = 0,
             pickle_blob: str | None = None) -> RegressionTest:
    """One test for one finding class (an adversary.Finding or the equivalent dict fields)."""
    probe, detail, args, base = f.probe, f.detail, f.args, f.base
    name = f"test_{_slug(item) + '_' if item else ''}{probe.lower()}_{_slug(detail)}_{index}"
    if label == "intended":
        return RegressionTest(f.signature, name, "", skipped="adjudicated intended: no test pins the old behaviour")
    imports = [import_line(target)]
    lines: list[str] = []
    doc = f'Breakwater {probe}: base behaviour pinned (found by differential testing; label: {label or "unlabelled"}).'

    if probe == "P1":
        a = _observe_assert(detail, call_expr(target, args[0]), base)
        if not a:
            return RegressionTest(f.signature, name, "", skipped=f"observation {detail!r} can't be asserted exactly")
        lines.append(a)
    elif probe == "P2":
        b = base if isinstance(base, dict) else {}
        expr = call_expr(target, args[0])
        if b.get("status") == "ok":
            lines.append(f"{expr}  # base returns normally")
        elif b.get("status") == "exc":
            imp, exc = _exc_import(b["exc"])
            if imp:
                imports.append(imp)
            imports.append("import pytest")
            lines += [f"with pytest.raises({exc}) as excinfo:", f"    {expr}",
                      f"assert type(excinfo.value) is {exc}  # exact type: a subclass would be a behaviour change"]
        else:
            return RegressionTest(f.signature, name, "", skipped=f"base outcome {b.get('status')!r} can't be pinned")
    elif probe == "P3":
        if len(args) != 2:
            return RegressionTest(f.signature, name, "", skipped="relation finding without a pair of inputs")
        lines += [f"a = {call_expr(target, args[0])}", f"b = {call_expr(target, args[1])}"]
        rel = {"eq": "a == b", "lt": "a < b", "gt": "a > b", "hash_eq": "hash(a) == hash(b)"}.get(detail)
        if rel and isinstance(base, bool):
            lines.append(f"assert ({rel}) is {base}")
        elif detail == "eq-hash-contract":
            lines += ["if a == b:", "    assert hash(a) == hash(b)  # objects that compare equal must hash equal"]
        else:
            return RegressionTest(f.signature, name, "", skipped=f"relation {detail!r} has no template")
    elif probe == "P4":
        if not pickle_blob:
            return RegressionTest(f.signature, name, "", skipped="no base pickle recorded")
        imports += ["import base64", "import pickle"]
        lines += ["# pickled by the base version (lazy caches warmed first)",
                  f"old = pickle.loads(base64.b64decode({pickle_blob!r}))"]
        # A load failure pins only that the old pickle loads: equality after a round trip can be
        # broken on base already (e.g. #1116's base: cached Infinity sentinels compare by identity).
        if detail.endswith("load"):
            lines.append("assert old is not None  # loading must not raise")
        else:
            lines.append(f"assert old == {call_expr(target, args[0])}")
    else:
        return RegressionTest(f.signature, name, "", skipped=f"no template for {probe}")

    code = "\n".join(lines)
    target_name = split_target(target)[1].removesuffix("()").split(".")[0]
    if not re.search(rf"\b{re.escape(target_name)}\(", code):
        imports = [i for i in imports if i != import_line(target)]
    body = "\n".join(f"    {x}" if x else "" for x in [f'"""{doc}"""', *sort_imports(imports), *lines])
    return RegressionTest(f.signature, name, f"def {name}():\n{body}\n")


STDLIB = {"base64", "pickle"}


def sort_imports(imports: list[str]) -> list[str]:
    """isort order (what ruff's I001 expects): stdlib, blank line, third party; `import x` before
    `from x import ...`; names from one module merged."""
    plain: dict[bool, set[str]] = {True: set(), False: set()}
    froms: dict[str, set[str]] = {}
    for line in imports:
        if line.startswith("import "):
            mod = line[7:]
            plain[mod.split(".")[0] in STDLIB].add(mod)
        else:
            mod, _, names = line[5:].partition(" import ")
            froms.setdefault(mod, set()).update(n.strip() for n in names.split(","))
    out: list[str] = []
    for std in (True, False):
        section = [f"import {m}" for m in sorted(plain[std])]
        section += [f"from {m} import {', '.join(sorted(froms[m], key=str.lower))}"
                    for m in sorted(froms) if (m.split(".")[0] in STDLIB) == std]
        if section:
            out += ([""] if out else []) + section
    return out


def render_file(tests: list[RegressionTest], header: str) -> str:
    """A ready-to-commit test module of the verified tests."""
    good = [t for t in tests if t.verified]
    return (f'"""{header}\n\nGenerated by Breakwater. Each test passed on the base commit and failed on the head '
            'commit when\ngenerated; it pins the old behaviour.\n"""\n\n\n' + "\n\n".join(t.source for t in good))


# ---------------------------------------------------------------------------------------------------
# Sandbox: base pickles and verification

_VERIFY = r'''
import contextlib, json, signal, sys, types

class _Raises:
    def __init__(self, exc):
        self.exc, self.value = exc, None
    def __enter__(self):
        return self
    def __exit__(self, et, ev, tb):
        if et is None:
            raise AssertionError(f"DID NOT RAISE {self.exc.__name__}")
        if not issubclass(et, self.exc):
            return False
        self.value = ev
        return True

pytest = types.ModuleType("pytest")
pytest.raises = lambda exc, **kw: _Raises(exc)
sys.modules["pytest"] = pytest

def _alarm(*a):
    raise TimeoutError("test timed out")

signal.signal(signal.SIGALRM, _alarm)
out = {}
for case in json.load(sys.stdin):
    ns = {}
    signal.alarm(10)
    try:
        exec(compile(case["source"], case["name"], "exec"), ns)
        ns[case["name"]]()
        out[case["name"]] = "pass"
    except AssertionError:
        out[case["name"]] = "fail"
    except BaseException as e:
        out[case["name"]] = "error:" + type(e).__name__
    finally:
        signal.alarm(0)
print(json.dumps(out))
'''


def base_pickles(backend: Backend, image: PairImage, target: str, inputs: list[list[Any]]) -> list[str | None]:
    """Pickles made by the base version (warmed), base64, for P4 tests."""
    req = {"target": target, "observe": [], "ops": [{"op": "pickle_dump", "inputs": inputs, "warm": True}]}
    res = backend.run(image.ref, [image.BASE_PY, image.WORKER], stdin=json.dumps(req), timeout_s=120)
    if res.exit_code != 0:
        return [None] * len(inputs)
    return json.loads(res.stdout)["results"][0]["blobs"]


def verify(backend: Backend, image: PairImage, tests: list[RegressionTest]) -> None:
    """Run every generated test on base and on head (in the sandbox); fills .base and .head."""
    cases = [{"name": t.name, "source": t.source} for t in tests if t.source]
    if not cases:
        return
    for side, py in (("base", image.BASE_PY), ("head", image.HEAD_PY)):
        res = backend.run(image.ref, [py, "-c", _VERIFY], stdin=json.dumps(cases), timeout_s=60 + 12 * len(cases))
        results = json.loads(res.stdout) if res.exit_code == 0 else {}
        for t in tests:
            if t.source:
                setattr(t, side, results.get(t.name, f"error:runner exit {res.exit_code}"))


def for_findings(backend: Backend, image: PairImage, target: str, findings: list[Any], *, item: str = "",
                 labels: dict[str, str] | None = None) -> list[RegressionTest]:
    """Generate and verify one test per finding class."""
    labels = labels or {}
    p4 = [f for f in findings if f.probe == "P4" and labels.get(f.signature) != "intended"]
    blobs = dict(zip((f.signature for f in p4), base_pickles(backend, image, target, [f.args[0] for f in p4]),
                     strict=True)) if p4 else {}
    tests = [generate(f, target, item=item, label=labels.get(f.signature), index=i,
                      pickle_blob=blobs.get(f.signature)) for i, f in enumerate(findings)]
    verify(backend, image, tests)
    return tests

