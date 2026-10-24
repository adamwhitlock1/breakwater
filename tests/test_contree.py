"""ContreeBackend and the Sandboxes pair-image builder, against a recorded fixture (no network).

The fixture is one real operation result from Token Factory Sandboxes (tests/fixtures/contree_run.json).
The fake client below speaks the slice of the contree-sdk 0.3.6 surface the backend uses:
images.use(ref, strict=) -> image; image.run(**kw).wait() -> done with .uuid/.result; image.tag_as(tag).
"""

from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

from breakwater.backends.contree import INPUTS_DIR, OUTPUT_CAP, RUN_ENV, ContreeBackend, transient
from breakwater.images import PairImage, build_pair, harness_tag, image_exists

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "contree_run.json").read_text())


def _ns(d):
    return SimpleNamespace(**{k: _ns(v) if isinstance(v, dict) else v for k, v in d.items()}) if isinstance(d, dict) else d


# -- SDK-shaped errors (the backend classifies by class name, like the real ones) ----------------

class NotFoundError(Exception):
    status = 404


class TooManyRequestsError(Exception):
    status = 429


class ApiStatusCodeError(Exception):
    def __init__(self, status):
        super().__init__(f"status {status}")
        self.status = status


class FailedOperationError(Exception):
    pass


class FakeResult:
    def __init__(self, stdout="out\n", stderr="err\n", exit_code=3, truncated=False, timed_out=False):
        raw = json.loads(json.dumps(FIXTURE["raw"]))
        raw["result"]["state"]["exit_code"] = exit_code
        raw["result"]["state"]["timed_out"] = timed_out
        raw["result"]["stdout"]["truncated"] = truncated
        self._raw = _ns(raw)
        self.stdout, self.stderr, self.exit_code = stdout, stderr, exit_code
        self.cost, self.truncated = FIXTURE["cost"], truncated


class FakeClient:
    """Scripted fake: `outcomes` is a list of FakeResult or exceptions, consumed one per run."""

    def __init__(self, outcomes, *, tags=None, keep_uuid="11111111-2222-3333-4444-555555555555"):
        self.outcomes = list(outcomes)
        self.tags = dict(tags or {})  # tag -> uuid
        self.keep_uuid = keep_uuid
        self.runs: list[dict] = []
        self.tagged: list[tuple[str, str]] = []
        self.in_flight = 0
        self.max_in_flight = 0
        self.lock = threading.Lock()

    class _Image:
        def __init__(self, client, ref):
            self.client, self.ref = client, ref
            self.uuid = ref

        def run(self, **kw):
            c = self.client
            with c.lock:
                c.runs.append({"image": self.ref, **kw})
                c.in_flight += 1
                c.max_in_flight = max(c.max_in_flight, c.in_flight)
                outcome = c.outcomes.pop(0) if c.outcomes else FakeResult()
            time.sleep(0.01)
            with c.lock:
                c.in_flight -= 1
            return FakeClient._Op(c, outcome, kw)

        def tag_as(self, tag):
            self.client.tagged.append((self.ref, tag))
            self.client.tags[tag] = self.ref

    class _Op:
        def __init__(self, client, outcome, kw):
            self.client, self.outcome, self.kw = client, outcome, kw

        def wait(self):
            if isinstance(self.outcome, BaseException):
                raise self.outcome
            uuid = self.client.keep_uuid if not self.kw.get("disposable", True) else None
            return SimpleNamespace(uuid=uuid, result=self.outcome)

    @property
    def images(self):
        client = self

        class Images:
            def use(self, ref, strict=False):
                if strict and ref not in client.tags and ref != client.keep_uuid and ref != FIXTURE["image"]:
                    raise NotFoundError(ref)
                return FakeClient._Image(client, client.tags.get(ref, ref))

        return Images()

    def get_token_info(self, refresh=False):
        return SimpleNamespace(token_uuid="932a73cf-0000", permissions={"spawn": True},
                               limits={"instance_max_concurrency": 50, "instance_max_timeout": 3600},
                               operations_stat={"running_instances": 0})


def backend(outcomes=(), **kw):
    client = FakeClient(outcomes, **{k: v for k, v in kw.items() if k in ("tags",)})
    be = ContreeBackend(client=client, sleep=lambda s: None, **{k: v for k, v in kw.items() if k not in ("tags",)})
    return be, client


