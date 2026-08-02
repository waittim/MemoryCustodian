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
