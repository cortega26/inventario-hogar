"""Small presentation helpers shared by the UI layer."""

from __future__ import annotations

from datetime import datetime

MONTHS_ES = (
    "ene",
    "feb",
    "mar",
    "abr",
    "may",
    "jun",
    "jul",
    "ago",
    "sep",
    "oct",
    "nov",
    "dic",
)

_DATE_FORMATS = (
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
)


def format_date(value: object) -> str:
    """Render a database timestamp as a short, human-friendly Spanish date."""
    if value is None:
        return "—"

    text = str(value).strip()
    if not text:
        return "—"

    parsed = None
    for date_format in _DATE_FORMATS:
        try:
            parsed = datetime.strptime(text, date_format)
            break
        except ValueError:
            continue

    if parsed is None:
        return text

    return f"{parsed.day:02d} {MONTHS_ES[parsed.month - 1]} {parsed.year}"
