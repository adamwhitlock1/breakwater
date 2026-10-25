# Final sprint: audit of Oct 17 and the plan to Oct 30

This is the forward plan from Oct 17. [roadmap.md](roadmap.md) stays the ledger of what was built and when; this file says what to add and refine in the 12 days left, in priority order, with gates and a budget. Decisions here follow [decisions.md](decisions.md); nothing below reopens a settled one.

**Deadline: Fri Oct 30, 10:00 PT. Submit Thu Oct 29. Feature freeze moved from Sat Oct 24 to Mon Oct 26 23:59 PT (decided Oct 25).** Judging is Dec 1–15; the demo URL must stay up and free until then.

## 1. Where the project stands (audit)

### Built and verified (all on Token Factory unless stated)

| Piece | Evidence |
|---|---|
| Deterministic differential probes P1–P4 with controls (fresh-object and round-trip) | `probes.py`, `harness/`, 71 tests pass, `ruff` clean |
| Nemotron adversary: Ultra plans (v3, medium effort, 3 samples), Lightning writes strategies, sandboxed Hypothesis search, hostile mutations, relations pass | `adversary.py`, `mutate.py`; plan-only eval 0/15 → 7/15 productive attacks |
| Perf attacks: Ultra families + Super variants + Lightning search, confirmed by cachegrind Ir with a three-point linearity check and per-size validity | `perf.py`; 0.0000% Ir A/A on day 1 |
| Ultra adjudication with deterministic guards (strict majority, verbatim-quote check, pinned schema) | `adjudicate.py`; 8/10 known issues labelled likely-bug |
| Verified regression tests, one per class, kept only if pass-on-base and fail-on-head | `regress.py`; 30/30 packaging, 6/6 Codeflash |
| Packaging backtest: 29 PRs, 4 arms; 9/9 verified regressions caught (best no-LLM baseline 7/9) | `artifacts/backtest/packaging-v3`, `docs/backtest.md` |
| Codeflash corpus: 10 merged AI speedups in 7 repos; 4/10 change behaviour (3 likely-bug, 1 intended), 1/10 is a 363× complexity regression; no-LLM baselines found 0 | `artifacts/backtest/codeflash-v2` (Sandboxes, Oct 24); `codeflash-v1` is the Docker run (3/10, 393×) |
| Static report site (overview, PR pages with cards, ladders, receipts), Codeflash sub-site, judge box (Pyodide), live page + replay, run pages | `src/breakwater/site/`; 43 pages, no network requests except the opt-in Pyodide load |
| Cost ledger by tier and provider; dev provider (OpenRouter) kept out of published numbers | `ledger.py`, `models.py`; $13.06 of Token Factory credit spent through Oct 12 |
| GitHub Action: one PR comment updated in place, job summary, artifact, fail-on | **uncommitted in the main checkout** (`action.yml`, `comment.py`, `verdict.py`, `docs/github-action.md`, tests). Not yet run on GitHub |

### Claimed but not built (judges will read these)

- **README line 1 says the adversary runs "in Nebius Token Factory Sandboxes".** Every published artifact records `backend: docker`. Until today Sandboxes was untested. The gap between the first sentence of the README and the artifacts is the single most damaging thing a careful judge could find.
- README says **"Two clocks catch timing hacks."** P8 does not exist. The data for it does (in-process `t_ns` from the worker, out-of-process `user_cpu_s` from both backends), but nothing compares them.
- README "NVIDIA and Nebius usage" lists **Serverless Jobs** (finalist timing) and **NeMo Gym**. Neither is used.
- README status is "pre-alpha, day 1" and "How it works (planned)". `spec.md` still defines `FASTER / INCONCLUSIVE / BLOCK` with wall-clock CIs; the product ships `BLOCK / REVIEW / PASS` on Ir (decisions.md 2026-10-12). `judging-map.md` promises "CI-confirmed finalists on a Serverless Job".
- Tavily is a key in `.env.example` and nothing else.
- P5–P8, the sealed PyPI corpus, the Lightning-vs-Ultra ablation and the headline table are open roadmap items.

### Sandboxes check (Oct 17, `artifacts/day1/contree.json`, free during beta)

`scripts/day1/check_contree.py` passed end to end on the first attempt with contree-sdk 0.3.6:

