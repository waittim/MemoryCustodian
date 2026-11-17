"""A local installed-artifact smoke test, without an agent or global install."""

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == "posix", "local installer smoke uses POSIX shell and symlinks")
class InstalledWorkflowSmokeTests(unittest.TestCase):
    def test_copied_plugin_install_runs_real_scoped_cli_workflow(self):
        with tempfile.TemporaryDirectory(prefix="memory-installed-smoke-") as location:
            scratch = Path(location)
            distribution = scratch / "distribution"
            distribution.mkdir()
            # The installer checks both adapters' distribution metadata. Copy
            # actual runtime/support files, not tests or project memory.
            for relative in (
                "install.sh", "bin", "cli", "skills", "hooks", "adapters", "assets",
                ".codex-plugin", ".claude-plugin", ".agents/plugins", "GEMINI.md",
                "scripts/memory-custodian", "scripts/package-codex-plugin.py",
            ):
                source, target = ROOT / relative, distribution / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                if source.is_dir():
                    shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
                else:
                    shutil.copy2(source, target)
            agent_home, private_state = scratch / "agent-home", scratch / "private-state"
            project = scratch / "project"
            project.mkdir()
            (project / "README.md").write_text(
                "# Installed workflow fixture\n\nKeep fixture processing offline.\n", encoding="utf-8"
            )
            (project / "src").mkdir()
            (project / "src/demo.py").write_text("VALUE = 1\n", encoding="utf-8")
            environment = os.environ.copy()
            for name in ("PYTHONPATH", "PYTHONHOME", "CURSOR_PLUGIN_ROOT", "COPILOT_CLI", "CLAUDE_PLUGIN_ROOT"):
                environment.pop(name, None)
            # HOME and CODEX_HOME are deliberately left untouched. All installer
            # and MemoryCustodian state writes use documented custom roots.
            environment.update({
                "CLAUDE_HOME": str(agent_home), "XDG_STATE_HOME": str(private_state),
                "PYTHON": sys.executable, "PYTHONDONTWRITEBYTECODE": "1",
            })

            def process(command, *, expected=0, extra_env=None):
                result = subprocess.run(
                    [str(part) for part in command], cwd=project,
                    env={**environment, **(extra_env or {})}, text=True,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=False,
                )
                self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
                return result

            installed = agent_home / "skills/memory-custodian"
            process([distribution / "install.sh", "claude"])
            self.assertTrue(installed.is_symlink())
            self.assertEqual(installed.resolve(), distribution.resolve())
            skill = installed / "skills/memory-custodian/SKILL.md"
            skill_text = skill.read_text(encoding="utf-8")
            self.assertIn("name: memory-custodian", skill_text)
            self.assertIn("scripts/memory-custodian", skill_text)
            self.assertTrue((skill.parent / "references/routing-policy.md").is_file())
            self.assertEqual(
                hashlib.sha256(skill.read_bytes()).hexdigest(),
                hashlib.sha256((ROOT / "skills/memory-custodian/SKILL.md").read_bytes()).hexdigest(),
            )
            metadata = json.loads((installed / ".claude-plugin/plugin.json").read_text())
            self.assertEqual(metadata["name"], "memory-custodian")
            wrapper = installed / "bin/memory-custodian"
            version = process([wrapper, "--version"])
            self.assertIn(f"memory-custodian {metadata['version']}", version.stdout)
            hook = process([installed / "hooks/session-start"], extra_env={"CLAUDE_PLUGIN_ROOT": str(installed)})
            hook_text = json.loads(hook.stdout)["hookSpecificOutput"]["additionalContext"]
            self.assertIn("docs/memory/manifest.md", hook_text)
            self.assertIn("invoke the memory-custodian skill", hook_text)

            def invoke(*arguments, expected=0):
                result = process([
                    wrapper, *arguments, "--project-root", project, "--format", "json",
                ], expected=expected)
                payload = json.loads(result.stdout)
                self.assertEqual(payload["output_schema_version"], 1)
                self.assertNotIn(str(scratch), result.stdout)
                return payload

            uninitialized = invoke("read", "--task", "implementation", "--path", "src/demo.py",
                                   "--strict-routing", expected=2)
            self.assertEqual(uninitialized["status"], "FAIL")
            invoke("init", "--agent", "all")
            memory = project / "docs/memory"
            for filename in ("AGENTS.md", "CLAUDE.md", "GEMINI.md"):
                bootstrap = (project / filename).read_text(encoding="utf-8")
                self.assertIn("docs/memory/manifest.md", bootstrap)
                self.assertIn("docs/memory/brief.md", bootstrap)
                self.assertIn("--strict-routing", bootstrap)
                self.assertNotIn("## Core Workflow", bootstrap)
            # Curate the deliberately scaffolded brief from the fixture README,
            # as required by the installed Skill before relying on memory.
            (memory / "brief.md").write_text(
                "# Project Brief\n\nPurpose:\nA local installed-workflow fixture.\n\n"
                "Current direction:\nKeep fixture processing offline.\n", encoding="utf-8"
            )
            active_message = "Keep fixture processing offline."
            subject_args = ("subject", "add", "Installed workflow", "--kind", "concept", "--evidence", "repo:README.md")
            preview = invoke(*subject_args)
            self.assertNotRegex((memory / "subjects.md").read_text(), r"MC-SUBJ-\d{8}-[0-9a-f]{8}")
            plan_id = preview["data"]["plan"]["plan_id"]
            invoke(*subject_args, "--apply", "--confirm-plan", plan_id)
            subject_id = re.search(r"(?m)^## (MC-SUBJ-\d{8}-[0-9a-f]{8}) — Installed workflow$",
                                   (memory / "subjects.md").read_text()).group(1)
            invoke("add", active_message, "--type", "constraint", "--subject", subject_id,
                   "--facet", "security", "--evidence", "repo:README.md")
            candidate_message = "CANDIDATE_ONLY_INSTALLED_SMOKE_014"
            invoke("add", candidate_message, "--type", "constraint", "--candidate", "--evidence", "agent-observed")
            self.assertIn(candidate_message, (memory / "inbox.md").read_text())
            invoke("enable", "area/backend", "--path", "src/**")
            incomplete = invoke("read", "--task", "implementation", "--strict-routing", expected=1)
            self.assertEqual(incomplete["data"]["routing_completeness"], "INCOMPLETE")
            complete = invoke("read", "--task", "implementation", "--path", "src/demo.py",
                              "--strict-routing", "--explain", "--no-local")
            self.assertEqual(complete["data"]["routing_completeness"], "COMPLETE")
            context = complete["data"]["rendered_context"]
            self.assertIn(active_message, context)
            self.assertIn("areas/backend.md", context)
            self.assertNotIn(candidate_message, context)
            self.assertNotIn("## inbox.md", context)
            checked = invoke("check", "--routing", "--security", "--privacy")
            self.assertEqual(checked["status"], "PASS", checked)
            audit = invoke("audit", "--routing", "--subjects", "--conflicts", "--transactions",
                           "--privacy", "--security")
            self.assertEqual(audit["status"], "PASS", audit)
            self.assertEqual(audit["data"]["audit_schema_version"], 1)
            self.assertTrue((private_state / "memory-custodian").is_dir())
            self.assertFalse((distribution / "docs/memory").exists())


if __name__ == "__main__":
    unittest.main()
