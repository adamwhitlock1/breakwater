# Backtest: pypa/packaging 2026 perf PRs (v2, 2026-10-08)

Full results: `artifacts/backtest/packaging-v2/` (`table.md`, `results.json`, one JSON per PR). Corpus: `corpus/packaging.json`, 28 merged library perf PRs plus #1082's intermediate commit. The base of each item is the parent of its merge commit. Backend: Docker. Total Nemotron cost: **$2.69** for the main run plus **$0.16** for two re-runs.

## Known regressions caught

| Arm | LLM | Verified (9) | Candidates (3) | PRs with any divergence |
|---|---|---|---|---|
| PR's own tests + benchmarks | — | 0 (by construction: these PRs merged green) | 0 | 0 |
| `hypothesis`: `st.text()` search | no | 2 | 0 | 4/29 |
| `mutations`: the PR's own test literals + hostile mutations | no | 7 | 1 | 10/29 |
| `llm-plan`: Ultra's example inputs only | Ultra | 5 | 1 | 10/29 |
| **`breakwater`**: plan + Lightning strategies + search + mutations + test literals | Ultra, Lightning | **9** | **1** | 11/29 |

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
| #1320 | Requirement pickles (candidate, linked fix #1171) | | | | |
| #1118 | hash cache when copying (candidate, linked fix #1242) | | | | |

## What Nemotron adds (honest reading)

- **Two verified issues are caught only by the full pipeline:** #1082's Unicode digits (only Ultra's examples contained a non-ASCII digit to mutate) and #1108's equality change (found by the focused relations pass over planner seeds and their equivalents).
- **The deterministic layer does most of the work on this corpus.** Hostile mutations of the project's own test strings catch 7/9. That is a product feature, not an embarrassment: Breakwater runs both, and the LLM extends coverage where the project's tests have no hostile examples to start from.
- **Circularity note:** #1030 entered the ground truth because Breakwater found it in v1. Excluding it, the full pipeline catches 8/8 pre-existing verified issues, and the no-LLM mutations arm 6/8.
- **Contamination:** Ultra said it has no specific memory of #1082 or #1155. Of the 9 PRs merged after Ultra's release, Breakwater flagged behavior changes in #1236 (exception types) and #1429 (pickles); none of them has a documented fix yet, so none counts toward recall.

## Adjudication (Token Factory, 2026-10-08)

Full results: `artifacts/adjudication/packaging-v2/` (`adjudication.md` lists every class with its votes, rationale and quoted evidence). Ultra labels each class of the breakwater arm `likely-bug`, `intended` or `needs-human`: 3 samples, strict majority, and a vote counts only if its quotes are found verbatim in the PR material (see `decisions.md`). Command: `breakwater adjudicate artifacts/backtest/packaging-v2`. Cost: **$0.39**.

Every known issue was fixed upstream, so its classes should be `likely-bug`.

| Classes | likely-bug | intended | needs-human |
|---|---|---|---|
| Matching a known issue (19) | 15 | 3 | 1 |
| No ground truth (28) | 12 | 16 | 0 |

- **Known issues: 8 of 10 labelled likely-bug.** #1082's oversized-int `ValueError` → `InvalidVersion` is the miss: `intended` on the merged PR, `needs-human` on the intermediate commit (two classes of that issue labelled `intended`). The model's evidence is real: the PR's own tests expect `InvalidVersion` for invalid simple versions, and `InvalidVersion` subclasses `ValueError`. Maintainers decided otherwise for the int-digit case in #1155. We did not tune the prompt toward that answer.
- **`intended` is not a rubber stamp.** 9 of the 16 `intended` labels are on #1064, which restored the lowercasing that #1030 had broken. That label is verifiably right: the changed behavior *is* the fix, as `canonicalize_name`'s docstring (`.lower()` from PEP 503) says. The other 7 are #1236's `ValueError` → `InvalidTag`, where `parse_tag`'s docstring says it raises `InvalidTag` on empty components.
- **Without ground truth, 12 `likely-bug`:** #1030's ordering flips (same root cause as its known issue), exception-type changes on non-string input (#1030, #1082 intermediate), #1108's long-specifier outcomes and hash change, and pickle breaks in #1032, #1115 and #1429. They are candidates for the findings log, not counted as recall.

