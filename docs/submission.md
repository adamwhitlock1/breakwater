# Devpost submission: copy-paste answers

Drafted Oct 29 from the README, `docs/backtest.md`, `docs/feedback-log.md` and the cost ledger. Every number here is also in the README or the committed artifacts, except the ledger totals, which come from the local `artifacts/ledger.jsonl` files (not committed; say "about"). **[YOU]** marks a field only you can answer. Ratings are suggestions with the reason attached; change them to your own view.

Form: https://nebiusglobalaihackathon.devpost.com/ → "Enter a submission". Deadline **Fri Oct 30, 10:00 PT** (17:00 UTC). Submissions lock at the deadline: don't push to the repo or edit the video after it.

## Checklist, in order

Checked Oct 29 evening: 89 tests pass, ruff clean, no keys in any commit on any branch, the site builds 53 pages with no broken links, and the judge box runs in the browser.

1. [ ] **Land this branch on `main`** and push. Nothing after Oct 25 has been pushed.
2. [ ] **Record the video** from [demo-script.md](demo-script.md): under 3:00, say "Nebius Token Factory", "Sandboxes" and the Nemotron model names aloud, and no third-party music. Upload it to YouTube as **Public**, not Unlisted. Allow 2–3 h in total, and upload early.
3. [ ] **Make the repo public:** `gh repo edit adamwhitlock1/breakwater --visibility public --accept-visibility-change-consequences`. Check that the Apache-2.0 badge shows in About.
4. [ ] **Turn on Pages and deploy:** `gh api -X POST repos/adamwhitlock1/breakwater/pages -f build_type=workflow`, then `gh workflow run report`. Open https://adamwhitlock1.github.io/breakwater/ in a private window and click Start on "Try it".
5. [ ] **Set the repo homepage** to the Pages URL: `gh repo edit adamwhitlock1/breakwater --homepage https://adamwhitlock1.github.io/breakwater/`.
6. [ ] **Put the video link in the README** (the `Video: [x]` line) and push. This is the last push before the deadline.
7. [ ] **Devpost:** create the project, paste the answers below, fill in the [YOU] fields, add the video and both URLs, and pick "Coding and agentic engineering". Submit before **10:00 PT Fri**, ideally tonight.
8. [ ] **After submitting:** no pushes and no video edits. Keep Pages up through judging (Devpost lists Dec 9–23) and winners (Jan 25).

## Project page

**Name:** Breakwater

**Tagline (≤200 chars):** A red team for "faster" pull requests: a Nemotron adversary in Nebius Token Factory Sandboxes hunts for the inputs where the speedup reverses or the behaviour silently changes.

**Built with:** python, nvidia-nemotron, nemotron-3-ultra, nemotron-3.5-lightning, nemotron-3-super, nebius-token-factory, token-factory-sandboxes, hypothesis, valgrind, cachegrind, pyodide, github-actions, docker, uv

**Video URL:** [YOU] the public YouTube link

**Try it out links:** https://github.com/adamwhitlock1/breakwater and https://adamwhitlock1.github.io/breakwater/ (live once Pages is enabled)

### About the project (markdown)

