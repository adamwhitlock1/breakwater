"""Target images: one image per (base, head) pair, with each side in its own virtualenv.

    /envs/base/bin/python   <- base requirement installed
    /envs/head/bin/python   <- head requirement installed
    /usr/local/bin/python   <- Hypothesis only (runs the search; never imports the target)
    /harness/               <- breakwater.harness: worker.py, compare.py, diffrun.py (stdlib + Hypothesis)

Requirements are pip strings, so refs can be git commits (`git+https://...@sha`) or releases
(`packaging==26.1`), or `src+...` for repos that aren't packages (see `src_req`). Network is needed
only at build time. The tag is content-addressed (recipe + requirements + harness sources), so
rebuilding the same pair is a cache hit.

Two builders produce the same layout:

* Docker (`build_pair(..., backend="docker")`): a Dockerfile on top of the local `breakwater-harness`
  image; `PairImage.ref` is the Docker tag.
* Token Factory Sandboxes (`backend=ContreeBackend`): a one-time kept harness image
  (python:3.12-slim + valgrind + git + uv, tagged `bw-harness:<hash>`), then one kept run per pair
  that creates both venvs, installs both sides and uploads the harness files with `files=`.
  `PairImage.ref` is the resulting image UUID, which every report cites; `PairImage.tag` is the
  content-addressed tag it was found or built under. Both are looked up by tag before building.
"""

from __future__ import annotations

import hashlib
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

HARNESS = Path(__file__).parent / "harness"
HARNESS_FILES = ("worker.py", "compare.py", "diffrun.py")
BASE_IMAGE = "breakwater-harness"
HYPOTHESIS = "hypothesis==6.168.5"  # keep in sync with uv.lock

# Sandboxes harness image: the same recipe as docker/harness.Dockerfile, as a shell script run on
# python:3.12-slim with networking. uv comes from PyPI (no multi-stage COPY in a sandbox run).
CONTREE_BASE = "python:3.12-slim"
UV_PIP = "uv==0.7.22"
HARNESS_ENV = {"PYTHONHASHSEED": "0", "PYTHONDONTWRITEBYTECODE": "1", "UV_CACHE_DIR": "/cache/uv"}
HARNESS_RECIPE = "\n".join([
    "set -eu",
    "apt-get update -qq",
    "apt-get install -y -qq --no-install-recommends valgrind git ca-certificates >/dev/null",
    "rm -rf /var/lib/apt/lists/*",
    f'pip install -q --root-user-action=ignore "{UV_PIP}"',
    "mkdir -p /work /cache/uv",
    "valgrind --version && git --version && uv --version",
])


@dataclass(frozen=True)
class PairImage:
    ref: str  # Docker tag, or the ConTree image UUID
    base_req: str
    head_req: str
    tag: str = ""  # content-addressed tag (ConTree: the tag `ref` was built or found under)

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
    """Shell commands that install `req` into /envs/<side> (one per line; Docker prefixes RUN)."""
    py = f"/envs/{side}/bin/python"
    req, _, newer = req.partition(";exclude-newer=")
    pin = f" --exclude-newer {newer}" if newer else ""
    if not req.startswith("src+"):
        return [f'uv pip install -q{pin} --python {py} "{req}"']
    spec, _, opts = req[4:].partition("#")
    repo, _, ref = spec.rpartition("@")
    o = dict(kv.split("=", 1) for kv in opts.split("&") if "=" in kv)
    deps = [d for d in o.get("deps", "").split(",") if d]
    src = f"/src/{side}/{o.get('subdir', '')}".rstrip("/")
    lines = [f"git clone -q {repo} /src/{side} && git -C /src/{side} checkout -q {ref}"]
    if deps:
        lines.append(f"uv pip install -q{pin} --python {py} " + " ".join(f'"{d}"' for d in deps))
    lines.append(f'{py} -c "import site, pathlib; '
                 f"pathlib.Path(site.getsitepackages()[0], 'breakwater_src.pth').write_text('{src}')\"")
    return lines


def _pair_lines(base_req: str, head_req: str) -> list[str]:
    return [
        "uv venv -q --python /usr/local/bin/python /envs/base && uv venv -q --python /usr/local/bin/python /envs/head",
        *_install_lines(base_req, "base"),
        *_install_lines(head_req, "head"),
        f'uv pip install -q --system "{HYPOTHESIS}"',
    ]


