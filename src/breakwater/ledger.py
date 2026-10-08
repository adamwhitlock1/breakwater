"""Append-only JSONL cost ledger. Every model call lands here; the README bill is built from it."""

from __future__ import annotations

import json
import os
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path

DEFAULT_PATH = Path(os.environ.get("BREAKWATER_LEDGER", "artifacts/ledger.jsonl"))


@dataclass
class Entry:
    tier: str
    model: str
    purpose: str
    tokens_in: int
    tokens_out: int
    reasoning_tokens: int
    usd: float
    latency_ms: int
    ok: bool
    ts: float = field(default_factory=time.time)
    run_id: str | None = None


def append(entry: Entry, path: Path = DEFAULT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(asdict(entry)) + "\n")


def summarize(path: Path = DEFAULT_PATH, run_id: str | None = None) -> dict[str, dict[str, float]]:
    """Totals per tier: calls, tokens and dollars."""
    totals: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    if not path.exists():
        return {}
    for line in path.read_text().splitlines():
        e = json.loads(line)
        if run_id and e.get("run_id") != run_id:
            continue
        t = totals[e["tier"]]
        t["calls"] += 1
        t["tokens_in"] += e["tokens_in"]
        t["tokens_out"] += e["tokens_out"]
        t["usd"] += e["usd"]
    return {k: dict(v) for k, v in totals.items()}
