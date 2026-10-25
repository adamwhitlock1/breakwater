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


@pytest.mark.skipif(not (Path("artifacts/backtest/packaging-v3") / "results.json").exists(), reason="v3 not present")
def test_v3_site_reuses_v2_perf_and_says_so(tmp_path):
    v3, v2 = Path("artifacts/backtest/packaging-v3"), BACKTEST
    build(v3, Path("artifacts/adjudication/packaging-v3"), tmp_path / "s", perf_from=v2)
    pr = (tmp_path / "s" / "pr" / "1030.html").read_text()
    assert '<svg class="chart"' in pr and "Measured in backtest <code>packaging-v2</code>" in pr
    index = (tmp_path / "s" / "index.html").read_text()
    assert "Perf columns come from backtest <code>packaging-v2</code>" in index and "4.52×" in index
    assert (tmp_path / "s" / "data" / "perf-packaging-v2.json").exists()
    with pytest.raises(ValueError, match="different corpus"):
        other = _mini(tmp_path, "tokenfactory", "x")
        build(v3, None, tmp_path / "t", perf_from=other)


def test_perf_verdicts():
    from breakwater.site.build import combine, perf_verdict

    def summary(ratio, verdict):
        return {"worst_valid_ratio": ratio, "worst_family": "f",
                "report": {"findings": [{"family": "f", "verdict": verdict}]}}

    assert perf_verdict(summary(393.4, "complexity-regression"))[0] == "BLOCK"
    assert perf_verdict(summary(1.34, "slower"))[0] == "REVIEW"
    assert perf_verdict(summary(1.10, "slower")) == ("PASS", "")  # small constant overhead doesn't flip a verdict
    assert perf_verdict(None) == ("PASS", "")
    assert combine("REVIEW", ("BLOCK", "x")) == "BLOCK" and combine("BLOCK", ("REVIEW", "x")) == "BLOCK"


CODEFLASH = Path("artifacts/backtest/codeflash-v1")


@pytest.mark.skipif(not (CODEFLASH / "results.json").exists(), reason="codeflash results not present")
def test_extra_corpus_is_a_self_contained_sub_site(tmp_path):
    from breakwater.site.build import Corpus

    build(BACKTEST, ADJUDICATION, tmp_path / "s", extras=[Corpus(
        "codeflash", CODEFLASH, Path("artifacts/adjudication/codeflash-v1"), Path("artifacts/regress/codeflash-v1"))])
    sub = tmp_path / "s" / "codeflash"
    page = (sub / "pr" / "json_repair-113.html").read_text()
    assert '<span class="verdict block">BLOCK</span>' in page and "complexity regression" in page
    assert '<a href="../index.html">Codeflash</a>' in page and "mangiucugna/json_repair#113" in page
    assert (sub / "data" / "backtest" / "json_repair-113.json").exists()  # slugged; the source file has a "#"
    assert (sub / "tests" / "test_Math_Interpreter_1.py").exists()
    index = (sub / "index.html").read_text()
    assert "109% faster" in index and "393" in index
    root = (tmp_path / "s" / "index.html").read_text()
    assert 'href="codeflash/index.html">Codeflash</a>' in root and "Also audited: 10 merged AI-written speedups" in root


JUDGE_BUNDLE = Path("artifacts/judge/packaging-1082.json")


