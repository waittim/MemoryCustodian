#!/usr/bin/env python3
"""Check MemoryCustodian static scenarios and core skill contracts."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "evals" / "memory-custodian" / "eval-manifest.json"
ADAPTERS = (
    "adapters/codex/AGENTS.snippet.md",
    "adapters/claude-code/CLAUDE.snippet.md",
    "adapters/gemini/GEMINI.snippet.md",
    "adapters/generic/agent-instructions.md",
)
ADAPTER_PATHS = {
    "codex": "adapters/codex/AGENTS.snippet.md",
    "claude-code": "adapters/claude-code/CLAUDE.snippet.md",
    "gemini": "adapters/gemini/GEMINI.snippet.md",
    "generic": "adapters/generic/agent-instructions.md",
}
CROSS_AGENT_FIXTURE = ROOT / "evals" / "memory-custodian" / "cross-agent" / "shared-contract.json"
FIXTURE_PROJECT_FILES = CROSS_AGENT_FIXTURE.parent / "project-files"
LIVE_EVALUATION = ROOT / "evals" / "memory-custodian" / "live-evaluation.md"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _has_section(text: str, heading: str) -> bool:
    return any(line.strip() == heading for line in text.splitlines())


def _section_body(text: str, heading: str) -> list[str]:
    lines = text.splitlines()
    body: list[str] = []
    in_section = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            if in_section:
                break
            in_section = stripped == heading
            continue
        if in_section:
            body.append(line)
    return body


def _has_bullet(text: str, heading: str) -> bool:
    return any(line.lstrip().startswith("- ") for line in _section_body(text, heading))


def _check_skill_contract(config: dict) -> list[str]:
    skill_path = ROOT / config["skill"]
    issues: list[str] = []
    if not skill_path.exists():
        return [f"{config['skill']}: missing skill file"]

    skill_text = _read_text(skill_path)
    for contract in config["skill_contract"]:
        missing = [term for term in contract["terms"] if term not in skill_text]
        if missing:
            joined = ", ".join(repr(term) for term in missing)
            issues.append(f"{config['skill']}: contract {contract['id']} missing {joined}")
    return issues


def _check_scenarios(config: dict) -> list[str]:
    scenarios_dir = ROOT / config["scenarios_dir"]
    issues: list[str] = []
    if not scenarios_dir.exists():
        return [f"{config['scenarios_dir']}: missing scenarios directory"]

    for scenario_id in config["required_scenarios"]:
        relative = f"{config['scenarios_dir']}/{scenario_id}.md"
        path = ROOT / relative
        if not path.exists():
            issues.append(f"{relative}: missing required scenario")
            continue

        text = _read_text(path)
        for heading in config["required_sections"]:
            if not _has_section(text, heading):
                issues.append(f"{relative}: missing section {heading}")
        for heading in ("## Required Observations", "## Forbidden Outcomes"):
            if _has_section(text, heading) and not _has_bullet(text, heading):
                issues.append(f"{relative}: {heading} must contain bullet checks")
    return issues


def _check_adapters() -> list[str]:
    issues: list[str] = []
    forbidden = ("## Load by task", "### Planning / architecture / refactoring")
    for relative in ADAPTERS:
        path = ROOT / relative
        if not path.exists():
            issues.append(f"{relative}: missing adapter")
            continue
        text = _read_text(path)
        if "canonical task" not in text.casefold() or "touched/planned" not in text:
            issues.append(f"{relative}: missing explicit task/scope workflow")
        if "strict-routing" not in text:
            issues.append(f"{relative}: missing shared strict-routing invocation")
        for marker in forbidden:
            if marker in text:
                issues.append(f"{relative}: embeds a second routing table ({marker})")
    return issues


def _check_cross_agent_fixture() -> list[str]:
    issues: list[str] = []
    if not CROSS_AGENT_FIXTURE.exists():
        return ["evals/memory-custodian/cross-agent/shared-contract.json: missing fixture"]
    try:
        fixture = json.loads(_read_text(CROSS_AGENT_FIXTURE))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"{CROSS_AGENT_FIXTURE.relative_to(ROOT)}: invalid JSON: {exc}"]
    if fixture.get("agents") != ["codex", "claude-code", "gemini", "generic"]:
        issues.append("cross-agent fixture must cover the four supported adapters in stable order")
    required = {
        "file_set", "skipped_module_set", "entry_set", "order",
        "routing_completeness", "reason_codes", "module_reasons", "warnings",
        "context_sha256", "subject_ids", "conflict_status",
        "conflict_findings", "reconciliation_findings", "erasure_scope_field",
    }
    contract = fixture.get("expected_contract", {})
    missing = sorted(required - set(contract)) if isinstance(contract, dict) else sorted(required)
    if missing:
        issues.append("cross-agent fixture missing expected fields: " + ", ".join(missing))
    if not isinstance(fixture.get("expected_forget"), dict):
        issues.append("cross-agent fixture is missing the forgetting contract")
    if not isinstance(fixture.get("expected_conflict"), dict):
        issues.append("cross-agent fixture is missing the conflict contract")
    setup = fixture.get("setup", {})
    if not isinstance(setup, dict) or setup.get("local_mode") != "disabled":
        issues.append("cross-agent fixture must declare a disabled local mode")
    elif not setup.get("project_files"):
        issues.append("cross-agent fixture must declare its project file set")
    elif not isinstance(setup.get("seed_files"), list) or not setup["seed_files"]:
        issues.append("cross-agent fixture must declare its seeded memory files")
    if not issues:
        issues.extend(_run_cross_agent_fixture(fixture))
    if not LIVE_EVALUATION.exists() or "not a claim" not in _read_text(LIVE_EVALUATION):
        issues.append("live cross-agent evaluation recipe must remain explicit and non-aspirational")
    return issues


def _run_cross_agent_fixture(fixture: dict) -> list[str]:
    """Execute the shared CLI fixture once per named adapter contract.

    This is intentionally an offline deterministic fixture runner.  It proves
    that all four adapters point at the same CLI contract and that the
    resulting payload fields are stable across those adapter labels; it does not
    claim that four external agent runtimes were launched (that remains the
    job of ``live-evaluation.md``).
    """

    issues: list[str] = []
    input_data = fixture.get("input", {})
    expected = fixture.get("expected_contract", {})
    agents = fixture.get("agents", [])
    setup = fixture.get("setup", {})
    with (
        tempfile.TemporaryDirectory(prefix="memory-custodian-cross-agent-") as project,
        tempfile.TemporaryDirectory(prefix="memory-custodian-cross-agent-state-") as state,
    ):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT / "cli") + os.pathsep + env.get("PYTHONPATH", "")
        env["XDG_STATE_HOME"] = state
        env["LOCALAPPDATA"] = state
        init = subprocess.run(
            [sys.executable, "-m", "memory_custodian.main", "init", "--extended", "--project-root", project],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        if init.returncode != 0:
            return [f"cross-agent fixture setup failed: {init.stderr.strip() or init.stdout.strip()}"]
        memory_root = Path(project) / "docs" / "memory"
        for relative in setup.get("seed_files", []):
            source = FIXTURE_PROJECT_FILES / str(relative)
            target = memory_root / str(relative)
            if not source.is_file() or not source.resolve().is_relative_to(FIXTURE_PROJECT_FILES.resolve()):
                return [f"cross-agent fixture seed is missing or unsafe: {relative}"]
            if not target.resolve().is_relative_to(memory_root.resolve()):
                return [f"cross-agent fixture target is unsafe: {relative}"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
        manifest_path = memory_root / "manifest.md"
        manifest = manifest_path.read_text(encoding="utf-8")
        for replacement in setup.get("manifest_replacements", []):
            before, after = replacement["before"], replacement["after"]
            if manifest.count(before) != 1:
                return ["cross-agent fixture manifest replacement is not unique"]
            manifest = manifest.replace(before, after, 1)
        manifest_path.write_text(manifest, encoding="utf-8")
        actual_files = sorted(
            path.relative_to(memory_root).as_posix()
            for path in memory_root.rglob("*")
            if path.is_file()
        )
        declared_files = sorted(
            str(item).removeprefix("docs/memory/")
            for item in setup.get("project_files", [])
        )
        if actual_files != declared_files:
            issues.append(
                "cross-agent fixture project file set drift: "
                f"expected {declared_files!r}, got {actual_files!r}"
            )
        command = [
            sys.executable, "-m", "memory_custodian.main", "read",
            "--task", str(input_data.get("task", "default")),
            "--strict-routing", "--explain", "--no-local", "--format", "json",
            "--project-root", project,
        ]
        for path in input_data.get("paths", []):
            command.extend(("--path", str(path)))
        for name in input_data.get("explicit_rules", []):
            command.extend(("--rule", str(name)))
        for name in input_data.get("explicit_profiles", []):
            command.extend(("--profile", str(name)))
        for name in input_data.get("explicit_areas", []):
            command.extend(("--area", str(name)))
        baseline_values = None
        baseline_payload = None
        for agent in agents:
            if not isinstance(agent, str) or not agent:
                issues.append("cross-agent fixture contains an invalid adapter name")
                continue
            adapter_path = ADAPTER_PATHS.get(agent)
            if adapter_path is None or not (ROOT / adapter_path).is_file():
                issues.append(f"cross-agent fixture names an unknown or missing adapter: {agent}")
                continue
            adapter_env = dict(env)
            # This label makes the four deterministic executions explicit in
            # CI logs and leaves room for a future live adapter harness.  The
            # core CLI intentionally does not inspect it.
            adapter_env["MEMORY_CUSTODIAN_CROSS_AGENT"] = agent
            run = subprocess.run(
                command, cwd=ROOT, env=adapter_env, text=True,
                capture_output=True, check=False,
            )
            if run.returncode != 0:
                issues.append(
                    f"cross-agent fixture read failed for {agent}: "
                    f"{run.stderr.strip() or run.stdout.strip()}"
                )
                continue
            try:
                payload = json.loads(run.stdout)
            except json.JSONDecodeError as exc:
                issues.append(f"cross-agent fixture emitted invalid JSON for {agent}: {exc}")
                continue
            if payload.get("output_schema_version") != 1:
                issues.append(f"cross-agent fixture output schema drift for {agent}")
            if payload.get("command") != "read" or payload.get("status") != "PASS":
                issues.append(f"cross-agent fixture read result is not a PASS read for {agent}")
            if str(project) in run.stdout:
                issues.append(f"cross-agent fixture leaked the temporary project path for {agent}")
            data = payload.get("data", {})
            values = {
                "file_set": data.get("loaded_modules", []),
                "skipped_module_set": data.get("skipped_modules", []),
                "entry_set": data.get("loaded_entry_ids", []),
                "order": data.get("loaded_modules", []),
                "routing_completeness": data.get("routing_completeness"),
                "reason_codes": sorted({
                    item.get("reason") for item in data.get("module_dispositions", [])
                    if item.get("reason")
                }),
                "module_reasons": [
                    [item.get("module"), item.get("disposition"), item.get("reason")]
                    for item in data.get("module_dispositions", [])
                ],
                "warnings": data.get("warnings", []),
                "subject_ids": data.get("subject_ids", []),
                "conflict_status": data.get("conflict_status"),
                "conflict_findings": data.get("conflict_findings", []),
                "reconciliation_findings": data.get("reconciliation_findings", []),
            }
            context_sha = data.get("context_sha256")
            expected_hash = expected.get("context_sha256")
            if expected_hash and context_sha != expected_hash:
                issues.append(
                    f"cross-agent fixture context_sha256 drift for {agent}: "
                    f"expected {expected_hash}, got {context_sha}"
                )
            elif expected.get("context_sha256_field") and not context_sha:
                issues.append(f"cross-agent fixture context_sha256 field is absent for {agent}")
            for key in (
                "file_set", "skipped_module_set", "entry_set", "order", "routing_completeness",
                "reason_codes", "module_reasons", "warnings", "conflict_status", "conflict_findings",
                "reconciliation_findings",
            ):
                if values[key] != expected.get(key):
                    issues.append(
                        f"cross-agent fixture {key} drift for {agent}: "
                        f"expected {expected.get(key)!r}, got {values[key]!r}"
                    )
            if values["subject_ids"] != expected.get("subject_ids"):
                issues.append(
                    f"cross-agent fixture Subject IDs drift for {agent}: "
                    f"expected {expected.get('subject_ids')!r}, got {values['subject_ids']!r}"
                )
            if expected.get("erasure_scope_field") == "not-applicable-for-read" and "erasure_scope" in data:
                issues.append(f"cross-agent read fixture unexpectedly emitted an ErasureScope for {agent}")
            if baseline_values is None:
                baseline_values = values
                baseline_payload = payload
            elif values != baseline_values:
                issues.append(f"cross-agent fixture payload fields differ for {agent}")
            elif payload != baseline_payload:
                issues.append(f"cross-agent fixture JSON payload differs for {agent}")

        forgetting = fixture["expected_forget"]
        forget_command = [
            sys.executable, "-m", "memory_custodian.main", "forget",
            "--id", forgetting["entry_id"], "--mode", forgetting["mode"],
            "--project-root", project, "--format", "json",
        ]
        baseline_forget = None
        for agent in agents:
            adapter_env = dict(env, MEMORY_CUSTODIAN_CROSS_AGENT=agent)
            run = subprocess.run(
                forget_command, cwd=ROOT, env=adapter_env, text=True,
                capture_output=True, check=False,
            )
            try:
                payload = json.loads(run.stdout)
            except json.JSONDecodeError:
                issues.append(f"cross-agent forget preview did not emit JSON for {agent}")
                continue
            if run.returncode != 0 or payload.get("status") != "PASS":
                issues.append(f"cross-agent forget preview failed for {agent}")
            scope = payload.get("data", {}).get("erasure_scope")
            if scope != forgetting["erasure_scope"]:
                issues.append(f"cross-agent ErasureScope drift for {agent}: {scope!r}")
            if any(text in run.stdout for text in forgetting["forbidden_public_text"]):
                issues.append(f"cross-agent hard-forget preview leaked managed text for {agent}")
            if str(project) in run.stdout:
                issues.append(f"cross-agent hard-forget preview leaked the project path for {agent}")
            result = (scope, payload.get("findings"), payload.get("disclaimers"))
            if baseline_forget is None:
                baseline_forget = result
            elif result != baseline_forget:
                issues.append(f"cross-agent hard-forget result differs for {agent}")

        conflict = fixture["expected_conflict"]
        conflict_source = CROSS_AGENT_FIXTURE.parent / conflict["source"]
        if not conflict_source.is_file() or not conflict_source.resolve().is_relative_to(CROSS_AGENT_FIXTURE.parent.resolve()):
            return ["cross-agent conflict fixture source is missing or unsafe"]
        decisions_path = memory_root / "decisions.md"
        decisions_path.write_text(
            decisions_path.read_text(encoding="utf-8")
            + "\n" + conflict_source.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        conflict_command = [
            sys.executable, "-m", "memory_custodian.main", "audit",
            "--conflicts", "--project-root", project, "--format", "json",
        ]
        baseline_conflict = None
        for agent in agents:
            adapter_env = dict(env, MEMORY_CUSTODIAN_CROSS_AGENT=agent)
            run = subprocess.run(
                conflict_command, cwd=ROOT, env=adapter_env, text=True,
                capture_output=True, check=False,
            )
            try:
                payload = json.loads(run.stdout)
            except json.JSONDecodeError:
                issues.append(f"cross-agent conflict audit did not emit JSON for {agent}")
                continue
            findings = payload.get("findings", [])
            structural = next(
                (item for item in findings if item.get("code") == "MC-CONFLICT-001"),
                {},
            )
            details = structural.get("details", {})
            result = (
                run.returncode, payload.get("status"),
                payload.get("data", {}).get("conflict_status"),
                [item.get("code") for item in findings],
                details.get("entry_ids"), details.get("subject_id"),
                payload.get("data", {}).get("reconciliation_findings"),
            )
            expected_result = (
                conflict["exit_code"], conflict["status"],
                conflict["conflict_status"], conflict["finding_codes"],
                conflict["owner_entry_ids"], conflict["subject_id"],
                conflict["reconciliation_findings"],
            )
            if result != expected_result:
                issues.append(f"cross-agent conflict finding drift for {agent}: {result!r}")
            if str(project) in run.stdout:
                issues.append(f"cross-agent conflict audit leaked the project path for {agent}")
            if baseline_conflict is None:
                baseline_conflict = (result, findings)
            elif (result, findings) != baseline_conflict:
                issues.append(f"cross-agent conflict audit differs for {agent}")
    return issues


def main() -> int:
    config = json.loads(_read_text(MANIFEST))
    issues = _check_skill_contract(config)
    issues.extend(_check_scenarios(config))
    issues.extend(_check_adapters())
    issues.extend(_check_cross_agent_fixture())

    if issues:
        print("MemoryCustodian skill contract check: FAILED")
        for issue in issues:
            print(f"- {issue}")
        return 1

    print("MemoryCustodian skill contract check: OK")
    print(f"Scenarios: {len(config['required_scenarios'])}")
    print(f"Skill contracts: {len(config['skill_contract'])}")
    print(f"Adapter contracts: {len(ADAPTERS)}")
    print(f"Cross-agent fixture: offline CLI contract checked under {len(ADAPTER_PATHS)} adapter labels")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