| Check | Result |
|---|---|
| Auth | OK (no 403) |
| Kept image: `python:3.12-slim` + valgrind + packaging 26.3 | built in 20.2 s, image UUID returned |
| Branch fidelity | two branches from one snapshot: identical files; 941 / 952 ms per run |
| Per-run resources | `user_cpu_s`, `sys_cpu_s`, `max_rss_kb`, `involuntary_switches` and a per-run `cost_usd` (~$0.0005) all populated (via `_raw`) |
| A/A user CPU inside the microVM | CV 10.4% over 10 runs: wall/CPU time is noisy there too, so Ir stays the search metric |
| cachegrind inside the microVM | works: 428,703,675 Ir in 3.8 s |

Documented limits that matter for us: 50 concurrent operations during beta; recorded stdout/stderr default 1 MiB per stream (max 10 MiB); images retained 180 days; resource fields are "diagnostics only" until units are confirmed with the team. The docs are at docs.tokenfactory.nebius.com/sandboxes (the "Prepare inputs, then verify with networking disabled" cookbook is our exact pattern).

### Code-level notes from the audit

- `images.py` builds pair images with Docker only; the ConTree builder is the missing piece for WS-A below. `PairImage.ref` already carries whatever the backend returns, so reports need no schema change to cite a Sandboxes image UUID.
- `backends/contree.py` reads resources from `result._raw` (private; logged in the feedback log). It has no retry, no concurrency bound and no handling for the 1 MiB stream cap. The perf `make` ladder returns up to 2 MB of JSON on stdout, which will exceed the default cap.
- `perf.py`: a ladder that stops at n=4096 because inputs exceed 2 MB is shown as `error:` on the report. It is a stop, not an error; the wording should say so.
- `adversary.py` `_BANNED_NAMES` is hygiene, not the security boundary (documented). With Sandboxes as the backend the boundary becomes a microVM, which is the right story for the Coding track.
- The packaging backtest v3 reused perf from v2 (`--perf-from`), labelled on the site. Fine, but a Sandboxes re-run of the perf-bearing items would remove the label.
- `harness/worker.py` already sums in-process CPU (`t_ns`); `ObservedBackend` already sums out-of-process CPU. P8 is a comparison and a card, not a new measurement.
- Tests cover probes, adversary parsing, adjudication guards, regress templates, classes and the site; nothing covers `ContreeBackend` (there was no access). A recorded-fixture test is enough.

## 2. Scorecard against the judging criteria

Stage 1 (pass/fail: fits the track, applies the required tools) passes today on Token Factory inference alone. Stage 2 is four equally weighted criteria. Ties break on the first criterion, so Technological Implementation matters most.

| Criterion | Where we are | The gap | Fix (items below) |
|---|---|---|---|
| **Technological Implementation** ("how well built; how effectively does it use Token Factory and Nemotron") | Three tiers with explicit reasoning control and a per-tier bill; evidence-checked adjudication; deterministic measurement; verified tests | Untrusted code does not yet run in Token Factory Sandboxes; the README claims it does | **A1–A5** run the published artifacts on Sandboxes; every number cites a microVM image UUID; branch-per-strategy is the non-obvious Sandboxes use |
| **Design** ("complete, coherent product, not a proof of concept") | CLI → verdict, cards, tests; report site; live page; judge box; GitHub Action (uncommitted) | A judge opening the demo URL cannot see an audit *happen*; README reads like day 1; the Action has never run on GitHub | **B1** README, **B2** static replay on the site, **E1** Action run once with a screenshot, **E2** backend chips |
| **Potential Impact** ("credible, specific case for a real audience; does it address it as demonstrated") | Real regressions in pip's version parser reproduced and caught pre-merge; 4/10 merged AI speedups change behaviour (3 likely-bug); 1 reverses 363× | Numbers are adversarial-size; no real-world weighting; nothing audited *before* merge for real | **C1** PyPI-weighted speedups, **C2** audit an open PR live, **C3** tier ablation |
| **Quality of the Idea** ("creative, non-obvious use; genuine understanding") | The benchmark is the suspect; falsify rather than prove; honest ablations | The honest ablation reads as "mutations do 7/9"; the Codeflash result (no-LLM baselines 0, Nemotron 3 behaviour changes + the complexity regression) is the stronger story and is buried | **B1/B3** lead with Codeflash in README and video; **C4** Tavily-cited adjudication (also the $3,000 bonus) |

## 3. The three moves

