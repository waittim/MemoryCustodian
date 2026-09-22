"""Unified Protocol 0.8 project and invocation audit facade."""

from __future__ import annotations

from contextlib import redirect_stdout
from dataclasses import asdict, dataclass
from io import StringIO
from pathlib import Path
import re

from . import check as check_cmd
from . import read as read_cmd
from .output import envelope, print_json
from .protocol import (
    CURRENT_PROTOCOL_VERSION,
    manifest_contract_metadata,
    project_id_from_manifest,
    read_managed_text,
    resolve_memory_dir,
    resolve_project_root,
)
from .transactions import binding_directory, unfinished_transaction_directories

AUDIT_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str
    path: str
    entry_id: str | None
    message: str
    remediation: str

    def canonical(self) -> dict[str, object]:
        return asdict(self)


def _finding(message: str, severity: str) -> Finding:
    lowered = message.casefold()
    if "transaction" in lowered:
        code = "MC-TRANSACTION-001"
    elif "subject" in lowered:
        code = "MC-SUBJECT-006"
    elif "conflict" in lowered:
        code = "MC-CONFLICT-004"
    elif "evidence" in lowered:
        code = "MC-EVIDENCE-001"
    elif "routing" in lowered or "route" in lowered:
        code = "MC-ROUTING-001"
    else:
        code = "MC-ENTRY-001"
    path = message.split(":", 1)[0] if ":" in message else "docs/memory"
    if not path.endswith(".md") and "/" not in path:
        path = "docs/memory"
    return Finding(code, severity, path.replace("\\", "/"), None, message, "Review the referenced managed-memory source and run audit again.")


