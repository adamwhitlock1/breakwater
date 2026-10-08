"""Token Factory Sandboxes (ConTree) backend.

Written against contree-sdk 0.3.6 (PyPI). Auth comes from env: NEBIUS_API_KEY and
NEBIUS_PROJECT_ID; the default base URL is the Token Factory Sandboxes endpoint.
Every run returns a new immutable image UUID, so `RunResult.image_ref` is the snapshot to
branch from, and every reported number can cite the image that reproduces it.

Runs are disposable unless `keep=True`; keep=True is how we build tagged images (repo at a
ref, deps installed) that probe runs then branch from.

Unverified until Sandboxes access is granted (scripts/day1/check_contree.py checks them):
units of the ProcessResources fields, and the absolute path semantics of `files=`.
"""

from __future__ import annotations

import time

from breakwater.backends.base import Resources, RunResult


class ContreeBackend:
    name = "contree"

    def __init__(self) -> None:
        from contree_sdk import ContreeSync  # optional dependency: `uv sync --extra sandboxes`

        self.contree = ContreeSync()

    def image(self, ref: str):
        """`ref` is a tag (e.g. "python:3.12-slim") or an image UUID from a previous run."""
        return self.contree.images.use(ref)

    def run(self, image_ref, cmd, *, files=None, stdin=None, timeout_s=300, keep=False, tag=None) -> RunResult:
        image = self.image(image_ref)
        t0 = time.perf_counter()
        done = image.run(
            command=cmd[0], args=tuple(cmd[1:]), stdin=stdin, files=files,
            timeout=timeout_s, disposable=not keep, tag=tag,
        ).wait()
        duration_ms = int((time.perf_counter() - t0) * 1000)
        result = done.result
        raw = getattr(result, "_raw", None)
        res = raw.result.resources if raw is not None and raw.result is not None else None
        resources = Resources(
            user_cpu_s=getattr(res, "user_cpu_time", None),
            sys_cpu_s=getattr(res, "system_cpu_time", None),
            max_rss_kb=getattr(res, "max_rss", None),
            involuntary_switches=getattr(res, "involuntary_switches", None),
            cost_usd=getattr(result, "cost", None),
        )
        return RunResult(
            stdout=result.stdout or "",
            stderr=result.stderr or "",
            exit_code=result.exit_code,
            duration_ms=duration_ms,
            backend=self.name,
            image_ref=str(done.uuid),
            resources=resources,
        )
