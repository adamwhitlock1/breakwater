# Breakwater adjudication

Known issues the audit found: 10 · labelled likely-bug 8 · labelled intended (dangerous miss) 2 · with at least one class labelled intended 4 · total Nemotron cost $0.46

| classes | likely-bug | intended | needs-human |
|---|---|---|---|
| matching a known issue | 19 | 3 | 0 |
| all others (no ground truth) | 9 | 11 | 3 |

| item | known issue | status | class labels | outcome |
|---|---|---|---|---|
| #1030 | unicode-lowercase | verified | likely-bug, likely-bug, likely-bug | **likely-bug** |
| #1082 | oversized-int-exception | verified | intended | **intended** |
| 1082@61967cca | unicode-digits | verified | likely-bug, likely-bug, intended | **likely-bug** |
| 1082@61967cca | inner-whitespace | verified | likely-bug, intended, likely-bug | **likely-bug** |
| 1082@61967cca | oversized-int-exception | verified | intended, intended | **intended** |
| #1108 | dedup-equality | verified | likely-bug | **likely-bug** |
| #1108 | dedup-str-len | verified | likely-bug, likely-bug, likely-bug, likely-bug, likely-bug, likely-bug, likely-bug, likely-bug | **likely-bug** |
| #1108 | old-pickles-break-comparison | verified | likely-bug, likely-bug | **likely-bug** |
| #1116 | old-pickles-fail-to-load | verified | likely-bug | **likely-bug** |
| #1147 | marker-pickle | candidate | likely-bug | **likely-bug** |

## Every class

### #1030 `canonicalize_name`: perf: translate for canonicalize_name

