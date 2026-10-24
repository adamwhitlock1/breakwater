## Breakwater audit: `packaging.version:Version`
https://github.com/pypa/packaging `59f183fe90` → `61967cca27` · backend `contree` · image `dbe8dafe-78c4-4fc8-b8c2-a5adaad2ed49` · run `e780ff68654f`

**BLOCK: 6 behavior divergence class(es)**: 4 likely-bug, 2 intended.

6 classes in 5 groups of near-duplicates.

- **likely-bug** **[P2] outcome**: input `[["٠"]]`
  - base: `{"status": "exc", "exc": "packaging.version.InvalidVersion"}`
  - head: `{"status": "ok", "obs": {"str": "0", "repr": "<Version('0')>", "attr:release": [0], "attr:public": "0"}}`
  - found by: A3/s1, A3/s4, seed, mutation:edges, mutation:separators, mutation:unicode-digits
  - why: The fast path accepts Arabic-Indic digits (e.g., '٠') because they are not in the indicator set, while the base version rejects them via the ASCII-only regex. This expands accepted characters unintentionally.
  - near-duplicates: `[["١ .2"]]`
- **likely-bug** **[P2] outcome**: input `[["0 .0"]]`
  - base: `{"status": "exc", "exc": "packaging.version.InvalidVersion"}`
  - head: `{"status": "ok", "obs": {"str": "0.0", "repr": "<Version('0.0')>", "attr:release": [0, 0], "attr:public": "0.0"}}`
  - found by: A1/s4, A1/s3, A5/s2, seed, mutation:whitespace-outer, mutation:whitespace-inner, mutation:equivalents, mutation:separators, batch
  - why: The fast path accepts a version with an internal space (e.g., '0 .0') because space is not in _NON_SIMPLE_VERSION_INDICATORS and strip() only removes leading/trailing whitespace. The base version correctly rejects it via regex. This is an unintended regression.
  - near-duplicates: `[["١ .2"]]`
- **likely-bug** **[P2] outcome**: input `[[["１"]]]`
  - base: `{"status": "exc", "exc": "builtins.TypeError"}`
  - head: `{"status": "exc", "exc": "builtins.AttributeError"}`
  - found by: A2/s2, batch
  - why: The fast path accepts full-width digits (e.g., '１') because they are not in the ASCII-only indicator set, but then an AttributeError occurs (likely due to incomplete initialization). The base version raises TypeError. This change in exception type and acceptance of non-ASCII digits is unintended.
- **intended** **[P2] outcome**: input `[["1000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000… (4309 chars)`
  - base: `{"status": "exc", "exc": "packaging.version.InvalidVersion"}`
  - head: `{"status": "ok", "obs": {"str": "1000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000`
  - found by: mutation:huge-number
  - why: The fast path is designed for all simple versions (only numbers and dots) without length limits. The base version's regex likely hit an internal recursion/length limit, causing InvalidVersion. The new behavior correctly accepts arbitrarily long simple versions per PEP 440.
- **intended** **[P2] outcome**: input `[["1000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000… (4307 chars)`
  - base: `{"status": "exc", "exc": "builtins.ValueError"}`
  - head: `{"status": "exc", "exc": "packaging.version.InvalidVersion"}`
  - found by: mutation:huge-number
  - why: The fast path wraps ValueError from int() into InvalidVersion, matching the library's documented exception for invalid versions. The base version let ValueError escape. This makes error handling consistent and deliberate.

### Attacks planned
- **A1** (3/4 strategies valid, 2 hits): The fast‑path guard assumes that a version lacking the indicator characters contains only ASCII digits and dots, so it splits on '.' and feeds each piece to int().
- **A2** (3/4 strategies valid, 1 hits): The fast‑path guard assumes that any string lacking the indicator characters consists only of ASCII digits and dots, so int() will only ever see ASCII digits.
- **A3** (3/4 strategies valid, 2 hits): The fast‑path assumes `int()` only accepts ASCII decimal digits; it treats any string without the indicator characters as a simple numeric version.
- **A4** (2/4 strategies valid, 0 hits): The fast‑path guard assumes that a version without indicator characters consists solely of ASCII decimal digits, but int() also accepts any Unicode decimal digit.
- **A5** (3/4 strategies valid, 1 hits): The fast‑path guard assumes that a string without indicator characters contains no whitespace inside the release segment.

**Cost:** $0.0402 (reasoning $0.0391, volume $0.0011) · **Time:** 45s

### Performance

Screened families (head/base Ir per call at one size; >1 means the change is slower):

