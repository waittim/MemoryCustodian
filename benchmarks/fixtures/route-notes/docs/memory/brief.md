# Project Brief

Purpose:
Route Notes selects project files for one declared task.

Current direction:
Select only paths listed for the task in the manifest.
Never load a path under archive/ unless the task explicitly asks for archive maintenance.
Token estimates count whitespace-delimited words.
Replace token-like secrets that start with sk- with [REDACTED] before writing a summary.
Do not infer an area from prose.
Load an area file only when the task explicitly names that area.
Routing rules stay in the manifest.
Do not store routing rules in a database.
Do not copy routing rules into the bootstrap file.
