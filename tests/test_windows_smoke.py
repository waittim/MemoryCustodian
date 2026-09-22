import json
import os
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests.cli_test_support import main
from memory_custodian.locking import state_root


class WindowsCliSmokeTests(unittest.TestCase):
    def _json(self, argv):
        stream = StringIO()
        with redirect_stdout(stream):
            code = main([*argv, "--format", "json"])
        self.assertEqual(stream.getvalue().count("\n"), 1)
        return code, json.loads(stream.getvalue())

    def test_init_read_add_and_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main(["init", "--project-root", tmp]), 0)
            memory = Path(tmp) / "docs" / "memory"
            (memory / "brief.md").write_text(
                "# Project Brief\n\nPurpose:\nCross-platform smoke test.\n",
                encoding="utf-8",
            )
            self.assertEqual(
                main(["add", "Work offline.", "--type", "constraint", "--project-root", tmp]),
                0,
            )
            with redirect_stdout(StringIO()):
                self.assertEqual(
                    main(["read", "--task", "implementation", "--names-only", "--project-root", tmp]),
                    0,
                )
                self.assertEqual(main(["check", "--project-root", tmp]), 0)

    def test_private_state_boundary_and_json_contract(self):
        """Exercise Windows-style state selection and path-safe JSON output.

        The test runs on every CI platform, but the state-root assertion uses
        the platform-specific resolver.  On Windows this covers the
        ``LOCALAPPDATA`` boundary; on POSIX it keeps the smoke test hermetic
        through ``XDG_STATE_HOME``.
        """

        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as state:
            with patch.dict(
                os.environ,
                {"LOCALAPPDATA": state, "XDG_STATE_HOME": state},
                clear=False,
            ):
                self.assertEqual(main(["init", "--project-root", tmp]), 0)
                memory = Path(tmp) / "docs" / "memory"
                (memory / "brief.md").write_text(
                    "# Project Brief\n\nPurpose:\nCross-platform private-state smoke.\n\n"
                    "Current direction:\nKeep JSON paths portable.\n",
                    encoding="utf-8",
                )

                code, status = self._json(["status", "--project-root", tmp])
                self.assertEqual(code, 0, status)
                self.assertEqual(status["output_schema_version"], 1)
                self.assertEqual(status["data"]["memory_directory"], "docs/memory")

                code, enabled = self._json(["local", "enable", "--project-root", tmp])
                self.assertEqual(code, 0, enabled)
                self.assertEqual(enabled["output_schema_version"], 1)
                encoded = json.dumps(enabled, ensure_ascii=False)
                self.assertNotIn(str(Path(tmp)), encoded)
                self.assertNotIn(str(Path(state)), encoded)

                code, audit = self._json([
                    "audit", "--all", "--project-root", tmp,
                ])
                self.assertEqual(code, 0, audit)
                self.assertEqual(audit["output_schema_version"], 1)
                self.assertEqual(audit["data"]["audit_schema_version"], 1)
                self.assertIn("erasure_scope", audit["data"])
                self.assertNotIn(str(Path(tmp)), json.dumps(audit, ensure_ascii=False))

                private_root = state_root()
                self.assertTrue(private_root.is_dir(), private_root)
                self.assertTrue(
                    any(path.is_file() for path in private_root.rglob("*")),
                    private_root,
                )

                code, read = self._json([
                    "read", "--task", "implementation", "--strict-routing",
                    "--names-only", "--no-local", "--project-root", tmp,
                ])
                self.assertEqual(code, 0, read)
                self.assertEqual(read["output_schema_version"], 1)
                self.assertEqual(read["data"]["routing_completeness"], "COMPLETE")
                self.assertNotIn(str(Path(tmp)), json.dumps(read, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
