#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./install.sh [codex|claude|check]

Commands:
  codex   Symlink skills/memory-custodian into ${CODEX_HOME:-$HOME/.codex}/skills
  claude  Symlink this plugin into ${CLAUDE_HOME:-$HOME/.claude}/skills
  check   Print installation paths and verify required files exist
EOF
}

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
skill_dir="$repo_root/skills/memory-custodian"
command="${1:-codex}"

check_files() {
  test -f "$skill_dir/SKILL.md"
  test -f "$repo_root/.codex-plugin/plugin.json"
  test -f "$repo_root/.claude-plugin/plugin.json"
  test -f "$repo_root/.claude-plugin/marketplace.json"
  test -f "$repo_root/.agents/plugins/marketplace.json"
  test -f "$repo_root/assets/memory-custodian.svg"
  test -x "$repo_root/scripts/memory-custodian"
  test -x "$repo_root/scripts/package-codex-plugin.py"
  test -x "$repo_root/bin/memory-custodian"
  test -f "$repo_root/hooks/hooks.json"
  test -x "$repo_root/hooks/session-start"
  test -x "$repo_root/hooks/run-hook.cmd"
  test -f "$skill_dir/references/manifest-policy.md"
  test -f "$repo_root/adapters/codex/AGENTS.snippet.md"
  test -f "$repo_root/adapters/claude-code/CLAUDE.snippet.md"
  test -f "$repo_root/adapters/generic/agent-instructions.md"
  echo "MemoryCustodian files: OK"
  echo "Codex plugin manifest: $repo_root/.codex-plugin/plugin.json"
  echo "Claude plugin metadata: $repo_root/.claude-plugin/plugin.json"
  echo "Repo marketplace: $repo_root/.agents/plugins/marketplace.json"
  echo "Skill source: $skill_dir"
  echo "Codex skill target: ${CODEX_HOME:-$HOME/.codex}/skills/memory-custodian"
  echo "Claude plugin target: ${CLAUDE_HOME:-$HOME/.claude}/skills/memory-custodian"
}

install_codex() {
  check_files
  target_root="${CODEX_HOME:-$HOME/.codex}/skills"
  mkdir -p "$target_root"
  ln -sfn "$skill_dir" "$target_root/memory-custodian"
  echo "Installed Codex skill: $target_root/memory-custodian"
  echo "Add adapters/codex/AGENTS.snippet.md to projects that use MemoryCustodian."
}

install_claude() {
  check_files
  target_root="${CLAUDE_HOME:-$HOME/.claude}/skills"
  mkdir -p "$target_root"
  ln -sfn "$repo_root" "$target_root/memory-custodian"
  echo "Installed Claude Code plugin: $target_root/memory-custodian"
  echo "Add adapters/claude-code/CLAUDE.snippet.md to projects that use MemoryCustodian."
}

case "$command" in
  codex)
    install_codex
    ;;
  claude)
    install_claude
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
