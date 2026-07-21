"""Test persistence requirement for NightNotes store."""

import unittest
from nightnotes.store import NoteStore

class TestNoteStorePersistence(unittest.TestCase):
    def test_notes_survive_across_store_instances(self):
        """Notes added in one store instance must survive in subsequent store instances."""
        store1 = NoteStore()
        test_note = "Session memory test note"
        store1.add_note(test_note)

        # Re-create store instance to simulate a separate process / launch
        store2 = NoteStore()
        notes = store2.get_notes()

        self.assertIn(test_note, notes, "Notes must survive across separate CLI runs.")

if __name__ == "__main__":
    unittest.main()
