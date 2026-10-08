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
