"""Adversarial coverage for check/status snapshot ownership."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from memory_custodian.main import main
from memory_custodian.snapshot import build_snapshot


def capture(argv: list[str]) -> tuple[int, str, str]:
    output, error = StringIO(), StringIO()
    with redirect_stdout(output), redirect_stderr(error):
        code = main(argv)
    return code, output.getvalue(), error.getvalue()


class CheckStatusSnapshotContractTests(unittest.TestCase):
    def _init(self, root: str) -> Path:
        code, output, error = capture(["init", "--project-root", root])
        self.assertEqual(code, 0, output + error)
        memory = Path(root) / "docs/memory"
        (memory / "brief.md").write_text(
            "# Project Brief\n\nPurpose:\nSnapshot test project.\n\n"
            "Current direction:\nCheck captured state.\n",
            encoding="utf-8",
        )
        return memory

    @staticmethod
    def _invalid_version(manifest: Path) -> str:
        return manifest.read_text(encoding="utf-8").replace(
            "- protocol_version: 0.7",
            "- protocol_version: 0.7.0",
            1,
        )

    def test_check_captures_valid_manifest_before_later_disk_corruption(self):
        with tempfile.TemporaryDirectory() as root:
            memory = self._init(root)
            manifest = memory / "manifest.md"
            valid = manifest.read_text(encoding="utf-8")

            def capture_then_corrupt(*args, **kwargs):
                snapshot = build_snapshot(*args, **kwargs)
                manifest.write_text(self._invalid_version(manifest), encoding="utf-8")
                return snapshot

            with patch(
                "memory_custodian.check.build_snapshot",
                side_effect=capture_then_corrupt,
            ) as builder:
                code, output, error = capture(["check", "--project-root", root])

            self.assertEqual(code, 0, output + error)
            self.assertEqual(builder.call_count, 1)
            self.assertNotIn("MC-ROUTING-007", output)
            self.assertIn("MemoryCustodian check: OK", output)
            manifest.write_text(valid, encoding="utf-8")

    def test_conflicts_captures_valid_manifest_before_later_disk_corruption(self):
        with tempfile.TemporaryDirectory() as root:
            memory = self._init(root)
            manifest = memory / "manifest.md"
            valid = manifest.read_text(encoding="utf-8")

            def capture_then_corrupt(*args, **kwargs):
                snapshot = build_snapshot(*args, **kwargs)
                manifest.write_text(self._invalid_version(manifest), encoding="utf-8")
                return snapshot

            with patch(
                "memory_custodian.check.build_snapshot",
                side_effect=capture_then_corrupt,
            ) as builder:
                code, output, error = capture([
                    "check", "--conflicts", "--project-root", root,
                ])

            self.assertEqual(code, 0, output + error)
            self.assertEqual(builder.call_count, 1)
            self.assertIn("Conflict status: CLEAR", output)
            self.assertNotIn("MC-ROUTING-007", output)
            manifest.write_text(valid, encoding="utf-8")

    def test_check_keeps_captured_invalid_manifest_after_later_repair(self):
        with tempfile.TemporaryDirectory() as root:
            memory = self._init(root)
            manifest = memory / "manifest.md"
            valid = manifest.read_text(encoding="utf-8")
            invalid = self._invalid_version(manifest)
            manifest.write_text(invalid, encoding="utf-8")

            def capture_then_repair(*args, **kwargs):
                snapshot = build_snapshot(*args, **kwargs)
                manifest.write_text(valid, encoding="utf-8")
                return snapshot

            with patch(
                "memory_custodian.check.build_snapshot",
                side_effect=capture_then_repair,
            ) as builder:
                code, output, error = capture(["check", "--project-root", root])

            self.assertEqual(code, 1, output + error)
            self.assertEqual(builder.call_count, 1)
            self.assertIn("MC-ROUTING-007 INVALID", output)

    def test_conflicts_keeps_captured_invalid_manifest_after_later_repair(self):
        with tempfile.TemporaryDirectory() as root:
            memory = self._init(root)
            manifest = memory / "manifest.md"
            valid = manifest.read_text(encoding="utf-8")
            manifest.write_text(self._invalid_version(manifest), encoding="utf-8")

            def capture_then_repair(*args, **kwargs):
                snapshot = build_snapshot(*args, **kwargs)
                manifest.write_text(valid, encoding="utf-8")
                return snapshot

            with patch(
                "memory_custodian.check.build_snapshot",
                side_effect=capture_then_repair,
            ) as builder:
                code, output, error = capture([
                    "check", "--conflicts", "--project-root", root,
                ])

            self.assertEqual(code, 1, output + error)
            self.assertEqual(builder.call_count, 1)
            self.assertIn("Conflict status: INVALID", output)
            self.assertIn("MC-ROUTING-007 INVALID", output)

    def test_each_check_mode_builds_one_snapshot(self):
        modes = (
            (),
            ("--conflicts",),
            ("--routing",),
            ("--reachability",),
            ("--freshness",),
        )
        for mode in modes:
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as root:
                self._init(root)
                with patch(
                    "memory_custodian.check.build_snapshot",
                    wraps=build_snapshot,
                ) as builder:
                    code, output, error = capture([
                        "check", *mode, "--project-root", root,
                    ])

                self.assertEqual(code, 0, output + error)
                self.assertEqual(builder.call_count, 1)

    def test_status_uses_one_snapshot_for_inventory_and_manifest(self):
        with tempfile.TemporaryDirectory() as root:
            memory = self._init(root)
            manifest = memory / "manifest.md"
            valid = manifest.read_text(encoding="utf-8")

            def capture_then_corrupt(*args, **kwargs):
                snapshot = build_snapshot(*args, **kwargs)
                manifest.write_text(self._invalid_version(manifest), encoding="utf-8")
                return snapshot

            with patch(
                "memory_custodian.status.build_snapshot",
                side_effect=capture_then_corrupt,
            ) as builder:
                code, output, error = capture(["status", "--project-root", root])

            self.assertEqual(code, 0, output + error)
            self.assertEqual(builder.call_count, 1)
            self.assertIn("Protocol version: 0.7 (current)", output)
            self.assertNotIn("Protocol metadata: INVALID", output)
            manifest.write_text(valid, encoding="utf-8")

    def test_check_and_status_do_not_repeat_snapshot_inventory_or_managed_reads(self):
        for command in ("check", "status"):
            with self.subTest(command=command), tempfile.TemporaryDirectory() as root:
                memory = self._init(root)
                from memory_custodian import snapshot as snapshot_module

                real_inventory = snapshot_module.managed_markdown_files
                real_read = snapshot_module.read_managed_text
                with patch(
                    "memory_custodian.snapshot.managed_markdown_files",
                    wraps=real_inventory,
                ) as inventory, patch(
                    "memory_custodian.snapshot.read_managed_text",
                    wraps=real_read,
                ) as managed_read:
                    code, output, error = capture([
                        command, "--project-root", root,
                    ])

                self.assertEqual(code, 0, output + error)
                self.assertEqual(inventory.call_count, 1)
                read_paths = [
                    Path(call.args[1]).resolve().relative_to(memory.resolve()).as_posix()
                    for call in managed_read.call_args_list
                ]
                self.assertEqual(len(read_paths), len(set(read_paths)))
                self.assertEqual(
                    set(read_paths),
                    {
                        item.relative
                        for item in build_snapshot(memory, Path(root)).files
                    },
                )

    def test_status_keeps_captured_invalid_manifest_after_later_repair(self):
        with tempfile.TemporaryDirectory() as root:
            memory = self._init(root)
            manifest = memory / "manifest.md"
            valid = manifest.read_text(encoding="utf-8")
            manifest.write_text(self._invalid_version(manifest), encoding="utf-8")

            def capture_then_repair(*args, **kwargs):
                snapshot = build_snapshot(*args, **kwargs)
                manifest.write_text(valid, encoding="utf-8")
                return snapshot

            with patch(
                "memory_custodian.status.build_snapshot",
                side_effect=capture_then_repair,
            ) as builder:
                code, output, error = capture(["status", "--project-root", root])

            self.assertEqual(code, 1, output + error)
            self.assertEqual(builder.call_count, 1)
            self.assertIn("Protocol metadata: INVALID", output)
            self.assertIn("manifest.md: INVALID", output)

    def test_check_reuses_one_captured_local_overlay_for_integrity(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as state:
            with patch.dict(os.environ, {"XDG_STATE_HOME": state}):
                self._init(root)
                self.assertEqual(capture(["local", "enable", "--project-root", root])[0], 0)
                self.assertEqual(capture(["local", "link", "--project-root", root])[0], 0)

                from memory_custodian import check as check_module
                from memory_custodian import integrity as integrity_module

                real_inspect = check_module.inspect_overlay
                captured = []

                def capture_overlay(*args, **kwargs):
                    overlay = real_inspect(*args, **kwargs)
                    captured.append(overlay)
                    return overlay

                real_integrity = integrity_module.cross_unit_integrity_findings
                passed_overlays = []

                def track_integrity(*args, **kwargs):
                    passed_overlays.append(kwargs.get("overlay"))
                    return real_integrity(*args, **kwargs)

                with patch(
                    "memory_custodian.check.inspect_overlay",
                    side_effect=capture_overlay,
                ), patch(
                    "memory_custodian.integrity.inspect_overlay",
                    side_effect=AssertionError("integrity recaptured local overlay"),
                ), patch(
                    "memory_custodian.check.cross_unit_integrity_findings",
                    side_effect=track_integrity,
                ):
                    code, output, error = capture([
                        "check", "--project-root", root,
                    ])

                self.assertEqual(code, 0, output + error)
                self.assertEqual(len(captured), 1)
                self.assertEqual(len(passed_overlays), 1)
                self.assertIs(passed_overlays[0], captured[0])

    def test_snapshot_aware_quality_and_integrity_do_not_rebuild_or_reread(self):
        with tempfile.TemporaryDirectory() as root:
            memory = self._init(root)
            snapshot = build_snapshot(memory, Path(root))
            with patch(
                "memory_custodian.quality.build_snapshot",
                side_effect=AssertionError("quality rebuilt supplied snapshot"),
            ):
                from memory_custodian.quality import reachability_findings, routing_findings

                routing_findings(memory, snapshot=snapshot)
                reachability_findings(memory, snapshot=snapshot)

            with patch(
                "memory_custodian.integrity.build_snapshot",
                side_effect=AssertionError("integrity rebuilt supplied snapshot"),
            ):
                from memory_custodian.integrity import cross_unit_integrity_findings

                cross_unit_integrity_findings(
                    Path(root), memory, snapshot.manifest_text, snapshot=snapshot,
                )


if __name__ == "__main__":
    unittest.main()
