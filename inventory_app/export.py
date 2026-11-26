"""Export inventory rows to CSV and Excel workbooks."""

from __future__ import annotations

import csv
from datetime import datetime
from typing import Iterable, Mapping

EXPORT_COLUMNS = ("id", "name", "box", "quantity", "notes", "updated_at")
EXCEL_HEADERS = ("ID", "Artículo", "Ubicación", "Cantidad", "Notas", "Actualizado")

_FORMULA_PREFIXES = ("=", "+", "-", "@")
_DATE_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d",
)


def _as_text(value: object) -> str:
    return "" if value is None else str(value)


def _csv_safe(value: object) -> str:
    """Prefix spreadsheet formula triggers so exported CSV stays inert."""
    text = _as_text(value)
    if text.startswith(_FORMULA_PREFIXES):
        return "'" + text
    return text


def parse_updated_at(value: object) -> datetime | str:
    """Convert the stored timestamp to a datetime when possible."""
    text = _as_text(value).strip()
    for date_format in _DATE_FORMATS:
        try:
            return datetime.strptime(text, date_format)
        except ValueError:
            continue
    return text


def write_csv(path: str, items: Iterable[Mapping]) -> int:
    """Write rows as a UTF-8 CSV report and return the number exported."""
    count = 0
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(EXPORT_COLUMNS)
        for item in items:
            writer.writerow([_csv_safe(item.get(column, "")) for column in EXPORT_COLUMNS])
            count += 1
    return count


def write_xlsx(path: str, items: Iterable[Mapping]) -> int:
    """Write a styled Excel workbook and return the number exported."""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise RuntimeError(
            "Para exportar a Excel instala openpyxl: pip install openpyxl"
        ) from exc

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Inventario"
    sheet.sheet_view.showGridLines = False
    sheet.freeze_panes = "A2"

    header_fill = PatternFill("solid", fgColor="0F766E")
    header_font = Font(color="FFFFFF", bold=True, size=11)
    zebra_fill = PatternFill("solid", fgColor="F8FAFC")
    border = Border(bottom=Side(style="thin", color="E2E8F0"))

    for column_index, header in enumerate(EXCEL_HEADERS, start=1):
        cell = sheet.cell(row=1, column=column_index, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(vertical="center")

    count = 0
    for row_index, item in enumerate(items, start=2):
        values = (
            item.get("id", ""),
            item.get("name", ""),
            item.get("box", ""),
            item.get("quantity", ""),
            item.get("notes", ""),
            parse_updated_at(item.get("updated_at", "")),
        )
        for column_index, value in enumerate(values, start=1):
            cell = sheet.cell(row=row_index, column=column_index)
            cell.value = value
            if isinstance(value, str):
                # Force text so values like "=HYPERLINK(...)" never become formulas.
                cell.data_type = "s"
            cell.alignment = Alignment(
                vertical="top",
                wrap_text=column_index in (2, 3, 5),
            )
            cell.border = border
            if row_index % 2 == 0:
                cell.fill = zebra_fill
            if column_index == 4:
                cell.number_format = "#,##0"
            elif column_index == 6 and isinstance(value, datetime):
                cell.number_format = "dd mmm yyyy hh:mm"
        count += 1

    widths = {"A": 8, "B": 44, "C": 26, "D": 11, "E": 60, "F": 20}
    for column_letter, width in widths.items():
        sheet.column_dimensions[column_letter].width = width

    sheet.row_dimensions[1].height = 24
    sheet.auto_filter.ref = f"A1:F{max(1, sheet.max_row)}"
    sheet.print_title_rows = "1:1"
    sheet.sheet_properties.tabColor = "0F766E"

    workbook.properties.title = "Inventario Hogar"
    workbook.properties.creator = "Inventario Hogar"
    workbook.save(path)
    return count
