from __future__ import annotations

import copy
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
from memory_custodian.plans import MutationPlan
from memory_custodian.transactions import (
    RootBinding,
    RecoveryRequiredError,
    TransactionFailpoint,
    analyze_transaction,
    apply_transaction,
    apply_plan_transaction,
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

    def _write_journal(self, directory: Path, journal: dict[str, object]) -> None:
        write_private_file(
            directory / "journal.json",
            json.dumps(journal, ensure_ascii=False, sort_keys=True) + "\n",
        )

    def _prepared_replace_fixture(self):
        temporary, state, project, memory = self._fixture()
        self.addCleanup(temporary.cleanup)
        first = memory / "first.md"
        second = memory / "second.md"
        first.write_bytes(b"old-first\n")
        second.write_bytes(b"old-second\n")
        directory = self._interrupted(
            state,
            project,
            memory,
            (TextMutation(first, "new-first"), TextMutation(second, "new-second")),
            "after-journal-prepared",
        )
        roots = {"shared": RootBinding("shared", project, "shared")}
        journal = json.loads((directory / "journal.json").read_text(encoding="utf-8"))
        return directory, roots, journal, (first, second)

    def _state_snapshot(self, directory: Path) -> dict[str, bytes | None]:
        return {
            path.relative_to(directory).as_posix(): path.read_bytes() if path.is_file() else None
            for path in sorted(directory.rglob("*"))
        }

    def _assert_journal_blocked(
        self,
        directory: Path,
        roots: dict[str, RootBinding],
        watched: tuple[Path, ...],
        *,
        expected_kind: str,
    ) -> None:
        private_before = self._state_snapshot(directory)
        targets_before = {
            path: (path.exists(), path.read_bytes() if path.exists() else None)
            for path in watched
        }
        record = analyze_transaction(directory, roots)
        self.assertEqual(record.phase, "invalid")
        self.assertFalse(record.safe_complete)
        self.assertFalse(record.safe_rollback)
        inventory = {
            item.directory: item for item in transaction_inventory(directory.parent)
        }
        self.assertEqual(inventory[directory].kind, expected_kind)
        for action in ("complete", "rollback"):
            with self.assertRaises(RecoveryRequiredError):
                recover_transaction(directory, roots, action=action)
            self.assertTrue(directory.exists())
            self.assertEqual(self._state_snapshot(directory), private_before)
            self.assertEqual(
                {
                    path: (path.exists(), path.read_bytes() if path.exists() else None)
                    for path in watched
                },
                targets_before,
            )

    def test_windows_basic_mode_matching_uses_read_only_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "writable.md"
            target.write_bytes(b"windows-basic mode check\n")
            target.chmod(0o666)
            digest = transaction_module._sha256(target.read_bytes())
            with mock.patch.object(
                transaction_module, "_platform_mode_semantics", return_value="windows-basic"
            ):
                self.assertTrue(transaction_module._matches(target, True, digest, "0644"))
                self.assertTrue(transaction_module._matches(target, True, digest, "0600"))
                self.assertFalse(transaction_module._matches(target, True, digest, "0444"))

        with mock.patch.object(
            transaction_module, "_platform_mode_semantics", return_value="windows-basic"
        ):
            self.assertTrue(transaction_module._modes_match("0444", "0444"))
            self.assertFalse(transaction_module._modes_match("0444", "0644"))

        with mock.patch.object(
            transaction_module, "_platform_mode_semantics", return_value="posix"
        ):
            self.assertFalse(transaction_module._modes_match("0666", "0644"))

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

    def test_sensitive_replace_temp_is_topic_free_and_recovery_cleans_only_its_artifact(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        state = root / "state"
        project = root / "project"
        memory = project / "docs" / "memory"
        target = memory / "areas" / "SensitiveTopic.md"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"pre-operation content\n")

        child = r"""
from pathlib import Path
import os
import sys
from memory_custodian import transactions as transaction_module
from memory_custodian.mutations import TextMutation
from memory_custodian.plans import MutationPlan
from memory_custodian.transactions import apply_plan_transaction

project, memory, target = map(Path, sys.argv[1:])
original_replace = os.replace
def exit_before_target_replace(source, destination):
    source = Path(source)
    destination = Path(destination)
    if (
        destination == target
        and source.parent.parent == target.parent
        and source.parent.name.startswith(".memory-custodian-")
        and source.name == "replacement"
    ):
        os._exit(73)
    return original_replace(source, destination)

transaction_module.os.replace = exit_before_target_replace
plan = MutationPlan(
    command="forget",
    arguments={},
    project_id="legacy-protocol-0.5",
    protocol_version="0.8",
    mutations=(TextMutation(target, "redacted"),),
    project_root=project,
    sensitive=True,
    private_context={"privacy_nonce": "0123456789abcdef0123456789abcdef"},
)
apply_plan_transaction(plan, memory)
"""
        environment = dict(
            os.environ,
            XDG_STATE_HOME=str(state),
            MEMORY_CUSTODIAN_FAILPOINT="",
        )
        result = subprocess.run(
            [sys.executable, "-c", child, str(project), str(memory), str(target)],
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 73, result.stderr)
        self.assertEqual(target.read_bytes(), b"pre-operation content\n")

        with mock.patch.dict(os.environ, {"XDG_STATE_HOME": str(state)}):
            binding = binding_directory(project, memory, None)
            inventory = transaction_inventory(binding)
            self.assertEqual(len(inventory), 1)
            self.assertEqual(inventory[0].kind, "unfinished")
            transaction_id = inventory[0].transaction_id
            residue = target.parent / f".memory-custodian-{transaction_id}-0001.txn"
            residue_payload = residue / "replacement"
            self.assertTrue(residue_payload.is_file())
            self.assertNotIn("SensitiveTopic", residue.name)
            self.assertEqual(residue_payload.read_bytes(), b"redacted\n")
            if os.name != "nt":
                self.assertEqual(stat.S_IMODE(residue.stat().st_mode), 0o700)

            unrelated = target.parent / f".memory-custodian-{transaction_id}-other.txn"
            unrelated.write_bytes(b"unrelated temporary file")
            roots = {"shared": RootBinding("shared", project, "shared")}
            directory = inventory[0].directory
            recovered = recover_transaction(directory, roots, action="rollback")
            self.assertEqual(recovered.phase, "rolled-back")
            self.assertFalse(residue.exists())
            self.assertEqual(unrelated.read_bytes(), b"unrelated temporary file")
            self.assertEqual(target.read_bytes(), b"pre-operation content\n")
            self.assertEqual(transaction_inventory(binding), ())

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

    def test_incomplete_replace_journal_is_blocked_without_cleanup(self):
        temporary, state, project, memory = self._fixture()
        self.addCleanup(temporary.cleanup)
        with mock.patch.dict(os.environ, {"XDG_STATE_HOME": str(state)}):
            binding = binding_directory(project, memory, None)
        directory = ensure_private_directory(binding / uuid.uuid4().hex)
        ensure_private_directory(directory / "targets")
        missing = project / "missing.md"
        journal = {
            "transaction_schema_version": 1,
            "transaction_id": directory.name,
            "project_binding": {"kind": "bootstrap", "id": binding.name},
            "command": "fixture",
            "plan_id": "fixture-plan",
            "phase": "planned",
            "created_at": "2026-09-23T01:02:03Z",
            "targets": [{
                "root_kind": "shared",
                "path": "missing.md",
                "operation": "replace",
            }],
            "created_directories": [],
        }
        self._write_journal(directory, journal)
        roots = {"shared": RootBinding("shared", project, "shared")}

        self._assert_journal_blocked(
            directory, roots, (missing,), expected_kind="malformed"
        )

    def test_required_top_level_fields_types_and_formats_are_strict(self):
        directory, roots, pristine, watched = self._prepared_replace_fixture()
        required = (
            "transaction_schema_version",
            "transaction_id",
            "project_binding",
            "command",
            "plan_id",
            "phase",
            "created_at",
            "targets",
            "created_directories",
        )
        for field in required:
            with self.subTest(missing=field):
                journal = copy.deepcopy(pristine)
                del journal[field]
                self._write_journal(directory, journal)
                self._assert_journal_blocked(
                    directory, roots, watched, expected_kind="malformed"
                )

        wrong_types = {
            "transaction_schema_version": True,
            "transaction_id": 1,
            "project_binding": [],
            "command": 1,
            "plan_id": [],
            "phase": 1,
            "created_at": 1,
            "targets": {},
            "created_directories": {},
        }
        for field, value in wrong_types.items():
            with self.subTest(wrong_type=field):
                journal = copy.deepcopy(pristine)
                journal[field] = value
                self._write_journal(directory, journal)
                self._assert_journal_blocked(
                    directory, roots, watched, expected_kind="malformed"
                )

        invalid_values = (
            ("project_binding", {"kind": "bootstrap", "id": "0" * 64}, "malformed"),
            ("created_at", "2026-09-23T01:02:03-07:00", "malformed"),
            ("created_at", "2026-02-30T01:02:03Z", "malformed"),
            ("plan_id", "private topic", "malformed"),
            ("command", "private\ntopic", "malformed"),
            ("transaction_schema_version", 2, "unsupported"),
        )
        for field, value, expected_kind in invalid_values:
            with self.subTest(invalid=field, value=value):
                journal = copy.deepcopy(pristine)
                journal[field] = value
                self._write_journal(directory, journal)
                self._assert_journal_blocked(
                    directory, roots, watched, expected_kind=expected_kind
                )

    def test_target_fields_types_and_cross_field_invariants_are_strict(self):
        directory, roots, pristine, watched = self._prepared_replace_fixture()
        target_fields = tuple(pristine["targets"][0])
        for field in target_fields:
            with self.subTest(missing=field):
                journal = copy.deepcopy(pristine)
                del journal["targets"][0][field]
                self._write_journal(directory, journal)
                self._assert_journal_blocked(
                    directory, roots, watched, expected_kind="malformed"
                )

        wrong_types = {
            "target_id": 1,
            "root_kind": [],
            "path": [],
            "operation": [],
            "commit_group": [],
            "commit_order": False,
            "base_exists": 1,
            "base_sha256": [],
            "mode_semantics": [],
            "base_mode": 0o644,
            "output_exists": 1,
            "output_sha256": [],
            "output_mode": 0o644,
            "backup_path": 1,
            "prepared_path": 1,
            "replaced": 0,
        }
        for field, value in wrong_types.items():
            with self.subTest(wrong_type=field):
                journal = copy.deepcopy(pristine)
                journal["targets"][0][field] = value
                self._write_journal(directory, journal)
                expected_kind = "unsafe" if field == "path" else "malformed"
                self._assert_journal_blocked(
                    directory, roots, watched, expected_kind=expected_kind
                )

        def set_target(**updates):
            def mutate(journal):
                journal["targets"][0].update(updates)
            return mutate

        invalid_cases = (
            ("short target id", set_target(target_id="1"), "malformed"),
            ("unsafe path", set_target(path="../private-topic"), "unsafe"),
            ("operation existence", set_target(operation="create"), "malformed"),
            ("base existence digest", set_target(base_exists=False), "malformed"),
            ("output existence digest", set_target(output_exists=False), "malformed"),
            ("base digest", set_target(base_sha256="g" * 64), "malformed"),
            ("output digest", set_target(output_sha256="0" * 63), "malformed"),
            ("base mode", set_target(base_mode="644"), "malformed"),
            ("output mode", set_target(output_mode="0999"), "malformed"),
            ("mode semantics", set_target(mode_semantics="foreign"), "malformed"),
            ("content ordering", set_target(commit_order=1), "malformed"),
            ("group ordering", set_target(commit_group="authority"), "malformed"),
            ("backup locator", set_target(backup_path="targets/9999.backup"), "malformed"),
            ("prepared locator", set_target(prepared_path=None), "malformed"),
            ("progress", set_target(replaced=1), "malformed"),
            ("progress before commit", set_target(replaced=True), "malformed"),
        )
        for name, mutate, expected_kind in invalid_cases:
            with self.subTest(case=name):
                journal = copy.deepcopy(pristine)
                mutate(journal)
                self._write_journal(directory, journal)
                self._assert_journal_blocked(
                    directory, roots, watched, expected_kind=expected_kind
                )

        for duplicate in ("target_id", "path"):
            with self.subTest(duplicate=duplicate):
                journal = copy.deepcopy(pristine)
                journal["targets"][1][duplicate] = journal["targets"][0][duplicate]
                self._write_journal(directory, journal)
                self._assert_journal_blocked(
                    directory, roots, watched, expected_kind="malformed"
                )

        journal = copy.deepcopy(pristine)
        journal["targets"][0]["unexpected"] = "private-topic"
        self._write_journal(directory, journal)
        self._assert_journal_blocked(
            directory, roots, watched, expected_kind="malformed"
        )

    def test_created_directory_fields_and_invariants_are_strict(self):
        directory, roots, pristine, watched = self._prepared_replace_fixture()
        valid_directory = {
            "root_kind": "shared",
            "path": "planned-parent",
            "mode": "0755",
            "base_exists": False,
            "created": False,
            "identity": None,
        }
        pristine["created_directories"] = [valid_directory]
        self._write_journal(directory, pristine)
        self.assertNotEqual(analyze_transaction(directory, roots).phase, "invalid")

        for field in tuple(valid_directory):
            with self.subTest(missing=field):
                journal = copy.deepcopy(pristine)
                del journal["created_directories"][0][field]
                self._write_journal(directory, journal)
                self._assert_journal_blocked(
                    directory, roots, watched, expected_kind="malformed"
                )

        invalid_cases = (
            ("root", {"root_kind": 1}, "malformed"),
            ("path type", {"path": []}, "unsafe"),
            ("path traversal", {"path": "../private-topic"}, "unsafe"),
            ("mode", {"mode": "0700"}, "malformed"),
            ("base exists type", {"base_exists": 0}, "malformed"),
            ("base exists", {"base_exists": True}, "malformed"),
            ("created type", {"created": 1}, "malformed"),
            ("identity without progress", {"identity": {"st_dev": 1, "st_ino": 2}}, "malformed"),
            (
                "created before committing",
                {"created": True, "identity": {"st_dev": 1, "st_ino": 2}},
                "malformed",
            ),
        )
        for name, updates, expected_kind in invalid_cases:
            with self.subTest(case=name):
                journal = copy.deepcopy(pristine)
                journal["created_directories"][0].update(updates)
                self._write_journal(directory, journal)
                self._assert_journal_blocked(
                    directory, roots, watched, expected_kind=expected_kind
                )

        for name, records in (
            ("duplicate", [valid_directory, copy.deepcopy(valid_directory)]),
            (
                "unsorted",
                [
                    {**valid_directory, "path": "z-parent"},
                    {**valid_directory, "path": "a-parent"},
                ],
            ),
        ):
            with self.subTest(case=name):
                journal = copy.deepcopy(pristine)
                journal["created_directories"] = copy.deepcopy(records)
                self._write_journal(directory, journal)
                self._assert_journal_blocked(
                    directory, roots, watched, expected_kind="malformed"
                )

    def test_artifact_inventory_must_be_complete_exact_and_untampered(self):
        for case in (
            "missing-prepared",
            "missing-backup",
            "extra",
            "tampered-prepared",
            "tampered-backup",
        ):
            with self.subTest(case=case):
                directory, roots, journal, watched = self._prepared_replace_fixture()
                prepared = directory / journal["targets"][0]["prepared_path"]
                backup = directory / journal["targets"][0]["backup_path"]
                if case == "missing-prepared":
                    prepared.unlink()
                    expected_kind = "unsafe"
                elif case == "missing-backup":
                    backup.unlink()
                    expected_kind = "unsafe"
                elif case == "extra":
                    write_private_file(directory / "targets" / "private-topic", "opaque")
                    expected_kind = "orphan"
                elif case == "tampered-prepared":
                    write_private_file(prepared, "tampered")
                    expected_kind = "unsafe"
                else:
                    write_private_file(backup, "tampered")
                    expected_kind = "unsafe"
                self._assert_journal_blocked(
                    directory, roots, watched, expected_kind=expected_kind
                )

        directory, roots, journal, watched = self._prepared_replace_fixture()
        journal["phase"] = "recovering"
        self._write_journal(directory, journal)
        for artifact in (directory / "targets").iterdir():
            artifact.unlink()
        (directory / "targets").rmdir()
        self._assert_journal_blocked(
            directory, roots, watched, expected_kind="unsafe"
        )

    def test_valid_planned_partial_artifacts_and_windows_basic_modes_remain_supported(self):
        temporary, state, project, memory = self._fixture()
        self.addCleanup(temporary.cleanup)
        first = memory / "first.md"
        second = memory / "second.md"
        first.write_text("old-first\n", encoding="utf-8")
        second.write_text("old-second\n", encoding="utf-8")
        directory = self._interrupted(
            state,
            project,
            memory,
            (TextMutation(first, "new-first"), TextMutation(second, "new-second")),
            "after-first-backup",
        )
        roots = {"shared": RootBinding("shared", project, "shared")}
        record = analyze_transaction(directory, roots)
        self.assertEqual(record.phase, "planned")
        self.assertTrue(record.safe_rollback)

        journal = json.loads((directory / "journal.json").read_text(encoding="utf-8"))
        journal["created_at"] = "2026-09-23T01:02:03.123456789+00:00"
        for target in journal["targets"]:
            target["mode_semantics"] = "windows-basic"
        self._write_journal(directory, journal)
        with mock.patch.object(
            transaction_module, "_platform_mode_semantics", return_value="windows-basic"
        ):
            record = analyze_transaction(directory, roots)
        self.assertEqual(record.phase, "planned")
        self.assertTrue(record.safe_rollback)

    def test_single_file_with_existing_parent_keeps_atomic_fast_path(self):
        temporary, state, project, memory = self._fixture()
        self.addCleanup(temporary.cleanup)
        local_root = ensure_private_directory(state / "local-root")
        migration_root = ensure_private_directory(state / "migration-root")
        project_id = str(uuid.uuid4())
        shared = memory / "shared.md"
        local = local_root / "local.md"
        migration = migration_root / "migration.md"

        with mock.patch.dict(os.environ, {"XDG_STATE_HOME": str(state)}):
            # Reaching binding_directory means the atomic fast path was
            # rejected and a journal was created.
            with mock.patch.object(
                transaction_module,
                "binding_directory",
                side_effect=AssertionError("existing parent should retain fast path"),
            ):
                apply_transaction(
                    project_root=project, memory_root=memory, project_id=None,
                    command="single-shared", plan_id="existing-parent-shared",
                    shared_mutations=(TextMutation(shared, "shared"),),
                )
                apply_transaction(
                    project_root=project, memory_root=memory, project_id=project_id,
                    command="single-local", plan_id="existing-parent-local",
                    private_mutations=(PrivateTextMutation(local, "local.md", "local"),),
                    local_root=local_root,
                )
                apply_transaction(
                    project_root=project, memory_root=memory, project_id=None,
                    command="single-migration", plan_id="existing-parent-migration",
                    migration_mutations=(PrivateTextMutation(migration, "migration.md", "migration"),),
                    migration_root=migration_root,
                )

        self.assertEqual(shared.read_text(encoding="utf-8"), "shared\n")
        self.assertEqual(local.read_text(encoding="utf-8"), "local")
        self.assertEqual(migration.read_text(encoding="utf-8"), "migration")

    def test_single_target_missing_parents_are_journaled_and_removed_on_rollback(self):
        temporary, state, project, memory = self._fixture()
        self.addCleanup(temporary.cleanup)
        local_root = ensure_private_directory(state / "local-root")
        migration_root = ensure_private_directory(state / "migration-root")
        local_project_id = str(uuid.uuid4())
        cases = (
            (
                "shared-bootstrap",
                None,
                project / "docs" / "memory" / "created" / "nested" / "target.md",
                {"shared_mutations": (TextMutation(
                    project / "docs" / "memory" / "created" / "nested" / "target.md",
                    "new shared",
                ),)},
                {"shared": RootBinding("shared", project, "shared")},
                "shared",
                {"docs/memory/created", "docs/memory/created/nested"},
            ),
            (
                "local-project-binding",
                local_project_id,
                local_root / "created" / "nested" / "target.md",
                {"private_mutations": (PrivateTextMutation(
                    local_root / "created" / "nested" / "target.md",
                    "created/nested/target.md",
                    "new local",
                ),), "local_root": local_root},
                {
                    "shared": RootBinding("shared", project, "shared"),
                    "local-overlay": RootBinding("local-overlay", local_root, "local"),
                },
                "local-overlay",
                {"created", "created/nested"},
            ),
            (
                "migration-bootstrap",
                None,
                migration_root / "created" / "nested" / "target.md",
                {"migration_mutations": (PrivateTextMutation(
                    migration_root / "created" / "nested" / "target.md",
                    "created/nested/target.md",
                    "new migration",
                ),), "migration_root": migration_root},
                {
                    "shared": RootBinding("shared", project, "shared"),
                    "migration-state": RootBinding(
                        "migration-state", migration_root, "migration-state"
                    ),
                },
                "migration-state",
                {"created", "created/nested"},
            ),
        )

        for (
            name, project_id, target, mutation_kwargs, roots,
            expected_root_kind, expected_paths,
        ) in cases:
            with self.subTest(case=name):
                with mock.patch.dict(os.environ, {
                    "XDG_STATE_HOME": str(state),
                    "MEMORY_CUSTODIAN_FAILPOINT": "after-first-replace",
                }):
                    with self.assertRaises(TransactionFailpoint):
                        apply_transaction(
                            project_root=project,
                            memory_root=memory,
                            project_id=project_id,
                            command="single-parent-recovery",
                            plan_id="single-parent-recovery-plan",
                            **mutation_kwargs,
                        )

                with mock.patch.dict(os.environ, {
                    "XDG_STATE_HOME": str(state),
                    "MEMORY_CUSTODIAN_FAILPOINT": "",
                }):
                    binding = binding_directory(project, memory, project_id)
                    directories = unfinished_transaction_directories(binding)
                    self.assertEqual(len(directories), 1)
                    directory = directories[0]
                    journal = json.loads(
                        (directory / "journal.json").read_text(encoding="utf-8")
                    )
                    created = journal["created_directories"]
                    self.assertEqual(
                        {item["root_kind"] for item in created},
                        {expected_root_kind},
                    )
                    self.assertEqual(
                        {item["path"] for item in created},
                        expected_paths,
                    )
                    self.assertTrue(all(item["created"] for item in created))
                    self.assertTrue(all(item["identity"] for item in created))
                    self.assertTrue(analyze_transaction(directory, roots).safe_rollback)
                    recover_transaction(directory, roots, action="rollback")

                self.assertFalse(target.exists())
                self.assertFalse(target.parent.exists())
                self.assertFalse(target.parent.parent.exists())

    def test_rollback_keeps_transaction_created_parent_if_it_is_no_longer_empty(self):
        temporary, state, project, memory = self._fixture()
        self.addCleanup(temporary.cleanup)
        target = memory / "created" / "target.md"
        directory = self._interrupted(
            state,
            project,
            memory,
            (TextMutation(target, "new"),),
            "after-first-replace",
        )
        unrelated = target.parent / "unrelated.txt"
        unrelated.write_text("keep", encoding="utf-8")
        roots = {"shared": RootBinding("shared", project, "shared")}

        with mock.patch.dict(os.environ, {
            "XDG_STATE_HOME": str(state),
            "MEMORY_CUSTODIAN_FAILPOINT": "",
        }):
            recover_transaction(directory, roots, action="rollback")

        self.assertFalse(target.exists())
        self.assertEqual(unrelated.read_text(encoding="utf-8"), "keep")
        self.assertTrue(target.parent.is_dir())

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
            state_before = self._state_snapshot(directory)
            record = analyze_transaction(directory, roots)
            self.assertFalse(record.safe_complete)
            self.assertFalse(record.safe_rollback)
            for action in ("complete", "rollback"):
                with self.assertRaises(RecoveryRequiredError):
                    recover_transaction(directory, roots, action=action)
                self.assertEqual(self._state_snapshot(directory), state_before)

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