**Run history (honest accounting).** This is the fourth Token Factory run; total adjudication spend was **$1.64**. Each earlier run exposed a problem, which was fixed in code before re-running *everything* (no item was re-run on its own):
1. With the facts placed before ~8k tokens of code, some samples answered a different task ("compare the two snippets"). This happened on 1082@61967cca and #1429, with both batched (`n=3`) and separate calls. The quote check demoted all of them to `needs-human`, so no wrong label got through. Fix: context first, facts and task last.
2. The verbatim-quote check was too strict for multi-line code and `...` elisions. Fix: whitespace-insensitive matching, and elided quotes pass if every fragment is found.
3. With the task moved to the end, the "copy evidence verbatim" instruction was far from it, so samples paraphrased and correct votes were demoted. Fix: the instruction is restated in the task.

## v3: planner v3 (2026-10-09, Token Factory)

Same corpus, the four semantic arms re-run with planner v3 (see `decisions.md`). Perf was not re-run: it doesn't use the semantic planner, so the perf numbers below are from v2. Full results: `artifacts/backtest/packaging-v3/` and `artifacts/adjudication/packaging-v3/`. Cost: $1.58 for the backtest, and $1.39 for adjudication including two superseded attempts (details below).

| Arm | Verified (9), v2 → v3 | Candidates (3) | PRs with any divergence, v2 → v3 |
|---|---|---|---|
| hypothesis | 2 → 2 | 0 | 4 → 4 |
| mutations | 7 → 7 | 1 | 10 → 10 |
| llm-plan | 5 → **6** | 1 | 10 → 7 |
| **breakwater** | 9 → **9** | 1 | 11 → 10 |

- **The no-LLM arms reproduced v2 exactly.** They are deterministic, so this is a check that nothing else changed.
- **Plan only, 5 → 6:**
  - gained #1108's equality and `str`/`len` regressions;
  - lost 1082@61967cca's inner whitespace.

  Each item is one sample, so +1 is within run-to-run noise. Read it as "no worse, possibly slightly better". The plan-only eval (0/15 → 7/15 productive attacks) is the clearer evidence.
- **Full pipeline: still 9/9.** It flags fewer classes with no ground truth: three of #1236's seven exception-type classes, the #1429 pickle class, and two #1064 equality classes.

**Adjudication (v3 classes): 8 of 10 known issues labelled likely-bug, the same as v2.**
- 19 of the 22 classes that match a known issue are labelled likely-bug, 3 intended and none needs-human.
- The misses are #1082's oversized-int exception change, labelled `intended` on both the merged PR and the intermediate commit (in v2: intended and needs-human). As before, the PR's own tests expect `InvalidVersion`.
- Two classes on the intermediate commit carry both the non-ASCII and long-digits traits, so they match two known issues at once. Labelled `intended` because of the long digits, they show up as "with an intended class" under unicode-digits too: an artifact of trait matching, not a separate miss.

**Round-trip control (2026-10-09, re-scored without model calls):** a generated regression test for #1115's pickle class failed on **base**. On #1115's base commit, a `Version` pickled after hashing already doesn't equal a fresh one once unpickled: its cached `Infinity` sentinels compare by identity. So the class predates the change. P4 now also requires the object to survive a round trip on the version that pickled it. The re-score removed #1115's pickle class from v2 and v3, and #1429's (a load failure that also happens on its own base) from v2. Its adjudication verdicts were dropped. Headline numbers are unchanged; v3 PRs with any divergence: 10 → 9.

