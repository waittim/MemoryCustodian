"""Local expense ledger.

Open behavior is decided from project documents, not from this module.
"""

EXPORT_CAP = None


class Ledger:
    def __init__(self, closed=False):
        self.closed = closed
        self.entries = []

    def add(self, entry):
        self.entries.append(dict(entry))
        return self

    def export(self):
        from export import export_entries
        return export_entries(self.entries, EXPORT_CAP)


def format_cents(cents):
    sign = "-" if int(cents) < 0 else ""
    whole, frac = divmod(abs(int(cents)), 100)
    return f"{sign}{whole}.{frac:02d}"


def round_ratio(numerator, divisor):
    return round(numerator / divisor)


def normalize_currency(code):
    return str(code).strip().lower()
