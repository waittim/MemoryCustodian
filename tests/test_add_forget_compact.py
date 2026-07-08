from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli"))

from memory_custodian.main import main


class AddForgetCompactTests(unittest.TestCase):
    def test_add_decision_and_forget_topic(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            self.assertEqual(main(["add", "SQLite should be used for local cache.", "--type", "decision", "--project-root", tmp]), 0)
            memory = Path(tmp) / "docs" / "memory"
            self.assertIn("SQLite", (memory / "decisions.md").read_text(encoding="utf-8"))

            self.assertEqual(main(["forget", "SQLite", "--project-root", tmp, "--mode", "soft"]), 0)
            self.assertNotIn("SQLite", (memory / "decisions.md").read_text(encoding="utf-8"))
            tombstones = (memory / "do-not-use.md").read_text(encoding="utf-8")
            self.assertIn("Tombstone: SQLite", tombstones)
            self.assertNotIn("Status:", tombstones)
            self.assertLess(tombstones.index("Tombstone: SQLite"), tombstones.index("Tombstone: Full memory"))

    def test_add_time_series_memory_is_newest_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            self.assertEqual(main(["add", "First decision marker.", "--type", "decision", "--project-root", tmp]), 0)
            self.assertEqual(main(["add", "Second decision marker.", "--type", "decision", "--project-root", tmp]), 0)
            memory = Path(tmp) / "docs" / "memory"
            decisions = (memory / "decisions.md").read_text(encoding="utf-8")
            self.assertLess(decisions.index("Second decision marker"), decisions.index("First decision marker"))
            self.assertLess(decisions.index("First decision marker"), decisions.index("Use MemoryCustodian"))

            self.assertEqual(main(["add", "First rejected marker.", "--type", "tombstone", "--project-root", tmp]), 0)
            self.assertEqual(main(["add", "Second rejected marker.", "--type", "tombstone", "--project-root", tmp]), 0)
            tombstones = (memory / "do-not-use.md").read_text(encoding="utf-8")
            self.assertLess(tombstones.index("Tombstone: Second rejected marker"), tombstones.index("Tombstone: First rejected marker"))
            self.assertLess(tombstones.index("Tombstone: First rejected marker"), tombstones.index("Tombstone: Full memory"))

            self.assertEqual(main(["add", "First inbox marker.", "--type", "inbox", "--project-root", tmp]), 0)
            self.assertEqual(main(["add", "Second inbox marker.", "--type", "inbox", "--project-root", tmp]), 0)
            inbox = (memory / "inbox.md").read_text(encoding="utf-8")
            self.assertNotIn("No unprocessed memory candidates.", inbox)
            self.assertLess(inbox.index("Second inbox marker"), inbox.index("First inbox marker"))

    def test_compact_dry_run_and_apply(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            memory = Path(tmp) / "docs" / "memory"
            (memory / "inbox.md").write_text(
                "# Memory Inbox\n\n## Today\n- User prefers short context packs.\n- Must work offline.\n- Must work offline.\n- Unclear temporary note.\n",
                encoding="utf-8",
            )
            out = StringIO()
            with redirect_stdout(out):
                self.assertEqual(main(["compact", "--project-root", tmp]), 0)
            self.assertIn("Dry run only", out.getvalue())

            self.assertEqual(main(["compact", "--project-root", tmp, "--apply"]), 0)
            self.assertIn("short context packs", (memory / "preferences.md").read_text(encoding="utf-8"))
            self.assertIn("work offline", (memory / "constraints.md").read_text(encoding="utf-8"))
            inbox = (memory / "inbox.md").read_text(encoding="utf-8")
            self.assertIn("Unclear temporary note", inbox)
            self.assertEqual(inbox.count("Must work offline"), 0)

    def test_compact_prepends_dated_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            memory = Path(tmp) / "docs" / "memory"
            (memory / "inbox.md").write_text(
                "# Memory Inbox\n\n"
                "Entries are newest first.\n\n"
                "## Today\n"
                "- We decided to keep newest compact marker first.\n"
                "- We decided to keep older compact marker second.\n"
                "- Do not use stale memory ordering.\n",
                encoding="utf-8",
            )

            self.assertEqual(main(["compact", "--project-root", tmp, "--apply"]), 0)
            decisions = (memory / "decisions.md").read_text(encoding="utf-8")
            self.assertLess(decisions.index("newest compact marker"), decisions.index("older compact marker"))
            self.assertLess(decisions.index("older compact marker"), decisions.index("Use MemoryCustodian"))
            tombstones = (memory / "do-not-use.md").read_text(encoding="utf-8")
            self.assertLess(tombstones.index("stale memory ordering"), tombstones.index("Tombstone: Full memory"))

    def test_compact_target_archives_old_h2_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            memory = Path(tmp) / "docs" / "memory"
            entries = []
            for index in range(12):
                words = " ".join(f"word{index}_{number}" for number in range(80))
                entries.append(
                    f"## 2026-01-{index + 1:02d} - Decision marker {index}\n"
                    f"Decision:\nKeep decision marker {index}. {words}\n"
                    f"Reason:\nReason marker {index}."
                )
            (memory / "decisions.md").write_text("# Decisions\n\nEntries are newest first.\n\n" + "\n\n".join(entries) + "\n", encoding="utf-8")

            out = StringIO()
            with redirect_stdout(out):
                self.assertEqual(main(["compact", "--project-root", tmp, "--target", "decisions.md"]), 0)
            text = out.getvalue()
            self.assertIn("Target: decisions.md", text)
            self.assertIn("Archive entries:", text)
            self.assertFalse((memory / "archive").exists())

            self.assertEqual(main(["compact", "--project-root", tmp, "--target", "decisions.md", "--apply"]), 0)
            active = (memory / "decisions.md").read_text(encoding="utf-8")
            archive_files = sorted((memory / "archive").glob("decisions-*.md"))
            self.assertEqual(len(archive_files), 1)
            archived = archive_files[0].read_text(encoding="utf-8")
            self.assertIn("Decision marker 11", archived)
            self.assertNotIn("Decision marker 11", active)

            out = StringIO()
            with redirect_stdout(out):
                self.assertEqual(main(["check", "--project-root", tmp]), 0)

    def test_compact_target_dedupes_constraints(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            memory = Path(tmp) / "docs" / "memory"
            repeated = "\n".join("- Must keep duplicate constraint." for _ in range(120))
            (memory / "constraints.md").write_text("# Constraints\n\n" + repeated + "\n", encoding="utf-8")

            out = StringIO()
            with redirect_stdout(out):
                self.assertEqual(main(["compact", "--project-root", tmp, "--target", "constraints.md"]), 0)
            self.assertIn("remove 119 exact duplicate bullet(s)", out.getvalue())

            self.assertEqual(main(["compact", "--project-root", tmp, "--target", "constraints.md", "--apply"]), 0)
            constraints = (memory / "constraints.md").read_text(encoding="utf-8")
            self.assertEqual(constraints.count("Must keep duplicate constraint"), 1)

    def test_compact_target_changelog_does_not_reinflate_itself(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            self.assertEqual(main(["enable", "changelog", "--project-root", tmp]), 0)
            memory = Path(tmp) / "docs" / "memory"
            entries = []
            for index in range(12):
                words = " ".join(f"change{index}_{number}" for number in range(80))
                entries.append(f"## 2026-01-{index + 1:02d}\n- Changelog marker {index}. {words}")
            (memory / "changelog.md").write_text("# Memory Changelog\n\nEntries are newest first.\n\n" + "\n\n".join(entries) + "\n", encoding="utf-8")

            self.assertEqual(main(["compact", "--project-root", tmp, "--target", "changelog.md", "--apply"]), 0)
            out = StringIO()
            with redirect_stdout(out):
                self.assertEqual(main(["check", "--project-root", tmp]), 0)
            active = (memory / "changelog.md").read_text(encoding="utf-8")
            self.assertNotIn("Compacted changelog.md", active)

    def test_add_rule_creates_optional_rule_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            self.assertEqual(
                main(["add", "Do not include internal notes in published text.", "--type", "rule", "--name", "output", "--project-root", tmp]),
                0,
            )
            rule = Path(tmp) / "docs" / "memory" / "rules" / "output.md"
            self.assertIn("Rule: Output", rule.read_text(encoding="utf-8"))
            self.assertIn("published text", rule.read_text(encoding="utf-8"))
            manifest = Path(tmp) / "docs" / "memory" / "manifest.md"
            self.assertIn("`rules/output.md`", manifest.read_text(encoding="utf-8"))

    def test_add_area_indexes_optional_area_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            self.assertEqual(
                main(["add", "CLI code lives under cli/memory_custodian.", "--type", "area", "--name", "backend", "--project-root", tmp]),
                0,
            )
            memory = Path(tmp) / "docs" / "memory"
            self.assertIn("Area: Backend", (memory / "areas" / "backend.md").read_text(encoding="utf-8"))
            self.assertIn("`areas/backend.md`", (memory / "manifest.md").read_text(encoding="utf-8"))

    def test_hard_forget_does_not_rewrite_topic_to_changelog(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            self.assertEqual(main(["enable", "changelog", "--project-root", tmp]), 0)
            self.assertEqual(main(["add", "SensitiveTopic should not remain.", "--type", "decision", "--project-root", tmp]), 0)

            self.assertEqual(main(["forget", "SensitiveTopic", "--mode", "hard", "--project-root", tmp]), 0)
            memory = Path(tmp) / "docs" / "memory"
            self.assertNotIn("SensitiveTopic", (memory / "changelog.md").read_text(encoding="utf-8"))
            self.assertIn("Completed hard forget operation.", (memory / "changelog.md").read_text(encoding="utf-8"))

    def test_changelog_entries_are_newest_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            self.assertEqual(main(["enable", "changelog", "--project-root", tmp]), 0)
            self.assertEqual(main(["add", "Use newest-first changelog entries.", "--type", "decision", "--project-root", tmp]), 0)

            changelog = (Path(tmp) / "docs" / "memory" / "changelog.md").read_text(encoding="utf-8")
            self.assertIn("Entries are newest first.", changelog)
            self.assertLess(
                changelog.index("Added decision memory to decisions.md."),
                changelog.index("Enabled optional memory module changelog.md."),
            )


if __name__ == "__main__":
    unittest.main()
