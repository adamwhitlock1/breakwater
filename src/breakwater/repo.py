"""Read-only access to the repo under audit: the diff and the target module's source, for the planner.

Uses a blobless clone cached under artifacts/cache/. Nothing here executes repo code.
Tests and docs are excluded from the diff on purpose: the adversary should find behavior changes
from the implementation, not from tests that might already hint at the bug.
"""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path

CACHE = Path("artifacts/cache/repos")
EXCLUDE = (":(exclude)tests/**", ":(exclude)test/**", ":(exclude)docs/**", ":(exclude)*.md", ":(exclude)*.rst")
MAX_DIFF_CHARS = 40_000
MAX_SOURCE_CHARS = 60_000


@dataclass
class Context:
    repo: str
    base: str
    head: str
    target: str
    diff: str
    module_path: str | None
    module_source: str
    diff_stat: str


def _git(path: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(path), *args], capture_output=True, text=True, check=True).stdout


def checkout(repo: str) -> Path:
    path = CACHE / hashlib.sha256(repo.encode()).hexdigest()[:12]
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "-q", "--filter=blob:none", "--no-checkout", repo, str(path)], check=True)
    return path


def _has(path: Path, ref: str) -> bool:
    return subprocess.run(["git", "-C", str(path), "cat-file", "-e", f"{ref}^{{commit}}"],
                          capture_output=True).returncode == 0


def _ensure(path: Path, *refs: str) -> None:
    """Make refs resolvable. Commits that only live on PR branches (e.g. an intermediate commit of a
    merged PR) are not on any branch, so fall back to fetching GitHub's pull-request refs."""
    missing = [r for r in refs if not _has(path, r)]
    if missing:
        _git(path, "fetch", "-q", "origin")
    if any(not _has(path, r) for r in missing):
        _git(path, "fetch", "-q", "origin", "+refs/pull/*/head:refs/remotes/origin/pr/*")
    for r in refs:
        if not _has(path, r):
            raise ValueError(f"cannot resolve {r!r} in {path}; use a full SHA or a branch/tag name")


def gather(repo: str, base: str, head: str, target: str) -> Context:
    path = checkout(repo)
    _ensure(path, base, head)
    diff = _git(path, "diff", base, head, "--", ".", *EXCLUDE)
    stat = _git(path, "diff", "--stat", base, head, "--", ".", *EXCLUDE)
    if len(diff) > MAX_DIFF_CHARS:
        diff = diff[:MAX_DIFF_CHARS] + f"\n... [diff truncated at {MAX_DIFF_CHARS} chars]"

    module = target.split(":")[0].replace(".", "/") + ".py"
    files = _git(path, "ls-tree", "-r", "--name-only", head).splitlines()
    match = next((f for f in files if f.endswith(module)), None)
    if match is None:  # package __init__
        pkg = target.split(":")[0].replace(".", "/") + "/__init__.py"
        match = next((f for f in files if f.endswith(pkg)), None)
    source = _git(path, "show", f"{head}:{match}") if match else ""
    if len(source) > MAX_SOURCE_CHARS:
        source = source[:MAX_SOURCE_CHARS] + "\n# ... [source truncated]"
    return Context(repo, base, head, target, diff, match, source, stat)
