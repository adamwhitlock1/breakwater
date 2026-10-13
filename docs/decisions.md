# Decision log

Newest first. One entry per decision: what, why, what would reverse it.

## 2026-10-12: The verdict includes performance, not only behaviour
- **What:** a PR's verdict is the stricter of behaviour and performance:
  - behaviour: BLOCK on a likely bug, REVIEW on an unsettled or unlabelled class;
  - performance: BLOCK on a complexity regression in a family of mostly valid inputs, REVIEW on a valid family at least 1.25× slower.
  The banner states the performance reason.
- **Why:** json_repair #113 ("109% faster") does up to 393× the work on valid JSON objects, yet showed PASS, "No behaviour divergence found". A red team for performance PRs can't pass a speedup that reverses.
- **Effect:**
  - Codeflash: json_repair #113 becomes BLOCK and micropie #3 (1.34×) becomes REVIEW.
  - Packaging: no verdict changes. Its slower PRs were already BLOCK, and the rest are under 1.25×.
- **Reverse if:** the 1.25× bar flags noise in practice. Ir is deterministic, so it shouldn't.

## 2026-10-12: Instructions per call need a linear fit; relations accept non-bool comparisons
- **Linear Ir:** instructions per call now come from Ir at R, 2R and 3R repetitions. A point counts only if the two increments agree within 10% and are positive; otherwise it is "unmeasured".
  - **Why:** memoising targets aren't linear in repetitions. In the Codeflash dev run, pyhs3 #154 (`lru_cache` plus sympy's own cache) produced a ladder of 1.59, 0.86, 0.97, 4.65, 1.5, 2.02 and −0.52 under the two-point method, and a 4.65× "slower" verdict that was pure artifact.
  - **Cost:** one extra cachegrind run per measurement.
  - **Spot check:** the three-point method matches the published two-point numbers for non-memoising targets: packaging #1030 R1 within a few percent; micropie #3 F4 1.712 → 1.711. Published numbers stand.