@pytest.mark.skipif(not JUDGE_BUNDLE.exists(), reason="judge bundle not built")
def test_judge_box_python_reproduces_backtest_classes(monkeypatch, tmp_path):
    import sys

    from breakwater.harness import compare
    from breakwater.site.assets import judge  # noqa: F401  (also checks it imports cleanly)

    monkeypatch.setitem(sys.modules, "compare", compare)  # in the browser it's a top-level module
    bundle = json.loads(JUDGE_BUNDLE.read_text())
    assert judge.load(bundle["versions"], root=str(tmp_path)) == ["base", "pr", "merged", "fixed"]
    digits = judge.run("١.٢")  # Arabic-Indic digits
    assert digits["outcomes"]["base"]["status"] == "exc" and digits["outcomes"]["pr"]["status"] == "ok"
    # Same class signature as the sandboxed backtest found for 1082@61967cca.
    assert digits["diffs"]["pr"][0]["signature"] == "P2|outcome|exc:packaging.version.InvalidVersion|ok|non-ascii"
    assert digits["diffs"]["merged"] == [] and digits["diffs"]["fixed"] == []  # review fixed it before merge
    huge = judge.run("1" + "0" * 4400)  # Python's int-digit limit
    assert [d["signature"] for d in huge["diffs"]["merged"]] == [
        "P2|outcome|exc:builtins.ValueError|exc:packaging.version.InvalidVersion|long-digits"]
    assert huge["diffs"]["fixed"] == []  # #1155 restored ValueError
    assert judge.run("1.0")["diffs"] == {"pr": [], "merged": [], "fixed": []}



@pytest.mark.skipif(not JUDGE_BUNDLE.exists() or not (BACKTEST.parent / "packaging-v3").exists(), reason="inputs missing")
def test_judge_page_links_divergences_to_backtest_cards(tmp_path):
    v3 = Path("artifacts/backtest/packaging-v3")
    build(v3, Path("artifacts/adjudication/packaging-v3"), tmp_path / "s", judge=JUDGE_BUNDLE)
    html = (tmp_path / "s" / "judge.html").read_text()
    meta = json.loads(html.split('id="judge-meta">')[1].split("</script>")[0].replace("<\\/", "</"))
    assert [v["key"] for v in meta["versions"]] == ["base", "pr", "merged", "fixed"]
    assert "files" not in meta["versions"][0]  # sources load from data/judge.json, not the page
    sig = "P2|outcome|exc:packaging.version.InvalidVersion|ok|non-ascii"
    assert meta["known"]["pr"][sig]["href"] == "pr/1082-61967cca.html"
    assert (tmp_path / "s" / "data" / "judge.json").exists() and (tmp_path / "s" / "assets" / "compare.py").exists()
    assert 'href="judge.html">Try it</a>' in (tmp_path / "s" / "index.html").read_text()


def test_backend_of_infers_from_the_image_ref_and_prefers_the_record():
    from breakwater.site.build import backend_of

    assert backend_of("bw-pair:7a0f18c452d5a146") == "docker"
    assert backend_of("dbe8dafe-78c4-4fc8-b8c2-a5adaad2ed49") == "contree"
    assert backend_of("dbe8dafe-78c4-4fc8-b8c2-a5adaad2ed49", "docker") == "docker"  # the artifact's word wins


def _mini_backend(tmp_path: Path, name: str, image: str, backend: str | None, worst: float | None) -> Path:
    """A one-item backtest on a given backend (image ref + optional recorded backend)."""
    d = tmp_path / name
    d.mkdir()
    finding = {"signature": "P2|outcome|exc:builtins.ValueError|ok|plain", "probe": "P2", "detail": "outcome",
               "args": [["x"]], "base": {"status": "exc", "exc": "builtins.ValueError"}, "head": {"status": "ok"},
               "found_by": ["A1/s1"]}
    perf = None
    if worst:
        perf = {"worst_valid_ratio": worst, "worst_family": "f", "slower_families": [], "speedup_ratio_small": None,
                "report": {"findings": [{"family_id": "F1", "family": "f", "verdict": "slower", "kind": "suspected_slowdown",
                                         "origin": "plan", "valid_fraction": 1.0, "worst_ratio": worst,
                                         "ladder": [{"n": 2, "input_chars": 10, "ratio": worst, "judged": True},
                                                    {"n": 4, "input_chars": 100, "ratio": worst, "judged": True}]}]}}
    target = {"target": "m:F", "run_id": "r", "image": image, "usd": 0.01, "findings": [finding],
              "arms": {"breakwater": {"classes": [finding["signature"]], "known": ["k1"]}}, "perf": perf}
    if backend:
        target["backend"] = backend
    item = {"id": "#1", "pr": 1, "title": "perf: x", "base": "a" * 40, "head": "b" * 40, "merged": "2026-01-01",
            "after_ultra_release": False, "known": [{"id": "k1", "status": "verified", "match": {"probe": "P2"}}],
            "targets": [target]}
    summary = {"items": 1, "known_verified": 1, "known_candidate": 0, "caught_verified": {"breakwater": 1},
               "caught_candidate": {"breakwater": 0}, "items_with_classes": {"breakwater": 1}, "usd": 0.01,
               "provider": "tokenfactory"}
    (d / "results.json").write_text(json.dumps({"corpus": "missing.json", "arms": ["breakwater"], "items": [item],
                                                "summary": summary}))
    (d / "1.json").write_text(json.dumps(item))
    return d


