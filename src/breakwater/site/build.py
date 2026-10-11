"""Build the static report site from committed artifacts. Standard library only.

    uv run breakwater site --backtest artifacts/backtest/packaging-v2 \
        --adjudication artifacts/adjudication/packaging-v2 --out site

Inputs are the published JSON (backtest results, adjudication). Output:

    site/index.html          headline numbers, arms vs known regressions, every PR
    site/pr/<id>.html        verdict, counterexample cards with labels and evidence, perf ladders
    site/assets/style.css
    site/data/*.json         the source JSON, so every number on the page can be checked

The site makes no network requests (no CDN, fonts or analytics), so it stays live on any static
host at no cost. Output is deterministic: rebuilding from the same inputs gives identical files.
Only Token Factory results may be published; other providers need `allow_dev`, which stamps every
page with a development banner.
"""

from __future__ import annotations

import html
import json
import math
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from breakwater.adjudicate import describe
from breakwater.adversary import Finding
from breakwater.display import card_text, short, sources

ASSETS = Path(__file__).parent / "assets"
REPO_URL = "https://github.com/adamwhitlock1/breakwater"
ARM_NAMES = {
    "hypothesis": ("Plain Hypothesis", "st.text() search, no LLM"),
    "mutations": ("Mutations of the PR's own test strings", "hostile edits of literals from the project's tests, no LLM"),
    "llm-plan": ("Nemotron plan only", "Ultra's example inputs, no search"),
    "breakwater": ("Breakwater", "Ultra plan + Lightning strategies + search + mutations"),
}
LABEL_ORDER = {"likely-bug": 0, "needs-human": 1, "intended": 2, None: 3}
LABEL_TEXT = {"likely-bug": "Likely bug", "needs-human": "Needs a human", "intended": "Intended", None: "Unlabelled"}


def esc(v: Any) -> str:
    return html.escape(str(v), quote=True)


# ---------------------------------------------------------------------------------------------------
# Model


@dataclass
class Card:
    finding: Finding
    verdict: dict | None
    known: list[str]
    arms: list[str] | None  # backtest arms whose classes include this one; None outside a backtest
    test: dict | None = None  # regress.RegressionTest.to_json(), if tests were generated

    @property
    def label(self) -> str | None:
        return self.verdict["label"] if self.verdict else None


def verdict_of(cards: list[Card]) -> str:
    """BLOCK on any likely bug; REVIEW if anything is unsettled or unlabelled; otherwise PASS."""
    labels = {c.label for c in cards}
    if "likely-bug" in labels:
        return "BLOCK"
    if "needs-human" in labels or None in labels and cards:
        return "REVIEW"
    return "PASS"


@dataclass
class TargetView:
    target: str
    image: str
    run_id: str
    usd: float
    adj_usd: float
    cards: list[Card]
    perf: dict | None
    perf_source: str | None = None  # another backtest the perf was taken from, if not this one


@dataclass
class ItemView:
    raw: dict
    targets: list[TargetView] = field(default_factory=list)

    @property
    def slug(self) -> str:
        return self.raw["id"].strip("#").replace("@", "-")

    @property
    def cards(self) -> list[Card]:
        return [c for t in self.targets for c in t.cards]

    @property
    def verdict(self) -> str:
        return verdict_of(self.cards)

    @property
    def caught(self) -> list[str]:
        return sorted({k for t in self.targets for c in t.cards for k in c.known})

    @property
    def usd(self) -> float:
        return sum(t.usd + t.adj_usd for t in self.targets)


def load(backtest: Path, adjudication: Path | None, perf_from: Path | None = None,
         tests: Path | None = None) -> tuple[dict, dict | None, list[ItemView]]:
    """`perf_from`: a backtest of the same corpus whose perf results fill targets that have none
    (the semantic planner doesn't affect perf, so a semantic-only re-run can reuse them)."""
    results = json.loads((backtest / "results.json").read_text())
    adj = json.loads((adjudication / "adjudication.json").read_text()) if adjudication else None
    reuse: dict[tuple[str, str], dict] = {}
    if perf_from:
        for it in json.loads((perf_from / "results.json").read_text())["items"]:
            for t in it["targets"]:
                if t.get("perf"):
                    reuse[(it["id"], t["target"])] = t["perf"]
    adj_items = {i["id"]: i for i in (adj or {}).get("items", [])}
    by_test: dict[tuple[str, str, str], dict] = {}  # (item, target, signature) -> test
    if tests:
        for p in tests.glob("*.json"):
            if p.name == "summary.json":
                continue
            r = json.loads(p.read_text())
            for t in r["targets"]:
                for x in t["tests"]:
                    by_test[(r["id"], t["target"], x["signature"])] = x
    items = []
    for raw in results["items"]:
        view = ItemView(raw)
        adj_targets = {t["target"]: t for t in adj_items.get(raw["id"], {}).get("targets", [])}
        for t in raw["targets"]:
            at = adj_targets.get(t["target"], {})
            verdicts = {v["signature"]: v for v in at.get("verdicts", [])}
            cards = []
            for f in t.get("findings", []):
                finding = Finding(**f)
                known = [k["id"] for k in raw["known"] if _matches(f["signature"], k["match"])]
                arms = [a for a, r in t["arms"].items() if f["signature"] in r.get("classes", [])]
                cards.append(Card(finding, verdicts.get(f["signature"]), known, arms,
                                  by_test.get((raw["id"], t["target"], f["signature"]))))
            cards.sort(key=lambda c: (LABEL_ORDER.get(c.label, 3), not c.known, c.finding.probe,
                                      len(json.dumps(c.finding.args)), c.finding.signature))
            perf, source = t.get("perf"), None
            if not perf and (raw["id"], t["target"]) in reuse:
                perf, source = reuse[(raw["id"], t["target"])], perf_from.name if perf_from else None
            view.targets.append(TargetView(t["target"], t["image"], t["run_id"], t.get("usd", 0.0),
                                           at.get("usd", 0.0), cards, perf, source))
        items.append(view)
    return results, adj, items


