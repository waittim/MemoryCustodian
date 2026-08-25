"""Compatibility helpers for exercising Protocol 0.6 from legacy regression tests."""

from contextlib import redirect_stdout
from io import StringIO
import hashlib
from pathlib import Path
import re

from memory_custodian.main import main as cli_main
from memory_custodian.entries import parse_structured_entries


def _option(args, name, default=None):
    return args[args.index(name) + 1] if name in args else default


def _subject_for_add(args):
    if not args or args[0] != "add" or "--candidate" in args or "--subject" in args:
        return args
    kind = _option(args, "--type", "inbox")
    if kind not in {"decision", "constraint", "tombstone", "do-not-use", "area"} and "--area" not in args:
        return args
    project_root = Path(_option(args, "--project-root", ".")).resolve()
    memory_dir = project_root / _option(args, "--memory-dir", "docs/memory")
    if "--supersedes" in args:
        old_id = _option(args, "--supersedes")
        for path in memory_dir.rglob("*.md"):
            for entry in parse_structured_entries(path, path.read_text(encoding="utf-8")):
                if entry.entry_id.casefold() == old_id.casefold() and entry.fields.get("Subject"):
                    return [*args, "--subject", entry.fields["Subject"], "--facet", entry.fields["Facet"]]
    message = args[1] if len(args) > 1 else kind
    token = hashlib.sha256(f"{kind}\0{message}".encode("utf-8")).hexdigest()[:12]
    title = f"Regression subject {token}"
    subject_args = [
        "subject", "add", title,
        "--kind", "concept",
        "--evidence", "user-confirmed",
        "--project-root", str(project_root),
    ]
    if "--memory-dir" in args:
        subject_args.extend(["--memory-dir", _option(args, "--memory-dir")])
    captured = StringIO()
    with redirect_stdout(captured):
        code = cli_main(subject_args)
    if code != 0:
        return args
    match = re.search(r"Plan ID: ([0-9a-f]{16})", captured.getvalue())
    if not match:
        return args
    with redirect_stdout(StringIO()):
        code = cli_main([*subject_args, "--apply", "--confirm-plan", match.group(1)])
    if code != 0:
        return args
    subjects = (memory_dir / "subjects.md").read_text(encoding="utf-8")
    subject_id = re.search(
        rf"(?m)^## (MC-SUBJ-[^\s]+) — {re.escape(title)}$",
        subjects,
    ).group(1)
    return [*args, "--subject", subject_id, "--facet", "behavior"]


def main(argv):
    args = list(argv)
    if args and args[0] == "add" and "--evidence" not in args:
        kind = args[args.index("--type") + 1] if "--type" in args else "inbox"
        args.extend([
            "--evidence",
            "conversation-unconfirmed" if kind == "inbox" else "user-confirmed",
        ])
    args = _subject_for_add(args)
    preview_first = (
        args
        and args[0] in {"compact", "forget", "migrate"}
        and "--apply" in args
        and "--confirm-plan" not in args
    ) or (
        args
        and args[0] == "init"
        and "--replace-existing" in args
        and "--apply" in args
        and "--confirm-plan" not in args
    )
    if preview_first:
        preview_args = [value for value in args if value != "--apply"]
        captured = StringIO()
        with redirect_stdout(captured):
            code = cli_main(preview_args)
        if code != 0:
            return code
        match = re.search(r"Plan ID: ([0-9a-f]{16})", captured.getvalue())
        if match:
            args.extend(["--confirm-plan", match.group(1)])
    return cli_main(args)