1. **Run for real in Token Factory Sandboxes.** Access works, it is free in beta, cachegrind runs there, and branching from a snapshot is exactly our base/head pair image → one microVM branch per strategy. This turns the README's first sentence from a claim into an artifact and gives the Coding track judges the thing the track is named for.
2. **Make the story land in three minutes.** Judges may never open the app. README "For judges" table, a replay a judge can watch on the static site, and a video that says "Nebius Token Factory", "Sandboxes", "Nemotron 3 Ultra" and "Nemotron 3.5 Lightning" out loud.
3. **Sharpen impact with cheap, no-LLM evidence** (real-PyPI weighting, one open PR audited before merge) and claim the Tavily bonus with a use that fits the evidence-guard design.

## 4. Workstreams (P0 = must ship, P1 = should, P2 = if time)

### WS-A: Sandboxes backend (P0, critical path, Oct 17–20)

- [x] **A1. ConTree pair-image builder** (done 2026-10-18; `images.build_pair_contree`, harness `bw-harness:<hash>` + pair `bw-pair:<hash>` tags, both found by tag before building; probe acceptance passed: 2 classes on 3 inputs, 37 s including both builds) (`images.py`). Same layout as the Docker image (`/envs/base`, `/envs/head`, `/harness`, system Python with Hypothesis): a one-time kept harness image (python:3.12-slim + valgrind + uv + git), then one kept run per pair that creates both venvs, installs base/head requirements, uploads the harness files with `files=`, and returns the image UUID. Content-addressed `tag=` so a rebuilt pair is a cache hit (find-by-tag). Network is needed only here. *Acceptance:* `breakwater probe --backend contree` on #1082's intermediate commit reports the three known classes.
- [x] **A2. `ContreeBackend` hardening** (done 2026-10-18: semaphore 24, 10 MiB output cap per run with truncation treated as failure, retries with backoff and tag lookup before any kept-run retry, `PYTHONHASHSEED=0` per run, cost in the receipt, `tests/test_contree.py` on a recorded fixture; units confirmed as getrusage seconds/kB by inspection, the team has not been asked). Concurrency semaphore (24, under the 50 cap); retries per the docs (back off on rate/service rejections; never blindly resubmit a request that got no operation id); `stdout` capture above the 1 MiB default for `make` ladders (file/`BytesIO` capture, or chunk the ladder); per-run `cost_usd` into the receipt as "Sandbox cost (free during beta)"; a recorded-fixture unit test. Confirm the resource units with the team (docs call them diagnostics-only) and note it in the feedback log.
- [x] **A3. Network off for probe runs** (done 2026-10-18: 0.3.6 has no option; every non-build run goes through `unshare -n`, verified to break name resolution and connections; logged in the feedback log and the README limitations). Use the SDK's networking option if 0.3.6 exposes one; if not, log it in the feedback log and rely on microVM isolation (say so in the README).
- [x] **A4. Publishable runs on Sandboxes** (demo audit 2026-10-24, see G3; Codeflash `codeflash-v2` and the packaging subset `packaging-v4-sandboxes` 2026-10-24, see G2') (Token Factory + Sandboxes, in this order): the demo audit of #1082's intermediate commit (replaces `artifacts/demo/pr1082-61967cca`; this is the video run); the Codeflash corpus (10 items, ~$1); the packaging items with known issues plus the perf-bearing ones (#1030, #1064, #1082, 1082@61967cca, #1108, #1116, #1147, #1236; ~$1.5 incl. adjudication). Keep the full 29-item Docker backtest as published, labelled by backend. *Acceptance:* same verdicts on both backends for every re-run item; Ir ratios within a few percent (different CPUs, same instruction stream).
- [x] **A5. Provenance everywhere** (done 2026-10-24: backend chip and image on every index row, run row, PR page and card; a Backend column in every receipt; the reproduce command passes `--backend`; `report.md`'s perf section and Docker sandbox line cite backend and image; backtests, adjudications and regression runs record the backend next to the image, and the site infers it for older artifacts from the ref). The PR comment (`comment.py`) is still uncommitted in the main checkout, not on this branch, so it was left alone; add the backend/image line there when it lands (E1). README's usage table is B1.
- [x] **A6. `breakwater doctor`** (done 2026-10-18: whoami, concurrency and timeout limits against Breakwater's own caps, output cap, harness image by tag). calls Sandboxes `whoami`, prints the effective concurrency and timeout limits, and says whether the harness image exists.

**Gate G3 (Tue Oct 20):** the demo audit runs end to end on Sandboxes with Ir. If it does not, publish Docker numbers, keep the Docker backend as the honest default, and rewrite the README's first sentence. Either way the README stops claiming what the artifacts don't show.

**G3 result: passed (retake 2026-10-24).** `breakwater audit --backend contree` on Token Factory completed end to end on Sandboxes in 415 s: `artifacts/demo/pr1082-61967cca-sandboxes` (run `e780ff68654f`, image `dbe8dafe-78c4-4fc8-b8c2-a5adaad2ed49`, 358 microVM runs, 1,165 s CPU, Nemotron $0.18, nominal sandbox cost $11.92 shown as free during beta). Compared with the Docker run `artifacts/demo/pr1082-61967cca` (`scripts/day1/compare_backends.py`):

| | Docker (Oct 9) | Sandboxes (Oct 24) |
|---|---|---|
| Verdict | BLOCK | BLOCK |
| Behaviour classes | 6 (6 likely-bug) | 6 (4 likely-bug, 2 intended): 4 classes shared; each run has two near-duplicate variants of the huge-number class the other lacks. Labels on the huge-number classes vary between Ultra adjudications, not between backends |
| Verified regression tests | 6 | 4 |
| Perf families measured | 4 slower (2.4–2.8×), all from the archive | 5: archive family R4 slower 2.51× (Docker 2.44×, within 3%), its two Super variants 2.74×, one planned slower family 1.14×, and the claimed speedup confirmed faster (0.38× at n=2, 0.91× at n=4096) |

A first Sandboxes attempt on Oct 17 (run `028a9666580c`, same verdict, $0.24) had only neutral perf families because the perf archive (`artifacts/archive`, gitignored) lives in the main checkout and the worktree's copy was empty; it is superseded by the retake. The archived families were also replayed on Sandboxes with no model calls (`artifacts/day1/contree_perf_replay.json`: 16 families, 105 runs, 140 s): every screen ratio is within 1–6% of the Docker value (R1 2.09× → 2.00×, R3 1.288× → 1.287×, F2 0.644× → 0.631×, F6 0.440× → 0.428×), with 525 KB ladders intact. Token Factory spend on WS-A: $0.48 (one failed attempt $0.05, the first run $0.24, the retake $0.18).

Two Sandboxes-specific fixes came out of the live runs: the probe batch timeout (60 + 20 s per input, up to 18,860 s) is clamped to the 3,600 s limit, and `PYTHONHASHSEED=0` is passed per run (Ir drifted ~0.01% without it).

**G2' result (Fri Oct 24): evidence complete on Sandboxes.** Both runs on Token Factory inference with every untrusted run in a Sandboxes microVM, 3 items in parallel, 24 microVMs at most in flight. Spend: Codeflash backtest $0.81 + adjudication $0.08 (+ $0.04 on an aborted first attempt: two workers raced to clone one repo; fixed before any item finished) = **$0.92**; packaging subset backtest $0.77 + adjudication $0.35 = **$1.12**. A4 total **$2.04** against the $2.50 budgeted; WS-A in all $2.52. Compared with `scripts/backtest/compare_backends.py` (verdicts as the site computes them: behaviour + performance).

*Acceptance read honestly.* Same verdict on 13 of 18 re-run items. Every one of the five differences traces to the model sampling a different plan or a different adjudication on the same evidence, not to the backend: where both runs found a class with the same signature it has the same base/head facts, known-issue recall is identical (9/9 verified, mutations 7/9, hypothesis 2/9 on both), and the archived perf families (identical seeded inputs) agree in verdict on both backends. Ir ratios are within 0–8% on 10 of the 11 shared families and 44% apart on one regex-bound complexity regression; the gap is architecture (Docker on the Mac is arm64, the microVM is x86_64, see `decisions.md` 2026-10-24), so "within a few percent" holds only on one architecture and the README should say "deterministic on a given image", not "the same count everywhere".

Codeflash, `codeflash-v1` (Docker, Oct 12) → `codeflash-v2` (Sandboxes, Oct 24; the published run):

| Item | Docker | Sandboxes | Same? | Why not |
|---|---|---|---|---|
| Math-Interpreter #1 | BLOCK; 3 likely-bug; 3 tests | BLOCK; same 3 classes: 2 likely-bug, 1 needs-human; 3 tests | ✓ | |
| micropie #3 | REVIEW; 1.34× | REVIEW; 1.60× (new planned family) | ✓ | |
| caddy-feeds #4 | BLOCK; 1 likely-bug; 1 test | BLOCK; same; 1 test | ✓ | |
| patterns #9, rendercv #17, rendercv #19, pyhs3 #154 | PASS | PASS | ✓ | pyhs3 unmeasured (caching) on both |
| patterns #12 | PASS | **BLOCK**: new wrong-type class (nested list: `AttributeError` → `TypeError`), likely-bug 3/3, test verified | ✗ | a new Ultra attack found it |
| rendercv #18 | BLOCK; 2 likely-bug; 2 tests | **PASS**: 1 class, labelled intended 3/3 (Docker: likely-bug 2/3 on the same kind of class); the `AttributeError` near-duplicate not found | ✗ | adjudicator vote + search sampling |
| json_repair #113 | BLOCK; 393× | BLOCK; 363× (same four complexity families, 7.1–7.6% lower) | ✓ | |

Shared Codeflash families: Math-Interpreter ×3 0.0%, rendercv #18 0.2%, json_repair ×4 7.1–7.6%. Images: `6cbae808…`, `f05e47b2…`, `1bafd31e…`, `bcc79688…`, `87c6903e…`, `aa55391a…`, `54410864…`, `5d1921f3…`, `44ce7ab3…`, `78fcee79…` (full UUIDs on every page and in `results.json`).

Packaging subset, `packaging-v3` (Docker, Oct 9; perf from `packaging-v2`) → `packaging-v4-sandboxes` (Oct 24; shown on the site as the Sandboxes comparison next to the full 29-item Docker backtest):

| Item | Docker | Sandboxes | Same? | Why not |
|---|---|---|---|---|
| #1030 | BLOCK; 8 likely-bug; unicode-lowercase; 4.52× `many_underscores_and_dots` (complexity); 8 tests | BLOCK; 7 likely-bug; unicode-lowercase; 6.50× on the same archived family (complexity); 7 tests | ✓ | |
| #1064 | PASS; 7 classes all intended 3/3 (quoting the PEP 503 docstring: the lowercasing *is* the fix) | **BLOCK**; the same 7 classes, likely-bug 2/3 ("titled a performance improvement, no tests/docs updated"; the quote is the PR title); 7 tests | ✗ | adjudicator vote; the Docker label is the right one |
| #1082 | BLOCK; 2 classes: oversized-int → intended (the known miss), nested-input `TypeError` → `AttributeError` → likely-bug; 2.85× | **REVIEW**; only the oversized-int class, intended 3/3 (same miss as v2/v3); REVIEW from perf 2.91× | ✗ | search did not hit the nested-input class this run |
| 1082@61967cca | BLOCK; 5 classes (3 likely-bug, 2 intended); all 3 known; 1.91×; 3 tests | BLOCK; 6 classes (4 likely-bug, 2 needs-human); all 3 known; 2.86× (new planned family); 6 tests | ✓ | oversized-int: intended on Docker, needs-human here |
| #1108 | BLOCK; 15 classes (12 likely-bug, 3 needs-human); all 3 known; 15 tests | BLOCK; 11 classes (10 likely-bug, 1 needs-human); all 3 known; 11 tests | ✓ | |
| #1116 | BLOCK; 1 likely-bug; old-pickles-fail-to-load; 1 test | identical | ✓ | |
| #1147 | BLOCK; 1 likely-bug; marker-pickle; 1 test | identical | ✓ | |
| #1236 | PASS; 4 exception-type classes, intended 4/4 (docstring says `InvalidTag`); 1.09× | **REVIEW**; 6 such classes, needs-human on all (no majority: votes split three ways); 1.09× | ✗ | adjudicator abstained; a safe miss |

Known-issue labelling on Sandboxes: 8 of 10 found issues likely-bug (v3: 8 of 10); the miss is #1082's oversized-int exception, intended on the merged PR (as in v2 and v3) and needs-human on the intermediate commit (v3: intended). Regression tests: 39 of 39 generated verified, 1 class skipped as intended (v3, all 29 items: 30/30). Shared packaging families: #1064 `many_underscores_and_dots` 1.10× → 1.08× (2.2%); #1030 "names starting/ending with multiple dots" 2.28× → 2.46× (7.9%); #1030 `many_underscores_and_dots` 4.52× → 6.50× (44%: at n=4096, identical 8,196-char inputs, arm64 base 266,708 / head 1,204,830 Ir, x86_64 base 213,950 / head 1,390,193; the regex-bound head costs more instructions on x86_64 and the base fewer). Images: #1030 `a2d83f6b…`, #1064 `bfdb727b…`, #1082 `cdd80561…`, 1082@61967cca `62d98fe8…`, #1108 `052dfee2…`, #1116 `e7fbcc0c…`, #1147 `583e9e77…`, #1236 `5c5765e3…`.

What this adds to the story: the backend does not change what Breakwater finds; the adjudicator's vote on borderline "intended" classes varies between runs (#1064, rendercv #18, #1236), which is the honest motivation for C4 (a cited public spec in the adjudicator's context) and for keeping needs-human as the default when votes split.

### WS-B: Story and submission (P0, Oct 21–29)

- [x] **B1. README rewrite** (done 2026-10-25 without the architecture SVG; demo and video URLs left as `[x]` until B7; update the README when C2/C4/D1 land). Top: one paragraph, then the "For judges" table (Section 8). Then "What it found" (Codeflash first: 3/10 change behaviour, 393× reversal; then packaging 9/9 vs 7/9). Then how it works, as built, with an architecture figure (one SVG, no external assets). Usage table limited to what ran: Nemotron 3 Ultra, Nemotron 3.5 Lightning, Nemotron 3 Super, Token Factory inference, Sandboxes; Serverless Jobs and NeMo Gym removed unless D5 ships. Limitations: falsifies, doesn't prove; pre-existing bugs are invisible; Python 3.12, JSON-able arguments; Ir not wall time. Quickstart that works on a fresh machine (judges may try it). Remove "pre-alpha", "planned" and every `[x]`.
- [ ] **B2. Static replay on the site.** Playback of the committed `events.jsonl` entirely in the browser (reuse `live.js`; no polling server), with a speed control and the "replay of run <id>" label and real timestamps. Linked from the index as "Watch an audit". Judges who never run anything still see the plan, the strategies, the Sandbox gauge filling, cards landing and the bill ticking.
- [ ] **B3. Video** per [demo-script.md](demo-script.md), recorded from the Sandboxes demo run (replay at 8×, said on camera). Script locked Oct 25, recorded Oct 26–27, uploaded Oct 28 (allow 2–3 h). Say the model and product names aloud. Lead with the Codeflash reversal (a "109% faster" change that does 393× the work) within the first 20 s.
- [ ] **B4. Feedback write-up** from [feedback-log.md](feedback-log.md): required field, 10 × $100 prizes. Group by product (Token Factory inference, Nemotron reasoning controls, structured output, Sandboxes SDK/docs), each entry with what we tried, what happened, what would have helped. Add today's Sandboxes entries (worked first try; resources only via `_raw`; units documented as diagnostics-only; docs page inconsistencies).
- [ ] **B5. Consistency pass on docs:** `spec.md` verdicts and pipeline to match what shipped; `judging-map.md` replaced by Section 8; `risks.md` rows 1–2 retired; `day1-checklist.md` section D filled.
- [ ] **B6. Devpost submission:** track (Coding and Agentic Engineering), description, demo URL (GitHub Pages), repo URL (public, Apache-2.0 visible in About), video URL, feedback text, "what was built during the submission period" (everything: first commit Oct 8), City Winner city if a Builders & Brews event was attended (SF Oct 9 / LA Oct 13). Test instructions: `uv sync`, `breakwater site`, the judge box, and a Token Factory key for a live audit.
- [ ] **B7. Publish:** flip the repo public, run the Pages workflow, test in a clean browser (Pyodide loads from jsDelivr on click), check the license badge in About. Oct 28, before the video upload.

### WS-C: Evidence and impact (P1, Oct 21–24)

- [ ] **C1. Real-world weighting (no LLM).** Build a sealed corpus of real version strings, specifiers and project names from PyPI (top ~10k projects via the JSON API, or the `pypi-json-data` dataset; record source, date and license in decisions.md). Measure Ir base vs head over that distribution for #1082 (`Version`), #1108 (`SpecifierSet`) and #1030 (`canonicalize_name`). Headline: "2.06× on simple versions, 0.97× on everything else, **[x]× weighted over [x] real PyPI versions**." Site section + README line. Cost $0.
- [ ] **C2. One open PR audited before merge.** Pick a currently open "perf" PR in a pure-Python library (packaging first, then popular libs), run `breakwater audit` on Sandboxes, publish the run page under "Latest". If it finds something, a human verifies it and the team decides on an upstream note (tone rule in risks.md). Cost ~$0.3. This is the only item that demonstrates the product's actual job: pre-merge.
- [ ] **C3. Tier ablation "Lightning executes".** Strategies written by Ultra vs Lightning (and Nano, for $0.01) on the Codeflash corpus and the known-issue packaging items; report classes found per dollar and per minute by tier. Direct evidence for "effective use of Nemotron" and the spec's third headline. Cost ~$2.
- [ ] **C4. Tavily in the adjudicator** (functional runtime call; the $3,000 "Best Use of Tavily" bonus is separate from track/overall awards). The adjudicator's `intended` criterion is "what the library's own documentation says should happen", but it only sees in-repo docstrings. Add "Context 4: public specification and docs" fetched with Tavily search + extract (PEP 440/503, the project's docs, the upstream issue tracker for the Codeflash repos), quotable under the same verbatim-quote guard, behind `--recon` (default on when `TAVILY_API_KEY` is set). Ablation: re-adjudicate the 47 packaging classes and the 6 Codeflash classes with and without it (~$1 Nemotron); report every label change and whether the oversized-int miss moves. Keep it only if the ablation shows value; disclose either way. Log Tavily friction in the feedback log.
- [ ] **C5. (P2) Third corpus:** 8–10 human-written "perf:" PRs across other popular pure-Python libraries, to answer "does it only work on packaging?". Only if C1–C4 are done by Oct 23.

### WS-D: Harness completeness (P1/P2)

- [ ] **D1. Two clocks (P8), P1.** The README promises it. Compare the worker's summed in-process CPU with the backend's out-of-process user CPU per side; flag a residual above a threshold as "timing anomaly" and show it as a card. Demonstrate on one synthetic cheating candidate (work moved to a subprocess, or `time.process_time_ns` patched) in a test and on the site. If this cannot land by Oct 23, delete the claim from the README instead.
- [ ] **D2. Peak memory (P6), P2.** `max_rss_kb` is already recorded per run on both backends; add base vs head peak RSS per family to the perf table. Nearly free; judges like a memory column.
- [ ] **D3. Report wording, P2.** Ladder stop at the 2 MB input cap is "stopped at n=4096", not "error". Class split for Unicode digits vs inner whitespace stays as is (traits already separate them in v3).
- [ ] **D4. Hash-seed determinism (P7), non-mutation (P5): cut.** Say so in limitations.
- [ ] **D5. Serverless Jobs, P2 (stretch, after everything above).** Either finalist wall-clock timing with ABAB interleaving and bootstrap CIs on a dedicated CPU VM, or the Sandboxes backtest campaign itself as a Serverless Job (resumable). Costs AI Cloud balance and a day; only worth it if G3 and WS-B are done by Oct 24.

### WS-E: Product polish (P1)

- [ ] **E1. GitHub Action.** Commit the uncommitted work in the main checkout; add a repo secret and run it once on a test PR in a fork of pypa/packaging (owner's call); screenshot the comment for the README and video. Add `backend: contree` as the default when `NEBIUS_PROJECT_ID` is set.
- [ ] **E2. Site:** backend + image UUID chip on every page; "Latest audits" section (C2); Method page updated for Sandboxes; one pass at phone width.
- [ ] **E3. Live page:** show the Sandboxes image UUID and per-run cost in the sandbox gauge.
- [ ] **E4. Judge box:** unchanged; verify in a clean browser at B7.

## 5. Schedule and gates

| Date | Work | Gate |
|---|---|---|
| Fri Oct 17 – Mon Oct 19 | A1, A2, A3, A6; E1 commit | — |
| **Tue Oct 20** | A4 demo audit on Sandboxes | **G3: demo audit end to end on Sandboxes with Ir.** Fail → Docker stays, README reworded |
| Wed Oct 21 – Thu Oct 22 | A4 Codeflash + packaging subset on Sandboxes; A5; C1; B5 | **G2' (Oct 22): evidence complete.** Every published number has a backend, image UUID and provider. *Passed Oct 24 (A4, A5); C1 and B5 still open* |
| Sun Oct 25 – Mon Oct 26 | B1 README (done Oct 25); features: E1, B2, C2, C4, D1 or delete its claim, D2 | **Feature freeze Mon Oct 26 23:59 PT** (moved from Sat Oct 24). Cut from the bottom of Section 7 |
| Tue Oct 27 | B4 feedback write-up, script locked, record; README numbers refreshed for anything that landed | — |
| Wed Oct 28 | B7 publish (public repo, Pages, clean-browser test), B3 upload | — |
| **Thu Oct 29** | B6 submit on Devpost | Fri morning is buffer only |

## 6. Budget

Token Factory ledger through Oct 12: **$13.06** spent, so about $13 of the $26 credit remains (more if the Builder Program credit landed; check the console). Sandboxes is free during beta. Plan, in priority order; stop when the credit runs out:

| Item | Nemotron cost |
|---|---|
| A4 demo audit on Sandboxes (plus one retake) | $0.40 |
| A4 Codeflash on Sandboxes | $1.00 |
| A4 packaging subset + adjudication on Sandboxes | $1.50 |
| C2 open-PR audit | $0.30 |
| C4 Tavily ablation (adjudication only) | $1.00 |
| C3 tier ablation | $2.00 |
| Buffer for retakes and the final video run | $2.00 |
| **Total** | **$8.20** |

Development keeps using `BREAKWATER_PROVIDER=openrouter`. Nothing from OpenRouter is published.

## 7. Cut list (drop from the top)

1. D5 Serverless Jobs
2. C5 third corpus
3. C3 tier ablation
4. D1 two clocks (then delete the README claim)
5. C4 Tavily (then the bonus is gone, nothing else changes)
6. B2 static replay (keep the recorded replay command and the run pages)
7. C1 real-world weighting (keep the adversarial-size numbers, labelled as such)

**Never cut:** Sandboxes for the demo run (or the README reword), the README "For judges" table, the video, the feedback write-up, provenance on every number, the real bill.

## 8. "For judges" table (fill links at B1; replaces judging-map.md)

| Criterion | Claim | Evidence a judge can check in a minute |
|---|---|---|
| Technological Implementation | Three Nemotron tiers on Token Factory with explicit reasoning control, structured output and a per-tier bill; LLM-written code runs only in Token Factory Sandboxes microVMs branched from a recorded image; deterministic Ir measurement; evidence-checked adjudication; verified regression tests | `llm.py`, `backends/contree.py`, receipt on any run page (tier bill, image UUID, backend), `artifacts/day1/contree.json` |
| Design | One command or one GitHub Action → verdict, counterexample cards with ready-to-commit tests, a report page, a PR comment; a replay to watch; a judge box to try | Demo URL: index, a PR page, "Watch an audit", "Try it"; Action comment screenshot |
| Potential Impact | 9/9 documented regressions in pip's version parser caught before merge (best no-LLM baseline 7/9), on Docker and again on Sandboxes; 4/10 merged AI speedups change behaviour (3 adjudicated likely-bug) and one does 363× the work on valid input; [x] weighted over real PyPI versions; one open PR audited pre-merge | Backtest tables, Codeflash sub-site, `ground_truth.json`, the "Latest" run |
| Quality of the Idea | The benchmark is the suspect: an adversary that tries to falsify speed and equivalence claims, with honest ablations of what the model adds; the adjudicator must quote its evidence (and, with Tavily, the public spec) | README "Why", `docs/backtest.md` "What Nemotron adds", adjudication pages |
| Track fit | A coding agent that writes, runs and tests code in Token Factory Sandboxes | Live page sandbox gauge; image UUIDs on every number |
| Tavily bonus | A functional runtime call: the adjudicator cites the public specification | `adjudicate.py` recon context, ablation table |
| Feedback prize | 14+ specific entries with reproduction and a suggestion each | `docs/feedback-log.md`, the Devpost feedback field |

## 9. Submission checklist (Devpost)

- [ ] Public repo URL, Apache-2.0 visible in About
- [ ] README with setup, run instructions, NVIDIA/Nebius usage highlighted
- [ ] Demo URL (GitHub Pages) live and free through Dec 15; judge box tested in a clean browser
- [ ] YouTube video, public, under 3:00, shows the project working, names said aloud, no third-party music
- [ ] Text description: what, why, how; track chosen
- [ ] Feedback on Token Factory, Sandboxes, Nemotron (required)
- [ ] "Built during the submission period" statement (first commit Oct 8, inside Aug 26 – Oct 30)
- [ ] City for the City Winner award, if an event was attended
- [ ] Test instructions, including that a Token Factory key is needed for a live audit and that everything published is reproducible from the recorded image UUID and seed
