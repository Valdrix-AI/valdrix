from typing import Any

_CSV_FORMULA_PREFIXES = ("=", "+", "@", "\t")


def _sanitize_csv_cell(value: Any) -> str:
    """
    Prevent CSV formula injection when exported files are opened in spreadsheet tools.

    Note: we intentionally do NOT treat '-' as a formula prefix because negative values
    are valid and common in financial exports.
    """
    if value is None:
        return ""
    text = str(value)
    if not text:
        return ""
    if text.startswith(_CSV_FORMULA_PREFIXES):
        return "'" + text
    return text


def _rowcount(result: Any) -> int:
    raw_count = getattr(result, "rowcount", None)
    return raw_count if isinstance(raw_count, int) else 0