def _matches(sig: str, rule: dict) -> bool:
    from breakwater.backtest import matches

    return matches(sig, rule)


# ---------------------------------------------------------------------------------------------------
# Formatting helpers


_TICKS = re.compile(r"`([^`]+)`")


def inline(text: str) -> str:
    """Escape, then render `code` spans (PR titles use Markdown backticks)."""
    return _TICKS.sub(lambda m: f"<code>{m.group(1)}</code>", esc(text))


def money(usd: float) -> str:
    return f"${usd:.2f}" if usd >= 0.1 else f"${usd:.3f}"


PACKAGING = "https://github.com/pypa/packaging"


def gh_pr(pr: int | str, repo: str = PACKAGING) -> str:
    return f"{repo.removesuffix('.git')}/pull/{pr}"


def gh_commit(sha: str, repo: str = PACKAGING) -> str:
    return f"{repo.removesuffix('.git')}/commit/{sha}"


# ---------------------------------------------------------------------------------------------------
# Perf chart (inline SVG, log-log)

PALETTE = ("var(--c1)", "var(--c2)", "var(--c3)", "var(--c4)", "var(--c5)", "var(--c6)")


def ladder_chart(findings: list[dict]) -> str:
    series = [(f, [(p["input_chars"], p["ratio"]) for p in f.get("ladder", []) if p.get("ratio") and p.get("input_chars")])
              for f in findings]
    series = [(f, pts) for f, pts in series if len(pts) >= 2]
    if not series:
        return ""
    w, h, ml, mr, mt, mb = 640, 260, 52, 16, 14, 40
    xs = [x for _, pts in series for x, _ in pts]
    ys = [y for _, pts in series for _, y in pts] + [1.0]
    x0, x1 = math.log10(min(xs)), math.log10(max(xs))
    y0, y1 = math.log2(min(ys)) - 0.15, math.log2(max(ys)) + 0.15
    x1 = x1 if x1 > x0 else x0 + 1

    def px(x: float) -> float:
        return ml + (math.log10(x) - x0) / (x1 - x0) * (w - ml - mr)

    def py(y: float) -> float:
        return mt + (y1 - math.log2(y)) / (y1 - y0) * (h - mt - mb)

    out = [f'<svg class="chart" viewBox="0 0 {w} {h}" role="img" aria-label="Head/base instruction ratio by input size">']
    one = py(1.0)
    out.append(f'<rect x="{ml}" y="{mt}" width="{w - ml - mr}" height="{max(one - mt, 0):.1f}" class="slow-zone"/>')
    out.append(f'<text x="{w - mr - 6}" y="{mt + 14}" class="zone-label" text-anchor="end">head slower</text>')
    out.append(f'<text x="{w - mr - 6}" y="{h - mb - 6}" class="zone-label" text-anchor="end">head faster</text>')
    # Octave ticks (0.5x, 1x, 2x ...), or quarter-octaves when the range is narrow.
    step = 1.0 if y1 - y0 > 2.5 else 0.25
    k = math.ceil(y0 / step)
    while k * step <= y1:
        val = 2.0 ** (k * step)
        y = py(val)
        out.append(f'<line x1="{ml}" x2="{w - mr}" y1="{y:.1f}" y2="{y:.1f}" class="{"axis-one" if k == 0 else "grid"}"/>')
        out.append(f'<text x="{ml - 6}" y="{y + 4:.1f}" class="tick" text-anchor="end">{val:.2g}×</text>')
        k += 1
    for k in range(math.ceil(x0), math.floor(x1) + 1):
        x = px(10.0 ** k)
        out.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{mt}" y2="{h - mb}" class="grid"/>')
        out.append(f'<text x="{x:.1f}" y="{h - mb + 16}" class="tick" text-anchor="middle">{10 ** k:,}</text>')
    out.append(f'<text x="{(ml + w - mr) / 2}" y="{h - 4}" class="axis-title" text-anchor="middle">input size (characters)</text>')
    for i, (f, pts) in enumerate(series):
        color = PALETTE[i % len(PALETTE)]
        d = " ".join(f"{'M' if j == 0 else 'L'}{px(x):.1f},{py(y):.1f}" for j, (x, y) in enumerate(pts))
        dash = "" if i % 2 == 0 else ";stroke-dasharray:7 4"  # overlapping families stay distinguishable
        out.append(f'<path d="{d}" class="series" style="stroke:{color}{dash}"><title>{esc(f["family_id"])}</title></path>')
        for x, y in pts:
            out.append(f'<circle cx="{px(x):.1f}" cy="{py(y):.1f}" r="3" style="fill:{color}">'
                       f'<title>{esc(f["family_id"])}: {y:.2f}× at ~{x:,.0f} chars</title></circle>')
    out.append("</svg>")
    legend = "".join(f'<li><span class="swatch" style="background:{PALETTE[i % len(PALETTE)]}"></span>'
                     f'{esc(f["family_id"])}</li>' for i, (f, _) in enumerate(series))
    return "".join(out) + f'<ul class="legend">{legend}</ul>'


# ---------------------------------------------------------------------------------------------------
# Page shell


def page(title: str, body: str, *, depth: int, dev: str | None, description: str, site_nav: bool = True) -> str:
    """`site_nav=False` for pages that live outside the site (an audit's run directory)."""
    root = "../" * depth
    nav = (f'<a href="{root}index.html#prs">PRs</a><a href="{root}index.html#method">Method</a>' if site_nav else "")
    brand = f'{root}index.html' if site_nav else REPO_URL
    banner = (f'<div class="dev-banner">Development build (provider: {esc(dev)}). Not from Nebius Token Factory; '
              "do not cite these numbers.</div>") if dev else ""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}">
<link rel="stylesheet" href="{root}assets/style.css">
</head>
<body>
{banner}
<header class="top">
  <a class="brand" href="{brand}"><span class="mark" aria-hidden="true"></span>Breakwater</a>
  <nav>{nav}<a href="{REPO_URL}">Code</a></nav>
