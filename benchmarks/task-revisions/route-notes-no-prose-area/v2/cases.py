"""Fixed positive and negative controls for no-prose-area revision 2."""

from pathlib import Path


RULE_ONE = "Do not infer an area from prose."
RULE_TWO = "Load an area file only when the task explicitly names that area."
SKIP = "skip areas/billing.md"
LOAD = "load areas/billing.md"


def build_cases(root: Path) -> list[dict]:
    reference = (
        root / "benchmarks/references/route-notes-no-prose-area/PLAN.md"
    ).read_text(encoding="utf-8")
    rules = f"{RULE_ONE}\n{RULE_TWO}\n"
    cases = []

    def add(name, status, description, plan, label=None):
        cases.append({
            "name": name,
            "expected_status": status,
            "expected_labels": [label] if label else [],
            "description": description,
            "files": {"PLAN.md": plan},
        })

    add("reference", "PASS", "The original reference provides both rules and the skip action.",
        reference)
    add("negative-load-explanation", "PASS", "A sentence forbidding a load is not a load action.",
        reference + "\nDo not load areas/billing.md because the task does not name an area.\n")
    add("paragraph-rules", "PASS", "The verbatim rules need not each occupy their own line.",
        f"Project rules: {RULE_ONE} {RULE_TWO}\n\n{SKIP}\n")
    add("surrounding-whitespace", "PASS", "Whitespace around the standalone action is permitted.",
        rules + f"\n\t  {SKIP}  \t\n")
    add("backtick-fenced-action", "PASS", "A bare action in a Markdown code fence is an action.",
        rules + f"\n```text\n{SKIP}\n```\n")
    add("tilde-fenced-action", "PASS", "A tilde Markdown code fence also permits the action.",
        rules + f"\n~~~\n{SKIP}\n~~~\n")
    add("quoted-load-explanation", "PASS", "A Markdown blockquote mentioning load is not an action.",
        reference + f"\nRejected example:\n> {LOAD}\n")
    add("inline-code-load-explanation", "PASS", "An inline-code load mention is not an action.",
        reference + f"\n`{LOAD}`\nThis quoted command is not the chosen action.\n")
    add("quoted-string-load-explanation", "PASS", "A quoted string mentioning load is discussion.",
        reference + f'\nRejected action name: "{LOAD}".\n')
    add("repeated-skip", "PASS", "Repeated agreeing skip lines do not introduce a conflict.",
        reference + f"\n{SKIP}\n")

    omission = "MEMORY_OMISSION"
    forbidden = "MEMORY_FALSE_POSITIVE"
    add("missing-first-rule", "FAIL", "Both verbatim project rules must be retained.",
        f"{RULE_TWO}\n{SKIP}\n", omission)
    add("missing-second-rule", "FAIL", "Omitting the explicit-area rule is not sufficient.",
        f"{RULE_ONE}\n{SKIP}\n", omission)
    add("inline-skip", "FAIL", "An inline action mention does not satisfy the own-line requirement.",
        rules + f"Decision: {SKIP}\n", omission)
    add("load-action", "FAIL", "An exact standalone load line chooses the forbidden action.",
        rules + f"{LOAD}\n", forbidden)
    add("conflicting-actions", "FAIL", "A skip line cannot cancel an exact load line.",
        reference + f"{LOAD}\n", forbidden)
    add("fenced-load-conflict", "FAIL", "A forbidden bare load inside a code fence remains an action.",
        reference + f"\n```text\n{LOAD}\n```\n", forbidden)
    add("misspelled-path", "FAIL", "A different path is not the required skip action.",
        rules + "skip areas/billings.md\n", omission)
    add("explanation-without-action", "FAIL", "A correct explanation does not replace the action line.",
        rules + "Do not load areas/billing.md because no area was explicitly named.\n", omission)
    add("capitalized-action", "FAIL", "Action matching is explicitly case-sensitive.",
        rules + "Skip areas/billing.md\n", omission)
    add("inline-code-skip-only", "FAIL", "Inline-code wrapping cannot substitute for a bare action.",
        rules + f"`{SKIP}`\n", omission)
    add("list-item-skip-only", "FAIL", "A list item is discussion, not the required bare action line.",
        rules + f"- {SKIP}\n", omission)
    add("quoted-skip-only", "FAIL", "A blockquote alone does not record the chosen action.",
        rules + f"> {SKIP}\n", omission)
    add("skip-with-inline-comment", "FAIL", "Extra text prevents an exact standalone action match.",
        rules + f"{SKIP} # not explicitly requested\n", omission)
    return cases
