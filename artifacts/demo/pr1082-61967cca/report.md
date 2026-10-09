## Breakwater audit: `packaging.version:Version`
https://github.com/pypa/packaging `59f183fe90` → `61967cca27` · backend `docker` · image `bw-pair:348e2d05c100a5f9` · run `c1a7799be95f`

**BLOCK: 6 behavior divergence class(es)**: 6 likely-bug.

- **likely-bug** **[P2] outcome**: input `[["0. 0"]]`
  - base: `{"status": "exc", "exc": "packaging.version.InvalidVersion"}`
  - head: `{"status": "ok", "obs": {"str": "0.0", "repr": "<Version('0.0')>", "attr:release": [0, 0], "attr:public": "0.0"}}`
  - found by: A3/s3, A4/s3, mutation:whitespace-inner
  - why: Fast‑path added in src/packaging/version.py strips only leading/trailing whitespace and then splits on '.'; internal spaces such as "0. 0" pass the fast path (since space is not in _NON_SIMPLE_VERSION_INDICATORS) and int(" 0") succeeds, whereas the original PEP‑440 regex rejected internal spaces, raising InvalidVersion. This change was not documented and appears unintentional.
- **likely-bug** **[P2] outcome**: input `[[" ١.2.3 "]]`
  - base: `{"status": "exc", "exc": "packaging.version.InvalidVersion"}`
  - head: `{"status": "ok", "obs": {"str": "1.2.3", "repr": "<Version('1.2.3')>", "attr:release": [1, 2, 3], "attr:public": "1.2.3"}}`
  - found by: mutation:unicode-digits
  - why: The fast‑path treats any characters not in _NON_SIMPLE_VERSION_INDICATORS as “simple”. Arabic‑Indic digit “١” is not in that set, so the version " ١.2.3 " passes the fast path after stripping spaces, and int("١") succeeds (Python accepts Unicode digits). The original PEP 440 regex only accepts ASCII digits, so it raised InvalidVersion. This acceptance of non‑ASCII digits is unintended.
- **likely-bug** **[P2] outcome**: input `[[" 100000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000… (4313 chars)`
  - base: `{"status": "exc", "exc": "builtins.ValueError"}`
  - head: `{"status": "exc", "exc": "packaging.version.InvalidVersion"}`
  - found by: mutation:huge-number
  - why: A very long version consisting only of digits and dots contains no indicator characters, so the fast path parses it into a huge tuple of ints and returns successfully. The original regex‑based validation rejected it with a ValueError (InvalidVersion). Accepting arbitrarily long releases bypasses PEP 440 validation and is an unintended performance shortcut.
- **likely-bug** **[P2] outcome**: input `[["1000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000… (4309 chars)`
  - base: `{"status": "exc", "exc": "builtins.ValueError"}`
  - head: `{"status": "exc", "exc": "packaging.version.InvalidVersion"}`
  - found by: mutation:huge-number
  - why: Same reasoning as C3 – an extremely long numeric version passes the fast path because it contains only digits and dots, while the original regex raised ValueError. The fast path unintentionally relaxes the version length limits.
- **likely-bug** **[P2] outcome**: input `[["١.0.0"]]`
  - base: `{"status": "exc", "exc": "packaging.version.InvalidVersion"}`
  - head: `{"status": "ok", "obs": {"str": "1.0.0", "repr": "<Version('1.0.0')>", "attr:release": [1, 0, 0], "attr:public": "1.0.0"}}`
  - found by: mutation:unicode-digits
  - why: Arabic‑Indic digit “١” is not in the indicator set, so the fast path accepts "١.0.0" after stripping and splitting, converting the Unicode digit with int(). The original regex only allowed ASCII digits, raising InvalidVersion. Accepting non‑ASCII digits is a regression.
- **likely-bug** **[P2] outcome**: input `[["　 10000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000… (4315 chars)`
  - base: `{"status": "exc", "exc": "builtins.ValueError"}`
  - head: `{"status": "exc", "exc": "packaging.version.InvalidVersion"}`
  - found by: mutation:huge-number
  - why: A version with a leading ideographic space and a massive numeric component contains no indicator characters; strip() removes the leading space and the fast path parses the huge numeric segments successfully. The original validator rejected it with ValueError. This is another unintended relaxation of validation.

### Attacks planned
- **A1** (3/4 strategies valid, 0 hits): The fast‑path assumes the version string contains only ASCII digits and dots, so it strips leading/trailing whitespace before parsing.
- **A2** (2/4 strategies valid, 0 hits): The fast‑path assumes a simple numeric version never has trailing zero components, so it skips the normal trailing‑zero stripping logic.
- **A3** (3/4 strategies valid, 1 hits): The fast‑path assumes that surrounding whitespace is harmless because it strips the string before parsing, while the original regex validates the raw string.
- **A4** (4/4 strategies valid, 1 hits): The fast‑path assumes the version string contains only ASCII digits and dots, so it strips any Unicode whitespace characters before parsing.
- **A5** (3/4 strategies valid, 0 hits): The fast‑path assumes numeric dot‑only versions are already in normalized form, so it omits the trailing‑zero stripping step.

**Cost:** $0.0474 (reasoning $0.0464, volume $0.0010) · **Time:** 50s

### Performance

