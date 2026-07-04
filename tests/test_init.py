from contextlib import redirect_stdout
from io import StringIO
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
            manifest = (memory / "manifest.md").read_text(encoding="utf-8")
            self.assertIn("## MemoryCustodian Protocol", manifest)
            self.assertIn("- protocol_version: 0.4", manifest)
            self.assertIn("- initialized_with: memory-custodian 0.5.0", manifest)
            self.assertIn("Entries are newest first.", (memory / "decisions.md").read_text(encoding="utf-8"))
            self.assertIn("Tombstones are newest first.", (memory / "do-not-use.md").read_text(encoding="utf-8"))
            self.assertIn("Entries are newest first.", (memory / "inbox.md").read_text(encoding="utf-8"))

            brief = memory / "brief.md"
            brief.write_text("# Custom Brief\n", encoding="utf-8")
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            self.assertEqual(brief.read_text(encoding="utf-8"), "# Custom Brief\n")

    def test_init_accepts_custom_memory_dir_under_docs(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp, "--memory-dir", "docs/team-memory", "--agent", "codex"]), 0)
            memory = Path(tmp) / "docs" / "team-memory"
            self.assertTrue((memory / "manifest.md").exists())
            self.assertIn("docs/team-memory", (memory / "brief.md").read_text(encoding="utf-8"))
            self.assertIn("docs/team-memory/manifest.md", (Path(tmp) / "AGENTS.md").read_text(encoding="utf-8"))

    def test_init_rejects_memory_dir_outside_docs(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = StringIO()
            with redirect_stdout(out):
                code = main(["init", "--project-root", tmp, "--memory-dir", ".memory"])
            self.assertEqual(code, 1)
            self.assertIn("Memory directory must live under docs/", out.getvalue())
            self.assertFalse((Path(tmp) / ".memory").exists())

    def test_init_can_add_codex_snippet(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp, "--agent", "codex"]), 0)
            agents = Path(tmp) / "AGENTS.md"
            self.assertIn("## MemoryCustodian", agents.read_text(encoding="utf-8"))
            self.assertIn("manifest.md", agents.read_text(encoding="utf-8"))
            self.assertIn("After meaningful decisions", agents.read_text(encoding="utf-8"))

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
