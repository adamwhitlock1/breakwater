# Demo video script (draft v0; target 2:50, hard cap 3:00)

Rules from the organizers:
- Treat it as a pitch, not a tutorial.
- Say "Nebius Token Factory" and the NVIDIA model names **aloud**.
- Judges may not watch past 3:00 and may never open the app.
- Open with "X for Y".

`[x]` marks a number to fill from real runs. Never ship a placeholder.

| Time | Beat | On screen |
|---|---|---|
| 0:00–0:12 | "Breakwater is a red team for performance pull requests. Before your code is called faster, a Nemotron adversary tries to make it slower, or wrong." | A GitHub PR check turning red: `BLOCK — speedup reverses on non-simple versions; 2 behavior divergences` |
| 0:12–0:35 | The problem, with real artifacts. "pypa/packaging is the version parser inside pip. In 2026 its maintainers merged a run of performance PRs, and three of them changed behavior and needed follow-up fixes." Benchmarks only test the inputs you thought of. Then one line on reward hacking: AI speedup claims get gamed. | PR titles #1109, #1163, #1155; issue #1162 |
| 0:35–1:15 | **Live audit** of #1082's intermediate commit (benchmark: ~2x faster). Ultra's plan: "the fast path trusts `int()`". Lightning writes [x] strategies; Sandboxes gauge fills; cards land: `"1. 0"` accepted, Arabic-Indic digits accepted, oversized-int exception changed. **Perf card: 0.97x Ir on non-simple versions; slope chart.** | Attack feed, Sandboxes gauge, cost meter by tier; say the model names |
| 1:15–1:45 | **The verdict.** Per-family table: 2.06x simple vs [x] weighted over [x]M real PyPI versions, worst family [x]; finalist wall-clock CI from a Serverless Job, A/A floor ±[x]%. Two-clock panel. Each card has a generated pytest. | Report page |
| 1:45–2:05 | **Judge box.** Type a version string; base / PR / merged disagree live in the browser. | Pyodide box |
| 2:05–2:35 | **Evidence.** Backtest: [x]/3 documented regressions caught pre-merge vs tests+benchmarks 0/3, ghostwriter [x]/3, Ultra-reads-diff [x]/3. [x] of [x] merged Codeflash speedups reverse or diverge. $ per divergence class: Lightning [x] vs Ultra [x]. Total bill $[x]. | Table + bill |
| 2:35–2:50 | Honest limitation: "Breakwater falsifies; it doesn't prove. 'Survived' means survived [x] probes and [x] rounds." | — |
| 2:50–3:00 | "Breakwater. Nebius Token Factory and Sandboxes, NVIDIA Nemotron Ultra and Lightning." Repo + demo URL. | — |

Production: script locked Oct 25; record Oct 26–27; upload Oct 28.
