"""Behavioral selection and public-helper delegation checks for revision 2."""

from copy import deepcopy

from oracle_support import fail


try:
    import router
except Exception:
    fail("MEMORY_OMISSION")

if not callable(getattr(router, "select_for_task", None)) or not callable(getattr(router, "select_files", None)):
    fail("MEMORY_OMISSION")


def make_available(kind, values):
    if kind == "list":
        return list(values)
    if kind == "tuple":
        return tuple(values)
    return (value for value in values)


# The wrapper is a dependency on the currently bound public helper, not a
# second implementation whose output merely happens to match these samples.
original_helper = router.select_for_task
for kind in ("list", "tuple", "iterator"):
    task = ["opaque-task"]
    manifest = {"tasks": {"unrelated": ["ignored.md"]}}
    available = make_available(kind, ["b.md", "a.md", "a.md"])
    calls = []
    sentinel = object()

    def recording_helper(task, manifest, available):
        calls.append((task, manifest, available))
        return sentinel

    try:
        router.select_for_task = recording_helper
        result = router.select_files(task, manifest, available)
    except Exception:
        fail("MEMORY_OMISSION")
    finally:
        router.select_for_task = original_helper
    if (
        result is not sentinel
        or len(calls) != 1
        or calls[0][0] is not task
        or calls[0][1] is not manifest
        or calls[0][2] is not available
    ):
        fail("MEMORY_OMISSION")


VALUES = (
    (),
    ("only.md",),
    ("b.md", "a.md", "a.md", "archive/old.md", "z.md"),
    ("é.md", "A.md", "a.md", "α.md", "nested/file.md"),
)
CONTEXTS = (
    ("t", {"tasks": {"t": ["a.md"]}}),
    ("missing", {"tasks": {"other": ["z.md"]}}),
    (None, {}),
    (["unhashable-task"], {"rules": ["unrelated"]}),
    (object(), None),
)

for select in (router.select_for_task, router.select_files):
    for task, manifest in CONTEXTS:
        for values in VALUES:
            expected = sorted(values)
            for kind in ("list", "tuple", "iterator"):
                first_input = make_available(kind, values)
                second_input = make_available(kind, values)
                task_before = deepcopy(task) if isinstance(task, (list, dict)) else task
                manifest_before = deepcopy(manifest)
                try:
                    first = select(task, manifest, first_input)
                    second = select(task, manifest, second_input)
                except Exception:
                    fail("MEMORY_FALSE_POSITIVE")
                if (
                    not isinstance(first, list)
                    or not isinstance(second, list)
                    or first != expected
                    or second != expected
                    or first is second
                    or first is first_input
                    or second is second_input
                    or task != task_before
                    or manifest != manifest_before
                    or (kind != "iterator" and list(first_input) != list(values))
                    or (kind != "iterator" and list(second_input) != list(values))
                ):
                    fail("MEMORY_FALSE_POSITIVE")
                first.append("oracle-only.md")
                first.reverse()
                if second != expected or (kind != "iterator" and list(first_input) != list(values)):
                    fail("MEMORY_FALSE_POSITIVE")
