# 0.14.0 candidate package validation

Date: 2026-11-17. Source: `d125910bc54866b2dc77a71fc6730b676f748f03`.
This is candidate validation, not publication. No tag or release was created.

A detached, clean Git worktree supplied the actual packaging script and all
payload files. The normal clean-tree check remained enabled. Each format was
built twice with Python 3.13; the two builds within each format were identical.

| Format | Entries | SHA-256, both builds |
| --- | --- | --- |
| ZIP | 61 | `f8091fd2fb0b5a38284ab7cb5e5a04a71f42793ea8ea7b3ed9259d8b51bbac11` |
| tar.gz | 61 | `820cac39c290f92ed76815faf0a24f8b0ca6bcf32d8e88514ad94eddf7bad96a` |

Both archives contain identical file bytes and Unix permission modes. Inspection
rejected absolute/traversing paths and links, and confirmed the absence of Git
metadata and the source repository's project memory.

Each format was extracted into a separate temporary distribution, with executable
permissions restored from archive metadata. From another temporary project,
with `PYTHONPATH`/`PYTHONHOME` removed and private state redirected to a temporary
directory, its own `bin/memory-custodian` passed:

- `--version`: `memory-custodian 0.14.0`.
- `init --agent codex`, followed by a fixture-specific curated brief.
- `read --task implementation --path src/demo.py --strict-routing --no-local`:
  `COMPLETE` and `PASS`.
- `check --routing --security --privacy`: `PASS`.
- `audit --routing --subjects --conflicts --transactions --privacy --security`:
  `PASS`.

These checks use the extracted runtime, without imports from the source tree.
They do not establish automatic plugin discovery or another agent runtime's
conformance. Global agent installation, authentication, `HOME`, and `CODEX_HOME`
were unchanged. The structured [result](PACKAGE-BUILD-RESULTS-2026-11-17.json)
retains the source identity, hashes, and observed statuses.

Reproduce from the pinned clean source, using fresh output paths:

```sh
python3.13 scripts/package-codex-plugin.py --format zip --output /tmp/mc-1.zip
python3.13 scripts/package-codex-plugin.py --format zip --output /tmp/mc-2.zip
python3.13 scripts/package-codex-plugin.py --format tar.gz --output /tmp/mc-1.tar.gz
python3.13 scripts/package-codex-plugin.py --format tar.gz --output /tmp/mc-2.tar.gz
```

The packaging script and its `INCLUDE_PATHS` were checked unchanged through
observer-method commit `8f0bbe1` and the subsequent documentation-only candidate
updates. These results therefore describe the same candidate payload. Changes
to those paths require new build validation.
