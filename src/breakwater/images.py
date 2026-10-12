"""Target images: one image per (base, head) pair, with each side in its own virtualenv.

    /envs/base/bin/python   <- base requirement installed
    /envs/head/bin/python   <- head requirement installed
    /usr/local/bin/python   <- Hypothesis only (runs the search; never imports the target)
    /harness/               <- breakwater.harness: worker.py, compare.py, diffrun.py (stdlib + Hypothesis)

Requirements are pip strings, so refs can be git commits (`git+https://...@sha`) or releases
(`packaging==26.1`), or `src+...` for repos that aren't packages (see `src_req`). Network is needed only at build time; probe runs use --network=none.
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


def src_req(repo: str, ref: str, subdir: str = "", deps: tuple[str, ...] | list[str] = ()) -> str:
    """A repo that is not a package (a directory of scripts): cloned at `ref`, `subdir` put on the
    venv's path with a .pth file, `deps` pip-installed. Encoded as one string so the image tag stays
    content-addressed: `src+<repo>@<ref>#subdir=<dir>&deps=<a,b>`."""
    return f"src+{repo}@{ref}#subdir={subdir}&deps={','.join(deps)}"


def req_for(repo: str, ref: str, install: dict | None = None) -> str:
    """Requirement for a corpus item: a pip-installable package by default, or install={"mode": "src",
    "subdir": ..., "deps": [...]} for script repos. install["exclude_newer"] (a date) resolves
    dependencies as of that date, so an unpinned dependency can't drift past what the PR ran against."""
    install = install or {}
    req = src_req(repo, ref, install.get("subdir", ""), install.get("deps", [])) if install.get("mode") == "src" \
        else git_req(repo, ref)
    return f"{req};exclude-newer={install['exclude_newer']}" if install.get("exclude_newer") else req


def _install_lines(req: str, side: str) -> list[str]:
    py = f"/envs/{side}/bin/python"
    req, _, newer = req.partition(";exclude-newer=")
    pin = f" --exclude-newer {newer}" if newer else ""
    if not req.startswith("src+"):
        return [f'RUN uv pip install -q{pin} --python {py} "{req}"']
    spec, _, opts = req[4:].partition("#")
    repo, _, ref = spec.rpartition("@")
    o = dict(kv.split("=", 1) for kv in opts.split("&") if "=" in kv)
    deps = [d for d in o.get("deps", "").split(",") if d]
    src = f"/src/{side}/{o.get('subdir', '')}".rstrip("/")
    lines = [f"RUN git clone -q {repo} /src/{side} && git -C /src/{side} checkout -q {ref}"]
    if deps:
        lines.append(f"RUN uv pip install -q{pin} --python {py} " + " ".join(f'"{d}"' for d in deps))
    lines.append(f'RUN {py} -c "import site, pathlib; '
                 f"pathlib.Path(site.getsitepackages()[0], 'breakwater_src.pth').write_text('{src}')\"")
    return lines


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
            *_install_lines(base_req, "base"),
            *_install_lines(head_req, "head"),
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
