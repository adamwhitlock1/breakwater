import json
import shutil
import subprocess

import pytest

from breakwater.backends.base import RunResult
from breakwater.harness import worker
from breakwater.images import PairImage, build_pair, git_req
from breakwater.probes import Divergence, Runner, Target, run_probes


class InProcessBackend:
    """Runs the worker in-process, swapping the target per side, so probe logic is testable without Docker."""

    name = "inprocess"

    def __init__(self, base_target: str, head_target: str):
        self.targets = {PairImage.BASE_PY: base_target, PairImage.HEAD_PY: head_target}

    def run(self, image_ref, cmd, *, files=None, stdin=None, timeout_s=300, keep=False, tag=None):
        req = json.loads(stdin)
        req["target"] = self.targets[cmd[0]]
        return RunResult(json.dumps(worker.run(req)), "", 0, 0, self.name)


def fake_runner(observe=("str",)):
    backend = InProcessBackend("fake_targets:BaseVer", "fake_targets:HeadVer")
    return Runner(backend, PairImage("fake", "base", "head"), Target("ignored", observe))


def test_worker_reports_exceptions_by_exact_type_and_timeouts():
    res = worker.run({"target": "decimal:Decimal", "ops": [{"op": "construct", "inputs": [["1.5"], ["x"]]}]})
    ok, bad = res["results"][0]["outcomes"]
    assert ok["status"] == "ok" and ok["obs"] == {"str": "1.5", "repr": "Decimal('1.5')"}
    assert (bad["status"], bad["exc"]) == ("exc", "decimal.InvalidOperation")
    assert isinstance(ok["t_ns"], int)
    slow = worker.run({"target": "time:sleep", "observe": [], "timeout_s": 0.2,
                       "ops": [{"op": "construct", "inputs": [[2]]}]})
    assert slow["results"][0]["outcomes"][0]["status"] == "timeout"


def test_worker_pickle_round_trip_with_warm_state():
    dumped = worker.run({"target": "fractions:Fraction", "ops": [{"op": "pickle_dump", "inputs": [["1/3"]], "warm": True}]})
    blobs = dumped["results"][0]["blobs"]
    loaded = worker.run({"target": "fractions:Fraction", "ops": [{"op": "pickle_load", "blobs": blobs, "inputs": [["1/3"]]}]})
    assert loaded["results"][0]["loads"][0]["eq_fresh"] is True


def test_probes_find_each_planted_bug_class():
    inputs = [["1.2"], ["01.2"], ["١.٢"], ["x"]]
    report = run_probes(fake_runner(), inputs, ("P1", "P2", "P3"))
    classes = report.classes()
    assert "P1|str|differs|plain" in classes  # "01.2" prints differently
    p2 = [d for d in report.divergences if d.probe == "P2"]
    assert [d.inputs for d in p2] == [[["١.٢"]]]  # head accepts Arabic-Indic digits; "x" fails on both
    p3 = {(d.detail, d.base, d.head) for d in report.divergences if d.probe == "P3"}
    assert ("eq", True, False) in p3  # "1.2" == "01.2" on base only


def test_no_divergence_when_sides_agree():
    backend = InProcessBackend("fake_targets:BaseVer", "fake_targets:BaseVer")
    runner = Runner(backend, PairImage("fake", "base", "head"), Target("ignored", ("str", "repr")))
    assert run_probes(runner, [["1.2"], ["01.2"], ["x"]], ("P1", "P2", "P3")).divergences == []


def test_p1_signature_ignores_values():
    a = Divergence("P1", "str", [["a"]], "1", "01")
    b = Divergence("P1", "str", [["b"]], "2", "02")
    assert a.signature() == b.signature()


# ---- Docker integration: the real packaging regressions -------------------------------------------

PKG = "https://github.com/pypa/packaging"


def _harness() -> bool:
    return bool(shutil.which("docker")) and subprocess.run(
        ["docker", "image", "inspect", "breakwater-harness"], capture_output=True).returncode == 0


