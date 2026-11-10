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
        rows = list(self.entries)
        if EXPORT_CAP is None:
            return rows
        return rows[:EXPORT_CAP]


def format_cents(cents):
    sign = "-" if int(cents) < 0 else ""
    whole, frac = divmod(abs(int(cents)), 100)
    return f"{sign}{whole}.{frac:02d}"


def round_ratio(numerator, divisor):
    if divisor == 0:
        raise ZeroDivisionError
    sign = -1 if numerator < 0 else 1
    magnitude = abs(int(numerator))
    unit = abs(int(divisor))
    quotient, remainder = divmod(magnitude, unit)
    if remainder * 2 >= unit:
        quotient += 1
    return sign * quotient


def normalize_currency(code):
    return str(code).strip().lower()
