"""Fixed offline controls for split-export v2, independent of live outcomes."""

from pathlib import Path


def build_cases(root: Path) -> list[dict]:
    reference = root / "benchmarks/references/field-ledger-split-export"
    reference_ledger = (reference / "ledger.py").read_text(encoding="utf-8")
    reference_export = (reference / "export.py").read_text(encoding="utf-8")
    starter = (root / "benchmarks/fixtures/field-ledger/ledger.py").read_text(encoding="utf-8")
    delegation = (
        "    def export(self):\n"
        "        from export import export_entries\n"
        "        return export_entries(self.entries, EXPORT_CAP)\n"
    )
    starter_export = (
        "    def export(self):\n"
        "        rows = list(self.entries)\n"
        "        if EXPORT_CAP is None:\n"
        "            return rows\n"
        "        return rows[:EXPORT_CAP]\n"
    )
    if reference_ledger.count(delegation) != 1 or starter.count(starter_export) != 1:
        raise ValueError("historical split-export control source changed")

    def delegated(body: str) -> str:
        return reference_ledger.replace(delegation, body)

    def helper(body: str) -> str:
        return "def export_entries(entries, export_cap):\n" + body

    cases = []

    def add(name, status, description, ledger_source, export_source, label=None):
        cases.append({
            "name": name,
            "expected_status": status,
            "expected_labels": [label] if label else [],
            "description": description,
            "files": {"ledger.py": ledger_source, "export.py": export_source},
        })

    add("reference", "PASS", "Original reference keeps its valid delegation and behavior.",
        reference_ledger, reference_export)
    add("renamed-helper", "PASS", "A different helper name and global from-import are valid.",
        "from export import rows_with_limit\n\n" + delegated(
            "    def export(self):\n        return rows_with_limit(self.entries, EXPORT_CAP)\n"
        ), reference_export.replace("export_entries", "rows_with_limit"))
    add("module-alias", "PASS", "A global module alias and arbitrary helper name are valid.",
        "import export as writer\n\n" + delegated(
            "    def export(self):\n        return writer.collect(self.entries, EXPORT_CAP)\n"
        ), reference_export.replace("export_entries", "collect"))
    add("local-import", "PASS", "A local aliased import does not prescribe a helper name.",
        delegated("    def export(self):\n        from export import collect as send\n"
                  "        return send(self.entries, EXPORT_CAP)\n"),
        reference_export.replace("export_entries", "collect"))

    omission = "MEMORY_OMISSION"
    behavior = "MEMORY_FALSE_POSITIVE"
    add("empty-module", "FAIL", "Creating an empty export module does not move execution.",
        starter, "", omission)
    add("comment-masquerade", "FAIL", "A helper identifier in a comment does not move execution.",
        starter + "\n# export_entries belongs in another module.\n", "", omission)
    add("unused-helper", "FAIL", "An imported helper must actually supply the result.",
        "from export import export_entries\n\n" + starter, reference_export, omission)
    add("dead-branch-helper", "FAIL", "A helper called only in an unreachable branch is unused.",
        starter.replace("    def export(self):\n", "    def export(self):\n"
                        "        if False:\n            from export import export_entries\n"
                        "            return export_entries(self.entries, EXPORT_CAP)\n"),
        reference_export, omission)
    add("ignored-helper", "FAIL", "Executing an ignored no-op helper is not delegation.",
        starter.replace("    def export(self):\n", "    def export(self):\n"
                        "        from export import note_export\n        note_export(self.entries)\n"),
        "def note_export(entries):\n    return None\n", omission)
    add("reexport-unmoved", "FAIL", "Re-exporting the old ledger implementation does not move its code.",
        delegated("    def export(self):\n        from export import export_entries\n"
                  "        return export_entries(self.entries, EXPORT_CAP)\n")
        + "\ndef old_implementation(entries, cap):\n    rows = list(entries)\n"
          "    return rows if cap is None else rows[:cap]\n",
        "from ledger import old_implementation as export_entries\n", omission)
    add("drop-row", "FAIL", "Delegation must not silently discard an existing row.",
        reference_ledger, helper("    rows = list(entries)[:-1]\n"
                                 "    return rows if export_cap is None else rows[:export_cap]\n"), behavior)
    add("reverse-rows", "FAIL", "Delegation preserves row ordering.",
        reference_ledger, helper("    rows = list(reversed(entries))\n"
                                 "    return rows if export_cap is None else rows[:export_cap]\n"), behavior)
    add("fixed-cap", "FAIL", "The export helper cannot freeze the current cap at import time.",
        reference_ledger, "from ledger import EXPORT_CAP\n\n" + helper(
            "    rows = list(entries)\n    return rows if EXPORT_CAP is None else rows[:EXPORT_CAP]\n"), behavior)
    add("alias-list", "FAIL", "The returned outer list must not alias the ledger's list.",
        reference_ledger, helper("    return entries if export_cap is None else entries[:export_cap]\n"), behavior)
    add("deep-copy-rows", "FAIL", "The existing contract is a shallow list copy, not copied row dictionaries.",
        reference_ledger, "from copy import deepcopy\n\n" + helper(
            "    rows = deepcopy(entries)\n    return rows if export_cap is None else rows[:export_cap]\n"), behavior)
    return cases
