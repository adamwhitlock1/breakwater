# Breakwater adjudication

Known issues the audit found: 10 · labelled likely-bug 8 · labelled intended (dangerous miss) 1 · with at least one class labelled intended 3 · total Nemotron cost $0.39

| classes | likely-bug | intended | needs-human |
|---|---|---|---|
| matching a known issue | 15 | 3 | 1 |
| all others (no ground truth) | 12 | 16 | 0 |

| item | known issue | status | class labels | outcome |
|---|---|---|---|---|
| #1030 | unicode-lowercase | verified | likely-bug, likely-bug, likely-bug | **likely-bug** |
| #1082 | oversized-int-exception | verified | intended | **intended** |
| 1082@61967cca | unicode-digits | verified | likely-bug, likely-bug | **likely-bug** |
| 1082@61967cca | inner-whitespace | verified | likely-bug, likely-bug, intended, needs-human | **likely-bug** |
| 1082@61967cca | oversized-int-exception | verified | intended, intended, needs-human | **needs-human** |
| #1108 | dedup-equality | verified | likely-bug | **likely-bug** |
| #1108 | dedup-str-len | verified | likely-bug, likely-bug, likely-bug, likely-bug | **likely-bug** |
| #1108 | old-pickles-break-comparison | verified | likely-bug, likely-bug | **likely-bug** |
| #1116 | old-pickles-fail-to-load | verified | likely-bug | **likely-bug** |
| #1147 | marker-pickle | candidate | likely-bug | **likely-bug** |

## Every class

### #1030 `canonicalize_name`: perf: translate for canonicalize_name

- **likely-bug** [likely-bug 3] · known: unicode-lowercase: Output `value` differs. Input ["İ"]: base gives "i̇", head gives "İ".
  - The change replaces Unicode‑aware ``.lower()`` with an ASCII‑only translate table, so non‑ASCII letters like 'İ' are no longer lower‑cased. The PR is described only as a performance refactor and the new comment says it "Emulates … .lower()`` from PEP 503", indicating the old Unicode behaviour was expected.
  - > +    # Emulates ``re.sub(r"[-_.]+", "-", name).lower()`` from PEP 503
  - > -    value = _canonicalize_regex.sub("-", name).lower()
- **likely-bug** [likely-bug 3] · known: unicode-lowercase: Output `value` differs. Input [" À"]: base gives " à", head gives " À".
  - Same root cause as C1 – the translate table only maps ASCII A‑Z, leaving characters such as 'À' unchanged, whereas the original ``.lower()`` would case‑fold them.
  - > +    # Emulates ``re.sub(r"[-_.]+", "-", name).lower()`` from PEP 503
  - > -    value = _canonicalize_regex.sub("-", name).lower()
- **likely-bug** [likely-bug 3] · known: unicode-lowercase: Output `value` differs. Input ["\u001bÀ"]: base gives "\u001bà", head gives "\u001bÀ".
  - The control character ``\u001b`` is untouched by both versions, but the following 'À' is no longer lower‑cased because the new implementation lacks Unicode case folding.
  - > +    # Emulates ``re.sub(r"[-_.]+", "-", name).lower()`` from PEP 503
  - > -    value = _canonicalize_regex.sub("-", name).lower()
- **likely-bug** [likely-bug 3]: Outcome differs. Input [[]]: base raises builtins.TypeError, head raises builtins.AttributeError. (neither exception type subclasses the other.)
  - Both versions reject a non‑string input, but the exception type changes from ``TypeError`` (from ``.lower()``) to ``AttributeError`` (from ``.translate``). The PR makes no mention of altering error semantics.
  - > +    value = name.translate(_canonicalize_table)
  - > -    value = _canonicalize_regex.sub("-", name).lower()
- **likely-bug** [likely-bug 3]: Relation `a > b` differs for a = target(*["ẞ"]), b = target(*["K"]): base True, head False.
  - Ordering changes because characters like 'ẞ' and 'K' are no longer lower‑cased; the new code only folds ASCII letters, breaking the previous total‑ordering semantics.
  - > +    # Emulates ``re.sub(r"[-_.]+", "-", name).lower()`` from PEP 503
  - > -    value = _canonicalize_regex.sub("-", name).lower()
- **likely-bug** [likely-bug 3]: Relation `a > b` differs for a = target(*["K"]), b = target(*["py3"]): base False, head True.
  - Same as C5 – the loss of Unicode case folding flips the comparison result for 'K' vs 'py3'.
  - > +    # Emulates ``re.sub(r"[-_.]+", "-", name).lower()`` from PEP 503
  - > -    value = _canonicalize_regex.sub("-", name).lower()
