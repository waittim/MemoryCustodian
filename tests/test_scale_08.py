from __future__ import annotations

import contextlib
from io import StringIO
from pathlib import Path
import tempfile
import unittest

from memory_custodian.entries import render_active_entry, render_candidate_entry
from memory_custodian.main import main
from memory_custodian.protocol import manifest_with_optional_module_index
from memory_custodian.snapshot import build_snapshot


class Protocol08ScaleTests(unittest.TestCase):
    def test_scale_fixture_indexes_1500_entries_and_50_areas(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with contextlib.redirect_stdout(StringIO()):
                self.assertEqual(main(["init", "--project-root", str(root)]), 0)
            memory = root / "docs" / "memory"
            evidence_root = root / "fixtures" / "evidence"
            evidence_root.mkdir(parents=True)
            for index in range(100):
                (evidence_root / f"source-{index:03d}.txt").write_text(
                    f"source {index}\n", encoding="utf-8"
                )

            active_units: list[str] = []
            for index in range(450):
                evidence = (
                    f"repo:fixtures/evidence/source-{index:03d}.txt",
                ) if index < 100 else ("user-confirmed",)
                active_units.append(render_active_entry(
                    "preference", f"MC-PREF-20260921-{index:08x}",
                    f"Preference {index}", f"Prefer fixture behavior {index}.",
                    None, "project", evidence,
                ))
            (memory / "preferences.md").write_text(
                "# Preferences\n\nEntries are newest first.\n\n"
                + "\n\n".join(active_units) + "\n",
                encoding="utf-8",
            )

            manifest_path = memory / "manifest.md"
            manifest = manifest_path.read_text(encoding="utf-8")
            for index in range(50):
                slug = f"area-{index:02d}"
                relative = f"areas/{slug}.md"
                manifest, _ = manifest_with_optional_module_index(
                    manifest, relative, activation="explicit-only"
                )
                path = memory / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    f"# Area {index}\n\n"
                    + render_active_entry(
                        "preference", f"MC-PREF-20260922-{index:08x}",
                        f"Area preference {index}", f"Prefer area behavior {index}.",
                        None, f"area:{slug}", ("user-confirmed",),
                    ) + "\n",
                    encoding="utf-8",
                )
            manifest_path.write_text(manifest, encoding="utf-8")

            candidates = [
                render_candidate_entry(
                    f"MC-INBOX-20260923-{index:08x}", f"Candidate {index}",
                    "preference", f"Investigate candidate {index}.", "project",
                    ("agent-observed",), None,
                )
                for index in range(500)
            ]
            (memory / "inbox.md").write_text(
                "# Memory Inbox\n\n" + "\n\n".join(candidates) + "\n",
                encoding="utf-8",
            )

            archived = [
                render_active_entry(
                    "preference", f"MC-PREF-20260924-{index:08x}",
                    f"Archived preference {index}", f"Historical behavior {index}.",
                    None, "project", ("user-confirmed",),
                )
                for index in range(500)
            ]
            archive_path = memory / "archive" / "scale-history.md"
            archive_path.parent.mkdir(parents=True, exist_ok=True)
            archive_path.write_text(
                "# Scale History\n\n" + "\n\n".join(archived) + "\n",
                encoding="utf-8",
            )

            snapshot = build_snapshot(memory, root)
            active = [entry for entry in snapshot.entries if entry.status == "active"]
            candidate = [entry for entry in snapshot.entries if entry.status == "candidate"]
            archive = [
                entry for entry in snapshot.relation_entries
                if entry.path.relative_to(memory).as_posix().startswith("archive/")
            ]
            self.assertEqual(len(active), 500)
            self.assertEqual(len(candidate), 500)
            self.assertEqual(len(archive), 500)
            self.assertEqual(len(list((memory / "areas").glob("*.md"))), 50)
            source_refs = {
                value for entry in active for value in entry.evidence
                if value.startswith("repo:fixtures/evidence/")
            }
            self.assertEqual(len(source_refs), 100)
            self.assertEqual(len({entry.entry_id.casefold() for entry in snapshot.relation_entries}), 1500)


if __name__ == "__main__":
    unittest.main()