</header>
<main>
{body}
</main>
<footer>
  <p>Breakwater: a red team for performance PRs. Nemotron 3 Ultra and 3.5 Lightning on Nebius Token Factory plan
  and write attacks; deterministic probes and cachegrind instruction counts decide. Every number links to the
  JSON it came from{f' in <a href="{root}data/">data/</a>' if site_nav else " (report.json, events.jsonl)"}.</p>
</footer>
</body>
</html>
"""


def chip(label: str | None) -> str:
    cls = {"likely-bug": "bug", "needs-human": "human", "intended": "ok", None: "none"}.get(label, "none")
    return f'<span class="chip {cls}">{esc(LABEL_TEXT.get(label, label))}</span>'


def verdict_chip(v: str) -> str:
    return f'<span class="verdict {v.lower()}">{v}</span>'


# ---------------------------------------------------------------------------------------------------
# Index


def render_index(results: dict, adj: dict | None, items: list[ItemView], dev: str | None,
                 runs: list[dict] | None = None) -> str:
    s = results["summary"]
    arms = [a for a in results["arms"] if a in ARM_NAMES]
    nv, nc = s["known_verified"], s["known_candidate"]
    bw = s["caught_verified"].get("breakwater", 0)
    best_baseline = max((s["caught_verified"][a] for a in arms if a != "breakwater"), default=0)
    adj_s = (adj or {}).get("summary", {})
    usd_total = s["usd"] + adj_s.get("usd", 0.0)

    bars = ['<div class="bar-row"><div class="bar-label">The PRs\' own tests + benchmarks'
            '<small>these PRs merged green</small></div>'
            f'<div class="bar"><span style="width:0%"></span></div><div class="bar-value">0/{nv}</div></div>']
    for a in arms:
        name, sub = ARM_NAMES[a]
        n = s["caught_verified"][a]
        hero = " hero" if a == "breakwater" else ""
        bars.append(f'<div class="bar-row{hero}"><div class="bar-label">{esc(name)}<small>{esc(sub)}</small></div>'
                    f'<div class="bar"><span style="width:{100 * n / max(nv, 1):.1f}%"></span></div>'
                    f'<div class="bar-value">{n}/{nv}</div></div>')

    stats = [
        (f"{bw}/{nv}", "documented regressions caught before merge", f"best no-LLM baseline: {best_baseline}/{nv}"),
        (str(len(items)), "merged perf PRs audited", "pypa/packaging, the version library inside pip"),
    ]
    if adj_s:
        stats.append((f"{adj_s['issues_likely_bug']}/{len(adj_s['issues'])}", "found regressions labelled likely-bug",
                      "Ultra adjudication, evidence-checked"))
    stats.append((money(usd_total), "Nemotron cost of these results",
                  "Token Factory, backtest + adjudication; excludes dev and superseded runs"
                  + (" and reused perf" if any(t.perf_source for it in items for t in it.targets) else "")))
    stat_html = "".join(f'<div class="stat"><div class="stat-num">{esc(n)}</div><div class="stat-label">{esc(label)}'
                        f'</div><div class="stat-sub">{esc(sub)}</div></div>' for n, label, sub in stats)

    rows = []
    for it in items:
        r = it.raw
        counts = {k: sum(c.label == k for c in it.cards) for k in LABEL_ORDER}
        labels = " ".join(f'<span class="chip {cls} sm">{counts[k]}</span>' for k, cls in
                          (("likely-bug", "bug"), ("needs-human", "human"), ("intended", "ok"), (None, "none"))
                          if counts[k])
        perf = next((t.perf for t in it.targets if t.perf), None) or {}
        worst = f'{perf["worst_valid_ratio"]:.2f}×' if perf.get("worst_valid_ratio") else "–"
        caught = ", ".join(it.caught) or ("–" if not r["known"] else '<span class="muted">none</span>')
        late = ' <span class="dagger" title="merged after Nemotron 3 Ultra was released">†</span>' \
            if r["after_ultra_release"] else ""
        target = ", ".join(t.target.split(":")[1] for t in it.targets)
        rows.append(
            f'<tr><td><a href="pr/{it.slug}.html">{esc(r["id"])}</a>{late}</td>'
            f'<td class="title-cell">{inline(r["title"])}<small><code>{esc(target)}</code> · {esc(r["merged"])}</small></td>'
            f'<td>{verdict_chip(it.verdict) if it.cards else "<span class='muted nowrap'>no divergence</span>"}</td>'
            f'<td class="labels">{labels}</td><td>{caught if r["known"] else "–"}</td>'
            f'<td class="num">{worst}</td><td class="num">{money(it.usd)}</td></tr>')

    perf_sources = sorted({t.perf_source for it in items for t in it.targets if t.perf_source})
    corrections = results.get("corrections", [])
    notes = [
        "† merged after Nemotron 3 Ultra's release (2026-06-04), so it cannot be in the model's training data.",
        "Perf column: worst head/base instruction-count ratio over input families where most inputs are valid. "
        "Above 1× means the 'faster' change runs more instructions.",
    ]
    if perf_sources:
        notes.append("Perf columns come from backtest " + ", ".join(f"<code>{esc(x)}</code>" for x in perf_sources)
                     + " (same corpus and commits; the semantic arms were re-run later with a new planner, which perf "
                     "doesn't use). Costs shown exclude those perf measurements.")
    if corrections:
        notes.append(f"Probe corrections applied after the run ({len(corrections)} items re-scored deterministically, "
                     "no model calls): see <a href=\"data/backtest.json\">data/backtest.json</a> → corrections.")
    body = f"""
