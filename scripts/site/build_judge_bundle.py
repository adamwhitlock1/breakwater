"""Bundle the packaging sources the judge box runs in the browser (site/judge.html, via Pyodide).

    uv run python scripts/site/build_judge_bundle.py

Writes artifacts/judge/packaging-1082.json: `version.py`, `__init__.py` and the modules version.py
imports (followed per commit: `_structures.py` was removed in between) at four commits of pypa/packaging, so judges can watch #1082's fast path
change behaviour and later fixes restore it. Sources come from the git cache (repo.checkout); the
bundle is committed so building the site never needs network access.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from breakwater.repo import _ensure, _git, checkout  # noqa: E402

REPO = "https://github.com/pypa/packaging"
_RELATIVE = re.compile(r"^from \.(\w+) import", re.MULTILINE)


def files_at(path: Path, sha: str) -> dict[str, str]:
    """`version.py`, `__init__.py` and every module version.py imports relatively (transitively)."""
    files: dict[str, str] = {}
    todo = ["__init__", "version"]
    while todo:
        mod = todo.pop()
        name = f"packaging/{mod}.py"
        if name in files:
            continue
        files[name] = _git(path, "show", f"{sha}:src/{name}")
        todo += [m for m in _RELATIVE.findall(files[name]) if f"packaging/{m}.py" not in files]
    return dict(sorted(files.items()))
VERSIONS = [
    ("base", "Before #1082", "59f183fe90da403e41eef339ce9088bda0fe4cd3", "the parent of #1082's merge"),
    ("pr", "#1082, intermediate commit", "61967cca278dc51389b8973ba65bbbf23eaa3eda", "the fast path as first pushed"),
    ("merged", "#1082 as merged", "ee13ba2c1c9a01c97a08ca9d98ff9fa6f0a0a67b", "after review fixes"),
    ("fixed", "After #1155", "06c6555f44f0f7b84459c876375c5b1d52ee7fef", "int-digit-limit fix"),
]


def main() -> int:
    path = checkout(REPO)
    _ensure(path, *(v[2] for v in VERSIONS))
    bundle = {"repo": REPO, "target": "packaging.version:Version",
              "versions": [{"key": k, "label": label, "commit": sha, "note": note,
                            "files": files_at(path, sha)}
                           for k, label, sha, note in VERSIONS]}
    out = Path("artifacts/judge/packaging-1082.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(bundle, ensure_ascii=False))
    print(f"wrote {out} ({out.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
