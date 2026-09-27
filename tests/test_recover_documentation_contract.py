from __future__ import annotations

import contextlib
import io
from pathlib import Path
import shlex
import unittest

from memory_custodian.main import build_parser


ROOT = Path(__file__).resolve().parents[1]
CURRENT_DOCUMENTATION = (
    ROOT / "README.md",
    ROOT / "docs" / "MemoryCustodian-plan-0.12.0-erasure-aligned-revised.md",
)
CURRENT_DOCUMENTATION_TREES = (
    ROOT / "skills",
    ROOT / "adapters",
    ROOT / "examples",
)


def documented_recover_commands() -> list[tuple[Path, int, str]]:
    paths = set(CURRENT_DOCUMENTATION)
    for root in CURRENT_DOCUMENTATION_TREES:
        paths.update(root.rglob("*.md"))

    commands: list[tuple[Path, int, str]] = []
    for path in sorted(paths):
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            command = line.strip()
            if command == "memory-custodian recover" or command.startswith(
                "memory-custodian recover "
            ):
                commands.append((path, line_number, command))
    return commands


class RecoverDocumentationContractTests(unittest.TestCase):
    def test_current_documented_recover_commands_match_cli_parser(self):
        parser = build_parser()
        commands = documented_recover_commands()
        self.assertTrue(commands, "expected at least one documented recover command")

        for path, line_number, command in commands:
            location = f"{path.relative_to(ROOT)}:{line_number}"
            with self.subTest(location=location, command=command):
                argv = shlex.split(command)[1:]
                error = io.StringIO()
                with contextlib.redirect_stderr(error):
                    try:
                        args = parser.parse_args(argv)
                    except SystemExit as exc:
                        self.fail(
                            f"{location}: documented command is rejected by the CLI "
                            f"parser (exit {exc.code}): {error.getvalue().strip()}"
                        )
                self.assertEqual(args.command, "recover")


if __name__ == "__main__":
    unittest.main()
