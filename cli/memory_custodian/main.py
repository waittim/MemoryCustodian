"""Command-line entry point for MemoryCustodian."""

from __future__ import annotations

import argparse

from . import __version__
from . import add as add_cmd
from . import check as check_cmd
from . import compact as compact_cmd
from . import enable as enable_cmd
from . import forget as forget_cmd
from . import init as init_cmd
from . import migrate as migrate_cmd
from . import read as read_cmd
from . import status as status_cmd
from .protocol import TASK_CATEGORY
from .templates import DEFAULT_MEMORY_DIR


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project-root", default=".", help="Project root. Defaults to the current directory.")
    parser.add_argument("--memory-dir", default=DEFAULT_MEMORY_DIR, help="Memory directory under docs/. Defaults to docs/memory.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="memory-custodian", description="Local plain-text project memory governance for coding agents.")
    parser.add_argument("--version", action="version", version=f"memory-custodian {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    init_parser = sub.add_parser("init", help="Initialize memory files in a project.")
    _add_common(init_parser)
    init_parser.add_argument("--path", help="Memory directory under docs/. Alias for --memory-dir.")
    init_parser.add_argument("--extended", action="store_true", help="Also create optional preferences, changelog, rules, profiles, and archive templates.")
    init_parser.add_argument("--with-codex", action="store_true", help="Add the Codex AGENTS.md entry snippet.")
    init_parser.add_argument("--with-claude", action="store_true", help="Add the Claude Code CLAUDE.md entry snippet.")
    init_parser.add_argument("--with-gemini", action="store_true", help="Add the Gemini GEMINI.md entry snippet.")
    init_parser.add_argument(
        "--agent",
        choices=("none", "codex", "claude", "gemini", "all"),
        default="none",
        help="Optionally add platform entry snippets.",
    )
    init_parser.add_argument("--force", action="store_true", help="Overwrite existing memory files.")
    init_parser.add_argument("--force-agent", action="store_true", help="Replace an existing managed or recognized legacy MemoryCustodian block.")
    init_parser.set_defaults(func=init_cmd.run)

    status_parser = sub.add_parser("status", help="Report memory file health.")
    _add_common(status_parser)
    status_parser.set_defaults(func=status_cmd.run)

    read_parser = sub.add_parser("read", help="Render a small context pack for a task.")
    _add_common(read_parser)
    read_parser.add_argument("--task", choices=sorted(TASK_CATEGORY.keys()), default="default", help="Task type routed by the project manifest.")
    read_parser.add_argument("--profile", action="append", default=[], help="Optional workflow profile to include if present, such as git.")
    read_parser.add_argument("--area", action="append", default=[], help="Optional area memory to include if present, such as frontend.")
    read_parser.add_argument("--names-only", action="store_true", help="Only list files, without printing their contents.")
    read_parser.set_defaults(func=read_cmd.run)

    add_parser = sub.add_parser("add", help="Add a memory entry.")
    _add_common(add_parser)
    add_parser.add_argument("message", help="Memory text to add.")
    add_parser.add_argument(
        "--type",
        choices=("decision", "constraint", "preference", "tombstone", "do-not-use", "rule", "profile", "area", "inbox"),
        default="inbox",
        help="Memory type.",
    )
    add_parser.add_argument("--name", help="Name for rule, profile, or area memory.")
    add_parser.add_argument(
        "--area",
        help="Store a scoped decision, constraint, preference, or tombstone in areas/<name>.md.",
    )
    add_parser.add_argument("--reason", help="Optional reason for decisions or tombstones.")
    add_parser.add_argument(
        "--allow-long",
        action="store_true",
        help="Allow a decision over the recommended per-entry budget after semantic review.",
    )
    add_parser.set_defaults(func=add_cmd.run)

    compact_parser = sub.add_parser("compact", help="Compact inbox entries or review an over-budget memory file.")
    _add_common(compact_parser)
    compact_parser.add_argument("--target", help="Memory file to compact or review, such as decisions.md. Defaults to inbox.md.")
    compact_parser.add_argument("--apply", action="store_true", help="Write deterministic compaction changes. Default is dry run.")
    compact_parser.add_argument(
        "--archive-oldest",
        action="store_true",
        help="Explicitly allow age-based decision archival after semantic review.",
    )
    compact_parser.set_defaults(func=compact_cmd.run)

    forget_parser = sub.add_parser("forget", help="Forget a memory topic and add a tombstone.")
    _add_common(forget_parser)
    forget_parser.add_argument("topic", help="Topic or phrase to forget.")
    forget_parser.add_argument("--mode", choices=("soft", "hard", "purge"), default="soft", help="Forgetting mode.")
    forget_parser.add_argument("--apply", action="store_true", help="Apply the previewed forgetting plan. Default is dry run.")
    forget_parser.add_argument(
        "--allow-broad-match", action="store_true", help="Allow applying a short-topic or multi-unit match plan."
    )
    forget_parser.set_defaults(func=forget_cmd.run)

    enable_parser = sub.add_parser("enable", help="Enable an optional memory module.")
    _add_common(enable_parser)
    enable_parser.add_argument("feature", help="Feature to enable, such as preferences, changelog, rules/output, profile/git, or area/frontend.")
    enable_parser.add_argument("--force", action="store_true", help="Overwrite an existing optional memory file.")
    enable_parser.set_defaults(func=enable_cmd.run)

    check_parser = sub.add_parser("check", help="Check protocol consistency.")
    _add_common(check_parser)
    check_parser.set_defaults(func=check_cmd.run)

    migrate_parser = sub.add_parser("migrate", help="Migrate memory files to the current protocol.")
    _add_common(migrate_parser)
    migrate_parser.add_argument("--apply", action="store_true", help="Write migration changes. Default is dry run.")
    migrate_parser.set_defaults(func=migrate_cmd.run)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ValueError as exc:
        print(f"Error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
