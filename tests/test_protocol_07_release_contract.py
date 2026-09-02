"""Protocol 0.7 Entry schema 1-to-2 compatibility regression coverage."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from memory_custodian import (
    __entry_schema_version__,
    __protocol_version__,
    __version__,
)
from memory_custodian.entries import (
    BODY_FENCE_INFO,
    ENTRY_SCHEMA_VERSION,
    line_safe_markdown_body,
    migrate_entry_schema,
    parse_structured_entries,
)
from memory_custodian.local_overlay import add_local_preference, inspect_overlay
from memory_custodian.main import main
from memory_custodian.protocol import (
    entry_schema_version_for_manifest,
    inspect_manifest_contract,
)
from memory_custodian.snapshot import build_snapshot


ROOT = Path(__file__).resolve().parents[1]


def capture(argv: list[str]) -> tuple[int, str, str]:
    stdout, stderr = StringIO(), StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = main(argv)
    return code, stdout.getvalue(), stderr.getvalue()


class Protocol07ReleaseContractTests(unittest.TestCase):
    def test_schema_2_is_current_and_public_legacy_boundary_is_documented(self):
        self.assertEqual(__version__, "0.11.0")
        self.assertEqual(__protocol_version__, "0.7")
        self.assertEqual(__entry_schema_version__, "2")
        self.assertEqual(ENTRY_SCHEMA_VERSION, "2")
        self.assertEqual(BODY_FENCE_INFO, "memory-custodian-body-v1")

        reference = (
            ROOT / "skills" / "memory-custodian" / "references" / "memory-file-protocol.md"
        ).read_text(encoding="utf-8")
        self.assertIn("Protocol 0.7 Entry schema 1 to 2 boundary", reference)
        self.assertIn("schema 1 was publicly", reference)
        self.assertIn("schema 2 is the current grammar", reference)
        self.assertIn("literal-body semantics", reference)
        self.assertIn("bound local overlay", reference)
        self.assertIn("blocks the shared schema flip", reference)

        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("Protocol 0.7/schema 1 was publicly available", readme)
        self.assertIn("current Protocol 0.7/schema 2 grammar", readme)
        self.assertIn("must not treat schema 1 as current", readme)
        self.assertIn("Bound local files are included", readme)

        release_notes = (ROOT / "RELEASE-NOTES.md").read_text(encoding="utf-8")
        self.assertIn("Entry schema 1 to 2 compatibility boundary", release_notes)
        self.assertIn("supported legacy input", release_notes)
        self.assertIn("preview/applies a schema 1-to-2 migration", release_notes)
        self.assertIn("Bound local files migrate", release_notes)

        template = (ROOT / "templates" / "minimal" / "manifest.md").read_text(encoding="utf-8")
        self.assertIn("- entry_schema_version: 2", template)

    def test_malformed_schema_metadata_fails_closed_to_legacy_parser(self):
        malformed = (
            "## MemoryCustodian Protocol\n"
            "- protocol_version: 0.7\n"
            "- entry_schema_version: 1\n"
            "- entry_schema_version: 2\n"
        )
        self.assertEqual(entry_schema_version_for_manifest(malformed), "1")
        unknown = malformed.replace(
            "- entry_schema_version: 1\n- entry_schema_version: 2",
            "- entry_schema_version: 9",
        )
        self.assertEqual(entry_schema_version_for_manifest(unknown), "1")
        older_protocol = malformed.replace(
            "- protocol_version: 0.7", "- protocol_version: 0.6",
        ).replace(
            "- entry_schema_version: 1\n- entry_schema_version: 2",
            "- entry_schema_version: 2",
        )
        self.assertEqual(entry_schema_version_for_manifest(older_protocol), "1")
        unknown_schema = (
            "## MemoryCustodian Protocol\n"
            "- protocol_version: 0.7\n"
            "- entry_schema_version: unknown\n"
        )
        self.assertEqual(entry_schema_version_for_manifest(unknown_schema), "1")

    def test_schema_selection_ignores_unrelated_invalid_routing(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            memory = Path(tmp) / "docs" / "memory"
            manifest = memory / "manifest.md"
            manifest_text = manifest.read_text(encoding="utf-8")
            manifest.write_text(
                manifest_text.replace("- brief.md", "- ../outside.md", 1),
                encoding="utf-8",
            )
            literal = "Status: semantic body"
            entry = (
                "## MC-DEC-20260827-12121212 — Schema 2 body\n\n"
                "Status: active\nScope: project\nEvidence:\n- user-confirmed\n\n"
                f"Decision:\n```{BODY_FENCE_INFO}\n{literal}\n```\n"
            )
            (memory / "decisions.md").write_text(
                "# Decisions\n\n" + entry,
                encoding="utf-8",
            )

            self.assertEqual(entry_schema_version_for_manifest(
                manifest.read_text(encoding="utf-8"),
            ), "2")
            contract = inspect_manifest_contract(
                manifest.read_text(encoding="utf-8"),
            )
            self.assertFalse(contract.valid)
            self.assertIn("Invalid manifest routing", contract.error or "")
            snapshot = build_snapshot(memory, Path(tmp))
            self.assertEqual(snapshot.entry_schema_version, "2")
            self.assertFalse(snapshot.manifest_contract.valid)
            self.assertEqual(snapshot.entries[0].field_bodies["Decision"], literal)
            self.assertNotIn(
                f"Decision:\n```{BODY_FENCE_INFO}",
                snapshot.entries[0].display_text or "",
            )

    def test_schema_1_preserves_manual_wrapper_until_explicit_schema_2_migration(self):
        literal_wrapper = "```memory-custodian-body-v1\nStatus: literal\n```"
        legacy = (
            "## MC-DEC-20260827-aaaaaaaa — Legacy body\n\n"
            "Status: active\nScope: project\nEvidence:\n- user-confirmed\n\n"
            f"Decision:\n{literal_wrapper}\n"
        )
        parsed_legacy = parse_structured_entries(
            Path("decisions.md"), legacy, entry_schema_version="1",
        )[0]
        self.assertEqual(parsed_legacy.field_bodies["Decision"], literal_wrapper)
        self.assertIn(BODY_FENCE_INFO, parsed_legacy.display_text or "")

        migrated, changed = migrate_entry_schema(
            Path("decisions.md"), legacy, from_schema="1", to_schema="2",
        )
        self.assertEqual(changed, 1)
        self.assertIn(f"~~~{BODY_FENCE_INFO}", migrated)
        parsed_current = parse_structured_entries(
            Path("decisions.md"), migrated, entry_schema_version="2",
        )[0]
        self.assertEqual(parsed_current.field_bodies["Decision"], literal_wrapper)
        self.assertIn(literal_wrapper, parsed_current.display_text or "")

    def test_schema_1_decodes_its_legacy_four_space_body_escape_before_migration(self):
        legacy = (
            "## MC-DEC-20260827-cccccccc — Legacy escape\n\n"
            "Status: active\nScope: project\nEvidence:\n- user-confirmed\n\n"
            "Decision:\n    Status: literal\n    - keep this line\n"
        )
        parsed_legacy = parse_structured_entries(
            Path("decisions.md"), legacy, entry_schema_version="1",
        )[0]
        self.assertEqual(
            parsed_legacy.field_bodies["Decision"],
            "Status: literal\n- keep this line",
        )
        migrated, changed = migrate_entry_schema(
            Path("decisions.md"), legacy, from_schema="1", to_schema="2",
        )
        self.assertEqual(changed, 1)
        parsed_current = parse_structured_entries(
            Path("decisions.md"), migrated, entry_schema_version="2",
        )[0]
        self.assertEqual(
            parsed_current.field_bodies["Decision"],
            "Status: literal\n- keep this line",
        )

    def test_schema_migration_keeps_nonformal_unit_separators(self):
        legacy = (
            "# Decisions\n\n"
            "## MC-DEC-20260827-11111111 — First\n\n"
            "Status: active\nScope: project\nEvidence:\n- user-confirmed\n\n"
            "Decision:\n    Status: first\n\n"
            "## Notes\n\n"
            "This non-formal unit must remain unchanged.\n\n"
            "## MC-DEC-20260827-22222222 — Second\n\n"
            "Status: active\nScope: project\nEvidence:\n- user-confirmed\n\n"
            "Decision:\n    Status: second\n"
        )
        migrated, changed = migrate_entry_schema(
            Path("decisions.md"), legacy, from_schema="1", to_schema="2",
        )
        self.assertEqual(changed, 2)
        self.assertIn(
            "```memory-custodian-body-v1\nStatus: first\n```\n\n## Notes",
            migrated,
        )
        self.assertIn("## Notes\n\nThis non-formal unit must remain unchanged.", migrated)
        parsed = parse_structured_entries(
            Path("decisions.md"), migrated, entry_schema_version="2",
        )
        self.assertEqual(
            [entry.field_bodies["Decision"] for entry in parsed],
            ["Status: first", "Status: second"],
        )

    def test_schema_migration_preserves_crlf_body_source_and_nonformal_units(self):
        legacy = (
            "# Decisions\r\n\r\n"
            "## MC-DEC-20260827-abcdef12 — Preserve source\r\n"
            "Status: active\r\n"
            "Scope: project\r\n"
            "Subject: MC-SUBJ-20260827-abcdef12  \r\n"
            "Facet: behavior\r\n"
            "Evidence:\r\n"
            "- user-confirmed\r\n\r\n"
            "Decision:\r\n"
            "    first paragraph  \r\n"
            "\r\n"
            "      continuation indentation\r\n"
            "    Status: literal\r\n\r\n"
            "## Notes\r\n"
            "Non-formal unit text.  \r\n\r\n"
        )
        original_nonformal = "## Notes\r\nNon-formal unit text.  \r\n\r\n"
        legacy_entry = parse_structured_entries(
            Path("decisions.md"), legacy, entry_schema_version="1",
        )[0]
        migrated, changed = migrate_entry_schema(
            Path("decisions.md"), legacy, from_schema="1", to_schema="2",
        )
        self.assertEqual(changed, 1)
        self.assertNotIn("\n", migrated.replace("\r\n", ""))
        self.assertIn("Subject: MC-SUBJ-20260827-abcdef12  \r\n", migrated)
        self.assertIn("Facet: behavior\r\n", migrated)
        self.assertIn(original_nonformal, migrated)
        current_entry = parse_structured_entries(
            Path("decisions.md"), migrated, entry_schema_version="2",
        )[0]
        self.assertEqual(
            current_entry.field_bodies["Decision"],
            legacy_entry.field_bodies["Decision"],
        )
        self.assertIn("first paragraph  ", current_entry.field_bodies["Decision"])
        self.assertIn("\n\n", current_entry.field_bodies["Decision"])
        self.assertIn(
            "      continuation indentation",
            current_entry.field_bodies["Decision"],
        )

    def test_schema_specific_formatter_and_local_overlay_boundary(self):
        body = "Status: literal\n- keep this line"
        self.assertEqual(
            line_safe_markdown_body(body, entry_schema_version="1"),
            "    Status: literal\n    - keep this line",
        )
        self.assertIn(
            f"{BODY_FENCE_INFO}\n{body}",
            line_safe_markdown_body(body, entry_schema_version="2"),
        )
        self.assertEqual(
            line_safe_markdown_body("plain\r\ntext", entry_schema_version="2"),
            "plain\ntext",
        )

        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as state:
            with patch.dict(os.environ, {"XDG_STATE_HOME": state}):
                self.assertEqual(main(["init", "--project-root", root]), 0)
                self.assertEqual(main(["local", "enable", "--project-root", root]), 0)
                self.assertEqual(main(["local", "link", "--project-root", root]), 0)
                memory = Path(root) / "docs" / "memory"
                manifest = memory / "manifest.md"
                project_id = re.search(
                    r"(?m)^- project_id: (\S+)", manifest.read_text(encoding="utf-8"),
                ).group(1)
                local_dir = (
                    Path(state) / "memory-custodian" / "projects" / project_id / "local"
                )
                literal_wrapper = "```memory-custodian-body-v1\nStatus: literal\n```"
                local_entry = (
                    "## MC-PREF-20260827-dddddddd — Legacy local\n\n"
                    "Status: active\nScope: local-user\nEvidence:\n- user-confirmed\n\n"
                    f"Preference:\n{literal_wrapper}\n"
                )
                (local_dir / "preferences.md").write_text(
                    "# Local Preferences\n\n" + local_entry,
                    encoding="utf-8",
                )
                manifest.write_text(
                    manifest.read_text(encoding="utf-8").replace(
                        "entry_schema_version: 2", "entry_schema_version: 1",
                    ),
                    encoding="utf-8",
                )

                overlay = inspect_overlay(
                    Path(root), project_id, entry_schema_version="1",
                )
                self.assertEqual(overlay.status.value, "BOUND")
                self.assertEqual(
                    overlay.captured_modules[0].entries[0].field_bodies["Preference"],
                    literal_wrapper,
                )
                status_code, status, status_error = capture(
                    ["local", "status", "--project-root", root]
                )
                self.assertEqual(status_code, 0, status_error)
                self.assertIn("Local overlay status: BOUND", status)
                self.assertIn("migration to entry schema 2 is available", status)
                with self.assertRaisesRegex(ValueError, "migration to entry schema 2 is available"):
                    add_local_preference(
                        Path(root), project_id, "new local body", ("user-confirmed",),
                        entry_schema_version="1",
                    )

    def test_public_schema_1_project_reports_migration_and_preview_apply_preserves_body(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            memory = Path(tmp) / "docs" / "memory"
            manifest = memory / "manifest.md"
            manifest.write_text(
                manifest.read_text(encoding="utf-8").replace(
                    "entry_schema_version: 2", "entry_schema_version: 1",
                ),
                encoding="utf-8",
            )
            entry_id = "MC-DEC-20260827-bbbbbbbb"
            literal_wrapper = "```memory-custodian-body-v1\nStatus: literal\n```"
            (memory / "decisions.md").write_text(
                "# Decisions\n\n"
                f"## {entry_id} — Legacy wrapper\n\n"
                "Status: active\nScope: project\nEvidence:\n- user-confirmed\n\n"
                f"Decision:\n{literal_wrapper}\n",
                encoding="utf-8",
            )

            status_code, status, _ = capture(["status", "--project-root", tmp])
            self.assertEqual(status_code, 1)
            self.assertIn("entry schema 1", status)
            self.assertIn("migration available to entry schema 2", status)

            check_code, check, _ = capture(["check", "--project-root", tmp])
            self.assertEqual(check_code, 1)
            self.assertIn("migration to entry schema 2 is available", check)

            conflict_code, conflict, conflict_error = capture([
                "check", "--conflicts", "--project-root", tmp,
            ])
            self.assertEqual(conflict_code, 1, conflict + conflict_error)
            self.assertIn("Conflict status: INVALID", conflict)
            self.assertIn("migration to entry schema 2 is available", conflict)

            add_code, _add_output, add_error = capture([
                "add", "Legacy writer must stop", "--type", "decision",
                "--evidence", "user-confirmed", "--project-root", tmp,
            ])
            self.assertEqual(add_code, 2)
            self.assertIn("migration to entry schema 2 is available", add_error)
            promote_code, _promote_output, promote_error = capture([
                "promote", "MC-INBOX-20260827-99999999", "--type", "decision",
                "--evidence", "user-confirmed", "--project-root", tmp,
            ])
            self.assertEqual(promote_code, 2)
            self.assertIn("migration to entry schema 2 is available", promote_error)

            show_code, shown, show_error = capture(["show", entry_id, "--project-root", tmp])
            self.assertEqual(show_code, 0, show_error)
            self.assertIn(literal_wrapper, shown)

            strict_code, strict, _ = capture([
                "read", "--task", "implementation", "--strict-routing",
                "--names-only", "--project-root", tmp,
            ])
            self.assertNotEqual(strict_code, 0)
            self.assertIn("migration to entry schema 2 is available", strict)
            self.assertNotIn("Decision:\nStatus: literal", strict)

            preview_code, preview, preview_error = capture([
                "migrate", "--project-root", tmp,
            ])
            self.assertEqual(preview_code, 0, preview_error)
            self.assertIn("schema 1 bodies", preview)
            plan_id = re.search(r"Plan ID: ([0-9a-f]{16})", preview)
            self.assertIsNotNone(plan_id)
            apply_code, _applied, apply_error = capture([
                "migrate", "--apply", "--confirm-plan", plan_id.group(1),
                "--project-root", tmp,
            ])
            self.assertEqual(apply_code, 0, apply_error)
            self.assertIn("entry_schema_version: 2", manifest.read_text(encoding="utf-8"))
            migrated_entry = parse_structured_entries(
                memory / "decisions.md",
                (memory / "decisions.md").read_text(encoding="utf-8"),
            )[0]
            self.assertEqual(migrated_entry.field_bodies["Decision"], literal_wrapper)

            current_code, current, current_error = capture([
                "show", entry_id, "--project-root", tmp,
            ])
            self.assertEqual(current_code, 0, current_error)
            self.assertIn(literal_wrapper, current)
            self.assertNotIn(f"~~~{BODY_FENCE_INFO}", current)

    def test_init_repair_does_not_flip_schema_without_body_migration(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            manifest = Path(tmp) / "docs" / "memory" / "manifest.md"
            original = manifest.read_text(encoding="utf-8")
            manifest.write_text(
                original.replace("entry_schema_version: 2", "entry_schema_version: 1"),
                encoding="utf-8",
            )
            code, output, error = capture(["init", "--repair", "--project-root", tmp])
            self.assertEqual(code, 2)
            self.assertIn("migration to entry schema 2 is available", error)
            self.assertIn("cannot flip the manifest", error)
            self.assertIn("entry_schema_version: 1", manifest.read_text(encoding="utf-8"))

    def test_bound_local_schema_1_overlay_migrates_with_shared_manifest(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as state:
            with patch.dict(os.environ, {"XDG_STATE_HOME": state}):
                self.assertEqual(main(["init", "--project-root", root]), 0)
                self.assertEqual(main(["local", "enable", "--project-root", root]), 0)
                self.assertEqual(main(["local", "link", "--project-root", root]), 0)
                memory = Path(root) / "docs" / "memory"
                manifest = memory / "manifest.md"
                project_id = re.search(
                    r"(?m)^- project_id: (\S+)", manifest.read_text(encoding="utf-8"),
                ).group(1)
                local_dir = (
                    Path(state) / "memory-custodian" / "projects" / project_id / "local"
                )
                literal_wrapper = "```memory-custodian-body-v1\nStatus: literal\n```"
                local_entry = (
                    "## MC-PREF-20260827-eeeeeeee — Legacy local\n\n"
                    "Status: active\nScope: local-user\nEvidence:\n- user-confirmed\n\n"
                    f"Preference:\n{literal_wrapper}\n"
                )
                local_path = local_dir / "preferences.md"
                local_path.write_text(
                    "# Local Preferences\n\n" + local_entry,
                    encoding="utf-8",
                )
                manifest.write_text(
                    manifest.read_text(encoding="utf-8").replace(
                        "entry_schema_version: 2", "entry_schema_version: 1",
                    ),
                    encoding="utf-8",
                )

                preview_code, preview, preview_error = capture([
                    "migrate", "--project-root", root,
                ])
                self.assertEqual(preview_code, 0, preview_error)
                self.assertIn("bound local Entry files", preview)
                self.assertIn("local/preferences.md", preview)
                plan_id = re.search(r"Plan ID: ([0-9a-f]{16})", preview)
                self.assertIsNotNone(plan_id)
                apply_code, applied, apply_error = capture([
                    "migrate", "--apply", "--confirm-plan", plan_id.group(1),
                    "--project-root", root,
                ])
                self.assertEqual(apply_code, 0, apply_error)
                self.assertIn("local/preferences.md", applied)
                self.assertIn("entry_schema_version: 2", manifest.read_text(encoding="utf-8"))

                migrated_local = local_path.read_text(encoding="utf-8")
                self.assertIn(f"~~~{BODY_FENCE_INFO}", migrated_local)
                overlay = inspect_overlay(Path(root), project_id)
                self.assertEqual(overlay.status.value, "BOUND")
                self.assertEqual(
                    overlay.captured_modules[0].entries[0].field_bodies["Preference"],
                    literal_wrapper,
                )

    def test_bound_local_migration_rolls_back_all_preimages_on_shared_failure(self):
        from memory_custodian import migrate as migrate_module
        from memory_custodian.mutations import apply_mutations as real_apply_mutations

        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as state:
            with patch.dict(os.environ, {"XDG_STATE_HOME": state}):
                self.assertEqual(main(["init", "--project-root", root]), 0)
                self.assertEqual(main(["local", "enable", "--project-root", root]), 0)
                self.assertEqual(main(["local", "link", "--project-root", root]), 0)
                memory = Path(root) / "docs" / "memory"
                manifest = memory / "manifest.md"
                project_id = re.search(
                    r"(?m)^- project_id: (\S+)", manifest.read_text(encoding="utf-8"),
                ).group(1)
                local_path = (
                    Path(state) / "memory-custodian" / "projects" / project_id
                    / "local" / "preferences.md"
                )
                literal_wrapper = "```memory-custodian-body-v1\nStatus: literal\n```"
                shared_entry = (
                    "## MC-DEC-20260827-eeeeeeee — Legacy shared\n\n"
                    "Status: active\nScope: project\nEvidence:\n- user-confirmed\n\n"
                    f"Decision:\n{literal_wrapper}\n"
                )
                local_entry = (
                    "## MC-PREF-20260827-ffffffff — Legacy local\n\n"
                    "Status: active\nScope: local-user\nEvidence:\n- user-confirmed\n\n"
                    f"Preference:\n{literal_wrapper}\n"
                )
                shared_path = memory / "decisions.md"
                # Exercise exact preimage recovery for both roots, including
                # a private module whose CRLF source must not be normalized
                # while the shared manifest remains on schema 1.
                shared_path.write_bytes(("# Decisions\n\n" + shared_entry).encode("utf-8"))
                local_path.write_bytes(("# Local Preferences\n\n" + local_entry).replace("\n", "\r\n").encode("utf-8"))
                manifest.write_text(
                    manifest.read_text(encoding="utf-8").replace(
                        "entry_schema_version: 2", "entry_schema_version: 1",
                    ),
                    encoding="utf-8",
                )
                before_manifest = manifest.read_bytes()
                before_shared = shared_path.read_bytes()
                before_local = local_path.read_bytes()

                preview_code, preview, preview_error = capture([
                    "migrate", "--project-root", root,
                ])
                self.assertEqual(preview_code, 0, preview_error)
                plan_id = re.search(r"Plan ID: ([0-9a-f]{16})", preview).group(1)

                def fail_manifest(mutations):
                    if any(
                        mutation.path.resolve() == manifest.resolve()
                        for mutation in mutations
                    ):
                        raise OSError("injected shared write failure")
                    return real_apply_mutations(mutations)

                with patch.object(
                    migrate_module,
                    "apply_mutations",
                    side_effect=fail_manifest,
                ):
                    apply_code, _applied, apply_error = capture([
                        "migrate", "--apply", "--confirm-plan", plan_id,
                        "--project-root", root,
                    ])
                self.assertNotEqual(apply_code, 0)
                self.assertIn("restored", apply_error)
                self.assertIn("schema 1", apply_error)
                self.assertEqual(manifest.read_bytes(), before_manifest)
                self.assertEqual(shared_path.read_bytes(), before_shared)
                self.assertEqual(local_path.read_bytes(), before_local)
                self.assertIn("entry_schema_version: 1", manifest.read_text(encoding="utf-8"))

                retry_code, retry_preview, retry_error = capture([
                    "migrate", "--project-root", root,
                ])
                self.assertEqual(retry_code, 0, retry_error)
                retry_id = re.search(r"Plan ID: ([0-9a-f]{16})", retry_preview).group(1)
                applied_code, _output, applied_error = capture([
                    "migrate", "--apply", "--confirm-plan", retry_id,
                    "--project-root", root,
                ])
                self.assertEqual(applied_code, 0, applied_error)
                self.assertEqual(
                    parse_structured_entries(
                        shared_path,
                        shared_path.read_text(encoding="utf-8"),
                    )[0].field_bodies["Decision"],
                    literal_wrapper,
                )
                self.assertEqual(
                    inspect_overlay(Path(root), project_id).captured_modules[0]
                    .entries[0].field_bodies["Preference"],
                    literal_wrapper,
                )


if __name__ == "__main__":
    unittest.main()
