"""Contract evidence keeps its hashed bytes on every supported platform."""

from contextlib import redirect_stdout
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SPEC = importlib.util.spec_from_file_location("contract_record_encoding", ROOT / "scripts/check-benchmark-contracts.py")
cli = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cli)


class ContractRecordEncodingTests(unittest.TestCase):
    def test_written_evidence_bytes_match_inventory_with_unicode_and_lf(self):
        record = {"result_id": "contract__encoding__v2__unicode", "status": "PASS", "note": "é 中文 🙂"}
        with tempfile.TemporaryDirectory(prefix="contract-encoding-") as name:
            directory = Path(name) / "records"
            with patch.object(cli, "load_revision", return_value={}), patch.object(
                cli, "run_contracts", return_value=[record]
            ), redirect_stdout(io.StringIO()):
                status = cli.main(["--task", "encoding", "--task-version", "2",
                                   "--record-dir", str(directory), "--format", "json"])
            self.assertEqual(status, 0)
            path = directory / (record["result_id"] + ".json")
            raw = path.read_bytes()
            self.assertNotIn(b"\r\n", raw)
            self.assertEqual(json.loads(raw.decode("utf-8")), record)
            checksum, filename = (directory / "SHA256SUMS").read_text().strip().split("  ", 1)
            self.assertEqual(filename, path.name)
            self.assertEqual(checksum, hashlib.sha256(raw).hexdigest())


if __name__ == "__main__":
    unittest.main()