- **likely-bug** [likely-bug 3] · known: unicode-lowercase: Output `value` differs. Input ["İ"]: base gives "i̇", head gives "İ".
  - The PR aims only to speed up canonicalize_name while preserving the original semantics (lower‑casing per PEP 503). The new implementation only lower‑cases ASCII letters, so non‑ASCII characters like ‘İ’ are not lower‑cased, changing the output.
  - > Emulates ``re.sub(r
  - > perf: translate for canonicalize_name
- **likely-bug** [likely-bug 3] · known: unicode-lowercase: Output `value` differs. Input ["İ "]: base gives "i̇ ", head gives "İ ".
  - Same root cause as C1 – the translation table lacks mappings for non‑ASCII letters, so trailing characters are left unchanged, diverging from the original ``.lower()`` behavior.
  - > Emulates ``re.sub(r
  - > perf: translate for canonicalize_name
- **likely-bug** [likely-bug 3] · known: unicode-lowercase: Output `value` differs. Input ["İ\u0000"]: base gives "i̇\u0000", head gives "İ\u0000".
  - Identical to C1/C2; the null byte is preserved but the capital İ is not lower‑cased, contrary to the documented intent to emulate ``.lower()``.
  - > Emulates ``re.sub(r
  - > perf: translate for canonicalize_name
- **likely-bug** [likely-bug 3]: Outcome differs. Input [["İ"]]: base raises builtins.TypeError, head raises builtins.AttributeError. (neither exception type subclasses the other.)
  - The change introduces a different exception type (AttributeError vs TypeError) when processing the same input, which is not mentioned in the PR title, docs, or tests and therefore is an unintended regression.
  - > perf: translate for canonicalize_name
  - > Emulates ``re.sub(r
- **likely-bug** [likely-bug 3]: Relation `a > b` differs for a = target(*["İ"]), b = target(*["py3"]): base False, head True.
  - Ordering changes because the new code no longer lower‑cases Unicode letters, so comparison results differ from the original specification that required ``.lower()``.
  - > Emulates ``re.sub(r
  - > perf: translate for canonicalize_name
- **likely-bug** [likely-bug 3]: Relation `a > b` differs for a = target(*["ẞ"]), b = target(*["K"]): base True, head False.
  - Same as C5 – the missing Unicode lower‑casing flips the ordering for characters such as ‘ẞ’ and ‘K’.
  - > Emulates ``re.sub(r
  - > perf: translate for canonicalize_name
- **likely-bug** [likely-bug 3]: Relation `a < b` differs for a = target(*["İ"]), b = target(*["py3"]): base True, head False.
  - Opposite ordering result caused by the same loss of Unicode lower‑casing.
  - > Emulates ``re.sub(r
  - > perf: translate for canonicalize_name
- **likely-bug** [likely-bug 3]: Relation `a < b` differs for a = target(*["ẞ"]), b = target(*["K"]): base False, head True.
  - Ordering reversal for ‘ẞ’ vs ‘K’ stems from the new implementation not applying ``.lower()`` to non‑ASCII letters.
  - > Emulates ``re.sub(r
  - > perf: translate for canonicalize_name

### #1032 `Marker`: perf: add __slots__ to Nodes

- **likely-bug** [likely-bug 3]: An object built by base from ["os_name == 'foo'"], pickled, then unpickled by head fails to load: builtins.AttributeError.
  - Adding __slots__ to the Node hierarchy changes the object layout, breaking unpickling of instances created by older pickled Marker objects. The PR is a performance refactor with no tests, docs, or changelog noting the compatibility break.
  - > __slots__ = ()
  - > perf: add __slots__ to Nodes

### #1064 `canonicalize_name`: perf: dual replace

- **intended** [intended 3]: Output `value` differs. Input ["Ä"]: base gives "Ä", head gives "ä".
  - The docstring states that canonicalize_name should emulate `re.sub(r'[-_.]+', '-', name).lower()` from PEP 503, which lower‑cases the whole string including non‑ASCII characters. The new implementation uses `name.lower().replace(... )`, matching that specification.
  - > Emulates ``re.sub(r'[-_.]+', '-', name).lower()`` from PEP 503
  - > # Much faster than re, and even faster than str.translate
- **intended** [intended 3]: Output `value` differs. Input ["Á "]: base gives "Á ", head gives "á ".
  - Same reasoning as C1: the intended behavior per the docstring is to lower‑case after replacing `_` and `.` with `-`. The new code does exactly that, handling Unicode characters such as `Á`.
  - > Emulates ``re.sub(r'[-_.]+', '-', name).lower()`` from PEP 503
  - > # Much faster than re, and even faster than str.translate
- **intended** [intended 3]: Output `value` differs. Input ["Á\u0000"]: base gives "Á\u0000", head gives "á\u0000".
  - The change makes canonicalize_name apply Unicode lower‑casing (via `str.lower()`), which follows the documented emulation of `... .lower()` from PEP 503. This affects characters like `Á` and the null byte unchanged.
  - > Emulates ``re.sub(r'[-_.]+', '-', name).lower()`` from PEP 503
  - > # Much faster than re, and even faster than str.translate
- **intended** [intended 3]: Relation `a > b` differs for a = target(*["Á"]), b = target(*["İ"]): base False, head True.
  - Ordering differences arise because the new implementation lower‑cases Unicode letters (e.g., `Á` → `á`, `İ` → `i`) before comparison, matching the documented canonical form. The old version left such letters unchanged, causing different sort order.
  - > Emulates ``re.sub(r'[-_.]+', '-', name).lower()`` from PEP 503
  - > # Much faster than re, and even faster than str.translate
- **intended** [intended 3]: Relation `a > b` differs for a = target(*["İ"]), b = target(*["Ä"]): base True, head False.
  - Same as C4: the new Unicode‑aware lower‑casing changes relative ordering, which is the intended canonical form per the docstring.
  - > Emulates ``re.sub(r'[-_.]+', '-', name).lower()`` from PEP 503
  - > # Much faster than re, and even faster than str.translate
- **intended** [intended 3]: Relation `a < b` differs for a = target(*["Á"]), b = target(*["İ"]): base True, head False.
  - The `<` relation flips for the same reason: canonicalize_name now produces lower‑cased Unicode strings as specified, altering lexical ordering.
  - > Emulates ``re.sub(r'[-_.]+', '-', name).lower()`` from PEP 503
  - > # Much faster than re, and even faster than str.translate
- **intended** [intended 3]: Relation `a < b` differs for a = target(*["İ"]), b = target(*["Ä"]): base False, head True.
  - Consistent with C6; the new behavior follows the documented emulation of lower‑casing after replacement, changing ordering for Unicode characters.
  - > Emulates ``re.sub(r'[-_.]+', '-', name).lower()`` from PEP 503
  - > # Much faster than re, and even faster than str.translate

### #1082 `Version`: perf: Add fast path for parsing simple versions (digits and dots only)

- **likely-bug** [likely-bug 2, needs-human 1]: Outcome differs. Input [["1"]]: base raises builtins.TypeError, head raises builtins.AttributeError. (neither exception type subclasses the other.)
  - The fast‑path added in the PR returns early after setting a handful of private attributes (e.g., `self._epoch = 0; self._pre = None; …; self._key_cache = None; return`). The base version took the full regex path and raised a built‑in `TypeError` for the input `['1']`; the new fast path returns early and later code apparently accesses an attribute that was not initialised, causing a built‑in `AttributeError`. Since the two built‑in exception types are unrelated (neither subclasses the other), this change of exception type is an unintended regression.
  - > if _SIMPLE_VERSION_INDICATORS.issuperset(version):
  - >         self._release = tuple(map(int, version.split('.')))
- **intended** [intended 3] · known: oversized-int-exception: Outcome differs. Input ["100000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000... (4305 chars): base raises builtins.ValueError, head raises packaging.version.InvalidVersion. (packaging.version.InvalidVersion is a subclass of builtins.ValueError.)
  - The PR adds a fast‑path for simple dotted‑digit versions that parses with `split('.')` and `map(int, …)`. When that fast path fails it catches `ValueError` and raises `packaging.version.InvalidVersion`, a subclass of `ValueError`. The test diff explicitly adds cases that “trigger the fast path (digits/dots only)” and expects `InvalidVersion`. This change of exception type (subclass of the original `ValueError`) is the intended improvement.
  - >     self._release = tuple(map(int, version.split('.')))
  - > except ValueError:   raise InvalidVersion(f'Invalid version: {version!r}') from None

### 1082@61967cca `Version`: perf: fast path for simple versions (intermediate commit 61967cca)

- **likely-bug** [likely-bug 3] · known: unicode-digits: Outcome differs. Input ["０"]: base raises packaging.version.InvalidVersion, head returns normally.
  - The fast‑path treats any character not in `_NON_SIMPLE_VERSION_INDICATORS` as a simple numeric version. The set deliberately lists ASCII letters and punctuation (e.g. `!+-ABCDEHILOPRSTVW_abcdehiloprstvw`) but does not include full‑width digits such as `０`. Consequently `Version('０')` is accepted by the fast‑path (`int('０')` succeeds) whereas the original regex rejects it, a non‑conformant change.
  - > _NON_SIMPLE_VERSION_INDICATORS = frozenset('!+-ABCDEHILOPRSTVW_abcdehiloprstvw')
  - > if _NON_SIMPLE_VERSION_INDICATORS.isdisjoint(version):
- **likely-bug** [likely-bug 3] · known: unicode-digits, inner-whitespace: Outcome differs. Input ["０ "]: base raises packaging.version.InvalidVersion, head returns normally.
  - A trailing space is not in `_NON_SIMPLE_VERSION_INDICATORS`, so the fast‑path triggers, strips the space and parses the full‑width digit. The original regex does not allow whitespace, so the new behaviour accepts an invalid version string.
  - > _NON_SIMPLE_VERSION_INDICATORS = frozenset('!+-ABCDEHILOPRSTVW_abcdehiloprstvw')
  - > if _NON_SIMPLE_VERSION_INDICATORS.isdisjoint(version):
- **intended** [intended 2, needs-human 1] · known: inner-whitespace, oversized-int-exception: Outcome differs. Input [" 10000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000... (4307 chars): base raises builtins.ValueError, head raises packaging.version.InvalidVersion. (packaging.version.InvalidVersion is a subclass of builtins.ValueError.)
  - The fast‑path explicitly converts a `ValueError` from the integer parsing into `InvalidVersion` (`except ValueError: raise InvalidVersion(...)`). When the fast‑path is taken and the integer conversion fails, the new code raises `InvalidVersion` instead of letting the original `ValueError` propagate, which matches the observed change.
  - >     self._release = tuple(map(int, version.strip().split('.')))
  - > except ValueError: raise InvalidVersion(f'Invalid version: {version!r}') from None
- **intended** [intended 2, needs-human 1] · known: unicode-digits, oversized-int-exception: Outcome differs. Input ["100000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000... (4308 chars): base raises packaging.version.InvalidVersion, head returns normally.
  - The fast‑path is designed to accept simple dot‑separated numeric versions without invoking the full regex. A very long all‑digit version passes the `_NON_SIMPLE_VERSION_INDICATORS.isdisjoint` test and is parsed successfully, whereas the original regex path rejects it (raising `InvalidVersion`). This is the performance optimisation the PR targets.
  - > _NON_SIMPLE_VERSION_INDICATORS = frozenset('!+-ABCDEHILOPRSTVW_abcdehiloprstvw')
  - > if _NON_SIMPLE_VERSION_INDICATORS.isdisjoint(version):
- **likely-bug** [likely-bug 3] · known: inner-whitespace: Outcome differs. Input [" 1. 2.3 "]: base raises packaging.version.InvalidVersion, head returns normally.
  - The fast‑path calls `version.strip()` before splitting on dots, thereby accepting leading/trailing whitespace (e.g. `' 1.2.3 '`). PEP 440 does not permit whitespace in a version string, and the original regex rejects it. The change was not mentioned in the PR description, indicating an unintended relaxation.
  - > if _NON_SIMPLE_VERSION_INDICATORS.isdisjoint(version):
  - > self._release = tuple(map(int, version.strip().split('.')))

### #1108 `SpecifierSet`: perf: SpecifierSet use tuple instead of frozenset for `_specs`

- **likely-bug** [likely-bug 3] · known: dedup-str-len: Output `len` differs. Input [">=01.0,>=1.0"]: base gives 1, head gives 2.
  - The change deduplicates on raw specifier strings before parsing, so semantically equal specifiers like '>=01.0' and '>=1.0' are no longer merged. This changes __len__ and __str__ behavior (C1 shows len 1 → 2).
  - > -            self._specs = frozenset(map(Specifier, split_specifiers))
  - > +            # Deduplicate strings first.
- **likely-bug** [likely-bug 3] · known: dedup-str-len: Output `len` differs. Input [">= 1.0,>=1.0"]: base gives 1, head gives 2.
  - Same root cause: deduplication now uses literal strings, so '>= 1.0' and '>=1.0' are kept separate, changing length and string representation.
  - > -            self._specs = frozenset(map(Specifier, split_specifiers))
  - > +            # Deduplicate strings first.
- **likely-bug** [likely-bug 3] · known: dedup-str-len: Output `len` differs. Input [" >=1.0,>=1.0.0 "]: base gives 1, head gives 2.
  - Whitespace differences in the raw specifier strings (' >=1, e.g. ' >=1.0' vs '>=1.0.0') are no longer collapsed after parsing, so __len__ and __str__ diverge.
  - > -            self._specs = frozenset(map(Specifier, split_specifiers))
  - > +            # Deduplicate strings first.
- **likely-bug** [likely-bug 3] · known: dedup-str-len: Output `len` differs. Input [">=1000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000... (4322 chars): base gives 2, head gives 3.
  - Long version strings that are semantically equivalent (e.g., trailing zeros) are kept distinct because deduplication happens before canonicalisation.
  - > -            self._specs = frozenset(map(Specifier, split_specifiers))
  - > +            # Deduplicate strings first.
- **likely-bug** [likely-bug 3] · known: dedup-str-len: Output `str` differs. Input [">=01.0,>=1.0"]: base gives ">=01.0", head gives ">=01.0,>=1.0".
  - __str__ now reflects the tuple order with duplicates retained, changing the string representation from '>=01.0' to '>=01.0,>=1.0'.
  - > -            self._specs = frozenset(map(Specifier, split_specifiers))
  - > +            # Deduplicate strings first.
- **likely-bug** [likely-bug 3] · known: dedup-str-len: Output `str` differs. Input [">= 1.0,>=1.0"]: base gives ">=1.0", head gives ">=1.0,>=1.0".
  - Same deduplication regression changes __str__ output, showing both '>= 1.0' and '>=1.0'.
  - > -            self._specs = frozenset(map(Specifier, split_specifiers))
  - > +            # Deduplicate strings first.
- **likely-bug** [likely-bug 3] · known: dedup-str-len: Output `str` differs. Input [" >=1.0,>=1.0.0 "]: base gives ">=1.0", head gives ">=1.0,>=1.0.0".
  - Whitespace and version‑normalisation differences are no longer collapsed, so __str__ includes both specifiers.
  - > -            self._specs = frozenset(map(Specifier, split_specifiers))
  - > +            # Deduplicate strings first.
- **likely-bug** [likely-bug 3] · known: dedup-str-len: Output `str` differs. Input [">=1000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000... (4322 chars): base gives ">=1.0.0,>=100000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000... (4314 chars), head gives ">=1.0,>=1.0.0,>=100000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000... (4320 chars).
  - Large version strings that are semantically identical after canonicalisation are kept separate, inflating both length and string representation.
  - > -            self._specs = frozenset(map(Specifier, split_specifiers))
  - > +            # Deduplicate strings first.
- **needs-human** (model abstained) [needs-human 2]: Outcome differs. Input [">=1000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000... (4315 chars): base raises builtins.AssertionError, head returns normally.
  - Base raises AssertionError on a very large version string while head returns normally. The PR is described as a performance refactor with no mention of fixing large‑version parsing. The change in behavior is undocumented, so a human should decide whether the new permissive parsing is intended.
- **needs-human** (model abstained) [needs-human 2]: Outcome differs. Input [">=1000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000... (4318 chars): base raises builtins.AssertionError, head returns normally.
  - Same pattern as C1 – an AssertionError on a huge version string disappears in the new code. No test, doc, or changelog entry mentions fixing large‑version handling, so the intent is unclear.
- **needs-human** (model abstained) [needs-human 2]: Outcome differs. Input ["<=1000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000... (4311 chars): base raises builtins.ValueError, head returns normally.
  - Base raises ValueError on a very large “<=” specifier; head accepts it. The PR does not mention changing version‑parsing semantics, so the reviewer should decide whether the new permissive behaviour is desired.
- **likely-bug** [likely-bug 2] · known: dedup-equality: Relation `a == b` differs for a = target(*[">=01.0,>=1.0"]), b = target(*[">=1.0,>=1.0"]): base True, head False.
  - Equality semantics changed: the new __eq__ first checks length of the internal `_specs` tuple (which now reflects raw‑string deduplication) before comparing sorted specs. Two SpecifierSet objects that are semantically equal (e.g., `>=01.0,>=1.0` vs `>=1.0,>=1.0`) now compare False because their raw‑string tuples have different lengths. This is a regression introduced by the refactor.
  - > if len(self._specs) != len(other._specs): return False
  - > return self._sort_specs() == other._sort_specs()
- **likely-bug** [likely-bug 2]: Relation `hash(a) == hash(b)` differs for a = target(*[">=01.0,>=1.0"]), b = target(*[">=1.0,>=1.0"]): base True, head False.
  - Hash now uses the sorted `_specs` tuple (`hash(self._sort_specs())`). Because the new constructor deduplicates on raw strings, two semantically equal SpecifierSet objects can have different tuple lengths/contents, causing `hash(a) != hash(b)`. This breaks the hash‑equals contract.
  - > return hash(self._sort_specs())
  - > def __hash__(self) -> int: return hash(self._sort_specs())
- **likely-bug** [likely-bug 2] · known: old-pickles-break-comparison: An object built by base from [">=01.0,>=1.0"], pickled, then unpickled by head loads, but no longer equals a freshly built head object (== gives False).
  - The refactor added a new slot `_sorted` (`__slots__ = (..., '_sorted', '_specs')`). Objects pickled by the old code lack this attribute; when unpickled by the new code and compared to a freshly constructed object, an AttributeError is raised. This breaks pickle compatibility.
  - > __slots__ = (
  - >     '_prereleases',
- **likely-bug** [likely-bug 2] · known: old-pickles-break-comparison: An object built by base from [""], pickled, then unpickled by head loads, but comparing it with a freshly built head object fails: <exc:builtins.AttributeError>.
  - Same root cause as C6: the added `_sorted` slot is missing on a pickled legacy instance, leading to an AttributeError when the new code accesses it during comparison. This is an unintended regression in serialization compatibility.
  - > __slots__ = (
  - >     '_prereleases',

### #1115 `Version`: perf: skip hash property

- **likely-bug** [likely-bug 3]: An object built by base from ["0"], pickled, then unpickled by head loads, but no longer equals a freshly built head object (== gives False).
  - The PR introduces a cached `_key_cache` in `__hash__` but does not update the equality comparison (which relies on `_key`). After pickling a base‑version object (which stores `_key_cache = None`) and unpickling it with the new code, the cached hash key is computed lazily while equality still uses the uncached key, causing two equal logical versions to compare unequal.
  - > perf: skip hash property
  - >     def __hash__(self) -> int:

### #1116 `Version`: perf: Overhaul `_cmpkey` to remove use of custom objects

- **likely-bug** [likely-bug 3] · known: old-pickles-fail-to-load: An object built by base from ["0"], pickled, then unpickled by head fails to load: builtins.ModuleNotFoundError.
  - The change is a performance‑focused refactor (new __slots__, cached _key_cache, faster comparison methods) and the only backward‑compatibility note is a comment about internal _Version usage, not about pickling. No test or changelog entry mentions preserving pickle compatibility, so the unpickling failure is an unintended regression.
  - > # Backward compatibility for internals before 26.0. Do not use.
  - > # This is a hot function, so not calling self.base_version

### #1147 `Marker`: perf: add __slots__ to Marker

- **likely-bug** [likely-bug 3] · known: marker-pickle: An object built by base from ["\"b\" > \"a\""], pickled, then unpickled by head fails to load: builtins.AttributeError.
  - The PR adds `__slots__ = (('_markers',))` to `Marker` as a performance change (see PR title and added line). This change breaks backward compatibility for pickled `Marker` objects: an instance pickled by the old class (without `__slots__`) cannot be unpickled by the new class, raising `AttributeError`. The PR has no tests, docs, or changelog entry addressing pickling, so the regression is unintended.
  - > perf: add __slots__ to Marker
  - > __slots__ = ( '_markers', )

### #1236 † `parse_tag`: perf: simply work done in parse_tag a bit

- **intended** [intended 3]: Outcome differs. Input ["Ensure platform tags normalize spaces to underscores."]: base raises builtins.ValueError, head raises packaging.tags.InvalidTag. (packaging.tags.InvalidTag is a subclass of builtins.ValueError.)
  - The head version's docstring for `parse_tag` explicitly states it raises `InvalidTag` on empty tag components, and the `InvalidTag` class is documented as added in version 26.3. The change from a generic `ValueError` to the more specific `InvalidTag` subclass is therefore deliberate.
  - > .. versionadded:: 26.3
  - > Raises :class:`InvalidTag` on empty tag components.
- **intended** [intended 3]: Outcome differs. Input ["."]: base raises builtins.ValueError, head raises packaging.tags.InvalidTag. (packaging.tags.InvalidTag is a subclass of builtins.ValueError.)
  - Same reasoning as C1: the new `InvalidTag` exception is documented as the intended error for empty tag components, replacing the generic `ValueError`.
  - > .. versionadded:: 26.3
  - > Raises :class:`InvalidTag` on empty tag components.
- **intended** [intended 3]: Outcome differs. Input [""]: base raises builtins.ValueError, head raises packaging.tags.InvalidTag. (packaging.tags.InvalidTag is a subclass of builtins.ValueError.)
  - Same reasoning: the introduction of `InvalidTag` with a versionadded note and updated docstring shows the new exception type is intentional.
  - > .. versionadded:: 26.3
  - > Raises :class:`InvalidTag` on empty tag components.
- **intended** [intended 3]: Outcome differs. Input [".\u0000"]: base raises builtins.ValueError, head raises packaging.tags.InvalidTag. (packaging.tags.InvalidTag is a subclass of builtins.ValueError.)
  - Identical to the other cases; the head version documents raising `InvalidTag` for empty components, indicating the change is deliberate.
  - > .. versionadded:: 26.3
  - > Raises :class:`InvalidTag` on empty tag components.

† merged after Nemotron 3 Ultra's release (2026-06-04): no training-data contamination possible.