def run(args) -> int:
    project_root = resolve_project_root(args.project_root)
    memory_dir = resolve_memory_dir(project_root, args.memory_dir)
    manifest_path = memory_dir / "manifest.md"
    manifest = read_managed_text(memory_dir, manifest_path) if manifest_path.exists() else ""
    protocol: str | None = None
    project_id: str | None = None
    findings: list[Finding] = []
    if manifest:
        try:
            metadata = manifest_contract_metadata(manifest, allow_legacy_entry_schema=True)
            protocol = metadata.get("protocol_version")
            project_id = project_id_from_manifest(manifest, required=False)
        except ValueError as exc:
            findings.append(_finding(str(exc), "ERROR"))
    else:
        findings.append(_finding("manifest.md is missing", "BLOCKER"))

    def collect_check(*, focused: str | None = None) -> None:
        values = {
            "project_root": str(project_root), "memory_dir": str(memory_dir),
            "privacy": bool(args.privacy or args.all) if focused is None else False,
            "security": bool(args.security or args.all) if focused is None else False,
            "routing": focused == "routing", "reachability": focused == "reachability",
            "freshness": focused == "freshness", "conflicts": focused == "conflicts",
            "merge_base": args.merge_base if focused == "conflicts" else None,
        }
        stream = StringIO()
        with redirect_stdout(stream):
            check_cmd.run(type("AuditCheckArgs", (), values)())
        section = "ERROR" if "check: FAILED" in stream.getvalue() else None
        for line in stream.getvalue().splitlines():
            if line == "Warnings:":
                section = "WARNING"
                continue
            quality = re.match(r"^- (MC-[A-Z]+-\d+) (INFO|WARNING|ERROR|BLOCKER): (.*)$", line)
            if quality:
                findings.append(Finding(
                    quality.group(1), quality.group(2), "docs/memory", None,
                    quality.group(3),
                    "Review the referenced managed-memory source and run audit again.",
                ))
                continue
            conflict = re.match(r"^- (MC-CONFLICT-\d+) (?:REVIEW|CONFLICT|INVALID): (.*)$", line)
            if conflict:
                findings.append(Finding(
                    conflict.group(1), "ERROR", "docs/memory", None,
                    conflict.group(2),
                    "Resolve or reconcile the structural conflict and run audit again.",
                ))
                continue
            if line.startswith("- ") and line not in {"- none", "- no findings"} and section:
                findings.append(_finding(line[2:], section))

    # The ordinary check owns baseline entry/evidence/relation/budget/privacy
    # validation. Focused quality views are additive; no single focused flag
    # is allowed to short-circuit the rest of a project audit.
    collect_check()
    selected = any(
        bool(getattr(args, name))
        for name in (
            "routing", "reachability", "freshness", "evidence", "privacy", "security",
            "relations", "subjects", "conflicts", "budgets", "local", "transactions",
            "erasure", "history_exposure",
        )
    )
    for focused in ("routing", "reachability", "freshness", "conflicts"):
        if args.all or not selected or bool(getattr(args, focused)):
            collect_check(focused=focused)

    bindings = [binding_directory(project_root, memory_dir, None)]
    if project_id:
        bindings.append(binding_directory(project_root, memory_dir, project_id))
    unfinished = tuple(
        directory for binding in bindings
        for directory in unfinished_transaction_directories(binding)
    )
    for directory in unfinished:
        findings.append(Finding(
            "MC-TRANSACTION-001", "BLOCKER", "private/transactions", None,
            f"Unfinished transaction {directory.name} requires recovery.",
            "Run `memory-custodian recover` and select the opaque transaction ID.",
        ))

    invocation: dict[str, object] | None = None
    if args.routing_input:
        read_args = type("AuditReadArgs", (), {
            "project_root": str(project_root), "memory_dir": str(memory_dir),
            "task": args.task, "path": args.path, "profile": args.profile,
            "area": args.area, "rule": args.rule, "strict_routing": args.strict_routing,
            "no_local": args.no_local, "explain": True, "names_only": True,
        })()
        read_stream = StringIO()
        with redirect_stdout(read_stream):
            read_code = read_cmd.run(read_args)
        read_text = read_stream.getvalue()
        completeness = next(
            (line.split(":", 1)[1].strip() for line in read_text.splitlines() if line.startswith("Routing completeness:")),
            "INVALID",
        )
        invocation = {"routing_completeness": completeness, "rendered_context": read_text}
        if read_code:
            findings.append(Finding(
                "MC-ROUTING-003", "ERROR", "docs/memory/manifest.md", None,
                f"Routing invocation is {completeness}.",
                "Supply the canonical task and required path or explicit module scope.",
            ))

    unique_findings = {
        (item.code, item.severity, item.path, item.entry_id, item.message): item
        for item in findings
    }
    findings = list(unique_findings.values())
    severities = {item.severity for item in findings}
    return_code = 2 if "BLOCKER" in severities else 1 if "ERROR" in severities else 0
    data = {
        "audit_schema_version": AUDIT_SCHEMA_VERSION,
        "project_id": project_id,
        "routing_configuration": "INVALID" if any(item.code.startswith("MC-ROUTING") and item.severity in {"ERROR", "BLOCKER"} for item in findings) else "VALID",
        "transactions": "recovery-required" if unfinished else "clean",
        "finding_counts": {
            severity: sum(item.severity == severity for item in findings)
            for severity in ("INFO", "WARNING", "ERROR", "BLOCKER")
        },
    }
    if invocation is not None:
        data["invocation"] = invocation
    canonical = [
        item.canonical()
        for item in sorted(
            findings,
            key=lambda item: (item.severity, item.code, item.path, item.message),
        )
    ]
    if args.format == "json":
        print_json(envelope(
            command="audit", protocol_version=protocol, return_code=return_code,
            rendered_text="", data=data, findings=canonical,
            disclaimers=["Forgetting governs managed memory; Git history and distributed copies are outside that guarantee."],
        ))
    else:
        print("MemoryCustodian audit: " + ("FAIL" if return_code else "REVIEW" if "WARNING" in severities else "PASS"))
        print(f"Protocol: {protocol or 'unavailable'}")
        print(f"Routing configuration: {data['routing_configuration']}")
        print(f"Transactions: {data['transactions']}")
        print("Findings:")
        for item in canonical or [{"severity": "INFO", "code": "none", "message": "none"}]:
            print(f"- [{item['severity']}] {item['code']}: {item['message']}")
    return return_code
