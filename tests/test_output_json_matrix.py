"""Protocol 0.8 public JSON command matrix."""

from __future__ import annotations

import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import re
import tempfile
import unittest

from tests.cli_test_support import main


_MACHINE_PATHS = ("/Volumes/", "/private/var/", "/Users/", "C:\\Users\\")


class JsonCommandMatrixTests(unittest.TestCase):
    def _invoke(self, argv: list[str]):
        stream = StringIO()
        with redirect_stdout(stream):
            code = main(argv)
        payload = json.loads(stream.getvalue())
        self.assertEqual(stream.getvalue().count("\n"), 1)
        return code, payload

    def _init(self, root: str, *, extended: bool = False) -> Path:
        args = ["init", "--project-root", root]
        if extended:
            args.append("--extended")
        self.assertEqual(main(args), 0)
        memory = Path(root) / "docs" / "memory"
        (memory / "brief.md").write_text(
            "# Project Brief\n\nPurpose:\nJSON matrix fixture.\n\n"
            "Current direction:\nKeep public outputs stable.\n",
            encoding="utf-8",
        )
        return memory

    def _assert_no_machine_paths(self, payload: dict):
        encoded = json.dumps(payload, ensure_ascii=False)
        for marker in _MACHINE_PATHS:
            self.assertNotIn(marker, encoded)

    def test_read_only_contracts_have_structured_data(self):
        with tempfile.TemporaryDirectory() as root:
            self._init(root, extended=True)
            for command in ("status", "check", "audit"):
                args = [command, "--project-root", root, "--format", "json"]
                if command == "audit":
                    args.append("--all")
                code, payload = self._invoke(args)
                self.assertEqual(code, 0, payload)
                self.assertEqual(payload["output_schema_version"], 1)
                self.assertEqual(payload["command"], command)
                self.assertIn("findings", payload)
                if command == "status":
                    self.assertIn("files", payload["data"])
                    self.assertEqual(payload["data"]["memory_directory"], "docs/memory")
                elif command == "check":
                    self.assertIn("subjects", payload["data"])
                else:
                    self.assertEqual(payload["data"]["audit_schema_version"], 1)
                    self.assertIn("erasure_scope", payload["data"])
                    self.assertIn("history_exposure", payload["data"])
                self._assert_no_machine_paths(payload)

    def test_read_list_show_and_recovery_contracts(self):
        with tempfile.TemporaryDirectory() as root:
            memory = self._init(root)
            self.assertEqual(
                main([
                    "add", "Use a deterministic output model.", "--type", "decision",
                    "--project-root", root,
                ]),
                0,
            )
            text = (memory / "decisions.md").read_text(encoding="utf-8")
            entry_id = re.search(r"MC-DEC-\d{8}-[0-9a-f]{8}", text, re.I).group(0)
            for args in (
                ["read", "--task", "implementation", "--names-only", "--no-local"],
                ["list"],
                ["show", entry_id],
                ["recover"],
            ):
                code, payload = self._invoke([
                    *args, "--project-root", root, "--format", "json",
                ])
                self.assertEqual(code, 0, payload)
                self.assertEqual(payload["output_schema_version"], 1)
                if args[0] == "list":
                    self.assertEqual(payload["data"]["entries"][0]["entry_id"], entry_id)
                if args[0] == "recover":
                    self.assertEqual(payload["data"]["recovery_status"], "clean")
                self._assert_no_machine_paths(payload)

    def test_preview_and_local_reset_always_expose_complete_erasure_scope(self):
        with tempfile.TemporaryDirectory() as root:
            memory = self._init(root)
            self.assertEqual(
                main([
                    "add", "Sensitive bounded topic.", "--type", "decision",
                    "--project-root", root,
                ]),
                0,
            )
            code, payload = self._invoke([
                "forget", "Sensitive", "--project-root", root, "--format", "json",
            ])
            self.assertEqual(code, 0, payload)
            scope = payload["data"]["erasure_scope"]
            self.assertEqual(scope["operation_phase"], "preview")
            self.assertEqual(
                set(scope),
                {
                    "erasure_scope_schema_version", "operation_phase", "active_memory",
                    "managed_archive", "local_overlay", "git_worktree_modified",
                    "git_history_modified", "distributed_copies_revoked",
                    "history_check_status", "topic_retained_in_new_records",
                },
            )
            code, payload = self._invoke([
                "local", "reset", "--project-root", root, "--format", "json",
            ])
            self.assertEqual(code, 0, payload)
            self.assertEqual(payload["data"]["erasure_scope"]["operation_phase"], "no-op")
            self._assert_no_machine_paths(payload)


if __name__ == "__main__":
    unittest.main()
