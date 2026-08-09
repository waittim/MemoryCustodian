"""Release-gate coverage for Protocol 0.7 audit findings."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from memory_custodian.conflicts import analyze_conflicts
from memory_custodian.context import ContextRoutingResult
from memory_custodian.entries import render_active_entry, render_candidate_entry
from memory_custodian.main import main
from memory_custodian.routes import RouteReason, RoutingCompleteness


def capture(argv: list[str]) -> tuple[int, str, str]:
    out, err = StringIO(), StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


def git(root: str, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, text=True, capture_output=True, check=True,
    )
    return result.stdout.strip()


def initialize_git_project(root: str) -> Path:
    with redirect_stdout(StringIO()):
        assert main(["init", "--project-root", root]) == 0
    memory = Path(root) / "docs" / "memory"
    (memory / "brief.md").write_text(
        "# Project Brief\n\nPurpose:\nProtocol 0.7 release tests.\n",
        encoding="utf-8",
    )
    git(root, "init", "-q")
    git(root, "config", "user.name", "MemoryCustodian Tests")
    git(root, "config", "user.email", "tests@example.invalid")
    git(root, "add", ".")
    git(root, "commit", "-qm", "base")
    return memory


def subject_unit(subject_id: str, title: str, canonical_ref: str = "") -> str:
    canonical = f"Canonical-Ref: {canonical_ref}\n" if canonical_ref else ""
    return (
        f"## {subject_id} — {title}\n\n"
        f"Status: active\nKind: concept\n{canonical}"
        "Evidence:\n- user-confirmed\n\n"
        f"Aliases:\n- {title.casefold()}\n"
    )


class RoutingAndQualityReleaseTests(unittest.TestCase):
    def test_ambiguous_result_surface_remains_reserved_and_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            with redirect_stdout(StringIO()):
                self.assertEqual(main(["init", "--project-root", tmp]), 0)
            result = ContextRoutingResult(
                "implementation",
                "implementation",
                (),
                (),
                (),
                (),
                RoutingCompleteness.AMBIGUOUS,
                (),
                (),
                (),
                (f"{RouteReason.AMBIGUOUS.value}: reserved policy ambiguity",),
                ("reserved-policy-ambiguity",),
            )
            with patch("memory_custodian.read.route_context", return_value=result):
                code, output, error = capture([
                    "read", "--task", "implementation", "--names-only",
                    "--project-root", tmp,
                ])
                self.assertEqual(code, 1, output + error)
                self.assertIn("Routing completeness: AMBIGUOUS", output)
                self.assertIn("MC-ROUTE-AMBIGUOUS", output)
                code, output, error = capture([
                    "read", "--task", "implementation", "--strict-routing",
                    "--names-only", "--project-root", tmp,
                ])
                self.assertEqual(code, 2, output + error)
                self.assertIn("Context pack not approved", output)

    def test_manifest_lexical_contract_handles_code_spans_and_fence_info(self):
        with tempfile.TemporaryDirectory() as tmp:
            with redirect_stdout(StringIO()):
                self.assertEqual(main(["init", "--project-root", tmp]), 0)
            manifest = Path(tmp) / "docs/memory/manifest.md"
            original = manifest.read_text(encoding="utf-8")

            manifest.write_text("`<!--`\n\n" + original, encoding="utf-8")
            code, output, error = capture([
                "read", "--task", "implementation", "--strict-routing",
                "--names-only", "--project-root", tmp,
            ])
            self.assertEqual(code, 0, output + error)
            self.assertIn("Routing completeness: COMPLETE", output)

            manifest.write_text(
                original.rstrip()
                + "\n\n~~~`legal tilde info\n"
                + "## MemoryCustodian Protocol\n- protocol_version: 0.6\n~~~\n",
                encoding="utf-8",
            )
            code, output, error = capture([
                "check", "--routing", "--project-root", tmp,
            ])
            self.assertEqual(code, 0, output + error)

            manifest.write_text(
                "```python`invalid\n" + original + "\n```\n",
                encoding="utf-8",
            )
            for command in (
                ("read", "--task", "implementation", "--strict-routing", "--names-only"),
                ("check", "--routing"),
                ("enable", "preferences"),
            ):
                command_code, command_output, command_error = capture([
                    *command, "--project-root", tmp,
                ])
                self.assertNotEqual(
                    command_code,
                    0,
                    command_output + command_error,
                )
                self.assertIn(
                    "must not contain backticks",
                    command_output + command_error,
                )
            self.assertFalse((Path(tmp) / "docs/memory/preferences.md").exists())

    def test_migration_rejects_unparsed_and_escaping_optional_operands_before_seed(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as state:
            with redirect_stdout(StringIO()):
                self.assertEqual(main(["init", "--project-root", tmp]), 0)
            memory = Path(tmp) / "docs/memory"
            manifest = memory / "manifest.md"
            original = manifest.read_text(encoding="utf-8").replace(
                "- protocol_version: 0.7",
                "- protocol_version: 0.6",
                1,
            )
            outside = Path(tmp) / "outside.md"
            outside.write_text(
                "# Outside\n\n## Legacy\nDecision:\nDo not touch.\n",
                encoding="utf-8",
            )
            malicious = original.replace(
                "## Optional module index\n",
                "## Optional module index\n\n"
                "- `areas/../../../outside.md`\n"
                "  - activation: path\n"
                "  - paths: `src/**`\n",
                1,
            )
            manifest.write_text(malicious, encoding="utf-8")
            before = outside.read_bytes()
            with patch.dict(os.environ, {"XDG_STATE_HOME": state}):
                code, output, error = capture(["migrate", "--project-root", tmp])
            self.assertEqual(code, 2, output + error)
            self.assertNotIn("Plan ID:", output)
            self.assertIn("outside a canonical subsection", error)
            self.assertEqual(outside.read_bytes(), before)
            self.assertEqual(tuple(Path(state).rglob("*")), ())

            manifest.write_text(
                original.replace(
                    "### Enabled areas\n- None enabled.",
                    "### Enabled areas\n"
                    "- `areas/link.md`\n"
                    "  - activation: path\n"
                    "  - paths: `src/**`",
                ),
                encoding="utf-8",
            )
            (memory / "areas").mkdir(exist_ok=True)
            (memory / "areas/link.md").symlink_to(outside)
            with patch.dict(os.environ, {"XDG_STATE_HOME": state}):
                code, output, error = capture(["migrate", "--project-root", tmp])
            self.assertEqual(code, 2, output + error)
            self.assertNotIn("Plan ID:", output)
            self.assertIn("escapes the managed memory directory", error)
            self.assertEqual(tuple(Path(state).rglob("*")), ())

    @unittest.skipIf(os.name == "nt", "POSIX symlink semantics")
    def test_local_overlay_rejects_symlinked_project_state_ancestor(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as state, tempfile.TemporaryDirectory() as external:
            with patch.dict(os.environ, {"XDG_STATE_HOME": state}):
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["init", "--project-root", tmp]), 0)
                    self.assertEqual(main(["local", "enable", "--project-root", tmp]), 0)
                    self.assertEqual(main(["local", "link", "--project-root", tmp]), 0)
                    self.assertEqual(main([
                        "local", "add", "Ancestor symlink marker.",
                        "--type", "preference", "--evidence", "user-confirmed",
                        "--project-root", tmp,
                    ]), 0)
                manifest = Path(tmp) / "docs/memory/manifest.md"
                project_id = re.search(
                    r"(?m)^- project_id: (\S+)",
                    manifest.read_text(encoding="utf-8"),
                ).group(1)
                project_state = (
                    Path(state) / "memory-custodian/projects" / project_id
                )
                external_state = Path(external) / project_id
                shutil.move(project_state, external_state)
                project_state.symlink_to(external_state, target_is_directory=True)

                status_code, status, status_error = capture([
                    "local", "status", "--project-root", tmp,
                ])
                self.assertEqual(status_code, 0, status_error)
                self.assertIn("Local overlay status: REVIEW", status)
                self.assertIn("Unsafe local overlay project directory", status)

                read_code, read_output, read_error = capture([
                    "read", "--task", "preferences", "--project-root", tmp,
                ])
                self.assertEqual(read_code, 0, read_error)
                self.assertNotIn("Ancestor symlink marker.", read_output)
                self.assertNotIn("Local overlay status: BOUND", read_output)

                reset_code, reset, reset_error = capture([
                    "local", "reset", "--project-root", tmp,
                ])
                self.assertEqual(reset_code, 0, reset_error)
                self.assertNotIn("Blockers:\n- none", reset)
                self.assertIn("Unsafe local overlay", reset)

    @unittest.skipIf(os.name == "nt", "POSIX symlink and mode semantics")
    def test_local_overlay_root_and_modes_fail_closed_before_loading(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as state, tempfile.TemporaryDirectory() as external:
            with patch.dict(os.environ, {"XDG_STATE_HOME": state}):
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["init", "--project-root", tmp]), 0)
                    self.assertEqual(main(["local", "enable", "--project-root", tmp]), 0)
                    self.assertEqual(main(["local", "link", "--project-root", tmp]), 0)
                    self.assertEqual(main([
                        "local", "add", "Overlay boundary marker.",
                        "--type", "preference", "--evidence", "user-confirmed",
                        "--project-root", tmp,
                    ]), 0)
                manifest = Path(tmp) / "docs/memory/manifest.md"
                project_id = re.search(
                    r"(?m)^- project_id: (\S+)", manifest.read_text(encoding="utf-8"),
                ).group(1)
                project_state = Path(state) / "memory-custodian/projects" / project_id
                overlay = project_state / "local"

                external_overlay = Path(external) / "local"
                shutil.move(overlay, external_overlay)
                overlay.symlink_to(external_overlay, target_is_directory=True)
                code, status, error = capture(["local", "status", "--project-root", tmp])
                self.assertEqual(code, 0, error)
                self.assertIn("Local overlay status: REVIEW", status)
                code, output, error = capture([
                    "read", "--task", "preferences", "--project-root", tmp,
                ])
                self.assertEqual(code, 0, error)
                self.assertNotIn("Overlay boundary marker.", output)
                overlay.unlink()
                shutil.move(external_overlay, overlay)

                overlay.chmod(0o755)
                code, status, error = capture(["local", "status", "--project-root", tmp])
                self.assertEqual(code, 0, error)
                self.assertIn("mode 0700", status)
                code, reset, error = capture(["local", "reset", "--project-root", tmp])
                self.assertEqual(code, 0, error)
                self.assertNotIn("Blockers:\n- none", reset)
                overlay.chmod(0o700)

                preferences = overlay / "preferences.md"
                preferences.chmod(0o644)
                code, status, error = capture(["local", "status", "--project-root", tmp])
                self.assertEqual(code, 0, error)
                self.assertIn("Local overlay status: REVIEW", status)
                code, reset, error = capture(["local", "reset", "--project-root", tmp])
                self.assertEqual(code, 0, error)
                self.assertIn("mode 0600", reset)
                preferences.chmod(0o600)

                profiles = overlay / "profiles"
                profiles.chmod(0o755)
                code, status, error = capture(["local", "status", "--project-root", tmp])
                self.assertEqual(code, 0, error)
                self.assertIn("Local overlay status: REVIEW", status)
                self.assertIn("mode 0700", status)

    def test_local_overlay_metadata_and_binding_identity_are_unique(self):
        mutations = (
            lambda text, project_id: text.replace(
                "- local_overlay_schema_version: 1",
                "- local_overlay_schema_version: 1\n- local_overlay_schema_version: 2",
                1,
            ),
            lambda text, project_id: text.replace(
                f"- project_id: {project_id}",
                f"- project_id: {project_id}\n- project_id: 00000000-0000-4000-8000-000000000000",
                1,
            ),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate), tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as state:
                with patch.dict(os.environ, {"XDG_STATE_HOME": state}):
                    with redirect_stdout(StringIO()):
                        self.assertEqual(main(["init", "--project-root", tmp]), 0)
                        self.assertEqual(main(["local", "enable", "--project-root", tmp]), 0)
                        self.assertEqual(main(["local", "link", "--project-root", tmp]), 0)
                        self.assertEqual(main([
                            "local", "add", "Corrupt metadata marker.",
                            "--type", "preference", "--evidence", "user-confirmed",
                            "--project-root", tmp,
                        ]), 0)
                    shared = Path(tmp) / "docs/memory/manifest.md"
                    project_id = re.search(
                        r"(?m)^- project_id: (\S+)", shared.read_text(encoding="utf-8"),
                    ).group(1)
                    local_manifest = Path(state) / "memory-custodian/projects" / project_id / "local/manifest.md"
                    local_manifest.write_text(
                        mutate(local_manifest.read_text(encoding="utf-8"), project_id),
                        encoding="utf-8",
                    )
                    code, status, error = capture(["local", "status", "--project-root", tmp])
                    self.assertEqual(code, 0, error)
                    self.assertIn("Local overlay status: REVIEW", status)
                    code, output, error = capture([
                        "read", "--task", "preferences", "--project-root", tmp,
                    ])
                    self.assertEqual(code, 0, error)
                    self.assertNotIn("Corrupt metadata marker.", output)

        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as state:
            with patch.dict(os.environ, {"XDG_STATE_HOME": state}):
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["init", "--project-root", tmp]), 0)
                    self.assertEqual(main(["local", "enable", "--project-root", tmp]), 0)
                    self.assertEqual(main(["local", "link", "--project-root", tmp]), 0)
                    self.assertEqual(main([
                        "local", "add", "Mismatched binding marker.",
                        "--type", "preference", "--evidence", "user-confirmed",
                        "--project-root", tmp,
                    ]), 0)
                shared = Path(tmp) / "docs/memory/manifest.md"
                project_id = re.search(
                    r"(?m)^- project_id: (\S+)", shared.read_text(encoding="utf-8"),
                ).group(1)
                binding = Path(state) / "memory-custodian/projects" / project_id / "bindings.json"
                payload = json.loads(binding.read_text(encoding="utf-8"))
                payload["project_id"] = "00000000-0000-4000-8000-000000000000"
                binding.write_text(json.dumps(payload), encoding="utf-8")
                code, status, error = capture(["local", "status", "--project-root", tmp])
                self.assertEqual(code, 0, error)
                self.assertIn("Local overlay status: REVIEW", status)
                code, output, error = capture([
                    "read", "--task", "preferences", "--project-root", tmp,
                ])
                self.assertEqual(code, 0, error)
                self.assertNotIn("Mismatched binding marker.", output)

    def test_multi_root_review_blocks_writes_and_explicit_indexing(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second, tempfile.TemporaryDirectory() as state:
            with patch.dict(os.environ, {"XDG_STATE_HOME": state}):
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["init", "--project-root", first]), 0)
                    self.assertEqual(main(["local", "enable", "--project-root", first]), 0)
                    self.assertEqual(main(["local", "link", "--project-root", first]), 0)
                code, added, error = capture([
                    "local", "add", "Original multi-root marker.",
                    "--type", "preference", "--evidence", "user-confirmed",
                    "--project-root", first,
                ])
                self.assertEqual(code, 0, error)
                entry_id = re.search(r"MC-PREF-\d{8}-[0-9a-f]{8}", added).group(0)
                shutil.copytree(Path(first) / "docs", Path(second) / "docs")
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["local", "link", "--project-root", second]), 0)

                code, status, error = capture(["local", "status", "--project-root", first])
                self.assertEqual(code, 0, error)
                self.assertIn("Local overlay status: REVIEW", status)
                code, output, error = capture([
                    "read", "--task", "preferences", "--project-root", first,
                ])
                self.assertEqual(code, 0, error)
                self.assertIn("Local overlay status: REVIEW", output)
                self.assertNotIn("Original multi-root marker.", output)
                code, output, error = capture([
                    "local", "add", "Forbidden multi-root write.",
                    "--type", "preference", "--evidence", "user-confirmed",
                    "--project-root", first,
                ])
                self.assertEqual(code, 2, output + error)
                self.assertIn("requires review before writes", error)
                for command in (("list", "--local"), ("show", entry_id, "--local")):
                    code, output, error = capture([*command, "--project-root", second])
                    self.assertEqual(code, 2, output + error)
                    self.assertIn("requires review", error)
                    self.assertNotIn("Original multi-root marker.", output)

    def test_missing_local_scaffold_and_indented_metadata_are_corrupt(self):
        mutations = (
            lambda directory, project_id: (directory / "preferences.md").unlink(),
            lambda directory, project_id: (directory / "profiles").rmdir(),
            lambda directory, project_id: (directory / "manifest.md").write_text(
                (directory / "manifest.md").read_text(encoding="utf-8").replace(
                    "- preferences.md\n", "", 1,
                ),
                encoding="utf-8",
            ),
            lambda directory, project_id: (directory / "manifest.md").write_text(
                (directory / "manifest.md").read_text(encoding="utf-8").replace(
                    f"- project_id: {project_id}",
                    f"- project_id: {project_id}\n  - project_id: 00000000-0000-4000-8000-000000000000",
                    1,
                ),
                encoding="utf-8",
            ),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate), tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as state:
                with patch.dict(os.environ, {"XDG_STATE_HOME": state}):
                    with redirect_stdout(StringIO()):
                        self.assertEqual(main(["init", "--project-root", tmp]), 0)
                        self.assertEqual(main(["local", "enable", "--project-root", tmp]), 0)
                        self.assertEqual(main(["local", "link", "--project-root", tmp]), 0)
                    shared = Path(tmp) / "docs/memory/manifest.md"
                    project_id = re.search(
                        r"(?m)^- project_id: (\S+)", shared.read_text(encoding="utf-8"),
                    ).group(1)
                    directory = Path(state) / "memory-custodian/projects" / project_id / "local"
                    mutate(directory, project_id)
                    code, status, error = capture(["local", "status", "--project-root", tmp])
                    self.assertEqual(code, 0, error)
                    self.assertIn("Local overlay status: REVIEW", status)

    def test_bindings_reject_duplicate_json_keys(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as state:
            with patch.dict(os.environ, {"XDG_STATE_HOME": state}):
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["init", "--project-root", tmp]), 0)
                    self.assertEqual(main(["local", "enable", "--project-root", tmp]), 0)
                    self.assertEqual(main(["local", "link", "--project-root", tmp]), 0)
                shared = Path(tmp) / "docs/memory/manifest.md"
                project_id = re.search(
                    r"(?m)^- project_id: (\S+)", shared.read_text(encoding="utf-8"),
                ).group(1)
                binding = Path(state) / "memory-custodian/projects" / project_id / "bindings.json"
                binding.write_text(
                    "{\n"
                    '  "project_id": "wrong",\n'
                    f'  "project_id": "{project_id}",\n'
                    f'  "roots": [{json.dumps(str(Path(tmp).resolve()))}]\n'
                    "}\n",
                    encoding="utf-8",
                )
                code, status, error = capture(["local", "status", "--project-root", tmp])
                self.assertEqual(code, 0, error)
                self.assertIn("Local overlay status: REVIEW", status)
                self.assertIn("corrupt", status)

    def test_enable_and_link_reject_existing_corrupt_overlay(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second, tempfile.TemporaryDirectory() as state:
            with patch.dict(os.environ, {"XDG_STATE_HOME": state}):
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["init", "--project-root", first]), 0)
                    self.assertEqual(main(["local", "enable", "--project-root", first]), 0)
                    self.assertEqual(main(["local", "link", "--project-root", first]), 0)
                shutil.copytree(Path(first) / "docs", Path(second) / "docs")
                shared = Path(first) / "docs/memory/manifest.md"
                project_id = re.search(
                    r"(?m)^- project_id: (\S+)", shared.read_text(encoding="utf-8"),
                ).group(1)
                project_state = Path(state) / "memory-custodian/projects" / project_id
                local_manifest = project_state / "local/manifest.md"
                local_manifest.write_text("# corrupt\n", encoding="utf-8")
                binding = project_state / "bindings.json"
                before = binding.read_bytes()
                for command, root in ((('local', 'enable'), first), (('local', 'link'), second)):
                    code, output, error = capture([*command, "--project-root", root])
                    self.assertEqual(code, 2, output + error)
                    self.assertNotIn("enabled", output.casefold())
                    self.assertNotIn("linked", output.casefold())
                self.assertEqual(binding.read_bytes(), before)

    @unittest.skipIf(os.name == "nt", "POSIX symlink semantics")
    def test_invalid_overlay_state_never_scans_relative_sentinel(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as state, tempfile.TemporaryDirectory() as external, tempfile.TemporaryDirectory() as cwd:
            with patch.dict(os.environ, {"XDG_STATE_HOME": state}):
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["init", "--project-root", tmp]), 0)
                    self.assertEqual(main(["local", "enable", "--project-root", tmp]), 0)
                    self.assertEqual(main(["local", "link", "--project-root", tmp]), 0)
                shared = Path(tmp) / "docs/memory/manifest.md"
                project_id = re.search(
                    r"(?m)^- project_id: (\S+)", shared.read_text(encoding="utf-8"),
                ).group(1)
                project_state = Path(state) / "memory-custodian/projects" / project_id
                external_state = Path(external) / project_id
                shutil.move(project_state, external_state)
                project_state.symlink_to(external_state, target_is_directory=True)
                collision = Path(cwd) / "__invalid_local_overlay_state__"
                collision.mkdir()
                marker = collision / "unrelated.txt"
                marker.write_text("first", encoding="utf-8")
                previous = Path.cwd()
                try:
                    os.chdir(cwd)
                    _code, first, _error = capture(["local", "reset", "--project-root", tmp])
                    marker.write_text("second", encoding="utf-8")
                    _code, second, _error = capture(["local", "reset", "--project-root", tmp])
                finally:
                    os.chdir(previous)
                self.assertEqual(
                    re.search(r"Plan ID: ([0-9a-f]{16})", first).group(1),
                    re.search(r"Plan ID: ([0-9a-f]{16})", second).group(1),
                )

    @unittest.skipIf(os.name == "nt", "POSIX symlink semantics")
    def test_migration_normalizes_symlink_loops_and_preserves_prose_preamble(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as state:
            with redirect_stdout(StringIO()):
                self.assertEqual(main(["init", "--project-root", tmp]), 0)
            memory = Path(tmp) / "docs/memory"
            manifest = memory / "manifest.md"
            original = manifest.read_text(encoding="utf-8").replace(
                "- protocol_version: 0.7", "- protocol_version: 0.6", 1,
            )
            prose = original.replace(
                "## Optional module index\n",
                "## Optional module index\n\nMigration notes:\n- Human-readable migration note.\n",
                1,
            )
            manifest.write_text(prose, encoding="utf-8")
            with patch.dict(os.environ, {"XDG_STATE_HOME": state}):
                code, output, error = capture(["migrate", "--project-root", tmp])
            self.assertEqual(code, 0, output + error)
            self.assertIn("Plan ID:", output)

            manifest.write_text(
                original.replace(
                    "### Enabled areas\n- None enabled.",
                    "### Enabled areas\n- `areas/loop.md`\n"
                    "  - activation: path\n  - paths: `src/**`",
                    1,
                ),
                encoding="utf-8",
            )
            (memory / "areas").mkdir(exist_ok=True)
            loop = memory / "areas/loop.md"
            loop.symlink_to(loop)
            with patch.dict(os.environ, {"XDG_STATE_HOME": state}):
                code, output, error = capture(["migrate", "--project-root", tmp])
            self.assertEqual(code, 2, output + error)
            self.assertNotIn("Traceback", error)
            self.assertIn("cannot be safely resolved", error)

    def test_optional_and_task_topology_fail_closed(self):
        cases = (
            (
                lambda text: text.replace(
                    "### Enabled profiles",
                    "### Enabled rules\n- None enabled.\n\n### Enabled profiles",
                    1,
                ),
                "duplicate optional module subsection",
            ),
            (
                lambda text: text.replace(
                    "### Enabled rules\n- None enabled.",
                    "### Enabled rules\n- None enabled.\n"
                    "- `rules/output.md`\n  - activation: explicit-only",
                    1,
                ),
                "contradictory optional module sentinel",
            ),
            (
                lambda text: text.replace(
                    "### Planning / architecture / refactoring",
                    "### Unknown task route\nLoad:\n- decisions.md\n\n"
                    "### Planning / architecture / refactoring",
                    1,
                ),
                "unknown H3 route heading",
            ),
            (
                lambda text: text.replace(
                    "## Optional module index\n",
                    "## Optional module index\n\n"
                    "- `rules/output.md`\n  - activation: explicit-only\n",
                    1,
                ),
                "outside a canonical subsection",
            ),
        )
        for mutate, expected in cases:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as tmp:
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["init", "--project-root", tmp]), 0)
                manifest = Path(tmp) / "docs/memory/manifest.md"
                manifest.write_text(
                    mutate(manifest.read_text(encoding="utf-8")),
                    encoding="utf-8",
                )
                code, output, error = capture([
                    "check", "--routing", "--project-root", tmp,
                ])
                self.assertEqual(code, 1, output + error)
                self.assertIn(expected, output + error)

    def test_local_reset_binds_directories_and_blocks_unreadable_inventory(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as state:
            with patch.dict(os.environ, {"XDG_STATE_HOME": state}):
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["init", "--project-root", tmp]), 0)
                    self.assertEqual(main(["local", "enable", "--project-root", tmp]), 0)
                    self.assertEqual(main(["local", "link", "--project-root", tmp]), 0)
                manifest = Path(tmp) / "docs/memory/manifest.md"
                project_id = re.search(
                    r"(?m)^- project_id: (\S+)",
                    manifest.read_text(encoding="utf-8"),
                ).group(1)
                overlay = (
                    Path(state) / "memory-custodian/projects" / project_id / "local"
                )
                _code, baseline, _error = capture([
                    "local", "reset", "--project-root", tmp,
                ])
                baseline_plan = re.search(r"Plan ID: ([0-9a-f]{16})", baseline).group(1)

                empty = overlay / "empty"
                empty.mkdir()
                _code, with_empty, _error = capture([
                    "local", "reset", "--project-root", tmp,
                ])
                empty_plan = re.search(r"Plan ID: ([0-9a-f]{16})", with_empty).group(1)
                self.assertNotEqual(baseline_plan, empty_plan)

                locked = overlay / "locked"
                locked.mkdir()
                (locked / "state.bin").write_bytes(b"state")
                locked.chmod(0)
                try:
                    code, output, error = capture([
                        "local", "reset", "--project-root", tmp,
                    ])
                    self.assertEqual(code, 0, error)
                    self.assertNotIn("Blockers:\n- none", output)
                    self.assertIn("Unreadable local overlay directory", output)
                finally:
                    locked.chmod(0o700)

    def test_protocol_heading_edges_fail_closed_without_rejecting_comments(self):
        invalid_cases = (
            (
                "setext",
                lambda text: text.replace(
                    "## MemoryCustodian Protocol",
                    "MemoryCustodian Protocol\n---",
                    1,
                ),
            ),
            (
                "attached-closing-hash",
                lambda text: text.replace(
                    "## MemoryCustodian Protocol",
                    "## MemoryCustodian Protocol#",
                    1,
                ),
            ),
            (
                "indented-metadata",
                lambda text: re.sub(
                    r"(?m)^(- (?:protocol_version|entry_schema_version|subject_schema_version|"
                    r"subject_registry|routing_schema_version|conflict_schema_version|"
                    r"initialized_with|last_migrated_with|project_id|admission_policy|"
                    r"routing_policy|conflict_policy):)",
                    r"    \1",
                    text,
                ),
            ),
        )
        for name, mutate in invalid_cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["init", "--project-root", tmp]), 0)
                memory = Path(tmp) / "docs/memory"
                manifest = memory / "manifest.md"
                manifest.write_text(
                    mutate(manifest.read_text(encoding="utf-8")),
                    encoding="utf-8",
                )
                for command in (
                    ("read", "--task", "implementation", "--strict-routing", "--names-only"),
                    ("check", "--routing"),
                    ("enable", "preferences"),
                ):
                    code, output, error = capture([
                        *command,
                        "--project-root", tmp,
                    ])
                    self.assertNotEqual(code, 0, output + error)
                self.assertFalse((memory / "preferences.md").exists())

        with tempfile.TemporaryDirectory() as tmp:
            with redirect_stdout(StringIO()):
                self.assertEqual(main(["init", "--project-root", tmp]), 0)
            manifest = Path(tmp) / "docs/memory/manifest.md"
            manifest.write_text(
                manifest.read_text(encoding="utf-8").rstrip()
                + "\n\n<!--\n## MemoryCustodian Protocol\n"
                + "- protocol_version: 0.6\n-->\n",
                encoding="utf-8",
            )
            code, output, error = capture([
                "read", "--task", "implementation", "--strict-routing",
                "--names-only", "--project-root", tmp,
            ])
            self.assertEqual(code, 0, output + error)
            self.assertIn("Routing completeness: COMPLETE", output)

    def test_duplicate_optional_module_index_invalidates_all_contract_gates(self):
        with tempfile.TemporaryDirectory() as tmp:
            with redirect_stdout(StringIO()):
                self.assertEqual(main(["init", "--project-root", tmp]), 0)
            memory = Path(tmp) / "docs/memory"
            manifest = memory / "manifest.md"
            manifest.write_text(
                manifest.read_text(encoding="utf-8").rstrip()
                + "\n\n## Optional module index\n\n### Enabled rules\n"
                + "- `rules/evil.md`\n  - activation: explicit-only\n",
                encoding="utf-8",
            )
            for command in (
                ("read", "--task", "implementation", "--strict-routing", "--names-only"),
                ("check", "--routing"),
                ("enable", "preferences"),
            ):
                code, output, error = capture([*command, "--project-root", tmp])
                self.assertNotEqual(code, 0, output + error)
                self.assertIn("at most one Optional module index", output + error)
            self.assertFalse((memory / "preferences.md").exists())

    @unittest.skipIf(os.name == "nt", "POSIX symlink semantics")
    def test_local_reset_hashes_bytes_and_never_follows_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as state:
            with patch.dict(os.environ, {"XDG_STATE_HOME": state}):
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["init", "--project-root", tmp]), 0)
                    self.assertEqual(main(["local", "enable", "--project-root", tmp]), 0)
                    self.assertEqual(main(["local", "link", "--project-root", tmp]), 0)
                manifest = Path(tmp) / "docs/memory/manifest.md"
                project_id = re.search(
                    r"(?m)^- project_id: (\S+)",
                    manifest.read_text(encoding="utf-8"),
                ).group(1)
                overlay = (
                    Path(state) / "memory-custodian/projects" / project_id / "local"
                )
                outside = Path(state) / "outside.txt"
                outside.write_text("first", encoding="utf-8")
                link = overlay / "outside-link"
                link.symlink_to(outside)

                code, first, error = capture([
                    "local", "reset", "--project-root", tmp,
                ])
                self.assertEqual(code, 0, error)
                self.assertIn("Unsafe local overlay symlink", first)
                first_plan = re.search(r"Plan ID: ([0-9a-f]{16})", first).group(1)
                outside.write_text("second", encoding="utf-8")
                _code, second, _error = capture([
                    "local", "reset", "--project-root", tmp,
                ])
                self.assertEqual(
                    first_plan,
                    re.search(r"Plan ID: ([0-9a-f]{16})", second).group(1),
                )

                link.unlink()
                (overlay / "manifest.md").write_bytes(b"\xff\xfe")
                code, binary, error = capture([
                    "local", "reset", "--project-root", tmp,
                ])
                self.assertEqual(code, 0, error)
                self.assertIn("Local overlay status: REVIEW", binary)
                self.assertIn("Plan ID:", binary)
                self.assertNotIn("Blockers:\n- none", binary)

    def test_migration_completes_routes_from_the_template_authority(self):
        with tempfile.TemporaryDirectory() as tmp:
            with redirect_stdout(StringIO()):
                self.assertEqual(main(["init", "--project-root", tmp]), 0)
            manifest = Path(tmp) / "docs/memory/manifest.md"
            implementation = (
                "### Implementation / execution / debugging\n"
                "Load:\n- decisions.md\n- do-not-use.md\n"
                "Load if present:\n- preferences.md\n\n"
            )
            manifest.write_text(
                manifest.read_text(encoding="utf-8")
                .replace("- protocol_version: 0.7", "- protocol_version: 0.6", 1)
                .replace(implementation, "", 1),
                encoding="utf-8",
            )
            code, output, error = capture(["migrate", "--project-root", tmp])
            self.assertEqual(code, 0, output + error)
            self.assertIn("Plan ID:", output)
            self.assertNotIn("duplicate paths: constraints.md", output + error)

    def test_task_routes_require_one_parent_and_no_out_of_parent_canonical_h3(self):
        mutations = (
            (
                lambda text: text.replace("## Load by task", "## Other task routes", 1),
                "expected exactly one 'Load by task' section, found 0",
            ),
            (
                lambda text: text.rstrip() + "\n\n## Load by task\n",
                "expected exactly one 'Load by task' section, found 2",
            ),
            (
                lambda text: text.rstrip()
                + "\n\n## Other task routes\n\n### Planning / architecture / refactoring\n"
                + "Load:\n- decisions.md\n",
                "canonical heading appears outside",
            ),
        )
        for mutate, expected in mutations:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as tmp:
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["init", "--project-root", tmp]), 0)
                manifest = Path(tmp) / "docs/memory/manifest.md"
                manifest.write_text(
                    mutate(manifest.read_text(encoding="utf-8")),
                    encoding="utf-8",
                )
                code, output, error = capture([
                    "check", "--routing", "--project-root", tmp,
                ])
                self.assertEqual(code, 1, output + error)
                self.assertIn(expected, output)

    def test_migration_reuses_normalized_protocol_heading(self):
        with tempfile.TemporaryDirectory() as tmp:
            with redirect_stdout(StringIO()):
                self.assertEqual(main(["init", "--project-root", tmp]), 0)
            manifest = Path(tmp) / "docs/memory/manifest.md"
            manifest.write_text(
                manifest.read_text(encoding="utf-8")
                .replace("## MemoryCustodian Protocol", "## MEMORYCUSTODIAN PROTOCOL ##", 1)
                .replace("- protocol_version: 0.7", "- protocol_version: 0.6", 1),
                encoding="utf-8",
            )
            code, output, error = capture(["migrate", "--project-root", tmp])
            self.assertEqual(code, 0, output + error)
            self.assertIn("Plan ID:", output)
            self.assertNotIn("exactly one MemoryCustodian Protocol", output + error)

    def test_migration_operand_decode_failure_precedes_all_pending_seeds(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as state:
            with redirect_stdout(StringIO()):
                self.assertEqual(main(["init", "--project-root", tmp]), 0)
            memory = Path(tmp) / "docs/memory"
            manifest = memory / "manifest.md"
            manifest.write_text(
                re.sub(
                    r"(?m)^- project_id:.*\n",
                    "",
                    manifest.read_text(encoding="utf-8").replace(
                        "- protocol_version: 0.7", "- protocol_version: 0.6", 1,
                    ),
                ),
                encoding="utf-8",
            )
            (memory / "decisions.md").write_bytes(b"\xff\xfe")
            with patch.dict(os.environ, {"XDG_STATE_HOME": state}):
                code, output, _error = capture(["migrate", "--project-root", tmp])
            self.assertEqual(code, 2)
            self.assertNotIn("Plan ID:", output)
            self.assertEqual(tuple(Path(state).rglob("*")), ())

    def test_routing_contract_gates_writers_recovery_and_focused_checks(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as state:
            with redirect_stdout(StringIO()):
                self.assertEqual(main(["init", "--project-root", tmp]), 0)
            memory = Path(tmp) / "docs/memory"
            manifest = memory / "manifest.md"
            unsafe = manifest.read_text(encoding="utf-8").replace(
                "- brief.md\n- constraints.md",
                "- ../outside.md\n- constraints.md",
                1,
            )
            manifest.write_text(unsafe, encoding="utf-8")

            for command in (
                ("enable", "preferences"),
                ("init", "--repair"),
            ):
                code, output, error = capture([
                    *command, "--project-root", tmp,
                ])
                self.assertEqual(code, 2, output + error)
                self.assertIn("unsafe or malformed memory path", error)
                self.assertEqual(manifest.read_text(encoding="utf-8"), unsafe)
            self.assertFalse((memory / "preferences.md").exists())

            code, output, _error = capture([
                "check", "--reachability", "--project-root", tmp,
            ])
            self.assertEqual(code, 1)
            self.assertIn("MC-ROUTING-007 ERROR", output)
            self.assertIn("unsafe or malformed memory path", output)

            legacy = unsafe.replace(
                "- protocol_version: 0.7", "- protocol_version: 0.6", 1,
            )
            manifest.write_text(legacy, encoding="utf-8")
            (memory / "decisions.md").write_text(
                "# Decisions\n\n## Legacy decision\nDecision:\nKeep legacy.\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"XDG_STATE_HOME": state}):
                code, output, error = capture(["migrate", "--project-root", tmp])
            self.assertEqual(code, 2)
            self.assertNotIn("Plan ID:", output)
            self.assertIn("unsafe or malformed memory path", error)
            self.assertEqual(tuple(Path(state).rglob("*")), ())

    def test_protocol_heading_scan_respects_markdown_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            with redirect_stdout(StringIO()):
                self.assertEqual(main(["init", "--project-root", tmp]), 0)
            manifest = Path(tmp) / "docs/memory/manifest.md"
            original = manifest.read_text(encoding="utf-8")
            manifest.write_text(
                original.replace(
                    "## MemoryCustodian Protocol",
                    "    ## MemoryCustodian Protocol",
                    1,
                ),
                encoding="utf-8",
            )
            for command in (
                ("read", "--task", "implementation", "--strict-routing", "--names-only"),
                ("check", "--routing"),
                ("local", "status"),
            ):
                code, output, error = capture([
                    *command, "--project-root", tmp,
                ])
                self.assertNotEqual(code, 0, output + error)

            manifest.write_text(
                original.rstrip()
                + "\n\n```markdown\n## MemoryCustodian Protocol\n"
                + "- protocol_version: 0.6\n```\n",
                encoding="utf-8",
            )
            read_code, read_output, read_error = capture([
                "read", "--task", "implementation", "--strict-routing",
                "--names-only", "--project-root", tmp,
            ])
            self.assertEqual(read_code, 0, read_output + read_error)
            self.assertIn("Routing completeness: COMPLETE", read_output)
            check_code, check_output, check_error = capture([
                "check", "--routing", "--project-root", tmp,
            ])
            self.assertEqual(check_code, 0, check_output + check_error)

    def test_invalid_manifest_cannot_select_bound_local_overlay(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as state:
            with patch.dict(os.environ, {"XDG_STATE_HOME": state}):
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["init", "--project-root", tmp]), 0)
                    self.assertEqual(main(["local", "enable", "--project-root", tmp]), 0)
                    self.assertEqual(main(["local", "link", "--project-root", tmp]), 0)
                code, added, error = capture([
                    "local", "add", "Private local preference.",
                    "--type", "preference", "--evidence", "user-confirmed",
                    "--project-root", tmp,
                ])
                self.assertEqual(code, 0, error)
                entry_id = re.search(r"MC-PREF-\d{8}-[0-9a-f]{8}", added).group(0)
                manifest = Path(tmp) / "docs/memory/manifest.md"
                manifest.write_text(
                    manifest.read_text(encoding="utf-8").rstrip()
                    + "\n\n## MemoryCustodian Protocol\n- protocol_version: 0.6\n",
                    encoding="utf-8",
                )

                for command in (
                    ("list", "--local"),
                    ("show", entry_id, "--local"),
                ):
                    command_code, output, command_error = capture([
                        *command, "--project-root", tmp,
                    ])
                    self.assertEqual(command_code, 2, output + command_error)
                    self.assertNotIn("Private local preference.", output)

                project_id = re.search(
                    r"(?m)^- project_id: (\S+)",
                    manifest.read_text(encoding="utf-8"),
                ).group(1)
                local_preferences = (
                    Path(state) / "memory-custodian/projects" / project_id
                    / "local/preferences.md"
                )
                local_preferences.write_text(
                    local_preferences.read_text(encoding="utf-8")
                    + "\nprivate@example.com\n",
                    encoding="utf-8",
                )
                check_code, check_output, _check_error = capture([
                    "check", "--privacy", "--project-root", tmp,
                ])
                self.assertEqual(check_code, 1)
                self.assertNotIn("local/preferences.md", check_output)

    def test_promotion_validates_operand_and_binds_candidate_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            with redirect_stdout(StringIO()):
                self.assertEqual(main(["init", "--project-root", tmp]), 0)
            memory = Path(tmp) / "docs/memory"
            subject_id = "MC-SUBJ-20260808-11111111"
            candidate_id = "MC-INBOX-20260808-11111111"
            (memory / "subjects.md").write_text(
                "# Subject Registry\n\n" + subject_unit(subject_id, "Promotion"),
                encoding="utf-8",
            )
            candidate = render_candidate_entry(
                candidate_id, "Invalid candidate", "decision", "First body.",
                "project", ("user-confirmed",), None,
                subject=subject_id, facet="invalid-facet",
            )
            inbox = memory / "inbox.md"
            inbox.write_text("# Memory Inbox\n\n" + candidate + "\n", encoding="utf-8")
            command = [
                "promote", candidate_id, "--type", "decision",
                "--evidence", "user-confirmed", "--project-root", tmp,
            ]
            code, first, error = capture(command)
            self.assertEqual(code, 0, error)
            self.assertIn("Invalid provisional Facet 'invalid-facet'", first)
            self.assertNotIn("Blockers:\n- none", first)
            first_plan = re.search(r"Plan ID: ([0-9a-f]{16})", first).group(1)
            inbox.write_text(
                inbox.read_text(encoding="utf-8").replace(
                    "Statement:\nFirst body.", "Statement:\nChanged body.",
                ),
                encoding="utf-8",
            )
            _code, second, _error = capture(command)
            second_plan = re.search(r"Plan ID: ([0-9a-f]{16})", second).group(1)
            self.assertNotEqual(first_plan, second_plan)

    def test_subject_merge_validates_entries_and_binds_registry_and_entry_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            with redirect_stdout(StringIO()):
                self.assertEqual(main(["init", "--project-root", tmp]), 0)
            memory = Path(tmp) / "docs/memory"
            source_id = "MC-SUBJ-20260808-11111111"
            target_id = "MC-SUBJ-20260808-22222222"
            entry_id = "MC-DEC-20260808-11111111"
            subjects = memory / "subjects.md"
            subjects.write_text(
                "# Subject Registry\n\n"
                + subject_unit(source_id, "Source subject")
                + "\n" + subject_unit(target_id, "Target subject"),
                encoding="utf-8",
            )
            entry = render_active_entry(
                "decision", entry_id, "Invalid source entry", "Body.", None,
                "project", ("user-confirmed",), subject=source_id,
                facet="invalid-facet",
            )
            decisions = memory / "decisions.md"
            decisions.write_text("# Decisions\n\n" + entry + "\n", encoding="utf-8")
            command = [
                "subject", "merge", source_id, "--into", target_id,
                "--project-root", tmp,
            ]
            code, first, error = capture(command)
            self.assertEqual(code, 0, error)
            self.assertIn("Invalid Facet 'invalid-facet'", first)
            first_plan = re.search(r"Plan ID: ([0-9a-f]{16})", first).group(1)

            subjects.write_text(
                subjects.read_text(encoding="utf-8").replace(
                    "Target subject", "Renamed target",
                ),
                encoding="utf-8",
            )
            _code, renamed, _error = capture(command)
            renamed_plan = re.search(r"Plan ID: ([0-9a-f]{16})", renamed).group(1)
            self.assertNotEqual(first_plan, renamed_plan)

            decisions.write_text(
                decisions.read_text(encoding="utf-8").replace(
                    "Facet: invalid-facet", "Facet: behavior",
                ),
                encoding="utf-8",
            )
            _code, repaired, _error = capture(command)
            repaired_plan = re.search(r"Plan ID: ([0-9a-f]{16})", repaired).group(1)
            self.assertNotEqual(renamed_plan, repaired_plan)

    def test_local_reset_state_semantics_and_dependencies(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as second, tempfile.TemporaryDirectory() as state:
            with patch.dict(os.environ, {"XDG_STATE_HOME": state}):
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["init", "--project-root", tmp]), 0)
                code, disabled, error = capture([
                    "local", "reset", "--project-root", tmp,
                ])
                self.assertEqual(code, 0, error)
                self.assertNotIn("Plan ID:", disabled)
                self.assertIn("nothing to reset", disabled)
                self.assertIn("Local overlay: not-applicable", disabled)

                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["local", "enable", "--project-root", tmp]), 0)
                _code, unbound, _error = capture([
                    "local", "reset", "--project-root", tmp,
                ])
                self.assertIn("Blockers:", unbound)
                self.assertNotIn("Blockers:\n- none", unbound)
                self.assertIn("blocked-pending-local-overlay-review", unbound)

                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["local", "link", "--project-root", tmp]), 0)
                    self.assertEqual(main([
                        "local", "add", "First reset dependency.",
                        "--type", "preference", "--evidence", "user-confirmed",
                        "--project-root", tmp,
                    ]), 0)
                _code, bound, _error = capture([
                    "local", "reset", "--project-root", tmp,
                ])
                self.assertIn("Blockers:\n- none", bound)
                bound_plan = re.search(r"Plan ID: ([0-9a-f]{16})", bound).group(1)

                project_id = re.search(
                    r"(?m)^- project_id: (\S+)",
                    (Path(tmp) / "docs/memory/manifest.md").read_text(encoding="utf-8"),
                ).group(1)
                local_preferences = (
                    Path(state) / "memory-custodian/projects" / project_id
                    / "local/preferences.md"
                )
                local_preferences.write_text(
                    local_preferences.read_text(encoding="utf-8")
                    + "\nChanged reset dependency.\n",
                    encoding="utf-8",
                )
                _code, changed, _error = capture([
                    "local", "reset", "--project-root", tmp,
                ])
                changed_plan = re.search(r"Plan ID: ([0-9a-f]{16})", changed).group(1)
                self.assertNotEqual(bound_plan, changed_plan)

                shutil.copytree(Path(tmp) / "docs", Path(second) / "docs")
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["local", "link", "--project-root", second]), 0)
                _code, review, _error = capture([
                    "local", "reset", "--project-root", tmp,
                ])
                self.assertIn("Local overlay status: REVIEW", review)
                self.assertNotIn("Blockers:\n- none", review)

    def test_semantic_migrate_failure_creates_no_pending_seed(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as state:
            with redirect_stdout(StringIO()):
                self.assertEqual(main(["init", "--project-root", tmp]), 0)
            memory = Path(tmp) / "docs/memory"
            manifest = memory / "manifest.md"
            invalid = re.sub(
                r"(?m)^- project_id:.*$", "- project_id: invalid",
                manifest.read_text(encoding="utf-8"),
            ).replace("- protocol_version: 0.7", "- protocol_version: 0.6", 1)
            manifest.write_text(invalid, encoding="utf-8")
            (memory / "decisions.md").write_text(
                "# Decisions\n\n## Legacy\nDecision:\nNeeds an ID.\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"XDG_STATE_HOME": state}):
                code, output, error = capture(["migrate", "--project-root", tmp])
            self.assertEqual(code, 2)
            self.assertNotIn("Plan ID:", output)
            self.assertIn("Invalid project_id", error)
            self.assertEqual(tuple(Path(state).rglob("*")), ())

    def test_plain_check_classifies_malformed_only_heading_as_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            with redirect_stdout(StringIO()):
                self.assertEqual(main(["init", "--project-root", tmp]), 0)
            manifest = Path(tmp) / "docs/memory/manifest.md"
            manifest.write_text(
                manifest.read_text(encoding="utf-8").replace(
                    "## MemoryCustodian Protocol",
                    "### MemoryCustodian Protocol",
                    1,
                ),
                encoding="utf-8",
            )
            code, output, _error = capture(["check", "--project-root", tmp])
            self.assertEqual(code, 1)
            self.assertIn("invalid protocol metadata", output)
            self.assertNotIn("missing MemoryCustodian Protocol metadata", output)

    def test_invalid_protocol_contract_is_rejected_across_public_entrypoints(self):
        subject_id = "MC-SUBJ-20260801-11111111"
        active_id = "MC-DEC-20260801-11111111"
        candidate_id = "MC-INBOX-20260801-11111111"
        states = (
            (
                "duplicate-heading",
                lambda text: text.rstrip()
                + "\n\n## MemoryCustodian Protocol\n- protocol_version: 0.6\n",
            ),
            (
                "missing-schema",
                lambda text: re.sub(
                    r"(?m)^- routing_schema_version:.*\n", "", text,
                ),
            ),
            (
                "noncanonical-version",
                lambda text: text.replace(
                    "- protocol_version: 0.7", "- protocol_version: 0.7.0", 1,
                ),
            ),
            (
                "invalid-project-id",
                lambda text: re.sub(
                    r"(?m)^- project_id:.*$", "- project_id: invalid", text,
                ),
            ),
        )
        commands = (
            ("subject", ("subject", "list"), 2),
            (
                "add-supersedes",
                (
                    "add", "replacement", "--type", "decision",
                    "--evidence", "user-confirmed",
                    "--supersedes", active_id,
                    "--subject", subject_id,
                    "--facet", "architecture",
                ),
                2,
            ),
            ("forget", ("forget", "obsolete"), 2),
            (
                "forget-id",
                ("forget", "--id", active_id),
                2,
            ),
            ("compact", ("compact",), 2),
            (
                "promote",
                (
                    "promote", candidate_id,
                    "--type", "decision", "--evidence", "user-confirmed",
                ),
                2,
            ),
            ("init-replace", ("init", "--replace-existing"), 2),
            ("status", ("status",), 1),
            ("conflicts", ("check", "--conflicts"), 1),
            ("reachability", ("check", "--reachability"), 1),
            ("freshness", ("check", "--freshness"), 1),
            ("local-status", ("local", "status"), 2),
            ("local-reset", ("local", "reset"), 2),
        )
        for state_name, mutate in states:
            with self.subTest(state=state_name), tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as state:
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["init", "--project-root", tmp]), 0)
                memory = Path(tmp) / "docs/memory"
                (memory / "subjects.md").write_text(
                    "# Subject Registry\n\n"
                    + subject_unit(subject_id, "Matrix subject"),
                    encoding="utf-8",
                )
                active = render_active_entry(
                    "decision", active_id, "Existing decision", "Existing.", None,
                    "project", ("user-confirmed",), subject=subject_id,
                    facet="architecture",
                )
                (memory / "decisions.md").write_text(
                    "# Decisions\n\n" + active + "\n", encoding="utf-8",
                )
                candidate = render_candidate_entry(
                    candidate_id, "Candidate", "decision", "Candidate body.",
                    "project", ("user-confirmed",), None,
                    subject=subject_id, facet="behavior",
                )
                (memory / "inbox.md").write_text(
                    "# Memory Inbox\n\n" + candidate + "\n", encoding="utf-8",
                )
                manifest = memory / "manifest.md"
                invalid = mutate(manifest.read_text(encoding="utf-8"))
                manifest.write_text(invalid, encoding="utf-8")

                with patch.dict(os.environ, {"XDG_STATE_HOME": state}):
                    for command_name, command, expected_code in commands:
                        with self.subTest(state=state_name, command=command_name):
                            code, output, error = capture([
                                *command, "--project-root", tmp,
                            ])
                            self.assertEqual(code, expected_code, output + error)
                            self.assertNotIn("Plan ID:", output)
                            self.assertEqual(
                                manifest.read_text(encoding="utf-8"), invalid,
                            )
                            if command_name == "status":
                                self.assertIn("Protocol metadata: INVALID", output)
                                self.assertIn("manifest.md: INVALID", output)
                            elif command_name in {
                                "conflicts", "reachability", "freshness",
                            }:
                                self.assertIn("MC-ROUTING-007", output)
                self.assertEqual(tuple(Path(state).rglob("*")), ())

    def test_failed_migrate_syntax_preflight_creates_no_pending_seed(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as state:
            with redirect_stdout(StringIO()):
                self.assertEqual(main(["init", "--project-root", tmp]), 0)
            manifest = Path(tmp) / "docs/memory/manifest.md"
            malformed = manifest.read_text(encoding="utf-8").replace(
                "## MemoryCustodian Protocol", "### MemoryCustodian Protocol", 1,
            )
            manifest.write_text(malformed, encoding="utf-8")

            with patch.dict(os.environ, {"XDG_STATE_HOME": state}):
                code, output, error = capture(["migrate", "--project-root", tmp])

            self.assertEqual(code, 2)
            self.assertNotIn("Plan ID:", output)
            self.assertIn("exactly one MemoryCustodian Protocol heading", error)
            self.assertEqual(manifest.read_text(encoding="utf-8"), malformed)
            self.assertEqual(tuple(Path(state).rglob("*")), ())

    def test_extra_malformed_protocol_trace_invalidates_all_shared_gates(self):
        for malformed in ("### MemoryCustodian Protocol", "##MemoryCustodian Protocol"):
            with self.subTest(heading=malformed), tempfile.TemporaryDirectory() as tmp:
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["init", "--project-root", tmp]), 0)
                manifest = Path(tmp) / "docs/memory/manifest.md"
                manifest.write_text(
                    manifest.read_text(encoding="utf-8").rstrip()
                    + f"\n\n## Additional notes\n\n{malformed}\n",
                    encoding="utf-8",
                )

                read_code, read_output, read_error = capture([
                    "read", "--task", "implementation", "--strict-routing",
                    "--names-only", "--project-root", tmp,
                ])
                self.assertEqual(read_code, 2)
                self.assertIn("Routing completeness: INVALID", read_output)
                self.assertIn("exactly one MemoryCustodian Protocol heading", read_error)

                check_code, check_output, _check_error = capture([
                    "check", "--routing", "--project-root", tmp,
                ])
                self.assertEqual(check_code, 1)
                self.assertIn("MC-ROUTING-007 ERROR", check_output)
                self.assertIn("exactly one MemoryCustodian Protocol heading", check_output)

                before = manifest.read_text(encoding="utf-8")
                enable_code, _enable_output, enable_error = capture([
                    "enable", "preferences", "--project-root", tmp,
                ])
                self.assertEqual(enable_code, 2)
                self.assertIn("exactly one MemoryCustodian Protocol heading", enable_error)
                self.assertEqual(manifest.read_text(encoding="utf-8"), before)
                self.assertFalse((Path(tmp) / "docs/memory/preferences.md").exists())

    def test_noncanonical_current_and_future_versions_fail_all_shared_gates(self):
        cases = (
            ("0.7.0", "canonical value 0.7"),
            ("00.7", "canonical value 0.7"),
            ("0.8", "newer than this CLI supports"),
        )
        for version, expected in cases:
            with self.subTest(version=version), tempfile.TemporaryDirectory() as tmp:
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["init", "--project-root", tmp]), 0)
                manifest = Path(tmp) / "docs/memory/manifest.md"
                malformed = manifest.read_text(encoding="utf-8").replace(
                    "- protocol_version: 0.7", f"- protocol_version: {version}", 1,
                )
                if version != "0.8":
                    malformed = re.sub(
                        r"(?m)^- routing_schema_version:.*\n", "", malformed,
                    )
                manifest.write_text(malformed, encoding="utf-8")

                read_code, read_output, read_error = capture([
                    "read", "--task", "implementation", "--strict-routing",
                    "--names-only", "--project-root", tmp,
                ])
                self.assertEqual(read_code, 2)
                self.assertIn("Routing completeness: INVALID", read_output)
                self.assertIn(expected, read_error)

                check_code, check_output, _check_error = capture([
                    "check", "--routing", "--project-root", tmp,
                ])
                self.assertEqual(check_code, 1)
                self.assertIn("MC-ROUTING-007 ERROR", check_output)
                self.assertIn(expected, check_output)

                before = manifest.read_text(encoding="utf-8")
                enable_code, _enable_output, enable_error = capture([
                    "enable", "preferences", "--project-root", tmp,
                ])
                self.assertEqual(enable_code, 2)
                self.assertIn(expected, enable_error)
                self.assertEqual(manifest.read_text(encoding="utf-8"), before)

                governance_code, _governance_output, governance_error = capture([
                    "exception", "remove", "MC-CON-20260801-11111111",
                    "--project-root", tmp,
                ])
                self.assertEqual(governance_code, 2)
                self.assertIn(expected, governance_error)

    def test_present_protocol_section_requires_complete_current_contract(self):
        cases = (
            (
                lambda text: re.sub(r"(?m)^- protocol_version:.*\n", "", text),
                "requires protocol_version",
            ),
            (
                lambda text: re.sub(r"(?m)^- routing_schema_version:.*\n", "", text),
                "requires routing_schema_version: 1",
            ),
            (
                lambda text: re.sub(r"(?m)^- admission_policy:.*\n", "", text),
                "requires admission_policy: evidence-required",
            ),
        )
        for mutate, expected in cases:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as tmp:
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["init", "--project-root", tmp]), 0)
                manifest = Path(tmp) / "docs/memory/manifest.md"
                manifest.write_text(
                    mutate(manifest.read_text(encoding="utf-8")),
                    encoding="utf-8",
                )

                read_code, read_output, read_error = capture([
                    "read", "--task", "implementation", "--strict-routing",
                    "--names-only", "--project-root", tmp,
                ])
                self.assertEqual(read_code, 2)
                self.assertIn("Routing completeness: INVALID", read_output)
                self.assertIn(expected, read_error)

                check_code, check_output, _check_error = capture([
                    "check", "--routing", "--project-root", tmp,
                ])
                self.assertEqual(check_code, 1)
                self.assertIn("MC-ROUTING-007 ERROR", check_output)
                self.assertIn(expected, check_output)

                before = manifest.read_text(encoding="utf-8")
                enable_code, _enable_output, enable_error = capture([
                    "enable", "preferences", "--project-root", tmp,
                ])
                self.assertEqual(enable_code, 2)
                self.assertIn(expected, enable_error)
                self.assertEqual(manifest.read_text(encoding="utf-8"), before)
                self.assertFalse((Path(tmp) / "docs/memory/preferences.md").exists())

    def test_recovery_rejects_ambiguous_protocol_sections_before_planning(self):
        for command in (("migrate",), ("init", "--repair")):
            with self.subTest(command=command), tempfile.TemporaryDirectory() as tmp:
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["init", "--project-root", tmp]), 0)
                manifest = Path(tmp) / "docs/memory/manifest.md"
                original = manifest.read_text(encoding="utf-8")
                if command[0] == "migrate":
                    original = original.replace(
                        "- protocol_version: 0.7", "- protocol_version: 0.6", 1,
                    )
                ambiguous = original.rstrip() + (
                    "\n\n## MemoryCustodian Protocol\n"
                    "- protocol_version: 0.6\n"
                    "- project_id: 11111111-1111-4111-8111-111111111111\n"
                )
                manifest.write_text(ambiguous, encoding="utf-8")

                code, output, error = capture([
                    *command, "--project-root", tmp,
                ])
                self.assertEqual(code, 2)
                self.assertNotIn("Plan ID:", output)
                self.assertIn(
                    "exactly one MemoryCustodian Protocol heading", error,
                )
                self.assertEqual(manifest.read_text(encoding="utf-8"), ambiguous)

    def test_pre_metadata_legacy_routing_remains_compatible(self):
        with tempfile.TemporaryDirectory() as tmp:
            with redirect_stdout(StringIO()):
                self.assertEqual(main(["init", "--project-root", tmp]), 0)
            manifest = Path(tmp) / "docs/memory/manifest.md"
            manifest.write_text(
                re.sub(
                    r"(?ms)^## MemoryCustodian Protocol\n.*?(?=^## Trust boundary)",
                    "",
                    manifest.read_text(encoding="utf-8"),
                ),
                encoding="utf-8",
            )

            read_code, read_output, _read_error = capture([
                "read", "--task", "implementation", "--strict-routing",
                "--names-only", "--project-root", tmp,
            ])
            self.assertEqual(read_code, 0)
            self.assertIn("Routing completeness: COMPLETE", read_output)

            check_code, check_output, _check_error = capture([
                "check", "--routing", "--project-root", tmp,
            ])
            self.assertEqual(check_code, 0)
            self.assertNotIn("MC-ROUTING-007", check_output)

            enable_code, _enable_output, _enable_error = capture([
                "enable", "preferences", "--project-root", tmp,
            ])
            self.assertEqual(enable_code, 0)
            self.assertTrue((Path(tmp) / "docs/memory/preferences.md").is_file())

    def test_duplicate_protocol_section_invalidates_strict_read_and_routing_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            with redirect_stdout(StringIO()):
                self.assertEqual(main(["init", "--project-root", tmp]), 0)
            manifest = Path(tmp) / "docs/memory/manifest.md"
            manifest.write_text(
                manifest.read_text(encoding="utf-8").rstrip()
                + "\n\n## MEMORYCUSTODIAN PROTOCOL\n- protocol_version: 0.6\n",
                encoding="utf-8",
            )

            read_code, read_output, read_error = capture([
                "read", "--task", "implementation", "--strict-routing",
                "--explain", "--names-only", "--project-root", tmp,
            ])
            self.assertEqual(read_code, 2)
            self.assertIn("Routing completeness: INVALID", read_output)
            self.assertIn("MC-ROUTE-INVALID", read_output)
            self.assertIn("exactly one MemoryCustodian Protocol heading", read_error)

            check_code, check_output, _check_error = capture([
                "check", "--routing", "--project-root", tmp,
            ])
            self.assertEqual(check_code, 1)
            self.assertIn("MC-ROUTING-007 ERROR", check_output)
            self.assertIn("exactly one MemoryCustodian Protocol heading", check_output)

            before = manifest.read_text(encoding="utf-8")
            enable_code, _enable_output, enable_error = capture([
                "enable", "preferences", "--project-root", tmp,
            ])
            self.assertEqual(enable_code, 2)
            self.assertIn("exactly one MemoryCustodian Protocol heading", enable_error)
            self.assertEqual(manifest.read_text(encoding="utf-8"), before)
            self.assertFalse((Path(tmp) / "docs/memory/preferences.md").exists())

    def test_malformed_protocol_heading_invalidates_routing_and_mutation(self):
        for malformed in ("### MemoryCustodian Protocol", "##MemoryCustodian Protocol"):
            with self.subTest(heading=malformed), tempfile.TemporaryDirectory() as tmp:
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["init", "--project-root", tmp]), 0)
                manifest = Path(tmp) / "docs/memory/manifest.md"
                original = manifest.read_text(encoding="utf-8")
                manifest.write_text(
                    original.replace("## MemoryCustodian Protocol", malformed, 1),
                    encoding="utf-8",
                )

                read_code, read_output, _read_error = capture([
                    "read", "--task", "implementation", "--strict-routing",
                    "--names-only", "--project-root", tmp,
                ])
                self.assertEqual(read_code, 2)
                self.assertIn("Routing completeness: INVALID", read_output)

                check_code, check_output, _check_error = capture([
                    "check", "--routing", "--project-root", tmp,
                ])
                self.assertEqual(check_code, 1)
                self.assertIn("MC-ROUTING-007 ERROR", check_output)

                before = manifest.read_text(encoding="utf-8")
                enable_code, _enable_output, enable_error = capture([
                    "enable", "preferences", "--project-root", tmp,
                ])
                self.assertEqual(enable_code, 2)
                self.assertIn("exactly one MemoryCustodian Protocol heading", enable_error)
                self.assertEqual(manifest.read_text(encoding="utf-8"), before)
                self.assertFalse((Path(tmp) / "docs/memory/preferences.md").exists())

    def test_exclusive_group_is_unknown_in_routing_schema_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            with redirect_stdout(StringIO()):
                self.assertEqual(main(["init", "--project-root", tmp]), 0)
            manifest = Path(tmp) / "docs/memory/manifest.md"
            manifest.write_text(
                manifest.read_text(encoding="utf-8").replace(
                    "### Enabled areas\n- None enabled.",
                    "### Enabled areas\n"
                    "- `areas/backend.md`\n"
                    "  - activation: path\n"
                    "  - paths: `cli/**`\n"
                    "  - exclusive-group: runtime",
                ),
                encoding="utf-8",
            )
            code, output, error = capture([
                "read", "--task", "implementation", "--path", "cli/app.py",
                "--names-only", "--project-root", tmp,
            ])
            self.assertEqual(code, 2)
            self.assertIn("Routing completeness: INVALID", output)
            self.assertIn("unknown optional module key 'exclusive-group'", output + error)

    def test_invalid_routing_uses_structured_result_and_stderr(self):
        with tempfile.TemporaryDirectory() as tmp:
            with redirect_stdout(StringIO()):
                self.assertEqual(main(["init", "--project-root", tmp]), 0)
            manifest = Path(tmp) / "docs/memory/manifest.md"
            manifest.write_text(
                manifest.read_text(encoding="utf-8").replace(
                    "- brief.md\n- constraints.md", "- ../outside.md\n- constraints.md", 1,
                ),
                encoding="utf-8",
            )
            code, output, error = capture([
                "read", "--task", "implementation", "--explain",
                "--names-only", "--project-root", tmp,
            ])
            self.assertEqual(code, 2)
            self.assertIn("Routing completeness: INVALID", output)
            self.assertIn("Disposition: invalid", output)
            self.assertIn("MC-ROUTE-INVALID", output)
            self.assertIn("Error:", error)

    def test_reachability_and_freshness_cover_hard_and_historical_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            with redirect_stdout(StringIO()):
                self.assertEqual(main(["init", "--project-root", tmp]), 0)
            memory = Path(tmp) / "docs/memory"
            subject_id = "MC-SUBJ-20260801-a1b2c3d4"
            (memory / "subjects.md").write_text(
                "# Subject Registry\n\n" + subject_unit(subject_id, "Release quality"),
                encoding="utf-8",
            )
            orphan = render_active_entry(
                "constraint", "MC-CON-20260801-11111111", "Unreachable hard memory",
                "Keep this constraint reachable.", None, "project",
                ("user-confirmed",), subject=subject_id, facet="behavior",
            )
            (memory / "orphan.md").write_text("# Orphan\n\n" + orphan + "\n", encoding="utf-8")
            unreachable_code, unreachable, _error = capture([
                "check", "--reachability", "--project-root", tmp,
            ])
            self.assertEqual(unreachable_code, 1)
            self.assertIn("MC-REACH-001 ERROR", unreachable)

            active = render_active_entry(
                "decision", "MC-DEC-20260801-22222222", "Missing Evidence path",
                "Use the documented policy.", None, "project",
                ("repo:missing-policy.md",), subject=subject_id, facet="architecture",
            )
            superseded = (
                "## MC-DEC-20260801-33333333 — Broken historical relation\n\n"
                "Status: superseded\nScope: project\n"
                f"Subject: {subject_id}\nFacet: interface\n"
                "Evidence:\n- user-confirmed\n"
                "Superseded-By: MC-DEC-20260801-ffffffff\n\n"
                "Decision:\nOld interface.\n"
            )
            (memory / "decisions.md").write_text(
                "# Decisions\n\n" + active + "\n\n" + superseded,
                encoding="utf-8",
            )
            freshness_code, freshness, _error = capture([
                "check", "--freshness", "--project-root", tmp,
            ])
            self.assertEqual(freshness_code, 1)
            self.assertIn("MC-FRESH-001 ERROR", freshness)
            self.assertIn("MC-FRESH-004 ERROR", freshness)
            self.assertIn("MC-DEC-20260801-33333333", freshness)

    def test_malformed_reconciliation_is_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            with redirect_stdout(StringIO()):
                self.assertEqual(main(["init", "--project-root", tmp]), 0)
            path = Path(tmp) / "docs/memory/reconciliations.md"
            path.write_text(
                "# Reconciliations\n\n## MC-REC-bad — Broken\n\nStatus: active\n",
                encoding="utf-8",
            )
            code, output, _error = capture([
                "check", "--conflicts", "--project-root", tmp,
            ])
            self.assertEqual(code, 1)
            self.assertIn("Conflict status: INVALID", output)
            self.assertIn("MC-CONFLICT-008", output)

    def test_project_area_overlap_requires_valid_exception(self):
        with tempfile.TemporaryDirectory() as tmp:
            with redirect_stdout(StringIO()):
                self.assertEqual(main(["init", "--project-root", tmp]), 0)
            memory = Path(tmp) / "docs/memory"
            subject_id = "MC-SUBJ-20260801-a1b2c3d4"
            project_id = "MC-CON-20260801-11111111"
            (memory / "subjects.md").write_text(
                "# Subject Registry\n\n" + subject_unit(subject_id, "Area exception"),
                encoding="utf-8",
            )
            project_entry = render_active_entry(
                "constraint", project_id, "Project baseline", "Project rule.", None,
                "project", ("user-confirmed",), subject=subject_id, facet="behavior",
            )
            area_entry = render_active_entry(
                "constraint", "MC-CON-20260801-22222222", "Area policy", "Area rule.", None,
                "area:backend", ("user-confirmed",), subject=subject_id, facet="behavior",
            )
            (memory / "constraints.md").write_text(
                "# Constraints\n\n" + project_entry + "\n", encoding="utf-8",
            )
            (memory / "areas").mkdir()
            area_path = memory / "areas/backend.md"
            area_path.write_text("# Backend\n\n" + area_entry + "\n", encoding="utf-8")
            review = analyze_conflicts(memory)
            self.assertEqual(review.status.value, "REVIEW")
            self.assertTrue(any(item.code == "MC-CONFLICT-002" for item in review.findings))

            valid_exception = area_entry.replace(
                "Evidence:\n", f"Exception-To: {project_id}\nEvidence:\n",
            )
            area_path.write_text("# Backend\n\n" + valid_exception + "\n", encoding="utf-8")
            self.assertEqual(analyze_conflicts(memory).status.value, "CLEAR")

            invalid_exception = valid_exception.replace(project_id, "MC-CON-20260801-ffffffff")
            area_path.write_text("# Backend\n\n" + invalid_exception + "\n", encoding="utf-8")
            invalid = analyze_conflicts(memory)
            self.assertEqual(invalid.status.value, "INVALID")
            self.assertTrue(any(item.code == "MC-CONFLICT-006" for item in invalid.findings))

    def test_local_manifest_rejects_unknown_or_unsafe_declarations(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as state:
            with patch.dict(os.environ, {"XDG_STATE_HOME": state}), redirect_stdout(StringIO()):
                self.assertEqual(main(["init", "--project-root", tmp]), 0)
                self.assertEqual(main(["local", "enable", "--project-root", tmp]), 0)
                self.assertEqual(main(["local", "link", "--project-root", tmp]), 0)
                project_id = re.search(
                    r"project_id: ([0-9a-f-]+)",
                    (Path(tmp) / "docs/memory/manifest.md").read_text(encoding="utf-8"),
                ).group(1)
                local_manifest = (
                    Path(state) / "memory-custodian/projects" / project_id / "local/manifest.md"
                )
                local_manifest.write_text(
                    local_manifest.read_text(encoding="utf-8") + "- ../escape.md\n",
                    encoding="utf-8",
                )
                code, output, _error = capture([
                    "read", "--task", "implementation", "--strict-routing",
                    "--project-root", tmp,
                ])
                self.assertEqual(code, 1)
                self.assertIn("Local overlay status: REVIEW", output)
                self.assertIn("invalid declaration", output)


class ForgetAndHistoryReleaseTests(unittest.TestCase):
    def test_hard_forget_apply_preserves_clear_conflicts_and_strict_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            with redirect_stdout(StringIO()):
                self.assertEqual(main(["init", "--project-root", tmp]), 0)
            memory = Path(tmp) / "docs/memory"
            subject_id = "MC-SUBJ-20260801-a1b2c3d4"
            target_id = "MC-DEC-20260801-11111111"
            (memory / "subjects.md").write_text(
                "# Subject Registry\n\n" + subject_unit(subject_id, "Hard erasure"),
                encoding="utf-8",
            )
            target = render_active_entry(
                "decision", target_id, "Forget safely", "Remove this entry.", None,
                "project", ("user-confirmed",), subject=subject_id, facet="behavior",
            )
            (memory / "decisions.md").write_text(
                "# Decisions\n\n" + target + "\n", encoding="utf-8",
            )
            code, preview, _error = capture([
                "forget", "--id", target_id, "--mode", "hard", "--project-root", tmp,
            ])
            self.assertEqual(code, 0)
            plan_id = re.search(r"Plan ID: ([0-9a-f]{16})", preview).group(1)
            apply_code, _output, _error = capture([
                "forget", "--id", target_id, "--mode", "hard", "--apply",
                "--confirm-plan", plan_id, "--project-root", tmp,
            ])
            self.assertEqual(apply_code, 0)
            tombstones = (memory / "do-not-use.md").read_text(encoding="utf-8")
            self.assertRegex(tombstones, r"MC-TOMB-\d{8}-[0-9a-f]{8}")
            self.assertNotIn("Subject:", tombstones)
            self.assertEqual(analyze_conflicts(memory).status.value, "CLEAR")
            strict_code, strict_output, _error = capture([
                "read", "--task", "implementation", "--strict-routing",
                "--names-only", "--project-root", tmp,
            ])
            self.assertEqual(strict_code, 0)
            self.assertIn("Conflict status: CLEAR", strict_output)

    def test_id_forget_blocks_reconciliation_references(self):
        with tempfile.TemporaryDirectory() as tmp:
            with redirect_stdout(StringIO()):
                self.assertEqual(main(["init", "--project-root", tmp]), 0)
            memory = Path(tmp) / "docs/memory"
            subject_id = "MC-SUBJ-20260801-a1b2c3d4"
            first_id = "MC-DEC-20260801-11111111"
            second_id = "MC-DEC-20260801-22222222"
            (memory / "subjects.md").write_text(
                "# Subject Registry\n\n" + subject_unit(subject_id, "Audit chain"), encoding="utf-8",
            )
            first = render_active_entry(
                "decision", first_id, "First", "First invariant.", None, "project",
                ("user-confirmed",), subject=subject_id, facet="behavior",
            )
            second = render_active_entry(
                "decision", second_id, "Second", "Second invariant.", None, "project",
                ("user-confirmed",), subject=subject_id, facet="interface",
            )
            decisions = memory / "decisions.md"
            decisions.write_text("# Decisions\n\n" + first + "\n\n" + second + "\n", encoding="utf-8")
            (memory / "reconciliations.md").write_text(
                "# Reconciliations\n\n"
                "## MC-REC-20260801-abcdef12 — Distinct entries\n\n"
                "Status: active\nEntries:\n"
                f"- {first_id}\n- {second_id}\n"
                "Resolution: distinct\nEvidence:\n- user-confirmed\n",
                encoding="utf-8",
            )
            before = decisions.read_text(encoding="utf-8")
            code, output, _error = capture([
                "forget", "--id", first_id, "--mode", "hard", "--project-root", tmp,
            ])
            self.assertEqual(code, 0)
            self.assertIn("reconciliations.md:MC-REC-20260801-abcdef12", output)
            plan_id = re.search(r"Plan ID: ([0-9a-f]{16})", output).group(1)
            apply_code, _output, _error = capture([
                "forget", "--id", first_id, "--mode", "hard", "--apply",
                "--confirm-plan", plan_id, "--project-root", tmp,
            ])
            self.assertEqual(apply_code, 1)
            self.assertEqual(decisions.read_text(encoding="utf-8"), before)

    def test_id_forget_is_exact_and_blocks_live_relations(self):
        with tempfile.TemporaryDirectory() as tmp:
            with redirect_stdout(StringIO()):
                self.assertEqual(main(["init", "--project-root", tmp]), 0)
            memory = Path(tmp) / "docs/memory"
            subject_id = "MC-SUBJ-20260801-a1b2c3d4"
            (memory / "subjects.md").write_text(
                "# Subject Registry\n\n" + subject_unit(subject_id, "Precise forgetting"),
                encoding="utf-8",
            )
            target_id = "MC-DEC-20260801-11111111"
            target = render_active_entry(
                "decision", target_id, "Selected entry", "Selected body.", None,
                "project", ("user-confirmed",), subject=subject_id, facet="behavior",
            )
            reference = render_active_entry(
                "decision", "MC-DEC-20260801-22222222", "Referencing entry",
                "Keep this unit intact.", None, "project", ("user-confirmed",),
                subject=subject_id, facet="interface", supersedes=target_id,
            )
            decisions = memory / "decisions.md"
            decisions.write_text(
                "# Decisions\n\n" + target + "\n\n" + reference + "\n",
                encoding="utf-8",
            )
            before = decisions.read_text(encoding="utf-8")
            code, output, _error = capture([
                "forget", "--id", target_id, "--mode", "hard", "--project-root", tmp,
            ])
            self.assertEqual(code, 0)
            self.assertIn("Matched units: 1", output)
            self.assertIn("references selected Entry", output)
            plan_id = re.search(r"Plan ID: ([0-9a-f]{16})", output).group(1)
            apply_code, _output, _error = capture([
                "forget", "--id", target_id, "--mode", "hard", "--apply",
                "--confirm-plan", plan_id, "--project-root", tmp,
            ])
            self.assertEqual(apply_code, 1)
            self.assertEqual(decisions.read_text(encoding="utf-8"), before)

    def test_history_check_detected_and_not_detected_statuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            initialize_git_project(tmp)
            code, added, _error = capture([
                "add", "Committed preference.", "--type", "preference",
                "--evidence", "user-confirmed", "--project-root", tmp,
            ])
            self.assertEqual(code, 0)
            committed_id = re.search(r"MC-PREF-\d{8}-[0-9a-f]{8}", added).group(0)
            git(tmp, "add", ".")
            git(tmp, "commit", "-qm", "committed memory")
            code, detected, _error = capture([
                "forget", "--id", committed_id, "--mode", "hard", "--history-check",
                "--project-root", tmp,
            ])
            self.assertEqual(code, 0)
            self.assertIn("History inspection: reachable-copy-detected", detected)

            code, added, _error = capture([
                "add", "Uncommitted preference.", "--type", "preference",
                "--evidence", "user-confirmed", "--project-root", tmp,
            ])
            self.assertEqual(code, 0)
            uncommitted_id = re.search(r"MC-PREF-\d{8}-[0-9a-f]{8}", added).group(0)
            code, not_detected, _error = capture([
                "forget", "--id", uncommitted_id, "--mode", "hard", "--history-check",
                "--project-root", tmp,
            ])
            self.assertEqual(code, 0)
            self.assertIn("History inspection: no-reachable-copy-detected", not_detected)
            self.assertIn("not proof", not_detected)


class MergeAndDeterminismReleaseTests(unittest.TestCase):
    def test_exception_and_reconciliation_workflows_have_stable_complete_previews(self):
        with tempfile.TemporaryDirectory() as tmp:
            with redirect_stdout(StringIO()):
                self.assertEqual(main(["init", "--project-root", tmp]), 0)
            memory = Path(tmp) / "docs/memory"
            subject_id = "MC-SUBJ-20260801-a1b2c3d4"
            project_id = "MC-CON-20260801-11111111"
            area_id = "MC-CON-20260801-22222222"
            (memory / "subjects.md").write_text(
                "# Subject Registry\n\n" + subject_unit(subject_id, "Governance preview"), encoding="utf-8",
            )
            project_entry = render_active_entry(
                "constraint", project_id, "Baseline", "Project baseline.", None,
                "project", ("user-confirmed",), subject=subject_id, facet="behavior",
            )
            area_entry = render_active_entry(
                "constraint", area_id, "Area exception", "Area exception.", None,
                "area:backend", ("user-confirmed",), subject=subject_id, facet="behavior",
            )
            (memory / "constraints.md").write_text("# Constraints\n\n" + project_entry + "\n", encoding="utf-8")
            (memory / "areas").mkdir()
            area_path = memory / "areas/backend.md"
            area_path.write_text("# Backend\n\n" + area_entry + "\n", encoding="utf-8")

            command = [
                "exception", "add", area_id, "--to", project_id, "--project-root", tmp,
            ]
            code, first_preview, _error = capture(command)
            second_code, second_preview, _error = capture(command)
            self.assertEqual((code, second_code), (0, 0))
            self.assertEqual(first_preview, second_preview)
            self.assertIn("Blockers:\n- none", first_preview)
            self.assertIn(f"Exception-To: {project_id}", first_preview)
            self.assertRegex(first_preview, r"Plan ID: [0-9a-f]{16}")
            add_plan = re.search(r"Plan ID: ([0-9a-f]{16})", first_preview).group(1)
            manifest = memory / "manifest.md"
            original_manifest = manifest.read_text(encoding="utf-8")
            manifest.write_text(
                original_manifest.replace(
                    "initialized_with: memory-custodian 0.11.0",
                    "initialized_with: memory-custodian 0.11.0-audit",
                ),
                encoding="utf-8",
            )
            changed_code, changed_manifest_preview, _error = capture(command)
            self.assertEqual(changed_code, 0)
            self.assertNotEqual(
                add_plan,
                re.search(r"Plan ID: ([0-9a-f]{16})", changed_manifest_preview).group(1),
            )
            manifest.write_text(original_manifest, encoding="utf-8")

            reconcile = [
                "reconcile", "preview", "--entry", area_id, "--entry", project_id,
                "--resolution", "distinct", "--title", "Separate invariants",
                "--evidence", "user-confirmed", "--project-root", tmp,
            ]
            code, record_preview, _error = capture(reconcile)
            self.assertEqual(code, 0)
            self.assertIn("Reconciliation record preview:", record_preview)
            self.assertIn("Resolution: distinct", record_preview)
            self.assertIn("Blockers:\n- none", record_preview)
            self.assertRegex(record_preview, r"MC-REC-\d{8}-[0-9a-f]{8}")
            record_plan = re.search(r"Plan ID: ([0-9a-f]{16})", record_preview).group(1)

            subjects_path = memory / "subjects.md"
            original_subjects = subjects_path.read_text(encoding="utf-8")
            subjects_path.write_text(
                original_subjects.replace(
                    "- governance preview", "- governance preview revised",
                ),
                encoding="utf-8",
            )
            subject_code, subject_preview, _error = capture(reconcile)
            self.assertEqual(subject_code, 0)
            self.assertNotEqual(
                record_plan,
                re.search(r"Plan ID: ([0-9a-f]{16})", subject_preview).group(1),
            )
            subjects_path.write_text(original_subjects, encoding="utf-8")

            changed_scope = area_entry.replace("Scope: area:backend", "Scope: area:frontend")
            area_path.write_text("# Backend\n\n" + changed_scope + "\n", encoding="utf-8")
            changed_code, changed_preview, _error = capture(reconcile)
            self.assertEqual(changed_code, 0)
            self.assertIn("area:frontend", changed_preview)
            self.assertNotEqual(
                record_plan,
                re.search(r"Plan ID: ([0-9a-f]{16})", changed_preview).group(1),
            )
            area_path.write_text("# Backend\n\n" + area_entry + "\n", encoding="utf-8")

            duplicate_code, _output, duplicate_error = capture([
                "reconcile", "preview", "--entry", area_id,
                "--entry", area_id.lower(), "--resolution", "distinct",
                "--title", "Duplicate identity", "--evidence", "user-confirmed",
                "--project-root", tmp,
            ])
            self.assertEqual(duplicate_code, 2)
            self.assertIn("at least two distinct", duplicate_error)

            with_relation = area_entry.replace(
                "Evidence:\n", f"Exception-To: {project_id}\nEvidence:\n",
            )
            area_path.write_text("# Backend\n\n" + with_relation + "\n", encoding="utf-8")
            code, remove_preview, _error = capture([
                "exception", "remove", area_id, "--project-root", tmp,
            ])
            self.assertEqual(code, 0)
            self.assertIn("MC-CONFLICT-002", remove_preview)
            self.assertIn("Blockers:\n- none", remove_preview)
            remove_plan = re.search(r"Plan ID: ([0-9a-f]{16})", remove_preview).group(1)
            constraints_path = memory / "constraints.md"
            constraints_path.write_text(
                constraints_path.read_text(encoding="utf-8").replace(
                    "Status: active", "Status: superseded", 1,
                ),
                encoding="utf-8",
            )
            changed_code, changed_remove, _error = capture([
                "exception", "remove", area_id, "--project-root", tmp,
            ])
            self.assertEqual(changed_code, 0)
            self.assertNotIn("MC-CONFLICT-002", changed_remove)
            self.assertNotEqual(
                remove_plan,
                re.search(r"Plan ID: ([0-9a-f]{16})", changed_remove).group(1),
            )

    def test_reconciliation_distinct_rejects_duplicate_structural_owner(self):
        with tempfile.TemporaryDirectory() as tmp:
            with redirect_stdout(StringIO()):
                self.assertEqual(main(["init", "--project-root", tmp]), 0)
            memory = Path(tmp) / "docs/memory"
            subject_id = "MC-SUBJ-20260801-a1b2c3d4"
            first_id = "MC-CON-20260801-11111111"
            second_id = "MC-CON-20260801-22222222"
            (memory / "subjects.md").write_text(
                "# Subject Registry\n\n" + subject_unit(subject_id, "Duplicate owner"),
                encoding="utf-8",
            )
            entries = [
                render_active_entry(
                    "constraint", entry_id, title, body, None, "project",
                    ("user-confirmed",), subject=subject_id, facet="behavior",
                )
                for entry_id, title, body in (
                    (first_id, "First owner", "First."),
                    (second_id, "Second owner", "Second."),
                )
            ]
            (memory / "constraints.md").write_text(
                "# Constraints\n\n" + "\n\n".join(entries) + "\n", encoding="utf-8",
            )
            code, output, _error = capture([
                "reconcile", "preview", "--entry", first_id, "--entry", second_id,
                "--resolution", "distinct", "--title", "Not actually distinct",
                "--evidence", "user-confirmed", "--project-root", tmp,
            ])
            self.assertEqual(code, 0)
            self.assertNotIn("Blockers:\n- none", output)
            self.assertIn("different Scope + Subject + Facet identities", output)
            self.assertEqual(analyze_conflicts(memory).status.value, "CONFLICT")

    def test_exception_validation_rejects_invalid_structural_operands(self):
        with tempfile.TemporaryDirectory() as tmp:
            with redirect_stdout(StringIO()):
                self.assertEqual(main(["init", "--project-root", tmp]), 0)
            memory = Path(tmp) / "docs/memory"
            missing_subject = "MC-SUBJ-20260801-deadbeef"
            project_id = "MC-CON-20260801-11111111"
            area_id = "MC-CON-20260801-22222222"
            project_entry = render_active_entry(
                "constraint", project_id, "Invalid baseline", "Baseline.", None,
                "project", ("user-confirmed",), subject=missing_subject,
                facet="not-a-facet",
            )
            area_entry = render_active_entry(
                "constraint", area_id, "Invalid exception", "Exception.", None,
                "area:backend", ("user-confirmed",), subject=missing_subject,
                facet="not-a-facet",
            )
            (memory / "constraints.md").write_text(
                "# Constraints\n\n" + project_entry + "\n", encoding="utf-8",
            )
            (memory / "areas").mkdir()
            area_path = memory / "areas/backend.md"
            area_path.write_text("# Backend\n\n" + area_entry + "\n", encoding="utf-8")

            code, preview, _error = capture([
                "exception", "add", area_id, "--to", project_id,
                "--project-root", tmp,
            ])
            self.assertEqual(code, 0)
            self.assertNotIn("Blockers:\n- none", preview)
            self.assertIn("Subject must resolve exactly once", preview)
            self.assertIn("Invalid Facet 'not-a-facet'", preview)
            first_plan = re.search(r"Plan ID: ([0-9a-f]{16})", preview).group(1)
            (memory / "subjects.md").write_text(
                "# Subject Registry\n\n" + subject_unit(missing_subject, "Now registered"),
                encoding="utf-8",
            )
            _code, registered_preview, _error = capture([
                "exception", "add", area_id, "--to", project_id,
                "--project-root", tmp,
            ])
            self.assertNotEqual(
                first_plan,
                re.search(r"Plan ID: ([0-9a-f]{16})", registered_preview).group(1),
            )

            with_relation = area_entry.replace(
                "Evidence:\n", f"Exception-To: {project_id}\nEvidence:\n",
            )
            area_path.write_text("# Backend\n\n" + with_relation + "\n", encoding="utf-8")
            _code, invalid_remove, _error = capture([
                "exception", "remove", area_id, "--project-root", tmp,
            ])
            self.assertIn("result not established due to blockers", invalid_remove)
            self.assertNotIn("MC-CONFLICT-002", invalid_remove)
            (memory / "reconciliations.md").write_text(
                "# Reconciliations\n\n"
                "## MC-REC-20260801-abcdef12 — Invalid operands\n\n"
                "Status: active\nEntries:\n"
                f"- {project_id}\n- {area_id}\n"
                "Resolution: exception\nEvidence:\n- user-confirmed\n",
                encoding="utf-8",
            )
            result = analyze_conflicts(memory)
            self.assertEqual(result.status.value, "INVALID")
            self.assertTrue(any(item.code == "MC-CONFLICT-008" for item in result.findings))

    def test_governance_preview_requires_exact_protocol_and_schema(self):
        cases = (
            (lambda text: text.replace("protocol_version: 0.7", "protocol_version: 0.6"), "requires Protocol 0.7"),
            (lambda text: text.replace("protocol_version: 0.7", "protocol_version: 0.8"), "newer than this CLI"),
            (lambda text: re.sub(r"(?m)^- entry_schema_version:.*\n", "", text), "entry_schema_version: 1"),
            (
                lambda text: text.replace(
                    "- protocol_version: 0.7",
                    "- protocol_version: 0.6\n- protocol_version: 0.7",
                ),
                "Duplicate protocol metadata field: protocol_version",
            ),
            (
                lambda text: text.replace(
                    "- entry_schema_version: 1",
                    "- entry_schema_version: 1\n- entry_schema_version: 1",
                ),
                "Duplicate protocol metadata field: entry_schema_version",
            ),
            (
                lambda text: re.sub(
                    r"(?m)^(- project_id: .+)$", r"\1\n\1", text,
                ),
                "Duplicate protocol metadata field: project_id",
            ),
            (
                lambda text: re.sub(r"(?m)^- project_id:.*\n", "", text),
                "requires a valid UUIDv4 project_id",
            ),
            (
                lambda text: text.replace(
                    "- protocol_version: 0.7",
                    "- protocol_version:\n- protocol_version: 0.7",
                ),
                "Protocol metadata field protocol_version must not be empty",
            ),
            (
                lambda text: text.replace(
                    "- protocol_version: 0.7", "- protocol_version\n- protocol_version: 0.7",
                ),
                "Malformed protocol metadata line",
            ),
            (
                lambda text: text.rstrip()
                + "\n\n## MEMORYCUSTODIAN PROTOCOL\n- protocol_version: 0.6\n",
                "exactly one MemoryCustodian Protocol heading",
            ),
        )
        for mutate, expected in cases:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as tmp:
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["init", "--project-root", tmp]), 0)
                manifest = Path(tmp) / "docs/memory/manifest.md"
                manifest.write_text(mutate(manifest.read_text(encoding="utf-8")), encoding="utf-8")
                code, _output, error = capture([
                    "exception", "remove", "MC-CON-20260801-11111111",
                    "--project-root", tmp,
                ])
                self.assertEqual(code, 2)
                self.assertIn(expected, error)

    def test_invalid_superseded_replacement_is_rejected_in_merge_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory = initialize_git_project(tmp)
            subject_id = "MC-SUBJ-20260802-a1b2c3d4"
            old_id = "MC-DEC-20260802-11111111"
            replacement_id = "MC-DEC-20260802-22222222"
            (memory / "subjects.md").write_text(
                "# Subject Registry\n\n" + subject_unit(subject_id, "Superseded review"),
                encoding="utf-8",
            )
            old = render_active_entry(
                "decision", old_id, "Old", "Old decision.", None, "project",
                ("user-confirmed",), subject=subject_id, facet="behavior",
            )
            decisions = memory / "decisions.md"
            decisions.write_text("# Decisions\n\n" + old + "\n", encoding="utf-8")
            git(tmp, "add", ".")
            git(tmp, "commit", "-qm", "old decision")
            base = git(tmp, "rev-parse", "HEAD")

            git(tmp, "checkout", "-qb", "left")
            decisions.write_text(
                decisions.read_text(encoding="utf-8").replace(
                    "Decision:\nOld decision.", "Decision:\nOld decision changed on left.",
                ),
                encoding="utf-8",
            )
            git(tmp, "add", ".")
            git(tmp, "commit", "-qm", "extend old decision")

            git(tmp, "checkout", "-qb", "right", base)
            superseded = old.replace("Status: active", "Status: superseded").replace(
                "Evidence:\n", f"Superseded-By: {replacement_id}\nEvidence:\n",
            )
            replacement = render_active_entry(
                "decision", replacement_id, "Invalid replacement", "Replacement.", None,
                "project", ("user-confirmed",), subject="MC-SUBJ-20260802-deadbeef",
                facet="not-a-facet", supersedes=old_id,
            )
            decisions.write_text(
                "# Decisions\n\n" + replacement + "\n\n" + superseded + "\n",
                encoding="utf-8",
            )
            (memory / "reconciliations.md").write_text(
                "# Reconciliations\n\n"
                "## MC-REC-20260802-abcdef12 — Invalid replacement\n\n"
                "Status: active\nEntries:\n"
                f"- {old_id}\n- {replacement_id}\n"
                "Resolution: superseded\nEvidence:\n- user-confirmed\n",
                encoding="utf-8",
            )
            git(tmp, "add", ".")
            git(tmp, "commit", "-qm", "invalid superseded reconciliation")
            git(tmp, "checkout", "-q", "left")

            code, output, _error = capture([
                "check", "--conflicts", "--merge-base", "right", "--project-root", tmp,
            ])
            self.assertEqual(code, 1)
            self.assertIn("MC-MERGE-006", output)
            self.assertIn("superseded resolution is inconsistent", output)

    def test_subject_merged_requires_valid_current_target_operand(self):
        with tempfile.TemporaryDirectory() as tmp:
            with redirect_stdout(StringIO()):
                self.assertEqual(main(["init", "--project-root", tmp]), 0)
            memory = Path(tmp) / "docs/memory"
            source_subject = "MC-SUBJ-20260802-11111111"
            target_subject = "MC-SUBJ-20260802-22222222"
            historical_id = "MC-DEC-20260802-11111111"
            current_id = "MC-DEC-20260802-22222222"
            merged = (
                f"## {source_subject} — Old subject\n\nStatus: merged\nKind: concept\n"
                f"Merged-Into: {target_subject}\nEvidence:\n- user-confirmed\n\n"
                "Aliases:\n- old subject\n"
            )
            (memory / "subjects.md").write_text(
                "# Subject Registry\n\n" + merged + "\n"
                + subject_unit(target_subject, "Current subject"),
                encoding="utf-8",
            )
            historical = (
                f"## {historical_id} — Historical\n\nStatus: superseded\nScope: project\n"
                f"Subject: {source_subject}\nFacet: behavior\nEvidence:\n- user-confirmed\n\n"
                "Decision:\nHistorical.\n"
            )
            current = render_active_entry(
                "decision", current_id, "Invalid current", "Current.", None, "project",
                ("user-confirmed",), subject=target_subject, facet="not-a-facet",
            )
            (memory / "decisions.md").write_text(
                "# Decisions\n\n" + historical + "\n" + current + "\n", encoding="utf-8",
            )
            (memory / "reconciliations.md").write_text(
                "# Reconciliations\n\n"
                "## MC-REC-20260802-bcdefa12 — Invalid merge target\n\n"
                "Status: active\nEntries:\n"
                f"- {historical_id}\n- {current_id}\n"
                "Resolution: subject-merged\nEvidence:\n- user-confirmed\n",
                encoding="utf-8",
            )
            result = analyze_conflicts(memory)
            self.assertEqual(result.status.value, "INVALID")
            self.assertTrue(any(item.code == "MC-CONFLICT-008" for item in result.findings))

            valid_current = current.replace("Facet: not-a-facet", "Facet: behavior")
            (memory / "decisions.md").write_text(
                "# Decisions\n\n" + historical + "\n" + valid_current + "\n",
                encoding="utf-8",
            )
            valid_result = analyze_conflicts(memory)
            self.assertFalse(
                any(item.code == "MC-CONFLICT-008" for item in valid_result.findings)
            )

            unsupported_promoted = historical.replace(
                "Status: superseded", "Status: promoted",
            )
            (memory / "decisions.md").write_text(
                "# Decisions\n\n" + unsupported_promoted + "\n" + valid_current + "\n",
                encoding="utf-8",
            )
            promoted_result = analyze_conflicts(memory)
            self.assertTrue(
                any(item.code == "MC-CONFLICT-008" for item in promoted_result.findings)
            )

    def test_invalid_target_reconciliation_cannot_suppress_merge_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory = initialize_git_project(tmp)
            subject_id = "MC-SUBJ-20260801-a1b2c3d4"
            left_id = "MC-DEC-20260801-11111111"
            right_id = "MC-DEC-20260801-22222222"
            (memory / "subjects.md").write_text(
                "# Subject Registry\n\n" + subject_unit(subject_id, "Merge reconciliation"),
                encoding="utf-8",
            )
            git(tmp, "add", ".")
            git(tmp, "commit", "-qm", "subject")
            base = git(tmp, "rev-parse", "HEAD")

            git(tmp, "checkout", "-qb", "left")
            left = render_active_entry(
                "decision", left_id, "Left", "Left change.", None, "project",
                ("user-confirmed",), subject=subject_id, facet="behavior",
            )
            (memory / "decisions.md").write_text("# Decisions\n\n" + left + "\n", encoding="utf-8")
            git(tmp, "add", ".")
            git(tmp, "commit", "-qm", "left")

            git(tmp, "checkout", "-qb", "right", base)
            right = render_active_entry(
                "decision", right_id, "Right", "Right change.", None, "project",
                ("user-confirmed",), subject=subject_id, facet="interface",
            )
            (memory / "decisions.md").write_text("# Decisions\n\n" + right + "\n", encoding="utf-8")
            (memory / "reconciliations.md").write_text(
                "# Reconciliations\n\n"
                "## MC-REC-20260801-abcdef12 — Invalid cross-branch acknowledgement\n\n"
                "Status: active\nEntries:\n"
                f"- {left_id}\n- {right_id}\n"
                "Resolution: distinct\nEvidence:\n- user-confirmed\n",
                encoding="utf-8",
            )
            git(tmp, "add", ".")
            git(tmp, "commit", "-qm", "right with invalid reconciliation")
            git(tmp, "checkout", "-q", "left")

            code, output, _error = capture([
                "check", "--conflicts", "--merge-base", "right", "--project-root", tmp,
            ])
            self.assertEqual(code, 1)
            self.assertIn("Merge review status: CONFLICT", output)
            self.assertIn("MC-MERGE-006", output)
            self.assertIn("must each resolve exactly once", output)

    def test_partial_three_entry_relation_cannot_suppress_merge_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory = initialize_git_project(tmp)
            subject_id = "MC-SUBJ-20260801-a1b2c3d4"
            old_id = "MC-DEC-20260801-11111111"
            new_id = "MC-DEC-20260801-22222222"
            unrelated_id = "MC-DEC-20260801-33333333"
            (memory / "subjects.md").write_text(
                "# Subject Registry\n\n" + subject_unit(subject_id, "Partial relation"),
                encoding="utf-8",
            )
            old = (
                f"## {old_id} — Old\n\nStatus: superseded\nScope: project\n"
                f"Subject: {subject_id}\nFacet: behavior\nEvidence:\n- user-confirmed\n"
                f"Superseded-By: {new_id}\n\nDecision:\nOld.\n"
            )
            new = render_active_entry(
                "decision", new_id, "New", "New.", None, "project",
                ("user-confirmed",), subject=subject_id, facet="behavior",
                supersedes=old_id,
            )
            unrelated = render_active_entry(
                "decision", unrelated_id, "Unrelated", "Unrelated.", None, "project",
                ("user-confirmed",), subject=subject_id, facet="interface",
            )
            decisions = memory / "decisions.md"
            decisions.write_text(
                "# Decisions\n\n" + old + "\n" + new + "\n\n" + unrelated + "\n",
                encoding="utf-8",
            )
            git(tmp, "add", ".")
            git(tmp, "commit", "-qm", "base relation")
            base = git(tmp, "rev-parse", "HEAD")

            git(tmp, "checkout", "-qb", "left")
            decisions.write_text(
                decisions.read_text(encoding="utf-8").replace("Decision:\nOld.", "Decision:\nOld changed on left."),
                encoding="utf-8",
            )
            git(tmp, "add", ".")
            git(tmp, "commit", "-qm", "left changes old")

            git(tmp, "checkout", "-qb", "right", base)
            decisions.write_text(
                decisions.read_text(encoding="utf-8").replace(
                    "Decision:\nUnrelated.", "Decision:\nUnrelated changed on right.",
                ),
                encoding="utf-8",
            )
            (memory / "reconciliations.md").write_text(
                "# Reconciliations\n\n"
                "## MC-REC-20260801-abcdef12 — Partial supersession\n\n"
                "Status: active\nEntries:\n"
                f"- {old_id}\n- {new_id}\n- {unrelated_id}\n"
                "Resolution: superseded\nEvidence:\n- user-confirmed\n",
                encoding="utf-8",
            )
            git(tmp, "add", ".")
            git(tmp, "commit", "-qm", "right partial reconciliation")
            git(tmp, "checkout", "-q", "left")

            code, output, _error = capture([
                "check", "--conflicts", "--merge-base", "right", "--project-root", tmp,
            ])
            self.assertEqual(code, 1)
            self.assertIn("MC-MERGE-006", output)
            self.assertIn("requires exactly two Entry IDs", output)
            self.assertIn("MC-MERGE-REVIEW-001", output)

    def test_merge_review_detects_exact_owner_conflict(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory = initialize_git_project(tmp)
            subject_id = "MC-SUBJ-20260801-a1b2c3d4"
            (memory / "subjects.md").write_text(
                "# Subject Registry\n\n" + subject_unit(subject_id, "Merge owner"),
                encoding="utf-8",
            )
            git(tmp, "add", ".")
            git(tmp, "commit", "-qm", "subject")
            base = git(tmp, "rev-parse", "HEAD")

            git(tmp, "checkout", "-qb", "left")
            left = render_active_entry(
                "decision", "MC-DEC-20260801-11111111", "Left owner", "Left.", None,
                "project", ("user-confirmed",), subject=subject_id, facet="behavior",
            )
            (memory / "decisions.md").write_text("# Decisions\n\n" + left + "\n", encoding="utf-8")
            git(tmp, "add", ".")
            git(tmp, "commit", "-qm", "left owner")

            git(tmp, "checkout", "-qb", "right", base)
            right = render_active_entry(
                "decision", "MC-DEC-20260801-22222222", "Right owner", "Right.", None,
                "project", ("user-confirmed",), subject=subject_id, facet="behavior",
            )
            (memory / "decisions.md").write_text("# Decisions\n\n" + right + "\n", encoding="utf-8")
            git(tmp, "add", ".")
            git(tmp, "commit", "-qm", "right owner")
            git(tmp, "checkout", "-q", "left")

            code, output, _error = capture([
                "check", "--conflicts", "--merge-base", "right", "--project-root", tmp,
            ])
            self.assertEqual(code, 1)
            self.assertIn("Merge review status: CONFLICT", output)
            self.assertIn("MC-MERGE-003", output)

    def test_one_sided_custom_subject_does_not_claim_both_branches_changed(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory = initialize_git_project(tmp)
            base = git(tmp, "rev-parse", "HEAD")
            git(tmp, "checkout", "-qb", "right")
            (memory / "subjects.md").write_text(
                "# Subject Registry\n\n"
                + subject_unit("MC-SUBJ-20260801-22222222", "Right only"),
                encoding="utf-8",
            )
            git(tmp, "add", ".")
            git(tmp, "commit", "-qm", "right subject")
            git(tmp, "checkout", "-qb", "left", base)
            code, output, _error = capture([
                "check", "--conflicts", "--merge-base", "right", "--project-root", tmp,
            ])
            self.assertEqual(code, 0)
            self.assertIn("Merge review status: CLEAR", output)
            self.assertNotIn("both branches created", output)

    def test_merge_review_detects_registry_collision_and_two_sided_custom_review(self):
        for canonical_ref, expected_status, expected_code in (
            ("feature:shared", "CONFLICT", "MC-MERGE-001"),
            ("", "REVIEW", "MC-MERGE-REVIEW-003"),
        ):
            with self.subTest(canonical_ref=canonical_ref), tempfile.TemporaryDirectory() as tmp:
                memory = initialize_git_project(tmp)
                base = git(tmp, "rev-parse", "HEAD")
                git(tmp, "checkout", "-qb", "left")
                (memory / "subjects.md").write_text(
                    "# Subject Registry\n\n"
                    + subject_unit("MC-SUBJ-20260801-11111111", "Left custom", canonical_ref),
                    encoding="utf-8",
                )
                git(tmp, "add", ".")
                git(tmp, "commit", "-qm", "left subject")
                git(tmp, "checkout", "-qb", "right", base)
                (memory / "subjects.md").write_text(
                    "# Subject Registry\n\n"
                    + subject_unit("MC-SUBJ-20260801-22222222", "Right custom", canonical_ref),
                    encoding="utf-8",
                )
                git(tmp, "add", ".")
                git(tmp, "commit", "-qm", "right subject")
                git(tmp, "checkout", "-q", "left")
                code, output, _error = capture([
                    "check", "--conflicts", "--merge-base", "right", "--project-root", tmp,
                ])
                self.assertIn(f"Merge review status: {expected_status}", output)
                self.assertIn(expected_code, output)
                self.assertEqual(code, 1 if expected_status == "CONFLICT" else 0)

    def test_merge_review_detects_supersede_while_other_branch_extends_old_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory = initialize_git_project(tmp)
            subject_id = "MC-SUBJ-20260801-a1b2c3d4"
            old_id = "MC-DEC-20260801-aaaaaaaa"
            (memory / "subjects.md").write_text(
                "# Subject Registry\n\n" + subject_unit(subject_id, "Relation merge"),
                encoding="utf-8",
            )
            old = render_active_entry(
                "decision", old_id, "Old owner", "Old.", None, "project",
                ("user-confirmed",), subject=subject_id, facet="behavior",
            )
            (memory / "decisions.md").write_text("# Decisions\n\n" + old + "\n", encoding="utf-8")
            git(tmp, "add", ".")
            git(tmp, "commit", "-qm", "old owner")
            base = git(tmp, "rev-parse", "HEAD")

            git(tmp, "checkout", "-qb", "left")
            superseded = old.replace("Status: active", "Status: superseded").replace(
                "Evidence:\n", "Superseded-By: MC-DEC-20260801-bbbbbbbb\nEvidence:\n",
            )
            replacement = render_active_entry(
                "decision", "MC-DEC-20260801-bbbbbbbb", "Replacement", "New.", None,
                "project", ("user-confirmed",), subject=subject_id, facet="behavior",
                supersedes=old_id,
            )
            (memory / "decisions.md").write_text(
                "# Decisions\n\n" + replacement + "\n\n" + superseded + "\n",
                encoding="utf-8",
            )
            git(tmp, "add", ".")
            git(tmp, "commit", "-qm", "supersede old")

            git(tmp, "checkout", "-qb", "right", base)
            area = render_active_entry(
                "area", "MC-AREA-20260801-cccccccc", "Area extension", "Area rule.", None,
                "area:backend", ("user-confirmed",), subject=subject_id, facet="behavior",
            ).replace("Evidence:\n", f"Exception-To: {old_id}\nEvidence:\n")
            (memory / "areas").mkdir()
            (memory / "areas/backend.md").write_text("# Backend\n\n" + area + "\n", encoding="utf-8")
            git(tmp, "add", ".")
            git(tmp, "commit", "-qm", "extend old")
            git(tmp, "checkout", "-q", "left")

            code, output, _error = capture([
                "check", "--conflicts", "--merge-base", "right", "--project-root", tmp,
            ])
            self.assertEqual(code, 1)
            self.assertIn("MC-MERGE-004", output)

    def test_rendering_is_stable_across_hash_seeds(self):
        with tempfile.TemporaryDirectory() as tmp:
            with redirect_stdout(StringIO()):
                self.assertEqual(main(["init", "--project-root", tmp]), 0)
            command = [
                sys.executable, "-m", "memory_custodian.main", "read",
                "--task", "implementation", "--explain", "--names-only", "--no-local",
                "--project-root", tmp,
            ]
            outputs = []
            cli_root = str(Path(__file__).resolve().parents[1] / "cli")
            for seed in ("1", "987654"):
                env = dict(os.environ, PYTHONHASHSEED=seed, PYTHONPATH=cli_root)
                result = subprocess.run(
                    command, text=True, capture_output=True, check=True, env=env,
                )
                outputs.append(result.stdout)
            self.assertEqual(outputs[0], outputs[1])

    def test_optional_declaration_and_filesystem_order_are_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            with redirect_stdout(StringIO()):
                self.assertEqual(main(["init", "--project-root", tmp]), 0)
                self.assertEqual(main(["enable", "profile/a", "--project-root", tmp]), 0)
                self.assertEqual(main(["enable", "profile/b", "--project-root", tmp]), 0)
            args = [
                "read", "--task", "implementation", "--profile", "a", "--profile", "b",
                "--explain", "--names-only", "--no-local", "--project-root", tmp,
            ]
            first = capture(args)[1]
            manifest = Path(tmp) / "docs/memory/manifest.md"
            text = manifest.read_text(encoding="utf-8")
            first_decl = "- `profiles/a.md`\n  - activation: explicit-only"
            second_decl = "- `profiles/b.md`\n  - activation: explicit-only"
            text = text.replace(first_decl, "__PROFILE_A__").replace(
                second_decl, first_decl,
            ).replace("__PROFILE_A__", second_decl)
            manifest.write_text(text, encoding="utf-8")
            self.assertEqual(first, capture(args)[1])

            memory = Path(tmp) / "docs/memory"
            normal = analyze_conflicts(memory)
            original_rglob = Path.rglob

            def reversed_rglob(path: Path, pattern: str):
                return iter(reversed(list(original_rglob(path, pattern))))

            with patch.object(Path, "rglob", reversed_rglob):
                reversed_result = analyze_conflicts(memory)
            self.assertEqual(normal, reversed_result)


if __name__ == "__main__":
    unittest.main()