- **likely-bug** [likely-bug 3]: Relation `a < b` differs for a = target(*["ẞ"]), b = target(*["K"]): base False, head True.
  - Mirroring C5, the ``<`` relation flips because the new implementation does not lower‑case non‑ASCII letters.
  - > +    # Emulates ``re.sub(r"[-_.]+", "-", name).lower()`` from PEP 503
  - > -    value = _canonicalize_regex.sub("-", name).lower()
- **likely-bug** [likely-bug 3]: Relation `a < b` differs for a = target(*["K"]), b = target(*["py3"]): base True, head False.
  - Mirroring C6, the ``<`` relation flips for the same reason.
  - > +    # Emulates ``re.sub(r"[-_.]+", "-", name).lower()`` from PEP 503
  - > -    value = _canonicalize_regex.sub("-", name).lower()

### #1032 `Marker`: perf: add __slots__ to Nodes

- **likely-bug** [likely-bug 3]: An object built by base from ["extra== 'test'"], pickled, then unpickled by head fails to load: builtins.AttributeError.
  - The PR adds __slots__ to the internal node classes (Node, Variable, Value, Op) for performance, but does not address pickle compatibility. Existing pickled Marker objects (which contain these node instances) now raise AttributeError when unpickled because the new __slots__ prevent restoration of the instance __dict__. No tests, docs, or changelog mention this change, indicating it is an unintended regression.
  - > perf: add __slots__ to Nodes
  - >     __slots__ = ("value",)

### #1064 `canonicalize_name`: perf: dual replace

- **intended** [intended 2, likely-bug 1]: Output `value` differs. Input ["Α"]: base gives "Α", head gives "α".
  - The new implementation follows the documented spec (lower‑casing the whole name) which the old translate‑table did not.
  - > # Emulates ``re.sub(r"[-_.]+", "-", name).lower()`` from PEP 503
  - > # Much faster than re, and even faster than str.translate
- **intended** [intended 2, likely-bug 1]: Output `value` differs. Input [" À"]: base gives " À", head gives " à".
  - Same reasoning as C1 – the change makes canonicalize_name apply Unicode lower‑casing as the docstring specifies.
  - > # Emulates ``re.sub(r"[-_.]+", "-", name).lower()`` from PEP 503
  - > # Much faster than re, and even faster than str.translate
- **intended** [intended 2, likely-bug 1]: Output `value` differs. Input ["\u001bÀ"]: base gives "\u001bÀ", head gives "\u001bà".
  - Consistent with the documented behavior of lower‑casing the entire string.
  - > # Emulates ``re.sub(r"[-_.]+", "-", name).lower()`` from PEP 503
  - > # Much faster than re, and even faster than str.translate
- **intended** [intended 2, likely-bug 1]: Relation `a == b` differs for a = target(*["İ"]), b = target(*["i̇"]): base False, head True.
  - Equality changes stem from the same Unicode lower‑casing introduced to match the spec.
  - > # Emulates ``re.sub(r"[-_.]+", "-", name).lower()`` from PEP 503
  - > # Much faster than re, and even faster than str.translate
- **intended** [intended 2, likely-bug 1]: Relation `a > b` differs for a = target(*["K"]), b = target(*["ı"]): base True, head False.
  - Ordering differences are a direct result of the intended Unicode case‑folding change.
  - > # Emulates ``re.sub(r"[-_.]+", "-", name).lower()`` from PEP 503
  - > # Much faster than re, and even faster than str.translate
- **intended** [intended 2, likely-bug 1]: Relation `a > b` differs for a = target(*["Ω"]), b = target(*["K"]): base False, head True.
  - Same as C5 – ordering follows the new lower‑casing semantics.
  - > # Emulates ``re.sub(r"[-_.]+", "-", name).lower()`` from PEP 503
  - > # Much faster than re, and even faster than str.translate
- **intended** [intended 2, likely-bug 1]: Relation `hash(a) == hash(b)` differs for a = target(*["İ"]), b = target(*["i̇"]): base False, head True.
  - Hash equality follows from the new canonical forms produced by lower‑casing.
  - > # Emulates ``re.sub(r"[-_.]+", "-", name).lower()`` from PEP 503
  - > # Much faster than re, and even faster than str.translate
