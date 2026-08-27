"""Regression coverage for the shared snapshot validation boundary."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from memory_custodian.conflicts import analyze_conflicts
from memory_custodian.entries import render_candidate_entry
from memory_custodian.main import main
from memory_custodian.snapshot import build_snapshot


def capture(argv: list[str]) -> tuple[int, str, str]:
    output, error = StringIO(), StringIO()
    with redirect_stdout(output), redirect_stderr(error):
        code = main(argv)
    return code, output.getvalue(), error.getvalue()


def subject_unit(subject_id: str, title: str, alias: str | None = None) -> str:
    return (
        f"## {subject_id} — {title}\n\n"
        "Status: active\nKind: concept\nEvidence:\n- user-confirmed\n\n"
        f"Aliases:\n- {alias or title.casefold()}\n"
    )


class SnapshotValidationArchitectureTests(unittest.TestCase):
    def _init(self, root: str) -> Path:
        code, output, error = capture(["init", "--project-root", root])
        self.assertEqual(code, 0, output + error)
        return Path(root) / "docs/memory"

    def test_strict_read_reports_unclosed_canonical_entry_fence(self):
        with tempfile.TemporaryDirectory() as root:
            memory = self._init(root)
            decisions = memory / "decisions.md"
            decisions.write_text(
                decisions.read_text(encoding="utf-8")
                + "\n```text\n"
                + "DO_NOT_PRINT_DECISIONS " * 1000,
                encoding="utf-8",
            )

            code, output, error = capture([
                "read", "--task", "implementation", "--strict-routing",
                "--project-root", root,
            ])

            self.assertEqual(code, 2, output + error)
            self.assertIn("Conflict status: INVALID", output)
            self.assertIn("MC-CONFLICT-007 INVALID", output)
            self.assertIn("Unclosed fenced code block", output)
            self.assertIn("Context pack not approved for substantial work", output)
            self.assertNotIn("DO_NOT_PRINT_DECISIONS", output)

    def test_strict_read_reports_unclosed_fence_in_matched_optional_entry_module(self):
        with tempfile.TemporaryDirectory() as root:
            memory = self._init(root)
            code, output, error = capture([
                "enable", "area/backend", "--path", "cli/**",
                "--project-root", root,
            ])
            self.assertEqual(code, 0, output + error)
            area = memory / "areas" / "backend.md"
            area.write_text(
                area.read_text(encoding="utf-8")
                + "\n```text\n"
                + "DO_NOT_PRINT_BACKEND " * 1000,
                encoding="utf-8",
            )

            code, output, error = capture([
                "read", "--task", "implementation", "--path", "cli/example.py",
                "--strict-routing", "--project-root", root,
            ])

            self.assertEqual(code, 2, output + error)
            self.assertIn("areas/backend.md", output)
            self.assertIn("Conflict status: INVALID", output)
            self.assertIn("MC-CONFLICT-007 INVALID", output)
            self.assertIn("Unclosed fenced code block", output)
            self.assertIn("Context pack not approved for substantial work", output)
            self.assertNotIn("DO_NOT_PRINT_BACKEND", output)

    def test_alias_collision_has_same_current_and_planned_blocker(self):
        with tempfile.TemporaryDirectory() as root:
            memory = self._init(root)
            (memory / "subjects.md").write_text(
                "# Subject Registry\n\n"
                + subject_unit("MC-SUBJ-20260826-11111111", "First", "shared alias")
                + "\n"
                + subject_unit("MC-SUBJ-20260826-22222222", "Second", "shared alias"),
                encoding="utf-8",
            )

            current = analyze_conflicts(memory)
            self.assertEqual(current.status.value, "INVALID")
            self.assertEqual(
                {finding.code for finding in current.findings},
                {"MC-CONFLICT-004"},
            )

            code, output, error = capture([
                "check", "--conflicts", "--project-root", root,
            ])
            self.assertEqual(code, 1, output + error)
            self.assertIn("Conflict status: INVALID", output)
            self.assertIn("MC-CONFLICT-004 INVALID", output)
            self.assertNotIn("MC-CONFLICT-003", output)

            code, preview, error = capture([
                "forget", "unrelated", "--mode", "soft", "--project-root", root,
            ])
            self.assertEqual(code, 0, preview + error)
            self.assertIn("MC-CONFLICT-004 INVALID", preview)
            self.assertNotIn("MC-CONFLICT-003", preview)

    def test_subject_merge_reference_has_same_current_check_and_planned_code(self):
        with tempfile.TemporaryDirectory() as root:
            memory = self._init(root)
            source_id = "MC-SUBJ-20260826-44444444"
            target_id = "MC-SUBJ-20260826-55555555"
            source = (
                f"## {source_id} — Merged source\n\n"
                "Status: merged\nKind: concept\n"
                f"Merged-Into: {target_id}\n"
                "Evidence:\n- user-confirmed\n\n"
                "Aliases:\n- merged source\n"
            )
            target = subject_unit(target_id, "Canonical target") + (
                "\nMerged-From:\n"
                "- MC-SUBJ-20260826-66666666\n"
            )
            (memory / "subjects.md").write_text(
                "# Subject Registry\n\n" + source + "\n" + target,
                encoding="utf-8",
            )

            current = analyze_conflicts(memory)
            current_merge = [
                finding for finding in current.findings
                if "Merged-From references" in finding.message
            ]
            self.assertTrue(current_merge)
            self.assertEqual({finding.code for finding in current_merge}, {"MC-CONFLICT-005"})
            self.assertNotIn("MC-CONFLICT-003", {
                finding.code for finding in current.findings
            })

            code, output, error = capture([
                "check", "--conflicts", "--project-root", root,
            ])
            self.assertEqual(code, 1, output + error)
            self.assertIn("MC-CONFLICT-005 INVALID", output)
            self.assertNotIn("MC-CONFLICT-003", output)

            code, ordinary_output, error = capture([
                "check", "--project-root", root,
            ])
            self.assertEqual(code, 1, ordinary_output + error)
            self.assertIn("MC-CONFLICT-005", ordinary_output)
            self.assertNotIn("MC-CONFLICT-003", ordinary_output)

            code, preview, error = capture([
                "forget", "unrelated", "--mode", "soft",
                "--project-root", root,
            ])
            self.assertEqual(code, 0, preview + error)
            self.assertIn("MC-CONFLICT-005 INVALID", preview)
            self.assertNotIn("MC-CONFLICT-003", preview)

    def test_entry_schema_is_shared_by_check_conflict_and_planned_forget(self):
        with tempfile.TemporaryDirectory() as root:
            memory = self._init(root)
            subject_id = "MC-SUBJ-20260826-33333333"
            (memory / "subjects.md").write_text(
                "# Subject Registry\n\n" + subject_unit(subject_id, "Candidate"),
                encoding="utf-8",
            )
            candidate = render_candidate_entry(
                "MC-INBOX-20260826-abcdef12",
                "Incomplete provisional identity",
                "decision",
                "Candidate body.",
                "project",
                ("user-confirmed",),
                None,
                subject=subject_id,
            )
            (memory / "inbox.md").write_text(
                "# Memory Inbox\n\n" + candidate + "\n",
                encoding="utf-8",
            )

            current = analyze_conflicts(memory)
            self.assertEqual(current.status.value, "INVALID")
            self.assertTrue(any(
                finding.code == "MC-CONFLICT-007"
                and "Provisional-Subject and Provisional-Facet together" in finding.message
                for finding in current.findings
            ))

            code, output, error = capture(["check", "--project-root", root])
            self.assertEqual(code, 1, output + error)
            self.assertIn(
                "must declare Provisional-Subject and Provisional-Facet together",
                output,
            )

            code, preview, error = capture([
                "forget", "unrelated", "--mode", "soft", "--project-root", root,
            ])
            self.assertEqual(code, 0, preview + error)
            self.assertIn("MC-CONFLICT-007 INVALID", preview)
            self.assertIn(
                "must declare Provisional-Subject and Provisional-Facet together",
                preview,
            )

    def test_unclosed_registry_fence_is_shared_by_conflict_and_planned_forget(self):
        cases = (
            ("subjects.md", "MC-CONFLICT-010"),
            ("reconciliations.md", "MC-CONFLICT-008"),
        )
        for filename, expected_code in cases:
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as root:
                memory = self._init(root)
                (memory / filename).write_text(
                    f"# {filename[:-3].title()}\n\n```text\nunterminated\n",
                    encoding="utf-8",
                )

                current = analyze_conflicts(memory)
                self.assertEqual(current.status.value, "INVALID")
                self.assertTrue(any(
                    finding.code == expected_code
                    and "Unclosed fenced code block" in finding.message
                    for finding in current.findings
                ))

                code, output, error = capture([
                    "check", "--conflicts", "--project-root", root,
                ])
                self.assertEqual(code, 1, output + error)
                self.assertIn("Conflict status: INVALID", output)
                self.assertIn(expected_code + " INVALID", output)

                code, preview, error = capture([
                    "forget", "unrelated", "--mode", "soft", "--project-root", root,
                ])
                self.assertEqual(code, 0, preview + error)
                self.assertIn(expected_code + " INVALID", preview)
                self.assertIn("Unclosed fenced code block", preview)

    def test_subject_registry_schema_uses_dedicated_stable_finding_code(self):
        with tempfile.TemporaryDirectory() as root:
            memory = self._init(root)
            subject_id = "MC-SUBJ-20260826-99999999"
            (memory / "subjects.md").write_text(
                "# Subject Registry\n\n"
                + subject_unit(subject_id, "Schema failure")
                + "\nUnknown-Field: must be diagnosed as schema\n",
                encoding="utf-8",
            )

            result = analyze_conflicts(memory)
            schema_findings = [
                finding for finding in result.findings
                if "Unknown-Field" in finding.message
            ]
            self.assertEqual(len(schema_findings), 1)
            self.assertEqual(schema_findings[0].code, "MC-CONFLICT-010")
            self.assertEqual(schema_findings[0].status.value, "INVALID")
            self.assertNotIn(schema_findings[0].code, {
                "MC-CONFLICT-003", "MC-CONFLICT-004", "MC-CONFLICT-005",
            })

            code, output, error = capture([
                "check", "--conflicts", "--project-root", root,
            ])
            self.assertEqual(code, 1, output + error)
            self.assertIn("MC-CONFLICT-010 INVALID", output)
            self.assertNotIn("MC-CONFLICT-003", output)
            self.assertNotIn("MC-CONFLICT-004", output)
            self.assertNotIn("MC-CONFLICT-005", output)

            table = Path(
                "docs/MemoryCustodian-plan-0.11.0-erasure-aligned-revised.md"
            ).read_text(encoding="utf-8")
            self.assertIn(
                "MC-CONFLICT-010  Invalid Subject registry syntax or schema",
                table,
            )

    def test_check_builds_one_entry_inventory_for_all_downstream_validation(self):
        with tempfile.TemporaryDirectory() as root:
            memory = self._init(root)
            from memory_custodian.entries import parse_entry_inventory

            with patch(
                "memory_custodian.snapshot.parse_entry_inventory",
                wraps=parse_entry_inventory,
            ) as parser:
                code, output, error = capture(["check", "--project-root", root])
            self.assertEqual(code, 1, output + error)
            paths = [
                call.args[0].relative_to(memory.resolve()).as_posix()
                for call in parser.call_args_list
            ]
            self.assertTrue(paths)
            self.assertEqual(len(paths), len(set(paths)))
            self.assertNotIn("structured_entry_schema_issues", Path(
                "cli/memory_custodian/check.py"
            ).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