```markdown
## Inspiration
AI-written optimisation PRs are now routine, and a benchmark only tests the inputs someone thought of. In 2026, pypa/packaging (the version parser inside pip) merged a run of performance PRs. Several of them quietly changed behaviour: one accepted `"1. 0"` and Arabic-Indic digits as versions, one broke `SpecifierSet` equality, and one made old pickles fail to load. Every one of them passed its tests and benchmarks. We wanted a reviewer that treats the benchmark as the suspect.

## What it does
Breakwater audits a "faster" change before it merges. You give it a repo with base and head refs, or add the GitHub Action. A Nemotron adversary reads the diff, works out which assumptions the fast path relies on, and writes attacks to break them. Every line of code it writes runs in a Nebius Token Factory Sandboxes microVM. You get:
- a verdict: `BLOCK`, `REVIEW` or `PASS`;
- minimal counterexamples, each as a ready-to-commit pytest that is verified to pass on base and fail on head;
- per-family slowdown measurements from deterministic instruction counts (cachegrind Ir);
- a bill by model tier, with the image UUID behind every number.

What it found:
- **Merged AI-written speedups:** 4 of 10 Codeflash-bot PRs change behaviour, 3 of them adjudicated likely-bug. One, "Speed up `ObjectComparer.is_same_object` by 109%" in json_repair, does up to 363× the instructions on same-sized JSON objects that differ by one key. The no-LLM baselines found nothing in these repos.
- **pip's version parser:** all 9 documented regressions in 29 audited packaging PRs were caught from the parent commit, with no hint of which bug exists. The best no-LLM baseline caught 7. A re-run on Sandboxes caught all 9 again.

## How we built it
- **Nemotron 3 Ultra** (Token Factory, reasoning on, `medium_effort`) reads the diff white-box. It traces the old code, then plans attacks that each predict a base/head difference. It also plans slowdown families and adjudicates each finding as likely-bug, intended or needs-human. A vote counts only if its quoted evidence is found verbatim in the PR.
- **Nemotron 3.5 Lightning** (reasoning off) writes the high-volume part: Hypothesis strategies and input generators.
- **Nemotron 3 Super** writes variants of the slowest perf families.
- **Token Factory Sandboxes** runs all of it. Base and head are installed into one kept image, and every probe, strategy, generator and cachegrind run executes in a microVM branched from it, with networking removed. Deterministic probes compare output, exception type, dunders and cross-version pickles outside both processes.
- A static report site (with an in-browser judge box running four real versions of `packaging`), a live audit page with replay, and a GitHub Action that posts one PR comment.

## Challenges we ran into
- Getting Ultra to plan attacks that predict a difference, rather than generic fuzzing ideas. Planner v3, which must trace the old code first, took productive attacks from 0/15 to 7/15 on a plan-only eval.
- Structured output that was schema-valid but empty, or that ran to the token cap. Pinning array bounds and keeping each call to 8 items or fewer fixed it.
- Measuring speed without noise. CPU time varied by about 10% between identical runs, even inside a microVM, so we measure cachegrind instruction counts, which are deterministic on a given image.
- Honest provenance: the same family measured 4.5× on arm64 Docker and 6.5× on the x86_64 microVM. Every number now names its backend and image.

## Accomplishments that we're proud of
- Real regressions in pip's version parser caught from the parent commit, on two backends.
- A 363× complexity regression in a merged "109% faster" AI PR.
- Every published number can be reproduced from a recorded image UUID and seed. Every finding ships with a verified regression test.
- Honest baselines that show what the model adds. Our limitations are published.

## What we learned
Lightning executes and Ultra reasons. In our ledger, Lightning made about 79% of the Token Factory calls for about 1% of the spend, and Ultra's planning and adjudication were the rest. Reasoning controls via `chat_template_kwargs` matter: `medium_effort` halved Ultra's reasoning tokens on the planner and kept its quality. An adjudicator must quote its evidence, and its label still varies between runs on borderline classes, so a split vote becomes needs-human.

## What's next
- Audit open PRs before they merge.
- Cite the public spec (PEP 440, project docs) in adjudication to settle the borderline "intended" labels.
- Weight slowdowns by real-world input frequency.
- Add wall-clock confirmation of finalists.
```

## Custom questions

| Field | Answer |
|---|---|
| Submitter Type | [YOU] probably Individual |
| Organization Name | [YOU] `N/A` if none |
| Country of Residence | [YOU] |
| Canada province | [YOU] `N/A` unless Canada |
| Track | **Coding and agentic engineering** |
| New or existing prior to Aug 26, 2026 | **New** (first commit Oct 8, 2026) |
| If existing, what changed | leave blank |
| Public repo URL | https://github.com/adamwhitlock1/breakwater (must be public before you submit) |
| Demo URL | https://adamwhitlock1.github.io/breakwater/ (check it loads first) |
| Did you use Tavily? | **No.** Tavily is only a key in `.env.example`; nothing calls its API, so it doesn't qualify |
| Builders & Brews city | [YOU] only if you attended one (the roadmap mentions SF Oct 9 / LA Oct 13) |
| Age / Employee checkboxes | [YOU] |
| Level of learning | [YOU] |
| AI value for your career | [YOU] |

