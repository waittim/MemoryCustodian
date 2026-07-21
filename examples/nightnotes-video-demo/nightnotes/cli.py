"""NightNotes command-line interface."""

import sys
from nightnotes.store import NoteStore

def main() -> None:
    store = NoteStore()
    args = sys.argv[1:]

    if not args or args[0] == "list":
        notes = store.get_notes()
        if not notes:
            print("No notes found.")
        else:
            for idx, note in enumerate(notes, 1):
                print(f"{idx}. {note}")
    elif args[0] == "add" and len(args) > 1:
        note_text = " ".join(args[1:])
        store.add_note(note_text)
        print(f"Added note: {note_text}")
    else:
        print("Usage: nightnotes [list | add <text>]")

if __name__ == "__main__":
    main()
