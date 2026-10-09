import json
from pathlib import Path

import pytest

from breakwater.display import show_args
from breakwater.site.build import build, ladder_chart

BACKTEST = Path("artifacts/backtest/packaging-v2")
ADJUDICATION = Path("artifacts/adjudication/packaging-v2")


def _tree(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


@pytest.mark.skipif(not (BACKTEST / "results.json").exists(), reason="published backtest not present")
def test_site_builds_from_published_artifacts_deterministically(tmp_path):
    pages = build(BACKTEST, ADJUDICATION, tmp_path / "a")
    build(BACKTEST, ADJUDICATION, tmp_path / "b")
    assert _tree(tmp_path / "a") == _tree(tmp_path / "b")  # rebuilds give clean diffs
    assert len(pages) == 1 + len(json.loads((BACKTEST / "results.json").read_text())["items"])
    index = (tmp_path / "a" / "index.html").read_text()
    assert "9/9" in index and "Development build" not in index
    pr = (tmp_path / "a" / "pr" / "1082-61967cca.html").read_text()
    assert "known regression: unicode-digits" in pr and '<svg class="chart"' in pr
    assert "http://" not in pr.replace("http://www.w3.org", "")  # no third-party requests
    assert (tmp_path / "a" / "data" / "adjudication.json").exists()


def _mini(tmp_path: Path, provider: str, title: str) -> Path:
    d = tmp_path / "bt"
    d.mkdir()
    finding = {"signature": "P2|outcome|exc:builtins.ValueError|ok|plain", "probe": "P2", "detail": "outcome",
               "args": [["<b>x</b>"]], "base": {"status": "exc", "exc": "builtins.ValueError"},
               "head": {"status": "ok"}, "found_by": ["A1/s1"]}
    item = {"id": "#1", "pr": 1, "title": title, "base": "a" * 40, "head": "b" * 40, "merged": "2026-01-01",
            "after_ultra_release": False, "known": [],
            "targets": [{"target": "m:F", "run_id": "r", "image": "img", "usd": 0.01, "findings": [finding],
                         "arms": {"breakwater": {"classes": [finding["signature"]]}}, "perf": None}]}
    summary = {"items": 1, "known_verified": 0, "known_candidate": 0, "caught_verified": {"breakwater": 0},
               "caught_candidate": {"breakwater": 0}, "items_with_classes": {"breakwater": 1}, "usd": 0.01,
               "provider": provider}
    (d / "results.json").write_text(json.dumps({"corpus": "missing.json", "arms": ["breakwater"], "items": [item],
                                                "summary": summary}))
    (d / "1.json").write_text(json.dumps(item))
    return d


def test_dev_results_need_explicit_opt_in_and_get_a_banner(tmp_path):
    src = _mini(tmp_path, "openrouter", "perf: x")
    with pytest.raises(ValueError, match="only Token Factory"):
        build(src, None, tmp_path / "out")
    build(src, None, tmp_path / "out", allow_dev=True)
    for page in ("index.html", "pr/1.html"):
        assert "Development build (provider: openrouter)" in (tmp_path / "out" / page).read_text()


def test_untrusted_text_is_escaped(tmp_path):
    build(_mini(tmp_path, "tokenfactory", "perf: `fast` <script>alert(1)</script>"), None, tmp_path / "out")
    pr = (tmp_path / "out" / "pr" / "1.html").read_text()
    assert "<script>" not in pr and "&lt;script&gt;" in pr
    assert "<code>fast</code>" in pr  # Markdown code spans in titles still render
    assert "&lt;b&gt;x&lt;/b&gt;" in pr  # inputs are escaped too


def test_long_inputs_are_shortened_with_their_length():
    shown = show_args(["1" + "0" * 4304], "Version")
    assert "…" in shown and "(4,305 chars)" in shown and len(shown) < 100


def test_chart_needs_two_points_and_marks_the_one_x_line():
    assert ladder_chart([{"family_id": "F", "ladder": [{"input_chars": 10, "ratio": 1.2}]}]) == ""
    svg = ladder_chart([{"family_id": "F", "ladder": [{"input_chars": 10, "ratio": 1.2},
                                                      {"input_chars": 1000, "ratio": 2.4}]}])
    assert 'class="axis-one"' in svg and "head slower" in svg


def _run_report(provider="tokenfactory"):
    finding = {"signature": "P2|outcome|exc:pkg.Invalid|ok|non-ascii", "probe": "P2", "detail": "outcome",
               "args": [["\u0661"]], "base": {"status": "exc", "exc": "pkg.Invalid"}, "head": {"status": "ok"},
               "found_by": ["A1/s1", "seed"]}
    return {"run_id": "abc123", "repo": "https://github.com/o/r", "base": "a" * 40, "head": "b" * 40,
            "target": "pkg:Version", "title": "perf: fast path", "provider": provider,
            "semantic": {"image": "bw-pair:x", "backend": "docker", "findings": [finding], "seconds": {"plan": 3.0},
                         "attacks": [{"id": "A1", "assumption": "trusts int()", "why_it_breaks": "Unicode digits",
                                      "input_family": "digits", "example_args": [["1.0"]]}],
                         "strategies": [{"id": "A1/s1", "attack": "A1", "valid": True, "findings": 1}]},
            "adjudication": {"verdicts": [{"signature": finding["signature"], "label": "likely-bug",
                                           "votes": {"likely-bug": 3}, "rationale": "<b>no</b>", "evidence": [],
                                           "rejected": [], "reason": ""}]},
            "usd_by_tier": {"reasoning": 0.05, "volume": 0.001}}


def test_audit_run_page_and_live_page(tmp_path):
    from breakwater.site.build import write_live_page, write_run_page

    run = tmp_path / "run"
    run.mkdir()
    (run / "report.json").write_text(json.dumps(_run_report()))
    html = write_run_page(run).read_text()
    assert "BLOCK" in html and "trusts int()" in html and "1/1 valid, 1 hits" in html
    assert "Nemotron 3 Ultra" in html and "$0.051" in html  # cost by tier, with total
    assert "&lt;b&gt;no&lt;/b&gt;" in html and "no baseline" not in html  # escaped; no backtest arms here
    assert "https://github.com/o/r/commit/" + "a" * 40 in html
    assert 'href="index.html' not in html  # standalone: no links into a site that isn't there
    assert "Model (Nebius Token Factory)" in html
    (run / "report.json").write_text(json.dumps(_run_report("openrouter")))
    dev = write_run_page(run).read_text()
    assert "Model (openrouter)" in dev and "Development build (provider: openrouter)" in dev
    live = write_live_page(run).read_text()
    assert '<script src="assets/live.js"></script>' in live and (run / "assets" / "live.js").exists()


def test_site_includes_audit_runs_and_gates_dev_runs(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    (run / "report.json").write_text(json.dumps(_run_report("openrouter")))
    src = _mini(tmp_path, "tokenfactory", "perf: x")
    with pytest.raises(ValueError, match="only Token Factory"):
        build(src, None, tmp_path / "out", runs=[run])
    (run / "report.json").write_text(json.dumps(_run_report()))
    build(src, None, tmp_path / "out", runs=[run])
    assert 'href="runs/abc123.html"' in (tmp_path / "out" / "index.html").read_text()
    assert (tmp_path / "out" / "runs" / "abc123.html").exists() and (tmp_path / "out" / "data" / "runs" / "abc123.json").exists()