**Regression tests (`artifacts/regress/packaging-v3/`):** 30 of 30 generated tests verified (pass on base, fail on head). 14 classes were skipped because they're labelled intended. One `test_<item>.py` per PR.

**Adjudication run history:**
1. #1108 abstained on all 15 classes. One sample ran away to 51k output tokens, and some quotes used literal `\n` escapes that the checker rejected.
2. After bounding the schema and accepting escaped whitespace, #1108 still lost samples to runaways. All three hit the 24k cap with little reasoning, which suggests runaway output outside the bounded fields.
3. Fix: at most 8 classes per call and a 16k-token cap, which only changes items with more than 8 classes. #1108 was re-adjudicated alone (12 likely-bug, 3 needs-human) and the summary re-computed with no model calls. Every other item comes from attempt 2.

**Per-size validity (2026-10-11, no model calls):** perf verdicts now use only ladder sizes where the base version accepts most inputs. The v2 ladders were regenerated from their recorded generators: every size reproduced exactly. Validity was then measured and the families re-judged:
- the worst ratios below are unchanged;
- #1082's claimed-speedup family F2 changed from `neutral` to `faster` (its n=2 size was mostly invalid);
- #1236's R1.1 changed from `complexity-regression` to `slower` (all sizes but n=2 mostly invalid; not #1236's worst family).

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
- **P4 control fix (re-scored with `scripts/backtest/rescore_p4.py`, no model calls):** P4 flagged a base-pickled object that failed to equal a fresh head object. In #1081, #1106, #1258 and #1320 the failing comparison was on 4,300-digit inputs, where `==` raises even between two **fresh** objects on **both** sides (Python's int-digit limit), so the pickle was not to blame. In #1030 and #1064 the target returns a `str`, so P4 only restated the P1 output change. P4 now requires two fresh objects to compare equal and skips builtin values. No-LLM arms were re-run in full and LLM arms re-checked on their stored inputs. Effect: verified catches unchanged; the #1320 `requirement-pickle` candidate is **no longer caught** (realistic `Requirement`s round-trip cleanly from its base to its head, so if that issue exists it involves pickles from an older release); items with any divergence fell from 15 to 11 (breakwater) and 14 to 10 (mutations).
- Totals above already include these corrections. The table no longer has `err` cells.

## Still open

- **Adjudication:** see below.
- **Pre-existing bugs are invisible by design.** A differential tool reports what changed. The eq/hash bug above existed on both sides of #1258, so it is out of scope even though it is real.

# Codeflash corpus (2026-10-12, Token Factory)

Ten merged Codeflash-bot speedup PRs in seven repos (`corpus/codeflash.json`; selection and install modes in `decisions.md`). There are no known regressions: the question is how many merged AI speedups change behaviour or don't deliver. Full results: `artifacts/backtest/codeflash-v1/`, `artifacts/adjudication/codeflash-v1/` and `artifacts/regress/codeflash-v1/`. Cost: **$1.01** (backtest $0.95 including a failed pyhs3 attempt; adjudication $0.06).

**3 of 10 change behaviour** (all classes adjudicated likely-bug; 6 of 6 regression tests verified):
- **Math-Interpreter #1** ("Speed up method `Lexer.generate_number` by 11%"). It swapped `ch in DIGITS` for `ch.isdigit()`, so the lexer now tokenises `"0٠"` and `"1١ "` (Arabic-Indic digits) as numbers where the original raised "Illegal character". This is the same bug class as packaging #1082. Found by the full pipeline (3 classes); the plan alone found 1.
- **caddy-feeds #4** ("Speed up function `is_excluded` by 17,376%"). `@lru_cache` makes an unhashable argument (a list) raise `TypeError` where the original returned a result. Wrong-type input. The adjudicator's label is right but its rationale (a Python-version claim about `maxsize`) is wrong: the quote check can't catch a wrong explanation built on a real quote.
- **rendercv #18** ("Speed up function `validate_date_field` by 47%"). A list argument raises `ValueError`/`AttributeError` instead of `TypeError`. Wrong-type input.