- **Non-bool relations:** the relations probe crashed the worker when `a < b` returned an object (sympy's `StrictLessThan`), which made every pyhs3 arm fail. Non-bool results are now recorded by normalised repr.
- **Request deadline:** every model request now has a 15-minute wall-clock deadline and is retried after it. The SDK timeout bounds the gap between bytes, so an OpenRouter call that trickled keep-alive bytes sat in an SSL read for 30+ minutes. The free Ultra route still stalled repeatedly on pyhs3's plan; that dev re-run was stopped.
- **Reverse if:** never. Memoisation is common in AI speedups (4 of the 10 Codeflash PRs add `lru_cache`).

## 2026-10-12: Codeflash corpus: script repos, merge-date dependencies, no ground truth
- **What:**
  - Ten merged Codeflash-bot speedup PRs: json_repair, rendercv ×3, pyhs3, Math-Interpreter, patterns ×2, caddy-feeds and micropie.
  - Repos that aren't packages are cloned at the commit and put on the venv path.
  - Every item's dependencies resolve as of the day after its merge.
  - Base is the merge commit's first parent.
- **Why:**
  - The most aggressive speedup claims (9,172%, 17,376%) are in script repos, so leaving those out would bias the sample toward tidy packages.
  - Unpinned dependencies drift: pyhs3 failed to import against a 2026-10 pytensor.
  - Without known regressions, the claim is "N of M merged AI speedups change behaviour or don't deliver", with each finding adjudicated and checked by a verified regression test.
- **Excluded:** kornia, roboflow/inference, langflow, gdsfactory and chembench (torch, klayout, LLM SDKs, cloud clients), app repos without a package, and targets that need keyword arguments or live objects.
- **Reverse if:** a Codeflash PR turns out to need its repo's test fixtures to behave realistically. In that case, add fixtures to the item.

## 2026-10-11: Perf verdicts use only ladder sizes with mostly valid inputs
- **What:**
  - Every ladder size records `valid_fraction`: the share of its inputs that the base version accepts.
  - The verdict, slopes and worst ratio use only sizes with `valid_fraction >= 0.5`. A family whose every size is mostly invalid is judged on all sizes and is already flagged as error-path.
  - Excluded sizes stay visible: hollow points on the chart, with a count in the table.
- **Why:** LLM-written generators drift. In the 2026-10-09 demo run, a claimed-speedup family (head ~0.36× on simple versions) emitted one invalid input at n=1024, where head's failed fast path costs 2.2×. That single point labelled the family `slower`.
- **Backfill:** generators run seeded in the sandbox, so published ladders regenerate exactly. Each regenerated size is checked against the recorded mean input size before its validity is used.
- **Reverse if:** never. The error-path cost is still reported, as error-path families and excluded points.

## 2026-10-09: Planner v3: attacks must predict a difference, checked against the old code
- **What:**
  - The plan schema leads with the false assumption, then base behaviour, head behaviour and a required `difference` kind (with an explicit "no difference expected" option).
  - Attacks marked "no difference expected", or with identical base/head behaviour, are dropped before they take a slot.
  - The prompt says path-mapping is not an attack, and asks Ultra to trace the old code on each example before claiming a difference.
- **Why:** on Token Factory, Ultra's plans for #1082's intermediate commit mostly described which code path an input takes. `scripts/eval/planner_eval.py` probes each attack's own examples, with no search and no mutations. Results, 3 runs each:

  | Prompt | Productive attacks | Runs whose plan alone exposes a class | Cost |
  |---|---|---|---|
  | v1 (original) | 0/15 | 0/3 | $0.11 |
  | v2 (schema + drop) | 4/13 | 2/3 | $0.08 |
  | v3 (+ trace the old code) | 7/15 | 3/3 | $0.14 |

  Earlier "planner finds the bug" results came from the full pipeline (search and mutations), not the plan alone.
- **Caveats:**
  - n=3 per version on one PR, so these are directional numbers.
  - The backtest ran with v1, so its llm-plan arm (5/9) measures v1.
- **Reverse if:** a backtest re-run with v3 shows fewer known issues caught than v1.

## 2026-10-09: The perf archive records who proposed each family
- **What:** archive entries carry `proposed_by` (provider of the run that first proposed the family; existing entries backfilled from the ledger: 67 Token Factory, 8 OpenRouter). Token Factory runs re-screen only Token Factory-proposed families; dev runs may use any.
- **Why:** the archive is what keeps good finds across runs (the demo run's 2.76x family came from it), but a publishable run must not contain inputs a non-Token-Factory model proposed. Turning the archive off for publishable runs threw away 67 legitimate families and gave a weak demo plan.
- **Reverse if:** never for publishable runs.

## 2026-10-08: Adjudication = Ultra votes, checked by deterministic guards
- **What:** `adjudicate.py` labels every divergence class `likely-bug`, `intended` or `needs-human`. One Ultra call per target covers all its classes, with 3 samples, `medium_effort` and a JSON schema. The audit report says BLOCK only on `likely-bug`.
- **What the model sees:** what a reviewer has at PR time:
  - the PR title and code diff;
  - the PR's own test, doc and changelog changes (`repo.intent_diff`). The planner never sees these; for adjudication they are the author's statement of intent;
  - the head module source with its docstrings;
  - the facts for each class, including how the two exception types relate, resolved in the sandbox.
  It never sees later fixes, issue threads or the known-issue list.
- **Guards (deterministic):**
  - a label needs a strict majority of the samples *requested*, so a lost sample can't create one;
  - a likely-bug or intended vote must quote evidence that is found verbatim (whitespace- and diff-marker-normalised) in the material it was given, otherwise it counts as needs-human;
  - the model can only add labels; it cannot drop, merge or edit a finding.
- **Why:** an `intended` label waves a divergence through, so a hallucinated reason is the costly failure. Quote checks and majority voting make that failure need agreement across samples plus real text.
- **Scoring:** known issues were all fixed upstream, so their classes should be `likely-bug`. `needs-human` is a safe miss; `intended` is the dangerous one.
- **Lessons from the development runs (free OpenRouter routes; numbers not published):**
  - **The adjudicator can't catch probe artifacts.** It labelled the P4 int-digit artifacts (see `backtest.md`, P4 control fix) `likely-bug`, with confident rationales and real quotes. Fixing those facts is the probes' job, which is why facts come first.
  - **Facts state relations without interpreting them.** "`InvalidVersion` subclasses `ValueError`" is a fact. "…so `except ValueError` still catches it" argues one side and nudged votes toward `intended`.
  - **Free routes drop samples.** One top-up call refills them, so an abstention means disagreement, not a lost response.
  - **Runaway samples on large calls (backtest v3, #1108, 15 classes):** samples hit the token cap with little reasoning, apparently running away outside the bounded fields. Now at most 8 classes per call and a 16k-token cap, with bounded rationale and evidence lengths. Quotes written with literal `\n` escapes now match.
  - **Empty samples on Token Factory (2026-10-09 demo run):** 2 of 3 samples came back as `{"verdicts": []}`, which is valid under the schema and counted as parsed, so every class had one vote and abstained. The schema is now pinned per call (exactly one verdict per class, ids enumerated), and a sample covering under half the classes counts as lost and is topped up. The published backtest adjudication had full votes on all 47 classes, so it was not affected.
- **Lessons from the Token Factory runs:** put long context first and the facts and task last, restating the evidence rule there. With the task first, Ultra sometimes answered a different task about the code. The quote guard demoted those votes, which is the guard doing its job. Results and run history: `backtest.md`, Adjudication.
- **Reverse if:** the backtest shows guards demoting most correct votes (too strict), or `intended` on a known issue survives them (too weak).

## 2026-10-08: OpenRouter as a development-only provider
- **What:** `BREAKWATER_PROVIDER=openrouter` routes the same three Nemotron tiers to OpenRouter's free routes (`nvidia/nemotron-3.5-lightning:free`, `nemotron-3-super-120b-a12b:free`, `nemotron-3-ultra-550b-a55b:free`). The default stays `tokenfactory`.
- **Why:** Token Factory credit is $26 in total and ~$6.44 was spent by the end of day 1, almost all on Ultra planning. Prompt tuning and debugging should not spend it.
- **Rules:** only Token Factory runs feed published numbers (hackathon rule: NVIDIA calls must go through Token Factory). Every ledger entry, audit report and backtest result records its provider; non-Token-Factory reports carry a "development run" banner; `breakwater bill` splits by provider.
- **Differences handled in `llm.py`:** reasoning via OpenRouter's `reasoning` parameter; no `n` (parallel requests); free Ultra/Lightning reject `response_format`, so the schema goes in the prompt; retries with backoff for rate limits (also now on for Token Factory, after the backtest's transient connection error).
- **Reverse if:** free-route quality or rate limits make development results misleading. Then use OpenRouter's paid routes via `BREAKWATER_OPENROUTER_MODEL_<TIER>` (cents), or a local model.

## 2026-10-08: Stabilise with search over families plus deterministic coverage, not better prompts alone
- **Why:** plan quality varied a lot between samples (5 perf runs on one PR: 1 clean, others weak, mislabelled or broken). Now: more samples, a cheap Ir screen of every family, Super-written variants of the slowest realistic ones, an archive of slower families per target, and deterministic hostile-string mutations for the semantic side. Since then every run has found valid slower families and 3/3 known semantic classes.
- **Model roles:** Ultra plans; Super writes code that needs reasoning (family variants); Lightning writes volume code (strategies, generator repair).
- **Reverse if:** the ablation shows mutations alone match the full pipeline, in which case Nemotron's role shrinks to planning examples and families, and we say so.

## 2026-10-08: Planner = Ultra, `medium_effort`, structured output, 2 plans per call, never reasoning-off
- **Why:** the first live audit failed because Ultra used the full 16k budget and the generic fallback retried with reasoning off, which ignored the diff. With a change-centred prompt, `medium_effort` + `json_schema` finished in ~2.3k reasoning tokens, found the bug, and cost ~$0.02. Plans vary per sample, so two per call are interleaved.
- **Reverse if:** a held-out PR shows regular effort finding classes that medium misses.

## 2026-10-08: Search metric is cachegrind Ir; wall clock only for finalists
- **Why:** day-1 A/A in Docker gave Ir CV 0.0000% vs wall CV 1.8–4.5%, at ~3.5 s per cachegrind run. It also reproduces the #1082 trade-off (2.06x simple / 0.97x non-simple).
- **Reverse if:** cachegrind won't run inside Sandboxes microVMs. Then search on Sandbox user-CPU time with repeats and keep Ir in the Docker backend.

## 2026-10-08: Two execution backends behind one interface
`ContreeBackend` (Token Factory Sandboxes, contree-sdk 0.3.6) and `DockerBackend` (`--network=none`, rusage as the second clock). Every result records its backend.
- **Why:** Sandboxes beta access has unknown lead time; the project can't block on it.
- **Reverse if:** never. The README states which backend produced each published number.

## 2026-10-08: Audit-first scope; harden mode is a stretch
- **Why:** all three simulated judges called the original plan 2–3x over-scoped and recommended making audit mode the product, with performance findings as the hero.
- Semantic divergences stay, credited as building on differential testing (MUTINY in this hackathon does that).
- **Reverse if:** the audit is done and polished by Oct 21.

## 2026-10-08: Breakwater chosen over Last Exit
- **Why (user's call):** Breakwater has no competing entry, ground truth that is known to exist (verified today), and lower statistical and budget risk.
- **Known weaknesses to answer with data:**
  - the NVIDIA hook is weaker → address with tiering + a measured Lightning-vs-Ultra adversary comparison;
  - Hypothesis alone may catch some cases → the ghostwriter baseline is mandatory.
- Research notes are kept private (gitignored `research/`).

## 2026-10-08: Stack
- Python 3.12, uv, hatchling. Apache-2.0.
- The `openai` SDK against Token Factory's OpenAI-compatible API, not LiteLLM: LiteLLM's `nebius/` prefix still defaults to the old AI Studio URL.
- contree-sdk pinned to the 0.3.6 API; the GitHub README describes unreleased 0.4.
- GEPA deferred with harden mode; pin 0.1.4 if it comes back.
