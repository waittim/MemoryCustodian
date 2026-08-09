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
    """Return lines under the manifest's deliberately limited Markdown contract."""

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
                    "HTML comment closing lines in manifest.md must contain no other content"
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
                    "Backtick fence info strings in manifest.md must not contain backticks"
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
                        "HTML comments in manifest.md must occupy complete lines"
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
        raise ValueError("Unclosed fenced code block in manifest.md")
    if in_comment:
        raise ValueError("Unclosed HTML comment in manifest.md")
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