def test_every_page_and_card_names_its_backend_and_image(tmp_path):
    uuid = "dbe8dafe-78c4-4fc8-b8c2-a5adaad2ed49"
    build(_mini_backend(tmp_path, "sb", uuid, "contree", None), None, tmp_path / "out")
    index = (tmp_path / "out" / "index.html").read_text()
    assert f'<span class="chip backend sm contree" title="image {uuid}">Sandboxes</span>' in index
    assert "Backend: where the untrusted code ran" in index
    pr = (tmp_path / "out" / "pr" / "1.html").read_text()
    assert f"Token Factory Sandboxes · image <code>{uuid}</code>" in pr  # on the card
    assert "--backend contree --input" in pr  # the reproduce command re-runs where it was found
    assert "<th>Backend</th>" in pr and "<td>Token Factory Sandboxes</td>" in pr  # receipt
    build(_mini_backend(tmp_path, "dk", "bw-pair:abc", None, None), None, tmp_path / "out2")  # older artifact: no record
    assert 'class="chip backend sm docker"' in (tmp_path / "out2" / "index.html").read_text()
    assert "local Docker · image <code>bw-pair:abc</code>" in (tmp_path / "out2" / "pr" / "1.html").read_text()


def test_compare_sub_site_puts_the_backends_side_by_side(tmp_path):
    from breakwater.site.build import Corpus, compare_rows, load

    main = _mini_backend(tmp_path, "docker", "bw-pair:abc", "docker", 2.44)
    sub = _mini_backend(tmp_path, "sandboxes", "dbe8dafe-78c4-4fc8-b8c2-a5adaad2ed49", "contree", 2.51)
    rows = compare_rows(load(main, None)[2], load(sub, None)[2])
    assert len(rows) == 1 and rows[0]["same_verdict"] and rows[0]["same_known"]
    assert abs(rows[0]["worst_delta"] - (2.51 - 2.44) / 2.44) < 1e-9
    build(main, None, tmp_path / "out", extras=[Corpus("sandboxes", sub, compare=True)])
    index = (tmp_path / "out" / "sandboxes" / "index.html").read_text()
    assert rows[0]["families"][0]["family"] == "f" and abs(rows[0]["families"][0]["gap"] - 0.07 / 2.44) < 1e-9
    assert "1/1" in index and "same verdict on both backends" in index and "3%" in index  # the shared family's gap
    assert "bw-pair:abc" in index and "dbe8dafe-78c4-4fc8-b8c2-a5adaad2ed49" in index  # both images, every row
    assert (tmp_path / "out" / "sandboxes" / "pr" / "1.html").exists()
    root = (tmp_path / "out" / "index.html").read_text()
    assert "Checked on Token Factory Sandboxes: 1/1 verdicts agree" in root
    assert 'href="sandboxes/index.html">Sandboxes</a>' in root


def test_run_page_names_backend_and_image_from_the_receipt_when_the_semantic_report_lacks_them(tmp_path):
    from breakwater.site.build import run_provenance

    rep = _run_report()
    assert run_provenance(rep) == ("docker", "bw-pair:x")
    rep["semantic"].pop("backend"), rep["semantic"].pop("image")
    rep["sandbox"] = {"backend": "contree", "image": "dbe8dafe-78c4-4fc8-b8c2-a5adaad2ed49", "runs": 3, "cpu_s": 1.0}
    assert run_provenance(rep) == ("contree", "dbe8dafe-78c4-4fc8-b8c2-a5adaad2ed49")
