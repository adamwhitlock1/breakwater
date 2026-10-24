"""Token Factory Sandboxes (ConTree) backend: every untrusted run is a microVM branched from an image.

Written against contree-sdk 0.3.6 (PyPI). Auth comes from env: NEBIUS_API_KEY and NEBIUS_PROJECT_ID;
the default base URL is the Token Factory Sandboxes endpoint. Verified live on 2026-10-17/18
(scripts/day1/check_contree.py, artifacts/day1/contree.json, and the checks recorded in
docs/feedback-log.md):

* A run on image X branches a fresh microVM from X; X is never modified. A disposable run
  (keep=False) leaves no image, so `RunResult.image_ref` is X, the snapshot that reproduces it.
  A kept run (keep=True) returns the new image's UUID; `tag=` names it (applied only when the
  command exits 0, so a failed build is never a cache hit).
* Output: the API records stdout/stderr up to `truncate_output_at` bytes per stream and flags
  truncation. The SDK's default is 65535 bytes (the docs say 1 MiB); the API accepts up to 10 MiB
  and rejects more. Breakwater asks for 10 MiB on every run, since a perf `make(n)` ladder returns
  up to ~2 MB of JSON, and treats a truncated stream as a failed run.
* Networking: 0.3.6 has no option to disable it, and the microVM has internet access by default.
  Breakwater runs every non-build command under `unshare -n` (the process is root in the microVM),
  which drops it into an empty network namespace: name resolution and connections fail. Build steps
  pass `network=True`.
* Env: `preserve_env=True` bakes a run's env into the resulting image, but it only reaches later
  `shell=` runs, not `command`/`args` runs (checked both ways on 2026-10-18). So every run passes
  RUN_ENV explicitly: PYTHONHASHSEED=0 is what makes cachegrind Ir repeat to the instruction, as the
  Docker harness image's ENV does.
* Resources: per-run user/system CPU, max RSS, context switches and a cost (USD) come back on the
  operation result (`result._raw`, a private attribute; the public surface only has `cost`). The
  docs call the resource fields diagnostics; units match getrusage (seconds, kB).
* Limits (`whoami`): 50 concurrent instances, 3600 s max timeout. A timed-out command returns
  exit -1 with `timed_out` set, not an exception.

Retries: a 429, a 5xx, a transport error or a client-side HTTP timeout is retried with backoff.
That is safe for disposable runs: a run has no side effects outside its microVM, and when the SDK
loses contact with an operation it already started, it cancels it before raising. A kept run is
not blindly resubmitted: before each retry the tag is looked up, and if a previous attempt did
finish, its image is returned instead. The SDK's own retrier covers 429s on submission; this layer
adds the rest and never retries a run the sandbox itself reported as failed.
"""

from __future__ import annotations

import logging
import random
import threading
import time
from collections.abc import Callable
from typing import Any

from breakwater.backends.base import Resources, RunResult

MAX_CONCURRENCY = 24  # under the 50-instance limit, leaving room for image builds and a second session
OUTPUT_CAP = 10 * 1024 * 1024  # the API's maximum per stream; the SDK default (65535) truncates our ladders
MAX_TIMEOUT_S = 3600  # instance_max_timeout from whoami
INPUTS_DIR = "/inputs"  # same place the Docker backend mounts `files=`
NO_NETWORK = ("unshare", "-n")
RUN_ENV = {"PYTHONHASHSEED": "0", "PYTHONDONTWRITEBYTECODE": "1"}  # docker/harness.Dockerfile ENV, per run here
RETRIES = 4
BACKOFF_S = (1.0, 3.0, 9.0, 20.0)

# Error class names (duck-typed so tests can use fakes) that mean "the request may not have been
# served": rate limit, server-side rejection, broken transport, client-side HTTP timeout.
_TRANSIENT = frozenset({"TooManyRequestsError", "ApiTimeoutError", "ContreeTransportError"})

logger = logging.getLogger(__name__)


def transient(exc: BaseException) -> bool:
    """Is this SDK error worth a retry? 429, 5xx, transport and HTTP-timeout errors are. A failed or
    cancelled operation, a 4xx other than 429, and our own run timeout are not."""
    names = {c.__name__ for c in type(exc).__mro__}
    if names & _TRANSIENT:
        return True
    if "ApiStatusCodeError" in names:
        return (getattr(exc, "status", None) or 0) >= 500
    return False


