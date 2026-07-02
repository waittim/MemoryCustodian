# Monorepo Example

Use one top-level memory directory for repository-wide decisions:

```text
docs/memory/
```

If a package needs distinct memory, add a package-level memory directory and mention it from the root `docs/memory/manifest.md` instead of loading all package memory by default.
