"""Build corpus/codeflash.json: merged Codeflash-bot speedup PRs that Breakwater can run.

    uv run python scripts/backtest/build_codeflash_corpus.py

Source: artifacts/corpus/codeflash_prs.json (scripts/day1/codeflash_corpus.sh), 178 merged PRs in
42 repos. Selected by hand for what the harness can execute on Python 3.12 without heavy native
dependencies (no torch, klayout, cloud SDKs) and with a target whose arguments are JSON values.
Repos that are directories of scripts rather than packages use install mode "src" (see
images.src_req). There are no known regressions: this corpus measures how many merged AI speedups
change behaviour or don't deliver, not recall.

Base = first parent of the merge commit (the branch the PR merged into); head = the merge commit.
Dependencies resolve as of the day after the merge (uv --exclude-newer), so an unpinned dependency
can't drift past what the PR ran against (pyhs3 broke on a 2026-10 pytensor otherwise).
Commits and titles come from the GitHub API, so the file is reproducible.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

ULTRA_RELEASE = "2026-06-04"

# (repo, PR, target, observe, arg kinds, install)
SELECTED = [
    ("mangiucugna/json_repair", 113, "json_repair.object_comparer:ObjectComparer.is_same_object", ["value"],
     ["json", "json"], None),
    ("IanHollow/rendercv", 17, "rendercv.themes.options:validate_typst_dimension", ["value"], ["str"], None),
    ("IanHollow/rendercv", 18, "rendercv.data.models.computers:get_date_object", ["str", "repr"], ["str"], None),
    ("IanHollow/rendercv", 19, "rendercv.data.models.computers:get_date_object", ["str", "repr"], ["str"], None),
    ("scipp-atlas/pyhs3", 154, "pyhs3.generic_parse:parse_expression", ["str", "repr"], ["str"], None),
    ("hoopinwhoopin/Math-Interpreter", 1, "lexer:Lexer#generate_tokens", ["value"], ["str"],
     {"mode": "src", "subdir": "", "deps": []}),
    ("fabriziosalmi/patterns", 9, "json2haproxy:validate_regex", ["value"], ["str"],
     {"mode": "src", "subdir": "", "deps": []}),
    ("fabriziosalmi/patterns", 12, "json2nginx:sanitize_pattern", ["value"], ["str"],
     {"mode": "src", "subdir": "", "deps": []}),
    ("fabriziosalmi/caddy-feeds", 4, "ip:is_excluded", ["value"], ["str"],
     {"mode": "src", "subdir": "scripts", "deps": ["requests", "pyyaml", "aiohttp", "prometheus-client"]}),
    ("hoopinwhoopin/micropie", 3, "MicroPie:App()#_parse_cookies", ["value"], ["str"], None),
]


def gh(path: str) -> dict:
    return json.loads(subprocess.run(["gh", "api", path], capture_output=True, text=True, check=True).stdout)


def main() -> int:
    items = []
    for repo, n, target, observe, kinds, install in SELECTED:
        pr = gh(f"repos/{repo}/pulls/{n}")
        merge = pr["merge_commit_sha"]
        base = gh(f"repos/{repo}/commits/{merge}")["parents"][0]["sha"]
        merged = pr["merged_at"][:10]
        item = {"id": f"{repo.split('/')[1]}#{n}", "pr": n, "repo": f"https://github.com/{repo}",
                "title": pr["title"], "base": base, "head": merge, "merged": merged,
                "after_ultra_release": merged >= ULTRA_RELEASE, "known": [],
                "targets": [{"callable": target, "observe": observe, "arg_kinds": kinds}]}
        # Resolve dependencies as they were the day after the merge (uv --exclude-newer).
        day_after = (date.fromisoformat(merged) + timedelta(days=1)).isoformat()
        item["install"] = {**(install or {}), "exclude_newer": day_after}
        items.append(item)
        print(f"{item['id']:28s} {merged} {base[:10]}..{merge[:10]} {target}")
    out = Path("corpus/codeflash.json")
    out.write_text(json.dumps({"name": "codeflash", "items": items}, indent=1, ensure_ascii=False) + "\n")
    print(f"wrote {out} ({len(items)} items)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