docker = pytest.mark.skipif(not _harness(), reason="needs Docker and the breakwater-harness image")


def _probe(base_req, head_req, target, inputs, probes=("P1", "P2", "P3", "P4")):
    from breakwater.backends.docker import DockerBackend

    return run_probes(Runner(DockerBackend(), build_pair(base_req, head_req), target), inputs, probes)


@docker
def test_pr1082_intermediate_commit_accepts_invalid_versions():
    rep = _probe(git_req(PKG, "59f183fe90da"), git_req(PKG, "61967cca278d"),
                 Target("packaging.version:Version"), [["1.0"], ["1. 0"], ["١.٠"], ["1" * 5000 + ".0"]], ("P1", "P2"))
    flagged = {d.inputs[0][0][:6] for d in rep.divergences}
    assert flagged == {"1. 0", "١.٠", "111111"}


@docker
def test_pr1108_changes_specifierset_equality():
    rep = _probe(git_req(PKG, "20f1523cf37d"), git_req(PKG, "f59d6ee9afe2"),
                 Target("packaging.specifiers:SpecifierSet", ("str", "len")), [[">1.0.0,>1.0"], [">1.0"]], ("P1", "P3"))
    assert ("P3", "eq", True, False) in {(d.probe, d.detail, d.base, d.head) for d in rep.divergences}


@docker
def test_packaging_26_1_breaks_old_pickles_and_26_2_fixes_it():
    target = Target("packaging.version:Version")
    broken = _probe("packaging==26.0", "packaging==26.1", target, [["1.2.3"]], ("P4",))
    assert any(d.detail == "base->head load" and "ModuleNotFoundError" in d.head["exc"] for d in broken.divergences)
    assert _probe("packaging==26.0", "packaging==26.2", target, [["1.2.3"]], ("P4",)).divergences == []


def test_traits_split_distinct_root_causes():
    from breakwater.harness.compare import signature, traits

    assert traits(["١.٠"]) == "non-ascii"
    assert traits(["1. 0"]) == "whitespace"
    assert traits(["1" * 5000]) == "long-digits"
    assert traits([["."]]) == "nested"
    exc = {"status": "exc", "exc": "x.InvalidVersion"}
    ok = {"status": "ok", "obs": {}}
    assert signature("P2", "outcome", exc, ok, ["١.٠"]) != signature("P2", "outcome", exc, ok, ["1. 0"])


def test_worker_survives_a_raising_repr():
    import sys
    import types

    mod = types.ModuleType("bw_bad_repr")

    class Bad:
        def __init__(self, s):
            self.s = s

        def __repr__(self):
            raise RuntimeError("boom")

    mod.Bad = Bad
    sys.modules["bw_bad_repr"] = mod
    res = worker.run({"target": "bw_bad_repr:Bad", "observe": ["repr"], "ops": [{"op": "construct", "inputs": [["x"]]}]})
    assert res["results"][0]["outcomes"][0]["obs"]["repr"] == "<exc:builtins.RuntimeError>"


def test_eq_hash_contract_violation_present_on_both_sides_is_not_a_divergence(tmp_path, monkeypatch):
    import sys
    import types

    mod = types.ModuleType("bw_hash_bug")

    class Both:  # violates eq/hash on base and head alike
        def __init__(self, s):
            self.s = s

        def __eq__(self, other):
            return self.s.lstrip("0") == other.s.lstrip("0")

        def __hash__(self):
            return hash(self.s)

    mod.Both = Both
    monkeypatch.setitem(sys.modules, "bw_hash_bug", mod)
    backend = InProcessBackend("bw_hash_bug:Both", "bw_hash_bug:Both")
    runner = Runner(backend, PairImage("fake", "base", "head"), Target("ignored", ("str",)))
    assert run_probes(runner, [["2"], ["02"]], ("P3",)).divergences == []