**1 of 10 has a performance reversal on valid input:**
- **json_repair #113** ("Speed up method `ObjectComparer.is_same_object` by 109%"), labelled `complexity-regression`. Base compares two dicts' key sets and returns at once when the keys differ. Head checks only the lengths, then recursively compares values key by key until it reaches the missing key. On same-sized JSON objects that differ by one key and have large values, head runs 1.6× the instructions at ~175 characters, 15× at ~2 KB, 86× at ~33 KB and 393× at ~600 KB. Both return the same answer. Its claimed-speedup family does measure faster (0.48–0.58×).

**Smaller or no effect:**
- micropie #3: cookie headers with many parts missing `=` cost up to 1.34× (1.71× in the dev run).
- rendercv #18: `"present"` costs 1.11×.
- Math-Interpreter #1: single-digit-heavy expressions cost up to 1.05×.
- **pyhs3 #154** (an `lru_cache` on a sympy parser): all six perf families are **unmeasured**. The instruction count isn't linear in repetitions (caching), so no honest per-call number exists. The first run's arms failed on a harness bug (sympy's symbolic comparisons broke JSON output); fixed, then the item was re-run.
- No behaviour change found in json_repair #113, rendercv #17 and #19, patterns #9 and #12, micropie #3 or pyhs3 #154.

