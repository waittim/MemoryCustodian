# Running Headless Agent Benchmarks

This guide explains how to run and verify the MemoryCustodian benchmark matrix across the four isolated conditions:

1. `NO_MEMORY`
2. `PLATFORM_FILE_ONLY`
3. `EQUIVALENT_MANUAL_DOCS`
4. `MEMORYCUSTODIAN`

## Architecture Overview

```
                        [run-batch-benchmark.py]
                                   │
               ┌───────────────────┴───────────────────┐
               ▼                                       ▼
  [scripts/run-memory-bench.py]           [Aggregate & Generate Report]
               │                                       ▲
               ├───────────────────┐                   │
               ▼                   ▼                   │
    [Prepare Temp Checkout]  [Mechanical Grader]───────┘
               │                   ▲
               ▼                   │
    [headless-agent-adapter.py] ───┘
         (mock / api / cli)
```

1. **`scripts/run-memory-bench.py`**: Pinned runner providing checkout preparation, integrity checks, isolation enforcement, and mechanical hidden-oracle grading.
2. **`scripts/headless-agent-adapter.py`**: Bridges task prompts and checkouts to an agent runtime (mock heuristic, LLM API, or external CLI).
3. **`scripts/run-batch-benchmark.py`**: Executes the matrix across tasks and conditions, records append-only results, and calculates paired statistics.

---

## 1. Quick Verification (Offline Mock Agent)

To verify the entire evaluation harness without API keys or network access, use the built-in heuristic mock adapter:

### Run a Single Task Across All 4 Conditions

```bash
python3 scripts/run-batch-benchmark.py \
  --tasks field-ledger-export-cap \
  --agent-cmd "python3 $(pwd)/scripts/headless-agent-adapter.py --provider mock --mock-strategy heuristic"
```

### Run the Full 18-Task Core Suite (Dry-Run)

```bash
python3 scripts/run-batch-benchmark.py \
  --agent-cmd "python3 $(pwd)/scripts/headless-agent-adapter.py --provider mock" \
  --dry-run
```

---

## 2. Running with Real LLM APIs

`scripts/headless-agent-adapter.py` supports direct HTTP calls using Python standard library:

### OpenAI / Compatible Endpoint

```bash
export OPENAI_API_KEY="your-api-key"
# Optional: export OPENAI_BASE_URL="https://api.openai.com/v1"

python3 scripts/run-batch-benchmark.py \
  --tasks "field-ledger-export-cap" \
  --runtime "openai-api" \
  --model-version "gpt-4o" \
  --timeout 120 \
  --record-dir "benchmarks/results/gpt4o" \
  --agent-cmd "python3 $(pwd)/scripts/headless-agent-adapter.py --provider api --api-type openai --model gpt-4o"
```

### Anthropic Claude

```bash
export ANTHROPIC_API_KEY="your-api-key"

python3 scripts/run-batch-benchmark.py \
  --tasks "field-ledger-export-cap" \
  --runtime "anthropic-api" \
  --model-version "claude-3-5-sonnet-20241022" \
  --timeout 120 \
  --record-dir "benchmarks/results/claude-sonnet" \
  --agent-cmd "python3 $(pwd)/scripts/headless-agent-adapter.py --provider api --api-type anthropic --model claude-3-5-sonnet-20241022"
```

### Google Gemini

```bash
export GEMINI_API_KEY="your-api-key"

python3 scripts/run-batch-benchmark.py \
  --tasks "field-ledger-export-cap" \
  --runtime "gemini-api" \
  --model-version "gemini-1.5-pro" \
  --timeout 120 \
  --record-dir "benchmarks/results/gemini-pro" \
  --agent-cmd "python3 $(pwd)/scripts/headless-agent-adapter.py --provider api --api-type gemini --model gemini-1.5-pro"
```

---

## 3. Running with Local Agent CLIs

If you have an interactive coding CLI configured (e.g. `claude`, `codex`, `aider`):

```bash
python3 scripts/run-batch-benchmark.py \
  --tasks "field-ledger-export-cap" \
  --runtime "claude-cli" \
  --agent-cmd "python3 $(pwd)/scripts/headless-agent-adapter.py --provider cli --cli-cmd 'claude -p \"{prompt}\"'"
```

---

## 4. Resuming Interrupted Batch Runs

Because results are append-only and immutable, pass `--resume` and `--record-dir` to resume without repeating finished runs:

```bash
python3 scripts/run-batch-benchmark.py \
  --record-dir "benchmarks/results/run-1" \
  --resume \
  --agent-cmd "..."
```

---

## 5. Output and Reports

Add `--report-file <path>` to save a Markdown evaluation report:

```bash
python3 scripts/run-batch-benchmark.py \
  --tasks all \
  --report-file docs/evaluations/benchmark/RESULTS.md \
  --agent-cmd "..."
```

The report includes:
- Condition summary with pass rates.
- Prespecified primary paired comparison (`EQUIVALENT_MANUAL_DOCS` vs `MEMORYCUSTODIAN`).
- Detailed breakdown of failure labels (`MEMORY_OMISSION`, `MEMORY_STALE_USE`, etc.).
- Complete per-task outcome matrix.
