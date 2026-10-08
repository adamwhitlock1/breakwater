# Roadmap: Oct 8 → Oct 30, 2026

**Deadline: Fri Oct 30, 10:00 PT.** Plan to submit on **Thu Oct 29**. Judging runs Dec 1–15, and the demo must stay live and free until then.

**Scope in one line:** Breakwater *audits* "faster" PRs. Performance findings are the hero; semantic divergences come second. Harden mode (GEPA optimizing the code) is a stretch goal. Reasons are in [decisions.md](decisions.md).

## Milestones and gates

| Date | Milestone | Gate: must be true to continue as planned | If it fails |
|---|---|---|---|
| Thu Oct 8 | Day 1 | [Checklist](day1-checklist.md) sections A–B done; C done once a key exists | — |
| **Sun Oct 11** | **G0: first automatic finding** ✅ met Oct 8: 3/3 cold runs found a #1082 bug, ~$0.027 each | Day-1 C done (D too if access arrived). `breakwater audit` prototype on #1082's intermediate commit finds ≥1 known class with no hint about which bug exists | Debug the adversary prompts and probes before building anything else |
| **Wed Oct 14** | **G1: hero works** | ≥2 of 3 known #1082-era classes found automatically, **and** ≥1 performance reversal family (e.g. non-simple versions) found by the adversary and confirmed by Ir | Lean on deterministic probes plus Hypothesis and make the Nemotron delta a measured ablation; or change the hero PR |
| **Wed Oct 21** | **G2: evidence + product v1** | Backtest done over packaging 2026 perf PRs + ≥8 Codeflash PRs, with baselines; report page v1; GitHub Action posts a check | Shrink the Codeflash set; keep packaging |
| **Sat Oct 24 23:59 PT** | **Feature freeze** | — | Cut from the bottom of the cut list |
| Sun Oct 25 – Tue Oct 27 | Rerun from clean images; fill numbers; README; record video | — | — |
| Wed Oct 28 | Upload video (allow 2–3 h); deploy static demo; clean-browser test | — | — |
| Thu Oct 29 | **Submit on Devpost** | — | Fri morning is buffer only |

Also watch the GTC Berlin keynote (Oct 21) for Sandboxes or Nemotron news. Mention anything relevant; don't chase it.

## Workstreams

The project starts as one person. Critical path order: **WS1 → WS2 → WS3**. WS4 is what newcomers should pick up first.

### WS1: Harness and measurement (critical path)
- [x] Differential runner: base and candidate in separate processes, identical serialized inputs, results compared outside both (`probes.py`, `harness/worker.py`).
- [x] Probes P1 output parity, P2 exception-type parity, P3 dunder parity, P4 cross-version pickle (with warmed state); P4down opt-in. All three packaging ground-truth regressions are caught (Docker tests).
- [ ] P7 hash-seed determinism.
- [ ] Ir measurement: whole-process Ir minus a null run, size ladders and log-log slope per family.
- [ ] Two clocks (P8): in-process timer total vs out-of-process CPU (Sandbox resources or Docker rusage); flag large residuals.
- [ ] P5 input non-mutation, P6 peak RSS.
- [x] Image builder (Docker): one image per base/head pair, a venv per side, content-addressed tag (`images.py`).
- [ ] Image builder (ConTree): same layout as a kept, tagged Sandboxes image.
- [ ] Finalist timing on a Serverless Job (week 2): fresh process per sample, ABAB interleaving, ≥30 pairs, frozen GC, bootstrap 95% CI, A/A floor.

