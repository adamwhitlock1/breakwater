# Breakwater product spec (v0, 2026-10-08)

## One-liner
Breakwater audits AI-written "faster" pull requests. A Nemotron adversary in Nebius Token Factory Sandboxes hunts for the real-world input family where the speedup reverses or behavior silently changes, and two clocks catch timing hacks.

## User
The reviewer or maintainer of a hot-path Python library with a "faster" PR open, often AI-generated. First named example: pypa/packaging, the version parser vendored into pip. Secondary: teams merging bot optimization PRs (Codeflash), and RL/eval teams who need performance rewards that resist gaming.

## Inputs
- Repo URL, base ref and head ref (or a PR URL)
- Target symbol(s), e.g. `packaging.version:Version.__init__`. Inferred from the diff when omitted.
- Optional benign corpus (default: the repo's own benchmark samples)
- Budget cap in dollars (default $0.50 per audit)

## Outputs
- **Verdict**
  - `FASTER`: CI lower bound > 1.0 **and** Ir agrees **and** no family's slowdown CI upper bound exceeds 5%.
  - `INCONCLUSIVE`: the clocks disagree, or the result sits inside the A/A floor.
  - `BLOCK`: a probe divergence labelled likely-bug.
- **Per-family table:** Ir ratio, wall ratio with 95% CI, complexity slope, real-corpus-weighted speedup next to the worst family.
- **Counterexample cards:** minimal input, base vs head behavior, probe type, adjudication label, and a ready-to-commit pytest.
- **Receipt:** dollars by Nemotron tier and Sandbox cost, wall time, and the image UUID behind every number.
- **Formats:** JSON (machine), Markdown (PR comment), static HTML report.

## Pipeline
1. **Build** an image per ref: repo at ref + deps + harness. Cached by ref.
2. **Probe** (deterministic, no LLM). P1 output, P2 exception type, P3 dunders, P4 cross-version state (pickle, including after comparison/hash), P5 non-mutation, P6 peak RSS, P7 hash-seed determinism, P8 two-clock residual.
3. **Plan.** Ultra, reasoning on, reads diff + module (+ Tavily recon facts) → ranked hypotheses as JSON.
4. **Generate.** Lightning, reasoning off, writes N Hypothesis strategies per hypothesis in a restricted DSL. Each runs as a differential `@given` test in its own sandbox.
5. **Search.** Hypothesis shrinks; perf attacks use `target()` on CPU-time ratio and are confirmed by Ir over size ladders.
6. **Archive.** Dedupe by shrunk-example signature; key by (probe × family).
7. **Adjudicate.** Ultra labels each divergence (may abstain). Deterministic facts are never overridden.
8. **Confirm.** Finalist timing on a dedicated Serverless Job (paired, interleaved, bootstrap CI, A/A floor).

## Model tiering (Token Factory)
| Tier | Model | Reasoning | Calls |
|---|---|---|---|
| Volume | `nvidia/Nemotron-3_5-Lightning` | off | strategy writing, summaries, test boilerplate |
| Proposer | `nvidia/nemotron-3-super-120b-a12b` | on (`low_effort` if honoured) | contract drafting for new targets; stretch: patches |
| Reasoning | `nvidia/Nemotron-3-Ultra-550b-a55b` | on (`medium_effort` if honoured) | white-box planning, adjudication |

Every call sets `chat_template_kwargs` explicitly and is logged to the cost ledger.

## Backtest corpus
- **pypa/packaging 2026 perf PRs (~14).** Ground truth: #1082 (+#1155), #1108 (+#1109), #1116 (+#1162/#1163). Post-cutoff controls: #1371, #1429.
- **Codeflash bot PRs:** 8–10 sampled from `artifacts/corpus/codeflash_prs.json` (pure Python, testable on 3.12). _To be selected._
- **Sealed real-version corpus:** ~1M versions/specifiers from PyPI metadata. Used only for weighting and final confirmation.

## Headline claims we're aiming for (fill with real numbers; report nulls honestly)
- "Breakwater caught K of 3 documented packaging regressions before merge, for $X each." Baselines: tests+benchmarks 0/3; Hypothesis ghostwriter ?/3; Ultra-reads-diff ?/3.
- "N of M merged AI speedups reverse on a real input family or change behavior."
- "Lightning-written strategies find X divergence classes per dollar vs Ultra-written Y." This tests NVIDIA's "Lightning executes" claim with data.

## Out of scope
- GPU kernels
- Proving equivalence. We say "survived N probes / M rounds".
- Non-Python targets
- Upstream bug reports without human review and team approval

## Non-negotiables
- No API keys in the repo.
- Every number is reproducible from a recorded image + seed.
- Untrusted code only runs through a backend (Sandboxes or Docker with `--network=none`), never in the orchestrator process.
