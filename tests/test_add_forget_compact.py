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
            self.assertIn("Tombstone: SQLite", (memory / "do-not-use.md").read_text(encoding="utf-8"))

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


if __name__ == "__main__":
    unittest.main()
