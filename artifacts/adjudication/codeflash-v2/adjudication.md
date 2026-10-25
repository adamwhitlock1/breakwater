# Breakwater adjudication

Known issues the audit found: 0 · labelled likely-bug 0 · labelled intended (dangerous miss) 0 · with at least one class labelled intended 0 · total Nemotron cost $0.08

| classes | likely-bug | intended | needs-human |
|---|---|---|---|
| matching a known issue | 0 | 0 | 0 |
| all others (no ground truth) | 4 | 1 | 1 |

| item | known issue | status | class labels | outcome |
|---|---|---|---|---|

## Every class

### Math-Interpreter#1 `Lexer#generate_tokens`: ⚡️ Speed up method `Lexer.generate_number` by 11%

- **likely-bug** [likely-bug 3]: Outcome differs. Input ["1١"]: base raises builtins.Exception, head returns normally.
  - The change replaces the ASCII‑digit check (`self.current_char in DIGITS`) with `str.isdigit()`, which now accepts Unicode digits such as '١'. The PR only claims a speed‑up and does not mention expanding the accepted digit set, so the new acceptance of non‑ASCII digits is an unintended regression.
  - > DIGITS = '0123456789'
  - > -        while self.current_char is not None and (self.current_char in DIGITS or self.current_char == '.'):
- **needs-human** (model abstained) [likely-bug 1, needs-human 2]: Outcome differs. Input ["100000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000... (4305 chars): base raises builtins.Exception, head returns normally.
  - The only difference for the very long all‑zero input is that the old version raises an Exception while the new version succeeds. The provided material does not explain why the old version fails (no test, doc, or changelog mentions this case), so we cannot decide whether the change is intentional or a bug.
- **likely-bug** [likely-bug 3]: Outcome differs. Input ["1١ "]: base raises builtins.Exception, head returns normally.
  - Same Unicode‑digit issue as C1: the old lexer rejects '١' because it is not in `DIGITS`, while the new lexer accepts it via `isdigit()`. The PR does not document expanding the digit repertoire, indicating an unintended behavior change.
  - > DIGITS = '0123456789'
  - > -        while self.current_char is not None and (self.current_char in DIGITS or self.current_char == '.'):

### caddy-feeds#4 `is_excluded`: ⚡️ Speed up function `is_excluded` by 17,376%

- **likely-bug** [likely-bug 3]: Outcome differs. Input [[":"]]: base returns normally, head raises builtins.TypeError.
  - Base version gracefully handles invalid IPs by catching ValueError and returning True; the new @lru_cache decorator introduces a TypeError for the same input, changing documented behavior without any test, doc, or changelog update.
  - >         return True  # Treat invalid IPs as excluded
  - > +@lru_cache(maxsize=1024)

### patterns#12 `sanitize_pattern`: ⚡️ Speed up function `sanitize_pattern` by 11,547%

- **likely-bug** [likely-bug 3]: Outcome differs. Input [[["pattern", "0"]]]: base raises builtins.AttributeError, head raises builtins.TypeError. (neither exception type subclasses the other.)
  - The PR is presented as a pure performance refactor (caching) with no intended behavior change. The new exception type (TypeError) differs from the old (AttributeError) even though the core logic (calling re.escape) is unchanged, indicating an unintended regression.
  - > ⚡️ Speed up function `sanitize_pattern` by 11,547%
  - >     return _sanitize_pattern(pattern)

### rendercv#18 † `get_date_object`: ⚡️ Speed up function `validate_date_field` by 47%

- **intended** [intended 3]: Outcome differs. Input [["!!!!"]]: base raises builtins.TypeError, head raises builtins.ValueError. (neither exception type subclasses the other.)
  - The refactored `get_date_object` now explicitly raises `ValueError` with a clear message for invalid inputs, matching the function’s documented contract, whereas the previous implementation raised an unexpected `TypeError`. The change was a deliberate performance refactor (regex replaced by manual checks) and the new exception type aligns with the library’s own error handling.
  - >         message = (            
  - >             raise ValueError(message)

† merged after Nemotron 3 Ultra's release (2026-06-04): no training-data contamination possible.