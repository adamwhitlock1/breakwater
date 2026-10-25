import json

from breakwater.comment import marker, post, render


def _report(**over):
    finding = {"signature": "P2|outcome|exc:pkg.Invalid|ok|non-ascii", "probe": "P2", "detail": "outcome",
               "args": [["١"]], "base": {"status": "exc", "exc": "pkg.Invalid"}, "head": {"status": "ok"},
               "found_by": ["A1/s1"]}
    r = {"run_id": "r1", "target": "pkg:Version", "base": "a" * 40, "head": "b" * 40, "provider": "tokenfactory",
         "semantic": {"findings": [finding], "attacks": [{"id": "A1"}]},
         "adjudication": {"verdicts": [{"signature": finding["signature"], "label": "likely-bug", "votes": {},
                                        "rationale": "", "evidence": [], "rejected": [], "reason": ""}]},
         "regression_tests": [{"signature": finding["signature"], "verified": True, "source": "def test_x():\n    pass\n"}],
         "usd_by_tier": {"reasoning": 0.1}}
    return {**r, **over}


def test_comment_states_verdict_reasons_and_tests():
    body = render(_report(), artifact_url="https://x/a")
    assert body.startswith(marker("pkg:Version")) and "## 🛑 Breakwater: BLOCK" in body
    assert "likely bug" in body and "✅ verified" in body and "[download](https://x/a)" in body
    clean = render(_report(semantic={"findings": [], "attacks": []}, adjudication=None, regression_tests=[]))
    assert "## ✅ Breakwater: PASS" in clean and "No behaviour divergence" in clean
    dev = render(_report(provider="openrouter"))
    assert "development run" in dev


def test_post_updates_its_own_comment_and_creates_otherwise():
    calls = []

    def gh(existing):
        def run(args, stdin):
            calls.append((args, stdin))
            if args[1].endswith("/comments") and "--paginate" in args:
                return json.dumps([existing])
            return json.dumps({"html_url": "https://github.com/o/r/pull/7#c"})
        return run

    mine = {"id": 99, "body": marker("pkg:Version") + "\nold"}
    other = {"id": 5, "body": "lgtm"}
    assert post("new", repo="o/r", pr=7, target="pkg:Version", gh=gh([other, mine])).endswith("#c")
    assert calls[-1][0][:4] == ["api", "--method", "PATCH", "repos/o/r/issues/comments/99"]
    assert json.loads(calls[-1][1]) == {"body": "new"}
    post("new", repo="o/r", pr=7, target="pkg:Version", gh=gh([other]))
    assert calls[-1][0][:4] == ["api", "--method", "POST", "repos/o/r/issues/7/comments"]


def test_verdict_thresholds():
    from breakwater.verdict import fails

    assert fails("BLOCK", "block") and not fails("REVIEW", "block") and fails("REVIEW", "review")
    assert not fails("BLOCK", "never")


def test_comment_names_the_backend_and_image():
    uuid = "dbe8dafe-78c4-4fc8-b8c2-a5adaad2ed49"
    body = render(_report(sandbox={"backend": "contree", "image": uuid, "runs": 358, "cpu_s": 1.0}))
    assert f"Untrusted code: 358 runs in Token Factory Sandboxes microVMs · image `{uuid}`" in body
    docker = render(_report(semantic={"findings": [], "attacks": [], "image": "bw-pair:abc"}))
    assert "local Docker · image `bw-pair:abc`" in docker
