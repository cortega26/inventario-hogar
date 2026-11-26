"""Normalize the inventory database to the canonical runtime schema."""

import argparse

from inventory_app import AppConfig
from inventory_app.db import Database


def migrate_database(db_path: str = AppConfig.DB_PATH) -> None:
    """Rebuild the database schema using the application's canonical rules."""
    database = Database(db_path)
    try:
        removed_fts_tables = database.cleanup_legacy_fts()
    finally:
        database.close_all()

    message = f"Database migration completed successfully for {db_path}."
    if removed_fts_tables:
        message += f" Removed legacy FTS artifacts: {', '.join(removed_fts_tables)}."
    else:
        message += " No legacy FTS artifacts were present."
    print(message)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Normaliza la base de datos del inventario a la estructura canonica."
    )
    parser.add_argument(
        "--db-path",
        default=AppConfig.DB_PATH,
        help="Ruta a la base de datos SQLite que se desea migrar.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    migrate_database(args.db_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
