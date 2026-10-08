# Breakwater

Hackathon entry (Nebius x NVIDIA Global AI Hackathon, Coding track). Deadline 2026-10-30 10:00 PT. The plan lives in `docs/roadmap.md`; scope in `docs/spec.md`; settled choices in `docs/decisions.md` (don't relitigate them without new evidence).

## Commands
- `uv sync --extra sandboxes` — install (Python 3.12)
- `uv run pytest -q` and `uv run ruff check .` — run both before calling work done
- `uv run breakwater doctor` — env/key/Docker check
- `docker build -f docker/harness.Dockerfile -t breakwater-harness .` — local harness (valgrind); macOS has no valgrind, so Ir measurement runs in this container

## Rules
- All model calls go through `breakwater.llm.Nemotron` so they are tiered, reasoning-controlled and written to the cost ledger. Never use `reasoning_effort`; set `chat_template_kwargs` (Token Factory ignores the former).
- Untrusted code (LLM-written strategies, candidate patches) runs only through a `breakwater.backends` backend, never in the orchestrator process.
- contree-sdk is pinned to the 0.3.6 API. Its GitHub README documents unreleased 0.4.0; trust the installed source.
- Every published number must be reproducible from a recorded image + seed. Don't put placeholder numbers in the README or video script; use `[x]`.
- Log tool friction in `docs/feedback-log.md` when you hit it (it is a scored submission item).
- No keys in the repo; `.env` is gitignored.
