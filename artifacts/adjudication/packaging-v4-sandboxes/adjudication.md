# Breakwater adjudication

Known issues the audit found: 10 · labelled likely-bug 8 · labelled intended (dangerous miss) 1 · with at least one class labelled intended 1 · total Nemotron cost $0.35

| classes | likely-bug | intended | needs-human |
|---|---|---|---|
| matching a known issue | 17 | 1 | 2 |
| all others (no ground truth) | 13 | 0 | 7 |

| item | known issue | status | class labels | outcome |
|---|---|---|---|---|
| #1030 | unicode-lowercase | verified | likely-bug, likely-bug, likely-bug | **likely-bug** |
| #1082 | oversized-int-exception | verified | intended | **intended** |
| 1082@61967cca | unicode-digits | verified | likely-bug, likely-bug | **likely-bug** |
| 1082@61967cca | inner-whitespace | verified | likely-bug, likely-bug, needs-human | **likely-bug** |
| 1082@61967cca | oversized-int-exception | verified | needs-human, needs-human | **needs-human** |
| #1108 | dedup-equality | verified | likely-bug | **likely-bug** |
| #1108 | dedup-str-len | verified | likely-bug, likely-bug, likely-bug, likely-bug, likely-bug, likely-bug | **likely-bug** |
| #1108 | old-pickles-break-comparison | verified | likely-bug, likely-bug | **likely-bug** |
| #1116 | old-pickles-fail-to-load | verified | likely-bug | **likely-bug** |
| #1147 | marker-pickle | candidate | likely-bug | **likely-bug** |

## Every class

### #1030 `canonicalize_name`: perf: translate for canonicalize_name

- **likely-bug** [intended 1, likely-bug 2] · known: unicode-lowercase: Output `value` differs. Input ["İ"]: base gives "i̇", head gives "İ".
  - The PR is described as a performance refactor with no intention to change Unicode handling. The new code replaces Unicode‑aware `.lower()` with an ASCII‑only translation table, causing non‑ASCII letters like “İ” to remain uppercase. This is an unintended regression.
  - > # About 2x faster, safe since packages only support alphanumeric characters
  - > # Emulates ``re.sub(r
- **likely-bug** [intended 1, likely-bug 2] · known: unicode-lowercase: Output `value` differs. Input ["İ "]: base gives "i̇ ", head gives "İ ".
  - Same root cause as C1 – the ASCII‑only translation leaves the dotted capital I unchanged, while the original implementation lower‑cased it. The change was not documented as a behavior change.
  - > # About 2x faster, safe since packages only support alphanumeric characters
  - > # Emulates ``re.sub(r
- **likely-bug** [intended 1, likely-bug 2] · known: unicode-lowercase: Output `value` differs. Input ["İ\u0000"]: base gives "i̇\u0000", head gives "İ\u0000".
  - The null character does not affect the case conversion; the difference again stems from the loss of Unicode lower‑casing. No test or docs indicate this was desired.
  - > # About 2x faster, safe since packages only support alphanumeric characters
  - > # Emulates ``re.sub(r
- **likely-bug** [intended 1, likely-bug 2]: Relation `a > b` differs for a = target(*["İ"]), b = target(*["ÖÄ"]): base False, head True.
  - Ordering changes are a direct consequence of the case‑conversion regression for non‑ASCII letters. The PR did not intend to alter sorting semantics.
  - > # About 2x faster, safe since packages only support alphanumeric characters
  - > # Emulates ``re.sub(r
- **likely-bug** [intended 1, likely-bug 2]: Relation `a > b` differs for a = target(*["Ω"]), b = target(*["ẞ"]): base True, head False.
  - Same as C4 – the new ASCII‑only mapping flips the relative order of “Ω” and “ẞ”. This is an unintended side‑effect of the performance rewrite.
  - > # About 2x faster, safe since packages only support alphanumeric characters
  - > # Emulates ``re.sub(r
- **likely-bug** [intended 1, likely-bug 2]: Relation `a < b` differs for a = target(*["İ"]), b = target(*["ÖÄ"]): base True, head False.
  - The `<` relation mirrors the `>` change in C4; it diverges because the canonical form no longer lower‑cases non‑ASCII letters. No specification change accompanies the PR.
  - > # About 2x faster, safe since packages only support alphanumeric characters
  - > # Emulates ``re.sub(r
