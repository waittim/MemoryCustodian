"""Compatibility helpers for exercising Protocol 0.6 from legacy regression tests."""

from contextlib import redirect_stdout
from io import StringIO
import re

from memory_custodian.main import main as cli_main


def main(argv):
    args = list(argv)
    if args and args[0] == "add" and "--evidence" not in args:
        kind = args[args.index("--type") + 1] if "--type" in args else "inbox"
        args.extend([
            "--evidence",
            "conversation-unconfirmed" if kind == "inbox" else "user-confirmed",
        ])
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