**Which model(s) did you use, and why did you choose that size/variant?**

> Three Nemotron tiers on Nebius Token Factory, each matched to the job. Nemotron 3 Ultra (550B-A55B), with reasoning on at `medium_effort`, does the parts where a wrong answer is expensive. It does white-box attack planning (reading a diff and the module, then predicting where base and head differ), plans slowdown families, and adjudicates findings with quoted evidence. Nemotron 3.5 Lightning, with reasoning off, does the volume work: Hypothesis strategies and input generators, many per attack. Nemotron 3 Super (120B-A12B) writes one-aspect variants of the slowest perf families, where it needs more than Lightning but doesn't need Ultra's planning. In our cost ledger, Lightning made about 1,580 of roughly 2,000 Token Factory calls for $0.16. Ultra made about 370 calls and accounted for about 99% of the roughly $15.6 total. That split is the point: cheap tokens for breadth, expensive reasoning only where it decides the outcome.

**How would you rate Nemotron's output quality for your use case? (1–10)**

> Suggested 8. Ultra's white-box reasoning is the reason the pipeline works. It found the Unicode-digit and `SpecifierSet`-equality bugs in pip's version parser that no baseline found, and it found behaviour changes in merged AI speedups where the no-LLM baselines found nothing. Planner v3 raised productive attacks on a plan-only eval from 0/15 to 7/15, once each attack had to predict a difference and the planner had to trace the old code first. Lightning wrote valid, runnable Hypothesis strategies at high volume with reasoning off. What fell short: (1) with a tight budget and plain reasoning, Ultra sometimes reasoned for the whole budget without answering; `medium_effort` fixed it. (2) On ~8k-token prompts with the instruction first, some samples answered a different task; putting the instruction last fixed it. (3) Adjudication labels on borderline "intended vs bug" classes vary between runs, so we require a strict majority and verbatim quotes.

**Did you fine-tune, prompt-engineer, or use Nemotron out of the box?**

> Out of the box with prompt engineering and structure, no fine-tuning. Every call sets reasoning explicitly through `chat_template_kwargs` (on with `medium_effort` for Ultra, off for Lightning) and is logged to a per-tier cost ledger. Planning and adjudication use strict `json_schema` output with pinned array bounds. The planner (v3) must trace the old code first and state, for each attack, the base/head difference it predicts; 3 samples are merged. Adjudication takes 3 votes by strict majority, and a vote only counts if its quoted evidence appears verbatim in the PR. Deterministic facts (exception relations, base/head outputs) are computed in the sandbox and never overridden by the model. We tuned prompts on OpenRouter's free Nemotron routes and published only Token Factory runs.

**How did Nemotron's performance compare to other models you've used for similar tasks?**

> We didn't run another vendor's model in this pipeline, so we won't claim a head-to-head. The comparisons we measured are against no-LLM baselines and across Nemotron tiers. On 29 pip version-parser PRs, the full Nemotron pipeline caught 9/9 documented regressions, against 7/9 for hostile mutations of the PR's own test strings, 2/9 for plain Hypothesis and 0/9 for the PR's tests and benchmarks. On 10 merged AI-written speedups, the baselines found nothing and Nemotron found 4 behaviour changes and a 363× complexity regression. Across tiers, Lightning was the clear choice for volume (reasoning off, about 1% of spend), and Ultra was needed for planning: Ultra's planned example inputs alone caught 6/9. We also ran the same Nemotron models through another host during development. One prompt-layout issue (instruction-first on long prompts) appeared only on Token Factory.

**Which Nebius platform capabilities were most valuable to your project and how?**

