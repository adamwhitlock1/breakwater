# "For judges" map (draft; becomes the top README table at submission)

Each row must point at evidence a judge can check in under a minute. Fill as artifacts land.

| Criterion | Our claim | Evidence (link) |
|---|---|---|
| Technological Implementation | Three Nemotron tiers on Token Factory with explicit reasoning control and a per-tier bill; untrusted LLM-written code runs only in Sandboxes; deterministic Ir search + CI-confirmed finalists on a Serverless Job | _ledger summary, report receipts, `src/breakwater/llm.py`, `backends/`_ |
| Design | One command (`breakwater audit`) → a verdict, counterexample cards with tests, a report page and a PR check; judges can try their own input in the browser | _demo URL, screenshots_ |
| Potential Impact | Real regressions in pip's version library, reproduced; N of M merged AI speedups audited | _ground_truth.json, backtest table_ |
| Quality of Idea | The benchmark is the suspect: an adversary that falsifies speed and equivalence claims, with a second clock against timing hacks | _README "Why", demo video_ |
| Stage 1 track fit | Coding agent that writes and runs tests in Token Factory Sandboxes | _architecture section_ |
| Required tools | Nemotron 3 Ultra, 3.5 Lightning (Token Factory); Sandboxes; Serverless Jobs | _README "NVIDIA and Nebius usage"_ |
| Tavily (bonus) | Recon step, kept only if the ablation shows value | _ablation table_ |
