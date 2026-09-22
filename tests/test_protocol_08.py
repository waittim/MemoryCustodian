from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import re

from memory_custodian.entries import parse_structured_entries, render_active_entry
from memory_custodian.main import main
from memory_custodian.mutations import TextMutation
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