- `1.37x` R4.2 [suspected_slowdown, expand:R4, 67% valid] Trailing numeric sub-label added
- `1.35x` R4.1 [suspected_slowdown, expand:R4, 67% valid] Pre-release label variation
- `1.29x` R4 [suspected_slowdown, archive, 100% valid] Pre-release label changed from 'c5' to 'alpha.1'
- `1.08x` F1 [suspected_slowdown, plan, 100% valid] Long release segment (many dot-separated numbers) ending with a pre‑release marker (e.g. "1.1.1…a1"). The new 
- `1.08x` F5 [suspected_slowdown, plan, 100% valid] many numeric segments followed by a pre‑release marker (e.g. 'a1')
- `1.08x` F4 [suspected_slowdown, plan, 100% valid] Long release segment ending with a development release marker ("dev"). The letters d, e, v are all in the indi
- `1.03x` F6 [suspected_slowdown, plan, 100% valid] Pre‑release versions using the "a" (alpha) marker (e.g. "1.0a1").
- `0.65x` F3 [claimed_speedup, plan, 100% valid] Simple numeric versions (e.g. "1.2.3") – the fast‑path added by the change.
- `0.62x` F2 [claimed_speedup, plan, 100% valid] many numeric segments, no special characters
- `2.24x` R1 [suspected_slowdown, archive, 0% valid] Each numeric chunk is an ascending sequence starting at '0'
- `2.00x` R2 [suspected_slowdown, archive, 0% valid] Invalid version strings that nevertheless contain indicator characters (e.g. a trailing dot followed by a lett
- `2.00x` R3 [suspected_slowdown, archive, 0% valid] invalid strings that look simple (only digits and dots) but contain a non‑numeric segment, e.g. "1.2.x"
- `n/a` R4.3 [suspected_slowdown, expand:R4, validity ?] Long postfix via build metadata increase
- `n/a` F1.1 [suspected_slowdown, expand:F1, validity ?] Long major.minor.patch... sequence followed by development release suffix (.dev)
- `n/a` F1.2 [suspected_slowdown, expand:F1, validity ?] Repeated short segments creating long strings without early indicators
- `n/a` F1.3 [suspected_slowdown, expand:F1, validity ?] Numeric-only versions pushing into post-release parsing territory

Measured in full:

- **R4.2 [suspected_slowdown, expand:R4] slower**: head/base Ir per call 1.05x–2.74x across sizes; slope 0.57 → 0.70. Trailing numeric sub-label added
  - ladder (head/base Ir): n=2 (~14 chars): 1.05x, n=4 (~23 chars): 1.08x, n=16 (~161 chars): 1.37x, n=64 (~2153 chars): 2.17x, n=256 (~33161 chars): 2.74x, n=1024: n/a
  - error: ladder inputs exceed 2000000 chars at n=4096; ladder stops here
- **R4.1 [suspected_slowdown, expand:R4] slower**: head/base Ir per call 1.04x–2.74x across sizes; slope 0.55 → 0.68. Pre-release label variation
  - ladder (head/base Ir): n=2 (~13 chars): 1.04x, n=4 (~22 chars): 1.07x, n=16 (~160 chars): 1.35x, n=64 (~2152 chars): 2.16x, n=256 (~33160 chars): 2.74x, n=1024: n/a
  - error: ladder inputs exceed 2000000 chars at n=4096; ladder stops here
- **R4 [suspected_slowdown, archive] slower**: head/base Ir per call 1.04x–2.51x across sizes; slope 0.69 → 0.78. Pre-release label changed from 'c5' to 'alpha.1'
  - ladder (head/base Ir): n=2 (~16 chars): 1.04x, n=4 (~25 chars): 1.06x, n=16 (~163 chars): 1.29x, n=64 (~2155 chars): 1.98x, n=256 (~33163 chars): 2.51x, n=1024 (~525835 chars): 2.15x
  - error: ladder inputs exceed 2000000 chars at n=4096; ladder stops here
- **F1 [suspected_slowdown, plan] slower**: head/base Ir per call 1.03x–1.14x across sizes; slope 0.80 → 0.82. Long release segment (many dot-separated numbers) ending with a pre‑release marker (e.g. "1.1.1…a1"). The new fast‑path scans the whole string looking for indicator characters before falling back to the regex, so the disjointness check walks the entire long numeric prefix before finding the trailing 'a'.
  - ladder (head/base Ir): n=2 (~9 chars): 1.03x, n=4 (~13 chars): 1.04x, n=16 (~37 chars): 1.08x, n=64 (~133 chars): 1.12x, n=256 (~517 chars): 1.14x, n=1024 (~2053 chars): 1.14x, n=4096 (~8197 chars): 1.14x
  - search input `["1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.… (237 chars)`: CPU 1.14x, Ir 1.13x
  - search input `["1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.1.… (387 chars)`: CPU 1.14x, Ir 1.13x
- **F2 [claimed_speedup, plan] faster**: head/base Ir per call 0.38x–0.91x across sizes; slope 0.79 → 0.92. many numeric segments, no special characters
  - ladder (head/base Ir): n=2 (~7 chars): 0.38x, n=4 (~11 chars): 0.43x, n=16 (~35 chars): 0.62x, n=64 (~131 chars): 0.80x, n=256 (~515 chars): 0.88x, n=1024 (~2051 chars): 0.90x, n=4096 (~8195 chars): 0.91x

**Total Nemotron cost:** $0.1841 (proposer $0.0008, reasoning $0.1820, volume $0.0014)  
**Sandbox cost (free during beta):** $11.9248 for 358 Token Factory Sandboxes runs (1165.3 s CPU), image `dbe8dafe-78c4-4fc8-b8c2-a5adaad2ed49`