### WS2: Nemotron adversary (critical path)
- [x] Ultra planner: change-centred prompt (routing condition first), `medium_effort`, 2 plans per call, JSON schema. Live: 3/3 cold runs on #1082 found a known class.
- [ ] Planner still proposes "no divergence expected" hypotheses (wasted slots) and missed the oversized-int class in 3 runs; nudge toward builtin limits (`sys.int_info`, `int()` digit cap).
- [x] Lightning strategy writer: N strategies per attack, AST hygiene check, then a sandboxed `find()` search against persistent base/head workers (`harness/diffrun.py`).
- [x] Shrink (Hypothesis), dedupe by signature keeping the smallest input, credit every strategy that hit a class.
- [ ] Finer classes: "1. 0" and Arabic-Indic digits currently share one P2 class (exc → ok); split by input character class or by adjudication.
- [ ] Perf attacks: `hypothesis.target()` on a cheap CPU-time ratio, confirmed by Ir.
- [ ] Ultra adjudication: likely-bug / intended-change / needs-human, may abstain; never overrides deterministic facts.
- [ ] Tavily recon (spec + bug-tracker facts) behind an ablation flag. Keep it only if the ablation shows it adds classes.
- [ ] Each finding becomes a ready-to-commit pytest regression test.

### WS3: Corpus and experiments
- [ ] Packaging 2026 perf PR list with refs (start from #1082, #1108, #1116; ~14 total). Post-cutoff controls: #1371, #1429.
- [ ] Codeflash sample: 8–10 pure-Python PRs from `artifacts/corpus/codeflash_prs.json`.
- [ ] Sealed real-version corpus (~1M PyPI versions/specifiers); no agent ever sees it.
- [ ] Baselines: PR's own tests + benchmarks; `hypothesis write --equivalent` ghostwriter; Ultra-reads-the-diff with no execution; ablations (Lightning-only, Ultra-only, no Tavily).
- [ ] Headline table: known regressions caught, extra divergences (labelled), speedup reversals per family, $ per divergence class by tier.

### WS4: Product, story and submission
- [ ] `breakwater audit <repo> --base <ref> --head <ref> --target <symbol>` → JSON + Markdown report.
- [ ] Static web report (verdict, per-family table with CIs, counterexample cards, cost receipt, image UUIDs). Must stay live through Dec 15 at ~$0.
- [ ] Judge box: in-browser Pyodide "try your own version string" against base / PR / merged.
- [ ] GitHub Action that runs the CLI and posts a check + comment.
- [ ] README "For judges" table ([judging-map.md](judging-map.md)), limitations, the real bill.
- [ ] Video per [demo-script.md](demo-script.md). Say "Nebius Token Factory", "Sandboxes" and the Nemotron model names aloud.
- [ ] Feedback write-up from [feedback-log.md](feedback-log.md). It is required, and 10 × $100 prizes reward it.

### WS5: Stretch (only after G2, in this order)
1. Kill-and-resume of the campaign runner as a Serverless Job, on camera.
2. NeMo Gym resources server: Breakwater's frozen probes + archive as a reward that resists timing hacks; score recorded naive vs hardened candidates.
3. Harden mode: GEPA 0.1.4 (or a ~150-line reflective loop) proposing candidates that must survive the adversary.
4. Live "Attack it" endpoint (Serverless Endpoint, Dec 1–15, rate-limited, dollar-capped).

## Cut list (drop from the top)
1. Live "Attack it" endpoint (keep replays + Pyodide box)
2. Harden mode
3. NeMo Gym export
4. Tavily recon (if the ablation shows no value)
5. GitHub Action (keep CLI-generated PR comment)
6. Codeflash breadth (packaging only)
7. Complexity-slope charts (keep fixed-size ratios)

**Never cut:** the white-box adversary, probes P1–P4, Ir + CI measurement with an A/A floor, the packaging backtest with baselines, image provenance, the report page, the real bill, the video.

## For teammates joining
1. Read the README, this file and [spec.md](spec.md). Skim [decisions.md](decisions.md) and [risks.md](risks.md).
2. `uv sync --extra sandboxes`, `cp .env.example .env`, build the harness image, `uv run breakwater doctor`.
3. Claim a workstream item by putting your name on it here. WS3 and WS4 can start without waiting on the adversary.
4. Log every tool friction you hit in [feedback-log.md](feedback-log.md) as it happens.