<section class="hero">
  <p class="eyebrow">Backtest · pypa/packaging · 2026 performance PRs</p>
  <h1>Faster isn't the same as <em>correct</em>.</h1>
  <p class="lede">Breakwater audits performance pull requests the way an attacker would. A Nemotron adversary reads
  the diff, guesses which assumptions the "faster" code makes, and hunts for inputs where the new version behaves
  differently or runs slower. Deterministic probes and instruction counts confirm everything it claims.</p>
  <div class="stats">{stat_html}</div>
</section>

<section>
  <h2>Documented regressions caught before merge</h2>
  <p class="section-lede">{nv} regressions in these PRs were later fixed upstream. Each approach got the same PRs,
  the same probes and no hint of which bugs exist.</p>
  <div class="bars">{"".join(bars)}</div>
  <p class="note">Candidates (linked to fixes but not reproduced by hand): Breakwater {s["caught_candidate"].get("breakwater", 0)}/{nc}.
  PRs with any behaviour divergence: {s["items_with_classes"].get("breakwater", 0)}/{s["items"]}.</p>
</section>

<section id="prs">
  <h2>Every PR</h2>
  <div class="table-wrap"><table class="items">
  <thead><tr><th>PR</th><th>Change</th><th>Verdict</th><th>Classes</th><th>Known issue caught</th>
  <th class="num">Perf worst</th><th class="num">Cost</th></tr></thead>
  <tbody>{"".join(rows)}</tbody></table></div>
  <ul class="notes">{"".join(f"<li>{n}</li>" for n in notes)}</ul>
</section>

{render_runs_list(runs or [])}
<section id="method" class="method">
  <h2>How a verdict is made</h2>
  <ol class="steps">
    <li><strong>Plan.</strong> Nemotron 3 Ultra reads the diff and names the assumptions the fast path makes, with
    example inputs that would break them.</li>
    <li><strong>Search.</strong> Nemotron 3.5 Lightning writes Hypothesis strategies; base and head run side by side
    in isolated sandboxes, and counterexamples shrink to their minimal form. Hostile mutations of the project's own test
    strings run too.</li>
    <li><strong>Probe.</strong> Deterministic checks compare outputs, exact exception types, equality / ordering /
    hashing, and whether objects pickled by the old version still load and compare.</li>
    <li><strong>Measure.</strong> Slowdown families are confirmed by cachegrind instruction counts across input
    sizes from 2 to 4,096: deterministic, so a ratio is a fact rather than noise.</li>
    <li><strong>Adjudicate.</strong> Ultra labels each divergence likely-bug, intended or needs-human. Three votes;
    a vote counts only if its evidence is quoted verbatim from the PR. The model can label, never delete.</li>
  </ol>
</section>
"""
    return page("Breakwater: backtest on pypa/packaging", body, depth=0, dev=dev,
                description="A Nemotron red team for performance PRs, backtested on pypa/packaging.")


def render_runs_list(runs: list[dict]) -> str:
    if not runs:
        return ""
    rows = []
    for r in runs:
        cards = run_cards(r)
        v = verdict_of(cards)
        rows.append(f'<tr><td><a href="runs/{esc(r["run_id"])}.html"><code>{esc(r["run_id"])}</code></a></td>'
                    f'<td class="title-cell">{inline(r.get("title") or r["target"])}<small><code>{esc(r["target"])}</code></small></td>'
                    f'<td>{verdict_chip(v) if cards else "<span class=\'muted nowrap\'>no divergence</span>"}</td>'
                    f'<td class="num">{len(cards)}</td><td class="num">{money(sum(r.get("usd_by_tier", {}).values()))}</td></tr>')
    return (f'<section id="runs"><h2>Audit runs</h2><p class="section-lede">Single audits from <code>breakwater audit</code>, '
            'as shown in the demo.</p><div class="table-wrap"><table class="items"><thead><tr><th>Run</th><th>Change</th>'
            f'<th>Verdict</th><th class="num">Classes</th><th class="num">Cost</th></tr></thead><tbody>{"".join(rows)}'
            '</tbody></table></div></section>')


# ---------------------------------------------------------------------------------------------------
# PR page


def render_card(card: Card, fn: str, repo: str, base: str, head: str, target: str) -> str:
    f, v = card.finding, card.verdict
    # The base/head boxes already state the facts; keep only what they can't show (how the two
    # exception types relate).
    facts = (v or {}).get("facts") or describe(f)
    rel = facts[facts.rfind("(") + 1:].rstrip(".)") if f.probe == "P2" and facts.endswith(".)") else ""
    text = card_text(f.probe, f.detail, f.args, f.base, f.head, fn)
    inputs = "".join(f'<div class="io"><span class="k">{esc(k)}</span><code>{esc(v_)}</code></div>'
                     for k, v_ in text["inputs"])
    known = "".join(f'<span class="known">known regression: {esc(k)}</span>' for k in card.known)
    adj = ""
    if v:
        votes = ", ".join(f"{n} {k}" for k, n in sorted(v["votes"].items(), key=lambda kv: -kv[1]))
        reason = f' <span class="muted">({esc(v["reason"])})</span>' if v.get("reason") else ""
        quotes = "".join(f"<blockquote><code>{esc(short(q, 220))}</code></blockquote>" for q in v["evidence"][:2])
        adj = (f'<div class="adj"><div class="adj-head">{chip(v["label"])}<span class="votes">votes: {esc(votes)}'
               f'</span>{reason}</div>'
               + (f'<p>{esc(v["rationale"])}</p>' if v.get("rationale") else "") + quotes + "</div>")
    else:
        adj = f'<div class="adj">{chip(None)}</div>'
    how = ", ".join(sources(f.found_by)) or "—"
    arms = ", ".join(ARM_NAMES[a][0] for a in card.arms or [] if a in ARM_NAMES and a != "breakwater")
    baseline = "" if card.arms is None else f" · also caught by: {esc(arms)}" if arms else " · no baseline found it"
    single = (len(f.args) == 1 and isinstance(f.args[0], list) and len(f.args[0]) == 1
              and isinstance(f.args[0][0], str) and len(f.args[0][0]) <= 200)
    repro = ""
    if single and f.probe != "P3":
        cmd = (f"uv run breakwater probe --repo {repo} --base {base[:12]} --head {head[:12]} "
               f"--target {target} --input {json.dumps(f.args[0][0], ensure_ascii=False)}")
        repro = f'<details><summary>Reproduce</summary><pre><code>{esc(cmd)}</code></pre></details>'
    return f"""<article class="card {"card-" + (card.label or "none")}">
  <header><span class="probe">{esc(f.probe)}</span><h3>{esc(text["title"])}</h3>{known}</header>
  {inputs}
  <div class="sides"><div class="side base" title="{esc(text["base_exc"])}"><span class="k">base</span>{esc(text["base"])}</div>
  <div class="side head" title="{esc(text["head_exc"])}"><span class="k">head</span>{esc(text["head"])}</div></div>
  {f'<p class="facts">{esc(rel[0].upper() + rel[1:])}.</p>' if rel else ""}
  {adj}
  <p class="found">Found by: {esc(how)}{baseline}</p>
  {render_test(card.test)}
  {repro}
