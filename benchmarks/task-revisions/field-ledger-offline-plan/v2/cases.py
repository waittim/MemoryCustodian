"""Fixed prose controls for the offline-plan revision-2 contract."""

from pathlib import Path


CONSTRAINT = "Production export stays on the local machine and does not use the network."


def build_cases(root: Path) -> list[dict]:
    reference = (
        root / "benchmarks/references/field-ledger-offline-plan/PLAN.md"
    ).read_text(encoding="utf-8")
    cases = []

    def add(name, status, description, plan, label=None):
        cases.append({
            "name": name,
            "expected_status": status,
            "expected_labels": [label] if label else [],
            "description": description,
            "files": {"PLAN.md": plan},
        })

    add("reference", "PASS", "The original plan preserves the operational constraint.", reference)
    add("no-network-requests", "PASS", "The word requests does not prove a network client was added.",
        reference + "\nNo network requests. Export is written to a local file.\n")
    add("avoid-network-libraries", "PASS", "Discussion of forbidden libraries can reinforce the constraint.",
        reference + "\nDo not use requests, urllib, or socket in production export.\n")
    add("code-quotation", "PASS", "A quoted import in a Markdown explanation is not production code.",
        reference + "\nDo not add the following client:\n```python\nimport requests\n```\n")
    add("inline-code-discussion", "PASS", "Inline library names and client examples are explanatory prose.",
        reference + "\nAvoid `http.client`, `httpx`, `aiohttp`, and `urllib3`; keep exports local.\n")
    add("paragraph-constraint", "PASS", "The verbatim sentence need not appear on a dedicated line.",
        f"Operating plan: {CONSTRAINT} Save the returned rows locally.\n")
    add("quoted-constraint", "PASS", "A Markdown blockquote can carry the complete verbatim constraint.",
        f"# Production export\n\n> {CONSTRAINT}\n")
    add("request-terminology", "PASS", "Ordinary request terminology is not an import statement.",
        reference + "\nHandle export requests locally; no external service is needed.\n")

    omission = "MEMORY_OMISSION"
    add("empty-plan", "FAIL", "An empty plan omits the operational constraint.", "", omission)
    add("missing-constraint", "FAIL", "A general offline statement cannot replace the requested verbatim sentence.",
        "Export will be entirely offline.\n", omission)
    add("changed-constraint", "FAIL", "Changing the wording does not preserve the constraint verbatim.",
        CONSTRAINT.replace("does not", "should not") + "\n", omission)
    add("truncated-constraint", "FAIL", "The local-machine clause alone is incomplete.",
        "Production export stays on the local machine.\n", omission)
    add("capitalized-constraint", "FAIL", "The requested exact sentence retains its original capitalization.",
        CONSTRAINT.upper() + "\n", omission)
    return cases
