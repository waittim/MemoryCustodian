from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock

from memory_custodian.locking import ensure_private_directory, write_private_file
from memory_custodian.mutations import PrivateDeleteMutation, PrivateTextMutation, TextMutation
from memory_custodian.transactions import (
    RootBinding,
    TransactionFailpoint,
    analyze_transaction,
    apply_transaction,
    binding_directory,
    recover_transaction,
    unfinished_transaction_directories,
)


class TransactionProtocol08Tests(unittest.TestCase):
    def _fixture(self):
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        project = root / "project"
        memory = project / "docs" / "memory"
        memory.mkdir(parents=True)
        return temporary, root / "state", project, memory

    def _interrupted(self, state, project, memory, mutations, failpoint, **kwargs):
        with mock.patch.dict(os.environ, {
            "XDG_STATE_HOME": str(state),
            "MEMORY_CUSTODIAN_FAILPOINT": failpoint,
        }):
            with self.assertRaises(TransactionFailpoint):
                apply_transaction(
                    project_root=project,
                    memory_root=memory,
                    project_id=None,
                    command="fixture",
                    plan_id="fixture-plan",
                    shared_mutations=mutations,
                    **kwargs,
                )
            binding = binding_directory(project, memory, None)
            directories = unfinished_transaction_directories(binding)
            self.assertEqual(len(directories), 1)
            return directories[0]

    def test_complete_after_first_replace_and_committed_cleanup_are_safe(self):
        for failpoint, expected_phase in (
            ("after-first-replace", "failed"),
            ("after-committed-before-cleanup", "committed"),
        ):
            with self.subTest(failpoint=failpoint):
                temporary, state, project, memory = self._fixture()
                self.addCleanup(temporary.cleanup)
                first, second = memory / "first.md", memory / "second.md"
                first.write_bytes(b"old-one\r\n")
                second.write_bytes(b"old-two")
                directory = self._interrupted(
                    state, project, memory,
                    (TextMutation(first, "new-one"), TextMutation(second, "new-two")),
                    failpoint,
                )
                roots = {"shared": RootBinding("shared", project, "shared")}
                record = analyze_transaction(directory, roots)
                self.assertEqual(record.phase, expected_phase)
                self.assertTrue(record.safe_complete)
                with mock.patch.dict(os.environ, {"XDG_STATE_HOME": str(state), "MEMORY_CUSTODIAN_FAILPOINT": ""}):
                    recover_transaction(directory, roots, action="complete")
                self.assertEqual(first.read_bytes(), b"new-one\n")
                self.assertEqual(second.read_bytes(), b"new-two\n")
                self.assertFalse(directory.exists())

    def test_delete_rollback_restores_exact_bytes_and_mode(self):
        temporary, state, project, memory = self._fixture()
        self.addCleanup(temporary.cleanup)
        local_root = ensure_private_directory(state / "local-root")
        first = local_root / "first.txt"
        second = local_root / "second.txt"
        first.write_bytes(b"first\r\nwithout-terminal-newline")
        second.write_bytes(b"second")
        first.chmod(0o600)
        second.chmod(0o600)
        with mock.patch.dict(os.environ, {
            "XDG_STATE_HOME": str(state),
            "MEMORY_CUSTODIAN_FAILPOINT": "after-first-replace",
        }):
            with self.assertRaises(TransactionFailpoint):
                apply_transaction(
                    project_root=project, memory_root=memory, project_id=None,
                    command="local-reset", plan_id="delete-plan",
                    private_deletions=(
                        PrivateDeleteMutation(first, "first.txt"),
                        PrivateDeleteMutation(second, "second.txt"),
                    ),
                    local_root=local_root, force_journal=True,
                )
            directory = unfinished_transaction_directories(binding_directory(project, memory, None))[0]
            roots = {
                "shared": RootBinding("shared", project, "shared"),
                "local-overlay": RootBinding("local-overlay", local_root, "local"),
            }
            self.assertTrue(analyze_transaction(directory, roots).safe_rollback)
            with mock.patch.dict(os.environ, {"MEMORY_CUSTODIAN_FAILPOINT": ""}, clear=False):
                recover_transaction(directory, roots, action="rollback")
        self.assertEqual(first.read_bytes(), b"first\r\nwithout-terminal-newline")
        self.assertEqual(second.read_bytes(), b"second")
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(first.stat().st_mode), 0o600)

    def test_external_edit_and_missing_prepared_output_block_unsafe_recovery(self):
        temporary, state, project, memory = self._fixture()
        self.addCleanup(temporary.cleanup)
        first, second = memory / "first.md", memory / "second.md"
        first.write_text("old", encoding="utf-8")
        second.write_text("old", encoding="utf-8")
        directory = self._interrupted(
            state, project, memory,
            (TextMutation(first, "new"), TextMutation(second, "new")),
            "after-journal-prepared",
        )
        roots = {"shared": RootBinding("shared", project, "shared")}
        journal = json.loads((directory / "journal.json").read_text(encoding="utf-8"))
        (directory / journal["targets"][1]["prepared_path"]).unlink()
        record = analyze_transaction(directory, roots)
        self.assertFalse(record.safe_complete)
        first.write_text("external", encoding="utf-8")
        record = analyze_transaction(directory, roots)
        self.assertFalse(record.safe_complete)
        self.assertFalse(record.safe_rollback)

    def test_created_private_directories_are_removed_on_rollback(self):
        temporary, state, project, memory = self._fixture()
        self.addCleanup(temporary.cleanup)
        local_root = ensure_private_directory(state / "local-root")
        local = local_root / "local"
        with mock.patch.dict(os.environ, {
            "XDG_STATE_HOME": str(state),
            "MEMORY_CUSTODIAN_FAILPOINT": "after-first-replace",
        }):
            with self.assertRaises(TransactionFailpoint):
                apply_transaction(
                    project_root=project, memory_root=memory, project_id=None,
                    command="local-enable", plan_id="directory-plan",
                    private_mutations=(
                        PrivateTextMutation(local / "manifest.md", "local/manifest.md", "manifest"),
                        PrivateTextMutation(local / "preferences.md", "local/preferences.md", "preferences"),
                    ),
                    private_directories=(local / "profiles",),
                    local_root=local_root, force_journal=True,
                )
            directory = unfinished_transaction_directories(binding_directory(project, memory, None))[0]
            roots = {
                "shared": RootBinding("shared", project, "shared"),
                "local-overlay": RootBinding("local-overlay", local_root, "local"),
            }
            with mock.patch.dict(os.environ, {"MEMORY_CUSTODIAN_FAILPOINT": ""}, clear=False):
                recover_transaction(directory, roots, action="rollback")
        self.assertFalse(local.exists())

    def test_orphan_and_newer_journal_are_detected_as_invalid(self):
        temporary, state, project, memory = self._fixture()
        self.addCleanup(temporary.cleanup)
        with mock.patch.dict(os.environ, {"XDG_STATE_HOME": str(state)}):
            binding = binding_directory(project, memory, None)
            orphan = ensure_private_directory(binding / ("a" * 32))
            write_private_file(orphan / "artifact", "opaque")
            roots = {"shared": RootBinding("shared", project, "shared")}
            self.assertEqual(analyze_transaction(orphan, roots).phase, "invalid")
            orphan.joinpath("artifact").unlink()
            write_private_file(orphan / "journal.json", json.dumps({
                "transaction_schema_version": 999,
                "transaction_id": orphan.name,
                "targets": [],
            }) + "\n")
            record = analyze_transaction(orphan, roots)
            self.assertEqual(record.phase, "invalid")
            self.assertFalse(record.safe_complete)


if __name__ == "__main__":
    unittest.main()
