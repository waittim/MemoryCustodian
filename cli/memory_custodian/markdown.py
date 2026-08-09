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


def visible_lines(text: str) -> tuple[MarkdownLine, ...]:
    """Return lines outside fenced code and HTML comments."""

    visible: list[MarkdownLine] = []
    fence_character: str | None = None
    fence_length = 0
    in_comment = False
    for index, raw in enumerate(text.splitlines()):
        if fence_character is not None:
            closing = re.fullmatch(
                rf" {{0,3}}{re.escape(fence_character)}{{{fence_length},}}[ \t]*",
                raw,
            )
            if closing:
                fence_character = None
                fence_length = 0
            continue
        opening = re.match(r"^ {0,3}(`{3,}|~{3,})(?:[^`].*)?$", raw)
        if opening and not in_comment:
            marker = opening.group(1)
            fence_character = marker[0]
            fence_length = len(marker)
            continue

        remainder = raw
        rendered = ""
        while remainder:
            if in_comment:
                _before, marker, remainder = remainder.partition("-->")
                if not marker:
                    remainder = ""
                    break
                in_comment = False
                continue
            before, marker, after = remainder.partition("<!--")
            rendered += before
            if not marker:
                break
            in_comment = True
            remainder = after
        if in_comment and not rendered:
            continue
        leading_spaces = len(rendered) - len(rendered.lstrip(" "))
        visible.append(
            MarkdownLine(
                index,
                rendered,
                leading_spaces >= 4 or rendered.startswith("\t"),
            )
        )
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
