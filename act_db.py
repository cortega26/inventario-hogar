"""Import inventory data from CSV using the application's canonical schema."""

import argparse
import csv
import sqlite3
from pathlib import Path

from inventory_app import AppConfig, Cache, Database, InventoryManager


def iter_csv_items(filename: str):
    """Yield normalized (name, box) pairs from a column-based inventory CSV."""
    with open(filename, "r", encoding="utf-8", newline="") as file:
        csv_reader = csv.reader(file)
        headers = next(csv_reader, None)
        if not headers:
            return

        headers = [header.strip().lstrip("\ufeff") for header in headers]
        for row in csv_reader:
            for i, box in enumerate(headers):
                cell = row[i].strip() if i < len(row) else ""
                if cell:
                    yield cell, box


def update_inventory_from_csv(
    filename: str,
    db_path: str = AppConfig.DB_PATH,
    *,
    replace: bool = False,
) -> dict[str, int | bool]:
    """Import CSV items into the canonical runtime schema.

    The CSV is fully read and validated before the database is touched, so a
    failed ``--replace`` can never leave the inventory empty.
    """
    rows = list(iter_csv_items(filename))
    if replace and not rows:
        raise ValueError(
            "El CSV no contiene artículos; no se reemplazó el inventario."
        )

    db = Database(db_path)
    inventory = InventoryManager(db, Cache())

    try:
        if replace:
            db.create_backup(tag="pre-replace")
        inserted, skipped, invalid = inventory.import_items(rows, replace=replace)
        return {
            "inserted": inserted,
            "skipped": skipped,
            "invalid": invalid,
            "replaced": replace,
        }
    finally:
        db.close_all()



def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Importa artículos desde un CSV a la base de datos del inventario."
    )
    parser.add_argument(
        "csv_filename",
        nargs="?",
        default=AppConfig.DEFAULT_CSV_IMPORT_PATH,
        help="Ruta al archivo CSV de origen.",
    )
    parser.add_argument(
        "--db-path",
        default=AppConfig.DB_PATH,
        help="Ruta a la base de datos SQLite de destino.",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Borra primero todos los artículos existentes antes de importar.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = update_inventory_from_csv(
            args.csv_filename,
            db_path=args.db_path,
            replace=args.replace,
        )
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(f"Error: {exc}")
        return 1

    mode = (
        "reemplazando todos los artículos existentes"
        if args.replace
        else "sin borrar artículos existentes"
    )
    summary = (
        f"Importacion completada desde {Path(args.csv_filename)} hacia {args.db_path}: "
        f"{report['inserted']} agregados, {report['skipped']} omitidos por duplicado "
        f"({mode})."
    )
    if report.get("invalid"):
        summary += f" {report['invalid']} filas invalidas omitidas."
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
