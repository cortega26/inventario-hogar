import logging
import os
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import List, Optional

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
            try:
                self._backup_connection(conn, "pre-migration")
            except (OSError, sqlite3.Error) as exc:
                logging.warning("Could not create pre-migration backup: %s", exc)

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
        source_count = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        conn.execute(
            f"""
            INSERT OR IGNORE INTO items_new (
                id, name, box, quantity, notes, created_at, updated_at, search_text
            )
            SELECT {", ".join(select_parts)}
            FROM items
            """
        )
        copied_count = conn.execute("SELECT COUNT(*) FROM items_new").fetchone()[0]
        if copied_count < source_count:
            logging.warning(
                "Migration copied %d of %d rows; %d invalid or duplicate rows were skipped.",
                copied_count,
                source_count,
                source_count - copied_count,
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

            DROP TRIGGER IF EXISTS update_timestamp;
            CREATE TRIGGER update_timestamp
            AFTER UPDATE OF name, box, quantity, notes ON items
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

    def bulk_insert_items(
        self,
        rows: List[tuple[str, str, int, str]],
        *,
        replace: bool = False,
    ) -> tuple[int, int]:
        """Insert validated rows in one transaction.

        Returns ``(inserted, skipped)`` where skipped counts duplicates. With
        ``replace`` the existing inventory is deleted inside the same
        transaction, so a failure rolls everything back.
        """
        if self._closed:
            raise RuntimeError("Database connections have been closed")
        if replace and not rows:
            raise ValueError("No rows to import; refusing to clear the inventory")

        with self.get_connection() as conn:
            try:
                if replace:
                    conn.execute("DELETE FROM items")
                cursor = conn.executemany(
                    "INSERT OR IGNORE INTO items (name, box, quantity, notes) "
                    "VALUES (?, ?, ?, ?)",
                    rows,
                )
                inserted = max(cursor.rowcount, 0)
                skipped = len(rows) - inserted
                conn.commit()
                return inserted, skipped
            except sqlite3.Error:
                conn.rollback()
                raise

    def close_all(self) -> None:
        """Disable this database manager so future operations fail fast."""
        self._closed = True

    def create_backup(self, tag: str = "manual") -> Optional[str]:
        """Create a consistent SQLite backup and prune old copies."""
        if self._closed:
            raise RuntimeError("Database connections have been closed")
        if not Path(self.db_path).exists():
            return None

        source = sqlite3.connect(self.db_path)
        try:
            return self._backup_connection(source, tag)
        finally:
            source.close()

    def backup_if_due(self, interval_hours: Optional[int] = None) -> Optional[str]:
        """Create at most one automatic backup per configured interval."""
        if not Path(self.db_path).exists():
            return None

        interval = (
            AppConfig.BACKUP_INTERVAL_HOURS
            if interval_hours is None
            else interval_hours
        )
        directory = Path(self.db_path).parent / AppConfig.BACKUP_DIR
        stem = Path(self.db_path).stem or "inventory"
        backups = list(directory.glob(f"{stem}-*.db"))
        if backups:
            newest = max(backup.stat().st_mtime for backup in backups)
            if time.time() - newest < interval * 3600:
                return None

        return self.create_backup(tag="auto")

    def _backup_connection(
        self, conn: sqlite3.Connection, tag: str
    ) -> Optional[str]:
        destination = self._backup_path(tag)
        destination.parent.mkdir(parents=True, exist_ok=True)
        target = sqlite3.connect(destination)
        try:
            conn.backup(target)
        finally:
            target.close()
        try:
            os.chmod(destination, 0o600)
        except OSError as exc:
            logging.warning("Could not restrict backup permissions: %s", exc)
        self._prune_backups()
        return str(destination)

    def _backup_path(self, tag: str) -> Path:
        stem = Path(self.db_path).stem or "inventory"
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        return (
            Path(self.db_path).parent
            / AppConfig.BACKUP_DIR
            / f"{stem}-{tag}-{timestamp}.db"
        )

    def _prune_backups(self) -> None:
        directory = Path(self.db_path).parent / AppConfig.BACKUP_DIR
        stem = Path(self.db_path).stem or "inventory"
        backups = sorted(
            directory.glob(f"{stem}-*.db"),
            key=lambda backup: backup.stat().st_mtime,
            reverse=True,
        )
        for old_backup in backups[AppConfig.BACKUP_RETENTION :]:
            try:
                old_backup.unlink()
            except OSError as exc:
                logging.warning("Could not remove old backup %s: %s", old_backup, exc)

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
                safe_name = table_name.replace('"', '""')
                conn.execute(f'DROP TABLE IF EXISTS "{safe_name}"')
            conn.commit()
            return table_names
