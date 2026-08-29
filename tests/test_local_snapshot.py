"""Adversarial local-overlay capture and mutation-lock regression tests."""

from __future__ import annotations

from contextlib import contextmanager, redirect_stderr, redirect_stdout
from io import StringIO
import os
from pathlib import Path
import re
import shutil
import tempfile
import unittest
from unittest.mock import patch

from memory_custodian.entries import render_active_entry
from memory_custodian.main import main
from memory_custodian import local as local_command
from memory_custodian import local_overlay
from memory_custodian import read as read_command


class LocalSnapshotRaceTests(unittest.TestCase):
    def _capture(self, argv: list[str]) -> tuple[int, str, str]:
        output, error = StringIO(), StringIO()
        with redirect_stdout(output), redirect_stderr(error):
            code = main(argv)
        return code, output.getvalue(), error.getvalue()

    def _setup_bound_overlay(self, project_root: str) -> tuple[Path, Path, str]:
        self.assertEqual(main(["init", "--project-root", project_root]), 0)
        self.assertEqual(main(["local", "enable", "--project-root", project_root]), 0)
        self.assertEqual(main(["local", "link", "--project-root", project_root]), 0)
        memory = Path(project_root) / "docs" / "memory"
        project_id = re.search(
            r"(?m)^- project_id: (\S+)",
            (memory / "manifest.md").read_text(encoding="utf-8"),
        ).group(1)
        preferences = (
            Path(os.environ["XDG_STATE_HOME"])
            / "memory-custodian"
            / "projects"
            / project_id
            / "local"
            / "preferences.md"
        )
        return memory, preferences, project_id

    def test_read_uses_captured_local_text_after_replacement(self):
        with tempfile.TemporaryDirectory() as project_root, tempfile.TemporaryDirectory() as state:
            with patch.dict(os.environ, {"XDG_STATE_HOME": state}):
                memory, preferences, _project_id = self._setup_bound_overlay(project_root)
                self.assertEqual(main([
                    "local", "add", "Captured local text.",
                    "--type", "preference", "--evidence", "user-confirmed",
                    "--project-root", project_root,
                ]), 0)
                original = preferences.read_text(encoding="utf-8")
                shared_id = "MC-CON-20260827-deadbeef"
                subject_id = "MC-SUBJ-20260827-cafebabe"
                (memory / "subjects.md").write_text(
                    "# Subject Registry\n\n"
                    f"## {subject_id} — Shared race fixture\n\n"
                    "Status: active\nKind: concept\nCanonical-Ref: feature:shared-race\n"
                    "Evidence:\n- user-confirmed\n\nAliases:\n- shared race\n",
                    encoding="utf-8",
                )
                shared = render_active_entry(
                    "constraint", shared_id, "Shared collision", "Shared body.",
                    None, "project", ("user-confirmed",),
                    subject=subject_id, facet="behavior",
                )
                shared_path = memory / "constraints.md"
                shared_path.write_text(
                    shared_path.read_text(encoding="utf-8") + "\n" + shared + "\n",
                    encoding="utf-8",
                )
                replacement = render_active_entry(
                    "constraint", shared_id, "Replaced local", "REPLACED_LOCAL_BODY",
                    None, "local-user", ("user-confirmed",),
                )

                original_inspect = read_command.inspect_overlay

                def inspect_then_replace(*args, **kwargs):
                    overlay = original_inspect(*args, **kwargs)
                    preferences.write_text(
                        "# Local Preferences\n\n" + replacement + "\n",
                        encoding="utf-8",
                    )
                    return overlay

                calls: list[Path] = []
                original_read = local_overlay.read_local_private_file

                def tracked_read(path: Path) -> str:
                    calls.append(path)
                    return original_read(path)

                with patch.object(read_command, "inspect_overlay", side_effect=inspect_then_replace), \
                    patch.object(local_overlay, "read_local_private_file", side_effect=tracked_read):
                    code, output, error = self._capture([
                        "read", "--task", "general", "--strict-routing",
                        "--project-root", project_root,
                    ])

                self.assertEqual(code, 0, output + error)
                self.assertIn("Captured local text.", output)
                self.assertNotIn("REPLACED_LOCAL_BODY", output)
                self.assertIn("Local overlay status: BOUND", output)
                self.assertEqual(
                    sum(path == preferences for path in calls),
                    1,
                    "strict read must not reopen a module after inspection",
                )
                self.assertNotEqual(preferences.read_text(encoding="utf-8"), original)
                self.assertIn(shared_id, output)
                self.assertNotIn("Replaced local", output)

    def test_local_add_rebuilds_shared_ids_after_lock_acquisition(self):
        with tempfile.TemporaryDirectory() as project_root, tempfile.TemporaryDirectory() as state:
            with patch.dict(os.environ, {"XDG_STATE_HOME": state}):
                memory, preferences, _project_id = self._setup_bound_overlay(project_root)
                before = preferences.read_text(encoding="utf-8")
                shared_id = "MC-CON-20260827-feedface"
                shared_path = memory / "constraints.md"
                shared_entry = render_active_entry(
                    "constraint", shared_id, "Created while waiting", "Shared first.",
                    None, "project", ("user-confirmed",),
                )
                real_guard = local_command.project_mutation_guard

                @contextmanager
                def guard_then_create_shared(*args, **kwargs):
                    with real_guard(*args, **kwargs) as token:
                        shared_path.write_text(
                            shared_path.read_text(encoding="utf-8")
                            + "\n"
                            + shared_entry
                            + "\n",
                            encoding="utf-8",
                        )
                        yield token

                with patch.object(local_command, "project_mutation_guard", guard_then_create_shared), \
                    patch.object(local_overlay, "generate_entry_id", return_value=shared_id):
                    code, output, error = self._capture([
                        "local", "add", "Must not duplicate.",
                        "--type", "preference", "--evidence", "user-confirmed",
                        "--project-root", project_root,
                    ])

                self.assertEqual(code, 2, output + error)
                self.assertIn("collision", error.lower())
                self.assertNotIn("Must not duplicate.", preferences.read_text(encoding="utf-8"))
                self.assertEqual(
                    len(re.findall(re.escape(shared_id), shared_path.read_text(encoding="utf-8"))),
                    1,
                )
                self.assertEqual(
                    len(re.findall(re.escape(shared_id), preferences.read_text(encoding="utf-8"))),
                    0,
                )
                self.assertEqual(before, preferences.read_text(encoding="utf-8"))
                status_code, status_output, status_error = self._capture([
                    "local", "status", "--project-root", project_root,
                ])
                self.assertEqual(status_code, 0, status_output + status_error)
                self.assertIn("Local overlay status: BOUND", status_output)

    def test_local_link_uses_one_captured_overlay_when_later_read_would_change_scope(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second, tempfile.TemporaryDirectory() as state:
            with patch.dict(os.environ, {"XDG_STATE_HOME": state}):
                _memory, preferences, _project_id = self._setup_bound_overlay(first)
                self.assertEqual(main([
                    "local", "add", "Keep the captured preference.",
                    "--type", "preference", "--evidence", "user-confirmed",
                    "--project-root", first,
                ]), 0)
                shutil.copytree(Path(first) / "docs", Path(second) / "docs")
                original = preferences.read_text(encoding="utf-8")
                invalid = original.replace(
                    "Scope: local-user", "Scope: project", 1,
                )
                original_read = local_overlay.read_local_private_file
                module_reads = 0

                def race_read(path: Path) -> str:
                    nonlocal module_reads
                    value = original_read(path)
                    if path == preferences:
                        module_reads += 1
                        if module_reads == 2:
                            # This is the edit that used to land between the
                            # schema pass and the final ID-only pass.
                            preferences.write_text(invalid, encoding="utf-8")
                    return value

                with patch.object(local_overlay, "read_local_private_file", side_effect=race_read):
                    code, output, error = self._capture([
                        "local", "link", "--project-root", second,
                    ])

                self.assertEqual(code, 0, output + error)
                self.assertIn("linked", output)
                self.assertEqual(
                    module_reads,
                    1,
                    "local link must capture and validate each module once",
                )
                self.assertEqual(
                    preferences.read_text(encoding="utf-8"),
                    original,
                    "the later-read race must never be reached after capture",
                )
                binding = preferences.parents[1] / "bindings.json"
                self.assertIn(str(Path(second).resolve()), binding.read_text(encoding="utf-8"))

    def test_initial_enable_and_link_capture_generated_overlay_once(self):
        for command in ("enable", "link"):
            with self.subTest(command=command), tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as state:
                with patch.dict(os.environ, {"XDG_STATE_HOME": state}):
                    self.assertEqual(main(["init", "--project-root", root]), 0)
                    memory = Path(root) / "docs" / "memory"
                    project_id = re.search(
                        r"(?m)^- project_id: (\S+)",
                        (memory / "manifest.md").read_text(encoding="utf-8"),
                    ).group(1)
                    preferences = (
                        Path(state)
                        / "memory-custodian"
                        / "projects"
                        / project_id
                        / "local"
                        / "preferences.md"
                    )
                    original_read = local_overlay.read_local_private_file
                    module_reads = 0

                    def tracked_read(path: Path) -> str:
                        nonlocal module_reads
                        value = original_read(path)
                        if path == preferences:
                            module_reads += 1
                        return value

                    with patch.object(local_overlay, "read_local_private_file", side_effect=tracked_read):
                        code, output, error = self._capture([
                            "local", command, "--project-root", root,
                        ])

                    self.assertEqual(code, 0, output + error)
                    self.assertEqual(
                        module_reads,
                        1,
                        "initial local mutation must capture generated modules once",
                    )
                    self.assertIn(
                        "enabled" if command == "enable" else "linked",
                        output,
                    )
                    if command == "link":
                        self.assertTrue((preferences.parents[1] / "bindings.json").exists())

    def test_post_create_scope_corruption_blocks_enable_and_link(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as state:
            with patch.dict(os.environ, {"XDG_STATE_HOME": state}):
                self.assertEqual(main(["init", "--project-root", root]), 0)
                memory = Path(root) / "docs" / "memory"
                project_id = re.search(
                    r"(?m)^- project_id: (\S+)",
                    (memory / "manifest.md").read_text(encoding="utf-8"),
                ).group(1)
                project_state = (
                    Path(state) / "memory-custodian" / "projects" / project_id
                )
                binding = project_state / "bindings.json"
                real_write = local_overlay.write_private_file

                def write_then_corrupt(path: Path, text: str) -> None:
                    real_write(path, text)
                    if path.name == "preferences.md":
                        path.write_text(
                            "# Local Preferences\n\n"
                            "## MC-PREF-20260828-badc0de0 — Generated race\n\n"
                            "Status: active\nScope: project\n"
                            "Evidence:\n- user-confirmed\n\n"
                            "Preference:\nInjected invalid scope.\n",
                            encoding="utf-8",
                        )

                with patch.object(
                    local_overlay,
                    "write_private_file",
                    side_effect=write_then_corrupt,
                ):
                    enable_code, enable_output, enable_error = self._capture([
                        "local", "enable", "--project-root", root,
                    ])

                self.assertEqual(enable_code, 2, enable_output + enable_error)
                self.assertNotIn("enabled", enable_output.casefold())
                self.assertFalse(binding.exists())

                link_code, link_output, link_error = self._capture([
                    "local", "link", "--project-root", root,
                ])
                self.assertEqual(link_code, 2, link_output + link_error)
                self.assertNotIn("linked", link_output.casefold())
                self.assertFalse(binding.exists())


if __name__ == "__main__":
    unittest.main()