</article>"""


def render_test(test: dict | None) -> str:
    if not test:
        return ""
    if test.get("skipped"):
        return f'<p class="found">No regression test: {esc(test["skipped"])}.</p>'
    if not test.get("verified"):
        return (f'<p class="found">Generated test not verified (base: {esc(test["base"])}, head: {esc(test["head"])}); '
                "not offered.</p>")
    return (f'<details class="test"><summary>Regression test <span class="chip ok sm">verified</span> '
            f'<span class="muted small">passes on base, {esc("fails" if test["head"] == "fail" else "errors")} on head'
            f'</span></summary><pre><code>{esc(test["source"])}</code></pre></details>')


def render_perf(t: TargetView) -> str:
    rep = (t.perf or {}).get("report")
    if not rep or not rep.get("findings"):
        return ""
    rows = []
    for f in rep["findings"]:
        ratios = [p["ratio"] for p in f.get("ladder", []) if p.get("ratio")]
        valid = f.get("valid_fraction")
        realistic = valid is not None and valid >= 0.5
        cls = {"slower": "bug", "complexity-regression": "bug", "faster": "ok"}.get(f["verdict"], "none")
        rows.append(
            f'<tr><td><code>{esc(f["family_id"])}</code></td><td class="title-cell">{esc(f["family"])}'
            f'<small>{esc(f.get("kind", "").replace("_", " "))} · {esc(f.get("origin", ""))}'
            f'{"" if realistic else " · mostly invalid inputs (error path)"}</small></td>'
            f'<td class="num">{f"{min(ratios):.2f}× – {max(ratios):.2f}×" if ratios else "–"}</td>'
            f'<td class="num">{(f.get("slope_base") or 0):.2f} → {(f.get("slope_head") or 0):.2f}</td>'
            f'<td><span class="chip {cls} sm">{esc(f["verdict"])}</span></td></tr>')
    summary = t.perf or {}
    worst = (f'<p class="section-lede">Worst family with mostly valid inputs: <strong>{summary["worst_valid_ratio"]:.2f}×</strong> '
             f'the instructions of base ({esc(summary.get("worst_family") or "")}).</p>') if summary.get("worst_valid_ratio") else \
        '<p class="section-lede">No realistic input family measured slower.</p>'
    source = (f'<p class="note">Measured in backtest <code>{esc(t.perf_source)}</code> (same commits, run '
              f'<code>{esc(rep.get("run_id", ""))}</code>, image <code>{esc(rep.get("image", ""))}</code>). '
              "The semantic results above are from a later run; perf doesn't use the semantic planner, so it "
              "was not re-measured.</p>") if t.perf_source else ""
    return f"""<section>
  <h2>Performance <small class="muted">· {esc(t.target.split(":")[1])}</small></h2>
  {worst}
  {source}
  <figure>{ladder_chart(rep["findings"])}<figcaption>Head/base cachegrind instructions per call, by input size
  (log-log). Each line is one input family Nemotron proposed; points above 1× are where the "faster" code does more work.</figcaption></figure>
  <div class="table-wrap"><table class="perf"><thead><tr><th>Family</th><th>Inputs</th><th class="num">Ratio range</th>
  <th class="num">Slope base → head</th><th>Verdict</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>
</section>"""


def render_item(it: ItemView, repo: str, dev: str | None) -> str:
    r = it.raw
    late = ('<p class="note">† Merged after Nemotron 3 Ultra was released (2026-06-04): '
            "the model cannot have seen this PR or its fixes.</p>") if r["after_ultra_release"] else ""
    known = ""
    if r["known"]:
        lis = []
        for k in r["known"]:
            fix = k.get("fixed_by")
            fix_s = f'<a href="{gh_pr(fix)}">#{fix}</a>' if isinstance(fix, int) else esc(fix)
            got = k["id"] in it.caught
            lis.append(f'<li class="{"hit" if got else "miss"}"><span class="tick-mark">{"✓" if got else "✗"}</span>'
                       f'<code>{esc(k["id"])}</code> · fixed by {fix_s} · {esc(k["status"])}'
                       f'{" · first found by Breakwater" if k.get("discovered_by") == "breakwater" else ""}</li>')
        known = f'<section><h2>Known regressions in this PR</h2><ul class="known-list">{"".join(lis)}</ul></section>'
    cards_html = []
    for t in it.targets:
        fn = t.target.split(":")[1].split("#")[0]
        cards_html += [render_card(c, fn, repo, r["base"], r["head"], t.target) for c in t.cards]
    counts = {k: sum(c.label == k for c in it.cards) for k in LABEL_ORDER}
    summary = ", ".join(f"{n} {LABEL_TEXT[k].lower()}" for k, n in counts.items() if n)
    verdict_text = {
        "BLOCK": "At least one behaviour change looks like an unintended regression.",
        "REVIEW": "Behaviour changed; the evidence does not settle whether it was intended.",
        "PASS": "No unintended behaviour change found." if it.cards else "No behaviour divergence found by any probe.",
    }[it.verdict]
    cards_section = (f'<section><h2>Counterexamples <small class="muted">· {len(it.cards)} classes: {esc(summary)}</small>'
                     f'</h2><div class="cards">{"".join(cards_html)}</div></section>') if it.cards else ""
    verified = [c.test for c in it.cards if c.test and c.test.get("verified")]
    tests_note = (f'<section><h2>Regression tests</h2><p class="section-lede">{len(verified)} of {len(it.cards)} classes '
                  "have a generated pytest that pins the old behaviour. Each passed on the base commit and failed on "
                  "the head commit in the sandbox before it was offered.</p>"
                  f'<p><a class="button" href="../tests/test_{esc(it.slug.replace("-", "_"))}.py" download>'
                  f'Download test_{esc(it.slug.replace("-", "_"))}.py</a></p></section>') if verified else ""
    receipt = "".join(
        f'<tr><td><code>{esc(t.target)}</code></td><td><code>{esc(t.image)}</code></td><td><code>{esc(t.run_id)}</code></td>'
        f'<td class="num">{money(t.usd)}</td><td class="num">{money(t.adj_usd)}</td></tr>' for t in it.targets)
    body = f"""
