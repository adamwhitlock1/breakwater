"""Near-duplicate finding classes, grouped for reports. Presentation only: signatures, class counts
and known-issue matching are unchanged; a group just shows one primary class with its near-duplicates.

A class's signature carries input traits for P1/P2 (`non-ascii`, `whitespace+long-digits`, ...),
so one root cause seen on inputs with an extra trait becomes a second class. Within one structural
key (probe, detail, base and head outcome shapes) and one adjudication label:

  * a class whose traits strictly CONTAIN another class's traits is a near-duplicate of it
    (`long-digits+whitespace` folds under `long-digits`; anything folds under `plain`);
  * a class containing two minimal classes' traits (`non-ascii+whitespace` with both `non-ascii`
    and `whitespace` present) is listed under both, never used to merge them: distinct traits can be
    distinct bugs (#1082's Unicode digits and inner whitespace were fixed separately).

P3 `lt` and `gt` flips on a pair are one fact seen from both sides, so they form one ordering group.
Classes with different labels never merge.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

ORDERING = ("lt", "gt")


@dataclass
class Group:
    key: str
    label: str | None
    primary: str  # signature of the simplest member
    members: list[str] = field(default_factory=list)  # all signatures, primary first
    shared: list[str] = field(default_factory=list)  # members also listed under another group

    @property
    def duplicates(self) -> list[str]:
        return [m for m in self.members if m != self.primary]


def split(sig: str) -> tuple[str, frozenset[str]]:
    """Structural key and input traits of a signature."""
    parts = sig.split("|")
    if parts[0] == "P3" and len(parts) > 1 and parts[1] in ORDERING:
        return "P3|ordering", frozenset()
    if parts[0] in ("P1", "P2") and len(parts) > 2:
        traits = parts[-1]
        return "|".join(parts[:-1]), frozenset() if traits == "plain" else frozenset(traits.split("+"))
    return sig, frozenset()


def group_classes(signatures: list[str], labels: dict[str, str | None] | None = None,
                  size: dict[str, int] | None = None) -> list[Group]:
    """Groups in first-seen order. `size` (e.g. length of the class's smallest input) breaks ties
    when choosing a primary among members with equal traits."""
    labels, size = labels or {}, size or {}
    buckets: dict[tuple[str, str | None], list[tuple[frozenset[str], str]]] = defaultdict(list)
    order: list[tuple[str, str | None]] = []
    for sig in signatures:
        key, traits = split(sig)
        k = (key, labels.get(sig))
        if k not in buckets:
            order.append(k)
        buckets[k].append((traits, sig))
    groups: list[Group] = []
    for k in order:
        mem = buckets[k]
        if k[0] == "P3|ordering":
            sigs = sorted((s for _, s in mem), key=lambda s: (size.get(s, 0), s))
            groups.append(Group(k[0], k[1], sigs[0], sigs))
            continue
        minimal = [(t, s) for t, s in mem if not any(o < t for o, _ in mem)]
        minimal.sort(key=lambda m: (len(m[0]), size.get(m[1], 0), m[1]))
        for traits, sig in minimal:
            members = [sig] + sorted((s for t, s in mem if traits < t), key=lambda s: (size.get(s, 0), s))
            groups.append(Group(k[0], k[1], sig, members))
    seen: dict[str, int] = defaultdict(int)
    for g in groups:
        for m in g.members:
            seen[m] += 1
    for g in groups:
        g.shared = [m for m in g.members if seen[m] > 1]
    return groups
