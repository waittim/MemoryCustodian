"""Adversarial regression coverage for the Protocol 0.7 release boundary."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from memory_custodian.conflicts import analyze_conflicts
from memory_custodian.entries import (
    parse_structured_entries,
    render_active_entry,
    structured_entry_schema_issues,
    supersede_entry,
)
from memory_custodian.main import main
from memory_custodian.mutations import TextMutation, apply_mutations
from memory_custodian.protocol import count_inbox_items, decision_entry_sizes


def run_cli(arguments: list[str]) -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = main(arguments)
    return code, stdout.getvalue(), stderr.getvalue()


def git(root: str, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments], cwd=root, text=True,
        capture_output=True, check=True,
    )
    return result.stdout.strip()


class AdversarialAuditRegressionTests(unittest.TestCase):
    def test_duplicate_entry_schema_blocks_conflicts(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(run_cli(["init", "--project-root", tmp])[0], 0)
            memory = Path(tmp) / "docs/memory"
            entry = render_active_entry(
                "decision", "MC-DEC-20260825-aaaaaaaa", "Duplicate", "Body.",
                None, "project", ("user-confirmed",),
            ).replace("Status: active", "Status: active\nStatus: active", 1)
            (memory / "decisions.md").write_text(
                "# Decisions\n\n" + entry + "\n", encoding="utf-8",
            )
            result = analyze_conflicts(memory)
            self.assertEqual(result.status.value, "INVALID")
            self.assertTrue(any("duplicate Status" in item.message for item in result.findings))

    def test_fenced_body_round_trips_without_rewriting_code(self):
        body = '```python\nif True:\n    print("x")\n```'
        rendered = render_active_entry(
            "decision", "MC-DEC-20260825-bbbbbbbb", "Code", body,
            None, "project", ("user-confirmed",),
        )
        parsed = parse_structured_entries(Path("decisions.md"), rendered)
        self.assertEqual(parsed[0].field_bodies["Decision"], body)
        self.assertEqual(structured_entry_schema_issues(parsed[0], "decisions.md"), [])

    def test_rule_supersession_uses_real_storage_schema(self):
        old_id = "MC-AREA-20260825-cccccccc"
        new_id = "MC-AREA-20260825-dddddddd"
        original = render_active_entry(
            "rule", old_id, "Backend rule", "Keep it short.", None,
            "project", ("user-confirmed",),
        )
        updated = supersede_entry(
            "# Rules\n\n" + original + "\n",
            old_id,
            new_id,
            relative_path="rules/backend.md",
        )
        parsed = parse_structured_entries(Path("rules/backend.md"), updated)
        self.assertEqual(parsed[0].status, "superseded")
        self.assertEqual(parsed[0].fields["Superseded-By"], new_id)

    def test_readme_is_not_a_promotable_or_addable_module(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(run_cli(["init", "--project-root", tmp])[0], 0)
            code, _output, error = run_cli([
                "add", "Documentation", "--type", "rule", "--name", "README",
                "--evidence", "user-confirmed", "--project-root", tmp,
            ])
            self.assertEqual(code, 2)
            self.assertIn("reserved documentation", error)

    def test_init_refuses_agent_file_symlink(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            secret = Path(outside) / "secret.md"
            secret.write_text("ExternalSecretToken\n", encoding="utf-8")
            agent = Path(tmp) / "AGENTS.md"
            agent.symlink_to(secret)
            code, output, error = run_cli([
                "init", "--with-codex", "--project-root", tmp,
            ])
            self.assertEqual(code, 2)
            self.assertNotIn("ExternalSecretToken", output + error)
            self.assertTrue(agent.is_symlink())

    @unittest.skipIf(os.name == "nt", "POSIX symlink semantics")
    def test_init_and_repair_refuse_symlinked_docs_without_external_writes(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            root = Path(tmp)
            external_memory = Path(outside) / "memory"
            external_memory.mkdir()
            sentinel = external_memory / "sentinel.md"
            sentinel.write_text("do not modify\n", encoding="utf-8")
            (root / "docs").symlink_to(external_memory.parent, target_is_directory=True)

            for arguments in (
                ["init", "--project-root", tmp],
                ["init", "--repair", "--project-root", tmp],
            ):
                code, output, error = run_cli(arguments)
                self.assertEqual(code, 2, output + error)
                self.assertIn("symlinked path component", error)
                self.assertEqual(sentinel.read_text(encoding="utf-8"), "do not modify\n")
                self.assertFalse((root / "AGENTS.md").exists())
            self.assertEqual(tuple(external_memory.iterdir()), (sentinel,))

    @unittest.skipIf(os.name == "nt", "POSIX symlink semantics")
    def test_mutation_refuses_symlinked_ancestor(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "areas").mkdir()
            (root / "archive").symlink_to(root / "areas", target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "unsafe ancestor"):
                apply_mutations([TextMutation(root / "archive" / "entry.md", "secret")])
            self.assertFalse((root / "areas" / "entry.md").exists())

    @unittest.skipIf(os.name == "nt", "POSIX symlink semantics")
    def test_mutation_refuses_memory_ancestor_symlink_without_external_writes(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            root = Path(tmp)
            memory = root / "docs" / "memory"
            memory.mkdir(parents=True)
            external_archive = Path(outside) / "archive"
            external_archive.mkdir()
            target = memory / "archive" / "entry.md"
            (memory / "archive").symlink_to(external_archive, target_is_directory=True)

            with self.assertRaisesRegex(ValueError, "unsafe ancestor"):
                apply_mutations([TextMutation(target, "secret")])
            self.assertFalse((external_archive / "entry.md").exists())

    @unittest.skipIf(os.name == "nt", "POSIX symlink semantics")
    def test_mutation_refuses_docs_symlink_without_external_writes(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            root = Path(tmp)
            external_memory = Path(outside) / "memory"
            external_memory.mkdir()
            target = root / "docs" / "memory" / "new.md"
            (root / "docs").symlink_to(Path(outside), target_is_directory=True)

            with self.assertRaisesRegex(ValueError, "unsafe ancestor"):
                apply_mutations([TextMutation(target, "secret")])
            self.assertFalse((external_memory / "new.md").exists())

    def test_merge_review_reports_deletion_against_target_modification(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(run_cli(["init", "--project-root", tmp])[0], 0)
            git(tmp, "init", "-q")
            git(tmp, "config", "user.email", "audit@example.invalid")
            git(tmp, "config", "user.name", "Audit")
            memory = Path(tmp) / "docs/memory"
            subject_id = "MC-SUBJ-20260825-11111111"
            entry_id = "MC-DEC-20260825-22222222"
            (memory / "subjects.md").write_text(
                "# Subject Registry\n\n"
                f"## {subject_id} — Subject\n\nStatus: active\nKind: concept\n"
                "Evidence:\n- user-confirmed\n\nAliases:\n- subject\n",
                encoding="utf-8",
            )
            entry = render_active_entry(
                "decision", entry_id, "Concurrent", "Original.", None,
                "project", ("user-confirmed",), subject=subject_id, facet="behavior",
            )
            decisions = memory / "decisions.md"
            decisions.write_text("# Decisions\n\n" + entry + "\n", encoding="utf-8")
            git(tmp, "add", ".")
            git(tmp, "commit", "-qm", "base")
            base = git(tmp, "rev-parse", "HEAD")
            head_ref = git(tmp, "branch", "--show-current")

            decisions.write_text("# Decisions\n\n", encoding="utf-8")
            git(tmp, "add", ".")
            git(tmp, "commit", "-qm", "delete entry")

            git(tmp, "checkout", "-qb", "audit-target", base)
            decisions.write_text(
                "# Decisions\n\n" + entry.replace("Original.", "Target changed.") + "\n",
                encoding="utf-8",
            )
            git(tmp, "add", ".")
            git(tmp, "commit", "-qm", "modify entry")
            git(tmp, "checkout", "-q", head_ref)

            code, output, error = run_cli([
                "check", "--conflicts", "--merge-base", "audit-target",
                "--project-root", tmp,
            ])
            self.assertEqual(code, 0, output + error)
            self.assertIn("Merge review status: REVIEW", output)
            self.assertIn("MC-MERGE-REVIEW-006", output)

    def test_visible_counters_ignore_indented_and_fenced_markers(self):
        text = (
            "# Memory Inbox\n\n## MC-INBOX-20260825-eeeeeeee — Example\n\n"
            "```md\nStatus: candidate\n```\n\n"
            "    Status: candidate\n\n"
            "## MC-DEC-20260825-ffffffff — Decision\n\n"
            "```md\nDecision:\n" + "hidden " * 100 + "\n```\n"
        )
        self.assertEqual(count_inbox_items(text), 0)
        self.assertEqual(decision_entry_sizes(text), [])

    def test_protocol_heading_scanner_ignores_indented_code(self):
        from memory_custodian.protocol import strict_protocol_metadata

        manifest = (
            "## MemoryCustodian Protocol\n"
            "- protocol_version: 0.7\n\n"
            "    ## MemoryCustodian Protocol\n"
            "    - protocol_version: 0.6\n"
        )
        self.assertEqual(strict_protocol_metadata(manifest)["protocol_version"], "0.7")

    def test_conflict_integrity_covers_live_and_archive_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(run_cli(["init", "--project-root", tmp])[0], 0)
            memory = Path(tmp) / "docs" / "memory"
            subject_id = "MC-SUBJ-20260825-cccccccc"
            (memory / "subjects.md").write_text(
                "# Subject Registry\n\n"
                f"## {subject_id} — Integrity subject\n\n"
                "Status: active\nKind: concept\nEvidence:\n- user-confirmed\n\n"
                "Aliases:\n- integrity subject\n",
                encoding="utf-8",
            )
            live = render_active_entry(
                "decision", "MC-DEC-20260825-dddddddd", "Live malformed",
                "Live body.", None, "project", ("user-confirmed",),
                subject=subject_id, facet="behavior",
            ).replace("Evidence:\n", "Mystery: accepted\nEvidence:\n", 1)
            live = live.replace("- user-confirmed", "", 1)
            promoted = render_active_entry(
                "decision", "MC-DEC-20260825-eeeeeeee", "Promoted missing target",
                "Promoted body.", None, "project", ("user-confirmed",),
                subject=subject_id, facet="interface",
            ).replace("Status: active", "Status: promoted", 1)
            (memory / "decisions.md").write_text(
                "# Decisions\n\n" + live + "\n\n" + promoted + "\n",
                encoding="utf-8",
            )
            archive = memory / "archive"
            archive.mkdir()
            archived = render_active_entry(
                "decision", "MC-DEC-20260825-ffffffff", "Archive malformed",
                "Archived body.", None, "project", ("user-confirmed",),
                subject=subject_id, facet="workflow",
            ).replace("Evidence:\n", "Unknown-Scalar: accepted\nEvidence:\n", 1)
            (archive / "decisions-old.md").write_text(
                "# Archived Decisions\n\n" + archived + "\n", encoding="utf-8",
            )

            result = analyze_conflicts(memory)
            self.assertEqual(result.status.value, "INVALID")
            messages = "\n".join(item.message for item in result.findings)
            self.assertIn("unknown field Mystery", messages)
            self.assertIn("Evidence", messages)
            self.assertIn("promoted entry", messages)
            self.assertIn("unknown field Unknown-Scalar", messages)

            code, output, error = run_cli([
                "read", "--task", "implementation", "--strict-routing",
                "--names-only", "--project-root", tmp,
            ])
            self.assertEqual(code, 2, output + error)
            self.assertIn("Conflict status: INVALID", output)

    def test_merge_review_rejects_invalid_entries_relations_and_duplicate_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(run_cli(["init", "--project-root", tmp])[0], 0)
            git(tmp, "init", "-q")
            git(tmp, "config", "user.email", "audit@example.invalid")
            git(tmp, "config", "user.name", "Audit")
            memory = Path(tmp) / "docs" / "memory"
            subject_id = "MC-SUBJ-20260825-11111111"
            base_id = "MC-DEC-20260825-22222222"
            (memory / "subjects.md").write_text(
                "# Subject Registry\n\n"
                f"## {subject_id} — Merge subject\n\n"
                "Status: active\nKind: concept\nEvidence:\n- user-confirmed\n\n"
                "Aliases:\n- merge subject\n",
                encoding="utf-8",
            )
            base_entry = render_active_entry(
                "decision", base_id, "Base", "Base body.", None,
                "project", ("user-confirmed",), subject=subject_id, facet="behavior",
            )
            (memory / "decisions.md").write_text(
                "# Decisions\n\n" + base_entry + "\n", encoding="utf-8",
            )
            git(tmp, "add", ".")
            git(tmp, "commit", "-qm", "base")
            base = git(tmp, "rev-parse", "HEAD")
            head_ref = git(tmp, "branch", "--show-current")
            git(tmp, "checkout", "-qb", "audit-target", base)

            target_entry = render_active_entry(
                "decision", "MC-DEC-20260825-33333333", "Dangling and malformed",
                "Target body.", None, "project", ("user-confirmed",),
                subject=subject_id, facet="interface",
                supersedes="MC-DEC-20260825-44444444",
            ).replace("Evidence:\n", "Unknown: accepted\nEvidence:\n", 1)
            target_entry = target_entry.replace("Subject: " + subject_id + "\n", "", 1)
            (memory / "decisions.md").write_text(
                "# Decisions\n\n" + base_entry + "\n\n" + target_entry + "\n",
                encoding="utf-8",
            )
            (memory / "archive").mkdir()
            duplicate_archive = render_active_entry(
                "decision", base_id, "Duplicate archive copy", "Archive body.", None,
                "project", ("user-confirmed",), subject=subject_id, facet="behavior",
            )
            (memory / "archive" / "decisions-old.md").write_text(
                "# Archive\n\n" + duplicate_archive + "\n", encoding="utf-8",
            )
            git(tmp, "add", ".")
            git(tmp, "commit", "-qm", "invalid target entries")
            target_ref = git(tmp, "branch", "--show-current")
            git(tmp, "checkout", "-q", head_ref)

            code, output, error = run_cli([
                "check", "--conflicts", "--merge-base", target_ref,
                "--project-root", tmp,
            ])
            self.assertEqual(code, 1, output + error)
            self.assertIn("Merge review status: CONFLICT", output)
            self.assertIn("MC-MERGE-006", output)
            self.assertIn("references missing entry", output)
            self.assertIn("unknown field Unknown", output)
            self.assertIn("duplicate Entry ID", output)


if __name__ == "__main__":
    unittest.main()
