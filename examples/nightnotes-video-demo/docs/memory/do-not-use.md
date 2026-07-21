# Do Not Use / Tombstones

Tombstones are newest first.

## SQLite for session persistence

- Do not introduce SQLite for the current session store.
- The current data size does not justify a database, and portability is a product requirement.
