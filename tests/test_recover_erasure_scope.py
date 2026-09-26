from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import tempfile
import unittest
import uuid
from unittest import mock

from memory_custodian.erasure import ErasureScope, scope_for_forget
from memory_custodian.local_overlay import overlay_directory
from memory_custodian.locking import ensure_private_directory
from memory_custodian.main import main
from memory_custodian.mutations import PrivateDeleteMutation, TextMutation
from memory_custodian.protocol import project_id_from_manifest
from memory_custodian.transactions import (
    TransactionFailpoint,
    apply_transaction,
    binding_directory,
    unfinished_transaction_directories,
)


class RecoveryErasureScopeTests(unittest.TestCase):
    def _fixture(self, *, with_project_id: bool = False):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        state = root / "state"
        project = root / "project"
        project.mkdir()
        project = project.resolve()
        memory = project / "docs" / "memory"
        memory.mkdir(parents=True)
        memory = memory.resolve()
        project_id = None
        if with_project_id:
            with mock.patch.dict(os.environ, {"XDG_STATE_HOME": str(state)}, clear=False):
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["init", "--project-root", str(project)]), 0)
            memory = project / "docs" / "memory"
            project_id = project_id_from_manifest(
                (memory / "manifest.md").read_text(encoding="utf-8")
            )
        return state, project, memory, project_id

    def _interrupt(
        self,
        state: Path,
        project: Path,
        memory: Path,
        *,
        failpoint: str,
        command: str,
        scope: dict[str, object],
        mutations: tuple[TextMutation, ...] = (),
        private_deletions: tuple[PrivateDeleteMutation, ...] = (),
        project_id: str | None = None,
        local_root: Path | None = None,
    ) -> str:
        with mock.patch.dict(os.environ, {
            "XDG_STATE_HOME": str(state),
            "MEMORY_CUSTODIAN_FAILPOINT": failpoint,
        }, clear=False):
            with self.assertRaises(TransactionFailpoint):
                apply_transaction(
                    project_root=project,
                    memory_root=memory,
                    project_id=project_id,
                    command=command,
                    plan_id="recover-erasure-scope-fixture",
                    shared_mutations=mutations,
                    private_deletions=private_deletions,
                    local_root=local_root,
                    erasure_scope=scope,
                    force_journal=True,
                )
            binding = binding_directory(project, memory, project_id)
            transactions = unfinished_transaction_directories(binding)
        self.assertEqual(len(transactions), 1)
        return transactions[0].name

    def _recover_json(self, state: Path, project: Path, transaction_id: str, action: str):
        output = StringIO()
        with mock.patch.dict(os.environ, {"XDG_STATE_HOME": str(state)}, clear=False):
            with redirect_stdout(output):
                result = main([
                    "recover", "--project-root", str(project),
                    "--transaction-id", transaction_id, f"--{action}",
                    "--format", "json",
                ])
        self.assertEqual(result, 0, output.getvalue())
        return json.loads(output.getvalue())

    def test_rollback_before_first_replace_keeps_pending_scope_and_no_worktree_effect(self):
        state, project, memory, project_id = self._fixture()
        target = memory / "decisions.md"
        target.write_text("sensitive original\n", encoding="utf-8")
        scope = scope_for_forget(
            "hard", active_matches=True, archive_matches=False, has_mutations=True,
        ).canonical()
        transaction_id = self._interrupt(
            state, project, memory,
            failpoint="after-journal-prepared", command="forget-hard", scope=scope,
            mutations=(TextMutation(target, "redacted"),), project_id=project_id,
        )

        payload = self._recover_json(state, project, transaction_id, "rollback")
        recovered = payload["data"]["erasure_scope"]
        self.assertEqual(recovered["operation_phase"], "recovered-rollback")
        self.assertEqual(recovered["active_memory"], "pending-removal")
        self.assertEqual(recovered["git_worktree_modified"], "no")
        self.assertIn(
            "Managed content was unchanged by the interrupted transaction; "
            "start a new forget plan if removal is still intended.",
            payload["data"]["rendered_text"],
        )
        self.assertNotIn("Managed content was restored", payload["data"]["rendered_text"])
        self.assertEqual(target.read_text(encoding="utf-8"), "sensitive original\n")

    def test_planned_rollback_text_does_not_claim_content_was_restored(self):
        state, project, memory, project_id = self._fixture()
        target = memory / "decisions.md"
        target.write_text("sensitive original\n", encoding="utf-8")
        scope = scope_for_forget(
            "hard", active_matches=True, archive_matches=False, has_mutations=True,
        ).canonical()
        transaction_id = self._interrupt(
            state, project, memory,
            failpoint="after-planned-before-first-artifact", command="forget-hard",
            scope=scope, mutations=(TextMutation(target, "redacted"),),
            project_id=project_id,
        )

        output = StringIO()
        with mock.patch.dict(os.environ, {"XDG_STATE_HOME": str(state)}, clear=False):
            with redirect_stdout(output):
                result = main([
                    "recover", "--project-root", str(project),
                    "--transaction-id", transaction_id, "--rollback",
                ])
        self.assertEqual(result, 0, output.getvalue())
        self.assertIn("Active managed memory: pending-removal", output.getvalue())
        self.assertIn("Git worktree modified: no", output.getvalue())
        self.assertIn("start a new forget plan if removal is still intended.", output.getvalue())
        self.assertNotIn("Managed content was restored", output.getvalue())
        self.assertEqual(target.read_text(encoding="utf-8"), "sensitive original\n")

    def test_partial_purge_rollback_restores_only_changed_domain_and_text_is_accurate(self):
        state, project, memory, project_id = self._fixture()
        active = memory / "decisions.md"
        archive = memory / "archive" / "old.md"
        archive.parent.mkdir()
        active.write_text("active original\n", encoding="utf-8")
        archive.write_text("archive original\n", encoding="utf-8")
        scope = scope_for_forget(
            "purge", active_matches=True, archive_matches=True, has_mutations=True,
        ).canonical()
        transaction_id = self._interrupt(
            state, project, memory,
            failpoint="after-first-replace", command="forget-purge", scope=scope,
            mutations=(
                TextMutation(active, "redacted active"),
                TextMutation(archive, "redacted archive"),
            ), project_id=project_id,
        )

        payload = self._recover_json(state, project, transaction_id, "rollback")
        recovered = payload["data"]["erasure_scope"]
        self.assertEqual(recovered["active_memory"], "pending-removal")
        self.assertEqual(recovered["managed_archive"], "restored")
        self.assertEqual(recovered["git_worktree_modified"], "yes")
        rendered = payload["data"]["rendered_text"]
        self.assertIn("Managed content was restored from protected recovery state.", rendered)
        self.assertIn("Active managed memory: pending-removal", rendered)
        self.assertIn("Managed archive: restored", rendered)
        self.assertEqual(active.read_text(encoding="utf-8"), "active original\n")
        self.assertEqual(archive.read_text(encoding="utf-8"), "archive original\n")

    def test_complete_distinguishes_new_replacements_from_committed_cleanup(self):
        for failpoint, expected_worktree in (
            ("after-journal-prepared", "yes"),
            ("after-committed-before-cleanup", "no"),
        ):
            with self.subTest(failpoint=failpoint):
                state, project, memory, project_id = self._fixture()
                target = memory / "decisions.md"
                target.write_text("sensitive original\n", encoding="utf-8")
                scope = scope_for_forget(
                    "hard", active_matches=True, archive_matches=False, has_mutations=True,
                ).canonical()
                transaction_id = self._interrupt(
                    state, project, memory,
                    failpoint=failpoint, command="forget-hard", scope=scope,
                    mutations=(TextMutation(target, "redacted"),), project_id=project_id,
                )

                payload = self._recover_json(state, project, transaction_id, "complete")
                recovered = payload["data"]["erasure_scope"]
                self.assertEqual(recovered["operation_phase"], "recovered-complete")
                self.assertEqual(recovered["active_memory"], "removed")
                self.assertEqual(recovered["git_worktree_modified"], expected_worktree)
                self.assertEqual(target.read_text(encoding="utf-8"), "redacted\n")

    def test_complete_with_no_content_delta_does_not_claim_removal(self):
        state, project, memory, project_id = self._fixture()
        target = memory / "decisions.md"
        target.write_text("same content\n", encoding="utf-8")
        scope = scope_for_forget(
            "hard", active_matches=True, archive_matches=False, has_mutations=True,
        ).canonical()
        transaction_id = self._interrupt(
            state, project, memory,
            failpoint="after-journal-prepared", command="forget-hard", scope=scope,
            mutations=(TextMutation(target, "same content"),), project_id=project_id,
        )

        payload = self._recover_json(state, project, transaction_id, "complete")
        recovered = payload["data"]["erasure_scope"]
        self.assertEqual(recovered["active_memory"], "pending-removal")
        self.assertEqual(recovered["git_worktree_modified"], "no")
        self.assertIn(
            "No managed content was removed during recovery; start a new forget plan",
            payload["data"]["rendered_text"],
        )
        self.assertEqual(target.read_text(encoding="utf-8"), "same content\n")

    def test_local_reset_recovery_does_not_report_git_worktree_changes(self):
        state, project, memory, project_id = self._fixture(with_project_id=True)
        assert project_id is not None
        with mock.patch.dict(os.environ, {"XDG_STATE_HOME": str(state)}, clear=False):
            overlay = overlay_directory(project_id)
            ensure_private_directory(overlay.parent)
            ensure_private_directory(overlay)
            first = overlay / "first.md"
            second = overlay / "second.md"
            first.write_text("private one\n", encoding="utf-8")
            second.write_text("private two\n", encoding="utf-8")
        scope = ErasureScope(
            erasure_scope_schema_version=1,
            operation_phase="preview",
            active_memory="not-applicable",
            managed_archive="not-targeted",
            local_overlay="pending-removal",
            git_worktree_modified="no",
            git_history_modified=False,
            distributed_copies_revoked=False,
            history_check_status="not-requested",
            topic_retained_in_new_records=False,
        ).canonical()
        transaction_id = self._interrupt(
            state, project, memory,
            failpoint="after-first-replace", command="local-reset", scope=scope,
            private_deletions=(
                PrivateDeleteMutation(first, "first.md"),
                PrivateDeleteMutation(second, "second.md"),
            ), project_id=project_id, local_root=overlay.parent,
        )

        payload = self._recover_json(state, project, transaction_id, "rollback")
        recovered = payload["data"]["erasure_scope"]
        self.assertEqual(recovered["local_overlay"], "restored")
        self.assertEqual(recovered["git_worktree_modified"], "no")
        self.assertEqual(first.read_text(encoding="utf-8"), "private one\n")
        self.assertEqual(second.read_text(encoding="utf-8"), "private two\n")

    def test_local_reset_completion_removes_journaled_directories(self):
        for failpoint in (
            "after-committed-before-cleanup",
            "after-first-removed-directory",
        ):
            with self.subTest(failpoint=failpoint):
                state, project, memory, project_id = self._fixture(with_project_id=True)
                assert project_id is not None
                with mock.patch.dict(os.environ, {"XDG_STATE_HOME": str(state)}, clear=False):
                    with redirect_stdout(StringIO()):
                        self.assertEqual(main([
                            "local", "link", "--project-root", str(project),
                        ]), 0)
                    overlay = overlay_directory(project_id)
                    self.assertTrue((overlay / "profiles").is_dir())
                    preview = StringIO()
                    with redirect_stdout(preview):
                        self.assertEqual(main([
                            "local", "reset", "--project-root", str(project),
                            "--format", "json",
                        ]), 0)
                    plan_id = json.loads(preview.getvalue())["data"]["plan"]["plan_id"]
                    with mock.patch.dict(os.environ, {"MEMORY_CUSTODIAN_FAILPOINT": failpoint}):
                        with redirect_stdout(StringIO()):
                            self.assertNotEqual(main([
                                "local", "reset", "--project-root", str(project),
                                "--apply", "--confirm-plan", plan_id,
                            ]), 0)
                    transaction = unfinished_transaction_directories(
                        binding_directory(project, memory, project_id)
                    )
                    self.assertEqual(len(transaction), 1)
                    payload = self._recover_json(
                        state, project, transaction[0].name, "complete",
                    )
                    self.assertEqual(payload["data"]["erasure_scope"]["local_overlay"], "removed")
                    self.assertFalse(overlay.exists())
                    self.assertFalse((overlay.parent / "bindings.json").exists())
                    status = StringIO()
                    with redirect_stdout(status):
                        self.assertEqual(main([
                            "local", "status", "--project-root", str(project),
                        ]), 0)
                    self.assertIn("DISABLED", status.getvalue())


if __name__ == "__main__":
    unittest.main()
