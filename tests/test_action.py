"""Runs the composite action's own shell steps (action.yml) locally, with GitHub's files faked."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
ACTION = yaml.safe_load((ROOT / "action.yml").read_text())
DEMO = ROOT / "artifacts/demo/pr1082-61967cca-sandboxes"


def step(step_id: str) -> dict:
    return next(s for s in ACTION["runs"]["steps"] if s.get("id") == step_id)


def run_step(script: str, env: dict, tmp: Path) -> tuple[subprocess.CompletedProcess, dict]:
    out, summary = tmp / "out", tmp / "summary"
    out.write_text("")
    summary.write_text("")
    full = {**os.environ, **env, "GITHUB_OUTPUT": str(out), "GITHUB_STEP_SUMMARY": str(summary),
            "GITHUB_ACTION_PATH": str(ROOT)}
    proc = subprocess.run(["bash", "-e", "-c", script], env=full, capture_output=True, text=True)
    outputs = dict(line.split("=", 1) for line in out.read_text().splitlines() if "=" in line)
    return proc, outputs


def test_action_metadata():
    assert set(ACTION["inputs"]) >= {"target", "observe", "mode", "fail-on", "comment", "nebius-api-key",
                                    "nebius-project-id"}
    assert ACTION["inputs"]["target"]["required"] is True
    assert ACTION["runs"]["using"] == "composite"
    # Untrusted values (PR title, inputs) reach scripts through env, never ${{ }} inside `run:`.
    for s in ACTION["runs"]["steps"]:
        assert "${{" not in s.get("run", ""), s.get("id")


def test_skips_without_a_key_and_outside_pull_requests(tmp_path):
    script = step("check")["run"]
    proc, out = run_step(script, {"KEY": "", "EVENT": "pull_request"}, tmp_path)
    assert out["run"] == "false" and "fork" in proc.stdout
    proc, out = run_step(script, {"KEY": "k", "EVENT": "pull_request_target"}, tmp_path)
    assert out["run"] == "false" and "pull_request events only" in proc.stdout
    _, out = run_step(script, {"KEY": "k", "EVENT": "pull_request"}, tmp_path)
    assert out["run"] == "true" and out["backend"] == "docker"
    _, out = run_step(script, {"KEY": "k", "PROJECT": "p", "EVENT": "pull_request"}, tmp_path)
    assert out["run"] == "true" and out["backend"] == "contree"


@pytest.mark.skipif(not (DEMO / "report.json").exists() or not shutil.which("uv"), reason="demo run or uv missing")
def test_result_and_fail_steps_on_the_recorded_demo_run(tmp_path):
    run = tmp_path / "run"
    shutil.copytree(DEMO, run)
    proc, out = run_step(step("result")["run"], {"RUN": str(run), "REPO": "o/r", "PR": "1", "POST": "false",
                                                 "ARTIFACT_URL": "https://x/a", "RUN_URL": "https://x/r"}, tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert out["verdict"] == "BLOCK"
    summary = (tmp_path / "summary").read_text()
    assert "## 🛑 Breakwater: BLOCK" in summary and "Token Factory Sandboxes microVMs" in summary
    fail = ACTION["runs"]["steps"][-1]["run"]
    assert run_step(fail, {"VERDICT": "BLOCK", "FAIL_ON": "block"}, tmp_path)[0].returncode == 1
    assert run_step(fail, {"VERDICT": "REVIEW", "FAIL_ON": "block"}, tmp_path)[0].returncode == 0
    assert run_step(fail, {"VERDICT": "REVIEW", "FAIL_ON": "review"}, tmp_path)[0].returncode == 1
    assert run_step(fail, {"VERDICT": "BLOCK", "FAIL_ON": "never"}, tmp_path)[0].returncode == 0