Screened families (head/base Ir per call at one size; >1 means the change is slower):

- `1.32x` R3.2 [suspected_slowdown, expand:R3, 100% valid] Pre-release label changed from 'c5' to 'alpha.1'
- `1.29x` R3 [suspected_slowdown, archive, 100% valid] Each numeric chunk consists of repeated digits (`'9'*i`) instead of zero-padded numbers
- `1.27x` R4 [suspected_slowdown, archive, 100% valid] Each numeric chunk increases digit count linearly while keeping total chunks fixed
- `1.23x` R3.3 [suspected_slowdown, expand:R3, 100% valid] Repeating triple-digit pattern in each chunk
- `0.64x` F2 [suspected_slowdown, plan, 100% valid] performance_optimization
- `0.44x` F6 [suspected_slowdown, plan, 100% valid] When the fast path is taken (pure numeric versions), the version string is stripped, split on ‘.’, and each co
- `2.38x` R3.1 [suspected_slowdown, expand:R3, 0% valid] Each numeric chunk is an ascending sequence starting at '0'
- `2.09x` R1 [suspected_slowdown, archive, 0% valid] Invalid version strings that nevertheless contain indicator characters (e.g. a trailing dot followed by a lett
- `2.09x` R2 [suspected_slowdown, archive, 0% valid] invalid strings that look simple (only digits and dots) but contain a non‑numeric segment, e.g. "1.2.x"
- `1.09x` F4 [suspected_slowdown, plan, 0% valid] The fast‑path guard uses a Python‑level frozenset `isdisjoint` check that iterates over every character of the
- `1.00x` F3 [claimed_speedup, plan, 0% valid] Fast‑path for simple numeric versions
- `0.99x` F1 [claimed_speedup, plan, 0% valid] Added a fast‑path that detects “simple” numeric versions (only digits and dots) with a fast frozenset disjoint
- `0.92x` F5 [suspected_slowdown, plan, 12% valid] Accidental acceptance of whitespace in simple versions
- `n/a` R4.1 [suspected_slowdown, expand:R4, validity ?] Each segment contains repeated identical digits instead of unique numbers
- `n/a` R4.2 [suspected_slowdown, expand:R4, validity ?] Segments grow exponentially in digit size but share a common prefix
- `n/a` R4.3 [suspected_slowdown, expand:R4, validity ?] Chunks stay small but are separated by variable-length non-digit markers

Measured in full:

- **R3.2 [suspected_slowdown, expand:R3] slower**: head/base Ir per call 1.04x–2.44x across sizes; slope 0.70 → 0.78. Pre-release label changed from 'c5' to 'alpha.1'
  - ladder (head/base Ir): n=2 (~16 chars): 1.04x, n=4 (~25 chars): 1.07x, n=16 (~163 chars): 1.32x, n=64 (~2155 chars): 1.93x, n=256 (~33163 chars): 2.44x, n=1024 (~525835 chars): 2.23x
  - error: ladder inputs exceed 2000000 chars at n=4096; ladder stops here
- **R3 [suspected_slowdown, archive] slower**: head/base Ir per call 1.04x–2.44x across sizes; slope 0.67 → 0.75. Each numeric chunk consists of repeated digits (`'9'*i`) instead of zero-padded numbers
  - ladder (head/base Ir): n=2 (~10 chars): 1.04x, n=4 (~19 chars): 1.07x, n=16 (~157 chars): 1.29x, n=64 (~2149 chars): 1.93x, n=256 (~33157 chars): 2.44x, n=1024 (~525829 chars): 2.23x
  - error: ladder inputs exceed 2000000 chars at n=4096; ladder stops here
- **R4 [suspected_slowdown, archive] slower**: head/base Ir per call 1.04x–2.76x across sizes; slope 0.63 → 0.73. Each numeric chunk increases digit count linearly while keeping total chunks fixed
  - ladder (head/base Ir): n=2 (~10 chars): 1.04x, n=4 (~19 chars): 1.07x, n=16 (~157 chars): 1.27x, n=64 (~2149 chars): 1.89x, n=256 (~33157 chars): 2.50x, n=1024 (~525829 chars): 2.76x
  - search input `["1.02.003.0004.00005.000006.0000007.00000008.000000009.0000000010.000… (280 chars)`: CPU 4.44x, Ir 1.39x
  - search input `["1.02.003.0004.00005.000006.0000007.00000008.000000009.0000000010.000… (439 chars)`: CPU 3.56x, Ir 1.48x
  - error: ladder inputs exceed 2000000 chars at n=4096; ladder stops here
- **R3.3 [suspected_slowdown, expand:R3] slower**: head/base Ir per call 1.03x–2.41x across sizes; slope 0.67 → 0.76. Repeating triple-digit pattern in each chunk
  - ladder (head/base Ir): n=2 (~16 chars): 1.03x, n=4 (~25 chars): 1.05x, n=16 (~163 chars): 1.23x, n=64 (~2155 chars): 1.88x, n=256 (~33163 chars): 2.41x, n=1024 (~525835 chars): 2.21x
  - error: ladder inputs exceed 2000000 chars at n=4096; ladder stops here

**Total Nemotron cost:** $0.1118 (proposer $0.0009, reasoning $0.1093, volume $0.0016)