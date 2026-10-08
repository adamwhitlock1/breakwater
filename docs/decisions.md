# Decision log

Newest first. One entry per decision: what, why, what would reverse it.

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
