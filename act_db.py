"""Import inventory data from CSV using the application's canonical schema."""

import argparse
import csv
from pathlib import Path

from inventory_app import AppConfig, Cache, Database, InventoryManager


def iter_csv_items(filename: str):
    """Yield normalized (name, box) pairs from a column-based inventory CSV."""
    with open(filename, "r", encoding="utf-8", newline="") as file:
        csv_reader = csv.reader(file)
        headers = next(csv_reader)

        for row in csv_reader:
            for i, box in enumerate(headers):
                cell = row[i].strip() if i < len(row) else ""
                if cell:
                    yield cell, box.strip()


def update_inventory_from_csv(
    filename: str,
    db_path: str = AppConfig.DB_PATH,
    *,
    replace: bool = False,
) -> dict[str, int | bool]:
    """Import CSV items into the canonical runtime schema."""
    db = Database(db_path)
    inventory = InventoryManager(db, Cache())
    inserted = 0
    skipped = 0

    try:
        if replace:
            db.execute_update("DELETE FROM items")

        for name, box in iter_csv_items(filename):
            if inventory.add_item(name, box):
                inserted += 1
            else:
                skipped += 1
        return {
            "inserted": inserted,
            "skipped": skipped,
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
    report = update_inventory_from_csv(
        args.csv_filename,
        db_path=args.db_path,
        replace=args.replace,
    )
    mode = (
        "reemplazando todos los artículos existentes"
        if args.replace
        else "sin borrar artículos existentes"
    )
    print(
        f"Importacion completada desde {Path(args.csv_filename)} hacia {args.db_path}: "
        f"{report['inserted']} agregados, {report['skipped']} omitidos por duplicado "
        f"({mode})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