# -- run() ---------------------------------------------------------------------------------------

def test_run_maps_recorded_result_and_resources():
    be, client = backend([FakeResult()])
    res = be.run(FIXTURE["image"], ["python", "-c", "pass"], stdin='{"x": 1}', files={"a/b.txt": b"data"})
    assert (res.stdout, res.stderr, res.exit_code) == ("out\n", "err\n", 3)
    assert res.backend == "contree"
    assert res.image_ref == FIXTURE["image"], "a disposable run cites the image it branched from"
    r = FIXTURE["raw"]["result"]["resources"]
    assert res.resources.user_cpu_s == r["user_cpu_time"]
    assert res.resources.max_rss_kb == r["max_rss"]
    assert res.resources.involuntary_switches == r["involuntary_switches"]
    assert res.resources.cost_usd == FIXTURE["cost"] > 0
    req = client.runs[0]
    assert req["disposable"] is True and req["timeout"] == 300
    assert req["truncate_output_at"] == OUTPUT_CAP == 10 * 1024 * 1024, "the SDK default (65535) would cut perf ladders"
    assert req["stdin"] == b'{"x": 1}', "stdin goes as bytes (base64 on the wire), never ascii-labelled text"
    assert req["files"] == {f"{INPUTS_DIR}/a/b.txt": b"data"}, "same place the Docker backend mounts inputs"
    assert req["env"] == RUN_ENV and req["env"]["PYTHONHASHSEED"] == "0", "explicit per run: preserve_env does not reach command runs"
    assert req["preserve_env"] is False


def test_network_is_off_unless_asked():
    be, client = backend([FakeResult(), FakeResult()])
    be.run("img", ["python", "-V"])
    be.run("img", ["sh", "-c", "apt-get update"], network=True)
    assert (client.runs[0]["command"], client.runs[0]["args"]) == ("unshare", ("-n", "python", "-V"))
    assert (client.runs[1]["command"], client.runs[1]["args"]) == ("sh", ("-c", "apt-get update"))


def test_truncated_output_fails_the_run_and_timeouts_are_noted():
    be, _ = backend([FakeResult(exit_code=0, truncated=True), FakeResult(exit_code=-1, timed_out=True)])
    cut = be.run("img", ["python"])
    assert cut.exit_code == 1 and "truncated" in cut.stderr
    late = be.run("img", ["python"], timeout_s=5)
    assert late.exit_code == -1 and "timed out after 5 s" in late.stderr


def test_timeout_above_the_sandboxes_limit_is_clamped():
    be, client = backend([FakeResult(exit_code=0)])
    be.run("img", ["python"], timeout_s=18860)  # a 940-input probe batch asks for this much
    assert client.runs[0]["timeout"] == 3600


def test_transient_classification():
    assert transient(TooManyRequestsError())
    assert transient(ApiStatusCodeError(503))
    assert not transient(ApiStatusCodeError(422))
    assert not transient(FailedOperationError("the sandbox said no"))
    assert not transient(ValueError())


def test_retries_transient_errors_then_gives_up():
    be, client = backend([TooManyRequestsError(), ApiStatusCodeError(502), FakeResult(exit_code=0)])
    assert be.run("img", ["python"]).exit_code == 0
    assert len(client.runs) == 3
    be, client = backend([FailedOperationError("boom")])
    with pytest.raises(FailedOperationError):
        be.run("img", ["python"])
    assert len(client.runs) == 1, "a failure the sandbox reported is not retried"
    be, client = backend([TooManyRequestsError()] * 10)
    with pytest.raises(TooManyRequestsError):
        be.run("img", ["python"])
    assert len(client.runs) == 5, "bounded: 1 attempt + 4 retries"


