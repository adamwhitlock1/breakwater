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


def test_events_are_ordered_and_reserved_fields_cannot_be_overwritten(tmp_path):
    import json
    import threading

    import pytest

    from breakwater.events import NULL, Events

    ev = Events(tmp_path / "e.jsonl")
    threads = [threading.Thread(target=lambda i=i: ev("x", i=i)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    lines = [json.loads(x) for x in (tmp_path / "e.jsonl").read_text().splitlines()]
    assert [e["seq"] for e in lines] == list(range(1, 21)) and {e["kind"] for e in lines} == {"x"}
    with pytest.raises(ValueError, match="reserved"):
        ev("family", kind="claimed_speedup")  # a perf family's kind once crashed a live run
    with pytest.raises(ValueError, match="reserved"):
        NULL("x", t=1)  # checked even when not recording, so tests catch it


def test_install_lines_for_packages_scripts_and_pinned_dates():
    from breakwater.images import _install_lines, req_for

    pip = req_for("https://github.com/o/r", "abc", {"exclude_newer": "2026-01-27"})
    assert _install_lines(pip, "base") == [
        'RUN uv pip install -q --exclude-newer 2026-01-27 --python /envs/base/bin/python "git+https://github.com/o/r@abc"']
    src = req_for("https://github.com/o/s", "def", {"mode": "src", "subdir": "scripts", "deps": ["pyyaml"]})
    lines = _install_lines(src, "head")
    assert lines[0] == "RUN git clone -q https://github.com/o/s /src/head && git -C /src/head checkout -q def"
    assert 'uv pip install -q --python /envs/head/bin/python "pyyaml"' in lines[1]
    assert "breakwater_src.pth" in lines[2] and "/src/head/scripts" in lines[2]
    assert req_for("https://github.com/o/r", "abc") == "git+https://github.com/o/r@abc"


def test_bare_constructor_method_targets(monkeypatch):
    import sys
    import types

    from breakwater.harness.worker import resolve
    from breakwater.regress import call_expr, import_line

    mod = types.ModuleType("bw_app")

    class App:
        def parse(self, s):
            return s.split(";")

    mod.App = App
    monkeypatch.setitem(sys.modules, "bw_app", mod)
    assert resolve("bw_app:App()#parse")("a;b") == ["a", "b"]
    assert call_expr("bw_app:App()#parse", ["a;b"]) == "App().parse('a;b')"
    assert import_line("bw_app:App()#parse") == "from bw_app import App"


def test_requests_that_hang_hit_the_deadline_and_retry(monkeypatch):
    import time
    from types import SimpleNamespace

    from breakwater import llm

    calls = []

    def create(**kw):
        calls.append(time.monotonic())
        if len(calls) == 1:
            time.sleep(1.0)  # a provider trickling keep-alive bytes forever
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="ok"), finish_reason="stop")],
                               usage=None)

    monkeypatch.setattr(llm, "REQUEST_DEADLINE_S", 0.2)
    monkeypatch.setattr(llm, "RETRY_DELAYS_S", (0,))
    client = llm.Nemotron.__new__(llm.Nemotron)
    client.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    t0 = time.monotonic()
    assert client._create(model="m").choices[0].message.content == "ok"
    assert len(calls) == 2 and time.monotonic() - t0 < 0.9  # abandoned the hung call, didn't wait it out
