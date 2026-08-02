"""Release-gate coverage for Protocol 0.7 audit findings."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from memory_custodian.conflicts import analyze_conflicts
from memory_custodian.entries import render_active_entry
from memory_custodian.main import main


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
    def test_mutually_exclusive_path_routes_are_reachably_ambiguous(self):
        with tempfile.TemporaryDirectory() as tmp:
            with redirect_stdout(StringIO()):
                self.assertEqual(main(["init", "--project-root", tmp]), 0)
            memory = Path(tmp) / "docs/memory"
            (memory / "areas").mkdir()
            (memory / "areas/client.md").write_text("# Client\n", encoding="utf-8")
            (memory / "areas/server.md").write_text("# Server\n", encoding="utf-8")
            manifest = memory / "manifest.md"
            manifest.write_text(
                manifest.read_text(encoding="utf-8").replace(
                    "### Enabled areas\n- None enabled.",
                    "### Enabled areas\n"
                    "- `areas/client.md`\n"
                    "  - activation: path-or-explicit\n"
                    "  - paths: `client/**`\n"
                    "  - exclusive-group: runtime\n"
                    "- `areas/server.md`\n"
                    "  - activation: path-or-explicit\n"
                    "  - paths: `server/**`\n"
                    "  - exclusive-group: runtime",
                ),
                encoding="utf-8",
            )
            code, output, error = capture([
                "read", "--task", "implementation", "--path", "client/app.py",
                "--path", "server/app.py",
                "--explain", "--names-only", "--project-root", tmp,
            ])
            self.assertEqual(code, 1)
            self.assertEqual(error, "")
            self.assertIn("Routing completeness: AMBIGUOUS", output)
            self.assertIn("MC-ROUTE-AMBIGUOUS", output)
            self.assertIn("brief.md", output)
            self.assertIn("constraints.md", output)
            self.assertIn("group 'runtime'", output)
            self.assertIn("areas/client.md", output)
            self.assertIn("Disposition: skipped", output)

            selected_code, selected, _error = capture([
                "read", "--task", "implementation", "--path", "client/app.py",
                "--path", "server/app.py",
                "--area", "client", "--explain", "--names-only",
                "--project-root", tmp,
            ])
            self.assertEqual(selected_code, 0)
            self.assertIn("Routing completeness: COMPLETE", selected)
            self.assertIn("MC-SKIP-EXCLUSIVE-SELECTION", selected)
            loaded_section = selected.split("Loaded:\n", 1)[1].split(
                "Skipped optional:\n", 1,
            )[0]
            self.assertIn("areas/client.md", loaded_section)
            self.assertNotIn("areas/server.md", loaded_section)

            mixed_code, mixed, _error = capture([
                "read", "--task", "implementation", "--path", "server/app.py",
                "--area", "client", "--explain", "--names-only",
                "--project-root", tmp,
            ])
            self.assertEqual(mixed_code, 0)
            self.assertIn("Routing completeness: COMPLETE", mixed)
            mixed_loaded = mixed.split("Loaded:\n", 1)[1].split(
                "Skipped optional:\n", 1,
            )[0]
            self.assertIn("areas/client.md", mixed_loaded)
            self.assertNotIn("areas/server.md", mixed_loaded)

            explicit_code, explicit_output, _error = capture([
                "read", "--task", "implementation", "--area", "client",
                "--area", "server", "--names-only", "--project-root", tmp,
            ])
            self.assertEqual(explicit_code, 1)
            self.assertIn("Routing completeness: AMBIGUOUS", explicit_output)

            strict_code, strict_output, strict_error = capture([
                "read", "--task", "implementation", "--path", "client/app.py",
                "--path", "server/app.py",
                "--strict-routing", "--names-only", "--project-root", tmp,
            ])
            self.assertEqual(strict_code, 2)
            self.assertIn("Context pack not approved for substantial work", strict_output)
            self.assertIn("completeness=AMBIGUOUS", strict_error)

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

    def test_exclusive_group_requires_path_activated_area(self):
        with tempfile.TemporaryDirectory() as tmp:
            with redirect_stdout(StringIO()):
                self.assertEqual(main(["init", "--project-root", tmp]), 0)
            manifest = Path(tmp) / "docs/memory/manifest.md"
            manifest.write_text(
                manifest.read_text(encoding="utf-8").replace(
                    "### Enabled areas\n- None enabled.",
                    "### Enabled areas\n"
                    "- `areas/backend.md`\n"
                    "  - activation: explicit-only\n"
                    "  - exclusive-group: runtime",
                ),
                encoding="utf-8",
            )
            code, output, error = capture([
                "read", "--task", "implementation", "--names-only",
                "--project-root", tmp,
            ])
            self.assertEqual(code, 2)
            self.assertIn("Routing completeness: INVALID", output)
            self.assertIn("exclusive-group requires path activation", output)
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
                "missing a valid UUIDv4 project_id",
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
