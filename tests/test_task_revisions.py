"""Offline task-revision contracts and fail-closed material loading."""

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from benchmarks.runners.harness import HarnessError, load_tasks  # noqa: E402
from benchmarks.runners import task_revisions as revisions  # noqa: E402


TASK = "field-ledger-split-export"
REVISION = Path("benchmarks/task-revisions") / TASK / "v2"
TASK_PATH = Path("benchmarks/tasks") / f"{TASK}.json"
SCRIPT_SPEC = importlib.util.spec_from_file_location(
    "task_revision_cli_tests", ROOT / "scripts/check-benchmark-contracts.py"
)
cli = importlib.util.module_from_spec(SCRIPT_SPEC)
SCRIPT_SPEC.loader.exec_module(cli)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class RevisionMaterials(unittest.TestCase):
    """Mutations affect isolated material copies, never historical sources."""

    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix="revision-tests-")
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name) / "root"
        self.root.mkdir()
        for relative in (
            "benchmarks/fixtures/field-ledger",
            "benchmarks/references/field-ledger-split-export",
            "benchmarks/oracles/field-ledger-split-export",
            "benchmarks/oracles/_lib",
            str(REVISION),
        ):
            shutil.copytree(ROOT / relative, self.root / relative)
        for relative in set(revisions.METHOD_PATHS) | {str(TASK_PATH), "benchmarks/benchmark-manifest.json"}:
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)
        self.descriptor_path = self.root / REVISION / "revision.json"
        self.descriptor = json.loads(self.descriptor_path.read_text())
        # A valid starting point prevents negative tests passing because of a
        # missing fixture or unrelated setup error.
        revisions.load_revision(self.root, TASK, 2)

    def write_descriptor(self, payload=None):
        self.descriptor_path.write_text(json.dumps(payload or self.descriptor), encoding="utf-8")

    def update_base_task(self, mutate):
        path = self.root / TASK_PATH
        task = json.loads(path.read_text())
        mutate(task)
        path.write_text(json.dumps(task), encoding="utf-8")
        self.descriptor["base_task_sha256"] = sha(path)
        self.write_descriptor()

    def load(self):
        return revisions.load_revision(self.root, TASK, 2)

    def marker_cases(self):
        marker = self.root / "cases-executed.txt"
        path = self.root / REVISION / "cases.py"
        path.write_text(path.read_text() + (
            "\nfrom pathlib import Path\nPath(" + repr(str(marker)) + ").write_text('executed')\n"
        ), encoding="utf-8")
        self.descriptor["cases_sha256"] = sha(path)
        self.write_descriptor()
        return marker

    def test_revision_identity_is_strict_and_old_task_stays_v1(self):
        revision = self.load()
        self.assertEqual(revision["base_task"]["task_version"], 1)
        self.assertEqual(revision["descriptor"]["task_version"], 2)
        self.assertEqual(len(load_tasks(ROOT)), 18)
        self.assertTrue(all(task["task_version"] == 1 for task in load_tasks(ROOT)))
        for version in (None, True, False, -1, 0, 1, 2.0, "2", "../../2"):
            with self.subTest(version=version), self.assertRaises(HarnessError):
                revisions.load_revision(self.root, TASK, version)
        for task_id in (None, "", "../field-ledger-split-export", "/tmp/task", "A", "a\\b", "a/../b"):
            with self.subTest(task_id=task_id), self.assertRaises(HarnessError):
                revisions.load_revision(self.root, task_id, 2)

    def test_descriptor_unknown_missing_and_mismatched_identity_are_rejected(self):
        mutations = (
            {"revision_format": True}, {"revision_format": "1"},
            {"task_id": "field-ledger-rounding"}, {"task_version": True},
            {"task_version": 3}, {"base_task_version": True}, {"base_task_version": 2},
            {"reason": " "}, {"reason": 3}, {"unknown_field": 1},
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                self.write_descriptor({**self.descriptor, **mutation})
                with self.assertRaises(HarnessError):
                    self.load()
        missing = dict(self.descriptor)
        missing.pop("oracle_sha256")
        self.write_descriptor(missing)
        with self.assertRaises(HarnessError):
            self.load()

    def test_duplicate_json_nonfinite_and_nonobject_descriptors_are_rejected(self):
        original = json.dumps(self.descriptor)
        variants = [
            original[:-1] + ', "task_version": 2}',
            original.replace('"reason": ' + json.dumps(self.descriptor["reason"]), '"reason": NaN'),
            original.replace('"reason": ' + json.dumps(self.descriptor["reason"]), '"reason": Infinity'),
            "[]", "null", "{not json}",
        ]
        for content in variants:
            with self.subTest(content=content[-40:]):
                self.descriptor_path.write_text(content, encoding="utf-8")
                with self.assertRaises(HarnessError):
                    self.load()

    def test_every_pinned_digest_is_verified(self):
        keys = [key for key in self.descriptor if key.endswith("_sha256")]
        self.assertEqual(len(keys), 7)
        for key in keys:
            with self.subTest(key=key):
                self.write_descriptor({**self.descriptor, key: "0" * 64})
                with self.assertRaises(HarnessError):
                    self.load()
        self.write_descriptor()
        (self.root / REVISION / "check.py").write_text("# changed oracle\n", encoding="utf-8")
        with self.assertRaises(HarnessError):
            self.load()

    def test_descriptor_and_revision_directory_symlinks_are_rejected(self):
        original = self.descriptor_path.read_bytes()
        target = Path(self.scratch.name) / "descriptor.json"
        target.write_bytes(original)
        self.descriptor_path.unlink()
        self.descriptor_path.symlink_to(target)
        with self.assertRaises(HarnessError):
            self.load()
        self.descriptor_path.unlink()
        self.descriptor_path.write_bytes(original)
        directory = self.root / REVISION
        moved = Path(self.scratch.name) / "revision-directory"
        directory.rename(moved)
        directory.symlink_to(moved, target_is_directory=True)
        with self.assertRaises(HarnessError):
            self.load()

    def test_base_material_parent_directory_symlinks_are_rejected(self):
        relatives = (
            "benchmarks/oracles/field-ledger-split-export",
            "benchmarks/references/field-ledger-split-export",
            "benchmarks/fixtures/field-ledger",
        )
        for index, relative in enumerate(relatives):
            with self.subTest(relative=relative):
                original = self.root / relative
                moved = Path(self.scratch.name) / f"outside-{index}"
                original.rename(moved)
                original.symlink_to(moved, target_is_directory=True)
                try:
                    with self.assertRaises(HarnessError):
                        self.load()
                finally:
                    original.unlink()
                    moved.rename(original)

    def test_base_paths_cannot_escape_before_reading_external_material(self):
        outside = Path(self.scratch.name) / "outside.py"
        outside.write_text("# private outside sentinel\n", encoding="utf-8")
        original_task = (self.root / TASK_PATH).read_bytes()
        for field, value in (
            ("oracle", "../outside.py"), ("oracle", str(outside)),
            ("reference", "../outside-dir"), ("fixture", "../outside-dir"),
        ):
            with self.subTest(field=field, value=value):
                (self.root / TASK_PATH).write_bytes(original_task)
                def change(task):
                    if field == "oracle":
                        task["success_oracle"]["script"] = value
                    elif field == "reference":
                        task["offline_expectations"]["reference_dir"] = value
                    else:
                        task["repo"]["root"] = value
                self.update_base_task(change)
                digest = revisions.digest
                def reject_external(path):
                    if not path.resolve().is_relative_to(self.root.resolve()):
                        self.fail("external file was read before validating its path")
                    return digest(path)
                with patch.object(revisions, "digest", side_effect=reject_external):
                    with self.assertRaises(HarnessError):
                        self.load()

    def test_hash_drift_is_rejected_before_cases_module_executes(self):
        marker = self.marker_cases()
        revision = self.load()
        path = self.root / REVISION / "cases.py"
        path.write_text(path.read_text() + "\n# drift after descriptor verification\n", encoding="utf-8")
        with self.assertRaises(HarnessError):
            revisions.load_cases(self.root, revision)
        self.assertFalse(marker.exists(), "unverified cases code executed")

    def test_base_source_drift_is_rejected_before_cases_module_executes(self):
        marker = self.marker_cases()
        revision = self.load()
        path = self.root / "benchmarks/oracles/field-ledger-split-export/check.py"
        path.write_text(path.read_text() + "\n# changed after revision load\n", encoding="utf-8")
        with self.assertRaises(HarnessError):
            revisions.load_cases(self.root, revision)
        self.assertFalse(marker.exists(), "case import preceded base-material verification")


class TaskRevisionExecutionTests(unittest.TestCase):
    def test_combined_status_preserves_all_infrastructure_outcomes(self):
        self.assertEqual(revisions.combined_status("PASS", "PASS"), "PASS")
        for pair in (("PASS", "FAIL"), ("FAIL", "PASS"), ("FAIL", "FAIL")):
            self.assertEqual(revisions.combined_status(*pair), "FAIL")
        for blocker in ("BLOCKER", "REVIEW", "INVALID", None):
            for other in ("PASS", "FAIL", "BLOCKER"):
                with self.subTest(blocker=blocker, other=other):
                    self.assertEqual(revisions.combined_status(blocker, other), "BLOCKER")
                    self.assertEqual(revisions.combined_status(other, blocker), "BLOCKER")

    def call_cli(self, args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = cli.main(["--task", TASK, "--task-version", "2"] + args)
        return status, stdout.getvalue(), stderr.getvalue()

    def test_fifteen_case_cli_records_report_and_append_only_guard(self):
        # The one real 15-case run exercises both actual oracles. Other tests
        # validate failures without repeating the subprocess matrix.
        with tempfile.TemporaryDirectory(prefix="contract-cli-tests-") as name:
            directory = Path(name)
            records_dir = directory / "records"
            report_file = directory / "report.md"
            args = ["--record-dir", str(records_dir), "--report-file", str(report_file), "--format", "json"]
            code, stdout, stderr = self.call_cli(args)
            self.assertEqual(code, 0, stderr)
            records = json.loads(stdout)
            self.assertEqual(len(records), 15)
            self.assertEqual(len({record["result_id"] for record in records}), 15)
            expected_names = {case["name"] for case in revisions.load_cases(ROOT, revisions.load_revision(ROOT, TASK, 2))}
            self.assertEqual({record["case"] for record in records}, expected_names)
            for record in records:
                with self.subTest(case=record["case"]):
                    self.assertEqual(record["status"], "PASS")
                    self.assertEqual(record["evidence_class"], "offline-contract")
                    self.assertEqual(record["task_version"], 2)
                    self.assertEqual(record["revision_descriptor"]["base_task_version"], 1)
                    self.assertEqual(record["grades"]["v2"]["oracle_status"], record["expected_status"])
                    self.assertEqual(record["grades"]["v2"]["failure_labels"], record["expected_labels"])
                    sources = record["source_sha256"]
                    self.assertIn(f"benchmarks/oracles/{TASK}/check.py", sources)
                    self.assertIn(str(REVISION / "check.py"), sources)
                    self.assertIn(str(REVISION / "public-contract.md"), sources)
                    self.assertIn(str(REVISION / "cases.py"), sources)
                    self.assertIn("benchmarks/oracles/_lib/oracle_support.py", sources)
                    self.assertTrue(set(revisions.METHOD_PATHS) <= set(sources))
                    self.assertEqual(record["revision_descriptor"]["base_oracle_sha256"], sources[f"benchmarks/oracles/{TASK}/check.py"])
                    self.assertEqual(record["revision_descriptor"]["oracle_sha256"], sources[str(REVISION / "check.py")])
            report = report_file.read_text()
            self.assertIn("Contract checks passed: 15/15", report)
            self.assertIn("not regrading", report)
            self.assertIn("no live-agent", report)
            inventory = (records_dir / "SHA256SUMS").read_text().splitlines()
            self.assertEqual(len(inventory), 15)
            expected_files = set()
            for line in inventory:
                checksum, filename = line.split("  ", 1)
                expected_files.add(filename)
                self.assertEqual(checksum, sha(records_dir / filename))
            self.assertEqual(expected_files, {path.name for path in records_dir.glob("*.json")})
            before = {path.name: path.read_bytes() for path in records_dir.iterdir()}
            with patch.object(cli, "run_contracts") as run:
                code, _, stderr = self.call_cli(args)
                self.assertEqual(code, 1)
                self.assertIn("new empty", stderr)
                run.assert_not_called()
                code, _, stderr = self.call_cli(["--record-dir", str(directory / "new-records"),
                                                "--report-file", str(report_file)])
                self.assertEqual(code, 1)
                self.assertIn("already exists", stderr)
                run.assert_not_called()
            self.assertEqual(before, {path.name: path.read_bytes() for path in records_dir.iterdir()})

    def test_cli_exit_distinguishes_contract_failure_and_blocker(self):
        for status, expected in (("FAIL", 1), ("BLOCKER", 2)):
            with self.subTest(status=status), patch.object(cli, "load_revision", return_value={}), patch.object(
                cli, "run_contracts", return_value=[{"status": status}]
            ):
                code, stdout, stderr = self.call_cli(["--format", "json"])
                self.assertEqual(code, expected, stderr)
                self.assertEqual(json.loads(stdout), [{"status": status}])


if __name__ == "__main__":
    unittest.main()
