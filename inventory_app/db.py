import logging
import sqlite3
from contextlib import contextmanager
from typing import List

from .config import AppConfig


class Database:
    """Database manager with per-operation SQLite connections."""

    def __init__(self, db_path: str = AppConfig.DB_PATH) -> None:
        self.db_path = db_path
        self._closed = False
        self._initialize_db()

    def _create_connection(self) -> sqlite3.Connection:
        """Create a new SQLite connection with standard configuration."""
        conn = sqlite3.connect(
            self.db_path,
            timeout=AppConfig.DB_TIMEOUT,
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        conn.row_factory = sqlite3.Row
        return conn

    def _initialize_db(self) -> None:
        """Initialize database schema with proper constraints."""
        conn = self._create_connection()
        try:
            self._rebuild_items_table(conn)
            self._ensure_runtime_objects(conn)
            conn.commit()
        finally:
            conn.close()

    def _rebuild_items_table(self, conn: sqlite3.Connection) -> None:
        """Normalize the items table to the canonical runtime schema."""
        table_exists = (
            conn.execute(
                """
                SELECT 1 FROM sqlite_master
                WHERE type='table' AND name='items'
                """
            ).fetchone()
            is not None
        )

        if table_exists:
            columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(items)").fetchall()
            }
            canonical_columns = {
                "id",
                "name",
                "box",
                "quantity",
                "notes",
                "created_at",
                "updated_at",
                "search_text",
            }
            if columns == canonical_columns:
                return

        conn.executescript(
            """
            DROP TRIGGER IF EXISTS update_timestamp;
            DROP TRIGGER IF EXISTS update_search_text;
            DROP TRIGGER IF EXISTS update_search_text_on_update;
            DROP INDEX IF EXISTS idx_search_text;
            DROP INDEX IF EXISTS idx_updated_at;
            DROP INDEX IF EXISTS idx_updated;

            CREATE TABLE items_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL CHECK(length(name) <= 255),
                box TEXT NOT NULL CHECK(length(box) <= 100),
                quantity INTEGER NOT NULL DEFAULT 1 CHECK(quantity >= 1),
                notes TEXT NOT NULL DEFAULT '' CHECK(length(notes) <= 1000),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                search_text TEXT,
                UNIQUE(name, box)
            );
            """
        )

        if table_exists:
            self._copy_items_data(conn)
            conn.execute("DROP TABLE items")

        conn.execute("ALTER TABLE items_new RENAME TO items")

    def _copy_items_data(self, conn: sqlite3.Connection) -> None:
        """Copy legacy data into the canonical table."""
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(items)").fetchall()
        }
        select_parts = [
            "id" if "id" in columns else "NULL AS id",
            "name",
            "box",
            "quantity" if "quantity" in columns else "1 AS quantity",
            "notes" if "notes" in columns else "'' AS notes",
            "created_at" if "created_at" in columns else "CURRENT_TIMESTAMP AS created_at",
            (
                "updated_at"
                if "updated_at" in columns
                else "CURRENT_TIMESTAMP AS updated_at"
            ),
            (
                "search_text"
                if "search_text" in columns
                else (
                    "trim(lower(name || ' ' || box || ' ' || coalesce(notes, ''))) AS search_text"
                    if "notes" in columns
                    else "trim(lower(name || ' ' || box)) AS search_text"
                )
            ),
        ]
        conn.execute(
            f"""
            INSERT OR IGNORE INTO items_new (
                id, name, box, quantity, notes, created_at, updated_at, search_text
            )
            SELECT {", ".join(select_parts)}
            FROM items
            """
        )
        conn.execute(
            """
            UPDATE items_new
            SET search_text = trim(lower(name || ' ' || box || ' ' || coalesce(notes, '')))
            WHERE search_text IS NULL OR trim(search_text) = ''
            """
        )

    def _ensure_runtime_objects(self, conn: sqlite3.Connection) -> None:
        """Create indexes and triggers required by the runtime schema."""
        conn.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_search_text ON items(search_text);
            CREATE INDEX IF NOT EXISTS idx_updated_at ON items(updated_at);

            CREATE TRIGGER IF NOT EXISTS update_timestamp
            AFTER UPDATE ON items
            BEGIN
                UPDATE items
                SET updated_at = CURRENT_TIMESTAMP
                WHERE id = NEW.id;
            END;

            CREATE TRIGGER IF NOT EXISTS update_search_text
            AFTER INSERT ON items
            BEGIN
                UPDATE items
                SET search_text = trim(lower(NEW.name || ' ' || NEW.box || ' ' || NEW.notes))
                WHERE id = NEW.id;
            END;

            CREATE TRIGGER IF NOT EXISTS update_search_text_on_update
            AFTER UPDATE OF name, box, notes ON items
            BEGIN
                UPDATE items
                SET search_text = trim(lower(NEW.name || ' ' || NEW.box || ' ' || NEW.notes))
                WHERE id = NEW.id;
            END;
            """
        )

    @contextmanager
    def get_connection(self):
        """Get a fresh database connection for one operation."""
        if self._closed:
            raise RuntimeError("Database connections have been closed")

        connection = self._create_connection()
        try:
            yield connection
        except sqlite3.Error:
            connection.rollback()
            raise
        finally:
            try:
                connection.close()
            except sqlite3.Error as close_error:
                logging.error("Error closing connection: %s", close_error)

    def execute_query(self, query: str, params: tuple = ()) -> List[sqlite3.Row]:
        """Execute a query that returns rows."""
        with self.get_connection() as conn:
            try:
                cursor = conn.execute(query, params)
                return cursor.fetchall()
            except sqlite3.Error as exc:
                logging.error("Query error: %s, params: %s, error: %s", query, params, exc)
                raise

    def execute_update(
        self,
        query: str,
        params: tuple = (),
        *,
        log_errors: bool = True,
    ) -> int:
        """Execute an update/delete query and return number of affected rows."""
        with self.get_connection() as conn:
            try:
                cursor = conn.execute(query, params)
                conn.commit()
                return cursor.rowcount
            except sqlite3.Error as exc:
                if log_errors:
                    logging.error(
                        "Update error: %s, params: %s, error: %s",
                        query,
                        params,
                        exc,
                    )
                raise

    def close_all(self) -> None:
        """Disable this database manager so future operations fail fast."""
        self._closed = True

    def cleanup_legacy_fts(self) -> List[str]:
        """Remove unmanaged legacy FTS tables left by older app versions."""
        if self._closed:
            raise RuntimeError("Database connections have been closed")

        with self.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type='table' AND name LIKE 'items_fts%'
                ORDER BY name
                """
            ).fetchall()
            table_names = [row["name"] for row in rows]
            for table_name in table_names:
                conn.execute(f'DROP TABLE IF EXISTS "{table_name}"')
            conn.commit()
            return table_names