<p class="crumbs"><a href="../index.html">Backtest</a> / {esc(r["id"])}</p>
<section class="pr-head">
  <h1>{inline(r["title"])}</h1>
  <p class="meta"><a href="{gh_pr(r["pr"])}">pypa/packaging#{esc(r["pr"])}</a> · merged {esc(r["merged"])} ·
  base <a href="{gh_commit(r["base"])}"><code>{esc(r["base"][:10])}</code></a> →
  head <a href="{gh_commit(r["head"])}"><code>{esc(r["head"][:10])}</code></a></p>
  <div class="verdict-box {it.verdict.lower()}">{verdict_chip(it.verdict)}<p>{esc(verdict_text)}</p></div>
  {late}
</section>
{known}
{cards_section}
{tests_note}
{"".join(render_perf(t) for t in it.targets)}
<section>
  <h2>Receipt</h2>
  <div class="table-wrap"><table class="receipt"><thead><tr><th>Target</th><th>Image</th><th>Run</th>
  <th class="num">Audit</th><th class="num">Adjudication</th></tr></thead><tbody>{receipt}</tbody></table></div>
  <p class="note">Nemotron cost on Nebius Token Factory. Images are content-addressed (repo at each commit + harness),
  so every card above can be re-run from the image and seed 0. Raw data: <a href="../data/backtest/{esc(it.slug)}.json">audit</a>{
    f', <a href="../data/adjudication/{esc(it.slug)}.json">adjudication</a>' if any(t.adj_usd for t in it.targets) else ""}.</p>