- **likely-bug** [intended 1, likely-bug 2]: Relation `a < b` differs for a = target(*["Ω"]), b = target(*["ẞ"]): base False, head True.
  - Analogous to C5, the `<` relation flips due to loss of Unicode lower‑casing. The PR’s intent was purely performance, not ordering semantics.
  - > # About 2x faster, safe since packages only support alphanumeric characters
  - > # Emulates ``re.sub(r

### #1064 `canonicalize_name`: perf: dual replace

- **likely-bug** [intended 1, likely-bug 2]: Output `value` differs. Input ["Á"]: base gives "Á", head gives "á".
  - The PR is titled a performance improvement with no intent to change Unicode handling; no tests/docs were updated.
  - > perf: dual replace
  - > Much faster than re, and even faster than str.translate
- **likely-bug** [intended 1, likely-bug 2]: Output `value` differs. Input ["Á "]: base gives "Á ", head gives "á ".
  - Same unintended Unicode lower‑casing introduced by the performance refactor.
  - > perf: dual replace
  - > Much faster than re, and even faster than str.translate
- **likely-bug** [intended 1, likely-bug 2]: Output `value` differs. Input ["Á\u0000"]: base gives "Á\u0000", head gives "á\u0000".
  - Null character unchanged but preceding letter lower‑cased, an accidental side‑effect of the new implementation.
  - > perf: dual replace
  - > Much faster than re, and even faster than str.translate
- **likely-bug** [intended 1, likely-bug 2]: Relation `a > b` differs for a = target(*["Á"]), b = target(*["ẞ"]): base False, head True.
  - Ordering changed because Unicode letters are now lower‑cased, not intended by the perf‑only PR.
  - > perf: dual replace
  - > Much faster than re, and even faster than str.translate
- **likely-bug** [intended 1, likely-bug 2]: Relation `a > b` differs for a = target(*["ẞ"]), b = target(*["Ω"]): base True, head False.
  - Relation flipped due to unintended case folding of non‑ASCII characters.
  - > perf: dual replace
  - > Much faster than re, and even faster than str.translate
- **likely-bug** [intended 1, likely-bug 2]: Relation `a < b` differs for a = target(*["Á"]), b = target(*["ẞ"]): base True, head False.
  - Same root cause: lower() now affects Unicode, altering comparison results.
  - > perf: dual replace
  - > Much faster than re, and even faster than str.translate
- **likely-bug** [intended 1, likely-bug 2]: Relation `a < b` differs for a = target(*["ẞ"]), b = target(*["Ω"]): base False, head True.
  - Comparison ordering changed unintentionally by the performance rewrite.
  - > perf: dual replace
  - > Much faster than re, and even faster than str.translate

### #1082 `Version`: perf: Add fast path for parsing simple versions (digits and dots only)

