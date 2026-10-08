# Day-1 checklist (Thu 2026-10-08)

Goal: retire the unknowns that could reshape the plan before writing product code. Tick items as they land and paste results under **Findings**. Owner is whoever picks it up; put your initials next to the box.

## A. Accounts and access (humans only, do first; some have lead time)

- [ ] **Request Token Factory Sandboxes beta access**: https://tokenfactory.nebius.com/sandboxes/about. Lead time is unknown and other teams waited. Until granted, every Sandboxes call returns 403. Mention the hackathon and the use case (isolated, branchable execution of LLM-written test code, per-run CPU metrics).
- [ ] Create a Token Factory API key; put it in `.env` as `NEBIUS_API_KEY`.
- [ ] Find the Nebius **project ID** (console) and set `NEBIUS_PROJECT_ID`. Sandboxes sends it as a `Project` header.
- [ ] Redeem **$25** credit: code `NEBIUS-DEVPOST-GLOBAL26` at https://nebius.com/promo-code. Each teammate does this on their own account.
- [ ] Join the **Builder Program** (https://dev.nebius.com/builders) for another $25 of Token Factory credit and $25 of Tavily credit.
- [ ] Tavily key (promo `BBDEVPOST`) → `TAVILY_API_KEY`.
- [ ] Nebius **AI Cloud** account for Serverless Jobs. Signup charges a $25 deposit that becomes balance. Not needed until week 2; do it early so billing issues surface.
- [ ] Set a team spend ceiling. Planned total: ~$35–40 Token Factory + <$10 Serverless + ~$24 for a live endpoint during judging (optional).
- [ ] Create the public GitHub repo with Apache-2.0 visible in the About section. The repo is initialised locally; nothing has been pushed.
- [ ] Decide on **City Winner** attendance: San Francisco **Fri Oct 9** 4–10pm or LA **Tue Oct 13**. In-person attendance is likely required; AI Cloud credits are reportedly handed out at events.

## B. Ground truth and measurement (no keys needed)

- [x] Reproduce the packaging regressions: `uv run python scripts/day1/ground_truth.py` → `artifacts/day1/ground_truth.json`.
- [x] Cachegrind Ir as the search metric: `ir_probe.py` in the harness container → `artifacts/day1/ir_probe.json`.
- [x] Backtest corpus of merged Codeflash bot PRs: `scripts/day1/codeflash_corpus.sh` → `artifacts/corpus/codeflash_prs.json`.
- [ ] Download a real-version corpus for the sealed set. Candidate: pypi-json-data; check its size and license, and sample ~1M versions and specifiers. Note the source and license in `docs/decisions.md`.
- [ ] Pick 8–10 Codeflash PRs that are pure-Python, have tests, and run on Python 3.12. Record them in `docs/spec.md` → Backtest corpus.

## C. Token Factory behaviour (needs `NEBIUS_API_KEY`)

Run `uv run python scripts/day1/check_token_factory.py --burst 40 --memorization` (~$0.10). It answers:

- [ ] Exact model IDs and casing (`GET /v1/models`). Set `BREAKWATER_MODEL_*` overrides if they differ.
- [ ] Is `chat_template_kwargs.enable_thinking=false` honoured on all three tiers (reasoning tokens ≈ 0)?
- [ ] Is `reasoning_effort` ignored? Do Ultra `medium_effort` and Super `low_effort` cut tokens?
- [ ] Does `n=4` work on Lightning? (The adversary samples 16 strategies per hypothesis.)
- [ ] Is `service_tier: flex` accepted? (Used for backtest sweeps.)
- [ ] Does `json_schema` structured output parse on each tier? (Hypotheses and adjudication labels depend on it.)
- [ ] Empty content when thinking eats `max_tokens`: reproduced? (`llm.py` retries without thinking.)
- [ ] Rate-limit headers and 40-way burst behaviour: how many 429s?
- [ ] Does `/v1/responses` work? (NeMo Gym's policy server; stretch.)
- [ ] Memorization probe: does Ultra already know what went wrong in #1082 and #1155? If yes, the backtest needs the post-cutoff controls (#1371, #1429) reported separately.

## D. Sandboxes (needs access + `NEBIUS_PROJECT_ID`)

Run `uv run python scripts/day1/check_contree.py`. It answers:

- [ ] Auth works (no 403).
- [ ] Can a `python:3.12-slim` image be pulled, and can valgrind and packaging be installed into a kept, tagged image?
- [ ] Branch fidelity: two branches from one snapshot see identical files. Branch latency.
- [ ] Units of the resource fields (`user_cpu_time`, `max_rss`, ...) and the per-run `cost`.
- [ ] A/A CV of user CPU time inside microVMs.
- [ ] Does cachegrind run inside a microVM, and how slow is it?
- [ ] Execution timeout and concurrency cap (docs say 50 concurrent operations).

## E. Decisions these checks drive

| Decision | Depends on | Default if unknown by Oct 11 |
|---|---|---|
| Search metric: cachegrind Ir vs paired CPU time | D: cachegrind in microVM | Ir in Docker locally, CPU time in Sandboxes |
| Execution backend | D: access granted | Docker backend; keep pressing DevRel |
| Adversary sampling: `n=16` vs parallel calls | C: `n` support | parallel single calls |
| Structured output vs parse-and-retry | C: `json_schema` | parse-and-retry |
| Backtest contamination handling | C: memorization probe | report post-cutoff PRs separately regardless |

## Findings

### B1. Ground truth reproduces (2026-10-08)

| Case | Refs | Result |
|---|---|---|
| #1082 fast path | base 59f183fe, c33a5218, **61967cca**, 4ecd2734, merge ee13ba2c | `61967cca` accepts `"1. 0"` and `"١.٠"` (Arabic-Indic). Every other ref raises `InvalidVersion`. |
| Oversized int (5,000 digits) | base 59f183fe → merge ee13ba2c → #1155 06c6555f | `ValueError` → `InvalidVersion` → `ValueError`. The #1082 merge changed the exception type, and #1155 restored it two months later. |
| #1108 → #1109 | 20f1523c → f59d6ee9 → 9b972011 | `SpecifierSet(">1.0.0,>1.0") == SpecifierSet(">1.0")`: True → **False** (len 2) → True |
| #1116 → #1163 pickle | packaging 26.0 → 26.1 → 26.2 | 26.1 raises `ModuleNotFoundError: packaging._structures`, **but only if the Version was compared or hashed before pickling**. A fresh Version pickles fine. The adversary must learn to set up state, not just pick inputs. |

### B2. Cachegrind instruction count (Ir) in Docker (linux/arm64, Python 3.12)

- **Ir A/A coefficient of variation: 0.0000%** over 5 runs per cell; wall-clock CV is 1.8–4.5%. Ir is a deterministic search signal.
- Cachegrind costs ~3.5 s per run (3,000 parses), so it is affordable inside the search loop.
- #1082 Ir speedup: **2.06x on simple versions, 0.97x on non-simple versions**. Maintainers measured 2.37x / 0.84x wall-clock on their benchmark. The direction matches; the magnitude needs real-corpus weighting.

### B3. Codeflash corpus

178 merged bot PRs across 42 repos outside `codeflash-ai/*`. Top repos: gdsfactory (29), chembench (24), kornia fork (14), roboflow/inference (12), SoniqueBay (12), langflow (11).

### C. Token Factory
_(pending key)_

### D. Sandboxes
_(pending access)_

SDK facts already confirmed from contree-sdk 0.3.6 source:
- `ContreeSync()` reads `NEBIUS_API_KEY` and `NEBIUS_PROJECT_ID`.
- Runs are disposable by default; pass `disposable=False` to keep a snapshot.
- Results carry `ProcessResources` (user/system CPU time, max RSS, involuntary switches, page faults) and a per-run `cost`.
- The GitHub README documents the unreleased 0.4.0 API (a separate `contree_client` package), not 0.3.6. That mismatch goes in the feedback log.
