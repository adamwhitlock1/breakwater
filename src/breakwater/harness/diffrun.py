"""In-sandbox differential search. Runs under the image's system Python, which has Hypothesis but
NOT the target library. Base and head run as persistent `worker.py --serve` subprocesses, so
LLM-written strategy code never shares a process with either side, and never runs outside the sandbox.

For each strategy we call hypothesis.find() with "base and head disagree (in a new way)" as the
condition. Hypothesis then shrinks to a minimal counterexample. We repeat with already-found
signatures excluded, to collect up to `max_classes` distinct finding classes per strategy.

Request (stdin JSON):
  {"strategy": "<python source defining `strategy`>", "target": "pkg.mod:Callable",
   "observe": [...], "max_examples": 300, "max_classes": 3, "seed": 0, "timeout_s": 5,
   "base_py": "/envs/base/bin/python", "head_py": "/envs/head/bin/python"}
Response (stdout JSON):
  {"findings": [{"args": [...], "signature": "...", "probe": "...", "detail": "...",
                 "base": ..., "head": ...}],
   "samples": [[...], ...], "examples": N, "error": null | "..."}
"""

from __future__ import annotations

import json
import random
import string
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from compare import compare_outcomes, signature  # noqa: E402

MAX_SAMPLES = 60


class Side:
    def __init__(self, python: str):
        self.proc = subprocess.Popen([python, str(Path(__file__).parent / "worker.py"), "--serve"],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding="utf-8")

    def construct(self, req_base: dict, args: list) -> dict:
        req = dict(req_base, ops=[{"op": "construct", "inputs": [args]}])
        self.proc.stdin.write(json.dumps(req, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()
        resp = json.loads(self.proc.stdout.readline())
        if "error" in resp:
            raise RuntimeError(resp["error"])
        return resp["results"][0]["outcomes"][0]

    def close(self):
        self.proc.stdin.close()
        self.proc.wait(timeout=10)


def load_strategy(src: str):
    from hypothesis import strategies as st

    scope = {"st": st, "string": string}
    exec(compile(src, "<strategy>", "exec"), scope)  # noqa: S102 - untrusted by design; we are the sandbox
    strat = scope.get("strategy")
    if strat is None:
        raise ValueError("source must define `strategy`")
    return strat.map(lambda v: list(v) if isinstance(v, tuple) else [v])


def main():
    from hypothesis import HealthCheck, Phase, find, settings
    from hypothesis.errors import NoSuchExample

    req = json.loads(sys.stdin.read())
    out = {"findings": [], "samples": [], "examples": 0, "error": None}
    worker_req = {"target": req["target"], "observe": req["observe"], "timeout_s": req.get("timeout_s", 5)}
    base, head = Side(req["base_py"]), Side(req["head_py"])
    seen_samples: set[str] = set()
    found: set[str] = set()

    def divergence(args):
        out["examples"] += 1
        try:
            key = json.dumps(args, ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError):
            return None  # not JSON-serializable: cannot be sent to the workers
        if key not in seen_samples and len(out["samples"]) < MAX_SAMPLES:
            seen_samples.add(key)
            out["samples"].append(args)
        b, h = base.construct(worker_req, args), head.construct(worker_req, args)
        for probe, detail, bv, hv in compare_outcomes(b, h, req["observe"]):
            sig = signature(probe, detail, bv, hv)
            if sig not in found:
                return {"args": args, "signature": sig, "probe": probe, "detail": detail, "base": bv, "head": hv}
        return None

    try:
        strat = load_strategy(req["strategy"])
        cfg = settings(max_examples=req.get("max_examples", 300), database=None, deadline=None,
                       phases=[Phase.generate, Phase.shrink],
                       suppress_health_check=list(HealthCheck))
        for _ in range(req.get("max_classes", 3)):
            try:
                args = find(strat, lambda a: divergence(a) is not None, settings=cfg,
                            random=random.Random(req.get("seed", 0)))
            except NoSuchExample:
                break
            hit = divergence(args)  # re-evaluate the shrunk example to record its details
            if hit is None:
                break
            found.add(hit["signature"])
            out["findings"].append(hit)
    except Exception as e:  # noqa: BLE001 - report strategy errors instead of crashing the batch
        out["error"] = f"{type(e).__name__}: {str(e)[:500]}"
    finally:
        base.close()
        head.close()
    json.dump(out, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