- **intended** [intended 3] · known: oversized-int-exception: Outcome differs. Input ["100000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000... (4309 chars): base raises builtins.ValueError, head raises packaging.version.InvalidVersion. (packaging.version.InvalidVersion is a subclass of builtins.ValueError.)
  - The PR adds a fast‑path for versions that contain only digits and dots. In that path it explicitly catches a `ValueError` from `int()` conversion and re‑raises it as `packaging.version.InvalidVersion`. This makes the exception type more specific and matches the library’s own error hierarchy, so the new behavior is deliberate.
  - > if _SIMPLE_VERSION_INDICATORS.issuperset(version):
  - >                 self._release = tuple(map(int, version.split('.')))

### 1082@61967cca `Version`: perf: fast path for simple versions (intermediate commit 61967cca)

- **likely-bug** [likely-bug 3] · known: unicode-digits: Outcome differs. Input ["٠"]: base raises packaging.version.InvalidVersion, head returns normally.
  - The fast path accepts Unicode digits (e.g., Arabic-Indic '٠') because `int()` supports them, while the original regex only matches ASCII `[0-9]`. This expands accepted input beyond PEP 440 without documentation or tests.
  - > _NON_SIMPLE_VERSION_INDICATORS = frozenset('!+-ABCDEHILOPRSTVW_abcdehiloprstvw')
  - >         if _NON_SIMPLE_VERSION_INDICATORS.isdisjoint(version):
- **likely-bug** [likely-bug 3]: Outcome differs. Input [["..0"]]: base raises builtins.TypeError, head raises builtins.AttributeError. (neither exception type subclasses the other.)
  - For non-string input (a list), the fast path bypasses the regex and calls `.strip()` on the list, raising `AttributeError` instead of the original `TypeError`. The PR does not intend to change error types for invalid input types.
  - >         if _NON_SIMPLE_VERSION_INDICATORS.isdisjoint(version):
  - >                 self._release = tuple(map(int, version.strip().split('.')))
- **likely-bug** [likely-bug 3] · known: inner-whitespace: Outcome differs. Input ["1 .2"]: base raises packaging.version.InvalidVersion, head returns normally.
  - The fast path accepts spaces in the version string (e.g., '1 .2') because `strip()` removes leading/trailing spaces and `int()` ignores spaces around digits, whereas the regex rejects spaces. This is an unintended relaxation of the version syntax.
  - >         if _NON_SIMPLE_VERSION_INDICATORS.isdisjoint(version):
  - >                 self._release = tuple(map(int, version.strip().split('.')))
- **likely-bug** [likely-bug 3] · known: unicode-digits, inner-whitespace: Outcome differs. Input ["١ .2"]: base raises packaging.version.InvalidVersion, head returns normally.
  - Combines Unicode digit and space acceptance (as in C1 and C3). The fast path's use of `int()` and `strip()` permits characters the regex forbids, expanding the accepted language without intent.
  - > _NON_SIMPLE_VERSION_INDICATORS = frozenset('!+-ABCDEHILOPRSTVW_abcdehiloprstvw')
  - >                 self._release = tuple(map(int, version.strip().split('.')))
- **needs-human** (no majority) [intended 1, likely-bug 1, needs-human 1] · known: inner-whitespace, oversized-int-exception: Outcome differs. Input ["100000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000... (4307 chars): base raises packaging.version.InvalidVersion, head returns normally.
  - The fast path accepts extremely long numbers that the regex rejects (likely due to regex engine limits). The PR is a perf refactor; no intent to change valid version set. PEP 440 doesn't forbid long numbers but the original behavior was to reject them.
- **needs-human** (no majority) [intended 1, likely-bug 1, needs-human 1] · known: oversized-int-exception: Outcome differs. Input ["100000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000... (4309 chars): base raises builtins.ValueError, head raises packaging.version.InvalidVersion. (packaging.version.InvalidVersion is a subclass of builtins.ValueError.)
  - Both error but with different exception types (ValueError vs InvalidVersion) for a very long number. The fast path catches ValueError and wraps in InvalidVersion; the base path lets ValueError propagate. The PR is a perf refactor; no intent to change exception types.

### #1108 `SpecifierSet`: perf: SpecifierSet use tuple instead of frozenset for `_specs`

- **likely-bug** [likely-bug 3] · known: dedup-str-len: Output `len` differs. Input [">=1.0,>=1.0.0"]: base gives 1, head gives 2.
  - SpecifierSet now deduplicates on raw strings (dict.fromkeys) instead of on canonical Specifier equality, so two specifiers that are equal after canonicalization (e.g. '>=1.0' and '>=1.0.0') are both kept, changing len().
  - > self._specs: tuple[Specifier, ...] = tuple(map(Specifier, dict.fromkeys(split_specifiers)))
  - > Specifier('==1.2.3') == Specifier('== 1.2.3.0') True
- **likely-bug** [likely-bug 3] · known: dedup-str-len: Output `len` differs. Input [">= 1.0,>=1.0.0"]: base gives 1, head gives 2.
  - Same root cause as C1 – whitespace differences do not affect string‑level deduplication, so both specifiers remain.
  - > self._specs: tuple[Specifier, ...] = tuple(map(Specifier, dict.fromkeys(split_specifiers)))
  - > Specifier('==1.2.3') == Specifier('== 1.2.3.0') True
- **likely-bug** [likely-bug 3] · known: dedup-str-len: Output `len` differs. Input [" >=1.0,>=1.0.0 "]: base gives 1, head gives 2.
  - Leading/trailing spaces are stripped before dict.fromkeys, but the two specifiers are still distinct strings, so both survive.
  - > split_specifiers = [s.strip() for s in specifiers.split(',') if s.strip()]
  - > Specifier('==1.2.3') == Specifier('== 1.2.3.0') True
- **likely-bug** [likely-bug 3] · known: dedup-str-len: Output `str` differs. Input [">=1.0,>=1.0.0"]: base gives ">=1.0", head gives ">=1.0,>=1.0.0".
  - __str__ joins the sorted tuple of specs; with two retained specifiers the string now contains both.
  - > return ','.join(str(s) for s in self._sort_specs())
  - > self._specs: tuple[Specifier, ...] = tuple(map(Specifier, dict.fromkeys(split_specifiers)))
- **likely-bug** [likely-bug 3] · known: dedup-str-len: Output `str` differs. Input [">= 1.0,>=1.0.0"]: base gives ">=1.0", head gives ">=1.0,>=1.0.0".
  - Same as C4 – whitespace does not change the fact that two distinct strings survive deduplication.
  - > return ','.join(str(s) for s in self._sort_specs())
  - > self._specs: tuple[Specifier, ...] = tuple(map(Specifier, dict.fromkeys(split_specifiers)))
- **likely-bug** [likely-bug 3] · known: dedup-str-len: Output `str` differs. Input [" >=1.0,>=1.0.0 "]: base gives ">=1.0", head gives ">=1.0,>=1.0.0".
  - Same as C4/C5 – extra spaces are stripped before dict.fromkeys, leaving two entries.
  - > return ','.join(str(s) for s in self._sort_specs())
  - > self._specs: tuple[Specifier, ...] = tuple(map(Specifier, dict.fromkeys(split_specifiers)))
- **needs-human** (model abstained) [needs-human 3]: Outcome differs. Input [">=1000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000... (4317 chars): base raises builtins.AssertionError, head returns normally.
  - The change from frozenset to tuple does not modify the comparison logic for a single '>=' specifier, yet the observed AssertionError disappears. No documentation or test change explains this, so the cause is unclear.
- **likely-bug** [likely-bug 3] · known: dedup-equality: Relation `a == b` differs for a = target(*[">=1.0,>=1.0.0"]), b = target(*[">=1.0.0,>=1.0.0"]): base True, head False.
  - Equality of SpecifierSet now depends on the tuple length after string‑level deduplication; the two sets have different lengths (2 vs 1) and therefore compare False, whereas the old frozenset canonicalized them to a single element and compared True.
  - > if len(self._specs) != len(other._specs): return False
  - > self._specs: tuple[Specifier, ...] = tuple(map(Specifier, dict.fromkeys(split_specifiers)))
- **likely-bug** [likely-bug 3]: Relation `hash(a) == hash(b)` differs for a = target(*[">=1.0,>=1.0.0"]), b = target(*[">=1.0.0,>=1.0.0"]): base True, head False.
  - Specifier equality is based on a canonical form that strips trailing zeros (e.g., '>=1.0' == '>=1.0.0'). The old SpecifierSet stored specifiers in a frozenset, which deduplicated equal specifiers, while the new implementation deduplicates only on the raw strings (dict.fromkeys(split_specifiers)), so two equal specifiers remain as two items. Consequently the hash of a set containing '>=1.0,>=1.0.0' differs from one containing '>=1.0.0,>=1.0' under the new code.
  - > return self._canonical_spec == other._canonical_spec
  - > canonicalize_version(spec_version, strip_trailing_zero=(operator != '~='))
- **likely-bug** [likely-bug 3] · known: old-pickles-break-comparison: An object built by base from [">=1.0,>=1.0.0"], pickled, then unpickled by head loads, but no longer equals a freshly built head object (== gives False).
  - The change adds a new slot '_sorted' and makes __hash__/__eq__ depend on it via _sort_specs. Objects pickled by the old version lack this slot; when unpickled by the new version the attribute is missing, causing an AttributeError during comparison.
  - > __slots__ = ( '_prereleases', '_sorted', '_specs')
  - > def __hash__(self) -> int: return hash(self._sort_specs())
- **likely-bug** [likely-bug 3] · known: old-pickles-break-comparison: An object built by base from [""], pickled, then unpickled by head loads, but comparing it with a freshly built head object fails: <exc:builtins.AttributeError>.
  - Same root cause as C2: the new '_sorted' slot is absent on objects pickled by the old implementation (including an empty SpecifierSet), leading to AttributeError when the unpickled object participates in equality checks.
  - > __slots__ = ( '_prereleases', '_sorted', '_specs')
  - > def __eq__(self, other: object) -> bool: ... return self._sort_specs() == other._sort_specs()

### #1116 `Version`: perf: Overhaul `_cmpkey` to remove use of custom objects

- **likely-bug** [likely-bug 3] · known: old-pickles-fail-to-load: An object built by base from ["0"], pickled, then unpickled by head fails to load: builtins.ModuleNotFoundError.
  - The PR removes the `_structures` module and its `Infinity`/`NegativeInfinity` sentinel classes, which were used in the comparison key (`_cmpkey`) of `Version` objects. Pickled `Version` objects from the old version may contain references to these sentinel classes in their cached `_key_cache`. Unpickling them in the new version fails with `ModuleNotFoundError` because the module no longer exists. This is an unintended regression for users who rely on pickling `Version` objects across versions; the PR presents itself as a performance refactor and does not mention pickling compatibility in tests,
  - > -@typing.final
  - > -class InfinityType:

### #1147 `Marker`: perf: add __slots__ to Marker

- **likely-bug** [likely-bug 2, needs-human 1] · known: marker-pickle: An object built by base from ["\"b\" > \"a\""], pickled, then unpickled by head fails to load: builtins.AttributeError.
  - Adding __slots__ changes the pickling format; objects pickled by the base version (which had a __dict__) cannot be unpickled by the head version (which expects slot storage), causing an AttributeError. The PR introduces the slots without any compatibility handling, and the change is described only as a performance tweak.
  - > __slots__ = ( '_markers', )
  - > perf: add __slots__ to Marker

### #1236 † `parse_tag`: perf: simply work done in parse_tag a bit

- **needs-human** (no majority) [intended 1, likely-bug 1, needs-human 1]: Outcome differs. Input [""]: base raises builtins.ValueError, head raises packaging.tags.InvalidTag. (packaging.tags.InvalidTag is a subclass of builtins.ValueError.)
  - The PR is described as a performance refactor, but the change turns a plain ValueError (from unpacking a tag that doesn't have three components) into the library‑specific InvalidTag. No test, doc, or changelog entry mentions this new error type, so existing callers that expect a ValueError for malformed tags could be affected.
- **needs-human** (no majority) [intended 1, likely-bug 1, needs-human 1]: Outcome differs. Input ["-"]: base raises builtins.ValueError, head raises packaging.tags.InvalidTag. (packaging.tags.InvalidTag is a subclass of builtins.ValueError.)
  - Same reasoning as C1: the refactor changes the exception type for a tag like '-' that lacks three components, raising InvalidTag instead of the original ValueError, without any documented intention.
- **needs-human** (no majority) [intended 1, likely-bug 1, needs-human 1]: Outcome differs. Input ["- "]: base raises builtins.ValueError, head raises packaging.tags.InvalidTag. (packaging.tags.InvalidTag is a subclass of builtins.ValueError.)
  - Input '- ' also lacks three components; the refactor now raises InvalidTag where the original code raised ValueError. No indication this was intended.
- **needs-human** (no majority) [intended 1, likely-bug 1, needs-human 1]: Outcome differs. Input ["- "]: base raises builtins.ValueError, head raises packaging.tags.InvalidTag. (packaging.tags.InvalidTag is a subclass of builtins.ValueError.)
  - The non‑breaking‑space variant '- ' behaves like '- ' and now raises InvalidTag instead of ValueError, an undocumented change introduced by the performance refactor.
- **needs-human** (no majority) [intended 1, likely-bug 1, needs-human 1]: Outcome differs. Input ["\u001b-"]: base raises builtins.ValueError, head raises packaging.tags.InvalidTag. (packaging.tags.InvalidTag is a subclass of builtins.ValueError.)
  - The tag containing a control character and a single hyphen ('<U+001B>-') likewise triggers the new InvalidTag path rather than the original ValueError, with no PR justification.
- **needs-human** (no majority) [intended 1, likely-bug 1, needs-human 1]: Outcome differs. Input ["-ç"]: base raises builtins.ValueError, head raises packaging.tags.InvalidTag. (packaging.tags.InvalidTag is a subclass of builtins.ValueError.)
  - The tag '-ç' (missing interpreter component) now raises InvalidTag instead of ValueError, a behavior change not mentioned in the PR, tests, docs, or changelog.

† merged after Nemotron 3 Ultra's release (2026-06-04): no training-data contamination possible.