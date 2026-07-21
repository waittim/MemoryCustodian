#!/usr/bin/env bash
set -euo pipefail

TARGET_DIR="${1:-/tmp/memory-custodian-video-demo}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
FIXTURE_DIR="$REPO_ROOT/examples/nightnotes-video-demo"

if [ ! -d "$FIXTURE_DIR" ]; then
  echo "Error: Fixture directory $FIXTURE_DIR does not exist." >&2
  exit 1
fi

echo "Preparing NightNotes video demo at: $TARGET_DIR"
rm -rf "$TARGET_DIR"
mkdir -p "$TARGET_DIR"

cp -R "$FIXTURE_DIR/"* "$TARGET_DIR/"
if [ -f "$FIXTURE_DIR/.gitignore" ]; then
  cp "$FIXTURE_DIR/.gitignore" "$TARGET_DIR/"
fi

echo "NightNotes video demo ready at $TARGET_DIR"
