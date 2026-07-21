"""NightNotes store implementation."""

class NoteStore:
    """Session note store."""

    def __init__(self):
        # In-memory storage (notes do not persist across separate runs)
        self._notes = []

    def add_note(self, text: str) -> None:
        """Add a new note to the store."""
        if text:
            self._notes.append(text)

    def get_notes(self) -> list[str]:
        """Retrieve all stored notes."""
        return list(self._notes)
