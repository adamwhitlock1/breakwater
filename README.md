# Breakwater

**A red team for performance pull requests.** Breakwater treats a "faster" change's benchmark as the suspect. A Nemotron adversary reads the diff and writes attacks, and every line of code it writes runs in a Nebius Token Factory Sandboxes microVM. The goal is to find the inputs where the speedup reverses or the behaviour silently changes. You get a verdict (`BLOCK` / `REVIEW` / `PASS`), minimal counterexamples as ready-to-commit pytest tests, deterministic instruction-count measurements, and a bill by model tier.

Entry for the [Nebius x NVIDIA Global AI Hackathon](https://nebiusglobalaihackathon.devpost.com/), Coding & Agentic Engineering track. Built Oct 8–30, 2026.

## For judges

| Criterion | Claim | Check it in a minute |
|---|---|---|
| Technological Implementation | Three Nemotron tiers on Token Factory, each with explicit reasoning control, structured output and its own line on the bill. LLM-written code runs only in Sandboxes microVMs branched from a recorded image. Measurement is deterministic (cachegrind Ir). Adjudication must quote its evidence. Regression tests are verified in the sandbox before they're offered | [`llm.py`](src/breakwater/llm.py), [`backends/contree.py`](src/breakwater/backends/contree.py), the receipt on any run page (tier bill, backend, image UUID), [`artifacts/day1/contree.json`](artifacts/day1/contree.json) |
| Design | One command or a GitHub Action gives a verdict, counterexample cards with tests, a report page, a PR comment and a live view. A recorded run can be replayed. The judge box runs four real versions of pip's version parser in your browser | Demo site: index, a PR page, the Codeflash sub-site, "Try it" |
| Potential Impact | 9/9 documented regressions in pip's version parser caught pre-merge, on Docker and again on Sandboxes (best no-LLM baseline 7/9). 4/10 merged AI-written speedups change behaviour (3 adjudicated likely-bug). One does 363× the work on valid input | [`docs/backtest.md`](docs/backtest.md), [`scripts/day1/ground_truth.py`](scripts/day1/ground_truth.py), the Codeflash sub-site |
| Quality of the Idea | Falsify rather than prove: the adversary tries to break the speed and equivalence claims, and honest baselines show what the model adds | [Why](#why) below, "What Nemotron adds" in [`docs/backtest.md`](docs/backtest.md) |
| Track fit | A coding agent that writes, runs and tests code in Token Factory Sandboxes | The live page's sandbox gauge; an image UUID on every number |
| Feedback | Specific entries, each with a reproduction and a suggestion | [`docs/feedback-log.md`](docs/feedback-log.md) |

Demo site: [x] (GitHub Pages, published at submission). Video: [x].

## What it found

**AI-written speedups (Codeflash corpus).** These are ten merged Codeflash-bot "Speed up …" PRs in seven repos. The run was on Token Factory with Sandboxes (`artifacts/backtest/codeflash-v2`, $0.88).
- **json_repair #113**, "Speed up method `ObjectComparer.is_same_object` by 109%". Base returns as soon as two dicts' key sets differ. Head checks only the lengths, then recursively compares values key by key. On same-sized JSON objects that differ by one key, head does **up to 363× the instructions**. Both versions return the same answer. The claimed path does get faster (0.48–0.58×).
- **4 of 10 change behaviour.** Three were adjudicated likely-bug:
  - Math-Interpreter #1 ("by 11%") now tokenises Arabic-Indic digits as numbers. This is the same bug class as packaging #1082.
  - caddy-feeds #4 ("by 17,376%") added an `lru_cache`, so a list argument now raises `TypeError`.
  - patterns #12: a nested list raises `TypeError` instead of `AttributeError`.

  The fourth, rendercv #18, was adjudicated intended.
- **The no-LLM baselines found nothing here.** These repos have few tests to mine, so the Nemotron plan and search did all the finding.

**Human-written speedups (pypa/packaging, the version parser inside pip).** In 2026 it merged a string of performance PRs, and several changed behaviour:

| PR | Claimed | What actually changed | Fixed by |
|---|---|---|---|
| [#1082](https://github.com/pypa/packaging/pull/1082) fast path for simple versions | ~2× faster parsing | Intermediate commit accepted `"1. 0"` and Arabic-Indic digits; merged version changed the exception type for oversized integers; slower on non-simple versions | review, then [#1155](https://github.com/pypa/packaging/pull/1155) two months later |
| [#1108](https://github.com/pypa/packaging/pull/1108) tuple instead of frozenset | faster `SpecifierSet` | `SpecifierSet(">1.0.0,>1.0") != SpecifierSet(">1.0")` | [#1109](https://github.com/pypa/packaging/pull/1109), same day |
| [#1116](https://github.com/pypa/packaging/pull/1116) overhaul `_cmpkey` | faster comparisons | `Version` objects pickled with 26.0 fail to load in 26.1 | [#1163](https://github.com/pypa/packaging/pull/1163) ([issue #1162](https://github.com/pypa/packaging/issues/1162)) |

The backtest covers 28 merged 2026 perf PRs plus #1082's intermediate commit, each audited from its parent commit. Recall on the 9 verified regressions by arm:

| Arm | LLM | Verified (9) |
|---|---|---|
| The PR's own tests and benchmarks | — | 0 (by construction: these PRs merged green) |
| Plain Hypothesis (`st.text()`) | no | 2 |
| Hostile mutations of the PR's own test strings | no | 7 |
| Ultra's planned example inputs only | Ultra | 6 |
| **Breakwater** (plan + Lightning strategies + search + mutations) | Ultra, Lightning | **9** |

- The two issues only the full pipeline caught are #1082's Unicode digits and #1108's equality change.
- The mutations baseline is part of Breakwater. It's reported separately so the model's contribution is visible.
- Adjudication labelled 8 of 10 found known issues likely-bug. The miss is #1082's oversized-int exception: the PR's own tests expect the new exception, and the maintainers later decided otherwise.
- All 30 generated regression tests passed on base and failed on head.
- The worst valid slowdowns were #1030 at 4.52× (names with many underscores and dots) and #1082 at 2.85× (long numeric chunks). Those sizes are adversarial. On simple versions #1082 does its job: 2.06× fewer instructions.

The eight packaging items with known issues or slowdowns were re-run on Sandboxes (`packaging-v4-sandboxes`). All 9/9 known issues were caught again. Where both runs found a class, it has the same base/head facts. Verdict differences between runs trace to the model sampling a different plan or a different adjudication, not to the backend. Full accounting, including every re-run and correction, is in [`docs/backtest.md`](docs/backtest.md).

## Why

AI-written optimization PRs are now routine, and benchmarks only test the inputs someone thought of. A speedup is a claim about a distribution of inputs, and the PR shows you one point in it. Breakwater's adversary sees the diff and attacks the assumptions the fast path relies on, for example "the fast path trusts `int()` to see only ASCII digits". It searches for counterexamples instead of confirming the benchmark.

## How it works

1. **Image.** Base and head are installed into one image, one venv per side, with a content-addressed tag. On Sandboxes it's a kept image whose UUID every number cites. Only the image build has network access: every other run executes under `unshare -n`.
2. **Deterministic probes (no LLM).** Base and head run in separate processes on identical serialized inputs, and the results are compared outside both:
   - P1: output parity.
   - P2: exception-type parity.
   - P3: dunder parity (`==`, `hash`, ordering).
   - P4: cross-version pickle, with warmed state.

   Each probe has fresh-object and round-trip controls so pre-existing bugs aren't blamed on the PR.
3. **Semantic adversary.** Nemotron 3 Ultra reads the diff white-box. It traces the old code first, then plans attacks, each predicting a base/head difference (3 samples, medium effort, JSON schema). Nemotron 3.5 Lightning writes Hypothesis strategies per attack with reasoning off. Each strategy runs in the sandbox against persistent base and head workers, alongside deterministic hostile mutations. Hypothesis shrinks each finding, and findings are grouped into classes by signature.
4. **Performance adversary.** Ultra plans slowdown families as `make(n)` input generators, and Nemotron 3 Super writes variants of the slowest ones. Families are screened, then measured on size ladders (n=2…4096) with cachegrind instruction counts. Start-up and parsing cancel out: per-call cost is (Ir at 2R − Ir at R) / (R × inputs), with a linearity check. Only sizes where base accepts most inputs count. Ir is deterministic on a given image (0.0000% A/A variation).
5. **Adjudication.** Ultra labels each class `likely-bug`, `intended` or `needs-human` from 3 samples, by strict majority. A vote counts only if its quoted evidence is found verbatim in the PR material, and exception relations are computed in the sandbox. Adjudication never drops or edits a finding.
6. **Tests and verdict.** Each class becomes a pytest that pins base behaviour. A test is offered only if it passes on base and fails on head. The verdict is:
   - `BLOCK` on a likely bug, or on a complexity regression on mostly valid inputs.
   - `REVIEW` on an unsettled class, or on a valid family at least 1.25× slower.
   - `PASS` otherwise.

## NVIDIA and Nebius usage

| Piece | Used for |
|---|---|
| `nvidia/Nemotron-3-Ultra-550b-a55b` (Token Factory) | White-box attack planning, perf family planning, adjudication with abstain; reasoning on, `medium_effort` |
| `nvidia/Nemotron-3_5-Lightning` (Token Factory) | High-volume strategy and generator writing; reasoning off |
| `nvidia/nemotron-3-super-120b-a12b` (Token Factory) | One-aspect variants of the slowest perf families |
| Token Factory Sandboxes (ConTree, contree-sdk 0.3.6) | Kept pair images; every probe, strategy, generator and cachegrind run in a microVM; per-run CPU, memory and nominal cost on the receipt |

Reasoning is set per call through `chat_template_kwargs`, and every call is written to a cost ledger by tier and provider (`breakwater bill`). Published runs used Token Factory only:

| Run | Nemotron cost |
|---|---|
| Demo audit of #1082's intermediate commit | $0.18 |
| Codeflash corpus, 10 PRs | $0.88 |
| Packaging subset, 8 items | $1.12 |
| Full packaging backtest, 29 items (Docker backend) | $1.58, plus $1.39 for adjudication |

Sandboxes was free during the beta. The demo run's nominal Sandboxes cost was $11.92 for 358 microVM runs.

## Quickstart

```bash
uv sync --extra sandboxes          # Python 3.12
cp .env.example .env               # NEBIUS_API_KEY, NEBIUS_PROJECT_ID
uv run breakwater doctor           # keys, Sandboxes auth and limits, Docker
```

With `NEBIUS_API_KEY` and `NEBIUS_PROJECT_ID` set, untrusted code runs in Sandboxes. Without them it falls back to a local Docker image, which needs `docker build -f docker/harness.Dockerfile -t breakwater-harness .`. Override with `--backend contree|docker`.

**No keys needed.** Reproduce the packaging regressions, and build the report site from the committed artifacts:

```bash
uv run python scripts/day1/ground_truth.py
uv run breakwater site --run artifacts/demo/pr1082-61967cca --run artifacts/demo/pr1082-61967cca-sandboxes
```

The site is written to `site/`; open `site/index.html`. It makes no network requests except the judge box's Pyodide load from jsDelivr, which happens only after you click Start.

**Replay the recorded Sandboxes demo audit** in a local live page:

```bash
uv run breakwater replay artifacts/demo/pr1082-61967cca-sandboxes --speed 4
```

**Run the deterministic probes** on #1082's intermediate commit. There are no model calls, so only the backend is needed:

```bash
uv run breakwater probe --target packaging.version:Version \
  --repo https://github.com/pypa/packaging --base 59f183fe90da --head 61967cca278d \
  --input "1.0" --input "1. 0" --input "١.٠"
```

**Run a full audit.** This needs a Token Factory key and costs about $0.20. `--live` serves the live page on localhost:

```bash
uv run breakwater audit --target packaging.version:Version \
  --repo https://github.com/pypa/packaging --base 59f183fe90da --head 61967cca278d --live --open
```

It writes `report.json`, `report.md`, `report.html`, `events.jsonl` and `test_regressions.py` under `artifacts/runs/<run_id>/`.

**Other commands:**
- `breakwater backtest` runs the arms over a corpus (`corpus/packaging.json`, `corpus/codeflash.json`).
- `breakwater adjudicate <backtest-dir>` labels a backtest's classes.
- `breakwater regress` generates verified tests for a backtest.
- `breakwater bill` shows spend by tier.
- `breakwater comment <run>` and `breakwater verdict <run>` render a run as a PR comment and print its verdict.

**GitHub Action.** `uses: adamwhitlock1/breakwater@main` audits each pull request against its merge base. It posts one comment that is updated on every push, uploads the report, and fails the check on BLOCK. Pass `nebius-project-id` to run the untrusted code in Sandboxes. Setup and limits are in [docs/github-action.md](docs/github-action.md).

For development, `BREAKWATER_PROVIDER=openrouter` runs the same Nemotron tiers on OpenRouter's free routes. The site refuses non-Token-Factory artifacts unless you pass `--allow-dev`.

## Repository layout

```
src/breakwater/          probes, adversary, mutations, perf, adjudication, regression tests, CLI
src/breakwater/backends/ Sandboxes (ConTree) and Docker execution backends
src/breakwater/harness/  the worker that runs inside the sandbox
src/breakwater/site/     static report builder (stdlib only)
corpus/                  packaging and Codeflash corpora
artifacts/               published runs, backtests, adjudications, tests (all Token Factory)
scripts/                 corpus builders, backend comparison, day-1 checks, judge-box bundle
docs/                    backtest write-up, decisions, roadmap, feedback log
```

## Limitations

- **Falsifies, doesn't prove.** "No divergence found" means these probes and this search budget found none.
- **Differential by design.** A bug present on both base and head is invisible.
- **Instruction counts, not wall time.** Ir is deterministic on a given image but differs across CPU architectures. The same #1030 family measured 4.52× on arm64 Docker and 6.50× on the x86_64 microVM, with the same verdict. Wall-clock confidence intervals aren't implemented.
- **Adversarial sizes.** Slowdown ratios are measured on the families the adversary built, not weighted by real-world input frequency.
- **Adjudication varies between runs on borderline classes.** A class labelled `intended` in one run can be `likely-bug` in another. Every label shows its votes and quoted evidence, and split votes become `needs-human`.
- **Not implemented:** an in-process vs out-of-process timing cross-check, input-mutation and hash-seed probes, and memory columns.
- **Sandbox networking.** contree-sdk 0.3.6 has no option to disable networking. Breakwater runs every non-build run under `unshare -n`, verified to break name resolution and connections. The Docker backend uses `--network=none`.
- **Scope.** Python 3.12 targets with JSON-serialisable arguments.

## License

[Apache-2.0](LICENSE)
