"""Two toy 'versions' of a parser. HeadVer is a plausible-looking 'optimization' with bugs:
it trusts int() (so it accepts non-ASCII digits) and keeps the raw string for str() and ==."""


class BaseVer:
    def __init__(self, s: str):
        if not s.isascii() or not s.replace(".", "").isdigit():
            raise ValueError(f"invalid version {s!r}")
        self.parts = tuple(int(p) for p in s.split("."))
        self.raw = s

    def __str__(self):
        return ".".join(map(str, self.parts))

    def __eq__(self, other):
        return self.parts == other.parts

    def __lt__(self, other):
        return self.parts < other.parts

    def __gt__(self, other):
        return self.parts > other.parts

    def __hash__(self):
        return hash(self.parts)


class HeadVer(BaseVer):
    def __init__(self, s: str):
        self.parts = tuple(int(p) for p in s.split("."))
        self.raw = s

    def __str__(self):
        return self.raw

    def __eq__(self, other):
        return self.raw == other.raw

    __hash__ = BaseVer.__hash__
