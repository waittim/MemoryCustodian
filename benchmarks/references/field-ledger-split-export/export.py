def export_entries(entries, export_cap):
    rows = list(entries)
    if export_cap is None:
        return rows
    return rows[:export_cap]
