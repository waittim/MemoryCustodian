from pathlib import Path
import json
import shlex
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from benchmarks.runners.harness import (  # noqa: E402
    HarnessError,
    iter_files,
    load_manifest,
    load_tasks,
    validate_task,
)


class BenchmarkHarnessTests(unittest.TestCase):
    def test_integrity_command(self):
        result = self._run(["--check-integrity"])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("MemoryCustodian benchmark integrity: OK", result.stdout)
        self.assertIn("Tasks: 18", result.stdout)
        self.assertIn("Repositories: 2", result.stdout)
        self.assertIn("Conditions: 4", result.stdout)

    def test_dry_run_writes_no_result_and_makes_no_pass_claim(self):
        with tempfile.TemporaryDirectory() as name:
            record_dir = Path(name) / "results"
            result = self._run(
                [
                    "--dry-run",
                    "--suite",
                    "core",
                    "--runtime",
                    "codex",
                    "--condition",
                    "MEMORYCUSTODIAN",
                    "--task",
                    "field-ledger-export-cap",
                    "--record-dir",
                    str(record_dir),
                ]
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["dry_run"])
            self.assertEqual(payload["runtime"], "codex")
            self.assertEqual(payload["plans"][0]["evidence_class"], "plan")
            self.assertNotIn("status", payload)
            self.assertFalse(record_dir.exists())

    def test_live_mode_is_a_blocker(self):
        result = self._run(
            [
                "--mode",
                "live",
                "--runtime",
                "codex",
                "--condition",
                "NO_MEMORY",
                "--task",
                "field-ledger-export-cap",
            ]
        )
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload[0]["status"], "BLOCKER")
        self.assertEqual(payload[0]["evidence_class"], "live-runtime-unavailable")
        self.assertNotIn(str(ROOT), result.stdout)

    def test_offline_starter_and_reference_are_distinct(self):
        starter = self._run(
            [
                "--mode",
                "offline-fixture",
                "--runtime",
                "offline-fixture",
                "--condition",
                "MEMORYCUSTODIAN",
                "--task",
                "field-ledger-export-cap",
                "--grade",
                "starter",
            ]
        )
        reference = self._run(
            [
                "--mode",
                "offline-fixture",
                "--runtime",
                "offline-fixture",
                "--condition",
                "MEMORYCUSTODIAN",
                "--task",
                "field-ledger-export-cap",
                "--grade",
                "reference",
            ]
        )
        self.assertEqual(starter.returncode, 0, starter.stderr)
        self.assertEqual(reference.returncode, 0, reference.stderr)
        starter_payload = json.loads(starter.stdout)[0]
        reference_payload = json.loads(reference.stdout)[0]
        self.assertEqual(starter_payload["status"], "FAIL")
        self.assertEqual(starter_payload["failure_labels"], ["MEMORY_OMISSION"])
        self.assertEqual(starter_payload["evidence_class"], "offline-fixture")
        self.assertEqual(reference_payload["status"], "PASS")
        self.assertEqual(reference_payload["memory_label"], "MEMORY_NONE")
        self.assertNotIn(str(ROOT), reference.stdout)

    def test_result_ids_are_append_only(self):
        with tempfile.TemporaryDirectory() as name:
            command = [
                "--mode",
                "offline-fixture",
                "--runtime",
                "offline-fixture",
                "--condition",
                "MEMORYCUSTODIAN",
                "--task",
                "field-ledger-offline-plan",
                "--grade",
                "reference",
                "--record-dir",
                name,
            ]
            first = self._run(command)
            second = self._run(command)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 1, second.stdout + second.stderr)
            self.assertIn("already exists", second.stderr)
            self.assertEqual(len(list(Path(name).glob("*.json"))), 1)

    def test_command_adapter_is_not_a_named_runtime_result(self):
        with tempfile.TemporaryDirectory() as name:
            script = Path(name) / "apply.py"
            script.write_text(
                "import shutil\n"
                "import sys\n"
                "from pathlib import Path\n"
                "shutil.copy(sys.argv[1], Path.cwd() / sys.argv[2])\n",
                encoding="utf-8",
            )
            source = ROOT / "benchmarks/references/field-ledger-offline-plan/PLAN.md"
            command = " ".join(
                shlex.quote(part)
                for part in (sys.executable, str(script), str(source), "PLAN.md")
            )
            result = self._run(
                [
                    "--mode",
                    "command",
                    "--runtime",
                    "generic-reference",
                    "--condition",
                    "EQUIVALENT_MANUAL_DOCS",
                    "--task",
                    "field-ledger-offline-plan",
                    "--agent-cmd",
                    command,
                ]
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)[0]
            self.assertEqual(payload["status"], "PASS")
            self.assertEqual(payload["evidence_class"], "command-adapter")
            self.assertEqual(payload["runtime"], "generic-reference")
            self.assertNotEqual(payload["evidence_class"], "live-runtime")

    def test_visibility_cannot_escape_the_checkout(self):
        manifest = load_manifest(ROOT)
        task = json.loads(json.dumps(load_tasks(ROOT)[0]))
        task["condition_visibility"]["NO_MEMORY"]["hide"] = ["../outside"]
        issues = validate_task(task, ROOT, manifest)
        self.assertTrue(any("condition_visibility" in issue for issue in issues))

    def test_fixture_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            target = root / "target.txt"
            target.write_text("x", encoding="utf-8")
            link = root / "link.txt"
            try:
                link.symlink_to(target)
            except OSError:
                self.skipTest("symlinks are unavailable")
            with self.assertRaises(HarnessError):
                iter_files(root, ())

    def _run(self, args):
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "run-memory-bench.py"), *args],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )


if __name__ == "__main__":
    unittest.main()
