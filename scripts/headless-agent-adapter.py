#!/usr/bin/env python3
"""Headless Agent Adapter for MemoryCustodian Benchmark Harness.

Executes a task prompt in a benchmark checkout directory using either:
1. `mock`: An offline deterministic heuristic agent for testing and verification without API keys.
2. `api`: Direct HTTP calls to OpenAI, Anthropic, or Gemini APIs using Python standard library.
3. `cli`: An external CLI tool command.

Input is accepted from stdin (provided by run-memory-bench.py) or --prompt.
Working directory is assumed to be the temporary checkout directory.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import shlex
import shutil
import subprocess
import sys
import urllib.error
import urllib.request


def find_repo_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for parent in [current, *current.parents]:
        if (parent / "benchmarks" / "benchmark-manifest.json").is_file():
            return parent
    return current


def read_checkout_files(checkout: Path, max_bytes: int = 100_000) -> dict[str, str]:
    files = {}
    ignored_parts = {".git", "__pycache__", ".DS_Store", "node_modules", ".tmp"}
    for path in sorted(checkout.rglob("*")):
        if path.is_file() and not path.is_symlink():
            rel = path.relative_to(checkout).as_posix()
            if any(part in ignored_parts for part in path.relative_to(checkout).parts):
                continue
            try:
                content = path.read_text(encoding="utf-8")
                if len(content.encode("utf-8")) <= max_bytes:
                    files[rel] = content
            except UnicodeDecodeError:
                continue
    return files


def apply_edits_from_text(checkout: Path, response_text: str) -> list[str]:
    """Parse FILE: <path> or markdown fences from text and write files."""
    edits: list[tuple[str, str]] = []

    # Pattern 1: Explicit header:
    # *** FILE: <path> ***
    # <code>
    # *** END FILE ***
    pattern_explicit = re.compile(
        r"\*\*\*\s*FILE:\s*([^\n\r]+?)\s*\*\*\*\s*\n(.*?)\n\*\*\*\s*END FILE\s*\*\*\*",
        re.DOTALL,
    )
    for match in pattern_explicit.finditer(response_text):
        rel_path = match.group(1).strip()
        code = match.group(2)
        if not code.endswith("\n"):
            code += "\n"
        edits.append((rel_path, code))

    # Pattern 2: Markdown fence with path header:
    # File: `path` or `path`:
    # ```python
    # <code>
    # ```
    pattern_fence = re.compile(
        r"(?:File:\s*`?([^\n\r`]+?)`?|###\s*`?([^\n\r`]+?)`?)\s*\n```[a-zA-Z0-9_-]*\n(.*?)\n```",
        re.DOTALL,
    )
    if not edits:
        for match in pattern_fence.finditer(response_text):
            rel_path = (match.group(1) or match.group(2)).strip()
            code = match.group(3)
            if not code.endswith("\n"):
                code += "\n"
            edits.append((rel_path, code))

    # Validate the whole response before making the first write. Model output
    # is untrusted even when the agent command itself was explicitly selected.
    targets = [_edit_target(checkout, rel_path) for rel_path, _ in edits]
    if len(set(targets)) != len(targets):
        raise ValueError("model response contains duplicate edit paths")
    target_set = set(targets)
    if any(parent in target_set for target in targets for parent in target.parents):
        raise ValueError("model response contains conflicting file and directory paths")
    for target, (_, code) in zip(targets, edits):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(code, encoding="utf-8")
    return [rel_path for rel_path, _ in edits]


def _edit_target(checkout: Path, rel_path: str) -> Path:
    """Accept only normalized, non-symlink paths inside the checkout."""
    path = PurePosixPath(rel_path)
    if (
        not rel_path
        or "\\" in rel_path
        or "\x00" in rel_path
        or path.is_absolute()
        or PureWindowsPath(rel_path).drive
        or any(part.casefold() in {"", ".", "..", ".git"} for part in rel_path.split("/"))
    ):
        raise ValueError("model edit path must be a normalized checkout-relative path")
    root = checkout.resolve()
    target = root.joinpath(*path.parts)
    current = root
    for index, part in enumerate(path.parts):
        current = current / part
        if current.is_symlink():
            raise ValueError("model edit path must not traverse a symlink")
        if index < len(path.parts) - 1 and current.exists() and not current.is_dir():
            raise ValueError("model edit ancestor must be a directory")
    if target.exists() and not target.is_file():
        raise ValueError("model edit target must be a regular file")
    return target


def run_mock(
    checkout: Path,
    repo_root: Path,
    task_id: str,
    strategy: str,
) -> int:
    """Offline heuristic or canned solution application."""
    if not task_id:
        task_id = checkout.name
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", task_id):
        print("mock: invalid task id", file=sys.stderr)
        return 1

    ref_dir = repo_root / "benchmarks" / "references" / task_id
    neg_dir = repo_root / "benchmarks" / "negatives" / task_id

    if strategy == "reference":
        if ref_dir.is_dir():
            _copy_tree(ref_dir, checkout)
            return 0
        print(f"mock: reference dir not found for {task_id}", file=sys.stderr)
        return 1

    if strategy == "starter":
        # Leave as starter
        return 0

    if strategy == "negative":
        if neg_dir.is_dir():
            _copy_tree(neg_dir, checkout)
            return 0
        return 0

    if strategy == "heuristic":
        # Heuristic smart agent: checks whether memory or manual docs exist in the checkout
        has_memory = (checkout / "docs" / "memory").is_dir()
        has_manual = (checkout / "docs" / "manual").is_dir()

        if has_memory or has_manual:
            # Memory or equivalent documentation is accessible.
            # Real agents reading the documentation discover the required facts.
            if ref_dir.is_dir():
                _copy_tree(ref_dir, checkout)
                return 0
        else:
            # Under NO_MEMORY or PLATFORM_FILE_ONLY, the required facts are absent.
            # If a negative exists (stale limit, bad default), apply it to reflect omission/stale use.
            if neg_dir.is_dir():
                _copy_tree(neg_dir, checkout)
                return 0
            # Otherwise leave starter unmodified (which fails hidden oracle)
            return 0

    print(f"unknown mock strategy: {strategy}", file=sys.stderr)
    return 1


def _copy_tree(src: Path, dst: Path) -> None:
    for path in src.rglob("*"):
        if path.is_file():
            rel = path.relative_to(src)
            if path.is_symlink():
                raise ValueError("mock source must not contain symlinks")
            target = _edit_target(dst, rel.as_posix())
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)


def run_api(
    checkout: Path,
    prompt: str,
    api_type: str,
    model: str,
    api_key: str,
    api_base: str | None,
) -> int:
    """Call an LLM API via urllib to solve the task."""
    files = read_checkout_files(checkout)
    file_manifest = "\n".join(f"- {path}" for path in files.keys())

    system_prompt = (
        "You are an expert coding agent participating in a repository benchmark.\n"
        "Read the repository structure, existing documentation, constraints, and code.\n"
        "Carefully follow instructions and constraints present in the repository.\n"
        "Return the complete updated file content for every file you need to create or modify.\n"
        "Format every updated file strictly as follows:\n\n"
        "*** FILE: path/to/file.ext ***\n"
        "<full file content here>\n"
        "*** END FILE ***\n"
    )

    context_blocks = []
    for rel_path, content in files.items():
        context_blocks.append(f"--- File: {rel_path} ---\n{content}\n")

    user_content = (
        f"Available files in current repository:\n{file_manifest}\n\n"
        f"Files content:\n{''.join(context_blocks)}\n\n"
        f"Task Prompt:\n{prompt}\n\n"
        "Provide your code updates following the specified *** FILE: ... *** format."
    )

    response_text = ""
    try:
        if api_type == "openai":
            base = api_base or os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1"
            url = f"{base.rstrip('/')}/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key or os.environ.get('OPENAI_API_KEY', '')}",
                "Content-Type": "application/json",
            }
            body = {
                "model": model or "gpt-4o",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                "temperature": 0.0,
            }
            req = urllib.request.Request(
                url,
                data=json.dumps(body).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                response_text = data["choices"][0]["message"]["content"]

        elif api_type == "anthropic":
            base = api_base or "https://api.anthropic.com/v1"
            url = f"{base.rstrip('/')}/messages"
            headers = {
                "x-api-key": api_key or os.environ.get("ANTHROPIC_API_KEY", ""),
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            }
            body = {
                "model": model or "claude-3-5-sonnet-20241022",
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_content}],
                "max_tokens": 4096,
                "temperature": 0.0,
            }
            req = urllib.request.Request(
                url,
                data=json.dumps(body).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                response_text = data["content"][0]["text"]

        elif api_type == "gemini":
            key = api_key or os.environ.get("GEMINI_API_KEY", "")
            mod = model or "gemini-1.5-pro"
            base = api_base or "https://generativelanguage.googleapis.com/v1beta"
            url = f"{base.rstrip('/')}/models/{mod}:generateContent?key={key}"
            headers = {"Content-Type": "application/json"}
            body = {
                "contents": [
                    {
                        "parts": [
                            {"text": f"{system_prompt}\n\n{user_content}"}
                        ]
                    }
                ],
                "generationConfig": {"temperature": 0.0},
            }
            req = urllib.request.Request(
                url,
                data=json.dumps(body).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                response_text = data["candidates"][0]["content"]["parts"][0]["text"]

        else:
            print(f"unsupported api type: {api_type}", file=sys.stderr)
            return 1

    except urllib.error.HTTPError as exc:
        # Provider error bodies and request URLs can contain credential values.
        print(f"api request failed (HTTP {exc.code})", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"api request exception: {type(exc).__name__}", file=sys.stderr)
        return 1

    try:
        if not isinstance(response_text, str):
            raise ValueError("model response must contain text")
        applied = apply_edits_from_text(checkout, response_text)
    except (OSError, ValueError) as exc:
        print(f"model edits rejected: {type(exc).__name__}", file=sys.stderr)
        return 1
    if not applied:
        print("warning: no file modifications parsed from model response", file=sys.stderr)
    return 0


def run_cli(checkout: Path, prompt: str, cli_cmd: str) -> int:
    """Execute an argv command; supply prompt on stdin and optional argv slot."""
    if not cli_cmd:
        print("cli provider requires --cli-cmd", file=sys.stderr)
        return 1
    try:
        cmd = [arg.replace("{prompt}", prompt) for arg in shlex.split(cli_cmd)]
        if not cmd:
            raise ValueError("empty command")
        proc = subprocess.run(
            cmd,
            cwd=checkout,
            text=True,
            input=prompt,
            check=False,
        )
    except (OSError, ValueError) as exc:
        print(f"cli command failed: {type(exc).__name__}", file=sys.stderr)
        return 1
    return proc.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Headless Agent Adapter for Memory Benchmark")
    parser.add_argument("--provider", choices=("mock", "api", "cli"), default="mock")
    parser.add_argument(
        "--mock-strategy",
        choices=("heuristic", "reference", "starter", "negative"),
        default="heuristic",
    )
    parser.add_argument("--api-type", choices=("openai", "anthropic", "gemini"), default="openai")
    parser.add_argument("--model", default="")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--api-base", default="")
    parser.add_argument("--cli-cmd", default="")
    parser.add_argument("--task-id", default="")
    parser.add_argument("--prompt", default="")
    parser.add_argument("--repo-root")

    args = parser.parse_args(argv)
    checkout = Path.cwd()
    repo_root = Path(args.repo_root) if args.repo_root else find_repo_root(checkout)

    prompt = args.prompt
    if not prompt and not sys.stdin.isatty():
        prompt = sys.stdin.read()

    if args.provider == "mock":
        if not args.repo_root and not (repo_root / "benchmarks" / "benchmark-manifest.json").is_file():
            installed_root = Path(__file__).resolve().parents[1]
            if (installed_root / "benchmarks" / "benchmark-manifest.json").is_file():
                repo_root = installed_root
        return run_mock(checkout, repo_root, args.task_id, args.mock_strategy)
    elif args.provider == "api":
        return run_api(checkout, prompt, args.api_type, args.model, args.api_key, args.api_base)
    elif args.provider == "cli":
        return run_cli(checkout, prompt, args.cli_cmd)

    return 1


if __name__ == "__main__":
    sys.exit(main())