</section>
"""
    return page(f"{r['id']}: {r['title']} · Breakwater", body, depth=1, dev=dev,
                description=f"Breakwater audit of pypa/packaging {r['id']}: {r['title']}")


# ---------------------------------------------------------------------------------------------------
# Audit-run page (`breakwater audit` output)

TIER_TEXT = {"reasoning": "Nemotron 3 Ultra", "proposer": "Nemotron 3 Super", "volume": "Nemotron 3.5 Lightning"}
VERDICT_TEXT = {
    "BLOCK": "At least one behaviour change looks like an unintended regression.",
    "REVIEW": "Behaviour changed; the evidence does not settle whether it was intended.",
    "PASS": "No unintended behaviour change found.",
}


def perf_summary(perf: dict | None) -> dict | None:
    """Same summary the backtest stores: worst ladder ratio over slower families with mostly valid inputs."""
    if not perf:
        return None
    slower = [f for f in perf.get("findings", []) if f.get("verdict") in ("slower", "complexity-regression")
              and (f.get("valid_fraction") or 0) >= 0.5]
    worst = max(slower, key=lambda f: max((p["ratio"] for p in f["ladder"] if p.get("ratio")), default=0),
                default=None)
    ratio = max((p["ratio"] for p in worst["ladder"] if p.get("ratio")), default=None) if worst else None
    return {"report": perf, "worst_valid_ratio": ratio, "worst_family": worst["family"] if worst else None}


def run_cards(report: dict) -> list[Card]:
    sem = report.get("semantic") or {}
    verdicts = {v["signature"]: v for v in (report.get("adjudication") or {}).get("verdicts", [])}
    tests = {t["signature"]: t for t in report.get("regression_tests", [])}
    cards = [Card(Finding(**f), verdicts.get(f["signature"]), [], None, tests.get(f["signature"]))
             for f in sem.get("findings", [])]
    cards.sort(key=lambda c: (LABEL_ORDER.get(c.label, 3), c.finding.probe, len(json.dumps(c.finding.args)),
                              c.finding.signature))
    return cards


def render_run(report: dict, *, depth: int, dev: str | None, home: str | None = None, site_nav: bool = True) -> str:
    repo, base, head, target = report["repo"], report["base"], report["head"], report["target"]
    sem = report.get("semantic") or {}
    cards = run_cards(report)
    verdict = verdict_of(cards)
    fn = target.split(":")[1].split("#")[0]
    image = sem.get("image") or (report.get("perf") or {}).get("image", "")
    title = report.get("title") or f"Audit of {target}"
    provider = report.get("provider", "tokenfactory")
    provider_name = "Nebius Token Factory" if provider == "tokenfactory" else provider
    crumbs = f'<p class="crumbs"><a href="{home}">Report</a> / run {esc(report["run_id"])}</p>' if home else ""

    plan = ""
    if sem.get("attacks"):
        lis = []
        for a in sem["attacks"]:
            ran = [j for j in sem.get("strategies", []) if j["attack"] == a["id"]]
            hits = sum(j.get("findings", 0) for j in ran)
            ex = ", ".join(show_args_short(x, fn) for x in a.get("example_args", [])[:3])
            lis.append(f'<li><div class="attack-head"><code>{esc(a["id"])}</code><strong>{esc(a["assumption"])}</strong></div>'
                       f'<p>{esc(a["why_it_breaks"])}</p>'
                       f'<p class="muted small">Inputs: {esc(a["input_family"])}' + (f' · e.g. <code class="bidi">{esc(ex)}</code>' if ex else "")
                       + f' · Lightning strategies: {sum(j["valid"] for j in ran)}/{len(ran)} valid, {hits} hits</p></li>')
        plan = (f'<section><h2>Ultra\'s plan <small class="muted">· {len(sem["attacks"])} attacks</small></h2>'
                '<p class="section-lede">Nemotron 3 Ultra read the diff and named the assumptions the change makes. '
                'Nothing here is trusted: each attack only counts through the counterexamples below.</p>'
                f'<ol class="attacks">{"".join(lis)}</ol></section>')
    counts = {k: sum(c.label == k for c in cards) for k in LABEL_ORDER}
    summary = ", ".join(f"{n} {LABEL_TEXT[k].lower()}" for k, n in counts.items() if n)
    cards_html = "".join(render_card(c, fn, repo, base, head, target) for c in cards)
    cards_section = (f'<section><h2>Counterexamples <small class="muted">· {len(cards)} classes: {esc(summary)}</small>'
                     f'</h2><div class="cards">{cards_html}</div></section>') if cards else ""
    n_verified = sum(bool(c.test and c.test.get("verified")) for c in cards)
    tests_href = f"../tests/run_{report['run_id']}.py" if site_nav else "test_regressions.py"
    tests_note = (f'<section><h2>Regression tests</h2><p class="section-lede">{n_verified} of {len(cards)} classes have '
                  "a generated pytest that passed on base and failed on head in the sandbox.</p>"
                  f'<p><a class="button" href="{tests_href}" download>Download test_regressions.py</a></p>'
                  "</section>") if n_verified else ""
    perf = perf_summary(report.get("perf"))
    perf_html = render_perf(TargetView(target, image, report["run_id"], 0.0, 0.0, [], perf)) if perf else ""
    usd = report.get("usd_by_tier", {})
    tiers = "".join(f'<tr><td>{esc(TIER_TEXT.get(t, t))}</td><td class="num">{money(u)}</td></tr>'
                    for t, u in sorted(usd.items(), key=lambda kv: -kv[1]))
    secs = {**{f"semantic {k}": v for k, v in (sem.get("seconds") or {}).items() if k != "total"},
            **{f"perf {k}": v for k, v in ((report.get("perf") or {}).get("seconds") or {}).items() if k != "total"}}
    times = " · ".join(f"{esc(k)} {v:.0f}s" for k, v in secs.items())
    verdict_box = (f'<div class="verdict-box {verdict.lower()}">{verdict_chip(verdict)}<p>{esc(VERDICT_TEXT[verdict] if cards else "No behaviour divergence found by any probe.")}'
                   f'{"" if report.get("adjudication") or not cards else " (not adjudicated)"}</p></div>')
    body = f"""
{crumbs}
<section class="pr-head">
  <p class="eyebrow">Breakwater audit · {esc(report.get("provider", "tokenfactory"))}</p>
  <h1>{inline(title)}</h1>
  <p class="meta"><a href="{esc(repo)}">{esc(repo.removeprefix("https://github.com/"))}</a> ·
  base <a href="{gh_commit(base, repo)}"><code>{esc(base[:10])}</code></a> →
  head <a href="{gh_commit(head, repo)}"><code>{esc(head[:10])}</code></a> · target <code>{esc(target)}</code></p>
  {verdict_box}
</section>
{plan}
{cards_section}
{tests_note}
{perf_html}
<section>
  <h2>Receipt</h2>
  <div class="receipt-grid">
  <div class="table-wrap"><table class="receipt"><thead><tr><th>Model ({esc(provider_name)})</th><th class="num">Cost</th></tr></thead>
  <tbody>{tiers}<tr><td><strong>Total</strong></td><td class="num"><strong>{money(sum(usd.values()))}</strong></td></tr></tbody></table></div>
  <div class="receipt-facts"><p><span class="k">run</span><code>{esc(report["run_id"])}</code></p>
  <p><span class="k">image</span><code>{esc(image)}</code></p>
  <p><span class="k">backend</span>{esc(sem.get("backend") or (report.get("perf") or {}).get("backend", ""))}</p>
  <p class="muted small">{times}</p></div>
  </div>
</section>
"""
    return page(f"{title} · Breakwater audit", body, depth=depth, dev=dev,
                description=f"Breakwater audit of {target}: {verdict}", site_nav=site_nav)


LIVE_BODY = """
<div id="dev" class="dev-banner" hidden></div>
<section class="live-head">
  <p class="eyebrow">Breakwater · live audit <span class="clock" id="clock">00:00</span></p>
  <h1 id="title">Waiting for the audit to start…</h1>
  <p class="meta" id="meta"></p>
  <ol class="steps-bar" id="steps"></ol>
  <p class="phase-text" id="phase-text">Connecting…</p>
  <div id="verdict" hidden></div>
</section>
<div class="live-grid">
  <section class="panel feed-panel"><h2>Attack feed</h2><ol class="feed" id="feed"></ol></section>
  <aside class="panel meters">
    <h2><span id="cost-title">Nemotron on Token Factory</span> <span class="meter-total" id="cost-total">$0.000</span></h2>
    <div id="thinking"></div>
    <div id="cost"></div>
    <h2 class="sb-title">Sandboxes</h2>
    <div class="gauge"><span id="sb-gauge"></span></div>
    <div class="sb-stats"><div><strong id="sb-now">0</strong><span>running now</span></div>
    <div><strong id="sb-runs">0</strong><span>runs</span></div><div><strong id="sb-cpu">0s</strong><span>CPU</span></div></div>
  </aside>