The no-LLM baselines (plain Hypothesis; mutations of the project's test strings) found nothing on this corpus. Most of these repos have no tests next to the changed function to harvest, so the Nemotron plan and search did all the finding.

## Codeflash corpus on Token Factory Sandboxes (v2, 2026-10-24)

The same ten items re-run with every untrusted run in a Token Factory Sandboxes microVM (`--backend contree`): `artifacts/backtest/codeflash-v2/`, `artifacts/adjudication/codeflash-v2/`, `artifacts/regress/codeflash-v2/`. Token Factory inference throughout. Cost: **$0.88** (backtest $0.81, adjudication $0.08) plus $0.04 on an aborted first attempt (two workers raced to clone the rendercv repo; fixed, the run restarted before any item finished). Wall time 45 minutes with 3 items in parallel; 6 transient Sandboxes API errors (3 HTTP timeouts, 3 transport errors), every one recovered by the backend's retry. **This is the run the site shows**; v1 (Docker) stays committed as the cross-check. Per item (`scripts/backtest/compare_backends.py codeflash-v1 codeflash-v2`):

| Item | Docker (v1) | Sandboxes (v2) | Same? |
|---|---|---|---|
| Math-Interpreter #1 | BLOCK; 3 classes, 3 likely-bug; 3 tests | BLOCK; the same 3 classes, 2 likely-bug + 1 needs-human (the 4,305-digit input abstained 1–2); 3 tests | verdict ✓ |
| micropie #3 | REVIEW; worst 1.34× (cookies surrounded by whitespace) | REVIEW; worst 1.60× (many empty segments; a newly planned family) | verdict ✓ |
| caddy-feeds #4 | BLOCK; 1 likely-bug; 1 test | BLOCK; the same class, likely-bug 3/3; 1 test | ✓ |
| patterns #9 | PASS | PASS | ✓ |
| patterns #12 | PASS, no divergence | **BLOCK**: a new wrong-type-input class (a nested list raises `TypeError` from the `lru_cache` where base raised `AttributeError`), likely-bug 3/3, test verified | ✗ (new finding) |
| rendercv #17 | PASS | PASS | ✓ |
| rendercv #18 | BLOCK; 2 likely-bug classes (wrong-type input: `TypeError` → `ValueError` / `AttributeError`); 2 tests | **PASS**: 1 class (the `TypeError` → `ValueError` one), labelled intended 3/3 ("the new exception type aligns with the library's own error handling"); the `AttributeError` near-duplicate was not found | ✗ (adjudicator and search variation) |
| rendercv #19 | PASS | PASS | ✓ |
| json_repair #113 | BLOCK; complexity regression up to 393× | BLOCK; the same four complexity-regression families, up to 363× | verdict ✓ |
| pyhs3 #154 | PASS; perf unmeasured (caching) | PASS; perf unmeasured | ✓ |

- **8/10 same verdict.** Neither difference is a backend effect: both are the adversary sampling a different plan (patterns #12's class comes from a new Ultra attack; rendercv #18's missing near-duplicate too) and the adjudicator voting differently on the same kind of evidence (rendercv #18: likely-bug 2/3 on Docker, intended 3/3 on Sandboxes, for a `TypeError` → `ValueError` change on non-string input). The headline becomes **4 of 10 change behaviour** (3 adjudicated likely-bug, 1 intended), 1 of 10 reverses on valid input, 5 of 5 generated tests verified.
- **Ir across backends.** Docker on the development Mac is arm64; the Sandboxes microVM is x86_64 (AMD EPYC 9654, Python 3.12.13, valgrind 3.24.0), so cachegrind counts different instruction streams. The eight families measured in full on both backends agree in verdict and shape: Math-Interpreter's three families 0.0% apart, rendercv #18's `present` family 0.2%, json_repair's four complexity ladders 7.1–7.6% lower on x86_64 (393× → 363×, 172× → 160×, 4.03× → 3.73×, 3.66× → 3.39×). See `decisions.md` 2026-10-24.
- Every number on the Codeflash pages now cites a Sandboxes image UUID (receipt and cards); the images are in the table `compare_backends.py` prints.

## Packaging subset on Token Factory Sandboxes (v4, 2026-10-24)

The eight items with known issues or measured slowdowns (#1030, #1064, #1082, 1082@61967cca, #1108, #1116, #1147, #1236) re-run with `--backend contree --perf`: `artifacts/backtest/packaging-v4-sandboxes/`, `artifacts/adjudication/packaging-v4-sandboxes/`, `artifacts/regress/packaging-v4-sandboxes/`. Token Factory inference; 23 minutes; no API retries needed. Cost **$1.12** (backtest $0.77, adjudication $0.35). The full 29-item Docker backtest (v3, perf from v2) stays the published backtest; the site shows this run as an item-by-item comparison (`site/sandboxes/`), and every page and card now says which backend and image produced it.

| Arm | Verified (9), Docker v3 → Sandboxes v4 | Candidates (1 in this subset) |
|---|---|---|
| hypothesis | 2 → 2 | 0 |
| mutations | 7 → 7 | 1 → 1 |
| llm-plan | 6 → 5 (v2 had 5) | 1 → 0 |
| **breakwater** | 9 → **9** | 1 → 1 |

- **Same recall, same classes where found.** 5/8 items have the same verdict; the three that differ are adjudicator votes (#1064 likely-bug 2/3 here vs intended 3/3 on Docker, where the docstring makes intended the right label; #1236 needs-human on all six classes vs intended 4/4) and one search miss (#1082's nested-input class). None is a backend effect. The per-item table is in `roadmap-final-sprint.md`, G2'.
- **Adjudication:** 8 of 10 found known issues labelled likely-bug (v3: 8 of 10). Miss: #1082's oversized-int exception, intended on the merged PR (needs-human on the intermediate commit). Cost $0.35.
- **Regression tests:** 39 of 39 generated tests verified in the sandbox (pass on base, fail on head); 1 class skipped as intended.
- **Ir across architectures:** #1064's archived family 1.10× → 1.08× (2.2%), #1030's 2.28× → 2.46× (7.9%) and its complexity regression 4.52× → 6.50× (44%; identical inputs, the regex-bound head simply costs more instructions on x86_64 and the base fewer). Same verdict on every shared family. See `decisions.md` 2026-10-24.
