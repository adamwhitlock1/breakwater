"""Reproduce the pypa/packaging 2026 perf-PR regressions that anchor the Breakwater backtest.

Each case installs packaging at specific refs into throwaway uv environments and records
how the same inputs behave. Nothing here uses an LLM; this is the ground truth the
adversary must later rediscover on its own.

    uv run python scripts/day1/ground_truth.py            # writes artifacts/day1/ground_truth.json
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

REPO = "https://github.com/pypa/packaging"
OUT = Path("artifacts/day1/ground_truth.json")

# PR #1082: fast path for simple versions. Commits in PR order, then the merge.
PR1082_REFS = {
    "base 59f183fe": "59f183fe90da",
    "c33a5218 (add fast path)": "c33a52184a2b",
    "61967cca (drop fastpath regex)": "61967cca278d",
    "4ecd2734 (simple version indicators)": "4ecd273424f1",
    "merge ee13ba2c": "ee13ba2c1c9a",
}
VERSION_INPUTS = [
    "1.0",
    "1. 0",
    "١.٠",  # Arabic-Indic digits "١.٠"
    "1.0 ",  # trailing no-break space
    " 1.0 ",
    "v1.0",
    "1" * 5000 + ".0",
]

# PR #1155: oversized integer components should raise the same thing on every path.
PR1155_REFS = {"base 905c90c1": "905c90c1eb8c", "merge 06c6555f": "06c6555f44f0"}

# PR #1108 -> #1109: SpecifierSet dedup changed equality.
PR1108_REFS = {
    "base 20f1523c": "20f1523cf37d",
    "#1108 merge f59d6ee9": "f59d6ee9afe2",
    "#1109 fix 9b972011": "9b972011a531",
}

VERSION_PROBE = textwrap.dedent(
    """
    import json, sys
    from packaging.version import Version
    out = {}
    for s in json.loads(sys.argv[1]):
        key = s if len(s) < 40 else s[:12] + f"...({len(s)} chars)"
        try:
            out[key] = "OK " + str(Version(s))[:40]
        except Exception as e:
            out[key] = "RAISE " + type(e).__module__ + "." + type(e).__name__
    print(json.dumps(out))
    """
)

SPECSET_PROBE = textwrap.dedent(
    """
    import json
    from packaging.specifiers import SpecifierSet
    a, b = SpecifierSet(">1.0.0,>1.0"), SpecifierSet(">1.0")
    print(json.dumps({"SpecifierSet('>1.0.0,>1.0') == SpecifierSet('>1.0')": a == b,
                      "len(SpecifierSet('>1.0.0,>1.0'))": len(a)}))
    """
)

# The bug only appears once the cached sort key is populated (by a comparison or hash),
# because that cache references packaging._structures, which #1116 removed.
PICKLE_DUMP = textwrap.dedent(
    """
    import pickle, sys
    from packaging.version import Version
    fresh, compared = Version("1.2.3"), Version("1.2.3")
    compared < Version("2")
    sys.stdout.buffer.write(pickle.dumps({"fresh": fresh, "compared": compared}))
    """
)
PICKLE_LOAD = textwrap.dedent(
    """
    import pickle, sys
    try:
        d = pickle.loads(sys.stdin.buffer.read())
        print("OK", {k: str(v) for k, v in d.items()})
    except Exception as e:
        print("RAISE", type(e).__name__, str(e)[:80])
    """
)


def run_with(spec: str, code: str, *args: str, stdin: bytes | None = None) -> bytes:
    cmd = ["uv", "run", "--quiet", "--no-project", "--python", "3.12", "--with", spec, "python", "-c", code, *args]
    proc = subprocess.run(cmd, input=stdin, capture_output=True, timeout=600)
    if proc.returncode != 0:
        raise RuntimeError(f"{spec}: {proc.stderr.decode()[-800:]}")
    return proc.stdout


def git_spec(sha: str) -> str:
    return f"packaging @ git+{REPO}@{sha}"


def main() -> int:
    results: dict[str, dict] = {}

    print("== #1082 fast path: Version() across PR commits")
    results["pr1082_version"] = {}
    for label, sha in PR1082_REFS.items():
        res = json.loads(run_with(git_spec(sha), VERSION_PROBE, json.dumps(VERSION_INPUTS)))
        results["pr1082_version"][label] = res
        print(f"  {label}: {res}")

    print("== #1155 oversized int component")
    results["pr1155_bigint"] = {}
    for label, sha in PR1155_REFS.items():
        res = json.loads(run_with(git_spec(sha), VERSION_PROBE, json.dumps(["1" * 5000 + ".0", "1." + "9" * 5000])))
        results["pr1155_bigint"][label] = res
        print(f"  {label}: {res}")

    print("== #1108 -> #1109 SpecifierSet equality")
    results["pr1108_specset"] = {}
    for label, sha in PR1108_REFS.items():
        res = json.loads(run_with(git_spec(sha), SPECSET_PROBE))
        results["pr1108_specset"][label] = res
        print(f"  {label}: {res}")

    print("== #1116 -> #1162/#1163 pickle compatibility (pickled with 26.0)")
    blob = run_with("packaging==26.0", PICKLE_DUMP)
    results["pr1116_pickle"] = {}
    for spec in ["packaging==26.0", "packaging==26.1", "packaging==26.2"]:
        res = run_with(spec, PICKLE_LOAD, stdin=blob).decode().strip()
        results["pr1116_pickle"][f"load with {spec}"] = res
        print(f"  load with {spec}: {res}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
