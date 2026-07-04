#!/usr/bin/env python3
"""Package the MemoryCustodian Codex plugin as a deterministic rootless archive."""

from __future__ import annotations

import argparse
import gzip
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FORMAT = "zip"
DEFAULT_DATE_TIME = (1980, 1, 1, 0, 0, 0)
TAR_MTIME = 0

INCLUDE_PATHS = (
    ".codex-plugin",
    "assets",
    "bin",
    "cli",
    "scripts/memory-custodian",
    "skills",
    "README.md",
    "LICENSE",
)

EXCLUDED_SUFFIXES = (".pyc", ".pyo")
EXCLUDED_NAMES = {"__pycache__", ".DS_Store"}


def die(message: str) -> int:
    print(f"ERROR: {message}", file=sys.stderr)
    return 1


def infer_format(output: str | None, requested: str | None) -> str:
    if requested:
        return requested
    if output:
        if output.endswith(".tar.gz") or output.endswith(".tgz"):
            return "tar.gz"
        if output.endswith(".zip"):
            return "zip"
    return DEFAULT_FORMAT


def validate_output_format(output: Path, archive_format: str) -> None:
    output_name = output.name
    if archive_format == "zip" and output_name.endswith((".tar.gz", ".tgz")):
        raise ValueError(f"--output extension does not match --format zip: {output}")
    if archive_format == "tar.gz" and output.suffix == ".zip":
        raise ValueError(f"--output extension does not match --format tar.gz: {output}")


def read_version() -> str:
    manifest = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    version = manifest.get("version")
    if not isinstance(version, str) or not version:
        raise ValueError(".codex-plugin/plugin.json is missing a non-empty version")
    return version


def git_status() -> str:
    result = subprocess.run(
        ["git", "-C", str(ROOT), "status", "--porcelain", "--untracked-files=all"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git status failed")
    return result.stdout.strip()


def should_skip(path: Path) -> bool:
    return any(part in EXCLUDED_NAMES for part in path.parts) or path.suffix in EXCLUDED_SUFFIXES


def iter_payload_files() -> list[Path]:
    files: list[Path] = []
    for include in INCLUDE_PATHS:
        path = ROOT / include
        if not path.exists():
            raise FileNotFoundError(include)
        if path.is_file():
            if not should_skip(path):
                files.append(path)
            continue
        for child in path.rglob("*"):
            if child.is_file() and not should_skip(child.relative_to(ROOT)):
                files.append(child)
    return sorted(files, key=lambda item: item.relative_to(ROOT).as_posix())


def unix_mode(path: Path) -> int:
    return 0o755 if os.access(path, os.X_OK) else 0o644


def write_zip(output: Path, files: list[Path]) -> None:
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            relative = path.relative_to(ROOT).as_posix()
            info = zipfile.ZipInfo(relative, DEFAULT_DATE_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (unix_mode(path) & 0xFFFF) << 16
            archive.writestr(info, path.read_bytes())


def write_tar_gz(output: Path, files: list[Path]) -> None:
    with output.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=9, mtime=0) as gz:
            with tarfile.open(fileobj=gz, mode="w") as archive:
                for path in files:
                    relative = path.relative_to(ROOT).as_posix()
                    data = path.read_bytes()
                    info = tarfile.TarInfo(relative)
                    info.size = len(data)
                    info.mode = unix_mode(path)
                    info.uid = 0
                    info.gid = 0
                    info.uname = ""
                    info.gname = ""
                    info.mtime = TAR_MTIME
                    archive.addfile(info, fileobj=_BytesReader(data))


class _BytesReader:
    def __init__(self, data: bytes) -> None:
        self._data = data
        self._offset = 0

    def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            size = len(self._data) - self._offset
        chunk = self._data[self._offset : self._offset + size]
        self._offset += len(chunk)
        return chunk


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", help="Archive output path. Defaults to ../_tmp/memory-custodian-codex-packaging/memory-custodian-VERSION.zip.")
    parser.add_argument("--format", choices=("zip", "tar.gz"), help="Archive format. Defaults to zip or the --output extension.")
    parser.add_argument("--allow-dirty", action="store_true", help="Package even if the git working tree has uncommitted changes.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        version = read_version()
        if not args.allow_dirty:
            status = git_status()
            if status:
                print("Working tree has uncommitted changes:", file=sys.stderr)
                for line in status.splitlines():
                    print(f"  {line}", file=sys.stderr)
                return die("commit or stash changes first, or pass --allow-dirty")

        archive_format = infer_format(args.output, args.format)
        extension = "zip" if archive_format == "zip" else "tar.gz"
        output = Path(args.output) if args.output else ROOT.parent / "_tmp" / "memory-custodian-codex-packaging" / f"memory-custodian-{version}.{extension}"
        validate_output_format(output, archive_format)
        if archive_format == "zip" and output.suffix != ".zip":
            output = output.with_suffix(".zip")
        if archive_format == "tar.gz" and not output.name.endswith((".tar.gz", ".tgz")):
            output = Path(str(output) + ".tar.gz")
        output = output.expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)

        files = iter_payload_files()
        if archive_format == "zip":
            write_zip(output, files)
        else:
            write_tar_gz(output, files)

        print(f"Archive: {output}")
        print(f"Format:  {archive_format}")
        print(f"Version: {version}")
        print(f"Entries: {len(files)}")
        return 0
    except (OSError, RuntimeError, ValueError) as exc:
        return die(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
