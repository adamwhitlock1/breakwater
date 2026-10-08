# Candidate findings (unverified until a human checks them)

Findings Breakwater surfaces beyond the documented ground truth. **Nothing goes upstream without human review and team approval**; see the tone rule in `risks.md`.

| Date | Target | Probe | What we saw | Status |
|---|---|---|---|---|
| 2026-10-08 | packaging #1108 (base 20f1523c → head f59d6ee9), `SpecifierSet` | P4 base→head | A `SpecifierSet` pickled by base loads in head, but comparing it with a freshly built one returns False (`">1.0.0,>1.0"`) or raises `AttributeError` (`">1.0"`). Likely cause: the pickled `_specs` is a frozenset where head expects a tuple. **It shipped:** 26.0 → 26.1 gives `AttributeError` on all 3 inputs tried; 26.2 and 26.3 are clean. So it was fixed upstream in 26.2 (released 2026-04-24, alongside the pickle-safety PRs #1170/#1174). Not a new bug, but a **fourth ground-truth case**, found by a probe rather than from the issue tracker. Add it to the backtest. | fixed upstream in 26.2; add to backtest |
| 2026-10-08 | packaging #1082 merged (59f183fe → ee13ba2c), `Version` | perf (Ir ladder, run 5cc766ba4829) | The fast path is faster only on simple versions (0.64x Ir at ~37 chars, shrinking to 0.90x at ~8k chars). Every non-simple family Ultra proposed is slower: pre-release 1.08–1.14x, **dev and post releases 1.22–1.52x** more instructions per call. Slopes match, so these are constant-factor costs of the new guard. Maintainers measured 2.37x / 0.84x by wall clock in review. Needs the real-PyPI-weighted number before it becomes a headline. | measured; weight by real corpus |
