"""Fixed offline controls for the rename-selection-helper v2 contract."""

from pathlib import Path


def build_cases(root: Path) -> list[dict]:
    source = (root / "benchmarks/references/route-notes-rename-helper/router.py").read_text(encoding="utf-8")
    starter = (root / "benchmarks/fixtures/route-notes/router.py").read_text(encoding="utf-8")
    helper = "def select_for_task(task, manifest, available):\n    return sorted(available)\n"
    wrapper = "def select_files(task, manifest, available):\n    return select_for_task(task, manifest, available)\n"
    if source.count(helper) != 1 or source.count(wrapper) != 1:
        raise ValueError("historical rename-helper reference changed")
    cases = []

    def add(name, status, description, content, label=None):
        cases.append({"name": name, "expected_status": status,
                      "expected_labels": [label] if label else [],
                      "description": description, "files": {"router.py": content}})

    def with_helper(body):
        return source.replace(helper, "def select_for_task(task, manifest, available):\n" + body)

    def with_wrapper(body):
        return source.replace(wrapper, "def select_files(task, manifest, available):\n" + body)

    add("reference", "PASS", "The original reference is valid under the public behavioral contract.", source)
    add("sorted-copy", "PASS", "Materializing the iterable before sorted is equivalent.",
        with_helper("    return sorted(list(available))\n"))
    add("list-sort", "PASS", "Sorting a fresh list in place preserves the input and result.",
        with_helper("    rows = list(available)\n    rows.sort()\n    return rows\n"))
    add("keyword-delegate", "PASS", "A wrapper may forward named arguments in any order.",
        with_wrapper("    return select_for_task(available=available, task=task, manifest=manifest)\n"))
    add("local-alias-delegate", "PASS", "A wrapper may resolve the current public helper through a local alias.",
        with_wrapper("    select = select_for_task\n    return select(task, manifest, available)\n"))

    omission = "MEMORY_OMISSION"
    behavior = "MEMORY_FALSE_POSITIVE"
    add("text-only", "FAIL", "A comment cannot supply the required public helper.",
        starter + "\n# def select_for_task(task, manifest, available):\n", omission)
    add("copied-wrapper", "FAIL", "Duplicating the selection expression is not delegation.",
        with_wrapper("    return sorted(list(available))\n"), omission)
    add("ignored-return", "FAIL", "Calling the helper but recomputing the answer ignores its return value.",
        with_wrapper("    select_for_task(task, manifest, available)\n    return sorted(list(available))\n"), omission)
    add("dead-branch-helper", "FAIL", "A helper call in a dead branch does not make the function a wrapper.",
        with_wrapper("    if False:\n        return select_for_task(task, manifest, available)\n"
                     "    return sorted(list(available))\n"), omission)
    add("captured-helper-alias", "FAIL", "A permanently captured alias does not track the currently bound helper.",
        source.replace(wrapper, "_captured = select_for_task\n\n\n"
                       "def select_files(task, manifest, available):\n"
                       "    return _captured(task, manifest, available)\n"), omission)
    add("copied-input", "FAIL", "The wrapper must forward the original available object.",
        with_wrapper("    return select_for_task(task, manifest, list(available))\n"), omission)
    add("manifest-filter", "FAIL", "Manifest filtering would change this task's existing selection behavior.",
        with_helper("    allowed = manifest.get('tasks', {}).get(task, [])\n"
                    "    return sorted(path for path in available if path in allowed)\n"), behavior)
    add("archive-filter", "FAIL", "This refactor must preserve archive paths already returned by the starter.",
        with_helper("    return sorted(path for path in available if not path.startswith('archive/'))\n"), behavior)
    add("deduplicate", "FAIL", "The existing selection result preserves duplicate paths.",
        with_helper("    return sorted(set(available))\n"), behavior)
    add("reverse-order", "FAIL", "The result remains in ordinary ascending order.",
        with_helper("    return sorted(available, reverse=True)\n"), behavior)
    add("fixed-answer", "FAIL", "A fixed answer can match the old oracle's only behavioral sample.",
        with_helper("    return ['a.md', 'b.md']  # sorted(available)\n"), behavior)
    add("mutates-input", "FAIL", "Sorting the caller's list changes existing behavior.",
        with_helper("    available.sort()\n    return list(available)\n"), behavior)
    add("sequence-only", "FAIL", "A slice-based implementation loses support for one-pass iterables.",
        with_helper("    return sorted(available[:])\n"), behavior)
    add("cached-result", "FAIL", "Repeated calls must not return a shared result list.",
        source.replace(helper, "_last = []\n\n\n"
                       "def select_for_task(task, manifest, available):\n"
                       "    _last[:] = sorted(available)\n    return _last\n"), behavior)
    return cases
