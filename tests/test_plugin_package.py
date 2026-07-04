import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]


class PluginPackageTests(unittest.TestCase):
    def test_codex_plugin_manifest_points_to_existing_components(self):
        manifest_path = ROOT / ".codex-plugin" / "plugin.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(manifest["name"], "memory-custodian")
        self.assertRegex(manifest["version"], r"^\d+\.\d+\.\d+$")
        self.assertEqual(manifest["skills"], "./skills/")
        self.assertTrue((ROOT / "skills" / "memory-custodian" / "SKILL.md").exists())

        interface = manifest["interface"]
        self.assertIn("Interactive", interface["capabilities"])
        self.assertIn("Read", interface["capabilities"])
        self.assertIn("Write", interface["capabilities"])
        for key in ("composerIcon", "logo"):
            asset = interface[key]
            self.assertTrue(asset.startswith("./assets/"), asset)
            self.assertTrue((ROOT / asset[2:]).exists(), asset)
        self.assertLessEqual(len(interface["defaultPrompt"]), 3)
        self.assertTrue(all(len(prompt) <= 128 for prompt in interface["defaultPrompt"]))

    def test_repo_marketplace_points_to_this_plugin(self):
        marketplace = json.loads((ROOT / ".agents" / "plugins" / "marketplace.json").read_text(encoding="utf-8"))
        self.assertEqual(marketplace["name"], "memory-custodian-dev")
        self.assertEqual(marketplace["interface"]["displayName"], "MemoryCustodian Dev")

        plugins = marketplace["plugins"]
        self.assertEqual(len(plugins), 1)
        entry = plugins[0]
        self.assertEqual(entry["name"], "memory-custodian")
        self.assertEqual(entry["category"], "Developer Tools")
        self.assertEqual(entry["policy"]["installation"], "AVAILABLE")
        self.assertEqual(entry["policy"]["authentication"], "ON_INSTALL")
        self.assertEqual(entry["source"], {"source": "url", "url": "./"})
        self.assertTrue((ROOT / ".codex-plugin" / "plugin.json").exists())

    def test_claude_plugin_metadata_points_to_existing_components(self):
        manifest_path = ROOT / ".claude-plugin" / "plugin.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(manifest["name"], "memory-custodian")
        self.assertRegex(manifest["version"], r"^\d+\.\d+\.\d+$")
        self.assertEqual(manifest["repository"], "https://github.com/waittim/MemoryCustodian")
        self.assertIn("skills", manifest["keywords"])
        self.assertTrue((ROOT / ".claude-plugin" / "plugin.json").exists())
        self.assertTrue((ROOT / "skills" / "memory-custodian" / "SKILL.md").exists())
        self.assertTrue(os.access(ROOT / "bin" / "memory-custodian", os.X_OK))
        self.assertTrue((ROOT / "adapters" / "claude-code" / "CLAUDE.snippet.md").exists())
        self.assertTrue((ROOT / "adapters" / "claude-code" / "install.md").exists())
        self.assertTrue((ROOT / ".claude-plugin" / "marketplace.json").exists())
        self.assertTrue((ROOT / "hooks" / "hooks.json").exists())
        self.assertTrue(os.access(ROOT / "hooks" / "session-start", os.X_OK))
        self.assertTrue(os.access(ROOT / "hooks" / "run-hook.cmd", os.X_OK))

    def test_claude_marketplace_points_to_this_plugin(self):
        marketplace = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
        self.assertEqual(marketplace["name"], "memory-custodian-dev")
        plugins = marketplace["plugins"]
        self.assertEqual(len(plugins), 1)
        entry = plugins[0]
        self.assertEqual(entry["name"], "memory-custodian")
        self.assertEqual(entry["source"], "./")
        self.assertEqual(entry["version"], "0.5.0")

    def test_session_start_hook_outputs_lightweight_context(self):
        result = subprocess.run(
            [str(ROOT / "hooks" / "session-start")],
            cwd=ROOT,
            env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(ROOT)},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        context = payload["hookSpecificOutput"]["additionalContext"]
        self.assertIn("docs/memory/manifest.md", context)
        self.assertIn("Read the memory brief.", context)
        self.assertIn("Do not load archive/ or inbox.md", context)
        self.assertNotIn("## Core Workflow", context)
        self.assertNotIn("## Memory Files", context)

    def test_plugin_cli_wrapper_runs_packaged_cli(self):
        wrapper = ROOT / "scripts" / "memory-custodian"
        self.assertTrue(os.access(wrapper, os.X_OK), "scripts/memory-custodian should be executable")

        result = subprocess.run(
            [str(wrapper), "--version"],
            cwd=ROOT,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("memory-custodian 0.5.0", result.stdout)

    def test_claude_plugin_bin_wrapper_runs_packaged_cli(self):
        wrapper = ROOT / "bin" / "memory-custodian"
        self.assertTrue(os.access(wrapper, os.X_OK), "bin/memory-custodian should be executable")

        result = subprocess.run(
            [str(wrapper), "--version"],
            cwd=ROOT,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("memory-custodian 0.5.0", result.stdout)

    def test_installer_can_install_claude_plugin_to_custom_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [str(ROOT / "install.sh"), "claude"],
                cwd=ROOT,
                env={**os.environ, "CLAUDE_HOME": str(Path(tmp) / ".claude")},
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            target = Path(tmp) / ".claude" / "skills" / "memory-custodian"
            self.assertTrue(target.is_symlink(), target)
            self.assertEqual(target.resolve(), ROOT)
            self.assertTrue((target / ".claude-plugin" / "plugin.json").exists())
            self.assertTrue((target / ".claude-plugin" / "marketplace.json").exists())
            self.assertTrue((target / "skills" / "memory-custodian" / "SKILL.md").exists())
            self.assertTrue((target / "hooks" / "session-start").exists())
            self.assertIn("Installed Claude Code plugin", result.stdout)

    def test_package_codex_plugin_creates_rootless_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "memory-custodian.zip"
            result = subprocess.run(
                [
                    str(ROOT / "scripts" / "package-codex-plugin.py"),
                    "--allow-dirty",
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(output.exists())
            with zipfile.ZipFile(output) as archive:
                names = set(archive.namelist())
            self.assertIn(".codex-plugin/plugin.json", names)
            self.assertIn("skills/memory-custodian/SKILL.md", names)
            self.assertIn("scripts/memory-custodian", names)
            self.assertIn("cli/memory_custodian/main.py", names)
            self.assertIn("bin/memory-custodian", names)
            self.assertNotIn(".claude-plugin/plugin.json", names)
            self.assertNotIn("hooks/session-start", names)
            self.assertNotIn("docs/memory/brief.md", names)
            self.assertNotIn("tests/test_plugin_package.py", names)


if __name__ == "__main__":
    unittest.main()
