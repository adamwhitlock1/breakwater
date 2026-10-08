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
    accepts = [f for f in report.findings if f.signature == "P2|outcome|exc:packaging.version.InvalidVersion|ok"]
    assert accepts, render_markdown(report)
    assert "A1/s1" in accepts[0].found_by or "seed" in accepts[0].found_by
    assert (Tier.REASONING, "plan") in llm.calls
