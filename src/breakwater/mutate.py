"""Deterministic hostile-string mutations of example inputs. No LLM.

Plans vary a lot from sample to sample, so the semantic audit also mutates every example the
planner gives (and the samples the search produced) with a fixed dictionary of edge cases that
commonly separate a hand-written fast path from the parser it bypasses. This is generic, like a
fuzzer dictionary: nothing here knows about any particular library.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable
from typing import Any

# One representative per digit system, plus a few whitespace characters str.split/strip treat specially.
DIGIT_SYSTEMS = {
    "arabic-indic": 0x0660,
    "fullwidth": 0xFF10,
    "devanagari": 0x0966,
    "bengali": 0x09E6,
}
WHITESPACE = (" ", "\t", "\n", " ", " ", "\x0c")
_DIGITS = re.compile(r"\d+", re.ASCII)
_SEP = re.compile(r"[^0-9A-Za-z]")


def _digits(s: str, base: int, first_only: bool) -> str:
    def swap(m: re.Match) -> str:
        return "".join(chr(base + int(c)) for c in m.group(0))

    return _DIGITS.sub(swap, s, count=1 if first_only else 0)


def _huge(s: str, width: int) -> str:
    return _DIGITS.sub(lambda m: "1" + "0" * (width - 1), s, count=1)


MUTATORS: dict[str, Callable[[str], Iterable[str]]] = {
    "unicode-digits": lambda s: [f(s, b) for b in DIGIT_SYSTEMS.values()
                                 for f in (lambda x, b: _digits(x, b, True), lambda x, b: _digits(x, b, False))],
    "whitespace-outer": lambda s: [w + s + w for w in WHITESPACE],
    "whitespace-inner": lambda s: [s[: m.end()] + w + s[m.end():] for m in list(_SEP.finditer(s))[:2] for w in (" ", "\t")]
    + [s[: m.start()] + " " + s[m.start():] for m in list(_SEP.finditer(s))[:1]],
    "huge-number": lambda s: [_huge(s, 4300), _huge(s, 4301), _huge(s, 5000)],
    "separators": lambda s: [s[: m.start()] + m.group(0) * 2 + s[m.end():] for m in list(_SEP.finditer(s))[:2]]
    + [s[: m.start()] + s[m.end():] for m in list(_SEP.finditer(s))[:1]]
    + ([s[1:], s + s[-1]] if s and _SEP.match(s[-1]) is None else []),
    "case": lambda s: [s.upper(), s.swapcase()],
    "underscores": lambda s: [_DIGITS.sub(lambda m: "_".join(m.group(0)), s, count=1)],
    "signs": lambda s: ["+" + s, "-" + s],
    "edges": lambda s: ["", s[:1], s + "\x00"],
}


def mutate_args(examples: list[list[Any]], limit: int = 120) -> list[tuple[str, list[Any]]]:
    """Return (mutator, args) pairs: every string argument of every example, mutated, de-duplicated,
    round-robin across mutators so a small limit still covers every mutator."""
    per_mutator: dict[str, list[list[Any]]] = {name: [] for name in MUTATORS}
    seen = {json.dumps(e, ensure_ascii=False) for e in examples}
    for args in examples:
        for i, a in enumerate(args):
            if not isinstance(a, str):
                continue
            for name, fn in MUTATORS.items():
                for m in fn(a):
                    new = args[:i] + [m] + args[i + 1:]
                    key = json.dumps(new, ensure_ascii=False)
                    if key not in seen:
                        seen.add(key)
                        per_mutator[name].append(new)
    out: list[tuple[str, list[Any]]] = []
    while len(out) < limit and any(per_mutator.values()):
        for name, items in per_mutator.items():
            if items and len(out) < limit:
                out.append((name, items.pop(0)))
    return out
