from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

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
            self.assertIn("- protocol_version: 0.5", manifest)
            self.assertIn("- initialized_with: memory-custodian 0.9.1", manifest)
            decisions = (memory / "decisions.md").read_text(encoding="utf-8")
            constraints = (memory / "constraints.md").read_text(encoding="utf-8")
            self.assertIn("Entries are newest first.", decisions)
            self.assertNotIn("Use MemoryCustodian", decisions)
            self.assertNotIn("RAG", constraints)
            self.assertIn("Tombstones are newest first.", (memory / "do-not-use.md").read_text(encoding="utf-8"))
            self.assertIn("Entries are newest first.", (memory / "inbox.md").read_text(encoding="utf-8"))
            self.assertIn("TODO: Describe what this project does", (memory / "brief.md").read_text(encoding="utf-8"))

            brief = memory / "brief.md"
            brief.write_text("# Custom Brief\n", encoding="utf-8")
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            self.assertEqual(brief.read_text(encoding="utf-8"), "# Custom Brief\n")

    def test_init_accepts_custom_memory_dir_under_docs(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp, "--memory-dir", "docs/team-memory", "--agent", "codex"]), 0)
            memory = Path(tmp) / "docs" / "team-memory"
            self.assertTrue((memory / "manifest.md").exists())
            self.assertIn("docs/team-memory", (Path(tmp) / "AGENTS.md").read_text(encoding="utf-8"))
            self.assertIn("docs/team-memory/manifest.md", (Path(tmp) / "AGENTS.md").read_text(encoding="utf-8"))

    def test_init_rejects_memory_dir_outside_docs(self):
        with tempfile.TemporaryDirectory() as tmp:
            err = StringIO()
            with redirect_stderr(err):
                code = main(["init", "--project-root", tmp, "--memory-dir", ".memory"])
            self.assertEqual(code, 2)
            self.assertIn("Error: Memory directory must live under docs/", err.getvalue())
            self.assertFalse((Path(tmp) / ".memory").exists())

    def test_init_force_is_rejected_without_overwriting_curated_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            brief = Path(tmp) / "docs" / "memory" / "brief.md"
            brief.write_text("# Curated Brief\n\nKeep this project knowledge.\n", encoding="utf-8")

            err = StringIO()
            with redirect_stderr(err):
                code = main(["init", "--project-root", tmp, "--force"])

            self.assertEqual(code, 2)
            self.assertIn("init --force was removed", err.getvalue())
            self.assertEqual(brief.read_text(encoding="utf-8"), "# Curated Brief\n\nKeep this project knowledge.\n")

    def test_init_repair_preserves_curated_files_and_repairs_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            memory = Path(tmp) / "docs" / "memory"
            brief = memory / "brief.md"
            brief.write_text("# Curated Brief\n\nDo not replace this.\n", encoding="utf-8")
            manifest = memory / "manifest.md"
            damaged = manifest.read_text(encoding="utf-8").replace(
                "- protocol_version: 0.5", "- protocol_version: 0.4"
            )
            manifest.write_text(damaged, encoding="utf-8")
            (memory / "constraints.md").unlink()

            self.assertEqual(main(["init", "--project-root", tmp, "--repair"]), 0)

            self.assertEqual(brief.read_text(encoding="utf-8"), "# Curated Brief\n\nDo not replace this.\n")
            self.assertIn("- protocol_version: 0.5", manifest.read_text(encoding="utf-8"))
            self.assertTrue((memory / "constraints.md").exists())

    def test_init_repair_preserves_unknown_protocol_metadata_and_comments(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            manifest = Path(tmp) / "docs" / "memory" / "manifest.md"
            damaged = manifest.read_text(encoding="utf-8").replace(
                "- protocol_version: 0.5",
                "- protocol_version: 0.4\n"
                "- custom_owner: team-memory\n"
                "<!-- Preserve this project-specific protocol note. -->",
            )
            manifest.write_text(damaged, encoding="utf-8")

            self.assertEqual(main(["init", "--project-root", tmp, "--repair"]), 0)

            repaired = manifest.read_text(encoding="utf-8")
            self.assertIn("- protocol_version: 0.5", repaired)
            self.assertIn("- custom_owner: team-memory", repaired)
            self.assertIn("<!-- Preserve this project-specific protocol note. -->", repaired)

    def test_init_repair_rejects_newer_project_protocol_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            memory = Path(tmp) / "docs" / "memory"
            manifest = memory / "manifest.md"
            newer = manifest.read_text(encoding="utf-8").replace(
                "- protocol_version: 0.5", "- protocol_version: 0.6"
            )
            manifest.write_text(newer, encoding="utf-8")
            (memory / "constraints.md").unlink()

            err = StringIO()
            with redirect_stderr(err):
                code = main(["init", "--project-root", tmp, "--repair"])

            self.assertEqual(code, 2)
            self.assertIn("newer than this CLI supports", err.getvalue())
            self.assertEqual(manifest.read_text(encoding="utf-8"), newer)
            self.assertFalse((memory / "constraints.md").exists())

    def test_init_repair_rejects_invalid_project_protocol_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            memory = Path(tmp) / "docs" / "memory"
            manifest = memory / "manifest.md"
            invalid = manifest.read_text(encoding="utf-8").replace(
                "- protocol_version: 0.5", "- protocol_version: not-a-version"
            )
            manifest.write_text(invalid, encoding="utf-8")
            (memory / "constraints.md").unlink()

            err = StringIO()
            with redirect_stderr(err):
                code = main(["init", "--project-root", tmp, "--repair"])

            self.assertEqual(code, 2)
            self.assertIn("invalid protocol version", err.getvalue().lower())
            self.assertEqual(manifest.read_text(encoding="utf-8"), invalid)
            self.assertFalse((memory / "constraints.md").exists())

    def test_init_repair_adds_missing_protocol_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            manifest = Path(tmp) / "docs" / "memory" / "manifest.md"
            without_version = manifest.read_text(encoding="utf-8").replace(
                "- protocol_version: 0.5\n", ""
            )
            manifest.write_text(without_version, encoding="utf-8")

            self.assertEqual(main(["init", "--project-root", tmp, "--repair"]), 0)

            self.assertIn("- protocol_version: 0.5", manifest.read_text(encoding="utf-8"))

    def test_init_repair_keeps_same_protocol_manifest_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            manifest = Path(tmp) / "docs" / "memory" / "manifest.md"
            original = manifest.read_text(encoding="utf-8")

            self.assertEqual(main(["init", "--project-root", tmp, "--repair"]), 0)

            self.assertEqual(manifest.read_text(encoding="utf-8"), original)

    def test_init_replace_existing_previews_then_requires_apply(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            brief = Path(tmp) / "docs" / "memory" / "brief.md"
            curated = "# Curated Brief\n\nImportant project context.\n"
            brief.write_text(curated, encoding="utf-8")

            out = StringIO()
            with redirect_stdout(out):
                self.assertEqual(main(["init", "--project-root", tmp, "--replace-existing"]), 0)
            preview = out.getvalue()
            self.assertIn("MemoryCustodian replacement plan", preview)
            self.assertIn("brief.md: replace planned", preview)
            self.assertIn("contain non-template content", preview)
            self.assertIn("Dry run only", preview)
            self.assertEqual(brief.read_text(encoding="utf-8"), curated)

            self.assertEqual(
                main(["init", "--project-root", tmp, "--replace-existing", "--apply"]),
                0,
            )
            self.assertIn("TODO: Describe what this project does", brief.read_text(encoding="utf-8"))

    def test_init_can_add_codex_snippet(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp, "--agent", "codex"]), 0)
            agents = Path(tmp) / "AGENTS.md"
            self.assertIn("## MemoryCustodian", agents.read_text(encoding="utf-8"))
            self.assertIn("manifest.md", agents.read_text(encoding="utf-8"))
            self.assertIn("After meaningful decisions", agents.read_text(encoding="utf-8"))

    def test_init_can_add_gemini_snippet(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp, "--with-gemini"]), 0)
            gemini = Path(tmp) / "GEMINI.md"
            text = gemini.read_text(encoding="utf-8")
            self.assertIn("## MemoryCustodian", text)
            self.assertIn("docs/memory/manifest.md", text)
            self.assertIn("After meaningful decisions", text)

    def test_init_agent_all_adds_all_entry_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp, "--agent", "all"]), 0)
            for name in ("AGENTS.md", "CLAUDE.md", "GEMINI.md"):
                text = (Path(tmp) / name).read_text(encoding="utf-8")
                self.assertIn("## MemoryCustodian", text, name)
                self.assertIn("docs/memory/brief.md", text, name)

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

    def test_enable_force_is_rejected_without_overwriting_existing_module(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            self.assertEqual(main(["enable", "preferences", "--project-root", tmp]), 0)
            preferences = Path(tmp) / "docs" / "memory" / "preferences.md"
            curated = "# Preferences\n\n- Preserve this curated preference.\n"
            preferences.write_text(curated, encoding="utf-8")

            err = StringIO()
            with redirect_stderr(err):
                code = main(["enable", "preferences", "--project-root", tmp, "--force"])

            self.assertEqual(code, 2)
            self.assertIn("enable --force was removed", err.getvalue())
            self.assertEqual(preferences.read_text(encoding="utf-8"), curated)

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

    def test_enable_already_enabled_is_a_zero_write_no_op(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            self.assertEqual(main(["enable", "changelog", "--project-root", tmp]), 0)
            self.assertEqual(main(["enable", "preferences", "--project-root", tmp]), 0)
            memory = Path(tmp) / "docs" / "memory"
            tracked = (memory / "preferences.md", memory / "manifest.md", memory / "changelog.md")
            before = {path: path.read_bytes() for path in tracked}

            out = StringIO()
            with patch("memory_custodian.enable.apply_mutations") as apply, redirect_stdout(out):
                self.assertEqual(main(["enable", "preferences", "--project-root", tmp]), 0)

            apply.assert_not_called()
            self.assertIn("preferences.md: already enabled", out.getvalue())
            self.assertEqual({path: path.read_bytes() for path in tracked}, before)


if __name__ == "__main__":
    unittest.main()
