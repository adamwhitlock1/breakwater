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

Other modes (set "mode"):
  "perf"  Hypothesis targeted search maximizing log(head CPU / base CPU) per call. Returns the
          slowest-relative inputs: {"top": [{"args", "ratio", "base_ns", "head_ns"}], "examples", "error"}.
  "make"  Runs an LLM-written `make(n)` size-ladder generator (untrusted, so here in the sandbox):
          {"ladder": {"<n>": [args, ...]}, "error"}.
"""

from __future__ import annotations

import json
import math
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

    def _ask(self, req_base: dict, op: dict) -> dict:
        req = dict(req_base, ops=[op])
        self.proc.stdin.write(json.dumps(req, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()
        resp = json.loads(self.proc.stdout.readline())
        if "error" in resp:
            raise RuntimeError(resp["error"])
        return resp["results"][0]

    def construct(self, req_base: dict, args: list) -> dict:
        return self._ask(req_base, {"op": "construct", "inputs": [args]})["outcomes"][0]

    def time(self, req_base: dict, args: list) -> dict:
        return self._ask(req_base, {"op": "time", "inputs": [args]})["timings"][0]

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


MAX_LADDER_ARGS = 64  # inputs per ladder size
MAX_LADDER_CHARS = 2_000_000


MAKE_TIMEOUT_S = 10
MAKE_MEMORY_BYTES = 2 * 1024**3


class _MakeTimeout(Exception):
    pass


def run_make(req):
    """Execute an LLM-written `make(n) -> list of argument lists` for each requested size.
    Generators can explode (one day-1 plan built an n^3 list), so each size runs under an alarm and
    an address-space limit; the ladder stops at the first size that fails and keeps the smaller ones."""
    import itertools
    import resource
    import signal

    out = {"ladder": {}, "error": None}
    resource.setrlimit(resource.RLIMIT_AS, (MAKE_MEMORY_BYTES, MAKE_MEMORY_BYTES))

    def alarm(signum, frame):
        raise _MakeTimeout()

    signal.signal(signal.SIGALRM, alarm)
    try:
        random.seed(req.get("seed", 0))  # the module itself, seeded: models use both random.choice and random.Random
        scope = {"string": string, "random": random, "math": math, "itertools": itertools}
        exec(compile(req["make"], "<make>", "exec"), scope)  # noqa: S102 - sandboxed by design
        make = scope["make"]
    except Exception as e:  # noqa: BLE001
        out["error"] = f"{type(e).__name__}: {str(e)[:500]}"
        return out
    total = 0
    for n in req["sizes"]:
        try:
            signal.alarm(MAKE_TIMEOUT_S)
            items = make(int(n))
            items = [list(a) if isinstance(a, (list, tuple)) else [a] for a in itertools.islice(items, MAX_LADDER_ARGS)]
            blob = json.dumps(items, ensure_ascii=False)
            signal.alarm(0)
        except (_MakeTimeout, MemoryError) as e:
            signal.alarm(0)
            out["error"] = f"make({n}) {'timed out' if isinstance(e, _MakeTimeout) else 'ran out of memory'}; ladder stops at the previous size"
            break
        except Exception as e:  # noqa: BLE001
            signal.alarm(0)
            out["error"] = f"make({n}): {type(e).__name__}: {str(e)[:300]}"
            break
        total += len(blob)
        if total > MAX_LADDER_CHARS:
            out["error"] = f"ladder inputs exceed {MAX_LADDER_CHARS} chars at n={n}; ladder stops here"
            break
        out["ladder"][str(n)] = items
    return out


def run_perf(req):
    """Targeted property-based search for inputs where head is slowest relative to base."""
    from hypothesis import HealthCheck, Phase, given, settings, target
    from hypothesis import seed as hseed

    out = {"top": [], "examples": 0, "error": None}
    worker_req = {"target": req["target"], "observe": [], "timeout_s": req.get("timeout_s", 5)}
    base, head = Side(req["base_py"]), Side(req["head_py"])
    best: dict[str, dict] = {}
    try:
        strat = load_strategy(req["strategy"])

        @hseed(req.get("seed", 0))
        @settings(max_examples=req.get("max_examples", 150), database=None, deadline=None,
                  phases=[Phase.generate, Phase.target], suppress_health_check=list(HealthCheck))
        @given(strat)
        def probe(args):
            try:
                key = json.dumps(args, ensure_ascii=False, sort_keys=True)
            except (TypeError, ValueError):
                return
            out["examples"] += 1
            b, h = base.time(worker_req, args), head.time(worker_req, args)
            if b.get("ns") is None or h.get("ns") is None or (b["status"], b.get("exc")) != (h["status"], h.get("exc")):
                return  # behavior differs or timed out: the semantic search owns that
            if b.get("exc") == "builtins.TypeError":
                return  # wrong arity or argument types: not a workload anyone runs
            ratio = h["ns"] / max(b["ns"], 1.0)
            target(math.log(ratio), label="slowdown")
            if key not in best or ratio > best[key]["ratio"]:
                outcome = "ok" if b["status"] == "ok" else f"{b['status']}:{b.get('exc')}"
                best[key] = {"args": args, "ratio": ratio, "base_ns": b["ns"], "head_ns": h["ns"], "outcome": outcome}

        probe()
        out["top"] = sorted(best.values(), key=lambda r: -r["ratio"])[: req.get("top", 5)]
    except Exception as e:  # noqa: BLE001
        out["error"] = f"{type(e).__name__}: {str(e)[:500]}"
    finally:
        base.close()
        head.close()
    return out


def main():
    from hypothesis import HealthCheck, Phase, find, settings
    from hypothesis.errors import NoSuchExample

    req = json.loads(sys.stdin.read())
    if req.get("mode") == "make":
        json.dump(run_make(req), sys.stdout, ensure_ascii=False)
        return
    if req.get("mode") == "perf":
        json.dump(run_perf(req), sys.stdout, ensure_ascii=False)
        return
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