</div>
<section><h2>Ultra's plan</h2><ol class="attacks" id="attacks"></ol></section>
<section><h2>Lightning strategy <small class="muted">· first valid one, as written</small></h2>
<pre class="strategy" id="strategy">Waiting for Lightning…</pre></section>
<section><h2>Counterexamples <small class="muted">· <span id="card-count">0</span> classes</small></h2>
<div class="cards" id="cards"></div></section>
<section><h2>Perf families <small class="muted">· head/base instructions at the screening size</small></h2>
<ol class="families" id="families"></ol></section>
<script src="assets/live.js"></script>
"""


def write_live_page(run_dir: Path) -> Path:
    """live.html: polls events.jsonl in the same directory (serve the directory over HTTP)."""
    copy_assets(run_dir)
    out = run_dir / "live.html"
    out.write_text(page("Live audit · Breakwater", LIVE_BODY, depth=0, dev=None,
                        description="A Breakwater audit in progress", site_nav=False))
    return out


def show_args_short(args: Any, fn: str) -> str:
    from breakwater.display import show_args

    return show_args(args if isinstance(args, list) else [args], fn)


def write_run_page(run_dir: Path, *, allow_dev: bool = True) -> Path:
    """report.html next to an audit's report.json, with its own copy of the assets."""
    report = json.loads((run_dir / "report.json").read_text())
    provider = report.get("provider", "tokenfactory")
    if provider != "tokenfactory" and not allow_dev:
        raise ValueError(f"run {report['run_id']} used {provider}; only Token Factory results may be published")
    copy_assets(run_dir)
    out = run_dir / "report.html"
    out.write_text(render_run(report, depth=0, dev=None if provider == "tokenfactory" else provider, site_nav=False))
    return out


def copy_assets(root: Path) -> None:
    (root / "assets").mkdir(parents=True, exist_ok=True)
    for f in sorted(ASSETS.iterdir()):
        shutil.copy(f, root / "assets" / f.name)


# ---------------------------------------------------------------------------------------------------
# Build


def build(backtest: Path, adjudication: Path | None, out: Path, *, allow_dev: bool = False,
          runs: list[Path] | None = None, perf_from: Path | None = None, tests: Path | None = None) -> list[Path]:
    results, adj, items = load(backtest, adjudication, perf_from, tests)
    run_reports = [json.loads((r / "report.json").read_text()) for r in runs or []]
    providers = {results.get("summary", {}).get("provider", results.get("provider", "tokenfactory"))}
    if adj:
        providers.add(adj.get("provider", "tokenfactory"))
    providers |= {r.get("provider", "tokenfactory") for r in run_reports}
    if perf_from:
        pf = json.loads((perf_from / "results.json").read_text())
        providers.add(pf.get("summary", {}).get("provider", pf.get("provider", "tokenfactory")))
        if pf.get("corpus") != results.get("corpus"):
            raise ValueError(f"perf_from {perf_from} is a different corpus ({pf.get('corpus')})")
    dev_providers = sorted(p for p in providers if p != "tokenfactory")
    if dev_providers and not allow_dev:
        raise ValueError(f"inputs come from {dev_providers}; only Token Factory results may be published "
                         "(pass allow_dev to build a development site with a banner)")
    dev = ", ".join(dev_providers) or None
    repo = json.loads(Path(results["corpus"]).read_text())["repo"] if Path(results["corpus"]).exists() \
        else "https://github.com/pypa/packaging"

    if out.exists():
        shutil.rmtree(out)
    (out / "pr").mkdir(parents=True)
    copy_assets(out)
    written = [out / "index.html"]
    (out / "index.html").write_text(render_index(results, adj, items, dev, run_reports))
    if run_reports:
        (out / "runs").mkdir()
        (out / "data" / "runs").mkdir(parents=True)
    for r, src in zip(run_reports, runs or [], strict=True):
        p = out / "runs" / f"{r['run_id']}.html"
        p.write_text(render_run(r, depth=1, dev=dev, home="../index.html"))
        shutil.copy(src / "report.json", out / "data" / "runs" / f"{r['run_id']}.json")
        if (src / "test_regressions.py").exists():
            (out / "tests").mkdir(exist_ok=True)
            shutil.copy(src / "test_regressions.py", out / "tests" / f"run_{r['run_id']}.py")
        written.append(p)
    for it in items:
        p = out / "pr" / f"{it.slug}.html"
        p.write_text(render_item(it, repo, dev))
        written.append(p)
    data = out / "data"
    (data / "backtest").mkdir(parents=True, exist_ok=True)
    shutil.copy(backtest / "results.json", data / "backtest.json")
    for f in sorted(backtest.glob("*.json")):
        if f.name != "results.json":
            shutil.copy(f, data / "backtest" / f.name)
    if perf_from:
        shutil.copy(perf_from / "results.json", data / f"perf-{perf_from.name}.json")
    if tests:
        (out / "tests").mkdir(exist_ok=True)
        for f in sorted(tests.glob("test_*.py")):
            shutil.copy(f, out / "tests" / f.name)
        (data / "tests").mkdir()
        for f in sorted(tests.glob("*.json")):
            shutil.copy(f, data / "tests" / f.name)
    if adjudication:
        (data / "adjudication").mkdir()
        shutil.copy(adjudication / "adjudication.json", data / "adjudication.json")
        for f in sorted(adjudication.glob("*.json")):
            if f.name != "adjudication.json":
                shutil.copy(f, data / "adjudication" / f.name)
    listing = sorted(str(p.relative_to(data)) for p in data.rglob("*.json"))
    (data / "index.html").write_text(page("Data · Breakwater", '<section><h1>Source data</h1><ul class="files">' + "".join(
        f'<li><a href="{esc(n)}">{esc(n)}</a></li>' for n in listing) + "</ul></section>", depth=1, dev=dev,
        description="Raw JSON behind the Breakwater report"))
    (out / ".nojekyll").write_text("")
    return written
