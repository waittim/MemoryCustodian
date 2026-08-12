"""Small Markdown section primitives used by manifest protocol parsers."""

from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class MarkdownLine:
    index: int
    text: str
    indented_code: bool


@dataclass(frozen=True)
class MarkdownHeading:
    index: int
    level: int
    title: str


@dataclass(frozen=True)
class MarkdownUnitRange:
    """A source range for one visible semantic memory unit."""

    start: int
    end: int
    kind: str
    heading: str | None = None


_LIST_FIELDS = frozenset({"Aliases", "Entries", "Evidence", "Merged-From"})
_FORMAL_ENTRY_HEADING_RE = re.compile(
    r"^ {0,3}##[ \t]+MC-(?:DEC|CON|DNU|PREF|AREA|INBOX|TOMB)-", re.I
)
_FIELD_RE = re.compile(r"^([A-Za-z][A-Za-z-]*):[ \t]*(?:.*)?$")


def visible_lines(text: str) -> tuple[MarkdownLine, ...]:
    """Return source lines visible under the supported Markdown lexical contract."""

    visible: list[MarkdownLine] = []
    fence_character: str | None = None
    fence_length = 0
    in_comment = False
    for index, raw in enumerate(text.splitlines()):
        if in_comment:
            _comment, marker, trailing = raw.partition("-->")
            if not marker:
                continue
            if trailing.strip():
                raise ValueError(
                    "HTML comment closing lines must contain no other content"
                )
            in_comment = False
            continue
        if fence_character is not None:
            closing = re.fullmatch(
                rf" {{0,3}}{re.escape(fence_character)}{{{fence_length},}}[ \t]*",
                raw,
            )
            if closing:
                fence_character = None
                fence_length = 0
            continue
        opening = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", raw)
        if opening:
            marker = opening.group(1)
            info = opening.group(2)
            if marker[0] == "`" and "`" in info:
                raise ValueError(
                    "Backtick fence info strings must not contain backticks"
                )
            fence_character = marker[0]
            fence_length = len(marker)
            continue

        comment = re.match(r"^ {0,3}<!--", raw)
        if comment:
            _before, marker, trailing = raw[comment.end():].partition("-->")
            if marker:
                if trailing.strip():
                    raise ValueError(
                        "HTML comments must occupy complete lines"
                    )
            else:
                in_comment = True
            continue
        leading_spaces = len(raw) - len(raw.lstrip(" "))
        visible.append(
            MarkdownLine(
                index,
                raw,
                leading_spaces >= 4 or raw.startswith("\t"),
            )
        )
    if fence_character is not None:
        raise ValueError("Unclosed fenced code block")
    if in_comment:
        raise ValueError("Unclosed HTML comment")
    return tuple(visible)


def headings(text: str) -> tuple[MarkdownHeading, ...]:
    """Return real ATX headings with CommonMark closing sequences removed."""

    found: list[MarkdownHeading] = []
    for line in visible_lines(text):
        if line.indented_code:
            continue
        match = re.match(r"^ {0,3}(#{1,6})(?:[ \t]+|$)(.*)$", line.text)
        if not match:
            continue
        title = re.sub(r"[ \t]+#+[ \t]*$", "", match.group(2)).strip().casefold()
        found.append(MarkdownHeading(line.index, len(match.group(1)), title))
    return tuple(found)


def section_ranges(
    text: str,
    level: int,
    title: str,
) -> tuple[tuple[int, int], ...]:
    """Return body ranges for matching headings, excluding the heading line."""

    lines = text.splitlines()
    all_headings = headings(text)
    normalized = title.strip().casefold()
    ranges: list[tuple[int, int]] = []
    for position, heading in enumerate(all_headings):
        if heading.level != level or heading.title != normalized:
            continue
        end = len(lines)
        for following in all_headings[position + 1:]:
            if following.level <= level:
                end = following.index
                break
        ranges.append((heading.index + 1, end))
    return tuple(ranges)


def semantic_unit_ranges(text: str, *, start: int = 0) -> tuple[MarkdownUnitRange, ...]:
    """Return source-preserving H2, legacy-bullet, and body unit ranges.

    Only visible Markdown participates in boundary detection. Fenced examples,
    HTML comments, and indented code remain inside their containing source range
    and can never become selectable memory entries.
    """

    lines = text.splitlines()
    visible = {
        line.index: line
        for line in visible_lines(text)
        if line.index >= start and not line.indented_code
    }
    visible_indices = sorted(visible)
    next_h2: dict[int, int] = {}
    following_h2 = len(lines)
    for index in reversed(visible_indices):
        next_h2[index] = following_h2
        if re.match(r"^ {0,3}##(?:[ \t]+|$)", visible[index].text):
            following_h2 = index

    def formal_field_follows(index: int) -> bool:
        limit = next_h2.get(index, len(lines))
        return any(
            index < candidate < limit
            and _FIELD_RE.fullmatch(visible[candidate].text) is not None
            for candidate in visible_indices
        )

    starts: list[tuple[int, str, str | None]] = []
    current_kind: str | None = None
    formal_entry = False
    list_field = False
    for index in visible_indices:
        line = visible[index].text
        heading_match = re.match(r"^ {0,3}##(?:[ \t]+|$)(.*)$", line)
        if heading_match:
            heading = re.sub(r"[ \t]+#+[ \t]*$", "", heading_match.group(1)).strip()
            starts.append((index, "h2", heading))
            current_kind = "h2"
            formal_entry = _FORMAL_ENTRY_HEADING_RE.match(line) is not None
            list_field = False
            continue

        if current_kind == "h2":
            field = _FIELD_RE.fullmatch(line)
            if field:
                list_field = field.group(1) in _LIST_FIELDS
                continue
            if list_field:
                if line.startswith(("- ", "* ", "+ ")) or (line and line[0].isspace()):
                    continue
                list_field = False

        if line.startswith(("- ", "* ", "+ ")):
            if current_kind == "h2" and formal_entry and formal_field_follows(index):
                continue
            kind = "ambiguous-bullet" if current_kind == "h2" and formal_entry else "bullet"
            starts.append((index, kind, None))
            current_kind = kind
            formal_entry = False
            list_field = False
            continue
        if current_kind in {"bullet", "ambiguous-bullet"} and line and not line[0].isspace():
            starts.append((index, "body", None))
            current_kind = "body"

    return tuple(
        MarkdownUnitRange(
            unit_start,
            starts[position + 1][0] if position + 1 < len(starts) else len(lines),
            kind,
            heading,
        )
        for position, (unit_start, kind, heading) in enumerate(starts)
    )
