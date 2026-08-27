"""Regression coverage for single-snapshot freshness validation."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from memory_custodian.entries import render_active_entry
from memory_custodian.main import main
from memory_custodian.quality import freshness_findings
from memory_custodian.snapshot import build_snapshot


def capture(argv: list[str]) -> tuple[int, str, str]:
    output, error = StringIO(), StringIO()
    with redirect_stdout(output), redirect_stderr(error):
        code = main(argv)
    return code, output.getvalue(), error.getvalue()


def subject_unit(subject_id: str) -> str:
    return (
        f"## {subject_id} — Storage policy\n\n"
        "Status: active\nKind: concept\n"
        "Canonical-Ref: feature:storage-policy\n"
        "Evidence:\n- user-confirmed\n\n"
        "Aliases:\n- storage policy\n"
    )


class FreshnessSnapshotTests(unittest.TestCase):
    def _init(self, root: str) -> Path:
        code, output, error = capture(["init", "--project-root", root])
        self.assertEqual(code, 0, output + error)
        return Path(root) / "docs/memory"

    def test_freshness_builds_one_snapshot(self):
        with tempfile.TemporaryDirectory() as root:
            memory = self._init(root)
            with patch(
                "memory_custodian.quality.build_snapshot",
                wraps=build_snapshot,
            ) as build:
                freshness_findings(Path(root), memory)
            self.assertEqual(build.call_count, 1)

    def test_freshness_uses_manifest_contract_from_supplied_snapshot(self):
        """A later manifest edit cannot change an already captured check."""

        with tempfile.TemporaryDirectory() as root:
            memory = self._init(root)
            manifest = memory / "manifest.md"
            valid = manifest.read_text(encoding="utf-8")
            captured = build_snapshot(memory, Path(root))

            manifest.write_text(
                valid.replace("- protocol_version: 0.7", "- protocol_version: 0.7.0", 1),
                encoding="utf-8",
            )
            with patch(
                "memory_custodian.quality.build_snapshot",
                side_effect=AssertionError("freshness rebuilt its supplied snapshot"),
            ), patch(
                "memory_custodian.quality.read_managed_text",
                side_effect=AssertionError("freshness reread the manifest"),
            ):
                findings = freshness_findings(
                    Path(root), memory, snapshot=captured,
                )

            self.assertEqual(findings, ())

            manifest.write_text(valid, encoding="utf-8")
            invalid_manifest = valid.replace(
                "- protocol_version: 0.7", "- protocol_version: 0.7.0", 1,
            )
            manifest.write_text(invalid_manifest, encoding="utf-8")
            invalid_snapshot = build_snapshot(memory, Path(root))
            manifest.write_text(valid, encoding="utf-8")
            findings = freshness_findings(
                Path(root), memory, snapshot=invalid_snapshot,
            )
            self.assertEqual(
                [(item.code, item.message) for item in findings],
                [("MC-ROUTING-007", "Protocol version equivalent to 0.7 must use the canonical value 0.7; manifest has '0.7.0'")],
            )

    def test_snapshot_keeps_one_manifest_capture_for_canonical_authority(self):
        """Canonical selection is based on the manifest captured in the inventory."""

        with tempfile.TemporaryDirectory() as root:
            memory = self._init(root)
            area = memory / "areas" / "backend.md"
            area.parent.mkdir()
            area.write_text("# Backend\n", encoding="utf-8")
            manifest = memory / "manifest.md"
            valid = manifest.read_text(encoding="utf-8")
            declared = (
                "### Enabled areas\n"
                "- `areas/backend.md`\n"
                "  - activation: path\n"
                "  - paths: `cli/**`"
            )
            captured_manifest = valid.replace(
                "### Enabled areas\n- None enabled.", declared, 1,
            )
            manifest.write_text(captured_manifest, encoding="utf-8")
            real_read = __import__(
                "memory_custodian.snapshot", fromlist=["read_managed_text"],
            ).read_managed_text
            reads: list[str] = []

            def read_once(memory_dir, path, **kwargs):
                relative = Path(path).relative_to(Path(memory_dir)).as_posix()
                reads.append(relative)
                text = real_read(memory_dir, path, **kwargs)
                if relative == "manifest.md":
                    manifest.write_text(
                        captured_manifest.replace(declared, "### Enabled areas\n- None enabled."),
                        encoding="utf-8",
                    )
                return text

            with patch(
                "memory_custodian.snapshot.read_managed_text",
                side_effect=read_once,
            ), patch(
                "memory_custodian.snapshot.managed_markdown_files",
                wraps=__import__(
                    "memory_custodian.snapshot", fromlist=["managed_markdown_files"],
                ).managed_markdown_files,
            ) as inventory:
                snapshot = build_snapshot(memory, Path(root))

            self.assertEqual(inventory.call_count, 1)
            self.assertEqual(reads.count("manifest.md"), 1)
            self.assertEqual(len(reads), len(set(reads)))
            self.assertTrue(snapshot.manifest_contract.valid)
            self.assertTrue(snapshot.file_for("areas/backend.md").canonical)

    def test_planned_manifest_overlay_controls_contract_and_canonicality(self):
        with tempfile.TemporaryDirectory() as root:
            memory = self._init(root)
            area = memory / "areas" / "backend.md"
            area.parent.mkdir()
            area.write_text("# Backend\n", encoding="utf-8")
            manifest = memory / "manifest.md"
            valid = manifest.read_text(encoding="utf-8")
            declaration = (
                "### Enabled areas\n"
                "- `areas/backend.md`\n"
                "  - activation: path\n"
                "  - paths: `cli/**`"
            )
            planned_manifest = valid.replace(
                "### Enabled areas\n- None enabled.", declaration, 1,
            )
            snapshot = build_snapshot(
                memory,
                Path(root),
                planned_text={manifest: planned_manifest},
            )

            self.assertEqual(snapshot.manifest_text, planned_manifest)
            self.assertTrue(snapshot.manifest_contract.valid)
            self.assertTrue(snapshot.file_for("areas/backend.md").canonical)

            invalid = planned_manifest.replace(
                "- protocol_version: 0.7", "- protocol_version: 0.7.0", 1,
            )
            invalid_snapshot = build_snapshot(
                memory,
                Path(root),
                planned_text={manifest: invalid},
            )
            self.assertEqual(
                invalid_snapshot.manifest_contract.error,
                "Protocol version equivalent to 0.7 must use the canonical value 0.7; manifest has '0.7.0'",
            )

    def test_ordinary_check_reports_one_structural_owner_finding(self):
        with tempfile.TemporaryDirectory() as root:
            memory = self._init(root)
            subject_id = "MC-SUBJ-20260827-a1b2c3d4"
            (memory / "subjects.md").write_text(
                "# Subject Registry\n\n" + subject_unit(subject_id),
                encoding="utf-8",
            )
            (memory / "constraints.md").write_text(
                "# Constraints\n\n"
                f"## MC-CON-20260827-11111111 — First\n\n"
                f"Status: active\nScope: project\nSubject: {subject_id}\n"
                "Facet: behavior\nEvidence:\n- user-confirmed\n\n"
                "Constraint:\nFirst.\n\n"
                f"## MC-CON-20260827-22222222 — Second\n\n"
                f"Status: active\nScope: project\nSubject: {subject_id}\n"
                "Facet: behavior\nEvidence:\n- user-confirmed\n\n"
                "Constraint:\nSecond.\n",
                encoding="utf-8",
            )

            code, output, error = capture(["check", "--project-root", root])

            self.assertEqual(code, 1, output + error)
            self.assertEqual(output.count("MC-CONFLICT-001"), 1, output)
            self.assertIn("Multiple active owners for one structural identity", output)
            self.assertNotIn("duplicates active structural owner", output)

    def test_freshness_reports_one_entry_relation_finding(self):
        with tempfile.TemporaryDirectory() as root:
            memory = self._init(root)
            subject_id = "MC-SUBJ-20260827-b1b2c3d4"
            (memory / "subjects.md").write_text(
                "# Subject Registry\n\n" + subject_unit(subject_id),
                encoding="utf-8",
            )
            entry_id = "MC-DEC-20260827-11111111"
            replacement_id = "MC-DEC-20260827-22222222"
            replacement = render_active_entry(
                "decision", replacement_id, "Current entry", "Current body.", None,
                "project", ("user-confirmed",), subject=subject_id, facet="behavior",
            )
            (memory / "decisions.md").write_text(
                "# Decisions\n\n"
                f"## {entry_id} — Historical entry\n\n"
                f"Status: superseded\nScope: project\nSuperseded-By: {replacement_id}\n"
                f"Subject: {subject_id}\nFacet: behavior\n"
                "Evidence:\n- user-confirmed\n\n"
                "Decision:\nHistorical body.\n\n"
                + replacement + "\n",
                encoding="utf-8",
            )

            code, output, error = capture([
                "check", "--freshness", "--project-root", root,
            ])

            self.assertEqual(code, 1, output + error)
            self.assertEqual(output.count("MC-FRESH-004"), 1, output)
            self.assertIn(entry_id, output)

    def test_freshness_reports_one_subject_merge_finding(self):
        with tempfile.TemporaryDirectory() as root:
            memory = self._init(root)
            source_id = "MC-SUBJ-20260827-c1c2d3e4"
            (memory / "subjects.md").write_text(
                "# Subject Registry\n\n"
                f"## {source_id} — Merged source\n\n"
                "Status: merged\nKind: concept\n"
                "Merged-Into: MC-SUBJ-20260827-deadbeef\n"
                "Evidence:\n- user-confirmed\n\n"
                "Aliases:\n- merged source\n",
                encoding="utf-8",
            )

            code, output, error = capture([
                "check", "--freshness", "--project-root", root,
            ])

            self.assertEqual(code, 1, output + error)
            self.assertEqual(output.count("MC-FRESH-005"), 1, output)
            self.assertIn("Merged-Into must reference a different active Subject", output)

    def test_freshness_maps_reconciliation_origin_to_freshness_code(self):
        with tempfile.TemporaryDirectory() as root:
            memory = self._init(root)
            subject_id = "MC-SUBJ-20260827-e1e2f3a4"
            (memory / "subjects.md").write_text(
                "# Subject Registry\n\n" + subject_unit(subject_id),
                encoding="utf-8",
            )
            first_id = "MC-DEC-20260827-22222222"
            second_id = "MC-CON-20260827-33333333"
            first = render_active_entry(
                "decision", first_id, "First", "First body.", None,
                "project", ("user-confirmed",), subject=subject_id, facet="behavior",
            )
            second = render_active_entry(
                "constraint", second_id, "Second", "Second body.", None,
                "project", ("user-confirmed",), subject=subject_id, facet="interface",
            )
            (memory / "decisions.md").write_text(
                "# Decisions\n\n" + first + "\n", encoding="utf-8",
            )
            (memory / "constraints.md").write_text(
                "# Constraints\n\n" + second + "\n", encoding="utf-8",
            )
            (memory / "reconciliations.md").write_text(
                "# Reconciliations\n\n"
                "## MC-REC-20260827-abcdef12 — Invalid supersession\n\n"
                "Status: active\nResolution: superseded\nEntries:\n"
                f"- {second_id}\n- {first_id}\n"
                "Evidence:\n- user-confirmed\n",
                encoding="utf-8",
            )

            code, output, error = capture([
                "check", "--freshness", "--project-root", root,
            ])

            self.assertEqual(code, 1, output + error)
            self.assertEqual(output.count("MC-FRESH-006"), 1, output)
            self.assertNotIn("MC-FRESH-004", output)
            self.assertIn("superseded resolution is inconsistent", output)


if __name__ == "__main__":
    unittest.main()
