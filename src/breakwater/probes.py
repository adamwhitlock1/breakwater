"""Deterministic differential probes (no LLM). Base and head run in separate processes on identical
inputs; this module only compares what the workers report.

  P1 output     observable outputs (str, repr, len, attributes) differ
  P2 exception  one side raises and the other doesn't, or the exception types differ (exact type,
                so ValueError -> InvalidVersion counts even though InvalidVersion subclasses it)
  P3 dunder     ==, <, > or hash-equality between two inputs differ across sides; also a head-side
                violation of the eq/hash contract
  P4 state      an object pickled by base (after warming its lazy caches) fails to load on head, or
                loads but no longer equals a freshly built one: the upgrade path users actually hit
  P4down        the same check in the downgrade direction (head -> base). Opt-in: libraries rarely
                promise it, so it is noisy by default
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from breakwater.backends import Backend
from breakwater.images import PairImage

ALL_PROBES = ("P1", "P2", "P3", "P4")
OPTIONAL_PROBES = ("P4down",)
MAX_RELATION_INPUTS = 40  # pairs grow quadratically


@dataclass(frozen=True)
class Target:
    callable: str  # "packaging.version:Version"
    observe: tuple[str, ...] = ("str", "repr")


@dataclass
class Divergence:
    probe: str
    detail: str  # which field / relation / direction
    inputs: list[Any]  # the argument list(s) that expose it
    base: Any
    head: Any

    def signature(self) -> str:
        """Dedup key: same probe, detail and outcome shapes are one finding class."""
        if self.probe == "P1":  # the differing values themselves vary per input
            return f"P1|{self.detail}|differs"
        return f"{self.probe}|{self.detail}|{_shape(self.base)}|{_shape(self.head)}"


@dataclass
class ProbeReport:
    target: Target
    image: str
    backend: str
    n_inputs: int
    divergences: list[Divergence] = field(default_factory=list)
    cpu_s: dict[str, float] = field(default_factory=dict)

    def classes(self) -> dict[str, list[Divergence]]:
        out: dict[str, list[Divergence]] = {}
        for d in self.divergences:
            out.setdefault(d.signature(), []).append(d)
        return out

    def to_json(self) -> dict:
        return {
            "target": asdict(self.target), "image": self.image, "backend": self.backend,
            "n_inputs": self.n_inputs, "cpu_s": self.cpu_s,
            "divergences": [asdict(d) for d in self.divergences],
            "classes": sorted(self.classes()),
        }


def _shape(outcome: Any) -> str:
    if isinstance(outcome, dict):
        if outcome.get("status") in ("exc", "timeout"):
            return f"{outcome['status']}:{outcome.get('exc')}"
        if outcome.get("status") == "ok":
            return "ok"
    return type(outcome).__name__ if not isinstance(outcome, (str, bool, int)) else str(outcome)


class Runner:
    def __init__(self, backend: Backend, image: PairImage, target: Target, timeout_s: float = 5.0):
        self.backend, self.image, self.target, self.timeout_s = backend, image, target, timeout_s
        self.cpu_s = {"base": 0.0, "head": 0.0}

    def call(self, side: str, ops: list[dict]) -> list[dict]:
        py = self.image.BASE_PY if side == "base" else self.image.HEAD_PY
        req = {"target": self.target.callable, "observe": list(self.target.observe), "ops": ops,
               "timeout_s": self.timeout_s}
        n = sum(len(op.get("inputs", [])) for op in ops)
        res = self.backend.run(self.image.ref, [py, self.image.WORKER], stdin=json.dumps(req),
                               timeout_s=int(60 + n * self.timeout_s * 4))
        if res.exit_code != 0:
            raise RuntimeError(f"{side} worker failed (exit {res.exit_code}):\n{res.stderr[-1500:]}")
        if res.resources.user_cpu_s is not None:
            self.cpu_s[side] += res.resources.user_cpu_s
        return json.loads(res.stdout)["results"]


def run_probes(runner: Runner, inputs: list[list[Any]], probes: tuple[str, ...] = ALL_PROBES) -> ProbeReport:
    report = ProbeReport(runner.target, runner.image.ref, runner.backend.name, len(inputs))
    divs = report.divergences
    rel_inputs = inputs[:MAX_RELATION_INPUTS]

    ops: list[dict] = [{"op": "construct", "inputs": inputs}]
    if "P3" in probes:
        ops.append({"op": "relations", "inputs": rel_inputs})
    p4_dirs = [d for d, probe in ((("base", "head"), "P4"), (("head", "base"), "P4down")) if probe in probes]
    if p4_dirs:
        ops.append({"op": "pickle_dump", "inputs": inputs, "warm": True})
    base_res, head_res = runner.call("base", ops), runner.call("head", ops)

    # P1 / P2: per-input outcomes
    for args, b, h in zip(inputs, base_res[0]["outcomes"], head_res[0]["outcomes"], strict=True):
        if b["status"] == "ok" and h["status"] == "ok":
            if "P1" in probes:
                for key in runner.target.observe:
                    if b["obs"].get(key) != h["obs"].get(key):
                        divs.append(Divergence("P1", key, [args], b["obs"].get(key), h["obs"].get(key)))
        elif "P2" in probes and (b["status"], b.get("exc")) != (h["status"], h.get("exc")):
            divs.append(Divergence("P2", "outcome", [args], b, h))

    # P3: relations between pairs of inputs
    if "P3" in probes:
        b_rel, h_rel = base_res[1]["relations"], head_res[1]["relations"]
        for key in sorted(set(b_rel) & set(h_rel)):
            i, j = (int(x) for x in key.split(","))
            pair = [rel_inputs[i], rel_inputs[j]]
            for name in ("eq", "lt", "gt", "hash_eq"):
                if b_rel[key][name] != h_rel[key][name]:
                    divs.append(Divergence("P3", name, pair, b_rel[key][name], h_rel[key][name]))
            if h_rel[key]["eq"] is True and h_rel[key]["hash_eq"] is False:
                divs.append(Divergence("P3", "eq-hash-contract", pair, "contract holds", "a == b but hash differs"))

    # P4: cross-version state
    if p4_dirs:
        p4 = 2 if "P3" in probes else 1
        results = {"base": base_res, "head": head_res}
        for src, dst in p4_dirs:
            blobs = results[src][p4]["blobs"]
            loads = runner.call(dst, [{"op": "pickle_load", "blobs": blobs, "inputs": inputs}])[0]["loads"]
            for args, blob, ld in zip(inputs, blobs, loads, strict=True):
                if blob is None:
                    continue
                direction = f"{src}->{dst}"
                probe_name = "P4" if src == "base" else "P4down"
                if ld["status"] != "ok":
                    divs.append(Divergence(probe_name, f"{direction} load", [args], "loads", ld))
                elif "eq_fresh" in ld and ld["eq_fresh"] is not True:
                    divs.append(Divergence(probe_name, f"{direction} eq-fresh", [args], True, ld["eq_fresh"]))

    report.cpu_s = dict(runner.cpu_s)
    return report
