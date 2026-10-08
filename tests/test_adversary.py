import json
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from breakwater.adversary import audit, extract_code, extract_json, render_markdown, validate_strategy
from breakwater.models import Tier


def test_validate_strategy_accepts_plain_strategies_and_rejects_escape_hatches():
    assert validate_strategy("strategy = st.text(min_size=1)") is None
    assert validate_strategy("import os\nstrategy = st.text()") == "imports are not allowed"
    assert "not allowed" in validate_strategy("strategy = st.text().__class__")
    assert "not allowed" in validate_strategy("strategy = eval('st.text()')")
    assert validate_strategy("s = st.text()") == "code must assign `strategy`"
    assert validate_strategy("strategy = (") .startswith("syntax error")


def test_extractors():
    assert extract_code("Here:\n```python\nstrategy = st.just('1')\n```\nDone") == "strategy = st.just('1')"
    assert extract_json('Sure! {"attacks": []} hope that helps') == {"attacks": []}


class ScriptedLLM:
    """Stands in for Nemotron: a fixed plan and fixed strategies, so the pipeline is testable offline."""

    PLAN = {"attacks": [{
        "id": "A1",
        "routing_condition": "no letters, '!' or '+' in the string",
        "assumption": "the fast path trusts int() to see only ASCII digits",
        "why_it_breaks": "int() accepts any Unicode decimal digit and surrounding whitespace",
        "input_family": "dotted versions with non-ASCII digits or spaces",
        "example_args_json": ['["1.0"]', '["1. 0"]'],
    }]}
    STRATEGIES = [
        "```python\ndigits = st.text(alphabet=st.characters(categories=['Nd']), min_size=1, max_size=3)\n"
        "strategy = st.builds(lambda a, b: a + '.' + b, digits, digits)\n```",
        "```python\nimport os\nstrategy = st.just('1.0')\n```",  # rejected by validation
    ]

    def __init__(self):
        self.calls = []

    def complete(self, tier, messages, **kw):
        self.calls.append((tier, kw.get("purpose")))
        if tier == Tier.REASONING:
            return SimpleNamespace(text=json.dumps(self.PLAN), texts=[json.dumps(self.PLAN)])
        n = kw.get("n", 1)
        texts = (self.STRATEGIES * n)[:n]
        return SimpleNamespace(text=texts[0], texts=texts)


def _harness() -> bool:
    return bool(shutil.which("docker")) and subprocess.run(
        ["docker", "image", "inspect", "breakwater-harness"], capture_output=True).returncode == 0


@pytest.mark.skipif(not _harness(), reason="needs Docker and the breakwater-harness image")
def test_audit_pipeline_finds_pr1082_bug_with_scripted_llm():
    from breakwater.backends.docker import DockerBackend
    from breakwater.images import build_pair, git_req
    from breakwater.probes import Target
    from breakwater.repo import gather

    repo = "https://github.com/pypa/packaging"
    ctx = gather(repo, "59f183fe90da", "61967cca278d", "packaging.version:Version")
    image = build_pair(git_req(repo, "59f183fe90da"), git_req(repo, "61967cca278d"))
    llm = ScriptedLLM()
    report = audit(ctx, image, llm, DockerBackend(), Target("packaging.version:Version"),
                   n_attacks=1, strategies_per_attack=2, max_examples=200, log=lambda *_: None)

    assert [s.valid for s in report.strategies] == [True, False]
    accepts = [f for f in report.findings if f.signature == "P2|outcome|exc:packaging.version.InvalidVersion|ok|non-ascii"]
    assert accepts, render_markdown(report)
    assert "A1/s1" in accepts[0].found_by or "seed" in accepts[0].found_by
    assert (Tier.REASONING, "plan") in llm.calls


def test_strip_provided_imports_keeps_other_imports_for_validation():
    from breakwater.perf import strip_provided_imports

    src = "import random\nfrom string import digits as d, ascii_letters\nimport os\ndef make(n):\n    return [['1' * n]]"
    out = strip_provided_imports(src)
    assert "import random" not in out
    assert "d = string.digits" in out and "ascii_letters = string.ascii_letters" in out
    assert "import os" in out


def test_perf_verdicts():
    from breakwater.perf import LadderPoint, PerfFinding

    def finding(ratios, slopes=(1.0, 1.0)):
        f = PerfFinding("F1", "suspected_slowdown", "fam", "why")
        f.ladder = [LadderPoint(n, 100.0, 100.0 * r, float(n)) for n, r in zip((4, 16, 64, 256), ratios, strict=True)]
        f.slope_base, f.slope_head = slopes
        return f

    assert finding([1.2, 1.3, 1.4, 1.5]).verdict == "slower"
    assert finding([0.5, 0.6, 0.7, 0.8]).verdict == "faster"
    assert finding([0.4, 0.6, 0.8, 0.9], slopes=(0.5, 0.9)).verdict == "faster"  # shrinking speedup is not a regression
    assert finding([0.8, 0.95, 1.1, 1.3], slopes=(1.0, 1.4)).verdict == "complexity-regression"
    assert finding([0.99, 1.0, 1.01, 1.02]).verdict == "neutral"


def test_unescape_code_only_when_double_escaped():
    from breakwater.perf import unescape_code

    assert unescape_code("def make(n):\\n    return [[\\\"1\\\" * n]]") == 'def make(n):\n    return [["1" * n]]'
    one_liner = "def make(n):\n    return [['a\\nb']]"
    assert unescape_code(one_liner) == one_liner


def test_backtest_matching_and_literal_args():
    from breakwater.backtest import generic_strategy, literal_args, matches

    sig = "P2|outcome|exc:packaging.version.InvalidVersion|ok|non-ascii+whitespace"
    assert matches(sig, {"probe": "P2", "traits": "non-ascii"})
    assert not matches(sig, {"probe": "P2", "traits": "long-digits"})
    assert matches("P3|eq|True|False", {"probe": "P3", "detail": "eq"})
    assert not matches("P3|lt|True|False", {"probe": "P3", "detail": "eq"})
    args = literal_args(["a", "b", "c"], ["str", "list[str]"])
    assert len(args) == 3 and isinstance(args[0][1], list)
    assert generic_strategy(["str"]) == "strategy = st.text(max_size=30)"


def test_equivalents_keep_numeric_value():
    from breakwater.mutate import equivalents

    assert equivalents("1.2") == ["1.2.0", "01.2"]
    assert equivalents(">=1.0,!=2.0") == [">=1.0.0,!=2.0", ">=01.0,!=2.0", ">=1.0,!=2.0,>=1.0", ">=1.0,!=2.0,>=1.0.0"]
