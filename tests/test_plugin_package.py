import json
import os
from pathlib import Path
import subprocess
import unittest


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
        self.assertIn("memory-custodian 0.4.0", result.stdout)


if __name__ == "__main__":
    unittest.main()
