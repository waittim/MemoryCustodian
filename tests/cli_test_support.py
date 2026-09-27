"""Compatibility helpers for legacy protocol regression tests.

The production CLI intentionally requires explicit staged migration selectors.
Older regression tests predate that public contract, so this module translates
their bare ``migrate`` call into prepare/canonicalize/finalize while the v0.12
contract tests exercise the real parser directly.
"""

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


def _confirmed_stage(base_args, stage):
    preview = StringIO()
    with redirect_stdout(preview):
        code = cli_main([*base_args, stage])
    if code != 0:
        print(preview.getvalue(), end="")
        return code
    match = re.search(r"(?m)^Plan ID: ([0-9a-f]{16})$", preview.getvalue())
    if not match:
        print(preview.getvalue(), end="")
        return code
    applied = StringIO()
    with redirect_stdout(applied):
        code = cli_main([
            *base_args, stage, "--apply", "--confirm-plan", match.group(1),
        ])
    if code != 0:
        print(applied.getvalue(), end="")
    return code


def _legacy_staged_migrate(args):
    apply = "--apply" in args
    confirm = _option(args, "--confirm-plan")
    base = []
    skip = False
    for value in args:
        if skip:
            skip = False
            continue
        if value == "--apply":
            continue
        if value == "--confirm-plan":
            skip = True
            continue
        base.append(value)

    # A confirmation obtained from the compatibility preview is always the
    # finalize Plan ID; prepare and canonicalize were already committed to
    # private migration state by that preview.
    if apply and confirm:
        return cli_main([
            *base, "--finalize", "--apply", "--confirm-plan", confirm,
        ])

    for stage in ("--prepare", "--canonicalize"):
        code = _confirmed_stage(base, stage)
        if code != 0:
            return code

    if not apply:
        return cli_main([*base, "--finalize"])

    preview = StringIO()
    with redirect_stdout(preview):
        code = cli_main([*base, "--finalize"])
    if code != 0:
        print(preview.getvalue(), end="")
        return code
    match = re.search(r"(?m)^Plan ID: ([0-9a-f]{16})$", preview.getvalue())
    if not match:
        print(preview.getvalue(), end="")
        return code
    return cli_main([
        *base, "--finalize", "--apply", "--confirm-plan", match.group(1),
    ])


def main(argv):
    args = list(argv)
    if (
        args
        and args[0] == "migrate"
        and not {"--prepare", "--canonicalize", "--finalize"}.intersection(args)
    ):
        return _legacy_staged_migrate(args)
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
