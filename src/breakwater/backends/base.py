"""Execution backends. Untrusted code (LLM-written attack strategies, candidate patches) only
runs through this interface, so ConTree Sandboxes, local Docker and (later) OpenShell are
interchangeable and every result records which backend produced it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class Resources:
    """Out-of-process accounting, the "second clock". The measured process cannot tamper with it.

    ConTree reports these per run (contree-sdk ProcessResources); Docker fills them from rusage.
    """

    user_cpu_s: float | None = None
    sys_cpu_s: float | None = None
    max_rss_kb: int | None = None
    involuntary_switches: int | None = None
    cost_usd: float | None = None  # ConTree reports a per-run cost; None elsewhere


@dataclass
class RunResult:
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: int
    backend: str
    image_ref: str | None = None  # snapshot after the run (ConTree image UUID); None for local
    resources: Resources = field(default_factory=Resources)


class Backend(Protocol):
    name: str

    def run(
        self,
        image_ref: str,
        cmd: list[str],
        *,
        files: dict[str, bytes] | None = None,
        stdin: str | None = None,
        timeout_s: int = 300,
        keep: bool = False,  # snapshot the result (ConTree); ignored by Docker
        tag: str | None = None,
    ) -> RunResult: ...
