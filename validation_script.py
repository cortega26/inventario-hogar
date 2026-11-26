"""Validate the canonical inventory database schema."""

import argparse
import sqlite3
from pathlib import Path

from inventory_app import AppConfig


def validate_database_schema(db_path: str = AppConfig.DB_PATH) -> bool:
    """Validate that the runtime schema matches the canonical layout."""
    if db_path != ":memory:" and not Path(db_path).exists():
        print(f"Database file does not exist: {db_path}")
        return False

    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='items'
            """
        )
        if cursor.fetchone() is None:
            print("Items table does not exist")
            return False

        cursor.execute("PRAGMA table_info(items)")
        columns = [row[1] for row in cursor.fetchall()]
        required_columns = [
            "id",
            "name",
            "box",
            "quantity",
            "notes",
            "created_at",
            "updated_at",
            "search_text",
        ]
        if columns != required_columns:
            print(f"Unexpected columns: {columns}")
            return False

        cursor.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type='index' AND tbl_name='items'
            """
        )
        indexes = {row[0] for row in cursor.fetchall()}
        required_indexes = {"idx_search_text", "idx_updated_at"}
        missing_indexes = required_indexes - indexes
        if missing_indexes:
            print(f"Missing indexes: {missing_indexes}")
            return False
        if "idx_updated" in indexes:
            print("Legacy index idx_updated should not exist")
            return False

        cursor.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type='trigger' AND tbl_name='items'
            """
        )
        triggers = {row[0] for row in cursor.fetchall()}
        required_triggers = {
            "update_timestamp",
            "update_search_text",
            "update_search_text_on_update",
        }
        missing_triggers = required_triggers - triggers
        if missing_triggers:
            print(f"Missing triggers: {missing_triggers}")
            return False

        cursor.execute(
            """
            SELECT name FROM sqlite_master
            WHERE name LIKE 'items_fts%'
            ORDER BY name
            """
        )
        legacy_fts_tables = [row[0] for row in cursor.fetchall()]
        if legacy_fts_tables:
            print(
                "Database schema validation successful "
                f"(legacy unmanaged FTS artifacts detected: {', '.join(legacy_fts_tables)})"
            )
            return True

        print("Database schema validation successful")
        return True
    except sqlite3.Error as exc:
        print(f"Database validation error: {exc}")
        return False
    finally:
        conn.close()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Valida que la base de datos del inventario use la estructura canonica."
    )
    parser.add_argument(
        "--db-path",
        default=AppConfig.DB_PATH,
        help="Ruta a la base de datos SQLite que se desea validar.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return 0 if validate_database_schema(args.db_path) else 1


if __name__ == "__main__":
    raise SystemExit(main())