def test_kept_run_is_tagged_only_on_success_and_not_resubmitted_once_its_tag_exists():
    be, client = backend([FakeResult(exit_code=1)])
    failed = be.run("img", ["sh", "-c", "exit 1"], keep=True, tag="bw-pair:x")
    assert failed.exit_code == 1 and client.tagged == [], "a failed build must never become a cache hit"
    be, client = backend([FakeResult(exit_code=0)])
    ok = be.run("img", ["sh", "-c", "true"], keep=True, tag="bw-pair:x", env={"PYTHONHASHSEED": "0"})
    assert ok.image_ref == client.keep_uuid and client.tagged == [(client.keep_uuid, "bw-pair:x")]
    assert client.runs[0]["env"] == {**RUN_ENV, "PYTHONHASHSEED": "0"} and client.runs[0]["preserve_env"] is True

    # Contact lost after the build finished: the tag exists, so the image is reused, not rebuilt.
    be, client = backend([TooManyRequestsError()])
    client.tags["bw-pair:x"] = "aaaaaaaa-0000-0000-0000-000000000000"
    rec = be.run("img", ["sh", "-c", "true"], keep=True, tag="bw-pair:x")
    assert rec.image_ref == "aaaaaaaa-0000-0000-0000-000000000000" and len(client.runs) == 1


def test_concurrency_is_bounded_by_the_semaphore():
    be, client = backend([FakeResult()] * 40, max_concurrency=3)
    with ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(lambda _: be.run("img", ["python"]), range(40)))
    assert client.max_in_flight <= 3 and len(client.runs) == 40


def test_whoami_and_tag_lookup():
    be, client = backend(tags={"bw-pair:known": "bbbbbbbb-0000-0000-0000-000000000000"})
    who = be.whoami()
    assert who["limits"]["instance_max_concurrency"] == 50 and who["token"] == "932a73cf"
    assert be.find_tag("bw-pair:known") == "bbbbbbbb-0000-0000-0000-000000000000"
    assert be.find_tag("bw-pair:missing") is None
    assert image_exists("bbbbbbbb-0000-0000-0000-000000000000", be) is False  # a uuid, not a known tag, in the fake
    assert image_exists(FIXTURE["image"], be) is True


# -- images.build_pair on Sandboxes ----------------------------------------------------------------

def test_build_pair_contree_builds_harness_then_pair_and_tags_both():
    be, client = backend([FakeResult(exit_code=0), FakeResult(exit_code=0)])
    img = build_pair("packaging==26.0", "packaging==26.1", backend=be)
    assert isinstance(img, PairImage) and img.ref == client.keep_uuid and img.tag.startswith("bw-pair:")
    harness, pair = client.runs
    assert harness["image"] == "python:3.12-slim" and harness["disposable"] is False and harness["command"] == "sh"
    assert "valgrind" in harness["args"][1] and "uv==" in harness["args"][1], "harness recipe: valgrind + git + uv"
    assert harness["env"]["PYTHONHASHSEED"] == "0" and harness["preserve_env"] is True
    assert pair["image"] == client.keep_uuid, "the pair image is built on the harness image"
    script = pair["args"][1]
    assert "/envs/base" in script and '"packaging==26.0"' in script and '"packaging==26.1"' in script
    assert "hypothesis==6.168.5" in script
    assert set(pair["files"]) == {"/harness/worker.py", "/harness/compare.py", "/harness/diffrun.py"}
    assert [t for _, t in client.tagged] == [harness_tag(), img.tag]


def test_build_pair_contree_is_a_cache_hit_by_tag():
    be, client = backend([FakeResult(exit_code=0)] * 2, tags={harness_tag(): "hhhhhhhh-0000-0000-0000-000000000000"})
    first = build_pair("packaging==26.0", "packaging==26.1", backend=be)
    assert len(client.runs) == 1 and client.runs[0]["image"] == "hhhhhhhh-0000-0000-0000-000000000000"
    again = build_pair("packaging==26.0", "packaging==26.1", backend=be)
    assert again == first and len(client.runs) == 1, "found by tag; nothing rebuilt"
    other = build_pair("packaging==26.0", "packaging==26.2", backend=be)
    assert other.tag != first.tag and len(client.runs) == 2, "content-addressed: a different pair is a different tag"


def test_build_pair_contree_failed_install_raises_and_leaves_no_tag():
    be, client = backend([FakeResult(exit_code=0), FakeResult(exit_code=1, stderr="No solution found")])
    with pytest.raises(RuntimeError, match="No solution found"):
        build_pair("packaging==26.0", "nope==0", backend=be)
    assert [t for _, t in client.tagged] == [harness_tag()]
