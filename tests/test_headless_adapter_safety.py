from contextlib import redirect_stderr
import importlib.util
import io
import json
from pathlib import Path
import shlex
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "headless_adapter_safety", ROOT / "scripts" / "headless-agent-adapter.py"
)
adapter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(adapter)


def edit(path, content="changed"):
    return f"*** FILE: {path} ***\n{content}\n*** END FILE ***\n"


class HeadlessAdapterSafetyTests(unittest.TestCase):
    def test_unsafe_response_is_rejected_before_any_write(self):
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory) / "checkout"
            checkout.mkdir()
            for unsafe in (
                "../escaped.py", "/tmp/escaped.py", "C:/escaped.py",
                "..\\escaped.py", "src/../escaped.py", "./file.py",
                "src//file.py", ".git/config", ".GIT/config",
            ):
                with self.subTest(path=unsafe), self.assertRaises(ValueError):
                    adapter.apply_edits_from_text(checkout, edit("valid.py") + edit(unsafe))
                self.assertFalse((checkout / "valid.py").exists())
            self.assertFalse((Path(directory) / "escaped.py").exists())

    def test_markdown_fence_cannot_escape_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                adapter.apply_edits_from_text(
                    Path(directory), "File: `../escaped.py`\n```python\ninvalid\n```\n"
                )

    def test_duplicate_and_invalid_ancestor_preflight(self):
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory)
            with self.assertRaises(ValueError):
                adapter.apply_edits_from_text(checkout, edit("same.py") + edit("same.py"))
            self.assertFalse((checkout / "same.py").exists())
            with self.assertRaises(ValueError):
                adapter.apply_edits_from_text(checkout, edit("new") + edit("new/child.py"))
            self.assertFalse((checkout / "new").exists())
            (checkout / "file").write_text("unchanged")
            with self.assertRaises(ValueError):
                adapter.apply_edits_from_text(checkout, edit("valid.py") + edit("file/child.py"))
            self.assertFalse((checkout / "valid.py").exists())

    def test_symlinks_cannot_be_read_or_written(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkout = root / "checkout"
            checkout.mkdir()
            outside = root / "outside"
            outside.mkdir()
            secret = outside / "data.txt"
            secret.write_text("external-data")
            try:
                (checkout / "linked.txt").symlink_to(secret)
                (checkout / "linked-dir").symlink_to(outside, target_is_directory=True)
            except OSError:
                self.skipTest("symlinks unavailable")
            self.assertEqual(adapter.read_checkout_files(checkout), {})
            for path in ("linked.txt", "linked-dir/data.txt", "linked-dir/new.txt"):
                with self.subTest(path=path), self.assertRaises(ValueError):
                    adapter.apply_edits_from_text(checkout, edit("valid.py") + edit(path))
                self.assertFalse((checkout / "valid.py").exists())
            self.assertEqual(secret.read_text(), "external-data")
            self.assertFalse((outside / "new.txt").exists())

    def test_cli_prompt_is_literal_argument_and_stdin(self):
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory)
            script = checkout / "capture.py"
            script.write_text(
                "import json, pathlib, sys\n"
                "pathlib.Path('captured.json').write_text(json.dumps([sys.argv[1], sys.stdin.read()]))\n"
            )
            prompt = 'quotes " ; $(touch SHELL_EXECUTED) `touch SHELL_EXECUTED` {braces}'
            command = shlex.join([sys.executable, str(script), "{prompt}"])
            self.assertEqual(adapter.run_cli(checkout, prompt, command), 0)
            self.assertEqual(json.loads((checkout / "captured.json").read_text()), [prompt, prompt])
            self.assertFalse((checkout / "SHELL_EXECUTED").exists())

    def test_cli_missing_executable_is_controlled_failure(self):
        with tempfile.TemporaryDirectory() as directory, redirect_stderr(io.StringIO()) as output:
            self.assertEqual(adapter.run_cli(Path(directory), "task", "missing-agent-command-123"), 1)
        self.assertIn("cli command failed: FileNotFoundError", output.getvalue())

    def test_api_errors_do_not_echo_response_or_url_credentials(self):
        credential = "sensitive-test-value"
        error = urllib.error.HTTPError(
            f"https://provider.invalid/?key={credential}", 401, credential, {},
            io.BytesIO(credential.encode()),
        )
        with tempfile.TemporaryDirectory() as directory, patch.object(
            adapter.urllib.request, "urlopen", side_effect=error
        ), redirect_stderr(io.StringIO()) as output:
            self.assertEqual(adapter.run_api(Path(directory), "task", "gemini", "model", credential, None), 1)
        self.assertIn("HTTP 401", output.getvalue())
        self.assertNotIn(credential, output.getvalue())

    def test_mock_task_id_cannot_traverse_reference_root(self):
        with tempfile.TemporaryDirectory() as directory, redirect_stderr(io.StringIO()):
            self.assertEqual(adapter.run_mock(Path(directory), ROOT, "../escape", "reference"), 1)


if __name__ == "__main__":
    unittest.main()
