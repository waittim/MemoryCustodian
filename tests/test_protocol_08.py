from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import re
from types import SimpleNamespace

from memory_custodian.entries import parse_structured_entries, render_active_entry
from memory_custodian.main import main
from memory_custodian.migrate import _source_binding
from memory_custodian.mutations import TextMutation
from memory_custodian.protocol import parse_markdown_units, project_id_from_manifest
from memory_custodian.local_overlay import LocalStatus
from memory_custodian.transactions import (
    RootBinding,
    TransactionFailpoint,
    analyze_transaction,
    apply_transaction,
    binding_directory,
    recover_transaction,
    unfinished_transaction_directories,
)


class Protocol08Tests(unittest.TestCase):
    def _capture(self, argv):
        output, error = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            code = main(argv)
        return code, output.getvalue(), error.getvalue()

    def _stage(self, root: Path, stage: str) -> tuple[str, str]:
        base = ["migrate", stage, "--project-root", str(root)]
        code, preview, error = self._capture(base)
        self.assertEqual(code, 0, preview + error)
        match = re.search(r"(?m)^Plan ID: ([0-9a-f]{16})$", preview)
        self.assertIsNotNone(match, preview)
        plan_id = match.group(1)
        code, applied, error = self._capture([
            *base, "--apply", "--confirm-plan", plan_id,
        ])
        self.assertEqual(code, 0, applied + error)
        return plan_id, applied

    def test_schema3_area_entry_type_round_trip(self):
        text = render_active_entry(
            "area", "MC-AREA-20260921-abcdef12", "Area decision", "Use queues.",
            None, "area:backend", ("user-confirmed",),
            subject="MC-SUBJ-20260921-abcdef12", facet="architecture",
        )
        self.assertIn("Entry-Type: decision", text)
        parsed = parse_structured_entries(Path("areas/backend.md"), text, entry_schema_version="3")
        self.assertEqual(parsed[0].fields["Entry-Type"], "decision")

    def test_transaction_crash_can_rollback_exact_preimages(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / "state"
            project = root / "project"
            memory = project / "docs" / "memory"
            memory.mkdir(parents=True)
            first = memory / "first.md"
            second = memory / "second.md"
            first.write_bytes(b"old\r\nno-newline")
            second.write_bytes(b"")
            with mock.patch.dict(os.environ, {"XDG_STATE_HOME": str(state), "MEMORY_CUSTODIAN_FAILPOINT": "after-first-replace"}):
                with self.assertRaises(TransactionFailpoint):
                    apply_transaction(
                        project_root=project, memory_root=memory, project_id=None,
                        command="test", plan_id="plan",
                        shared_mutations=(TextMutation(first, "new"), TextMutation(second, "newer")),
                    )
                binding = binding_directory(project, memory, None)
                directories = unfinished_transaction_directories(binding)
                self.assertEqual(len(directories), 1)
                roots = {"shared": RootBinding("shared", project, "shared")}
                record = analyze_transaction(directories[0], roots)
                self.assertTrue(record.safe_rollback)
                with mock.patch.dict(os.environ, {"XDG_STATE_HOME": str(state), "MEMORY_CUSTODIAN_FAILPOINT": ""}, clear=False):
                    recover_transaction(directories[0], roots, action="rollback")
            self.assertEqual(first.read_bytes(), b"old\r\nno-newline")
            self.assertEqual(second.read_bytes(), b"")

    def test_init_authority_crash_blocks_add_until_recovery(self):
        with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryDirectory() as state:
            root = Path(temporary).resolve()
            memory = root / "docs" / "memory"
            with mock.patch.dict(os.environ, {
                "XDG_STATE_HOME": state,
                "MEMORY_CUSTODIAN_FAILPOINT": "before-committed",
            }):
                code, _output, error = self._capture([
                    "init", "--project-root", str(root),
                ])
            self.assertEqual(code, 1)
            self.assertIn("before-committed", error)

            manifest = memory / "manifest.md"
            project_id = project_id_from_manifest(
                manifest.read_text(encoding="utf-8")
            )
            self.assertIsNotNone(project_id)
            inbox = memory / "inbox.md"
            before = inbox.read_text(encoding="utf-8")
            add = [
                "add", "Crash boundary candidate.",
                "--type", "inbox",
                "--candidate",
                "--evidence", "conversation-unconfirmed",
                "--project-root", str(root),
            ]
            with mock.patch.dict(os.environ, {
                "XDG_STATE_HOME": state,
                "MEMORY_CUSTODIAN_FAILPOINT": "",
            }, clear=False):
                bootstrap = binding_directory(root, memory, None)
                directories = unfinished_transaction_directories(bootstrap)
                self.assertEqual(len(directories), 1)
                project_binding = bootstrap.parents[1] / "project-id" / project_id
                self.assertFalse(project_binding.exists())

                code, _output, error = self._capture(add)
                self.assertEqual(code, 1)
                self.assertIn("requires recovery before mutation", error)
                self.assertEqual(inbox.read_text(encoding="utf-8"), before)
                self.assertFalse(project_binding.exists())

                code, output, error = self._capture([
                    "recover",
                    "--transaction-id", directories[0].name,
                    "--complete",
                    "--project-root", str(root),
                ])
                self.assertEqual(code, 0, output + error)
                self.assertIn("committed", output)

                code, output, error = self._capture(add)
                self.assertEqual(code, 0, output + error)
            self.assertIn(
                "Crash boundary candidate.", inbox.read_text(encoding="utf-8")
            )

    def test_json_envelope_and_audit_child_schema(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                self.assertEqual(main(["init", "--project-root", str(root)]), 0)
            (root / "docs" / "memory" / "brief.md").write_text(
                "# Project Brief\n\nPurpose:\nAudit JSON fixture.\n\n"
                "Current direction:\nValidate the Protocol 0.8 output contract.\n",
                encoding="utf-8",
            )
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                code = main(["audit", "--project-root", str(root), "--format", "json"])
            self.assertEqual(code, 0)
            payload = json.loads(stream.getvalue())
            self.assertEqual(payload["output_schema_version"], 1)
            self.assertEqual(payload["protocol_version"], "0.8")
            self.assertEqual(payload["data"]["audit_schema_version"], 1)
            self.assertIn(payload["status"], {"PASS", "REVIEW"})

    def test_staged_migration_requires_explicit_stage(self):
        stream = io.StringIO()
        with contextlib.redirect_stderr(stream):
            with self.assertRaises(SystemExit) as caught:
                main(["migrate"])
        self.assertEqual(caught.exception.code, 2)

    def test_staged_migration_uses_distinct_plans_and_cleans_private_state(self):
        with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryDirectory() as state:
            root = Path(temporary)
            with mock.patch.dict(os.environ, {"XDG_STATE_HOME": state}):
                self.assertEqual(main(["init", "--project-root", str(root)]), 0)
                manifest = root / "docs" / "memory" / "manifest.md"
                manifest.write_text(
                    manifest.read_text(encoding="utf-8")
                    .replace("protocol_version: 0.8", "protocol_version: 0.7")
                    .replace("entry_schema_version: 3", "entry_schema_version: 2"),
                    encoding="utf-8",
                )
                prepare_id, _ = self._stage(root, "--prepare")
                canonicalize_id, _ = self._stage(root, "--canonicalize")
                finalize_id, _ = self._stage(root, "--finalize")
                self.assertEqual(len({prepare_id, canonicalize_id, finalize_id}), 3)
                migrated = manifest.read_text(encoding="utf-8")
                self.assertIn("protocol_version: 0.8", migrated)
                self.assertIn("entry_schema_version: 3", migrated)
                migration_root = Path(state) / "memory-custodian" / "migrations"
                self.assertFalse(any(migration_root.glob("*.json")))

    def test_supported_legacy_metadata_combinations_enter_all_stages(self):
        combinations = (("0.5", "1"), ("0.6", "1"), ("0.7", "1"), ("0.7", "2"))
        for protocol_version, entry_schema_version in combinations:
            with self.subTest(protocol=protocol_version, schema=entry_schema_version):
                with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryDirectory() as state:
                    root = Path(temporary)
                    with mock.patch.dict(os.environ, {"XDG_STATE_HOME": state}):
                        self.assertEqual(main(["init", "--project-root", str(root)]), 0)
                        manifest = root / "docs" / "memory" / "manifest.md"
                        source = manifest.read_text(encoding="utf-8")
                        source = source.replace(
                            "protocol_version: 0.8", f"protocol_version: {protocol_version}",
                        ).replace(
                            "entry_schema_version: 3", f"entry_schema_version: {entry_schema_version}",
                        )
                        manifest.write_text(source, encoding="utf-8")
                        ids = [self._stage(root, stage)[0] for stage in (
                            "--prepare", "--canonicalize", "--finalize",
                        )]
                        self.assertEqual(len(set(ids)), 3)
                        migrated = manifest.read_text(encoding="utf-8")
                        self.assertIn("protocol_version: 0.8", migrated)
                        self.assertIn("entry_schema_version: 3", migrated)

    def test_finalize_rejects_source_drift_after_canonicalization(self):
        with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryDirectory() as state:
            root = Path(temporary)
            with mock.patch.dict(os.environ, {"XDG_STATE_HOME": state}):
                self.assertEqual(main(["init", "--project-root", str(root)]), 0)
                manifest = root / "docs" / "memory" / "manifest.md"
                manifest.write_text(
                    manifest.read_text(encoding="utf-8")
                    .replace("protocol_version: 0.8", "protocol_version: 0.7")
                    .replace("entry_schema_version: 3", "entry_schema_version: 2"),
                    encoding="utf-8",
                )
                self._stage(root, "--prepare")
                self._stage(root, "--canonicalize")
                brief = root / "docs" / "memory" / "brief.md"
                brief.write_bytes(brief.read_bytes() + b"\nConcurrent source drift.\r\n")
                code, _output, error = self._capture([
                    "migrate", "--finalize", "--project-root", str(root),
                ])
                self.assertEqual(code, 2)
                self.assertIn("source changed after canonicalization", error)

    def test_migration_local_binding_hashes_raw_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assertEqual(main(["init", "--project-root", str(root)]), 0)
            memory = root / "docs" / "memory"
            manifest = (memory / "manifest.md").read_text(encoding="utf-8")
            metadata = {"project_id": re.search(r"project_id: (\S+)", manifest).group(1)}
            local_path = root / "private-local-preferences.md"
            local_path.write_bytes(b"first\r\nsecond\r\n")
            captured = SimpleNamespace(
                relative="preferences.md",
                path=local_path,
                text="first\nsecond\n",
            )
            overlay = SimpleNamespace(
                status=LocalStatus.BOUND,
                warnings=(),
                snapshot=SimpleNamespace(files=(captured,)),
            )
            with mock.patch("memory_custodian.migrate.inspect_overlay", return_value=overlay):
                binding, _source = _source_binding(root, memory, manifest, metadata)
            expected = hashlib.sha256(b"first\r\nsecond\r\n").hexdigest()
            self.assertEqual(
                binding["source_raw_byte_digests"]["local"]["preferences.md"],
                expected,
            )

    def test_add_from_legacy_replaces_exact_h2_without_duplication(self):
        with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryDirectory() as state:
            root = Path(temporary)
            with mock.patch.dict(os.environ, {"XDG_STATE_HOME": state}):
                self.assertEqual(main(["init", "--project-root", str(root)]), 0)
                subject_args = [
                    "subject", "add", "Legacy conversion", "--kind", "concept",
                    "--evidence", "user-confirmed", "--project-root", str(root),
                ]
                code, preview, error = self._capture(subject_args)
                self.assertEqual(code, 0, preview + error)
                plan_id = re.search(r"(?m)^Plan ID: ([0-9a-f]{16})$", preview).group(1)
                self.assertEqual(main([*subject_args, "--apply", "--confirm-plan", plan_id]), 0)
                subjects = (root / "docs" / "memory" / "subjects.md").read_text(encoding="utf-8")
                subject_id = re.search(r"(?m)^## (MC-SUBJ-\S+) — Legacy conversion$", subjects).group(1)
                decisions = root / "docs" / "memory" / "decisions.md"
                decisions.write_text(
                    decisions.read_text(encoding="utf-8").rstrip()
                    + "\n\n## 2026-09-22 - Legacy choice\nDecision:\nKeep exact body.\nReason:\nExplicit conversion.\n",
                    encoding="utf-8",
                )
                units = parse_markdown_units(decisions.read_text(encoding="utf-8")).units
                unit_index = next(
                    index for index, unit in enumerate(units)
                    if unit.kind == "h2" and unit.heading == "2026-09-22 - Legacy choice"
                )
                command = [
                    "add", "--from-legacy", f"decisions.md:{unit_index}",
                    "--type", "decision", "--title", "Canonical choice",
                    "--scope", "project", "--subject", subject_id,
                    "--facet", "behavior", "--evidence", "user-confirmed",
                    "--project-root", str(root),
                ]
                code, preview, error = self._capture(command)
                self.assertEqual(code, 0, preview + error)
                plan_id = re.search(r"(?m)^Plan ID: ([0-9a-f]{16})$", preview).group(1)
                code, output, error = self._capture([
                    *command, "--apply", "--confirm-plan", plan_id,
                ])
                self.assertEqual(code, 0, output + error)
                result = decisions.read_text(encoding="utf-8")
                self.assertNotIn("## 2026-09-22 - Legacy choice", result)
                self.assertEqual(result.count("Keep exact body."), 1)
                self.assertIn("## MC-DEC-", result)
                self.assertIn("Subject: " + subject_id, result)

    def test_local_reset_deletes_private_tree_transactionally(self):
        with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryDirectory() as state:
            root = Path(temporary)
            environment = {"XDG_STATE_HOME": state}
            with mock.patch.dict(os.environ, environment):
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["init", "--project-root", str(root)]), 0)
                    self.assertEqual(main(["local", "enable", "--project-root", str(root)]), 0)
                    self.assertEqual(main(["local", "link", "--project-root", str(root)]), 0)
                preview = io.StringIO()
                with contextlib.redirect_stdout(preview):
                    self.assertEqual(main(["local", "reset", "--project-root", str(root)]), 0)
                plan_id = re.search(r"(?m)^Plan ID: ([0-9a-f]{16})$", preview.getvalue())
                self.assertIsNotNone(plan_id)
                applied = io.StringIO()
                with contextlib.redirect_stdout(applied):
                    self.assertEqual(main([
                        "local", "reset", "--project-root", str(root), "--apply",
                        "--confirm-plan", plan_id.group(1),
                    ]), 0)
                self.assertIn("- Operation phase: applied", applied.getvalue())
                self.assertIn("- Local overlay: removed", applied.getvalue())
                project_id = re.search(
                    r"(?m)^- project_id: (\S+)$",
                    (root / "docs" / "memory" / "manifest.md").read_text(encoding="utf-8"),
                ).group(1)
                overlay = Path(state) / "memory-custodian" / "projects" / project_id / "local"
                self.assertFalse(overlay.exists())


if __name__ == "__main__":
    unittest.main()
