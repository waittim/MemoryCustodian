from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli"))

from memory_custodian.main import main


def curate_brief(memory: Path) -> None:
    (memory / "brief.md").write_text(
        "# Project Brief\n\nPurpose:\nTest project.\n\nCurrent direction:\nValidate memory behavior.\n",
        encoding="utf-8",
    )


class AddForgetCompactTests(unittest.TestCase):
    def test_add_decision_and_forget_topic(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            self.assertEqual(main(["add", "SQLite should be used for local cache.", "--type", "decision", "--project-root", tmp]), 0)
            memory = Path(tmp) / "docs" / "memory"
            self.assertIn("SQLite", (memory / "decisions.md").read_text(encoding="utf-8"))

            out = StringIO()
            with redirect_stdout(out):
                self.assertEqual(main(["forget", "SQLite", "--project-root", tmp, "--mode", "soft"]), 0)
            self.assertIn("Dry run only", out.getvalue())
            self.assertIn("SQLite", (memory / "decisions.md").read_text(encoding="utf-8"))
            self.assertEqual(main(["forget", "SQLite", "--project-root", tmp, "--mode", "soft", "--apply"]), 0)
            self.assertNotIn("SQLite", (memory / "decisions.md").read_text(encoding="utf-8"))
            tombstones = (memory / "do-not-use.md").read_text(encoding="utf-8")
            self.assertIn("Tombstone: SQLite", tombstones)
            self.assertNotIn("Status:", tombstones)

    def test_add_time_series_memory_is_newest_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            self.assertEqual(main(["add", "First decision marker.", "--type", "decision", "--project-root", tmp]), 0)
            self.assertEqual(main(["add", "Second decision marker.", "--type", "decision", "--project-root", tmp]), 0)
            memory = Path(tmp) / "docs" / "memory"
            decisions = (memory / "decisions.md").read_text(encoding="utf-8")
            self.assertLess(decisions.index("Second decision marker"), decisions.index("First decision marker"))

            self.assertEqual(main(["add", "First rejected marker.", "--type", "tombstone", "--project-root", tmp]), 0)
            self.assertEqual(main(["add", "Second rejected marker.", "--type", "tombstone", "--project-root", tmp]), 0)
            tombstones = (memory / "do-not-use.md").read_text(encoding="utf-8")
            self.assertLess(tombstones.index("Tombstone: Second rejected marker"), tombstones.index("Tombstone: First rejected marker"))

            self.assertEqual(main(["add", "First inbox marker.", "--type", "inbox", "--project-root", tmp]), 0)
            self.assertEqual(main(["add", "Second inbox marker.", "--type", "inbox", "--project-root", tmp]), 0)
            inbox = (memory / "inbox.md").read_text(encoding="utf-8")
            self.assertNotIn("No unprocessed memory candidates.", inbox)
            self.assertLess(inbox.index("Second inbox marker"), inbox.index("First inbox marker"))

    def test_compact_reports_candidates_and_applies_only_exact_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            memory = Path(tmp) / "docs" / "memory"
            original_decisions = (memory / "decisions.md").read_text(encoding="utf-8")
            original_constraints = (memory / "constraints.md").read_text(encoding="utf-8")
            (memory / "do-not-use.md").write_text(
                "# Do Not Use / Tombstones\n\n- Exact forbidden note.\n",
                encoding="utf-8",
            )
            (memory / "inbox.md").write_text(
                "# Memory Inbox\n\n"
                "## Today\n"
                "- User prefers short context packs.\n"
                "- Must investigate whether SQLite is appropriate.\n"
                "- Must investigate whether SQLite is appropriate.\n"
                "- We decided to evaluate a remote cache.\n"
                "- Exact forbidden note.\n",
                encoding="utf-8",
            )
            out = StringIO()
            with redirect_stdout(out):
                self.assertEqual(main(["compact", "--project-root", tmp]), 0)
            preview = out.getvalue()
            self.assertIn("Exact duplicates removable: 1", preview)
            self.assertIn("Exact tombstone matches removable: 1", preview)
            self.assertIn("Candidates requiring Agent review: 3", preview)
            self.assertIn("Must investigate whether SQLite is appropriate", preview)
            self.assertIn("No semantic destinations are inferred", preview)

            self.assertEqual(main(["compact", "--project-root", tmp, "--apply"]), 0)
            inbox = (memory / "inbox.md").read_text(encoding="utf-8")
            self.assertIn("User prefers short context packs", inbox)
            self.assertIn("We decided to evaluate a remote cache", inbox)
            self.assertEqual(inbox.count("Must investigate whether SQLite is appropriate"), 1)
            self.assertNotIn("Exact forbidden note", inbox)
            self.assertFalse((memory / "preferences.md").exists())
            self.assertEqual((memory / "decisions.md").read_text(encoding="utf-8"), original_decisions)
            self.assertEqual((memory / "constraints.md").read_text(encoding="utf-8"), original_constraints)

    def test_compact_inbox_preserves_shared_nested_details_in_distinct_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            inbox = Path(tmp) / "docs" / "memory" / "inbox.md"
            inbox.write_text(
                "# Memory Inbox\n\n"
                "Entries are newest first.\n\n"
                "- Evaluate local storage\n"
                "  Context for the local option.\n"
                "  - Compare SQLite and JSON\n"
                "- Evaluate sync storage\n"
                "  Context for the sync option.\n"
                "  - Compare SQLite and JSON\n",
                encoding="utf-8",
            )

            out = StringIO()
            with redirect_stdout(out):
                self.assertEqual(main(["compact", "--project-root", tmp]), 0)
            self.assertIn("Exact duplicates removable: 0", out.getvalue())

            self.assertEqual(main(["compact", "--project-root", tmp, "--apply"]), 0)
            compacted = inbox.read_text(encoding="utf-8")
            self.assertIn("Evaluate local storage", compacted)
            self.assertIn("Evaluate sync storage", compacted)
            self.assertEqual(compacted.count("Compare SQLite and JSON"), 2)

    def test_compact_inbox_dedupes_complete_top_level_bullet_units(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            inbox = Path(tmp) / "docs" / "memory" / "inbox.md"
            inbox.write_text(
                "# Memory Inbox\n\n"
                "Entries are newest first.\n\n"
                "- Evaluate local storage\n"
                "  Keep this continuation with its candidate.\n"
                "  - Compare SQLite and JSON\n"
                "- Evaluate local storage\n"
                "  Keep this continuation with its candidate.\n"
                "  - Compare SQLite and JSON\n",
                encoding="utf-8",
            )

            out = StringIO()
            with redirect_stdout(out):
                self.assertEqual(main(["compact", "--project-root", tmp]), 0)
            self.assertIn("Exact duplicates removable: 1", out.getvalue())

            self.assertEqual(main(["compact", "--project-root", tmp, "--apply"]), 0)
            compacted = inbox.read_text(encoding="utf-8")
            self.assertEqual(compacted.count("Evaluate local storage"), 1)
            self.assertEqual(compacted.count("Keep this continuation"), 1)
            self.assertEqual(compacted.count("Compare SQLite and JSON"), 1)

    def test_compact_preserves_nested_indentation_in_exact_unit_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            inbox = Path(tmp) / "docs" / "memory" / "inbox.md"
            inbox.write_text(
                "# Memory Inbox\n\n"
                "- Candidate\n"
                "  - Child\n"
                "    - Grandchild\n"
                "- Candidate\n"
                "    - Child\n"
                "  - Grandchild\n",
                encoding="utf-8",
            )

            out = StringIO()
            with redirect_stdout(out):
                self.assertEqual(main(["compact", "--project-root", tmp]), 0)

            preview = out.getvalue()
            self.assertIn("Inbox items: 2", preview)
            self.assertIn("Exact duplicates removable: 0", preview)
            self.assertIn("Grandchild", preview)

    def test_compact_counts_star_and_plus_top_level_units_but_not_nested_or_fenced_bullets(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            inbox = Path(tmp) / "docs" / "memory" / "inbox.md"
            inbox.write_text(
                "# Memory Inbox\n\n"
                "* Candidate A\n"
                "  - Nested detail\n"
                "+ Candidate B\n"
                "  * Nested detail\n"
                "```markdown\n"
                "- Example only\n"
                "```\n",
                encoding="utf-8",
            )

            out = StringIO()
            with redirect_stdout(out):
                self.assertEqual(main(["compact", "--project-root", tmp]), 0)

            preview = out.getvalue()
            self.assertIn("Inbox items: 2", preview)
            self.assertIn("Candidates requiring Agent review: 2", preview)

    def test_compact_removes_exact_inbox_match_for_h2_tombstone(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            self.assertEqual(
                main(["add", "Avoid remote cache.", "--type", "tombstone", "--project-root", tmp]),
                0,
            )
            self.assertEqual(
                main(["add", "Avoid remote cache.", "--type", "inbox", "--project-root", tmp]),
                0,
            )
            memory = Path(tmp) / "docs" / "memory"
            tombstones = (memory / "do-not-use.md").read_text(encoding="utf-8")

            out = StringIO()
            with redirect_stdout(out):
                self.assertEqual(main(["compact", "--project-root", tmp]), 0)
            self.assertIn("Exact tombstone matches removable: 1", out.getvalue())

            self.assertEqual(main(["compact", "--project-root", tmp, "--apply"]), 0)
            self.assertNotIn("Avoid remote cache.", (memory / "inbox.md").read_text(encoding="utf-8"))
            self.assertEqual((memory / "do-not-use.md").read_text(encoding="utf-8"), tombstones)

    def test_compact_apply_does_not_promote_keyword_candidates(self):
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
            original_inbox = (memory / "inbox.md").read_text(encoding="utf-8")
            original_decisions = (memory / "decisions.md").read_text(encoding="utf-8")
            original_tombstones = (memory / "do-not-use.md").read_text(encoding="utf-8")

            out = StringIO()
            with redirect_stdout(out):
                self.assertEqual(main(["compact", "--project-root", tmp, "--apply"]), 0)
            self.assertIn("No deterministic inbox changes to apply", out.getvalue())
            self.assertEqual((memory / "inbox.md").read_text(encoding="utf-8"), original_inbox)
            self.assertEqual((memory / "decisions.md").read_text(encoding="utf-8"), original_decisions)
            self.assertEqual((memory / "do-not-use.md").read_text(encoding="utf-8"), original_tombstones)

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
            self.assertIn("Semantic review required", text)
            self.assertFalse((memory / "archive").exists())

            self.assertEqual(main(["compact", "--project-root", tmp, "--target", "decisions.md", "--apply"]), 1)
            self.assertFalse((memory / "archive").exists())
            self.assertEqual(
                main(
                    [
                        "compact",
                        "--project-root",
                        tmp,
                        "--target",
                        "decisions.md",
                        "--apply",
                        "--archive-oldest",
                    ]
                ),
                0,
            )
            active = (memory / "decisions.md").read_text(encoding="utf-8")
            archive_files = sorted((memory / "archive").glob("decisions-*.md"))
            self.assertEqual(len(archive_files), 1)
            archived = archive_files[0].read_text(encoding="utf-8")
            self.assertIn("Decision marker 11", archived)
            self.assertNotIn("Decision marker 11", active)

            curate_brief(memory)
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

    def test_compact_target_preserves_shared_nested_details_in_distinct_bullets(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            memory = Path(tmp) / "docs" / "memory"
            payload = " ".join(f"context{index}" for index in range(230))
            constraints = memory / "constraints.md"
            constraints.write_text(
                "# Constraints\n\n"
                f"- Candidate A {payload}\n"
                "  - Shared nested detail\n"
                f"- Candidate B {payload}\n"
                "  - Shared nested detail\n",
                encoding="utf-8",
            )

            out = StringIO()
            with redirect_stdout(out):
                self.assertEqual(
                    main(["compact", "--project-root", tmp, "--target", "constraints.md"]),
                    0,
                )
            self.assertNotIn("exact duplicate bullet", out.getvalue())

            self.assertEqual(
                main(["compact", "--project-root", tmp, "--target", "constraints.md", "--apply"]),
                0,
            )
            compacted = constraints.read_text(encoding="utf-8")
            self.assertIn("Candidate A", compacted)
            self.assertIn("Candidate B", compacted)
            self.assertEqual(compacted.count("Shared nested detail"), 2)

    def test_compact_target_dedupes_complete_top_level_bullet_units(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            constraints = Path(tmp) / "docs" / "memory" / "constraints.md"
            unit = (
                "- Keep the exact candidate\n"
                "  Keep this continuation with its constraint.\n"
                "  - Preserve this nested detail\n"
            )
            constraints.write_text("# Constraints\n\n" + unit * 70, encoding="utf-8")

            out = StringIO()
            with redirect_stdout(out):
                self.assertEqual(
                    main(["compact", "--project-root", tmp, "--target", "constraints.md"]),
                    0,
                )
            self.assertIn("remove 69 exact duplicate bullet(s)", out.getvalue())

            self.assertEqual(
                main(["compact", "--project-root", tmp, "--target", "constraints.md", "--apply"]),
                0,
            )
            compacted = constraints.read_text(encoding="utf-8")
            self.assertEqual(compacted.count("Keep the exact candidate"), 1)
            self.assertEqual(compacted.count("Keep this continuation"), 1)
            self.assertEqual(compacted.count("Preserve this nested detail"), 1)

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
            curate_brief(memory)
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

    def test_add_scoped_decision_uses_area_and_reports_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            out = StringIO()
            with redirect_stdout(out):
                self.assertEqual(
                    main(
                        [
                            "add",
                            "Persist retry backoff across launches.",
                            "--type",
                            "decision",
                            "--area",
                            "sync",
                            "--reason",
                            "Keep retries bounded.",
                            "--project-root",
                            tmp,
                        ]
                    ),
                    0,
                )
            memory = Path(tmp) / "docs" / "memory"
            area = (memory / "areas" / "sync.md").read_text(encoding="utf-8")
            self.assertIn("Decision:", area)
            self.assertIn("Persist retry backoff", area)
            self.assertNotIn("Persist retry backoff", (memory / "decisions.md").read_text(encoding="utf-8"))
            self.assertIn("`areas/sync.md`", (memory / "manifest.md").read_text(encoding="utf-8"))
            self.assertIn("Budget: areas/sync.md", out.getvalue())

    def test_add_warns_when_decisions_exceed_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            memory = Path(tmp) / "docs" / "memory"
            words = " ".join(f"word{index}" for index in range(900))
            out = StringIO()
            with redirect_stdout(out):
                self.assertEqual(
                    main(["add", words, "--type", "decision", "--allow-long", "--project-root", tmp]),
                    0,
                )
            text = out.getvalue()
            self.assertIn("explicitly allowed long decision", text)
            self.assertIn("Warning: decisions.md is over its context budget", text)
            self.assertIn("consolidate or relocate scoped decisions", text)

    def test_add_rejects_long_decision_before_creating_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            message = " ".join(f"detail{index}" for index in range(140))
            out = StringIO()
            with redirect_stdout(out):
                code = main(
                    [
                        "add",
                        message,
                        "--type",
                        "decision",
                        "--area",
                        "sync",
                        "--project-root",
                        tmp,
                    ]
                )
            self.assertEqual(code, 1)
            self.assertIn("Decision entry budget:", out.getvalue())
            self.assertIn("Not added: shorten Decision", out.getvalue())
            self.assertFalse((Path(tmp) / "docs" / "memory" / "areas" / "sync.md").exists())

    def test_compact_reports_long_decision_even_when_file_is_within_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            message = " ".join(f"detail{index}" for index in range(140))
            self.assertEqual(
                main(["add", message, "--type", "decision", "--allow-long", "--project-root", tmp]),
                0,
            )
            out = StringIO()
            with redirect_stdout(out):
                self.assertEqual(main(["compact", "--target", "decisions.md", "--project-root", tmp]), 0)
            text = out.getvalue()
            self.assertIn("Long decision entries: 1 over 120 tokens", text)
            self.assertIn("Manual review required: shorten long decisions semantically", text)

    def test_compact_does_not_archive_around_kept_long_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            memory = Path(tmp) / "docs" / "memory"
            long_words = " ".join(f"long{index}" for index in range(180))
            entries = [
                "## 2026-07-12 - Long active decision\n"
                f"Decision:\n{long_words}\n"
                "Reason:\nIt is still active."
            ]
            for index in range(10):
                words = " ".join(f"short{index}_{number}" for number in range(70))
                entries.append(
                    f"## 2026-07-{index + 1:02d} - Short decision {index}\n"
                    f"Decision:\n{words}\nReason:\nHistorical context."
                )
            (memory / "decisions.md").write_text(
                "# Decisions\n\nEntries are newest first.\n\n" + "\n\n".join(entries) + "\n",
                encoding="utf-8",
            )

            out = StringIO()
            with redirect_stdout(out):
                code = main(
                    [
                        "compact",
                        "--target",
                        "decisions.md",
                        "--apply",
                        "--archive-oldest",
                        "--project-root",
                        tmp,
                    ]
                )
            self.assertEqual(code, 1)
            self.assertIn("shorten the kept long decisions", out.getvalue())
            self.assertFalse((memory / "archive").exists())

    def test_hard_forget_does_not_rewrite_topic_to_changelog(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            self.assertEqual(main(["enable", "changelog", "--project-root", tmp]), 0)
            self.assertEqual(main(["add", "SensitiveTopic should not remain.", "--type", "decision", "--project-root", tmp]), 0)

            self.assertEqual(main(["forget", "SensitiveTopic", "--mode", "hard", "--apply", "--project-root", tmp]), 0)
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
