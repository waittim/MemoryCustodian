"""Regression coverage for the unified public JSON result model."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from concurrent.futures import ThreadPoolExecutor
from io import StringIO
import json
import os
from pathlib import Path
import tempfile
from threading import Barrier
import unittest
from unittest.mock import patch

from memory_custodian.entries import render_active_entry, render_candidate_entry
from memory_custodian.main import main
from memory_custodian.output import (
    ResultContractError,
    collect_command_metadata,
    command_result,
    publish_data,
    publish_finding,
)
from memory_custodian.results import CommandResult, make_finding
from memory_custodian.subjects import render_subject


class JsonResultModelTests(unittest.TestCase):
    def _invoke(self, argv: list[str]) -> tuple[int, dict[str, object], str]:
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(argv)
        raw = stdout.getvalue()
        self.assertEqual(raw.count("\n"), 1, raw)
        payload = json.loads(raw)
        expected = {
            "success": ("PASS", 0),
            "success-with-review": ("REVIEW", 0),
            "domain-failure": ("FAIL", 1),
            "blocker": ("FAIL", 2),
            "fatal": ("FAIL", 2),
        }[payload["exit_class"]]
        self.assertEqual((payload["status"], code), expected, payload)
        return code, payload, stderr.getvalue()

    def _init(self, root: str) -> Path:
        code, payload, error = self._invoke([
            "init", "--project-root", root, "--format", "json",
        ])
        self.assertEqual(code, 0, payload)
        self.assertEqual(error, "")
        memory = Path(root) / "docs" / "memory"
        (memory / "brief.md").write_text(
            "# Project Brief\n\nPurpose:\nUnified JSON result fixture.\n\n"
            "Current direction:\nKeep every public outcome consistent.\n",
            encoding="utf-8",
        )
        return memory

    def test_command_result_derives_the_complete_exit_matrix(self):
        warning = make_finding("MC-TEST-001", "WARNING", "review")
        error = make_finding("MC-TEST-002", "ERROR", "domain failure")
        blocker = make_finding("MC-TEST-003", "BLOCKER", "blocked")
        cases = (
            (CommandResult("test", "0.8"), ("PASS", "success", 0)),
            (CommandResult("test", "0.8", findings=(warning,)), ("REVIEW", "success-with-review", 0)),
            (CommandResult("test", "0.8", findings=(error,)), ("FAIL", "domain-failure", 1)),
            (CommandResult("test", "0.8", findings=(blocker,)), ("FAIL", "blocker", 2)),
            (CommandResult("test", "0.8", findings=(blocker,), fatal=True), ("FAIL", "fatal", 2)),
        )
        for result, expected in cases:
            with self.subTest(expected=expected):
                result.validate()
                self.assertEqual(
                    (result.status, result.exit_class, result.return_code), expected,
                )

    def test_context_local_metadata_is_nested_and_concurrency_safe(self):
        with collect_command_metadata() as outer:
            publish_data(owner="outer", preserved=True)
            with collect_command_metadata() as inner:
                publish_data(owner="inner")
            publish_data(after_inner=True)
        publish_data(leaked_after_exit=True)

        self.assertEqual(
            outer.data,
            {"owner": "outer", "preserved": True, "after_inner": True},
        )
        self.assertEqual(inner.data, {"owner": "inner"})

        barrier = Barrier(4)

        def collect(value: int) -> dict[str, object]:
            with collect_command_metadata() as metadata:
                publish_data(owner=value)
                barrier.wait(timeout=10)
                return dict(metadata.data)

        with ThreadPoolExecutor(max_workers=4) as executor:
            collected = list(executor.map(collect, range(8)))
        self.assertEqual(collected, [{"owner": value} for value in range(8)])

    def test_legacy_handler_code_is_only_a_consistency_assertion(self):
        with collect_command_metadata() as metadata:
            publish_finding(make_finding(
                "MC-TEST-004", "ERROR", "typed domain failure",
            ))
        with self.assertRaises(ResultContractError):
            command_result(
                command="test",
                protocol_version="0.8",
                handler_return_code=0,
                rendered_text="",
                stderr_text="",
                metadata=metadata,
            )

    def test_strict_read_missing_manifest_is_one_blocker_document(self):
        with tempfile.TemporaryDirectory() as root:
            code, payload, error = self._invoke([
                "read", "--project-root", root,
                "--task", "implementation", "--path", "cli/example.py",
                "--strict-routing", "--format", "json",
            ])
        self.assertEqual(code, 2)
        self.assertEqual(error, "")
        self.assertIsNone(payload["protocol_version"])
        self.assertTrue(any(
            item["severity"] == "BLOCKER" for item in payload["findings"]
        ))
        self.assertEqual(payload["data"]["routing_completeness"], "INVALID")

    def test_blocked_forget_preview_keeps_preview_success_semantics(self):
        with tempfile.TemporaryDirectory() as root:
            memory = self._init(root)
            (memory / "decisions.md").write_text(
                "# Decisions\n\nSensitive phrase in non-removable preamble text.\n",
                encoding="utf-8",
            )
            code, payload, error = self._invoke([
                "forget", "Sensitive phrase", "--project-root", root,
                "--format", "json",
            ])
        self.assertEqual(code, 0, payload)
        self.assertEqual(error, "")
        self.assertIn(payload["status"], {"PASS", "REVIEW"})
        self.assertEqual(payload["data"]["plan"]["readiness"], "blocked")
        self.assertTrue(payload["data"]["plan"]["blockers"])
        self.assertIn("Dry run only", payload["data"]["rendered_text"])

    def test_protocol_version_comes_from_project_and_invalid_is_null(self):
        with tempfile.TemporaryDirectory() as root:
            memory = self._init(root)
            manifest = memory / "manifest.md"
            manifest.write_text(
                manifest.read_text(encoding="utf-8")
                .replace("protocol_version: 0.8", "protocol_version: 0.7", 1)
                .replace("entry_schema_version: 3", "entry_schema_version: 2", 1),
                encoding="utf-8",
            )
            code, payload, error = self._invoke([
                "list", "--project-root", root, "--format", "json",
            ])
            self.assertEqual((code, error, payload["protocol_version"]), (0, "", "0.7"))

            manifest.write_text(
                manifest.read_text(encoding="utf-8").replace(
                    "protocol_version: 0.7", "protocol_version: invalid", 1,
                ),
                encoding="utf-8",
            )
            code, payload, error = self._invoke([
                "status", "--project-root", root, "--format", "json",
            ])
            self.assertEqual((code, error), (1, ""))
            self.assertIsNone(payload["protocol_version"])

            code, payload, error = self._invoke([
                "read", "--project-root", root, "--task", "implementation",
                "--path", "cli/example.py", "--strict-routing", "--format", "json",
            ])
            self.assertEqual((code, error), (2, ""))
            self.assertIsNone(payload["protocol_version"])

    def test_json_preview_confirmation_round_trip_is_unchanged(self):
        with tempfile.TemporaryDirectory() as root:
            memory = self._init(root)
            tombstones = memory / "do-not-use.md"
            before = tombstones.read_text(encoding="utf-8")
            base = [
                "forget", "round trip topic", "--project-root", root,
                "--format", "json",
            ]
            code, preview, error = self._invoke(base)
            self.assertEqual((code, error), (0, ""), preview)
            self.assertEqual(tombstones.read_text(encoding="utf-8"), before)
            self.assertEqual(preview["data"]["plan"]["readiness"], "ready")
            plan_id = preview["data"]["plan"]["plan_id"]

            code, applied, error = self._invoke([
                *base, "--apply", "--confirm-plan", plan_id,
            ])
            self.assertEqual((code, error), (0, ""), applied)
            self.assertNotEqual(tombstones.read_text(encoding="utf-8"), before)
            self.assertEqual(
                applied["data"]["erasure_scope"]["operation_phase"], "applied",
            )

    def test_hard_forget_json_round_trip_preserves_privacy_boundaries(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as state:
            memory = self._init(root)
            secret = "PrivateJsonMarker"
            decisions = memory / "decisions.md"
            decisions.write_text(
                "# Decisions\n\nEntries are newest first.\n\n"
                + render_active_entry(
                    "decision",
                    "MC-DEC-20260924-1234abcd",
                    "Retire private marker",
                    f"Remove {secret} from managed memory.",
                    None,
                    "project",
                    ("user-confirmed",),
                )
                + "\n",
                encoding="utf-8",
            )
            base = [
                "forget", secret, "--mode", "hard", "--project-root", root,
                "--format", "json",
            ]
            with patch.dict(os.environ, {"XDG_STATE_HOME": state}):
                code, preview, error = self._invoke(base)
                self.assertEqual((code, error), (0, ""), preview)
                encoded_preview = json.dumps(preview, ensure_ascii=False)
                self.assertNotIn(secret, encoded_preview)
                self.assertNotIn(root, encoded_preview)
                self.assertNotIn(state, encoded_preview)
                for target in preview["data"]["plan"]["targets"]:
                    self.assertNotIn("base_sha256", target)
                    self.assertNotIn("expected_output_sha256", target)

                code, applied, error = self._invoke([
                    *base, "--apply", "--confirm-plan",
                    preview["data"]["plan"]["plan_id"],
                ])
            self.assertEqual((code, error), (0, ""), applied)
            self.assertNotIn(secret, json.dumps(applied, ensure_ascii=False))
            self.assertNotIn(secret, decisions.read_text(encoding="utf-8"))
            self.assertEqual(
                applied["data"]["erasure_scope"]["operation_phase"], "applied",
            )

    def test_review_domain_blocker_and_fatal_channels(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as state:
            self._init(root)
            with patch.dict(os.environ, {"XDG_STATE_HOME": state}):
                code, enabled, error = self._invoke([
                    "local", "enable", "--project-root", root, "--format", "json",
                ])
                self.assertEqual((code, enabled["status"], error), (0, "PASS", ""))
                code, reviewed, error = self._invoke([
                    "local", "status", "--project-root", root, "--format", "json",
                ])
                self.assertEqual((code, reviewed["status"], error), (0, "REVIEW", ""))

            code, domain, error = self._invoke([
                "show", "MC-DEC-20000101-deadbeef", "--project-root", root,
                "--format", "json",
            ])
            self.assertEqual((code, domain["exit_class"], error), (1, "domain-failure", ""))

            missing = str(Path(root) / "missing-project")
            code, blocked, error = self._invoke([
                "read", "--project-root", missing, "--task", "implementation",
                "--path", "cli/example.py", "--strict-routing", "--format", "json",
            ])
            self.assertEqual((code, blocked["exit_class"], error), (2, "blocker", ""))

            with patch("memory_custodian.main.read_cmd.run", side_effect=OSError("disk unavailable")):
                code, fatal, error = self._invoke([
                    "read", "--project-root", root, "--format", "json",
                ])
            self.assertEqual((code, fatal["exit_class"]), (2, "fatal"))
            self.assertIn("disk unavailable", error)

    def test_primary_command_families_emit_one_valid_document(self):
        with tempfile.TemporaryDirectory() as root:
            self._init(root)
            commands = (
                ["status"],
                ["check"],
                ["audit"],
                ["read", "--task", "general", "--names-only", "--no-local"],
                ["list"],
                ["recover"],
                ["local", "status"],
                ["subject", "list"],
                ["compact"],
                ["forget", "unused bounded topic"],
                ["enable", "changelog"],
                ["add", "Candidate note.", "--type", "inbox", "--evidence", "conversation-unconfirmed"],
                ["migrate", "--prepare"],
                ["init", "--repair"],
            )
            for command in commands:
                with self.subTest(command=command):
                    code, payload, error = self._invoke([
                        *command, "--project-root", root, "--format", "json",
                    ])
                    self.assertEqual(code, 0, payload)
                    self.assertEqual(error, "")
                    self.assertEqual(payload["protocol_version"], "0.8")

            code, listed, error = self._invoke([
                "list", "--project-root", root, "--format", "json",
            ])
            self.assertEqual((code, error), (0, ""))
            self.assertTrue(
                listed["data"]["entries"][0]["source"].startswith("docs/memory/")
            )
            entry_id = listed["data"]["entries"][0]["entry_id"]
            code, shown, error = self._invoke([
                "show", entry_id, "--project-root", root, "--format", "json",
            ])
            self.assertEqual((code, error), (0, ""))
            self.assertEqual(shown["data"]["entry"]["entry_id"], entry_id)
            self.assertTrue(shown["data"]["source"].startswith("docs/memory/"))

    def test_governance_preview_families_publish_typed_plans(self):
        with tempfile.TemporaryDirectory() as root:
            memory = self._init(root)
            subject_id = "MC-SUBJ-20260923-a1b2c3d4"
            project_id = "MC-DEC-20260923-11111111"
            area_id = "MC-AREA-20260923-22222222"
            candidate_id = "MC-INBOX-20260923-33333333"
            (memory / "subjects.md").write_text(
                "# Subject Registry\n\n" + render_subject(
                    subject_id, "Output ownership", "concept", None, (),
                    ("user-confirmed",),
                ) + "\n",
                encoding="utf-8",
            )
            (memory / "decisions.md").write_text(
                "# Decisions\n\nEntries are newest first.\n\n" + render_active_entry(
                    "decision", project_id, "Project output", "Use the project output.",
                    None, "project", ("user-confirmed",), subject=subject_id,
                    facet="interface",
                ) + "\n",
                encoding="utf-8",
            )
            code, _payload, error = self._invoke([
                "enable", "area/backend", "--project-root", root, "--format", "json",
            ])
            self.assertEqual((code, error), (0, ""))
            (memory / "areas" / "backend.md").write_text(
                "# Backend\n\n" + render_active_entry(
                    "area", area_id, "Backend output", "Use the backend exception.",
                    None, "area:backend", ("user-confirmed",), subject=subject_id,
                    facet="interface",
                ) + "\n",
                encoding="utf-8",
            )
            (memory / "inbox.md").write_text(
                "# Memory Inbox\n\n" + render_candidate_entry(
                    candidate_id, "Candidate output", "decision", "Candidate behavior.",
                    "project", ("user-confirmed",), None, subject=subject_id,
                    facet="interface",
                ) + "\n",
                encoding="utf-8",
            )

            commands = (
                ["promote", candidate_id, "--type", "decision", "--evidence", "user-confirmed"],
                ["exception", "add", area_id, "--to", project_id],
                [
                    "reconcile", "preview", "--entry", project_id, "--entry", area_id,
                    "--resolution", "exception", "--title", "Output exception",
                    "--evidence", "user-confirmed",
                ],
            )
            for command in commands:
                with self.subTest(command=command):
                    code, payload, error = self._invoke([
                        *command, "--project-root", root, "--format", "json",
                    ])
                    self.assertEqual((code, error), (0, ""), payload)
                    self.assertEqual(payload["protocol_version"], "0.8")
                    self.assertIn("plan", payload["data"])
                    self.assertIn(
                        payload["data"]["plan"]["readiness"], {"ready", "blocked"},
                    )


if __name__ == "__main__":
    unittest.main()
