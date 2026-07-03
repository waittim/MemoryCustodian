from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli"))

from memory_custodian.main import main


class InitTests(unittest.TestCase):
    def test_init_creates_expected_files_without_overwriting_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            memory = Path(tmp) / "docs" / "memory"
            for name in (
                "manifest.md",
                "brief.md",
                "decisions.md",
                "constraints.md",
                "do-not-use.md",
                "inbox.md",
            ):
                self.assertTrue((memory / name).exists(), name)
            self.assertFalse((memory / "preferences.md").exists())
            self.assertFalse((memory / "changelog.md").exists())
            self.assertFalse((memory / "archive").exists())

            brief = memory / "brief.md"
            brief.write_text("# Custom Brief\n", encoding="utf-8")
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            self.assertEqual(brief.read_text(encoding="utf-8"), "# Custom Brief\n")

    def test_init_can_add_codex_snippet(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp, "--agent", "codex"]), 0)
            agents = Path(tmp) / "AGENTS.md"
            self.assertIn("## MemoryCustodian", agents.read_text(encoding="utf-8"))
            self.assertIn("manifest.md", agents.read_text(encoding="utf-8"))

    def test_init_extended_creates_optional_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp, "--extended"]), 0)
            memory = Path(tmp) / "docs" / "memory"
            self.assertTrue((memory / "preferences.md").exists())
            self.assertTrue((memory / "changelog.md").exists())
            self.assertTrue((memory / "rules" / "README.md").exists())
            self.assertTrue((memory / "profiles" / "README.md").exists())
            self.assertTrue((memory / "archive" / "README.md").exists())

    def test_enable_creates_optional_feature(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            self.assertEqual(main(["enable", "rules/output", "--project-root", tmp]), 0)
            memory = Path(tmp) / "docs" / "memory"
            self.assertTrue((memory / "rules" / "output.md").exists())
            self.assertIn("`rules/output.md`", (memory / "manifest.md").read_text(encoding="utf-8"))

    def test_enable_indexes_optional_profiles_and_areas(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            self.assertEqual(main(["enable", "profile/git", "--project-root", tmp]), 0)
            self.assertEqual(main(["enable", "area/frontend", "--project-root", tmp]), 0)
            manifest = (Path(tmp) / "docs" / "memory" / "manifest.md").read_text(encoding="utf-8")
            self.assertIn("## Optional module index", manifest)
            self.assertIn("`profiles/git.md`", manifest)
            self.assertIn("`areas/frontend.md`", manifest)
            profiles_section = manifest.split("### Enabled profiles", 1)[1].split("### Enabled areas", 1)[0]
            self.assertNotIn("None enabled", profiles_section)


if __name__ == "__main__":
    unittest.main()
