# Demo video script (v1, locked Oct 29; target 2:47, hard cap 3:00)

Rules from the organizers:
- Treat it as a pitch, not a tutorial. Get to the aha moment in the first 30 seconds.
- Say "Nebius Token Factory", "Token Factory Sandboxes" and the Nemotron model names **aloud**, and show which model does what.
- Judges may not watch past 3:00 and may never open the app.
- Open with "X for Y". Public YouTube, no third-party music.

Every number below is checked against a committed Token Factory artifact (table at the end). Read the narration as written; at ~150 words a minute it runs about 2:47. If a beat runs long, cut words, not beats.

## Footage (no new spend)

```bash
uv sync
uv run breakwater site --out site --run artifacts/demo/pr1082-61967cca --run artifacts/demo/pr1082-61967cca-sandboxes
uv run python -m http.server 8000 -d site      # then open http://localhost:8000/ (or the published Pages URL)
uv run breakwater replay artifacts/demo/pr1082-61967cca-sandboxes --speed 10 --delay 3 --out artifacts/runs/replay-e780 --open
```

- The site command matches `.github/workflows/pages.yml`. The site has no network requests except the judge box's Pyodide download; click **Start** on `judge.html` once before recording so it is cached.
- The replay plays the recorded Sandboxes audit (run `e780ff68654f`, 415 s) in the live page, labelled "replay ×10 of run e780ff68654f", with the recorded times. At ×10 it takes about 42 s, which fits beat 3. `--out` under `artifacts/runs/` keeps the replay files out of git (the default writes into the committed run directory).
- Say on camera that the replay is sped up. Nothing is re-run.
- Pages per beat: 1 `codeflash/pr/json_repair-113.html` · 2 README "What it found" table (or the three GitHub PRs) · 3 the replay page · 4 `runs/e780ff68654f.html` · 5 `judge.html` · 6 `index.html` backtest table, then `codeflash/index.html` · 7 end card.

## Script

| Time | Say | On screen |
|---|---|---|
| 0:00–0:20 | "Breakwater is a red team for performance pull requests. This merged, AI-written PR claims 'speed up `is_same_object` by 109%'. On its own benchmark, it is faster. Breakwater's Nemotron adversary found where it isn't: two same-size JSON objects that differ by one key. There, the new code does 363 times the work." | json_repair #113 page: the PR title, the BLOCK banner ("up to 363× the work on valid inputs"), then the ladder chart climbing to 363.31× |
| 0:20–0:38 | "Benchmarks only test the inputs someone thought of, and careful humans get caught too. pypa/packaging, the version parser inside pip, merged speedups this year that changed behaviour and needed follow-up fixes. Breakwater is for the reviewer of a 'faster' PR, before it merges." | The three packaging PRs and their fixes: #1082 → #1155, #1108 → #1109, #1116 → #1163 (issue #1162) |
| 0:38–1:22 | "Here is a real audit of one of those pip changes, recorded on Nebius Token Factory and played back at ten times speed. Nemotron 3 Ultra, reasoning on, reads the diff and names the assumptions it makes: 'the fast path assumes `int()` only accepts ASCII decimal digits.' Nemotron 3.5 Lightning, reasoning off, writes twenty Hypothesis strategies to attack them. Every line the models write runs in a Token Factory Sandboxes microVM, never on my laptop: 358 microVM runs in this audit. Nemotron 3 Super writes variants of the slowest input families, and cachegrind counts instructions, so the measurement is deterministic. Counterexamples land: Arabic-Indic digits, and a space inside the version." | Replay page: "replay ×10" label, Ultra's plan (A1–A5), the strategy feed, the Sandboxes gauge filling, the cost meter by tier, cards landing. Lower-third: "Ultra: plan + adjudicate · Lightning: strategies · Super: perf variants" |
| 1:22–1:52 | "The verdict: BLOCK. Ultra adjudicates each difference three times, and a vote only counts if it quotes its evidence from the PR. Four are likely bugs, and each comes with a pytest that passes on the old code and fails on the new. Performance: the claimed speedup is real, 0.38 times the instructions on short simple versions. But long pre-release versions cost up to 2.74 times as much. The whole audit cost 18 cents." | Run page `e780ff68654f`: verdict banner, a card with its votes and quoted evidence and "verified" test, the perf ladders (F2 faster, R4.1 slower), the receipt: tier bill, backend Sandboxes, image `dbe8dafe…` |
| 1:52–2:07 | "You can try it yourself. This page runs four real versions of pip's version parser in your browser. 'One dot space zero': the original rejects it, the intermediate commit accepts it." | `judge.html`: click the "1. 0 · space inside" preset, then "١.٢ · Arabic-Indic digits"; the four columns disagree |
| 2:07–2:32 | "Across 29 packaging speedup changes, Breakwater caught all nine verified regressions. The PRs' own tests caught none, and the best baseline without a model caught seven. On ten merged AI-written speedups, run end to end in Sandboxes, four change behaviour, three of them likely bugs. Plain Hypothesis and mutations found nothing there." | Index backtest table (arms: tests 0/9, Hypothesis 2/9, mutations 7/9, Breakwater 9/9; "Docker" chip), then the Codeflash index (Sandboxes chip) |
| 2:32–2:47 | "Breakwater falsifies; it doesn't prove. A pass means these probes and this budget found nothing. Breakwater: Nebius Token Factory and Token Factory Sandboxes, with Nemotron 3 Ultra, 3.5 Lightning and 3 Super. The code and the live report are linked below." | End card: "Breakwater", repo URL, demo URL, "Nebius Token Factory · Token Factory Sandboxes · Nemotron 3 Ultra · Nemotron 3.5 Lightning · Nemotron 3 Super" |

