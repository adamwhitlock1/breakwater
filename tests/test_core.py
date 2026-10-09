import shutil
import subprocess

import pytest

from breakwater import ledger
from breakwater.llm import strip_think
from breakwater.models import Tier, model_for


def test_strip_think_removes_closed_and_unterminated_blocks():
    assert strip_think("<think>hmm</think>\n0.05") == "0.05"
    assert strip_think("answer <think>ran out of budg") == "answer"
    assert strip_think(None) == ""


def test_tier_costs_use_catalog_prices():
    ultra = model_for(Tier.REASONING)
    assert ultra.cost(1_000_000, 1_000_000) == pytest.approx(4.0)
    assert model_for(Tier.VOLUME).cost(1_000_000, 0) == pytest.approx(0.06)


def test_model_override_from_env(monkeypatch):
    monkeypatch.setenv("BREAKWATER_MODEL_VOLUME", "nvidia/nemotron-3_5-lightning")
    assert model_for(Tier.VOLUME).id == "nvidia/nemotron-3_5-lightning"


def test_ledger_summarize_by_tier(tmp_path):
    path = tmp_path / "ledger.jsonl"
    for tier, usd in [("volume", 0.01), ("volume", 0.02), ("reasoning", 0.5)]:
        ledger.append(ledger.Entry(tier, "m", "test", 10, 20, 0, usd, 5, True, run_id="r1"), path)
    totals = ledger.summarize(path, run_id="r1")
    assert totals["volume"]["calls"] == 2
    assert totals["volume"]["usd"] == pytest.approx(0.03)
    assert totals["reasoning"]["tokens_out"] == 20


def _harness_image() -> bool:
    if not shutil.which("docker"):
        return False
    return subprocess.run(["docker", "image", "inspect", "breakwater-harness"], capture_output=True).returncode == 0


@pytest.mark.skipif(not _harness_image(), reason="needs the breakwater-harness Docker image")
def test_docker_backend_reports_second_clock():
    from breakwater.backends.docker import DockerBackend

    res = DockerBackend().run("breakwater-harness", ["python", "-c", "print(sum(range(3_000_000)))"])
    assert res.exit_code == 0
    assert res.stdout.strip() == str(sum(range(3_000_000)))
    assert res.resources.user_cpu_s and res.resources.user_cpu_s > 0
    assert "__BW_RUSAGE__" not in res.stderr


def test_provider_request_translation():
    from breakwater.llm import request_kwargs
    from breakwater.models import Provider

    schema = {"type": "json_schema", "json_schema": {"name": "x", "schema": {"type": "object"}}}
    msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]
    common = dict(max_tokens=10, temperature=1.0, top_p=0.95, service_tier="flex")

    tf = request_kwargs(Provider.TOKENFACTORY, model_for(Tier.REASONING, Provider.TOKENFACTORY), msgs, thinking=True,
                        response_format=schema, template_kwargs={"medium_effort": True}, **common)
    assert tf["extra_body"] == {"chat_template_kwargs": {"enable_thinking": True, "medium_effort": True}}
    assert tf["response_format"] == schema and tf["service_tier"] == "flex" and tf["messages"] == msgs

    ultra = model_for(Tier.REASONING, Provider.OPENROUTER)
    assert ultra.id.endswith(":free") and not ultra.json_schema
    orr = request_kwargs(Provider.OPENROUTER, ultra, msgs, thinking=True, response_format=schema,
                         template_kwargs={"medium_effort": True}, **common)
    assert orr["extra_body"] == {"reasoning": {"effort": "medium"}}
    assert "response_format" not in orr and "service_tier" not in orr
    assert "JSON Schema" in orr["messages"][-1]["content"] and msgs[-1]["content"] == "u"  # caller's list untouched
    off = request_kwargs(Provider.OPENROUTER, model_for(Tier.VOLUME, Provider.OPENROUTER), msgs, thinking=False,
                         response_format=None, template_kwargs=None, **common)
    assert off["extra_body"] == {"reasoning": {"enabled": False}}


def test_provider_selection_and_overrides(monkeypatch):
    from breakwater.models import Provider, active_provider

    monkeypatch.delenv("BREAKWATER_PROVIDER", raising=False)
    assert active_provider() is Provider.TOKENFACTORY
    monkeypatch.setenv("BREAKWATER_PROVIDER", "OpenRouter")
    assert active_provider() is Provider.OPENROUTER
    monkeypatch.setenv("BREAKWATER_OPENROUTER_MODEL_REASONING", "nvidia/nemotron-3-ultra-550b-a55b")
    paid = model_for(Tier.REASONING)
    assert paid.json_schema and paid.usd_per_m_out == pytest.approx(2.2)
    monkeypatch.setenv("BREAKWATER_PROVIDER", "bogus")
    with pytest.raises(ValueError):
        active_provider()


def test_ledger_splits_by_provider(tmp_path):
    path = tmp_path / "ledger.jsonl"
    ledger.append(ledger.Entry("volume", "m", "p", 1, 1, 0, 0.5, 1, True), path)
    ledger.append(ledger.Entry("volume", "m", "p", 1, 1, 0, 0.0, 1, True, provider="openrouter"), path)
    assert ledger.providers(path) == ["tokenfactory", "openrouter"]
    assert ledger.summarize(path, provider="tokenfactory")["volume"]["usd"] == pytest.approx(0.5)
    assert ledger.summarize(path, provider="openrouter")["volume"]["calls"] == 1
