from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock
import tempfile
import unittest
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli"))

from memory_custodian.main import main
from memory_custodian.protocol import pack_to_budget, write_text


class AtomicWriteTests(unittest.TestCase):
    def test_atomic_writer_creates_replaces_and_normalizes_newline(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested" / "memory.md"
            write_text(path, "first")
            self.assertEqual(path.read_text(encoding="utf-8"), "first\n")
            write_text(path, "second\n")
            self.assertEqual(path.read_text(encoding="utf-8"), "second\n")

    def test_replace_failure_preserves_original_and_cleans_temporary(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "memory.md"
            path.write_text("original\n", encoding="utf-8")
            with mock.patch("memory_custodian.protocol.os.replace", side_effect=OSError("replace failed")):
                with self.assertRaises(OSError):
                    write_text(path, "updated")
            self.assertEqual(path.read_text(encoding="utf-8"), "original\n")
            self.assertEqual(list(Path(tmp).glob(".memory.md.*.tmp")), [])


class ForgetReliabilityTests(unittest.TestCase):
    def _init(self, tmp: str) -> Path:
        self.assertEqual(main(["init", "--project-root", tmp]), 0)
        return Path(tmp) / "docs" / "memory"

    def test_dry_run_and_complete_h2_removal(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory = self._init(tmp)
            decisions = memory / "decisions.md"
            decisions.write_text(
                "# Decisions\n\nEntries are newest first.\n\n"
                "## Keep entry\nDecision:\nKeep this.\nReason:\nStill needed.\n\n"
                "## Remove entry\nDecision:\nUse SQLite here.\nReason:\nOffline.\n",
                encoding="utf-8",
            )
            before = decisions.read_text(encoding="utf-8")
            out = StringIO()
            with redirect_stdout(out):
                self.assertEqual(main(["forget", "sqlite", "--project-root", tmp]), 0)
            self.assertEqual(decisions.read_text(encoding="utf-8"), before)
            self.assertIn("Matched units: 1", out.getvalue())
            self.assertEqual(main(["forget", "sqlite", "--apply", "--project-root", tmp]), 0)
            after = decisions.read_text(encoding="utf-8")
            self.assertNotIn("Remove entry", after)
            self.assertNotIn("Offline", after)
            self.assertIn("Keep entry", after)

    def test_short_and_multi_unit_apply_require_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory = self._init(tmp)
            constraints = memory / "constraints.md"
            constraints.write_text("# Constraints\n\n- Use Go.\n- Go builds stay offline.\n", encoding="utf-8")
            self.assertEqual(main(["forget", "Go", "--apply", "--project-root", tmp]), 1)
            self.assertIn("Use Go", constraints.read_text(encoding="utf-8"))
            self.assertEqual(
                main(["forget", "Go", "--apply", "--allow-broad-match", "--project-root", tmp]), 0
            )
            self.assertNotIn("Go", constraints.read_text(encoding="utf-8"))

    def test_hard_and_purge_do_not_persist_topic(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory = self._init(tmp)
            self.assertEqual(main(["enable", "changelog", "--project-root", tmp]), 0)
            (memory / "decisions.md").write_text(
                "# Decisions\n\n## Private\nDecision:\nSecretMarker.\nReason:\nPrivate.\n", encoding="utf-8"
            )
            self.assertEqual(main(["forget", "SecretMarker", "--mode", "hard", "--apply", "--project-root", tmp]), 0)
            self.assertNotIn("SecretMarker", (memory / "do-not-use.md").read_text(encoding="utf-8"))
            self.assertNotIn("SecretMarker", (memory / "changelog.md").read_text(encoding="utf-8"))

            archive = memory / "archive"
            archive.mkdir(exist_ok=True)
            (archive / "old.md").write_text("# Old\n\n## Old entry\nRetiredMarker.\n", encoding="utf-8")
            self.assertEqual(main(["forget", "RetiredMarker", "--mode", "purge", "--apply", "--project-root", tmp]), 0)
            self.assertNotIn("RetiredMarker", (archive / "old.md").read_text(encoding="utf-8"))
            self.assertNotIn("RetiredMarker", (memory / "changelog.md").read_text(encoding="utf-8"))


class PackingAndRoutingTests(unittest.TestCase):
    def test_packing_never_cuts_decision_and_reports_omissions(self):
        text = (
            "# Decisions\n\nEntries are newest first.\n\n"
            "## First\nDecision:\nKeep alpha.\nReason:\nBecause alpha.\n\n"
            "## Second\nDecision:\nKeep beta.\nReason:\nBecause beta.\n"
        )
        packed, omitted, oversized = pack_to_budget(text, 22)
        self.assertIn("Decision:\nKeep alpha.\nReason:\nBecause alpha.", packed)
        self.assertNotIn("## Second", packed)
        self.assertEqual(omitted, 1)
        self.assertFalse(oversized)

    def test_oversized_first_unit_is_included_whole(self):
        text = "# Decisions\n\n## Huge\nDecision:\n" + "word " * 40 + "\nReason:\nwhole\n"
        packed, omitted, oversized = pack_to_budget(text, 10)
        self.assertIn("Reason:\nwhole", packed)
        self.assertEqual(omitted, 0)
        self.assertTrue(oversized)

    def test_missing_ambiguous_and_unsafe_manifest_routes_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            memory = Path(tmp) / "docs" / "memory"
            (memory / "manifest.md").unlink()
            out = StringIO()
            with redirect_stdout(out):
                self.assertEqual(main(["read", "--task", "planning", "--project-root", tmp]), 1)
            self.assertIn("manifest.md is missing", out.getvalue())

        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            manifest = Path(tmp) / "docs" / "memory" / "manifest.md"
            text = manifest.read_text(encoding="utf-8")
            text = text.replace("- decisions.md\n- constraints.md", "- ../outside.md\n- constraints.md", 1)
            manifest.write_text(text, encoding="utf-8")
            self.assertEqual(main(["read", "--task", "planning", "--project-root", tmp]), 1)


class BootstrapReliabilityTests(unittest.TestCase):
    def test_managed_block_is_idempotent_and_force_replaces(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--agent", "codex", "--project-root", tmp]), 0)
            agents = Path(tmp) / "AGENTS.md"
            self.assertEqual(agents.read_text(encoding="utf-8").count("<!-- memory-custodian:start -->"), 1)
            self.assertEqual(main(["init", "--agent", "codex", "--project-root", tmp]), 0)
            self.assertEqual(main(["init", "--agent", "codex", "--force-agent", "--project-root", tmp]), 0)
            self.assertEqual(agents.read_text(encoding="utf-8").count("<!-- memory-custodian:start -->"), 1)

    def test_malformed_markers_fail_without_append(self):
        with tempfile.TemporaryDirectory() as tmp:
            agents = Path(tmp) / "AGENTS.md"
            agents.write_text("# Agent\n\n<!-- memory-custodian:start -->\n", encoding="utf-8")
            self.assertEqual(main(["init", "--agent", "codex", "--project-root", tmp]), 1)
            self.assertEqual(agents.read_text(encoding="utf-8").count("<!-- memory-custodian:start -->"), 1)


if __name__ == "__main__":
    unittest.main()