Notes for the speaker:
- "Twenty strategies" is what Lightning wrote; 14 of them were valid Hypothesis code (the feed shows both). Don't say "all twenty ran".
- The 2.74× is at about 33,000 characters (an adversarial size); at 160 characters the same family is 1.35×. If asked, that's the honest framing; the run page shows the whole ladder.
- The 29-PR packaging backtest ran on Token Factory with the Docker backend (Oct 9); its eight items with issues or slowdowns were re-run on Sandboxes with the same 9/9. Codeflash and the demo audit ran on Sandboxes. Don't say "all 29 on Sandboxes".
- The GitHub Action has not run on GitHub. Don't show a PR check; if you want a PR-comment shot, `uv run breakwater comment artifacts/demo/pr1082-61967cca-sandboxes` renders it locally (say "the comment the Action posts").

## If you only have 30 minutes

Record one take over the static site, no replay. Open on the json_repair #113 page and read beat 1. Show the packaging PR table and read beat 2. On the run page `e780ff68654f`, scroll Ultra's plan, two cards and the receipt while reading beats 3 and 4 combined ("Nemotron 3 Ultra planned five attacks, Nemotron 3.5 Lightning wrote twenty strategies, Nemotron 3 Super wrote perf variants, and all of it ran in Token Factory Sandboxes: 358 microVM runs, 18 cents"). Click one judge-box preset (beat 5), show the index table (beat 6), and close with beat 7. Keep it under 2:30, say the product and model names, upload, done.

## Numbers used

| Number | Source | Field |
|---|---|---|
| "by 109%" (json_repair #113 title) | `artifacts/backtest/codeflash-v2/json_repair#113.json` | `title` |
| 363× (363.31×), ~604,000 chars; same answer on both sides | `artifacts/backtest/codeflash-v2/results.json`, item `json_repair#113` | `targets[0].perf.worst_valid_ratio`; `perf.report.findings[R2].ladder`; `arms.breakwater.classes` is empty |
| Codeflash: 10 PRs, 4 change behaviour, 3 likely-bug, baselines 0 | `codeflash-v2/results.json` `summary.items_with_classes` (breakwater 4, hypothesis 0, mutations 0); `artifacts/adjudication/codeflash-v2/adjudication.json` | likely-bug on Math-Interpreter #1, caddy-feeds #4, patterns #12; rendercv #18 intended |
| Ultra's quote "assumes `int()` only accepts ASCII decimal digits" | `artifacts/demo/pr1082-61967cca-sandboxes/report.json` | `semantic.attacks[A3].assumption` |
| 5 attacks, 20 strategies (14 valid) | same | `semantic.attacks`, `semantic.strategies[*].valid` |
| 358 microVM runs, 1,165 s CPU, image `dbe8dafe-78c4-4fc8-b8c2-a5adaad2ed49` | same | `sandbox.runs`, `sandbox.cpu_s`, `sandbox.image` |
| Model per step (Ultra plan/adjudicate/perf-plan, Lightning strategies, Super perf-expand) | `.../events.jsonl` | `kind: llm` events, `tier`/`model`/`purpose` |
| BLOCK, 6 classes, 4 likely-bug | same `report.json` | `adjudication.verdicts[*].label` |
| 4 verified pytests (2 skipped as intended) | same | `regression_tests[*].verified` |
| 0.38× (claimed speedup, ~7 chars) | same | `perf.findings[F2].ladder[0].ratio` |
| 2.74× at ~33,000 chars; 1.35× at ~160 chars | same | `perf.findings[R4.1].ladder` (Super's variant of archive family R4, `origin: expand:R4`) |
| 18 cents ($0.1841) | same | `usd_by_tier` (reasoning 0.182, volume 0.0014, proposer 0.00075) |
| Run length 415 s → ~42 s at ×10 | same `events.jsonl` | last event `t: 414.93` |
| "1. 0" and "١.٠": base rejects, 61967cca accepts | `artifacts/day1/ground_truth.json` | `pr1082_version` |
| Packaging: 29 items, 9/9 vs tests 0/9, Hypothesis 2/9, mutations 7/9 (Docker backend) | `artifacts/backtest/packaging-v3/results.json` | `summary.caught_verified`, `summary.known_verified` |
| Packaging subset on Sandboxes: 9/9 again | `artifacts/backtest/packaging-v4-sandboxes/results.json` | `summary.caught_verified.breakwater`, `backend: contree` |

Cut from v0 because they weren't built or measured: the GitHub PR check turning red, real-PyPI weighting, Serverless Jobs finalist timing and the A/A floor, the two-clock panel, and the Lightning-vs-Ultra $/class ablation.
