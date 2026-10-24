## Breakwater audit: `packaging.version:Version`
https://github.com/pypa/packaging `59f183fe90` → `61967cca27` · backend `contree` · image `dbe8dafe-78c4-4fc8-b8c2-a5adaad2ed49` · run `028a9666580c`

**BLOCK: 5 behavior divergence class(es)**: 3 likely-bug, 2 intended.

5 classes in 3 groups of near-duplicates.

- **likely-bug** **[P2] outcome**: input `[["０"]]`
  - base: `{"status": "exc", "exc": "packaging.version.InvalidVersion"}`
  - head: `{"status": "ok", "obs": {"str": "0", "repr": "<Version('0')>", "attr:release": [0], "attr:public": "0"}}`
  - found by: A1/s2, A5/s2, seed, mutation:separators, mutation:edges, batch
  - why: The fast path treats full-width digits as simple versions because they are not in _NON_SIMPLE_VERSION_INDICATORS, then int() parses them, whereas the regex only accepts ASCII digits.
  - near-duplicates: `[["１ .２.３"]]`
- **likely-bug** **[P2] outcome**: input `[["0. 0"]]`
  - base: `{"status": "exc", "exc": "packaging.version.InvalidVersion"}`
  - head: `{"status": "ok", "obs": {"str": "0.0", "repr": "<Version('0.0')>", "attr:release": [0, 0], "attr:public": "0.0"}}`
  - found by: A2/s1, A2/s4, A4/s4, mutation:whitespace-inner
  - why: Internal whitespace is not in the indicator set, so the fast path accepts it; int() ignores surrounding whitespace, but the regex does not allow internal spaces.
  - near-duplicates: `[["１ .２.３"]]`
- **intended** **[P2] outcome**: input `[["1000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000… (4307 chars)`
  - base: `{"status": "exc", "exc": "builtins.ValueError"}`
  - head: `{"status": "exc", "exc": "packaging.version.InvalidVersion"}`
  - found by: mutation:huge-number
  - why: Same reasoning as C4: the new fast‑path wraps any `ValueError` from parsing a very long numeric version into `InvalidVersion`. The base version lets the raw `ValueError` propagate. The PR deliberately normalises the exception type.
  - near-duplicates: `[[" 100000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000… (4312 chars)`

### Attacks planned
- **A1** (4/4 strategies valid, 1 hits): The fast‑path assumes that a version string containing only ASCII digits and dots is a simple numeric version, but it does not verify that the digits are ASCII.
- **A2** (3/4 strategies valid, 2 hits): The fast‑path assumes that a version containing only ASCII digits and dots cannot have surrounding whitespace; it strips the whole string and therefore accepts versions with leading/trailing spaces that the PEP 440 regex would reject.
- **A3** (4/4 strategies valid, 0 hits): The fast‑path assumes a version string consists only of digits and dots, but it only checks a limited set of “non‑simple” characters and misses leading whitespace.
- **A4** (3/4 strategies valid, 1 hits): The fast‑path assumes that surrounding whitespace is not part of the version string and strips it before parsing.
- **A5** (4/4 strategies valid, 1 hits): The fast‑path only checks for the presence of ASCII letters and punctuation; it treats any other characters (including Unicode digits) as “simple” and parses each dot‑separated component with int(), which accepts Unicode decimal digits.

**Cost:** $0.0507 (reasoning $0.0497, volume $0.0010) · **Time:** 93s

### Performance

Screened families (head/base Ir per call at one size; >1 means the change is slower):

- `1.04x` F4 [suspected_slowdown, plan, 100% valid] versions with an epoch marker (N!...) – valid PEP 440
- `1.04x` F2 [suspected_slowdown, plan, 100% valid] post‑release versions (post or -N suffix) – valid PEP 440
- `1.03x` F3 [suspected_slowdown, plan, 100% valid] development releases (devN) – valid PEP 440
- `1.03x` F1 [suspected_slowdown, plan, 100% valid] pre-release versions containing letters a, b, rc (valid PEP 440)
- `1.03x` F5 [suspected_slowdown, plan, 100% valid] versions with a local segment (+local) – valid PEP 440
- `1.02x` F6 [suspected_slowdown, plan, 100% valid] versions that combine several non‑simple markers (epoch, pre, post, dev, local) – valid PEP 440
- `n/a` F4.1 [suspected_slowdown, expand:F4, validity ?] version specifier

Measured in full:

- **F4 [suspected_slowdown, plan] neutral**: head/base Ir per call 1.03x–1.04x across sizes; slope n/a → n/a. versions with an epoch marker (N!...) – valid PEP 440
  - ladder (head/base Ir): n=2 (~10 chars): 1.03x, n=4 (~10 chars): 1.03x, n=16 (~12 chars): 1.04x, n=64 (~12 chars): 1.04x, n=256 (~12 chars): 1.04x, n=1024 (~12 chars): 1.04x, n=4096 (~12 chars): 1.04x
  - search input `["00000!1.0"]`: CPU 1.08x, Ir 1.04x
  - search input `["0!1.0"]`: CPU 1.08x, Ir 1.03x
- **F2 [suspected_slowdown, plan] neutral**: head/base Ir per call 1.04x–1.04x across sizes; slope n/a → n/a. post‑release versions (post or -N suffix) – valid PEP 440
  - ladder (head/base Ir): n=2 (~14 chars): 1.04x, n=4 (~14 chars): 1.04x, n=16 (~16 chars): 1.04x, n=64 (~16 chars): 1.04x, n=256 (~16 chars): 1.04x, n=1024 (~16 chars): 1.04x, n=4096 (~16 chars): 1.04x
- **F3 [suspected_slowdown, plan] neutral**: head/base Ir per call 1.03x–1.03x across sizes; slope n/a → n/a. development releases (devN) – valid PEP 440
  - ladder (head/base Ir): n=2 (~12 chars): 1.03x, n=4 (~14 chars): 1.03x, n=16 (~16 chars): 1.03x, n=64 (~16 chars): 1.03x, n=256 (~16 chars): 1.03x, n=1024 (~16 chars): 1.03x, n=4096 (~16 chars): 1.03x
- **F1 [suspected_slowdown, plan] neutral**: head/base Ir per call 1.03x–1.03x across sizes; slope n/a → n/a. pre-release versions containing letters a, b, rc (valid PEP 440)
  - ladder (head/base Ir): n=2 (~10 chars): 1.03x, n=4 (~10 chars): 1.03x, n=16 (~12 chars): 1.03x, n=64 (~12 chars): 1.03x, n=256 (~12 chars): 1.03x, n=1024 (~12 chars): 1.03x, n=4096 (~12 chars): 1.03x

**Total Nemotron cost:** $0.2404 (proposer $0.0039, reasoning $0.2354, volume $0.0012)  
**Sandbox cost (free during beta):** $10.1823 for 293 Token Factory Sandboxes runs (995.9 s CPU), image `dbe8dafe-78c4-4fc8-b8c2-a5adaad2ed49`