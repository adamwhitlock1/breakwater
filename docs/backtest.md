# Backtest: pypa/packaging 2026 perf PRs (v2, 2026-10-08)

Full results: `artifacts/backtest/packaging-v2/` (`table.md`, `results.json`, one JSON per PR). Corpus: `corpus/packaging.json`, 28 merged library perf PRs plus #1082's intermediate commit. The base of each item is the parent of its merge commit. Backend: Docker. Total Nemotron cost: **$2.69** for the main run plus **$0.16** for two re-runs.

## Known regressions caught

| Arm | LLM | Verified (9) | Candidates (3) | PRs with any divergence |
|---|---|---|---|---|
| PR's own tests + benchmarks | — | 0 (by construction: these PRs merged green) | 0 | 0 |
| `hypothesis`: `st.text()` search | no | 2 | 0 | 4/29 |
| `mutations`: the PR's own test literals + hostile mutations | no | 7 | 2 | 14/29 |
| `llm-plan`: Ultra's example inputs only | Ultra | 5 | 1 | 10/29 |
| **`breakwater`**: plan + Lightning strategies + search + mutations + test literals | Ultra, Lightning | **9** | **2** | 15/29 |

Per issue:

| Item | Issue | hypothesis | mutations | llm-plan | breakwater |
|---|---|---|---|---|---|
| #1030 | non-ASCII names no longer lowercased (**found by Breakwater in v1**, fixed silently by #1064) | ✓ | ✓ | ✓ | ✓ |
| #1082 | oversized-int exception type (fixed #1155) | | ✓ | | ✓ |
| #1082 intermediate | Unicode digits accepted | | | ✓ | ✓ |
| #1082 intermediate | inner whitespace accepted | | ✓ | ✓ | ✓ |
| #1082 intermediate | oversized-int exception type | | ✓ | | ✓ |
| #1108 | equivalent specifiers no longer equal (fixed #1109) | | | | ✓ |
| #1108 | `str` / `len` changed (fixed #1109) | | ✓ | | ✓ |
| #1108 | 26.0 pickles break comparison in 26.1 (fixed in 26.2) | ✓ | ✓ | ✓ | ✓ |
| #1116 | 26.0 pickles fail to load in 26.1 (fixed #1163) | | ✓ | ✓ | ✓ |
| #1147 | Marker pickles (candidate, linked fix #1171) | | ✓ | ✓ | ✓ |
| #1320 | Requirement pickles (candidate, linked fix #1171) | | ✓ | | ✓ |
| #1118 | hash cache when copying (candidate, linked fix #1242) | | | | |

## What Nemotron adds (honest reading)

- **Two verified issues are caught only by the full pipeline:** #1082's Unicode digits (only Ultra's examples contained a non-ASCII digit to mutate) and #1108's equality change (found by the focused relations pass over planner seeds and their equivalents).
- **The deterministic layer does most of the work on this corpus.** Hostile mutations of the project's own test strings catch 7/9. That is a product feature, not an embarrassment: Breakwater runs both, and the LLM extends coverage where the project's tests have no hostile examples to start from.
- **Circularity note:** #1030 entered the ground truth because Breakwater found it in v1. Excluding it, the full pipeline catches 8/8 pre-existing verified issues, and the no-LLM mutations arm 6/8.
- **Contamination:** Ultra said it has no specific memory of #1082 or #1155. Of the 9 PRs merged after Ultra's release, Breakwater flagged behavior changes in #1236 (exception types), #1258, #1320 (pickles) and #1429; none of them has a documented fix yet, so none counts toward recall.

## Performance (worst valid input family per PR, head/base Ir per call)

| PR | Worst valid family | Ratio | Corroboration |
|---|---|---|---|
| #1030 | names with many underscores and dots | **4.52x** | #1064's author: "#1030 [was] a performance regression for Python 3.12 and 3.13" (our image is 3.12) |
| #1082 | versions with long numeric chunks | 2.85x | adversarial sizes; realistic sizes 3–14% (see findings) |
| #1082 intermediate | versions with an epoch | 1.91x | |
| #1064 | names with many underscores and dots | 1.10x | |
| #1236 | tiny tags | 1.09x | |

## Corrections after the main run

- **#1111** was re-run: the breakwater arm had failed on a transient Token Factory `APIConnectionError`. Clean re-run: no divergences ($0.12).
- **#1258** was re-run: the breakwater arm had crashed on a harness bug. The worker rendered an observed attribute outside its guard, and packaging's own `__hash__` raised. Fixed and tested.
- **#1028 and #1258 were re-scored after a P3 probe bug:** the eq/hash contract check flagged head whenever `a == b` but the hashes differed, without checking base. In both PRs the base commit **already** broke the contract (`Requirement("requests>=2.0") == Requirement("requests>=02.0")` with different hashes). That is a pre-existing bug, fixed upstream later by #1232, not a regression from either PR. The probe now requires base to keep the contract, and both classes were removed by a deterministic re-check (no new model calls).
- Totals above already include these corrections. The table no longer has `err` cells.

## Still open

- **Unadjudicated classes:** several, e.g. #1236's `ValueError` → `InvalidTag` and #1108's `AssertionError` → accepted. They need the adjudication step before they can be called bugs or intended changes.
- **Pre-existing bugs are invisible by design.** A differential tool reports what changed. The eq/hash bug above existed on both sides of #1258, so it is out of scope even though it is real.
