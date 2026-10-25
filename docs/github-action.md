# Breakwater as a GitHub Action

Breakwater runs on a pull request and posts **one comment** that is updated on every push:
- the verdict (BLOCK, REVIEW or PASS) and why;
- the counterexamples, grouped, with their adjudication labels;
- the perf measurements;
- ready-to-commit regression tests.

The full report, the live page and `test_regressions.py` are uploaded as an artifact. The check fails on BLOCK by default.

## Use it

```yaml
# .github/workflows/breakwater.yml in the repository whose PRs you want audited
name: Breakwater
on:
  pull_request:
    paths: ["src/**"]          # only PRs that touch the code under test

permissions:
  contents: read
  pull-requests: write         # the comment

jobs:
  breakwater:
    runs-on: ubuntu-latest
    timeout-minutes: 45
    steps:
      - uses: adamwhitlock1/breakwater@main
        with:
          target: packaging.version:Version      # module:Callable, Class#method or Class()#method
          observe: str,repr,attr:release
          nebius-api-key: ${{ secrets.NEBIUS_API_KEY }}
          nebius-project-id: ${{ secrets.NEBIUS_PROJECT_ID }}   # run untrusted code in Sandboxes
```

Audit several targets with a `strategy.matrix` over `target`. Each target gets its own comment.

| Input | Default | |
|---|---|---|
| `target` | required | The callable under test. |
| `observe` | `str,repr` | What to compare on results: `str`, `repr`, `value`, `len`, `attr:<name>`. |
| `mode` | `both` | `semantic`, `perf` or `both`. |
| `fail-on` | `block` | Fail the check at this verdict or worse: `block`, `review` or `never`. |
| `comment` | `true` | Post or update the PR comment. The job summary is always written. |
| `nebius-api-key` | — | Nebius Token Factory key. Without it the action skips with a notice. |
| `nebius-project-id` | — | Nebius project ID. With it, every untrusted run (probes, strategies, generators, cachegrind) happens in a Token Factory Sandboxes microVM and the images are built there. Without it, a local Docker container on the runner (GitHub-hosted Ubuntu runners have Docker). |
| `github-token` | `github.token` | Used for the comment and the merge-base lookup. |

Outputs: `verdict` (BLOCK, REVIEW, PASS or SKIPPED), `backend` (`contree` or `docker`) and `report-dir`.

## What it does

1. Skips with a notice when there's no key (pull requests from forks never receive secrets) or the event isn't `pull_request`.
2. Installs Breakwater with uv. With a project ID it uses the Sandboxes backend: the harness and pair images are kept Sandboxes images, found again by tag on later runs. Without one it builds the Docker harness image on the runner.
3. Audits the PR head against its **merge base**, not the base branch tip, so changes that landed on the base branch later aren't blamed on the PR. Model calls go to Nebius Token Factory; each run's cost is in the report.
4. Uploads the run directory, renders the comment (which names the backend and the image UUID or tag that reproduces it) into the job summary, and posts or edits the PR comment. The comment is found again by a hidden per-target marker.
5. Fails the job if the verdict reaches `fail-on`. This happens last, so a blocked PR still gets its comment and artifact.

Cost: about $0.10–0.30 per target per run on Token Factory with the default settings (the backtests' per-item range), plus about 10–20 runner minutes.

## Limits (v1)

- **Public target repositories.** Base and head are installed inside the harness image with `pip install git+https://github.com/<repo>@<sha>`, without credentials.
- **Only `pull_request`, not `pull_request_target`.** Installing the head commit runs its packaging code during the image build. Under `pull_request_target` that would happen while secrets are available, which is how forks steal them.
- **One provider: Token Factory.** The OpenRouter development provider isn't exposed.
- **Python 3.12 packages, with targets whose arguments are JSON values** (strings, numbers, lists, dicts).
- **While this repository is private,** `uses: adamwhitlock1/breakwater@…` only works from repositories its owner shares Actions access with.

## Check it locally

`tests/test_action.py` runs the action's own shell steps from `action.yml` against the recorded demo run, with GitHub's output and summary files faked. Render a comment by hand:

```bash
uv run breakwater comment artifacts/demo/pr1082-61967cca
uv run breakwater verdict artifacts/demo/pr1082-61967cca
```
