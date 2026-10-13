import ast
import json
import os
import subprocess
import sys
from types import SimpleNamespace

from breakwater.backends.base import RunResult
from breakwater.images import PairImage
from breakwater.regress import generate, py_literal, sort_imports, verify

BASE_SRC = '''
class InvalidVer(ValueError):
    pass

class Ver:
    def __init__(self, s):
        if not s.isascii() or " " in s:
            raise InvalidVer(s)
        self.parts = tuple(int(p) for p in s.split("."))
    def __str__(self):
        return ".".join(map(str, self.parts))
    def __eq__(self, other):
        return self.parts == other.parts
    def __hash__(self):
        return hash(self.parts)
'''
HEAD_SRC = '''
class InvalidVer(ValueError):
    pass

class Ver:  # "faster": trusts int(), keeps the raw string
    def __init__(self, s):
        self.raw = s
        self.parts = tuple(int(p) for p in s.split("."))
    def __str__(self):
        return self.raw
    def __eq__(self, other):
        return self.raw == other.raw
    def __hash__(self):
        return hash(self.parts)
'''


class LocalBackend:
    """Runs commands with this interpreter; the 'base' and 'head' sides import different toyver modules."""

    name = "local"

    def __init__(self, tmp):
        self.paths = {}
        for side, src in (("base", BASE_SRC), ("head", HEAD_SRC)):
            d = tmp / side
            d.mkdir()
            (d / "toyver.py").write_text(src)
            self.paths[PairImage.BASE_PY if side == "base" else PairImage.HEAD_PY] = str(d)

    def run(self, image_ref, cmd, *, stdin=None, timeout_s=60, **kw):
        env = {**os.environ, "PYTHONPATH": self.paths[cmd[0]]}
        p = subprocess.run([sys.executable, *cmd[1:]], input=stdin, capture_output=True, text=True, env=env,
                           timeout=timeout_s)
        return RunResult(p.stdout, p.stderr, p.returncode, 0, self.name)


def F(probe, detail, args, base, head, sig=None):
    return SimpleNamespace(probe=probe, detail=detail, args=args, base=base, head=head,
                           signature=sig or f"{probe}|{detail}")


def test_literals_are_valid_python_and_compress_long_runs():
    assert py_literal("1" + "0" * 4304) == "'1' + '0' * 4304"
    assert py_literal("\x1bÀ") == repr("\x1bÀ")
    assert ast.literal_eval(py_literal(["a", 1, None, {"k": [True]}])) == ["a", 1, None, {"k": [True]}]
    assert sort_imports(["from p.v import V", "import pickle", "from p.v import E", "import pytest"]) == \
        ["import pickle", "", "import pytest", "from p.v import E, V"]


def test_generated_tests_pass_on_base_and_fail_on_head(tmp_path):
    findings = [
        F("P2", "outcome", [["١"]], {"status": "exc", "exc": "toyver.InvalidVer"}, {"status": "ok"}),
        F("P1", "str", [["01.0"]], "1.0", "01.0"),
        F("P3", "eq", [["1.0"], ["01.0"]], True, False),
        F("P2", "outcome", [["1"]], {"status": "ok"}, {"status": "exc", "exc": "builtins.TypeError"}),  # not a real diff
    ]
    tests = [generate(f, "toyver:Ver", item="toy", index=i) for i, f in enumerate(findings)]
    tests.append(generate(F("P1", "str", [["2"]], "2", "x"), "toyver:Ver", label="intended", index=9))
    verify(LocalBackend(tmp_path), PairImage("local", "b", "h"), tests)
    assert [t.verified for t in tests[:3]] == [True, True, True]
    assert "assert type(excinfo.value) is InvalidVer" in tests[0].source  # exact type, not just pytest.raises
    assert (tests[3].base, tests[3].head, tests[3].verified) == ("pass", "pass", False)  # never offered
    assert tests[4].skipped.startswith("adjudicated intended") and tests[4].source == ""
    for t in tests[:4]:
        compile(t.source, t.name, "exec")


def test_pickle_tests_pin_loading_or_equality():
    load = generate(F("P4", "base->head load", [["1"]], "loads", {"status": "exc"}), "toyver:Ver", pickle_blob="QUJD")
    eq = generate(F("P4", "base->head eq-fresh", [["1"]], True, False), "toyver:Ver", pickle_blob="QUJD")
    assert "assert old is not None" in load.source and "from toyver import Ver" not in load.source
    assert "assert old == Ver('1')" in eq.source and "from toyver import Ver" in eq.source
    assert generate(F("P4", "base->head load", [["1"]], "loads", {}), "toyver:Ver").skipped == "no base pickle recorded"


def test_method_targets_and_value_observations():
    t = generate(F("P1", "value", [[">=1", ["1.0", "2.0"]]], ["2.0"], ["1.0", "2.0"]), "pkg.s:SpecifierSet#filter")
    assert "assert list(SpecifierSet('>=1').filter(['1.0', '2.0'])) == ['2.0']" in t.source
    assert json.dumps(t.to_json())  # serialisable for the report


def test_generator_methods_are_iterated_inside_the_check():
    t = generate(F("P2", "outcome", [["1²"]], {"status": "exc", "exc": "builtins.Exception"},
                   {"status": "exc", "exc": "builtins.ValueError"}), "lexer:Lexer#generate_tokens")
    assert "    result = Lexer('1²').generate_tokens()" in t.source and "        list(result)" in t.source
    compile(t.source, t.name, "exec")
