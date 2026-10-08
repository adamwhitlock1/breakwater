# Tool feedback log

The Devpost submission requires feedback on Token Factory, AI Cloud and the NVIDIA tools we use, and 10 × $100 prizes go to the most valuable. Log friction **as it happens**, with the tool name, what we tried, what happened and what would have helped. Be specific; vague praise scores nothing.

| Date | Tool | What we tried | What happened | Suggestion | Severity |
|---|---|---|---|---|---|
| 2026-10-08 | contree-sdk (Sandboxes) | Followed the GitHub README quick start | The README documents the unreleased 0.4.0 API (separate `contree_client` package, `ContreeClient(...)` objects). PyPI's latest is 0.3.6, where `ContreeSync()` reads `NEBIUS_API_KEY` / `NEBIUS_PROJECT_ID` from env. We had to read the installed source to find the right calls. | Pin the README to the latest release, or add a "you are reading docs for 0.4.0.dev" banner | Med |
| 2026-10-08 | contree-sdk | Looked for per-run CPU / memory metrics (needed for our second clock) | They exist (`ProcessResources`: user/system CPU, max RSS, context switches, plus per-run `cost`), but only through `result._raw.result.resources`, a private attribute | Expose resources as a public field on `ContreeResult` and document the units | Med |
| 2026-10-08 | Token Factory + LiteLLM | Evaluated GEPA/DSPy, which route through LiteLLM | LiteLLM's `nebius/` provider prefix still defaults to the old `api.studio.nebius.ai` URL (from research; re-verify) | Upstream a LiteLLM fix or document `openai/<model>` + `api_base` prominently | Low |
| 2026-10-08 | Sandboxes access | Requested beta access | _(record the date and how long approval took)_ | | |
