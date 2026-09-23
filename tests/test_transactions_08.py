from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
import uuid
from unittest import mock

from memory_custodian.locking import ensure_private_directory, write_private_file
from memory_custodian.mutations import PrivateDeleteMutation, PrivateTextMutation, TextMutation
from memory_custodian.transactions import (
    RootBinding,
    RecoveryRequiredError,
    TransactionFailpoint,
    analyze_transaction,
    apply_transaction,
    binding_directory,
    recover_transaction,
    transaction_inventory,
    unfinished_transaction_directories,
)
from memory_custodian import transactions as transaction_module


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
            with mock.patch.dict(os.environ, {"XDG_STATE_HOME": str(state)}):
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
                if expected_phase == "committed":
                    self.assertFalse(record.safe_rollback)
                    with self.assertRaises(RecoveryRequiredError):
                        recover_transaction(directory, roots, action="rollback")
                with mock.patch.dict(os.environ, {"XDG_STATE_HOME": str(state), "MEMORY_CUSTODIAN_FAILPOINT": ""}):
                    recover_transaction(directory, roots, action="complete")
                self.assertEqual(first.read_bytes(), b"new-one\n")
                self.assertEqual(second.read_bytes(), b"new-two\n")
                self.assertFalse(directory.exists())

    def test_bootstrap_recovery_blocks_project_id_write_until_complete(self):
        temporary, state, project, memory = self._fixture()
        self.addCleanup(temporary.cleanup)
        project_id = str(uuid.uuid4())
        manifest = memory / "manifest.md"
        brief = memory / "brief.md"
        later = memory / "inbox.md"
        manifest_text = (
            "# Memory Manifest\n\n"
            "## MemoryCustodian Protocol\n"
            f"- project_id: {project_id}\n"
        )
        with mock.patch.dict(os.environ, {
            "XDG_STATE_HOME": str(state),
            "MEMORY_CUSTODIAN_FAILPOINT": "before-committed",
        }):
            with self.assertRaises(TransactionFailpoint):
                apply_transaction(
                    project_root=project,
                    memory_root=memory,
                    project_id=None,
                    command="init",
                    plan_id="bootstrap-authority-plan",
                    shared_mutations=(
                        TextMutation(brief, "brief"),
                        TextMutation(manifest, manifest_text),
                    ),
                    force_journal=True,
                )
            bootstrap = binding_directory(project, memory, None)
            directories = unfinished_transaction_directories(bootstrap)
            self.assertEqual(len(directories), 1)
            project_binding = bootstrap.parents[1] / "project-id" / project_id
            self.assertFalse(project_binding.exists())

            with mock.patch.dict(
                os.environ, {"MEMORY_CUSTODIAN_FAILPOINT": ""}, clear=False
            ):
                with self.assertRaises(RecoveryRequiredError):
                    apply_transaction(
                        project_root=project,
                        memory_root=memory,
                        project_id=project_id,
                        command="add",
                        plan_id="ordinary-project-write",
                        shared_mutations=(TextMutation(later, "blocked"),),
                    )
                self.assertFalse(later.exists())
                self.assertFalse(project_binding.exists())

                roots = {"shared": RootBinding("shared", project, "shared")}
                record = analyze_transaction(directories[0], roots)
                self.assertEqual(record.phase, "failed")
                self.assertTrue(record.safe_complete)
                recover_transaction(directories[0], roots, action="complete")

                completed = apply_transaction(
                    project_root=project,
                    memory_root=memory,
                    project_id=project_id,
                    command="add",
                    plan_id="ordinary-project-write",
                    shared_mutations=(TextMutation(later, "allowed"),),
                )
            self.assertEqual(completed, (later,))
            self.assertEqual(later.read_text(encoding="utf-8"), "allowed\n")
            self.assertFalse(project_binding.exists())

    def test_bootstrap_recovery_state_does_not_block_another_project(self):
        temporary, state, project, memory = self._fixture()
        self.addCleanup(temporary.cleanup)
        first, second = memory / "first.md", memory / "second.md"
        with mock.patch.dict(os.environ, {
            "XDG_STATE_HOME": str(state),
            "MEMORY_CUSTODIAN_FAILPOINT": "after-first-replace",
        }):
            with self.assertRaises(TransactionFailpoint):
                apply_transaction(
                    project_root=project,
                    memory_root=memory,
                    project_id=None,
                    command="init",
                    plan_id="first-project-plan",
                    shared_mutations=(
                        TextMutation(first, "first"),
                        TextMutation(second, "second"),
                    ),
                )

            other_project = Path(temporary.name) / "other-project"
            other_memory = other_project / "docs" / "memory"
            other_memory.mkdir(parents=True)
            other_target = other_memory / "inbox.md"
            with mock.patch.dict(
                os.environ, {"MEMORY_CUSTODIAN_FAILPOINT": ""}, clear=False
            ):
                completed = apply_transaction(
                    project_root=other_project,
                    memory_root=other_memory,
                    project_id=str(uuid.uuid4()),
                    command="add",
                    plan_id="other-project-plan",
                    shared_mutations=(TextMutation(other_target, "allowed"),),
                )
        self.assertEqual(completed, (other_target,))
        self.assertEqual(other_target.read_text(encoding="utf-8"), "allowed\n")

    def test_bootstrap_writer_checks_planned_project_identity_binding(self):
        temporary, state, project, memory = self._fixture()
        self.addCleanup(temporary.cleanup)
        project_id = str(uuid.uuid4())
        first, second = memory / "first.md", memory / "second.md"
        manifest = memory / "manifest.md"
        with mock.patch.dict(os.environ, {
            "XDG_STATE_HOME": str(state),
            "MEMORY_CUSTODIAN_FAILPOINT": "after-first-replace",
        }):
            with self.assertRaises(TransactionFailpoint):
                apply_transaction(
                    project_root=project,
                    memory_root=memory,
                    project_id=project_id,
                    command="existing-project-write",
                    plan_id="project-id-plan",
                    shared_mutations=(
                        TextMutation(first, "first"),
                        TextMutation(second, "second"),
                    ),
                )

            target_manifest = (
                "# Memory Manifest\n\n"
                "## MemoryCustodian Protocol\n"
                f"- project_id: {project_id}\n"
            )
            with mock.patch.dict(
                os.environ, {"MEMORY_CUSTODIAN_FAILPOINT": ""}, clear=False
            ):
                with self.assertRaises(RecoveryRequiredError):
                    apply_transaction(
                        project_root=project,
                        memory_root=memory,
                        project_id=None,
                        command="init repair",
                        plan_id="bootstrap-plan",
                        shared_mutations=(
                            TextMutation(manifest, target_manifest),
                            TextMutation(memory / "brief.md", "brief"),
                        ),
                        force_journal=True,
                    )
        self.assertFalse(manifest.exists())

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

    @unittest.skipIf(os.name == "nt", "directory identity and rename semantics")
    def test_external_replacement_of_created_directory_blocks_rollback(self):
        temporary, state, project, memory = self._fixture()
        self.addCleanup(temporary.cleanup)
        local_root = ensure_private_directory(state / "local-root")
        local = local_root / "local" / "nested"
        first = local / "first.txt"
        second = local / "second.txt"
        with mock.patch.dict(os.environ, {
            "XDG_STATE_HOME": str(state),
            "MEMORY_CUSTODIAN_FAILPOINT": "after-first-replace",
        }):
            with self.assertRaises(TransactionFailpoint):
                apply_transaction(
                    project_root=project, memory_root=memory, project_id=None,
                    command="local-enable", plan_id="identity-plan",
                    private_mutations=(
                        PrivateTextMutation(first, "local/first.txt", "new-first"),
                        PrivateTextMutation(second, "local/second.txt", "new-second"),
                    ),
                    local_root=local_root, force_journal=True,
                )
            with mock.patch.dict(os.environ, {"XDG_STATE_HOME": str(state)}):
                directory = unfinished_transaction_directories(binding_directory(project, memory, None))[0]
            moved = local_root / "moved"
            moved.mkdir()
            first.rename(moved / first.name)
            local.rmdir()
            local.parent.rmdir()
            local.parent.mkdir(mode=0o700)
            local.mkdir(mode=0o700)
            (moved / first.name).rename(first)
            roots = {
                "shared": RootBinding("shared", project, "shared"),
                "local-overlay": RootBinding("local-overlay", local_root, "local"),
            }
            record = analyze_transaction(directory, roots)
            self.assertFalse(record.safe_rollback)
            with self.assertRaises(RecoveryRequiredError):
                recover_transaction(directory, roots, action="rollback")

    @unittest.skipIf(os.name == "nt", "POSIX symlink semantics")
    def test_delete_revalidates_ancestor_containment(self):
        temporary, state, project, memory = self._fixture()
        self.addCleanup(temporary.cleanup)
        target = memory / "target.md"
        target.write_text("old\n", encoding="utf-8")
        outside = Path(temporary.name) / "outside"
        outside.mkdir()
        (outside / "target.md").write_text("outside\n", encoding="utf-8")
        roots = {"shared": RootBinding("shared", project, "shared")}
        # The preflight validator rejects symlinked ancestors before a
        # transaction is even created; the same guard is used immediately
        # before every journaled and recovery unlink.
        link = project / "linked"
        link.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            apply_transaction(
                project_root=project, memory_root=memory, project_id=None,
                command="delete", plan_id="symlink-plan",
                shared_mutations=(TextMutation(link / "target.md", "new"),),
            )
        self.assertEqual((outside / "target.md").read_text(encoding="utf-8"), "outside\n")

    def test_transaction_inventory_classifies_private_states(self):
        temporary, state, project, memory = self._fixture()
        self.addCleanup(temporary.cleanup)
        with mock.patch.dict(os.environ, {"XDG_STATE_HOME": str(state)}):
            binding = binding_directory(project, memory, None)
            orphan = ensure_private_directory(binding / ("a" * 32))
            write_private_file(orphan / "artifact", "opaque")
            malformed = ensure_private_directory(binding / ("b" * 32))
            write_private_file(malformed / "journal.json", "not-json\n")
            unsupported = ensure_private_directory(binding / ("c" * 32))
            write_private_file(unsupported / "journal.json", json.dumps({
                "transaction_schema_version": 999,
                "transaction_id": unsupported.name,
                "targets": [],
            }) + "\n")
            if os.name != "nt":
                outside = Path(temporary.name) / "outside-state"
                outside.mkdir()
                symlink = binding / ("d" * 32)
                symlink.symlink_to(outside, target_is_directory=True)
            kinds = {item.kind for item in transaction_inventory(binding)}
        self.assertTrue({"orphan", "malformed", "unsupported"}.issubset(kinds))
        if os.name != "nt":
            self.assertIn("symlink", kinds)

    def test_subprocess_failpoint_leaves_detectable_recovery_state(self):
        temporary, state, project, memory = self._fixture()
        self.addCleanup(temporary.cleanup)
        first, second = memory / "first.md", memory / "second.md"
        first.write_text("old-first\n", encoding="utf-8")
        second.write_text("old-second\n", encoding="utf-8")
        source_root = Path(__file__).resolve().parents[1]
        script = (
            "import sys; from pathlib import Path; "
            "sys.path.insert(0, sys.argv[1]); "
            "from memory_custodian.mutations import TextMutation; "
            "from memory_custodian.transactions import apply_transaction; "
            "root=Path(sys.argv[2]); memory=Path(sys.argv[3]); "
            "apply_transaction(project_root=root, memory_root=memory, project_id=None, "
            "command='subprocess-fixture', plan_id='subprocess-plan', "
            "shared_mutations=(TextMutation(memory/'first.md','new-first'), "
            "TextMutation(memory/'second.md','new-second')))"
        )
        env = dict(os.environ, XDG_STATE_HOME=str(state), MEMORY_CUSTODIAN_FAILPOINT="after-first-replace")
        completed = subprocess.run(
            [sys.executable, "-c", script, str(source_root / "cli"), str(project), str(memory)],
            env=env, capture_output=True, text=True,
        )
        self.assertNotEqual(completed.returncode, 0)
        with mock.patch.dict(os.environ, {"XDG_STATE_HOME": str(state)}):
            binding = binding_directory(project, memory, None)
            directories = unfinished_transaction_directories(binding)
        self.assertEqual(len(directories), 1)
        roots = {"shared": RootBinding("shared", project, "shared")}
        self.assertTrue(analyze_transaction(directories[0], roots).safe_rollback)
        with mock.patch.dict(os.environ, {"XDG_STATE_HOME": str(state), "MEMORY_CUSTODIAN_FAILPOINT": ""}):
            recover_transaction(directories[0], roots, action="rollback")
        self.assertEqual(first.read_text(encoding="utf-8"), "old-first\n")
        self.assertEqual(second.read_text(encoding="utf-8"), "old-second\n")

    def test_subprocess_all_apply_failpoints_are_recoverable(self):
        failpoints = (
            "after-planned-before-first-artifact",
            "after-first-backup",
            "after-journal-prepared",
            "after-first-replace",
            "after-each-replace",
            "before-committed",
            "after-committed-before-cleanup",
        )
        source_root = Path(__file__).resolve().parents[1]
        script = (
            "import sys; from pathlib import Path; "
            "sys.path.insert(0, sys.argv[1]); "
            "from memory_custodian.mutations import TextMutation; "
            "from memory_custodian.transactions import apply_transaction; "
            "root=Path(sys.argv[2]); memory=Path(sys.argv[3]); "
            "apply_transaction(project_root=root, memory_root=memory, project_id=None, "
            "command='subprocess-fixture', plan_id='subprocess-plan', "
            "shared_mutations=(TextMutation(memory/'first.md','new-first'), "
            "TextMutation(memory/'second.md','new-second')))"
        )
        for failpoint in failpoints:
            with self.subTest(failpoint=failpoint):
                temporary, state, project, memory = self._fixture()
                self.addCleanup(temporary.cleanup)
                first, second = memory / "first.md", memory / "second.md"
                first.write_text("old-first\n", encoding="utf-8")
                second.write_text("old-second\n", encoding="utf-8")
                env = dict(os.environ, XDG_STATE_HOME=str(state), MEMORY_CUSTODIAN_FAILPOINT=failpoint)
                completed = subprocess.run(
                    [sys.executable, "-c", script, str(source_root / "cli"), str(project), str(memory)],
                    env=env, capture_output=True, text=True,
                )
                self.assertNotEqual(completed.returncode, 0)
                with mock.patch.dict(os.environ, {"XDG_STATE_HOME": str(state)}):
                    binding = binding_directory(project, memory, None)
                    directories = unfinished_transaction_directories(binding)
                self.assertEqual(len(directories), 1)
                roots = {"shared": RootBinding("shared", project, "shared")}
                record = analyze_transaction(directories[0], roots)
                self.assertTrue(record.safe_complete or record.safe_rollback)
                action = "complete" if failpoint == "after-committed-before-cleanup" else "rollback"
                with mock.patch.dict(os.environ, {"XDG_STATE_HOME": str(state), "MEMORY_CUSTODIAN_FAILPOINT": ""}):
                    recover_transaction(directories[0], roots, action=action)
                if action == "rollback":
                    self.assertEqual(first.read_text(encoding="utf-8"), "old-first\n")
                    self.assertEqual(second.read_text(encoding="utf-8"), "old-second\n")
                else:
                    self.assertEqual(first.read_text(encoding="utf-8"), "new-first\n")
                    self.assertEqual(second.read_text(encoding="utf-8"), "new-second\n")

    def test_mixed_shared_local_transaction_restores_modes(self):
        temporary, state, project, memory = self._fixture()
        self.addCleanup(temporary.cleanup)
        shared = memory / "shared.md"
        shared.write_bytes(b"shared\r\n")
        local_root = ensure_private_directory(state / "local-root")
        local = local_root / "overlay" / "local.txt"
        local.parent.mkdir()
        local.write_bytes(b"local\r\n")
        local.chmod(0o600)
        with mock.patch.dict(os.environ, {
            "XDG_STATE_HOME": str(state),
            "MEMORY_CUSTODIAN_FAILPOINT": "after-first-replace",
        }):
            with self.assertRaises(TransactionFailpoint):
                apply_transaction(
                    project_root=project, memory_root=memory, project_id=None,
                    command="mixed-root", plan_id="mixed-plan",
                    shared_mutations=(TextMutation(shared, "new-shared"),),
                    private_mutations=(PrivateTextMutation(local, "overlay/local.txt", "new-local"),),
                    local_root=local_root, force_journal=True,
                )
            directory = unfinished_transaction_directories(binding_directory(project, memory, None))[0]
            roots = {
                "shared": RootBinding("shared", project, "shared"),
                "local-overlay": RootBinding("local-overlay", local_root, "local"),
            }
            with mock.patch.dict(os.environ, {"XDG_STATE_HOME": str(state), "MEMORY_CUSTODIAN_FAILPOINT": ""}):
                recover_transaction(directory, roots, action="rollback")
        self.assertEqual(shared.read_bytes(), b"shared\r\n")
        self.assertEqual(local.read_bytes(), b"local\r\n")
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(local.stat().st_mode), 0o600)

    def test_recovery_failpoint_leaves_recovering_phase_for_retry(self):
        temporary, state, project, memory = self._fixture()
        self.addCleanup(temporary.cleanup)
        first, second = memory / "first.md", memory / "second.md"
        first.write_text("old-first\n", encoding="utf-8")
        second.write_text("old-second\n", encoding="utf-8")
        with mock.patch.dict(os.environ, {
            "XDG_STATE_HOME": str(state),
            "MEMORY_CUSTODIAN_FAILPOINT": "after-first-replace",
        }):
            with self.assertRaises(TransactionFailpoint):
                apply_transaction(
                    project_root=project, memory_root=memory, project_id=None,
                    command="recover-fixture", plan_id="recover-plan",
                    shared_mutations=(TextMutation(first, "new-first"), TextMutation(second, "new-second")),
                )
            directory = unfinished_transaction_directories(binding_directory(project, memory, None))[0]
            roots = {"shared": RootBinding("shared", project, "shared")}
            with mock.patch.dict(os.environ, {"MEMORY_CUSTODIAN_FAILPOINT": "while-recovering"}, clear=False):
                with self.assertRaises(TransactionFailpoint):
                    recover_transaction(directory, roots, action="rollback")
            journal = json.loads((directory / "journal.json").read_text(encoding="utf-8"))
            self.assertEqual(journal["phase"], "recovering")
            with mock.patch.dict(os.environ, {"MEMORY_CUSTODIAN_FAILPOINT": ""}, clear=False):
                recover_transaction(directory, roots, action="rollback")
        self.assertEqual(first.read_text(encoding="utf-8"), "old-first\n")
        self.assertEqual(second.read_text(encoding="utf-8"), "old-second\n")

    def test_journal_write_failure_preserves_previous_atomic_record(self):
        temporary, state, project, memory = self._fixture()
        self.addCleanup(temporary.cleanup)
        with mock.patch.dict(os.environ, {"XDG_STATE_HOME": str(state)}):
            binding = binding_directory(project, memory, None)
            journal_path = ensure_private_directory(binding / ("e" * 32)) / "journal.json"
            write_private_file(journal_path, json.dumps({"phase": "planned"}) + "\n")
            with mock.patch.object(transaction_module, "write_private_file", side_effect=OSError("simulated crash")):
                with self.assertRaises(OSError):
                    transaction_module._atomic_journal(journal_path, {"phase": "prepared"})
            self.assertEqual(json.loads(journal_path.read_text(encoding="utf-8"))["phase"], "planned")

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