> Two capabilities. Token Factory inference: an OpenAI-compatible API to all three Nemotron tiers, reasoning controls per call, strict `json_schema` output, and generous serverless limits (600 RPM / 400k TPM headers; 40 parallel calls with 0 errors, p50 0.9 s). A 29-PR backtest of about 1,500 calls finished in about two hours with one transient error. Token Factory Sandboxes: the security boundary for LLM-written code, and the reproducibility story. Base and head are installed once into a kept image (content-addressed by tag), and every strategy, probe and cachegrind measurement runs in a microVM branched from it, under `unshare -n`. Each run reports CPU, memory and cost, and every published number cites the image UUID that reproduces it. The demo audit made 358 microVM runs in 415 s at up to 24 concurrent. The Codeflash and packaging campaigns ran about 70 minutes at 24 in flight, with 6 transient SDK errors, all recovered on the first retry. cachegrind works inside the microVM, so measurements are deterministic on a given image. No GPU instances: everything ran on serverless Token Factory.

**How likely are you to recommend running Nemotron on Nebius to other developers? (1–10)**

> Suggested 8. The tier lineup on one API with real reasoning controls let us put cheap tokens where volume matters and Ultra where reasoning matters. Our whole project, including a 29-PR backtest and two Sandboxes campaigns, cost about $15.6 of credit. Sandboxes worked on the first try once access arrived, and it is the right primitive for coding agents. What holds it back from a 10 is discoverability: the reasoning-control behaviour, the `n` ≤ 3 cap, the SDK output cap and the networking switch all took experiments or source-reading to find.

**How would you rate your experience running Nemotron inference on Nebius compared to previous environments? (1–10)**

> Suggested 8. Fast, stable and cheap for what we ran: no rate-limit errors at our concurrency, one transient connection error in about 1,500 calls, and predictable timeouts in Sandboxes (exit −1 with `timed_out`, not an exception). We lost time to undocumented behaviour. When reasoning hits `max_tokens`, raw reasoning text is returned in `content` with `finish_reason=length`, so a client can mistake half-finished reasoning for the answer. The contree-sdk README documents an unreleased version. The SDK's default output cap is 64 KiB while the docs say 1 MiB.

**What additional features or improvements would have made the Nemotron on Nebius experience more effective?**

> 1. When a reasoning model hits `max_tokens` mid-reasoning, return empty `content` (keep the text in `reasoning_content`), or document the current behaviour prominently.
> 2. A short "reasoning controls for Nemotron" table: `chat_template_kwargs` values per model, what `reasoning_effort` does (it seemed to have no clear effect), and suggested budgets per effort level.
> 3. Structured-output notes: constrained decoding can return a schema-valid empty array, so recommend `minItems`. Say whether whitespace between JSON tokens is constrained.
> 4. Document the `n` ≤ 3 cap for non-dedicated models next to the parameter.
> 5. contree-sdk: pin the README to the released version (it documents 0.4.0 while PyPI has 0.3.6). Expose run resources publicly (today only via `result._raw`) with documented units. Make the 64 KiB default output cap match the documented 1 MiB, and name the 10 MiB maximum in the error. Expose the networking switch in 0.3.x. Apply an image's preserved env to `command` runs, not only `shell` runs. Add an option to tag only on success.
> 6. Sandboxes docs: state the microVM CPU architecture and model (x86_64 AMD EPYC here; instruction counts differ from arm64). Say what the per-run `cost` is priced on. List which SDK exceptions are safe to retry, or add a `retry_policy`.
> 7. A way to list kept images by tag prefix, for housekeeping within the 180-day retention.

**What do you most hope to see from the Nemotron team next?**

> Stable, documented reasoning-effort levels across all tiers, with budget guidance per level, plus a guarantee that truncated reasoning never leaks into `content`. Better long-context instruction following, so a model honours the task even when ~8k tokens of code follow it. More consistent judgement on borderline classification across samples, which would make Ultra an even better adjudicator. And a smaller Nemotron tuned for code generation at Lightning's price, for writing property-based tests and input generators.

**Which AI tools have you leveraged while working on this project?**

> [YOU] confirm. Suggested: Claude Code (Anthropic) for pair-programming, code review and docs. NVIDIA Nemotron 3 Ultra, 3.5 Lightning and 3 Super on Nebius Token Factory inside the product itself, plus OpenRouter's free Nemotron routes for development-time prompt tuning only.
