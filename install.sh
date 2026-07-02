#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./install.sh [codex|check]

Commands:
  codex   Symlink skills/memory-custodian into ${CODEX_HOME:-$HOME/.codex}/skills
  check   Print installation paths and verify required files exist
EOF
}

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
skill_dir="$repo_root/skills/memory-custodian"
command="${1:-codex}"

check_files() {
  test -f "$skill_dir/SKILL.md"
  test -f "$skill_dir/references/manifest-policy.md"
  test -f "$repo_root/adapters/codex/AGENTS.snippet.md"
  test -f "$repo_root/adapters/claude-code/CLAUDE.snippet.md"
  test -f "$repo_root/adapters/generic/agent-instructions.md"
  echo "MemoryCustodian files: OK"
  echo "Skill source: $skill_dir"
  echo "Codex skill target: ${CODEX_HOME:-$HOME/.codex}/skills/memory-custodian"
}

install_codex() {
  check_files
  target_root="${CODEX_HOME:-$HOME/.codex}/skills"
  mkdir -p "$target_root"
  ln -sfn "$skill_dir" "$target_root/memory-custodian"
  echo "Installed Codex skill: $target_root/memory-custodian"
  echo "Add adapters/codex/AGENTS.snippet.md to projects that use MemoryCustodian."
}

case "$command" in
  codex)
    install_codex
    ;;
  check)
    check_files
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
