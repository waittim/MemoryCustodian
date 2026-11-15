import unittest
from pathlib import Path

import router


class VisibleRouterTests(unittest.TestCase):
    def test_selection_stays_within_available_paths(self):
        available = ["b.md", "a.md"]
        got = router.select_files("t", {"tasks": {"t": ["a.md"]}}, available)
        self.assertTrue(set(got).issubset(set(available)))

    def test_estimate_is_non_negative(self):
        self.assertGreaterEqual(router.estimate_tokens("a b"), 0)

    def test_summary_writes_text(self):
        dest = Path("visible-summary.txt")
        try:
            router.write_summary("hello", dest)
            self.assertTrue(dest.read_text(encoding="utf-8"))
        finally:
            if dest.exists():
                dest.unlink()


if __name__ == "__main__":
    unittest.main()
