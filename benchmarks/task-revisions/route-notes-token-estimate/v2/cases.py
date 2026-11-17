"""Predetermined implementation controls for token-estimate revision 2."""

from pathlib import Path


def build_cases(root: Path) -> list[dict]:
    reference = (root / "benchmarks/references/route-notes-token-estimate/router.py").read_text(encoding="utf-8")
    starter = (root / "benchmarks/fixtures/route-notes/router.py").read_text(encoding="utf-8")
    original = "def estimate_tokens(text):\n    return len(str(text).split())\n"
    if reference.count(original) != 1:
        raise ValueError("historical token-estimate reference changed")
    cases = []

    def implementation(body, prefix=""):
        return prefix + reference.replace(original, "def estimate_tokens(text):\n" + body)

    def add(name, status, description, source):
        cases.append({"name": name, "expected_status": status,
                      "expected_labels": [] if status == "PASS" else ["MEMORY_OMISSION"],
                      "description": description, "files": {"router.py": source}})

    add("reference", "PASS", "The original whitespace-split reference satisfies the contract.", reference)
    add("unicode-regex", "PASS", "A Unicode-aware non-whitespace-run expression is equivalent.",
        implementation("    return len(re.findall(r'\u005cS+', str(text)))\n", "import re\n\n"))
    add("manual-state-machine", "PASS", "An isspace-based state machine counts word starts.",
        implementation("    count = 0\n    in_word = False\n    for char in str(text):\n"
                       "        if char.isspace():\n            in_word = False\n"
                       "        elif not in_word:\n            count += 1\n            in_word = True\n"
                       "    return count\n"))
    add("word-start-generator", "PASS", "A generator over non-whitespace word boundaries is equivalent.",
        implementation("    value = str(text)\n    return sum(1 for index, char in enumerate(value)\n"
                       "               if not char.isspace() and (index == 0 or value[index - 1].isspace()))\n"))
    add("splitlines-word-sum", "PASS", "Summing words per line is valid when line counts are not added.",
        implementation("    return sum(len(line.split()) for line in str(text).splitlines())\n"))

    add("constant-three", "FAIL", "A constant matches the old oracle's only input but not the rule.",
        implementation("    return 3\n"))
    add("line-counter", "FAIL", "The unchanged starter counts lines instead of words.", starter)
    add("character-counter", "FAIL", "Character count is not whitespace-delimited word count.",
        implementation("    return len(str(text))\n"))
    add("literal-space-split", "FAIL", "Splitting only on literal spaces mishandles empty and other whitespace.",
        implementation("    return len(str(text).split(' '))\n"))
    add("line-count-mixture", "FAIL", "Adding line boundaries to correct word counts changes the result.",
        implementation("    value = str(text)\n    return len(value.split()) + max(len(value.splitlines()) - 1, 0)\n"))
    add("sample-only", "FAIL", "Special-casing the old example does not implement the rule.",
        implementation("    return 3 if text == 'one two\\nthree' else 0\n"))
    add("boolean-zero", "FAIL", "False compares equal to zero but is not an integer count under this contract.",
        implementation("    count = len(str(text).split())\n    return count if count else False\n"))
    add("floating-count", "FAIL", "A numerically equal floating-point result is not a Python int.",
        implementation("    return float(len(str(text).split()))\n"))
    add("negative-count", "FAIL", "Counts cannot be negative.",
        implementation("    return -len(str(text).split())\n"))
    add("stale-first-result", "FAIL", "A cached count from an earlier input cannot serve a different input.",
        implementation("    global _cached_count\n    if _cached_count is None:\n"
                       "        _cached_count = len(str(text).split())\n    return _cached_count\n",
                       "_cached_count = None\n\n"))
    add("unstable-repeat", "FAIL", "Alternating counts violate repeated-call stability.",
        implementation("    global _calls\n    _calls += 1\n"
                       "    return len(str(text).split()) + (0 if _calls % 2 else 1)\n",
                       "_calls = 0\n\n"))
    add("string-only", "FAIL", "The existing reference stringifies non-string inputs first.",
        implementation("    return len(text.split())\n"))
    add("ascii-regex", "FAIL", "ASCII-only whitespace misses Python's Unicode separators.",
        implementation("    return len(re.findall(r'\u005cS+', str(text), flags=re.ASCII))\n", "import re\n\n"))
    add("bounded-count", "FAIL", "A three-word ceiling passes the old example but truncates larger counts.",
        implementation("    return min(3, len(str(text).split()))\n"))
    return cases