def _digest(*parts: str) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update(part.encode())
        h.update(b"\0")
    return h.hexdigest()[:16]


def _harness_sources() -> list[str]:
    return [(HARNESS / f).read_text() for f in HARNESS_FILES]


def harness_tag() -> str:
    """Content-addressed tag of the Sandboxes harness image."""
    return f"bw-harness:{_digest(CONTREE_BASE, HARNESS_RECIPE, UV_PIP, repr(sorted(HARNESS_ENV.items())))}"


def _tag(base_req: str, head_req: str, base: str = BASE_IMAGE) -> str:
    return f"bw-pair:{_digest(base, HYPOTHESIS, base_req, head_req, *_harness_sources())}"


def _exists(tag: str) -> bool:
    return subprocess.run(["docker", "image", "inspect", tag], capture_output=True).returncode == 0


def _backend_name(backend: Any) -> str:
    if backend is None:
        return "docker"
    return backend if isinstance(backend, str) else backend.name


def image_exists(ref: str, backend: Any = None) -> bool:
    """Does a recorded `PairImage.ref` still exist on this backend? (Backtests reuse recorded images.)"""
    if _backend_name(backend) == "contree":
        return bool(ref) and backend.image_exists(ref)
    return _exists(ref)


def build_pair(base_req: str, head_req: str, *, backend: Any = None, quiet: bool = True) -> PairImage:
    """Build (or find) the pair image on `backend`: a backend object, a backend name, or None (Docker)."""
    if _backend_name(backend) == "contree":
        if isinstance(backend, str):
            raise TypeError("build_pair(backend='contree') needs the ContreeBackend instance")
        return build_pair_contree(backend, base_req, head_req)
    return build_pair_docker(base_req, head_req, quiet=quiet)


def build_pair_docker(base_req: str, head_req: str, *, quiet: bool = True) -> PairImage:
    tag = _tag(base_req, head_req)
    if not _exists(tag):
        dockerfile = "\n".join([
            f"FROM {BASE_IMAGE}",
            *(f"RUN {line}" for line in _pair_lines(base_req, head_req)),
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
    return PairImage(tag, base_req, head_req, tag)


def build_harness_contree(backend: Any, *, log=None) -> str:
    """The one-time kept harness image on Sandboxes; returns its UUID. Found by tag when it exists."""
    tag = harness_tag()
    if found := backend.find_tag(tag):
        return found
    if log:
        log(f"building Sandboxes harness image {tag} from {CONTREE_BASE} (one-time)")
    res = backend.run(CONTREE_BASE, ["sh", "-c", HARNESS_RECIPE], keep=True, tag=tag, timeout_s=900,
                      network=True, env=HARNESS_ENV)
    if res.exit_code != 0 or not res.image_ref:
        raise RuntimeError(f"Sandboxes harness image build failed (exit {res.exit_code}):\n{res.stderr[-1500:]}")
    return res.image_ref


def build_pair_contree(backend: Any, base_req: str, head_req: str, *, log=None) -> PairImage:
    """One kept run on the harness image: both venvs, both sides installed, harness files uploaded.
    The result is tagged only when the install succeeds, so a failed build is never a cache hit."""
    tag = _tag(base_req, head_req, base=harness_tag())
    if found := backend.find_tag(tag):
        return PairImage(found, base_req, head_req, tag)
    harness = build_harness_contree(backend, log=log)
    if log:
        log(f"building Sandboxes pair image {tag}")
    script = "\n".join(["set -eu", *_pair_lines(base_req, head_req), "ls /harness"])
    files = {f"/harness/{f}": (HARNESS / f).read_bytes() for f in HARNESS_FILES}
    res = backend.run(harness, ["sh", "-c", script], files=files, keep=True, tag=tag, timeout_s=1800,
                      network=True, env=HARNESS_ENV)
    if res.exit_code != 0 or not res.image_ref:
        raise RuntimeError(f"Sandboxes pair image build failed for {base_req} / {head_req} "
                           f"(exit {res.exit_code}):\n{res.stderr[-1500:]}")
    return PairImage(res.image_ref, base_req, head_req, tag)
