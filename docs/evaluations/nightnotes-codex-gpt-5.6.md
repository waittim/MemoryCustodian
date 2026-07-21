# NightNotes Codex Evaluation

Date: 2026-07-21  
Model: GPT-5.6  
Session: New session, no prior conversation context  
Files modified: None  
Evidence: [Published demo video](https://www.youtube.com/watch?v=mYKzzATlOPw)
Repository snapshot: [`openai-build-week-submission-final`](https://github.com/waittim/MemoryCustodian/tree/openai-build-week-submission-final)

This is a reproducible live evaluation, not a benchmark. The fixture and exact
reproduction steps are documented in the
[NightNotes demo](../../examples/nightnotes-video-demo/README.md).

## Prompt

```text
Plan how to implement persistent session state.

Before proposing changes, use the repository's project memory. Explain which
existing decisions, constraints, and rejected approaches influenced your plan.

Do not modify any files.
```

## Expected

- Select human-readable local JSON.
- Preserve offline operation.
- Use only the Python standard library for routine operation.
- Keep existing note files human-readable.
- Avoid SQLite for the current session store.
- Modify no files.

## Observed

- [x] JSON decision recovered.
- [x] Offline constraint recovered.
- [x] Standard-library constraint recovered.
- [x] Human-readable-file constraint recovered.
- [x] SQLite rejection recovered.
- [x] No files modified.

## Observed result summary

The response recovered the existing decision to store session state in
human-readable local JSON, preserved offline and standard-library-only
operation, and respected the explicit rejection of SQLite for the current
session store. This is a paraphrase of the observed result, not a verbatim
transcript.
