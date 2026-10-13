# Breakwater adjudication

Known issues the audit found: 0 · labelled likely-bug 0 · labelled intended (dangerous miss) 0 · with at least one class labelled intended 0 · total Nemotron cost $0.06

| classes | likely-bug | intended | needs-human |
|---|---|---|---|
| matching a known issue | 0 | 0 | 0 |
| all others (no ground truth) | 6 | 0 | 0 |

| item | known issue | status | class labels | outcome |
|---|---|---|---|---|

## Every class

### Math-Interpreter#1 `Lexer#generate_tokens`: ⚡️ Speed up method `Lexer.generate_number` by 11%

- **likely-bug** [likely-bug 3]: Outcome differs. Input ["0٠"]: base raises builtins.Exception, head returns normally.
  - The PR is described as a pure performance improvement with no documentation or tests indicating a change in accepted numeric literals. The change replaces an explicit ASCII‑digit check (`in DIGITS`) with `str.isdigit()`, which now accepts Unicode digits such as Arabic‑Indic numbers, causing the lexer to succeed on inputs it previously rejected.
  - > ⚡️ Speed up method `Lexer.generate_number` by 11%
  - > DIGITS = '0123456789'
- **likely-bug** [likely-bug 2, needs-human 1]: Outcome differs. Input ["100000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000... (4305 chars): base raises builtins.Exception, head returns normally.
  - Same reasoning as C1: the performance‑only PR unintentionally broadens digit acceptance via `isdigit()`, so a very long numeric string containing non‑ASCII digits now parses without error whereas the base version raised an exception.
  - > ⚡️ Speed up method `Lexer.generate_number` by 11%
  - > DIGITS = '0123456789'
- **likely-bug** [likely-bug 3]: Outcome differs. Input ["1١ "]: base raises builtins.Exception, head returns normally.
  - Identical to C1/C2: the refactor swaps an explicit ASCII‑digit whitelist for `isdigit()`, letting a trailing Arabic‑Indic digit be consumed as part of a number and avoiding the “Illegal character” exception that the original code produced.
  - > ⚡️ Speed up method `Lexer.generate_number` by 11%
  - > DIGITS = '0123456789'

### caddy-feeds#4 `is_excluded`: ⚡️ Speed up function `is_excluded` by 17,376%

- **likely-bug** [likely-bug 3]: Outcome differs. Input [["0.0.0.0/31"]]: base returns normally, head raises builtins.TypeError.
  - The change adds an @lru_cache(maxsize=1024) decorator to `is_excluded`. The `maxsize` argument was introduced in Python 3.9; on earlier versions the decorator call itself raises a TypeError, causing the function to fail when invoked. The PR does not include any tests, docs, or changelog entries to justify or guard this change.
  - > +@lru_cache(maxsize=1024)
  - > None: this PR changes no tests, docs or changelog.

### rendercv#18 † `get_date_object`: ⚡️ Speed up function `validate_date_field` by 47%

- **likely-bug** [intended 1, likely-bug 2]: Outcome differs. Input [[]]: base raises builtins.TypeError, head raises builtins.ValueError. (neither exception type subclasses the other.)
  - The refactor replaced regex‑based validation with manual length/character checks. For a non‑string input (e.g. an empty list) the old code called `re.fullmatch` which raises `TypeError`; the new code falls through to the final `else` branch and raises `ValueError`. The exception type change is not documented or tested, so callers that catch `TypeError` would break.
  - > _YMD_PATTERN.fullmatch(date):
  - > _Y_PATTERN.fullmatch(date):
- **likely-bug** [likely-bug 3]: Outcome differs. Input [["present", "present", "´¢¯", "´¢¯"]]: base raises builtins.TypeError, head raises builtins.AttributeError. (neither exception type subclasses the other.)
  - With a list argument the old version again hit `re.fullmatch` and raised `TypeError`. The new version reaches `elif len(date) == 4 and date.isdigit():`; a list has no `isdigit` attribute, causing an `AttributeError`. This unintended change in exception type is a regression.
  - > _YMD_PATTERN.fullmatch(date):
  - > _Y_PATTERN.fullmatch(date):

† merged after Nemotron 3 Ultra's release (2026-06-04): no training-data contamination possible.