import unittest

import ledger


class VisibleLedgerTests(unittest.TestCase):
    def test_positive_entry_is_kept(self):
        book = ledger.Ledger()
        book.add({"cents": 125, "currency": "USD"})
        self.assertEqual(book.entries[0]["cents"], 125)

    def test_format_exact_cents(self):
        self.assertEqual(ledger.format_cents(130), "1.30")

    def test_export_returns_a_list(self):
        book = ledger.Ledger()
        book.add({"cents": 1, "currency": "USD"})
        self.assertIsInstance(book.export(), list)


if __name__ == "__main__":
    unittest.main()
