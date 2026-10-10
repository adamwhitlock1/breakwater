# Breakwater

**A red team for performance pull requests.** Before a "faster" change is merged, a Nemotron adversary running in Nebius Token Factory Sandboxes hunts for the real-world inputs where the speedup reverses or the behavior silently changes. Two clocks catch timing hacks. You get a verdict, minimal counterexamples as ready-to-commit tests, and a cost receipt.

> Status: **pre-alpha, day 1** of the [Nebius x NVIDIA Global AI Hackathon](https://nebiusglobalaihackathon.devpost.com/) (Coding & Agentic Engineering track). Submissions close 2026-10-30. See [docs/roadmap.md](docs/roadmap.md).

## Why

AI-written optimization PRs are now routine, and benchmarks only test the inputs someone thought of. Even careful maintainers get bitten. In 2026, pypa/packaging (the version parser inside pip) merged a string of performance PRs, and several changed behavior:

| PR | Claimed | What actually changed | Fixed by |
|---|---|---|---|
| [#1082](https://github.com/pypa/packaging/pull/1082) fast path for simple versions | ~2x faster parsing | Intermediate commit accepted `"1. 0"` and Arabic-Indic digits; merged version changed the exception type for oversized integers; slower on non-simple versions | review, then [#1155](https://github.com/pypa/packaging/pull/1155) two months later |
| [#1108](https://github.com/pypa/packaging/pull/1108) tuple instead of frozenset | faster `SpecifierSet` | `SpecifierSet(">1.0.0,>1.0") != SpecifierSet(">1.0")` | [#1109](https://github.com/pypa/packaging/pull/1109), same day |
| [#1116](https://github.com/pypa/packaging/pull/1116) overhaul `_cmpkey` | faster comparisons | `Version` objects pickled with 26.0 fail to load in 26.1 | [#1163](https://github.com/pypa/packaging/pull/1163) ([issue #1162](https://github.com/pypa/packaging/issues/1162)) |

All of these reproduce with `scripts/day1/ground_truth.py`. Instruction counts (`scripts/day1/ir_probe.py`) show the #1082 trade-off directly: **2.06x on simple versions, 0.97x on everything else**.

Breakwater's job is to find this class of problem before merge, automatically, for cents.

## How it works (planned)

1. **Images.** Base and candidate refs are built once into Sandboxes snapshots; every number cites the image UUID that reproduces it.
2. **Deterministic probes** (no LLM): output parity, exception-type parity, dunder parity (`==`, `hash`, ordering), cross-version pickle, determinism across hash seeds, memory, and a two-clock check that compares in-process timing with out-of-process CPU accounting the candidate cannot tamper with.
3. **Nemotron adversary.** Nemotron 3 Ultra reads the diff white-box and plans attack hypotheses ("the fast path trusts `int()` to see only ASCII digits"). Nemotron 3.5 Lightning writes many Hypothesis strategies per hypothesis; each runs as a differential test in its own sandbox branch. Hypothesis shrinks failures to minimal counterexamples.
4. **Performance attacks.** Search uses cachegrind instruction counts (deterministic: 0.0000% A/A variation on day 1), across input families and size ladders, to find where a speedup reverses. Finalists are re-timed with paired, interleaved wall-clock runs, bootstrap CIs and a published A/A noise floor.
5. **Verdict.** `FASTER` / `INCONCLUSIVE` / `BLOCK`, with a per-family table, counterexamples as pytest tests, and the bill, posted as a GitHub check and a web report.

## NVIDIA and Nebius usage

| Piece | Used for |
|---|---|
| `nvidia/Nemotron-3_5-Lightning` (Token Factory) | High-volume attack-strategy generation, reasoning off |
| `nvidia/Nemotron-3-Ultra-550b-a55b` (Token Factory) | White-box attack planning; adjudicating divergences (may abstain) |
| `nvidia/nemotron-3-super-120b-a12b` (Token Factory) | Contract drafting for new targets; stretch: candidate patches |
| Token Factory Sandboxes (ConTree) | Isolated, branchable execution of untrusted LLM-written code; per-run CPU/memory/cost |
| Nebius Serverless Jobs | Finalist wall-clock timing on a dedicated VM; resumable campaign runner |
| NeMo Gym (stretch) | Breakwater's verifier as a performance reward that resists timing hacks |

## Quickstart

```bash
uv sync --extra sandboxes          # Python 3.12
cp .env.example .env               # add NEBIUS_API_KEY, NEBIUS_PROJECT_ID, TAVILY_API_KEY
docker build -f docker/harness.Dockerfile -t breakwater-harness .
uv run breakwater doctor
```

For development, set `BREAKWATER_PROVIDER=openrouter` and `OPENROUTER_API_KEY` to run the same Nemotron tiers on OpenRouter's free routes. Published numbers come only from Nebius Token Factory runs; every report records its provider.

Run the deterministic probes on a real regression (pypa/packaging #1082's intermediate commit):

```bash
uv run breakwater probe --target packaging.version:Version \
  --repo https://github.com/pypa/packaging --base 59f183fe90da --head 61967cca278d \
  --input "1.0" --input "1. 0" --input "١.٠"
```

Run the Nemotron adversary on the same change (needs `NEBIUS_API_KEY`; ~cents):

```bash
uv run breakwater audit --target packaging.version:Version \
  --repo https://github.com/pypa/packaging --base 59f183fe90da --head 61967cca278d
```

Add `--live` to watch it run: the audit serves a live page on localhost (attack feed, Nemotron cost by tier, sandbox runs, counterexamples as they land) and writes `report.html` next to `report.json` when it finishes. `breakwater replay <run dir> --speed 4` replays a recorded run, labelled as a replay.

The audit labels each divergence class `likely-bug`, `intended` or `needs-human` (Ultra, 3 votes; a vote counts only if its quoted evidence is found in the PR). The report says BLOCK only for likely bugs. To label a finished backtest and score the labels against its known issues:

```bash
uv run breakwater adjudicate artifacts/backtest/packaging-v2
```

Build the static report (overview + one page per PR: verdict, counterexample cards with labels and quoted evidence, perf ladder charts, receipts). It reads only committed JSON, makes no network requests, and refuses non-Token-Factory inputs unless `--allow-dev`:

```bash
uv run breakwater site --run artifacts/demo/pr1082-61967cca   # writes site/; open site/index.html
```

A manually triggered workflow (`.github/workflows/pages.yml`) builds it from the committed artifacts and publishes it to GitHub Pages.

Day-1 checks (see [docs/day1-checklist.md](docs/day1-checklist.md)):

```bash
uv run python scripts/day1/ground_truth.py          # reproduce the packaging regressions (no keys needed)
docker run --rm -v "$PWD":/work -v bw-cache:/cache breakwater-harness python scripts/day1/ir_probe.py
uv run python scripts/day1/check_token_factory.py   # Token Factory behaviour, ~$0.05
uv run python scripts/day1/check_contree.py         # once Sandboxes access is granted
```

## Repository layout

```
src/breakwater/        package: Nemotron client + cost ledger, execution backends (Sandboxes, Docker)
scripts/day1/          day-1 verification scripts; results land in artifacts/day1/
docker/                local harness image (Python 3.12 + valgrind), the Sandboxes fallback
docs/                  roadmap, day-1 checklist, spec, decisions, risks, demo script, feedback log
```

## License

[Apache-2.0](LICENSE)