class ContreeBackend:
    name = "contree"

    def __init__(self, *, client: Any = None, max_concurrency: int = MAX_CONCURRENCY, network: bool = False,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        if client is None:
            from contree_sdk import ContreeSync  # optional dependency: `uv sync --extra sandboxes`

            # The SDK logs "Token expires in 0 hours" on every client: whoami reports a sliding
            # 300 s window, not the key's expiry (docs/feedback-log.md). Keep real errors.
            logging.getLogger("contree_sdk.sdk.client._base").setLevel(logging.ERROR)
            client = ContreeSync()
        self.contree = client
        self.max_concurrency = max_concurrency
        self.network = network  # default for runs; the image builder passes network=True
        self._slots = threading.BoundedSemaphore(max_concurrency)
        self._sleep = sleep

    # -- discovery -------------------------------------------------------------------------------

    def whoami(self) -> dict:
        """Auth check: token, permissions, limits and running instances (what `doctor` prints)."""
        info = self.contree.get_token_info(refresh=True)
        return {"token": str(info.token_uuid)[:8], "permissions": dict(info.permissions),
                "limits": dict(info.limits), "running": dict(info.operations_stat)}

    def find_tag(self, tag: str) -> str | None:
        """UUID of the image carrying `tag`, or None. Tags are how pair images are content-addressed."""
        try:
            return str(self.contree.images.use(tag, strict=True).uuid)
        except Exception as e:  # NotFoundError; anything else is a real problem
            if "NotFoundError" in {c.__name__ for c in type(e).__mro__}:
                return None
            raise

    def image_exists(self, ref: str) -> bool:
        try:
            self.contree.images.use(ref, strict=True)
            return True
        except Exception as e:
            if "NotFoundError" in {c.__name__ for c in type(e).__mro__}:
                return False
            raise

    def tag(self, image_ref: str, tag: str) -> None:
        self.contree.images.use(image_ref).tag_as(tag)

    # -- runs ------------------------------------------------------------------------------------

    def run(self, image_ref, cmd, *, files=None, stdin=None, timeout_s=300, keep=False, tag=None,
            network: bool | None = None, env: dict[str, str] | None = None) -> RunResult:
        if timeout_s > MAX_TIMEOUT_S:  # probe batches ask for 60 + 20 s per input; the sandbox kills at the limit
            logger.info("contree: timeout_s=%d clamped to the Sandboxes limit of %d s", timeout_s, MAX_TIMEOUT_S)
            timeout_s = MAX_TIMEOUT_S
        argv = list(cmd)
        if not (self.network if network is None else network):
            argv = [*NO_NETWORK, *argv]
        uploads = {(rel if rel.startswith("/") else f"{INPUTS_DIR}/{rel}"): data for rel, data in (files or {}).items()}
        kwargs: dict[str, Any] = dict(
            command=argv[0], args=tuple(argv[1:]), stdin=stdin.encode() if isinstance(stdin, str) else stdin,
            files=uploads or None, timeout=timeout_s, disposable=not keep, truncate_output_at=OUTPUT_CAP,
        )
        kwargs.update(env={**RUN_ENV, **(env or {})}, preserve_env=keep)
        with self._slots:
            for attempt in range(RETRIES + 1):
                try:
                    return self._run_once(image_ref, kwargs, keep=keep, tag=tag)
                except Exception as e:
                    if attempt >= RETRIES or not transient(e):
                        raise
                    if keep and tag and (found := self.find_tag(tag)):
                        # A previous attempt finished after we lost contact: use it, don't rebuild.
                        logger.warning("contree: %s; image %s already exists, using it", type(e).__name__, tag)
                        return RunResult("", f"[contree] recovered image {tag} after {type(e).__name__}", 0, 0,
                                         self.name, image_ref=found)
                    delay = BACKOFF_S[min(attempt, len(BACKOFF_S) - 1)] * (0.5 + random.random())
                    logger.warning("contree: %s on attempt %d, retrying in %.1f s", type(e).__name__, attempt + 1, delay)
                    self._sleep(delay)
        raise AssertionError("unreachable")

    def _run_once(self, image_ref: str, kwargs: dict, *, keep: bool, tag: str | None) -> RunResult:
        image = self.contree.images.use(image_ref)
        t0 = time.perf_counter()
        done = image.run(**kwargs).wait()
        duration_ms = int((time.perf_counter() - t0) * 1000)
        result = done.result
        raw = getattr(result, "_raw", None)
        raw_result = getattr(raw, "result", None)
        res = getattr(raw_result, "resources", None)
        state = getattr(raw_result, "state", None)
        stdout, stderr = _text(result.stdout), _text(result.stderr)
        exit_code = int(result.exit_code)
        notes = []
        if getattr(state, "timed_out", False):
            notes.append(f"[contree] command timed out after {kwargs['timeout']} s and was killed")
        if getattr(result, "truncated", False):
            notes.append(f"[contree] output exceeded the {OUTPUT_CAP} byte cap and was truncated")
            exit_code = exit_code or 1  # a parser downstream must not trust a cut-off stream
        if notes:
            stderr = (stderr + "\n" if stderr else "") + "\n".join(notes)
        new_uuid = str(done.uuid) if keep and getattr(done, "uuid", None) else None
        if keep and tag and new_uuid and exit_code == 0:
            self.tag(new_uuid, tag)
        return RunResult(
            stdout=stdout, stderr=stderr, exit_code=exit_code, duration_ms=duration_ms, backend=self.name,
            image_ref=new_uuid or str(image_ref),
            resources=Resources(
                user_cpu_s=getattr(res, "user_cpu_time", None),
                sys_cpu_s=getattr(res, "system_cpu_time", None),
                max_rss_kb=getattr(res, "max_rss", None),
                involuntary_switches=getattr(res, "involuntary_switches", None),
                cost_usd=getattr(result, "cost", None),
            ),
        )


def _text(v: Any) -> str:
    if v is None:
        return ""
    return v.decode("utf-8", "replace") if isinstance(v, bytes) else str(v)
