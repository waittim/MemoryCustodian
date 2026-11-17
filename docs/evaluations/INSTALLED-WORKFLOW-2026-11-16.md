# Local installed-workflow smoke — 2026-11-16

Status: Passed locally. This is a real local installer and bundled-CLI execution
check, without a model or agent runtime. It is not full installed-Skill
live-agent validation, an effectiveness benchmark, or a cross-runtime result.

## Gap addressed

Existing package tests inspect plugin metadata, installer symlinks, wrapper
versions, and archive contents. Most CLI behavior tests import `main` directly;
some older tests use a compatibility helper that supplies protocol inputs.
Those checks do not connect a relocated installation to its actual CLI entry
point and a fresh external project.

The new test, `tests/test_installed_workflow_014.py`, copies the real distribution
files to a temporary directory, invokes the documented `install.sh claude`
path with a temporary `CLAUDE_HOME`, and calls the resulting installed
`bin/memory-custodian` by absolute path. Its working directory is the separate
fixture project. `PYTHONPATH` and `PYTHONHOME` are removed from child-process
environment input, and `PYTHON` selects the test interpreter. The bundled
wrapper supplies the relocated distribution's own `cli` directory.

`HOME` and `CODEX_HOME` are not changed. Private CLI state uses a temporary
`XDG_STATE_HOME`; installation and test-project writes remain in temporary
directories. No global installation, authentication, or user configuration is
changed. The temporary installation, project, and private state are removed
when the test exits.

## Executed coverage

One integration test runs the installer, the installed SessionStart hook, and
12 actual bundled-CLI subprocess invocations. It verifies:

| Operation | Observed result |
| --- | --- |
| Install the copied plugin into a custom agent home | The installed link targets the temporary distribution; real Skill and routing references are present. |
| Installed `bin/memory-custodian --version` | Package 0.13.0 executes through the relocated bundled helper. |
| Installed SessionStart hook | Its JSON directs startup to the manifest/brief and names the installed Skill or bundled CLI. |
| Strict read before initialization | Fails with exit 2; no usable context is invented. |
| `init --agent all` | Creates managed memory and thin `AGENTS.md`, `CLAUDE.md`, and `GEMINI.md` bootstraps pointing to the manifest and brief. |
| Subject preview and confirmed apply | The preview does not create a Subject; applying the exact Plan ID creates it. |
| Active constraint with repository evidence | A Subject/Facet-bound constraint is written and appears in routed context. |
| Unconfirmed candidate add | The candidate remains in `inbox.md` and is absent from normal implementation context. |
| Path-routed area without task scope | Strict read reports `INCOMPLETE` and exits 1, the documented domain-failure outcome. |
| The same task with an explicit matching path | Routing is `COMPLETE`; the expected area and active constraint are loaded. |
| `check --routing --security --privacy` | PASS. |
| `audit --routing --subjects --conflicts --transactions --privacy --security` | PASS with audit schema 1. |

The test curates the generated brief from its fixture README before relying on
memory, as the Skill requires. Commands use the real parser and transaction
paths; no legacy compatibility helper or mocked CLI result is involved. Public
JSON outputs retain schema 1 and do not expose temporary machine paths.

## Reproduction and local evidence

```bash
PYTHONPATH=cli python3.13 -m unittest discover -s tests \
  -p test_installed_workflow_014.py
```

Observed locally: one test passed on Python 3.13.14, Darwin 25.6.0 arm64. The
test is explicitly skipped on non-POSIX platforms because this installation
path uses shell scripts and symlinks. No Windows or other Python-version result
is inferred.

Relevant source SHA-256 values at this run:

| Source | SHA-256 |
| --- | --- |
| `tests/test_installed_workflow_014.py` | `0db69858041b054b44578292cdec5ad2681e5dbbc53a25c0f28e8d00d0cd52dc` |
| `install.sh` | `057a3dd18fe8566418e485efae647b22a897191cda2bbc00917a541e1185ca87` |
| `bin/memory-custodian` | `55e7d60b2ffefd79ada6374c3d93dd255a4479ce8aa04731d2918d3fd3166eed` |
| `scripts/memory-custodian` | `121d69e21dd3200f05c6804dcfc3b87ddca232aa9421da794ff6b4e80b88d96c` |
| `skills/memory-custodian/SKILL.md` | `d949d989a3bc5df0960c5e9c79403067d1d4331b3b01c350ceaf6c8081802cc6` |
| `cli/memory_custodian/main.py` | `53e9d4ffc06addcc117ba2f91072107104d4a1efaa607b1520eb558b9cd35e37` |

## Interpretation and limits

No production CLI defect was observed within this local smoke. It establishes
that the documented copied-plugin install and bundled CLI work together for
the tested operations. It does not diagnose the earlier `split-export` agent
failure: that fixture task and its source workspaces were not replayed here.

The installed Skill text, references, hook, and project bootstraps are checked
as actual artifacts. No Claude, Codex, or Gemini agent process is launched, so
host discovery of the installed Skill, instruction following, agent routing
choices, and coding-task success remain untested. Generating all three
bootstrap files does not constitute three-runtime validation. Crash recovery,
all audit modes, and global marketplace installation are outside this smoke.
