"""Target images: one image per (base, head) pair, with each side in its own virtualenv.

    /envs/base/bin/python   <- base requirement installed
    /envs/head/bin/python   <- head requirement installed
    /usr/local/bin/python   <- Hypothesis only (runs the search; never imports the target)
    /harness/               <- breakwater.harness: worker.py, compare.py, diffrun.py (stdlib + Hypothesis)

Requirements are pip strings, so refs can be git commits (`git+https://...@sha`) or releases
(`packaging==26.1`). Network is needed only at build time; probe runs use --network=none.
The tag is content-addressed, so rebuilding the same pair is a cache hit.

This is the Docker implementation. The Sandboxes version builds the same layout as a kept
ConTree image and returns its UUID.
"""

from __future__ import annotations

import hashlib
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

HARNESS = Path(__file__).parent / "harness"
HARNESS_FILES = ("worker.py", "compare.py", "diffrun.py")
BASE_IMAGE = "breakwater-harness"
HYPOTHESIS = "hypothesis==6.168.5"  # keep in sync with uv.lock


@dataclass(frozen=True)
class PairImage:
    ref: str  # Docker tag (later: ConTree image UUID)
    base_req: str
    head_req: str

    BASE_PY = "/envs/base/bin/python"
    HEAD_PY = "/envs/head/bin/python"
    SYS_PY = "/usr/local/bin/python"
    WORKER = "/harness/worker.py"
    DIFFRUN = "/harness/diffrun.py"


def git_req(repo: str, ref: str) -> str:
    return f"git+{repo}@{ref}"


def _tag(base_req: str, head_req: str) -> str:
    h = hashlib.sha256()
    for part in (BASE_IMAGE, HYPOTHESIS, base_req, head_req, *((HARNESS / f).read_text() for f in HARNESS_FILES)):
        h.update(part.encode())
        h.update(b"\0")
    return f"bw-pair:{h.hexdigest()[:16]}"


def _exists(tag: str) -> bool:
    return subprocess.run(["docker", "image", "inspect", tag], capture_output=True).returncode == 0


def build_pair(base_req: str, head_req: str, *, quiet: bool = True) -> PairImage:
    tag = _tag(base_req, head_req)
    if not _exists(tag):
        dockerfile = "\n".join([
            f"FROM {BASE_IMAGE}",
            "RUN uv venv -q --python /usr/local/bin/python /envs/base && uv venv -q --python /usr/local/bin/python /envs/head",
            f'RUN uv pip install -q --python /envs/base/bin/python "{base_req}"',
            f'RUN uv pip install -q --python /envs/head/bin/python "{head_req}"',
            f'RUN uv pip install -q --system "{HYPOTHESIS}"',
            "COPY harness/ /harness/",
        ])
        with tempfile.TemporaryDirectory() as ctx:
            (Path(ctx) / "Dockerfile").write_text(dockerfile)
            (Path(ctx) / "harness").mkdir()
            for f in HARNESS_FILES:
                (Path(ctx) / "harness" / f).write_bytes((HARNESS / f).read_bytes())
            proc = subprocess.run(["docker", "build", "-q" if quiet else "--progress=plain", "-t", tag, ctx],
                                  capture_output=quiet, text=True)
            if proc.returncode != 0:
                raise RuntimeError(f"image build failed for {base_req} / {head_req}:\n{(proc.stderr or '')[-1500:]}")
    return PairImage(tag, base_req, head_req)
