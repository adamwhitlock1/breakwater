# Risk register

Review at each gate (Oct 11, 14, 21). Status: open / watching / retired.

| # | Risk | Likelihood | Impact | Trigger to act | Mitigation | Status |
|---|---|---|---|---|---|---|
| 1 | Sandboxes beta access slow or denied | Med | High (Nebius judges expect it) | No access by Oct 13 | Docker backend works today; keep asking DevRel; disclose the backend per run | open |
| 2 | Cachegrind unusable in microVMs | Med | Med | check_contree.py fails the cachegrind step | Ir in Docker; Sandbox CPU-time with repeats in Sandboxes | open |
| 3 | Nemotron adversary adds little over plain Hypothesis | Med | High (Quality of Idea) | Ghostwriter baseline finds ≥ what the adversary finds by G1 | Lead with perf reversals (needs white-box reasoning); report the measured delta honestly; lean on white-box planning | open |
| 4 | Contamination: models memorized the packaging PRs | Med | Med | Memorization probe shows Ultra knows #1082/#1155 | Never hint at the bug; report post-cutoff PRs (#1371, #1429) and Codeflash PRs separately | open |
| 5 | Timing noise fakes or hides speedups | Low (Ir is deterministic) | High | Wall and Ir disagree in direction | A/A floor, interleaving, frozen GC, INCONCLUSIVE verdict | watching |
| 6 | Token Factory quirks (thinking eats budget, ignored params) | High | Low | day-1 check C | `llm.py` sets `chat_template_kwargs`, strips `<think>`, retries without thinking | watching |
| 7 | Rate limits throttle fan-out | Med | Med | >10% 429s in the burst test | Token-bucket scheduler, `flex`, overnight sweeps | open |
| 8 | Scope creep with a growing team | High | High | Anything not on the roadmap before G2 | Roadmap gates; cut list; freeze Oct 24 | open |
| 9 | Budget overrun | Low | Med | Ledger passes $30 before G2 | Per-run caps, Lightning default, `flex` | open |
| 10 | Demo down in December | Med | High | — | Static report + Pyodide box; live endpoint optional and capped | open |
| 11 | Tone toward upstream maintainers | Low | Med | — | Frame maintainers as doing everything right; work on forks; no upstream reports without team review | watching |
| 12 | Judges see "perf tooling" as niche | Med | Med | Feedback on the rough video cut | Lead with reward-hacking and "inside pip"; name the reviewer persona in the first 12 s | open |
