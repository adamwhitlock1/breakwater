# Final sprint: audit of Oct 17 and the plan to Oct 30

This is the forward plan from Oct 17. [roadmap.md](roadmap.md) stays the ledger of what was built and when; this file says what to add and refine in the 12 days left, in priority order, with gates and a budget. Decisions here follow [decisions.md](decisions.md); nothing below reopens a settled one.

**Deadline: Fri Oct 30, 10:00 PT. Submit Thu Oct 29. Feature freeze Sat Oct 24.** Judging is Dec 1–15; the demo URL must stay up and free until then.

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
| Codeflash corpus: 10 merged AI speedups in 7 repos; 3/10 change behaviour, 1/10 is a 393× complexity regression; no-LLM baselines found 0 | `artifacts/backtest/codeflash-v1` |
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
| **Potential Impact** ("credible, specific case for a real audience; does it address it as demonstrated") | Real regressions in pip's version parser reproduced and caught pre-merge; 3/10 merged AI speedups change behaviour; 1 reverses 393× | Numbers are adversarial-size; no real-world weighting; nothing audited *before* merge for real | **C1** PyPI-weighted speedups, **C2** audit an open PR live, **C3** tier ablation |
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
- [ ] **A4. Publishable runs on Sandboxes** (Token Factory + Sandboxes, in this order): the demo audit of #1082's intermediate commit (replaces `artifacts/demo/pr1082-61967cca`; this is the video run); the Codeflash corpus (10 items, ~$1); the packaging items with known issues plus the perf-bearing ones (#1030, #1064, #1082, 1082@61967cca, #1108, #1116, #1147, #1236; ~$1.5 incl. adjudication). Keep the full 29-item Docker backtest as published, labelled by backend. *Acceptance:* same verdicts on both backends for every re-run item; Ir ratios within a few percent (different CPUs, same instruction stream).
- [ ] **A5. Provenance everywhere.** Backend and image UUID on every site page and card, in the PR comment, in `report.md`. README's usage table says exactly what ran where.
- [x] **A6. `breakwater doctor`** (done 2026-10-18: whoami, concurrency and timeout limits against Breakwater's own caps, output cap, harness image by tag). calls Sandboxes `whoami`, prints the effective concurrency and timeout limits, and says whether the harness image exists.

**Gate G3 (Tue Oct 20):** the demo audit runs end to end on Sandboxes with Ir. If it does not, publish Docker numbers, keep the Docker backend as the honest default, and rewrite the README's first sentence. Either way the README stops claiming what the artifacts don't show.

### WS-B: Story and submission (P0, Oct 21–29)

- [ ] **B1. README rewrite.** Top: one paragraph, then the "For judges" table (Section 8). Then "What it found" (Codeflash first: 3/10 change behaviour, 393× reversal; then packaging 9/9 vs 7/9). Then how it works, as built, with an architecture figure (one SVG, no external assets). Usage table limited to what ran: Nemotron 3 Ultra, Nemotron 3.5 Lightning, Nemotron 3 Super, Token Factory inference, Sandboxes; Serverless Jobs and NeMo Gym removed unless D5 ships. Limitations: falsifies, doesn't prove; pre-existing bugs are invisible; Python 3.12, JSON-able arguments; Ir not wall time. Quickstart that works on a fresh machine (judges may try it). Remove "pre-alpha", "planned" and every `[x]`.
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
| Wed Oct 21 – Thu Oct 22 | A4 Codeflash + packaging subset on Sandboxes; A5; C1; B5 | **G2' (Oct 22): evidence complete.** Every published number has a backend, image UUID and provider |
| Fri Oct 23 – Sat Oct 24 | C2, C4 (Tavily + ablation), C3, B2, D1, D2, E2, E3 | **Feature freeze Sat Oct 24 23:59 PT.** Cut from the bottom of Section 7 |
| Sun Oct 25 – Tue Oct 27 | B1 README, Section 8 table with links, B4 feedback write-up, script locked Oct 25, record Oct 26–27 | — |
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
| Potential Impact | 9/9 documented regressions in pip's version parser caught before merge (best no-LLM baseline 7/9); 3/10 merged AI speedups change behaviour and one does 393× the work on valid input; [x] weighted over real PyPI versions; one open PR audited pre-merge | Backtest tables, Codeflash sub-site, `ground_truth.json`, the "Latest" run |
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