- **intended** [intended 2, likely-bug 1]: Relation `a < b` differs for a = target(*["K"]), b = target(*["ı"]): base False, head True.
  - Less‑than comparison changes due to the intended Unicode lower‑casing behavior.
  - > # Emulates ``re.sub(r"[-_.]+", "-", name).lower()`` from PEP 503
  - > # Much faster than re, and even faster than str.translate
- **intended** [intended 2, likely-bug 1]: Relation `a < b` differs for a = target(*["Ω"]), b = target(*["K"]): base True, head False.
  - Same rationale as C8 – ordering follows the spec‑aligned implementation.
  - > # Emulates ``re.sub(r"[-_.]+", "-", name).lower()`` from PEP 503
  - > # Much faster than re, and even faster than str.translate

### #1082 `Version`: perf: Add fast path for parsing simple versions (digits and dots only)

- **intended** [intended 3] · known: oversized-int-exception: Outcome differs. Input ["100000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000... (4305 chars): base raises builtins.ValueError, head raises packaging.version.InvalidVersion. (packaging.version.InvalidVersion is a subclass of builtins.ValueError.)
  - The PR adds a fast‑path that parses simple “digit‑and‑dot” version strings. It catches a ValueError from the fast parse and re‑raises packaging.version.InvalidVersion, turning a generic ValueError into the project’s own InvalidVersion type. The added tests (e.g. "1..0", "1.0.", "1..2.3", " .1.0", "1.0a 1", etc.) expect InvalidVersion to be raised, confirming the new behavior is intended.
  - > _SIMPLE_VERSION_INDICATORS = frozenset(".0123456789")
  - > +            # Invalid versions that trigger the fast path (digits/dots only)

### 1082@61967cca `Version`: perf: fast path for simple versions (intermediate commit 61967cca)

- **likely-bug** [likely-bug 3] · known: unicode-digits: Outcome differs. Input ["١"]: base raises packaging.version.InvalidVersion, head returns normally.
  - Fast‑path accepts Arabic‑Indic digit “١” because it is not in _NON_SIMPLE_VERSION_INDICATORS and int('١') succeeds, so an invalid PEP 440 version is accepted whereas the base version raises InvalidVersion.
  - > _NON_SIMPLE_VERSION_INDICATORS = frozenset("!+-ABCDEHILOPRSTVW_abcdehiloprstvw")
  - > if _NON_SIMPLE_VERSION_INDICATORS.isdisjoint(version):
- **likely-bug** [likely-bug 3]: Outcome differs. Input [["0.0"]]: base raises builtins.TypeError, head raises builtins.AttributeError. (neither exception type subclasses the other.)
  - Passing a list (['0.0']) triggers the fast‑path because the list is iterable and disjoint from the indicator set, then version.strip() raises AttributeError instead of the base TypeError – a change in exception type for invalid input.
  - > if _NON_SIMPLE_VERSION_INDICATORS.isdisjoint(version):
  - >     self._release = tuple(map(int, version.strip().split(".")))
- **likely-bug** [likely-bug 3] · known: inner-whitespace: Outcome differs. Input ["0. 0"]: base raises packaging.version.InvalidVersion, head returns normally.
  - Version string "0. 0" contains a space, which is not in the indicator set, so the fast‑path parses it (int(" 0") succeeds) and accepts an invalid PEP 440 version that the base rejects.
  - > _NON_SIMPLE_VERSION_INDICATORS = frozenset("!+-ABCDEHILOPRSTVW_abcdehiloprstvw")
  - > if _NON_SIMPLE_VERSION_INDICATORS.isdisjoint(version):
- **likely-bug** [likely-bug 3] · known: unicode-digits, inner-whitespace: Outcome differs. Input ["١ .٢.٣"]: base raises packaging.version.InvalidVersion, head returns normally.
  - String "١ .٢.٣" contains only Arabic digits, spaces and dots – none are in the indicator set – so the fast‑path accepts it, while the base version correctly raises InvalidVersion.
  - > _NON_SIMPLE_VERSION_INDICATORS = frozenset("!+-ABCDEHILOPRSTVW_abcdehiloprstvw")
  - > if _NON_SIMPLE_VERSION_INDICATORS.isdisjoint(version):
- **intended** [intended 2, needs-human 1] · known: oversized-int-exception: Outcome differs. Input ["100000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000... (4305 chars): base raises builtins.ValueError, head raises packaging.version.InvalidVersion. (packaging.version.InvalidVersion is a subclass of builtins.ValueError.)
  - The fast‑path deliberately catches ValueError from int conversion and re‑raises InvalidVersion, normalising the exception type for overly large numeric segments.
  - >     self._release = tuple(map(int, version.strip().split(".")))
  - > except ValueError:
- **intended** [intended 2, needs-human 1] · known: inner-whitespace, oversized-int-exception: Outcome differs. Input [" 10000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000... (4311 chars): base raises builtins.ValueError, head raises packaging.version.InvalidVersion. (packaging.version.InvalidVersion is a subclass of builtins.ValueError.)
  - Leading whitespace triggers the fast‑path; the int conversion raises ValueError which is caught and re‑raised as InvalidVersion, matching the intended normalisation of error types.
  - >     self._release = tuple(map(int, version.strip().split(".")))
  - > except ValueError:
- **needs-human** (no majority) [intended 1, likely-bug 1, needs-human 1] · known: inner-whitespace, oversized-int-exception: Outcome differs. Input ["100000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000... (4309 chars): base raises packaging.version.InvalidVersion, head returns normally.
  - A very long numeric version with only digits and dots passes the fast‑path and is accepted, whereas the base version rejects it as InvalidVersion – a regression in version validation.

### #1108 `SpecifierSet`: perf: SpecifierSet use tuple instead of frozenset for `_specs`

- **likely-bug** [likely-bug 3] · known: dedup-str-len: Output `len` differs. Input [">=01.0,!=2.0,>=1.0"]: base gives 2, head gives 3.
  - The PR is a performance refactor ("perf: SpecifierSet use tuple instead of frozenset for `_specs`") but changes deduplication from canonicalized Specifier equality to raw‑string equality, changing `len(SpecifierSet(">=01.0,!=2.0,>=1.0"))` from 2 to 3.
  - > perf: SpecifierSet use tuple instead of frozenset for `_specs`
  - > self._specs: tuple[Specifier, ...] = tuple(map(Specifier, dict.fromkeys(split_specifiers)))
- **likely-bug** [likely-bug 3] · known: dedup-str-len: Output `len` differs. Input [">= 1.0,!=2.0,>=1.0"]: base gives 2, head gives 3.
  - Same deduplication change causes `len(SpecifierSet(">= 1.0,!=2.0,>=1.0"))` to change from 2 to 3.
  - > self._specs: tuple[Specifier, ...] = tuple(map(Specifier, dict.fromkeys(split_specifiers)))
  - > perf: SpecifierSet use tuple instead of frozenset for `_specs`
- **likely-bug** [likely-bug 3] · known: dedup-str-len: Output `str` differs. Input [">=01.0,!=2.0,>=1.0"]: base gives "!=2.0,>=01.0", head gives "!=2.0,>=01.0,>=1.0".
  - String representation now includes both “>=01.0” and “>=1.0” because deduplication no longer canonicalizes versions.
  - > self._specs: tuple[Specifier, ...] = tuple(map(Specifier, dict.fromkeys(split_specifiers)))
  - > perf: SpecifierSet use tuple instead of frozenset for `_specs`
- **likely-bug** [likely-bug 3] · known: dedup-str-len: Output `str` differs. Input [">= 1.0,!=2.0,>=1.0"]: base gives "!=2.0,>=1.0", head gives "!=2.0,>=1.0,>=1.0".
  - Same string‑representation change for the spaced version string.
  - > self._specs: tuple[Specifier, ...] = tuple(map(Specifier, dict.fromkeys(split_specifiers)))
  - > perf: SpecifierSet use tuple instead of frozenset for `_specs`
- **likely-bug** [likely-bug 3]: Outcome differs. Input [">=1000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000... (4309 chars): base raises builtins.AssertionError, head returns normally.
  - Base raises AssertionError from `_require_spec_version` on an extremely long version string; the refactor changes the compatible‑operator path and avoids the assertion, altering error behavior.
  - > def _require_spec_version(self, version: str) -> Version: ... assert spec_version is not None
  - > def _compare_compatible(self, prospective: Version, spec: str) -> bool: ... return (self._compare_greater_than_equal(prospective, spec)) and (self._compare_equal(prospective, prefix))
- **likely-bug** [likely-bug 3]: Outcome differs. Input ["<=1000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000... (4311 chars): base raises builtins.ValueError, head returns normally.
  - Base raises ValueError for a very long “<=” specifier; the new tuple‑based implementation no longer triggers that error, changing observable behavior.
  - > def _require_spec_version(self, version: str) -> Version: ... assert spec_version is not None
  - > def _compare_compatible(self, prospective: Version, spec: str) -> bool: ... return (self._compare_greater_than_equal(prospective, spec)) and (self._compare_equal(prospective, prefix))
- **likely-bug** [likely-bug 3] · known: dedup-equality: Relation `a == b` differs for a = target(*[">=01.0,!=2.0,>=1.0"]), b = target(*["!=2.0,>=1.0"]): base True, head False.
  - Equality of two SpecifierSet objects that were equal under canonicalized frozenset semantics now differs because the new tuple stores both raw strings.
  - > def __eq__(self, other: object) -> bool: ... return self._sort_specs() == other._sort_specs()
  - > self._specs: tuple[Specifier, ...] = tuple(map(Specifier, dict.fromkeys(split_specifiers)))
- **likely-bug** [likely-bug 3]: Relation `hash(a) == hash(b)` differs for a = target(*[">=01.0,!=2.0,>=1.0"]), b = target(*["!=2.0,>=1.0"]): base True, head False.
  - Hash now depends on the sorted tuple of raw Specifier objects, so two sets that were equal before now have different hashes.
  - > def __hash__(self) -> int: return hash(self._sort_specs())
  - > self._specs: tuple[Specifier, ...] = tuple(map(Specifier, dict.fromkeys(split_specifiers)))
- **likely-bug** [likely-bug 3] · known: old-pickles-break-comparison: An object built by base from [""], pickled, then unpickled by head loads, but comparing it with a freshly built head object fails: <exc:builtins.AttributeError>.
  - Adding `_sorted` to `__slots__` breaks unpickling of objects pickled by the old version (missing attribute).
  - > __slots__ = ("_prereleases", "_sorted", "_specs")
  - > __slots__ = ("_prereleases", "_specs")
- **likely-bug** [likely-bug 3] · known: old-pickles-break-comparison: An object built by base from [">=01.0,!=2.0,>=1.0"], pickled, then unpickled by head loads, but no longer equals a freshly built head object (== gives False).
  - Pickled old object unpickled in new version no longer equals a freshly built new object because of the new `_sorted` slot and changed deduplication semantics.
  - > __slots__ = ("_prereleases", "_sorted", "_specs")
  - > self._specs: tuple[Specifier, ...] = tuple(map(Specifier, dict.fromkeys(split_specifiers)))

### #1115 `Version`: perf: skip hash property

- **likely-bug** [likely-bug 3]: An object built by base from ["0"], pickled, then unpickled by head loads, but no longer equals a freshly built head object (== gives False).
  - The PR changes __hash__ to cache the comparison key in _key_cache, but __eq__ (inherited from _BaseVersion) still compares self._key == other._key. The base class's __hash__ used self._key, implying _key is a property that computes the key. The new __hash__ bypasses that property, so an unpickled object (which has _key_cache == None and never had __hash__ called) will compare unequal to a freshly constructed object whose __hash__ has populated _key_cache. This breaks pickling compatibility, an unintended regression.
  - >     def __eq__(self, other: object) -> bool:
        if not isinstance(other, _BaseVersion):
            return NotImplemented

        return self._key == other._key
  - >     def __hash__(self) -> int:
        return hash(self._key)

### #1116 `Version`: perf: Overhaul `_cmpkey` to remove use of custom objects

- **likely-bug** [likely-bug 3] · known: old-pickles-fail-to-load: An object built by base from ["0"], pickled, then unpickled by head fails to load: builtins.ModuleNotFoundError.
  - Unpickling a previously pickled Version object fails with a ModuleNotFoundError after a refactor that only claims to improve comparison performance and keep internal backward compatibility. No changelog, test, or documentation mentions breaking pickle compatibility, which callers reasonably rely on.
  - > # Backward compatibility for internals before 26.0. Do not use.
  - > Override comparison methods to use direct _key_cache access... This is faster than property access, especially before Python 3.12

### #1147 `Marker`: perf: add __slots__ to Marker

- **likely-bug** [likely-bug 3] · known: marker-pickle: An object built by base from ["\"b\" > \"a\""], pickled, then unpickled by head fails to load: builtins.AttributeError.
  - Adding __slots__ to Marker changes its pickle representation. Objects pickled by the old version (without __slots__) cannot be unpickled by the new version, raising AttributeError. The PR is a performance refactor with no mention of pickling, tests, or changelog updates, so this regression is unintended.
  - > +    __slots__ = ("_markers",)
  - > class Marker:

### #1236 † `parse_tag`: perf: simply work done in parse_tag a bit

- **intended** [intended 2, needs-human 1]: Outcome differs. Input ["-"]: base raises builtins.ValueError, head raises packaging.tags.InvalidTag. (packaging.tags.InvalidTag is a subclass of builtins.ValueError.)
  - The docstring for parse_tag states ".. versionadded:: 26.3 Raises :class:`InvalidTag` on empty tag components." and the code change replaces the ValueError with raising InvalidTag for empty components.
  - > .. versionadded:: 26.3
   Raises :class:`InvalidTag` on empty tag components.
  - > raise InvalidTag(f"Tag {tag!r} has an empty component: {component!r}")
- **intended** [intended 2, needs-human 1]: Outcome differs. Input ["- "]: base raises builtins.ValueError, head raises packaging.tags.InvalidTag. (packaging.tags.InvalidTag is a subclass of builtins.ValueError.)
  - Same reasoning as C1: the versionadded note documents the new InvalidTag exception for empty components, and the code now raises InvalidTag.
  - > .. versionadded:: 26.3
   Raises :class:`InvalidTag` on empty tag components.
  - > raise InvalidTag(f"Tag {tag!r} has an empty component: {component!r}")
- **intended** [intended 2, needs-human 1]: Outcome differs. Input ["-\u001b"]: base raises builtins.ValueError, head raises packaging.tags.InvalidTag. (packaging.tags.InvalidTag is a subclass of builtins.ValueError.)
  - Same reasoning; the new InvalidTag exception is documented as intended behavior for empty components.
  - > .. versionadded:: 26.3
   Raises :class:`InvalidTag` on empty tag components.
  - > raise InvalidTag(f"Tag {tag!r} has an empty component: {component!r}")
- **intended** [intended 2, needs-human 1]: Outcome differs. Input [""]: base raises builtins.ValueError, head raises packaging.tags.InvalidTag. (packaging.tags.InvalidTag is a subclass of builtins.ValueError.)
  - Same reasoning; the change intentionally raises InvalidTag for an empty tag string.
  - > .. versionadded:: 26.3
   Raises :class:`InvalidTag` on empty tag components.
  - > raise InvalidTag(f"Tag {tag!r} has an empty component: {component!r}")
- **intended** [intended 2, needs-human 1]: Outcome differs. Input ["-񠞝"]: base raises builtins.ValueError, head raises packaging.tags.InvalidTag. (packaging.tags.InvalidTag is a subclass of builtins.ValueError.)
  - Same reasoning; the new InvalidTag exception is documented as intended for empty components.
  - > .. versionadded:: 26.3
   Raises :class:`InvalidTag` on empty tag components.
  - > raise InvalidTag(f"Tag {tag!r} has an empty component: {component!r}")
- **intended** [intended 2, needs-human 1]: Outcome differs. Input ["py1000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000... (4307 chars): base raises builtins.ValueError, head raises packaging.tags.InvalidTag. (packaging.tags.InvalidTag is a subclass of builtins.ValueError.)
  - Same reasoning; the exception type change is documented as intentional.
  - > .. versionadded:: 26.3
   Raises :class:`InvalidTag` on empty tag components.
  - > raise InvalidTag(f"Tag {tag!r} has an empty component: {component!r}")
- **intended** [intended 2, needs-human 1]: Outcome differs. Input ["-"]: base raises builtins.ValueError, head raises packaging.tags.InvalidTag. (packaging.tags.InvalidTag is a subclass of builtins.ValueError.)
  - Same reasoning; the change deliberately raises InvalidTag instead of ValueError for empty components.
  - > .. versionadded:: 26.3
   Raises :class:`InvalidTag` on empty tag components.
  - > raise InvalidTag(f"Tag {tag!r} has an empty component: {component!r}")

### #1429 † `Marker`: perf(parser): avoid literal_eval for plain marker strings

- **likely-bug** [likely-bug 3]: An object built by base from ["python_version == '3.\\n11'"], pickled, then unpickled by head fails to load: builtins.TypeError.
  - The head version fails to unpickle a Marker that was pickled by the base version, raising a TypeError from the new Marker.__reduce__ implementation. The diff shows the new __reduce__ method raising TypeError when the pickled state does not match the expected '_markers' slot structure (see the added `raise TypeError(f"Cannot restore Marker from {state!r}")` and the strict `isinstance(markers, list)` check). This regression is unrelated to the parser performance change and indicates a bug introduced by the marker pickling changes.
  - > raise TypeError(f"Cannot restore Marker from {state!r}")
  - > if isinstance(markers, list):

† merged after Nemotron 3 Ultra's release (2026-06-04): no training-data contamination possible.