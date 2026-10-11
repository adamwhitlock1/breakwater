"""Structured progress events for a running audit, appended to `<run dir>/events.jsonl`.

The live page (`site/assets/live.js`) polls that file and renders the attack feed, cards as they
land, the sandbox gauge and the cost meter. Events are facts about the run (what was planned, what
was found, what each model call cost); the live page never computes a result itself.

Every line: {"seq": n, "t": seconds since start, "kind": "...", ...}. Kinds:
  run           repo, base, head, target, title, provider, run_id
  phase         name (plan, generate, search, batch, adjudicate, perf-plan, perf-screen,
                perf-expand, perf-full, report)
  llm-start     tier, purpose, requests (in flight until that many llm events; the page shows "thinking")
  llm           tier, model, purpose, tokens_in/out, reasoning_tokens, usd, latency_ms, ok
  sandbox       state (start|end), in_flight, runs, cpu_s, exit_code, ms
  plan          attacks: [{id, assumption, why_it_breaks, input_family, examples}]
  strategies    jobs: [{id, attack, valid, error, source}]
  strategy      id, examples, findings, error
  finding       signature, probe, title, inputs, base, head, found_by (a new class)
  batch         inputs, mutations, classes
  verdict       signature, label, votes, rationale, evidence
  tests         generated, verified, skipped (regression tests, see regress.py)
  family        id, family_kind, family, origin, screen_ratio, valid_fraction (screened)
  measured      family_id, family_kind, family, verdict, ladder ratios, slopes (full ladder)
  done          verdict (BLOCK|REVIEW|PASS), classes, report (relative path), usd_by_tier
  error         message
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from breakwater.backends.base import Backend, RunResult


def _plain(v: Any) -> Any:
    if is_dataclass(v) and not isinstance(v, type):
        return asdict(v)
    return str(v)


class Events:
    """Thread-safe JSONL appender. `Events(None)` is a no-op, so pipeline code can always call it."""

    def __init__(self, path: Path | None):
        self.path = path
        self._lock = threading.Lock()
        self._seq = 0
        self._t0 = time.monotonic()
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("")

    RESERVED = frozenset({"seq", "t", "kind"})

    def __call__(self, kind: str, /, **data: Any) -> None:
        if clash := self.RESERVED & data.keys():
            raise ValueError(f"event field(s) {sorted(clash)} are reserved")
        if not self.path:
            return
        with self._lock:
            self._seq += 1
            line = {"seq": self._seq, "t": round(time.monotonic() - self._t0, 2), "kind": kind, **data}
            with self.path.open("a") as f:
                f.write(json.dumps(line, ensure_ascii=False, default=_plain) + "\n")


NULL = Events(None)


class ObservedBackend:
    """Wraps a backend to report sandbox runs in flight (the live page's gauge). Behaviour unchanged."""

    def __init__(self, inner: Backend, events: Events):
        self.inner, self.events = inner, events
        self.name = inner.name
        self._lock = threading.Lock()
        self.in_flight = self.runs = 0
        self.cpu_s = 0.0

    def __getattr__(self, item: str) -> Any:
        return getattr(self.inner, item)

    def run(self, image_ref: str, cmd: list[str], **kw: Any) -> RunResult:
        with self._lock:
            self.in_flight += 1
            self.runs += 1
            self.events("sandbox", state="start", in_flight=self.in_flight, runs=self.runs)
        res: RunResult | None = None
        try:
            res = self.inner.run(image_ref, cmd, **kw)
            return res
        finally:
            with self._lock:
                self.in_flight -= 1
                cpu = getattr(getattr(res, "resources", None), "user_cpu_s", None) or 0.0
                self.cpu_s += cpu
                self.events("sandbox", state="end", in_flight=self.in_flight, runs=self.runs,
                            cpu_s=round(self.cpu_s, 2), exit_code=getattr(res, "exit_code", None),
                            ms=getattr(res, "duration_ms", None))
