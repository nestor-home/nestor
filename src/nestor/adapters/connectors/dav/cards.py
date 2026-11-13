"""iCalendar (RFC 5545) and vCard (RFC 6350) as calendars and address books store them: lines of `NAME;PARAM=…:VALUE`
inside `BEGIN:`/`END:` blocks. Only what the tools read is understood; the rest is left alone."""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime

ESCAPES = {"n": "\n", "N": "\n", ",": ",", ";": ";", "\\": "\\"}


@dataclass(slots=True)
class Line:
    name: str
    params: dict[str, str]
    value: str

    @property
    def text(self) -> str:
        """The value with its escapes (`\\n`, `\\,`…) undone."""
        return _unescaped(self.value)

    @property
    def parts(self) -> list[str]:
        """The components of a structured value (`ADR`, `ORG`, `N`), split on the semicolons that are not escaped."""
        parts, current, chars = [], [], iter(self.value)
        for char in chars:
            if char == "\\":
                current.append(char + next(chars, ""))
            elif char == ";":
                parts.append(_unescaped("".join(current)))
                current = []
            else:
                current.append(char)
        return [*parts, _unescaped("".join(current))]


@dataclass(slots=True)
class Block:
    """A `BEGIN:<kind>` … `END:<kind>` block: its lines, and the blocks inside it."""

    kind: str
    lines: list[Line] = field(default_factory=list)
    blocks: list["Block"] = field(default_factory=list)

    def first(self, name: str) -> Line | None:
        return next((line for line in self.lines if line.name == name), None)

    def all(self, name: str) -> list[Line]:
        return [line for line in self.lines if line.name == name]

    def text(self, name: str) -> str:
        line = self.first(name)
        return line.text if line else ""

    def find(self, kind: str) -> list["Block"]:
        """Every block of `kind` inside this one, at any depth."""
        return [b for child in self.blocks for b in ([child] if child.kind == kind else child.find(kind))]


def _unescaped(value: str) -> str:
    out, chars = [], iter(value)
    for char in chars:
        out.append(ESCAPES.get(escaped := next(chars, ""), escaped) if char == "\\" else char)
    return "".join(out)


def parse(data: str) -> Block:
    """The blocks of a document, under a root block of kind ""; a malformed line is skipped."""
    root = Block("")
    stack = [root]
    for raw in data.replace("\r\n", "\n").replace("\n ", "").replace("\n\t", "").split("\n"):
        head, colon, value = raw.partition(":")
        if not colon:
            continue
        name, *params = head.split(";")
        name = name.upper().rpartition(".")[2]  # a vCard group (`item1.EMAIL`) does not change what the line is
        if name == "BEGIN":
            block = Block(value.strip().upper())
            stack[-1].blocks.append(block)
            stack.append(block)
        elif name == "END" and len(stack) > 1:
            stack.pop()
        else:
            pairs = (p.partition("=") for p in params)
            stack[-1].lines.append(Line(name, {k.upper(): v.strip('"') for k, _, v in pairs}, value))
    return root


def moment(line: Line | None) -> date | datetime | None:
    """A `DTSTART`/`DTEND`: a day (`VALUE=DATE`), an instant in UTC (`…Z`), or a time with no zone, read as given
    (an expanded calendar answer gives its instants in UTC)."""
    if line is None:
        return None
    value = line.value.strip()
    try:
        if line.params.get("VALUE") == "DATE" or len(value) == 8:
            return datetime.strptime(value, "%Y%m%d").date()
        found = datetime.strptime(value.rstrip("Z"), "%Y%m%dT%H%M%S")
    except ValueError:
        return None
    return found.replace(tzinfo=UTC) if value.endswith("Z") else found


def escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", r"\;").replace(",", "\\,").replace("\n", "\\n")


def fold(line: str) -> str:
    """A line cut every 74 characters, as RFC 5545 wants (75 octets at most; characters keep it simple and safe)."""
    return "\r\n ".join(line[i : i + 74] for i in range(0, len(line), 74)) or line
