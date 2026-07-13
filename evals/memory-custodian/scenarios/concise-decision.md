# Concise Decision Entry

## Purpose
Verify that a verbose durable choice is compressed semantically instead of stored or truncated as a long decision entry.

## Setup
- A project uses MemoryCustodian with an indexed persistence area.
- The user provides a confirmed choice followed by extensive implementation narrative and examples.

## Prompt
The user says: "Remember that database writes must validate one non-empty owner inside the transaction. Also record every migration anecdote, caller example, test fixture, error message, and possible future schema variation I just described."

## Required Observations
- Agent preserves the confirmed choice and its concise reason.
- Agent keeps the complete decision entry within 120 tokens.
- Agent moves supporting implementation detail to matched area context or source documentation when it remains useful.
- Agent rewrites semantically rather than cutting text at a token boundary.

## Forbidden Outcomes
- Agent stores the full implementation narrative inside the decision entry.
- Agent silently truncates the user's text.
- Agent uses `--allow-long` without first attempting a faithful concise decision.
- Agent discards essential constraints while shortening the entry.

## Passing Criteria
Pass when the durable decision is concise, faithful, correctly scoped, and detailed evidence remains available only where it is useful.
