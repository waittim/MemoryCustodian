# Running controlled agent benchmarks

The core suite has 18 pinned development tasks across two fixture repositories.
Each task runs independently under `NO_MEMORY`, `PLATFORM_FILE_ONLY`,
`EQUIVALENT_MANUAL_DOCS`, and `MEMORYCUSTODIAN`. Hidden oracles and reference
solutions are never copied into runtime checkouts.

## Verify inputs

Use Python 3.10 or newer. Core operations use only the standard library.

```bash
python3 scripts/run-memory-bench.py --check-integrity
```

This verifies task schemas, fixture hashes, condition isolation, information
parity, starter failures, negative solutions, and reference solutions. It does
not launch an agent or establish an effectiveness claim.

## Run the native Codex pilot

Use an already-authenticated Codex CLI with `exec --json`, `--ephemeral`, and
`--ignore-user-config` support. Check availability without displaying credentials:

```bash
codex --version
codex login status
```

The native adapter requires explicit opt-in and a pinned model. It launches a
fresh session in an external temporary checkout for each matrix cell. The
subprocess uses `workspace-write`, no agent shell network access, and approval
policy `never`; actions requiring more permission fail. User config, host
skills, plugins, web search, external memory, and delegation are disabled for
the session. Authentication remains with the existing CLI; do not copy keys or
authentication files into a fixture.

```bash
python3 scripts/run-batch-benchmark.py \
  --mode live --runtime codex --codex-executable codex \
  --model-version gpt-6.1-sol --timeout 180 --jobs 4 \
  --condition-order balanced --repetition-id my-pilot-1 \
  --record-dir /tmp/my-memory-pilot-1 \
  --report-file /tmp/my-memory-pilot-1.md
```

Use `--tasks field-ledger-export-cap` for a four-condition preflight. Use
`--dry-run` to inspect the schedule without launching agents or creating
records. A model label is a requested model identifier, not an immutable server
snapshot. Record the observed CLI version and method hashes when comparing
samples. [The formal pilot plan](PILOT-2026-11-13.md) fixes this release's settings.

Without explicit `--codex-executable`, `--mode live` remains a `BLOCKER` with
evidence class `live-runtime-unavailable`. Other named runtimes require their
own native integrations; giving a command an arbitrary runtime label does not
make it a verified named-runtime run.

## Run a generic command adapter

The runner supplies the task prompt on stdin and sets the working directory to
the isolated checkout. The command must perform its own edits in that checkout.
Arguments use shell-style tokenization, but no shell is executed. Pipes,
redirection, and shell substitution are not supported inside `--agent-cmd` or
`--cli-cmd`. With the headless CLI bridge, `{prompt}` is one literal argv value;
stdin carries the prompt when that placeholder is absent.

```bash
python3 scripts/run-batch-benchmark.py \
  --mode command --runtime local-command \
  --agent-cmd 'python3 /absolute/path/to/my-agent.py' \
  --record-dir /tmp/my-command-pilot
```

`scripts/headless-agent-adapter.py` also supports direct API calls and
`--provider cli --cli-cmd ...`. API context contains only the visible checkout;
API runs send all visible files in one request and therefore do not test a
runtime's incremental file-routing behavior. Those runs remain evidence class
`command-adapter`. A real runtime-specific integration is required for stronger
provenance. Generated file paths are checked before any response edits are
written; symlinks and paths outside the checkout are rejected.

For offline wiring checks, use `--provider mock --mock-strategy starter` with the
headless adapter. The `reference` and `heuristic` mocks can use known solutions;
their scores are never live-agent evidence. Always keep mock results in a
separate directory from real evaluations.

## Resume and interpret results

Records are append-only: an existing result ID is never overwritten. Use
`--resume` with exactly the original record directory, repetition, model, tool
policy, runtime, and mode. The batch validates metadata and includes saved
records in the rebuilt report. Use a fresh repetition ID for an independent
sample, and document any infrastructure reruns without discarding failures.

`--format json` keeps progress on stderr and emits a machine-readable summary.
The batch exits nonzero for missing, blocked, or review-required cells; a graded
task failure is a valid experimental result. PASS requires both the existing
hidden oracle and visible tests to pass. BLOCKER/REVIEW cells are excluded from
paired success comparisons and counted explicitly.

Reports contain the full outcome matrix, failure labels, discordant pairs, and
a reproducible paired-task bootstrap interval. This small development split
and one repetition do not establish general benefits, population equivalence,
token savings, or latency improvements. Unobserved metrics stay `null`.
Normalized action traces contain statuses, relative source-path mentions and
hashes, not raw reasoning, commands, output, credentials, or machine paths.
Regenerate a new sample to inspect raw runtime behavior locally; raw traces
must not be committed.

Native isolation is a fresh visible fixture plus sandbox and prompt
confinement, not an adversarial filesystem read jail. Agents must not inspect
other workspaces, hidden grading sources, or prior results. Invalid isolation
or source hashes invalidate a sample rather than improving its score.
