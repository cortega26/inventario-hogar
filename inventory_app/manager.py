import logging
import re
import sqlite3
from typing import Any, Dict, Iterable, List, Literal, Optional

from .cache import Cache
from .config import AppConfig
from .db import Database

AddItemStatus = Literal["created", "duplicate", "error"]
UpdateItemStatus = Literal["updated", "duplicate", "not_found", "error"]
DeleteItemStatus = Literal["deleted", "not_found", "error"]
TouchItemStatus = Literal["updated", "not_found", "error"]


class InventoryManager:
    """Business logic layer with caching."""

    def __init__(self, db: Database, cache: Cache) -> None:
        self.db = db
        self.cache = cache

    def add_item(
        self,
        name: str,
        box: str,
        quantity: int | str = AppConfig.DEFAULT_QUANTITY,
        notes: str = "",
    ) -> bool:
        return self.add_item_status(name, box, quantity, notes) == "created"

    def add_item_status(
        self,
        name: str,
        box: str,
        quantity: int | str = AppConfig.DEFAULT_QUANTITY,
        notes: str = "",
    ) -> AddItemStatus:
        try:
            name = self._sanitize_input(name, AppConfig.MAX_NAME_LENGTH, "nombre del artículo")
            box = self._sanitize_input(box, AppConfig.MAX_BOX_LENGTH, "ubicación")
            quantity = self._sanitize_quantity(quantity)
            notes = self._sanitize_notes(notes)

            affected = self.db.execute_update(
                "INSERT INTO items (name, box, quantity, notes) VALUES (?, ?, ?, ?)",
                (name, box, quantity, notes),
                log_errors=False,
            )
            self._invalidate_item_cache()
            return "created" if affected > 0 else "error"
        except sqlite3.IntegrityError:
            return "duplicate"
        except sqlite3.Error:
            return "error"

    def update_item(
        self,
        item_id: int,
        name: str,
        box: str,
        quantity: int | str = AppConfig.DEFAULT_QUANTITY,
        notes: str = "",
    ) -> bool:
        return self.update_item_status(item_id, name, box, quantity, notes) == "updated"

    def update_item_status(
        self,
        item_id: int,
        name: str,
        box: str,
        quantity: int | str = AppConfig.DEFAULT_QUANTITY,
        notes: str = "",
    ) -> UpdateItemStatus:
        """Update an existing item."""
        try:
            name = self._sanitize_input(name, AppConfig.MAX_NAME_LENGTH, "nombre del artículo")
            box = self._sanitize_input(box, AppConfig.MAX_BOX_LENGTH, "ubicación")
            quantity = self._sanitize_quantity(quantity)
            notes = self._sanitize_notes(notes)

            affected_rows = self.db.execute_update(
                "UPDATE items SET name = ?, box = ?, quantity = ?, notes = ? WHERE id = ?",
                (name, box, quantity, notes, item_id),
                log_errors=False,
            )
            if affected_rows == 0:
                return "not_found"

            self._invalidate_item_cache()
            return "updated"
        except sqlite3.IntegrityError:
            return "duplicate"
        except sqlite3.Error:
            return "error"

    def delete_item(self, item_id: int) -> bool:
        return self.delete_item_status(item_id) == "deleted"

    def delete_item_status(self, item_id: int) -> DeleteItemStatus:
        try:
            affected_rows = self.db.execute_update(
                "DELETE FROM items WHERE id = ?",
                (item_id,),
            )
            self._invalidate_item_cache()
            return "deleted" if affected_rows > 0 else "not_found"
        except sqlite3.Error:
            return "error"

    def get_unique_boxes(self) -> List[str]:
        """Get list of unique box locations."""
        try:
            results = self.db.execute_query(
                "SELECT DISTINCT box FROM items ORDER BY box COLLATE NOCASE"
            )
            return ["Todas"] + [row["box"] for row in results]
        except sqlite3.Error as exc:
            logging.error("Error getting unique boxes: %s", exc)
            return ["Todas"]

    def import_items(
        self, items: Iterable[tuple[str, str]], *, replace: bool = False
    ) -> tuple[int, int, int]:
        """Validate and bulk-insert CSV rows in a single transaction.

        Returns ``(inserted, skipped, invalid)``. Invalid rows are reported
        instead of aborting the whole import.
        """
        prepared: List[tuple[str, str, int, str]] = []
        invalid = 0

        for name, box in items:
            try:
                clean_name = self._sanitize_input(
                    name, AppConfig.MAX_NAME_LENGTH, "nombre del artículo"
                )
                clean_box = self._sanitize_input(
                    box, AppConfig.MAX_BOX_LENGTH, "ubicación"
                )
            except ValueError:
                invalid += 1
                continue
            prepared.append(
                (clean_name, clean_box, AppConfig.DEFAULT_QUANTITY, "")
            )

        if replace and not prepared:
            raise ValueError(
                "No hay artículos válidos para importar; no se reemplazó el inventario."
            )

        inserted, skipped = self.db.bulk_insert_items(prepared, replace=replace)
        self._invalidate_item_cache()
        return inserted, skipped, invalid

    def get_all_items(
        self, sort_column: Optional[str] = None, descending: bool = False
    ) -> List[Dict[str, Any]]:
        """Get all items with optional sorting."""
        cache_key = f"items_all_{sort_column}_{descending}"
        cached_items = self.cache.get(cache_key)
        if cached_items is not None:
            return cached_items

        column_mapping = {
            "updated": "updated_at",
            "name": "name",
            "box": "box",
            "quantity": "quantity",
            "id": "id",
        }

        if sort_column:
            db_column = column_mapping.get(sort_column, "name")
            sort_direction = "DESC" if descending else "ASC"
            if db_column == "id":
                sort_clause = f"ORDER BY {db_column} {sort_direction}"
            else:
                sort_clause = f"ORDER BY {db_column} COLLATE NOCASE {sort_direction}"
        else:
            sort_clause = "ORDER BY name COLLATE NOCASE"

        items = [
            dict(row)
            for row in self.db.execute_query(
                f"""
                SELECT id, name, box, quantity, notes,
                       strftime('%Y-%m-%d %H:%M', updated_at) as updated_at
                FROM items 
                {sort_clause}
                """
            )
        ]
        self.cache.set(cache_key, items)
        return items

    def search_items(
        self, query: str, sort_column: Optional[str] = None, descending: bool = False
    ) -> List[Dict[str, Any]]:
        """Search items with improved relevance and corrected sorting."""
        if not query:
            return self.get_all_items(sort_column, descending)

        cache_key = f"items_search_{query}_{sort_column}_{descending}"
        cached_results = self.cache.get(cache_key)
        if cached_results is not None:
            return cached_results

        column_mapping = {
            "updated": "updated_at",
            "name": "name",
            "box": "box",
            "quantity": "quantity",
            "id": "id",
        }

        if sort_column:
            db_column = column_mapping.get(sort_column, "name")
            sort_direction = "DESC" if descending else "ASC"
            if db_column == "id":
                sort_clause = f"ORDER BY {db_column} {sort_direction}"
            else:
                sort_clause = f"ORDER BY {db_column} COLLATE NOCASE {sort_direction}"

            query_str = """
                SELECT id, name, box, quantity, notes,
                       strftime('%Y-%m-%d %H:%M', updated_at) as updated_at
                FROM items 
                WHERE search_text LIKE ?
                {sort_clause}
            """.format(
                sort_clause=sort_clause
            )
            params = (f"%{query.lower()}%",)
        else:
            sort_clause = """
                ORDER BY 
                    CASE 
                        WHEN lower(name) = ? THEN 1
                        WHEN lower(box) = ? THEN 2
                        WHEN lower(name) LIKE ? THEN 3
                        WHEN lower(box) LIKE ? THEN 4
                        ELSE 5
                    END,
                    name COLLATE NOCASE
            """
            query_str = f"""
                SELECT id, name, box, quantity, notes,
                       strftime('%Y-%m-%d %H:%M', updated_at) as updated_at
                FROM items 
                WHERE search_text LIKE ?
                {sort_clause}
            """
            search_term = f"%{query.lower()}%"
            params = (search_term, query.lower(), query.lower(), search_term, search_term)

        rows = self.db.execute_query(query_str, params)
        results = [dict(row) for row in rows]

        self.cache.set(cache_key, results, ttl=AppConfig.CACHE_TTL_SEARCH)
        return results

    def touch_item(self, item_id: int) -> bool:
        return self.touch_item_status(item_id) == "updated"

    def touch_item_status(self, item_id: int) -> TouchItemStatus:
        """Update an item's timestamp without changing other fields."""
        try:
            affected_rows = self.db.execute_update(
                "UPDATE items SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (item_id,),
            )
            if affected_rows == 0:
                return "not_found"

            self._invalidate_item_cache()
            return "updated"
        except sqlite3.Error:
            return "error"

    @staticmethod
    def _sanitize_input(value: str, max_length: int, field_name: str) -> str:
        """Sanitize input with meaningful validation feedback."""
        label = field_name or "campo"

        if not value or not value.strip():
            raise ValueError(f"El campo '{label}' no puede estar vacío")

        sanitized = re.sub(r"[^\w\s\-'(),\.°]", "", value.strip())
        if not sanitized.strip():
            raise ValueError(f"El campo '{label}' no contiene caracteres válidos")
        if len(sanitized) > max_length:
            raise ValueError(f"El campo '{label}' supera el máximo de {max_length} caracteres")

        return sanitized

    @staticmethod
    def _sanitize_quantity(quantity: int | str) -> int:
        """Validate and normalize positive integer quantities."""
        if isinstance(quantity, str):
            quantity = quantity.strip()

        try:
            normalized = int(quantity)
        except (TypeError, ValueError) as exc:
            raise ValueError("La cantidad debe ser un número entero positivo") from exc

        if normalized < 1:
            raise ValueError("La cantidad debe ser un número entero positivo")

        return normalized

    @staticmethod
    def _sanitize_notes(notes: str) -> str:
        """Normalize optional notes without stripping useful punctuation."""
        normalized = (notes or "").strip()
        if len(normalized) > AppConfig.MAX_NOTES_LENGTH:
            raise ValueError(
                f"Las notas superan el máximo de {AppConfig.MAX_NOTES_LENGTH} caracteres"
            )
        return normalized

    def _invalidate_item_cache(self) -> None:
        """Clear all cached item list and search results."""
        self.cache.invalidate_prefix("items_")
