"""The pull-request comment: an audit report (report.json) as Markdown, posted or updated in place.

One comment per target per PR, found again by a hidden marker, so every push edits the same comment
instead of adding a new one. Posting goes through the `gh` CLI (preinstalled on GitHub runners; the
token comes from GH_TOKEN), so this module needs no HTTP client of its own.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from typing import Any

from breakwater.classes import group_classes
from breakwater.display import card_text
from breakwater.verdict import of_report

ICON = {"BLOCK": "🛑", "REVIEW": "⚠️", "PASS": "✅"}
LABEL = {"likely-bug": "likely bug", "needs-human": "needs a human", "intended": "intended", None: "unlabelled"}
MAX_ROWS = 12
MAX_CELL = 90


def marker(target: str) -> str:
    return f"<!-- breakwater:{target} -->"


def _cell(text: str) -> str:
    text = text if len(text) <= MAX_CELL else text[: MAX_CELL - 1] + "…"
    return text.replace("|", "\\|").replace("\n", " ")


def ran_in(report: dict) -> str:
    """Where the untrusted code ran, and the image that reproduces every number."""
    from breakwater.site.build import backend_of

    sandbox = report.get("sandbox") or {}
    image = sandbox.get("image") or (report.get("semantic") or {}).get("image") \
        or (report.get("perf") or {}).get("image", "")
    backend = backend_of(image, sandbox.get("backend") or (report.get("semantic") or {}).get("backend"))
    where = "Token Factory Sandboxes microVMs" if backend == "contree" else "local Docker"
    runs = f"{sandbox['runs']} runs in " if sandbox.get("runs") else ""
    return f"Untrusted code: {runs}{where} · image `{image}`"


def render(report: dict, *, artifact_url: str | None = None, run_url: str | None = None) -> str:
    v = report.get("verdict") or of_report(report)
    target = report["target"]
    fn = target.split(":")[1].split("#")[0]
    sem = report.get("semantic") or {}
    findings = {f["signature"]: f for f in sem.get("findings", [])}
    verdicts = {x["signature"]: x for x in (report.get("adjudication") or {}).get("verdicts", [])}
    tests = {t["signature"]: t for t in report.get("regression_tests", [])}
    usd = sum((report.get("usd_by_tier") or {}).values())
    provider = report.get("provider", "tokenfactory")
    where = "Nemotron on Nebius Token Factory" if provider == "tokenfactory" else f"Nemotron via {provider} (development run)"
    lines = [
        marker(target),
        f"## {ICON[v['verdict']]} Breakwater: {v['verdict']}",
        f"`{target}` · base `{report['base'][:10]}` → head `{report['head'][:10]}` · {where} · ${usd:.2f}  ",
        ran_in(report),
        "",
    ]
    lines += [f"> {r}" for r in v["reasons"]] or ["> No behaviour divergence and no slowdown on valid inputs found."]
    lines.append("")

    if findings:
        labels = {s: (verdicts.get(s) or {}).get("label") for s in findings}
        sizes = {s: len(json.dumps(f["args"])) for s, f in findings.items()}
        groups = group_classes(list(findings), labels, sizes)
        rank = {"likely-bug": 0, "needs-human": 1, None: 2, "intended": 3}
        groups.sort(key=lambda g: rank.get(g.label, 2))
        lines += [f"### Behaviour: {len(findings)} divergence class(es) in {len(groups)} group(s)", "",
                  "| | Input | Base | Head | Label | Test |", "|---|---|---|---|---|---|"]
        for g in groups[:MAX_ROWS]:
            f = findings[g.primary]
            text = card_text(f["probe"], f["detail"], f["args"], f["base"], f["head"], fn)
            t = tests.get(g.primary) or {}
            test = "✅ verified" if t.get("verified") else "—"
            more = f" (+{len(g.duplicates)} similar)" if g.duplicates else ""
            lines.append(f"| {f['probe']} | `{_cell(' vs '.join(x for _, x in text['inputs']))}`{more} | "
                         f"{_cell(text['base'])} | {_cell(text['head'])} | {LABEL.get(g.label, g.label)} | {test} |")
        if len(groups) > MAX_ROWS:
            lines.append(f"\n…and {len(groups) - MAX_ROWS} more group(s) in the full report.")
        lines.append("")

    perf = report.get("perf")
    if perf:
        from breakwater.perf import judged, summarize

        s = summarize(perf)
        slower = [f for f in perf.get("findings", []) if f.get("verdict") in ("slower", "complexity-regression")
                  and (f.get("valid_fraction") or 0) >= 0.5 and judged(f)]
        lines.append("### Performance (cachegrind instructions per call, head ÷ base)")
        lines.append("")
        if s.get("speedup_ratio_small"):
            lines.append(f"- Claimed fast path: **{s['speedup_ratio_small']:.2f}×** (below 1× is faster).")
        for f in sorted(slower, key=lambda f: -max(judged(f)))[:3]:
            lines.append(f"- **{max(judged(f)):.2f}×** on _{_cell(f['family'])}_ ({f['verdict']}).")
        if not slower:
            lines.append("- No valid input family measured slower.")
        lines.append("")

    verified = [t for t in tests.values() if t.get("verified")]
    if verified:
        where_tests = f" ([download]({artifact_url}))" if artifact_url else ""
        lines += [f"### Regression tests: {len(verified)} ready to commit{where_tests}", "",
                  "Each pins the old behaviour, and passed on base and failed on head in the sandbox.", "",
                  "<details><summary>First test</summary>", "", "```python", verified[0]["source"].rstrip(), "```",
                  "", "</details>", ""]

    links = [f"[full report]({artifact_url})" if artifact_url else "", f"[run]({run_url})" if run_url else ""]
    links = " · ".join(x for x in links if x)
    attacks = len(sem.get("attacks", []))
    lines.append(f"<sub>Breakwater: Nemotron 3 Ultra planned {attacks} attack(s); probes, Hypothesis search and "
                 f"cachegrind decided. Run `{report['run_id']}`{' · ' + links if links else ''}.</sub>")
    return "\n".join(lines) + "\n"


Runner = Callable[[list[str], str | None], str]


def _gh(args: list[str], stdin: str | None = None) -> str:
    return subprocess.run(["gh", *args], input=stdin, capture_output=True, text=True, check=True).stdout


def post(body: str, *, repo: str, pr: int, target: str, gh: Runner = _gh) -> str:
    """Create the comment, or edit the one carrying this target's marker. Returns its URL."""
    mark = marker(target)
    existing = json.loads(gh(["api", f"repos/{repo}/issues/{pr}/comments", "--paginate", "--slurp"], None) or "[]")
    comments: list[dict[str, Any]] = [c for page in existing for c in page] if existing and isinstance(existing[0], list) \
        else existing
    mine = next((c for c in comments if mark in (c.get("body") or "")), None)
    payload = json.dumps({"body": body})
    if mine:
        out = gh(["api", "--method", "PATCH", f"repos/{repo}/issues/comments/{mine['id']}", "--input", "-"], payload)
    else:
        out = gh(["api", "--method", "POST", f"repos/{repo}/issues/{pr}/comments", "--input", "-"], payload)
    return json.loads(out).get("html_url", "")
