"""Build corpus/packaging.json: pypa/packaging's 2026 library perf PRs, with a callable target per PR
and the documented ground truth. Base = first parent of the merge commit (squash merges).

    uv run python scripts/backtest/build_packaging_corpus.py
"""

import json
import subprocess
from pathlib import Path

REPO = "https://github.com/pypa/packaging"
V = ("packaging.version:Version", ["str", "repr", "attr:release", "attr:public"])
SS = ("packaging.specifiers:SpecifierSet", ["str", "len"])
SS_FILTER = ("packaging.specifiers:SpecifierSet#filter", ["value"], ["str", "list[str]"])
SS_CONTAINS = ("packaging.specifiers:SpecifierSet#contains", ["value"], ["str", "str"])
SPEC = ("packaging.specifiers:Specifier", ["str", "repr"])
SPEC_CONTAINS = ("packaging.specifiers:Specifier#contains", ["value"], ["str", "str"])
MARKER = ("packaging.markers:Marker", ["str", "repr"])
MARKER_EVAL = ("packaging.markers:Marker#evaluate", ["value"])
REQ = ("packaging.requirements:Requirement", ["str", "attr:extras", "attr:specifier"])
CANON = ("packaging.utils:canonicalize_name", ["value"])

# (pr, targets, known issues). Known issue: id, how to recognise it, fixed by, status.
ITEMS = [
    (997, [V], []),
    (1028, [REQ], []),
    (1029, [MARKER], []),
    # Found by Breakwater's first backtest, then confirmed by hand: #1030 stopped lowercasing non-ASCII
    # letters; #1064 (a perf fix whose description only mentions speed) restored it 14 days later.
    (1030, [CANON], [{"id": "unicode-lowercase", "match": {"probe": "P1", "traits": "non-ascii"}, "fixed_by": 1064,
                      "status": "verified", "discovered_by": "breakwater"}]),
    (1032, [MARKER], []),
    (1058, [V], []),
    (1064, [CANON], []),
    (1076, [SS_FILTER], []),
    (1081, [SPEC], []),
    (1082, [V], [{"id": "oversized-int-exception", "match": {"probe": "P2", "traits": "long-digits"},
                  "fixed_by": 1155, "status": "verified"}]),
    (1083, [V], []),
    (1105, [SS_FILTER], []),
    (1106, [SPEC], []),
    (1108, [SS], [{"id": "dedup-equality", "match": {"probe": "P3", "detail": "eq"}, "fixed_by": 1109, "status": "verified"},
                  {"id": "dedup-str-len", "match": {"probe": "P1"}, "fixed_by": 1109, "status": "verified"},
                  {"id": "old-pickles-break-comparison", "match": {"probe": "P4"}, "fixed_by": "26.2", "status": "verified"}]),
    (1111, [SPEC_CONTAINS], []),
    (1115, [V], []),
    (1116, [V], [{"id": "old-pickles-fail-to-load", "match": {"probe": "P4"}, "fixed_by": 1163, "status": "verified"}]),
    (1118, [V], [{"id": "hash-cache-copy", "match": {"probe": "P3"}, "fixed_by": 1242, "status": "candidate"}]),
    (1147, [MARKER], [{"id": "marker-pickle", "match": {"probe": "P4"}, "fixed_by": 1171, "status": "candidate"}]),
    (1236, [("packaging.tags:parse_tag", ["value"])], []),
    (1250, [MARKER_EVAL], []),
    (1253, [SS_CONTAINS], []),
    (1256, [("packaging.utils:parse_wheel_filename", ["value"])], []),
    (1258, [REQ], []),
    (1259, [SS_CONTAINS], []),
    (1320, [REQ], [{"id": "requirement-pickle", "match": {"probe": "P4"}, "fixed_by": 1171, "status": "candidate"}]),
    (1371, [MARKER], []),
    (1429, [MARKER], []),
]

# The intermediate commit of #1082 that review caught by hand (not merged as-is).
EXTRA = [{
    "id": "1082@61967cca", "pr": 1082, "title": "perf: fast path for simple versions (intermediate commit 61967cca)",
    "base": "59f183fe90da403e41eef339ce9088bda0fe4cd3", "head": "61967cca278dc51389b8973ba65bbbf23eaa3eda", "merged": "2026-02-11",
    "targets": [{"callable": V[0], "observe": V[1], "arg_kinds": ["str"]}],
    "known": [{"id": "unicode-digits", "match": {"probe": "P2", "traits": "non-ascii"}, "fixed_by": "review", "status": "verified"},
              {"id": "inner-whitespace", "match": {"probe": "P2", "traits": "whitespace"}, "fixed_by": "review", "status": "verified"},
              {"id": "oversized-int-exception", "match": {"probe": "P2", "traits": "long-digits"}, "fixed_by": 1155, "status": "verified"}],
}]


def gh(*args: str) -> dict:
    return json.loads(subprocess.run(["gh", "api", *args], capture_output=True, text=True, check=True).stdout)


def main() -> None:
    items = list(EXTRA)
    for pr, targets, known in ITEMS:
        info = gh(f"repos/pypa/packaging/pulls/{pr}")
        merge = info["merge_commit_sha"]
        parent = gh(f"repos/pypa/packaging/commits/{merge}")["parents"][0]["sha"]
        items.append({
            "id": f"#{pr}", "pr": pr, "title": info["title"], "base": parent, "head": merge,
            "merged": info["merged_at"][:10],
            "targets": [{"callable": t[0], "observe": t[1], "arg_kinds": t[2] if len(t) > 2 else ["str"]}
                        for t in targets],
            "known": known,
        })
        print(f"#{pr} {info['merged_at'][:10]} {parent[:10]}..{merge[:10]} {info['title'][:60]}")
    # Nemotron 3 Ultra was released 2026-06-04; PRs merged after it are less likely to be memorized.
    for it in items:
        it["after_ultra_release"] = it["merged"] >= "2026-06-04"
    out = {"repo": REPO, "items": items}
    Path("corpus").mkdir(exist_ok=True)
    Path("corpus/packaging.json").write_text(json.dumps(out, indent=2))
    print(f"wrote corpus/packaging.json ({len(items)} items)")


if __name__ == "__main__":
    main()
