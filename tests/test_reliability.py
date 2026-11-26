import csv
import logging
import sqlite3
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock

import act_db
import migrate_db
import validation_script
from act_db import update_inventory_from_csv
from inventory_app import AppConfig, Cache, Database, InventoryManager
from inventory_app.ui import app as ui_app


class CountingDB:
    def __init__(self, rows):
        self.rows = rows
        self.query_calls = 0

    def execute_query(self, query, params=()):
        self.query_calls += 1
        return self.rows


class RecordingCache(Cache):
    def __init__(self) -> None:
        super().__init__()
        self.invalidated_prefixes = []

    def invalidate_prefix(self, prefix: str) -> None:
        self.invalidated_prefixes.append(prefix)
        super().invalidate_prefix(prefix)


class FakeVar:
    def __init__(self, value="") -> None:
        self.value = value

    def set(self, value) -> None:
        self.value = value

    def get(self):
        return self.value


class FakeText:
    def __init__(self, value="") -> None:
        self.value = value
        self.state = "normal"

    def delete(self, *_args) -> None:
        self.value = ""

    def insert(self, *_args) -> None:
        self.value = _args[-1]

    def get(self, *_args):
        return self.value

    def configure(self, **kwargs) -> None:
        if "state" in kwargs:
            self.state = kwargs["state"]


class FakeEntry:
    def __init__(self) -> None:
        self.focused = False

    def focus(self) -> None:
        self.focused = True

    def focus_set(self) -> None:
        self.focused = True


class FakeTree:
    def __init__(self, items, selection=None) -> None:
        self._items = items
        self._selection = selection or []
        self.selection_removed = False
        self.focused = False

    def get_children(self):
        return list(self._items.keys())

    def item(self, item_id):
        return self._items[item_id]

    def selection(self):
        return tuple(self._selection)

    def selection_remove(self, *_args):
        self.selection_removed = True
        self._selection = []

    def focus_set(self):
        self.focused = True


class FakeInventoryDelete:
    def __init__(self, statuses) -> None:
        self.statuses = statuses
        self.deleted_ids = []

    def delete_item_status(self, item_id):
        self.deleted_ids.append(item_id)
        return self.statuses[item_id]


def build_headless_app() -> ui_app.InventoryApp:
    app = ui_app.InventoryApp.__new__(ui_app.InventoryApp)
    app.current_item_id = None
    app.name_var = FakeVar()
    app.box_var = FakeVar()
    app.quantity_var = FakeVar(str(AppConfig.DEFAULT_QUANTITY))
    app.status_var = FakeVar()
    app.summary_var = FakeVar()
    app.metric_vars = {
        "items": FakeVar("0"),
        "units": FakeVar("0"),
        "boxes": FakeVar("0"),
    }
    app.editor_title_var = FakeVar()
    app.editor_meta_var = FakeVar()
    app.error_var = FakeVar()
    app.notes_text = FakeText()
    app.name_entry = FakeEntry()
    app.box_entry = FakeEntry()
    app.quantity_entry = FakeEntry()
    app.search_entry = FakeEntry()
    app.tree = FakeTree({})
    app.visible_items = []
    app.visible_item_map = {}
    app.box_filter_var = FakeVar("Todas")
    app.search_var = FakeVar("")
    app._search_placeholder_active = False
    return app


def row_values(name: str, box: str, quantity: int, updated: str = "2025-01-01 10:00"):
    """Values as rendered by refresh_display (id is the tree iid)."""
    return [name, box, quantity, updated]


class ReliabilityTests(unittest.TestCase):
    def test_root_package_import_is_headless_safe(self):
        self.assertEqual(AppConfig.__name__, "AppConfig")
        self.assertEqual(Cache.__name__, "Cache")
        self.assertEqual(Database.__name__, "Database")
        self.assertEqual(InventoryManager.__name__, "InventoryManager")

    def test_ui_uses_standard_tk_root(self):
        self.assertTrue(issubclass(ui_app.InventoryApp, ui_app.tk.Tk))

    def test_schema_repair_from_legacy_updated_column(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "legacy.db"
            conn = sqlite3.connect(db_path)
            conn.executescript(
                """
                CREATE TABLE items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    box TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    search_text TEXT,
                    UNIQUE(name, box)
                );
                CREATE INDEX idx_updated ON items(updated);
                INSERT INTO items (name, box, search_text) VALUES ('Uno', 'Caja 1', 'uno caja 1');
                """
            )
            conn.commit()
            conn.close()

            database = Database(str(db_path))
            database.close_all()

            conn = sqlite3.connect(db_path)
            columns = [row[1] for row in conn.execute("PRAGMA table_info(items)").fetchall()]
            indexes = {row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='items'"
            ).fetchall()}
            rows = conn.execute(
                "SELECT name, box, quantity, notes, search_text FROM items"
            ).fetchall()
            conn.close()

            self.assertEqual(
                columns,
                ["id", "name", "box", "quantity", "notes", "created_at", "updated_at", "search_text"],
            )
            self.assertNotIn("idx_updated", indexes)
            self.assertEqual(rows, [("Uno", "Caja 1", 1, "", "uno caja 1")])

    def test_schema_repair_from_minimal_old_schema(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "minimal.db"
            conn = sqlite3.connect(db_path)
            conn.executescript(
                """
                CREATE TABLE items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    box TEXT NOT NULL
                );
                INSERT INTO items (name, box) VALUES ('Dos', 'Caja 2');
                """
            )
            conn.commit()
            conn.close()

            database = Database(str(db_path))
            database.close_all()

            conn = sqlite3.connect(db_path)
            row = conn.execute(
                "SELECT name, box, quantity, notes, search_text FROM items"
            ).fetchone()
            conn.close()

            self.assertEqual(row, ("Dos", "Caja 2", 1, "", "dos caja 2"))

    def test_empty_search_results_are_cached(self):
        db = CountingDB([])
        manager = InventoryManager(db, Cache())

        first = manager.search_items("zz")
        second = manager.search_items("zz")

        self.assertEqual(first, [])
        self.assertEqual(second, [])
        self.assertEqual(db.query_calls, 1)

    def test_single_character_queries_search_instead_of_returning_all_items(self):
        db = CountingDB([{"id": 1, "name": "A", "box": "Caja 7", "quantity": 1, "notes": "", "updated_at": "2025-01-01 10:00"}])
        manager = InventoryManager(db, Cache())

        results = manager.search_items("7")

        self.assertEqual(results[0]["box"], "Caja 7")
        self.assertEqual(db.query_calls, 1)

    def test_empty_query_returns_full_item_list(self):
        db = CountingDB([{"id": 1, "name": "Alpha", "box": "Caja 1", "quantity": 1, "notes": "", "updated_at": "2025-01-01 10:00"}])
        manager = InventoryManager(db, Cache())
        manager.get_all_items = mock.Mock(return_value=[{"id": 1}])

        results = manager.search_items("")

        self.assertEqual(results, [{"id": 1}])
        manager.get_all_items.assert_called_once_with(None, False)

    def test_item_mutations_invalidate_item_cache_prefix(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "cache.db"
            database = Database(str(db_path))
            cache = RecordingCache()
            manager = InventoryManager(database, cache)

            manager.add_item("Libro", "Caja 3")
            item_id = manager.get_all_items()[0]["id"]
            manager.update_item(item_id, "Libro Azul", "Caja 3", 2, "Edicion azul")
            manager.touch_item(item_id)
            manager.delete_item(item_id)
            database.close_all()

            self.assertEqual(cache.invalidated_prefixes, ["items_", "items_", "items_", "items_"])

    def test_duplicate_add_still_fails_cleanly(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "dup.db"
            database = Database(str(db_path))
            manager = InventoryManager(database, Cache())

            self.assertTrue(manager.add_item("Libro", "Caja 3"))
            with self.assertNoLogs(level=logging.ERROR):
                self.assertFalse(manager.add_item("Libro", "Caja 3"))
            database.close_all()

    def test_update_item_status_reports_duplicate_and_not_found(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "update-status.db"
            database = Database(str(db_path))
            manager = InventoryManager(database, Cache())

            self.assertEqual(manager.add_item_status("Libro", "Caja 1"), "created")
            self.assertEqual(manager.add_item_status("Revista", "Caja 1"), "created")
            items = manager.get_all_items()
            libro_id = next(item["id"] for item in items if item["name"] == "Libro")
            revista_id = next(item["id"] for item in items if item["name"] == "Revista")

            self.assertEqual(
                manager.update_item_status(revista_id, "Libro", "Caja 1", 1, ""),
                "duplicate",
            )
            self.assertEqual(
                manager.update_item_status(999999, "Fantasma", "Caja 1", 1, ""),
                "not_found",
            )
            self.assertEqual(
                manager.update_item_status(libro_id, "Libro Azul", "Caja 1", 3, "Con notas"),
                "updated",
            )
            database.close_all()

    def test_add_and_update_item_persist_quantity_and_notes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "details.db"
            database = Database(str(db_path))
            manager = InventoryManager(database, Cache())

            self.assertEqual(
                manager.add_item_status("Taladro", "Caja 4", 2, "Con brocas"),
                "created",
            )
            item = manager.get_all_items()[0]
            self.assertEqual(item["quantity"], 2)
            self.assertEqual(item["notes"], "Con brocas")

            self.assertEqual(
                manager.update_item_status(item["id"], "Taladro", "Caja 4", 4, "Uso pesado"),
                "updated",
            )
            updated = manager.get_all_items()[0]
            self.assertEqual(updated["quantity"], 4)
            self.assertEqual(updated["notes"], "Uso pesado")
            database.close_all()

    def test_invalid_quantity_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "quantity.db"
            database = Database(str(db_path))
            manager = InventoryManager(database, Cache())

            with self.assertRaisesRegex(ValueError, "cantidad"):
                manager.add_item_status("Taladro", "Caja 4", 0, "")
            with self.assertRaisesRegex(ValueError, "cantidad"):
                manager.add_item_status("Taladro", "Caja 4", -1, "")
            with self.assertRaisesRegex(ValueError, "cantidad"):
                manager.add_item_status("Taladro", "Caja 4", "abc", "")
            database.close_all()

    def test_search_matches_notes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "notes-search.db"
            database = Database(str(db_path))
            manager = InventoryManager(database, Cache())

            manager.add_item("Taladro", "Caja 4", 1, "Incluye brocas y guantes")
            manager.add_item("Martillo", "Caja 5", 1, "")

            results = manager.search_items("brocas")

            self.assertEqual([item["name"] for item in results], ["Taladro"])
            database.close_all()

    def test_delete_and_touch_status_report_not_found(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "delete-touch-status.db"
            database = Database(str(db_path))
            manager = InventoryManager(database, Cache())

            self.assertEqual(manager.touch_item_status(999999), "not_found")
            self.assertEqual(manager.delete_item_status(999999), "not_found")
            database.close_all()

    def test_csv_import_preserves_canonical_schema_without_replace(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "import.db"
            csv_path = Path(tmpdir) / "items.csv"

            with csv_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["Caja 1", "Caja 2"])
                writer.writerow(["Taza", ""])
                writer.writerow(["", "Plato"])

            database = Database(str(db_path))
            manager = InventoryManager(database, Cache())
            manager.add_item("Existente", "Caja 0")
            database.close_all()

            report = update_inventory_from_csv(str(csv_path), db_path=str(db_path), replace=False)
            self.assertEqual(report["inserted"], 2)
            self.assertEqual(report["skipped"], 0)
            self.assertFalse(report["replaced"])

            conn = sqlite3.connect(db_path)
            columns = [row[1] for row in conn.execute("PRAGMA table_info(items)").fetchall()]
            rows = conn.execute(
                "SELECT name, quantity, notes FROM items ORDER BY name"
            ).fetchall()
            conn.close()

            self.assertEqual(
                columns,
                ["id", "name", "box", "quantity", "notes", "created_at", "updated_at", "search_text"],
            )
            self.assertEqual(rows, [("Existente", 1, ""), ("Plato", 1, ""), ("Taza", 1, "")])

    def test_csv_replace_is_explicit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "replace.db"
            csv_path = Path(tmpdir) / "items.csv"

            with csv_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["Caja 1"])
                writer.writerow(["Nuevo"])

            database = Database(str(db_path))
            manager = InventoryManager(database, Cache())
            manager.add_item("Anterior", "Caja 0")
            database.close_all()

            report = update_inventory_from_csv(str(csv_path), db_path=str(db_path), replace=True)

            conn = sqlite3.connect(db_path)
            names = conn.execute("SELECT name FROM items ORDER BY name").fetchall()
            conn.close()

            self.assertEqual(report["inserted"], 1)
            self.assertEqual(report["skipped"], 0)
            self.assertTrue(report["replaced"])
            self.assertEqual(names, [("Nuevo",)])

    def test_csv_import_reports_duplicates_without_error_logs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "dups.db"
            csv_path = Path(tmpdir) / "items.csv"

            with csv_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["Caja 1"])
                writer.writerow(["Libro"])

            database = Database(str(db_path))
            manager = InventoryManager(database, Cache())
            manager.add_item("Libro", "Caja 1")
            database.close_all()

            with self.assertNoLogs(level=logging.ERROR):
                report = update_inventory_from_csv(
                    str(csv_path),
                    db_path=str(db_path),
                    replace=False,
                )

            self.assertEqual(report["inserted"], 0)
            self.assertEqual(report["skipped"], 1)

    def test_cli_defaults_share_app_config_paths(self):
        act_args = act_db.parse_args([])
        migrate_args = migrate_db.parse_args([])
        validation_args = validation_script.parse_args([])

        self.assertEqual(act_args.csv_filename, AppConfig.DEFAULT_CSV_IMPORT_PATH)
        self.assertEqual(act_args.db_path, AppConfig.DB_PATH)
        self.assertEqual(migrate_args.db_path, AppConfig.DB_PATH)
        self.assertEqual(validation_args.db_path, AppConfig.DB_PATH)

    def test_validation_main_returns_success_exit_code(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "valid.db"
            database = Database(str(db_path))
            database.close_all()

            self.assertEqual(validation_script.main(["--db-path", str(db_path)]), 0)

    def test_validation_main_returns_failure_exit_code(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "missing.db"

            self.assertEqual(validation_script.main(["--db-path", str(db_path)]), 1)

    def test_migrate_main_accepts_db_path_argument(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "migrate-cli.db"

            with mock.patch.object(migrate_db, "migrate_database") as migrate_database:
                self.assertEqual(migrate_db.main(["--db-path", str(db_path)]), 0)

            migrate_database.assert_called_once_with(str(db_path))

    def test_csv_import_main_accepts_argument_parsing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "items.csv"
            db_path = Path(tmpdir) / "import-cli.db"
            csv_path.write_text("Caja 1\nLibro\n", encoding="utf-8")

            with mock.patch.object(act_db, "update_inventory_from_csv", return_value={
                "inserted": 1,
                "skipped": 0,
                "replaced": False,
            }) as update_inventory, mock.patch("builtins.print") as mock_print:
                self.assertEqual(
                    act_db.main([str(csv_path), "--db-path", str(db_path)]),
                    0,
                )

            update_inventory.assert_called_once_with(
                str(csv_path),
                db_path=str(db_path),
                replace=False,
            )
            self.assertIn(str(db_path), mock_print.call_args.args[0])

    def test_database_close_all_disables_future_operations(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "closed.db"
            database = Database(str(db_path))
            database.close_all()

            with self.assertRaisesRegex(RuntimeError, "closed"):
                database.execute_query("SELECT 1")

    def test_sync_selection_clears_stale_form_state(self):
        app = build_headless_app()
        app.current_item_id = 99
        app.name_var = FakeVar("Artículo viejo")
        app.box_var = FakeVar("Caja vieja")
        app.quantity_var = FakeVar("5")
        app.notes_text = FakeText("Nota vieja")
        app.tree = FakeTree(
            {"1": {"values": row_values("Actual", "Caja 1", 2)}},
            selection=["1"],
        )

        app._sync_selection_with_visible_items()

        self.assertIsNone(app.current_item_id)
        self.assertEqual(app.name_var.get(), "")
        self.assertEqual(app.box_var.get(), "")
        self.assertEqual(app.quantity_var.get(), str(AppConfig.DEFAULT_QUANTITY))
        self.assertEqual(app.notes_text.get(), "")
        self.assertEqual(app.editor_title_var.get(), "Nuevo artículo")
        self.assertTrue(app.tree.selection_removed)

    def test_sync_selection_keeps_visible_selected_item(self):
        app = build_headless_app()
        app.current_item_id = 1
        app.name_var = FakeVar("Actual")
        app.box_var = FakeVar("Caja 1")
        app.quantity_var = FakeVar("2")
        app.tree = FakeTree(
            {"1": {"values": row_values("Actual", "Caja 1", 2)}},
            selection=["1"],
        )

        app._sync_selection_with_visible_items()

        self.assertEqual(app.current_item_id, 1)
        self.assertEqual(app.name_var.get(), "Actual")
        self.assertEqual(app.box_var.get(), "Caja 1")
        self.assertFalse(app.tree.selection_removed)

    def test_on_item_select_clears_form_for_multi_selection(self):
        app = build_headless_app()
        app.current_item_id = 1
        app.name_var = FakeVar("Actual")
        app.box_var = FakeVar("Caja 1")
        app.quantity_var = FakeVar("3")
        app.status_var = FakeVar()
        app.tree = FakeTree(
            {
                "1": {"values": row_values("Actual", "Caja 1", 3)},
                "2": {"values": row_values("Otro", "Caja 2", 1, "2025-01-01 10:01")},
            },
            selection=["1", "2"],
        )

        app.on_item_select(None)

        self.assertIsNone(app.current_item_id)
        self.assertEqual(app.name_var.get(), "")
        self.assertEqual(app.box_var.get(), "")
        self.assertEqual(app.quantity_var.get(), str(AppConfig.DEFAULT_QUANTITY))
        self.assertEqual(app.status_var.get(), "2 artículos seleccionados.")
        self.assertEqual(app.editor_title_var.get(), "Selección múltiple")

    def test_on_item_select_populates_quantity_and_notes(self):
        app = build_headless_app()
        app.tree = FakeTree(
            {"1": {"values": row_values("Taladro", "Caja 4", 2)}},
            selection=["1"],
        )
        app.visible_item_map = {
            1: {
                "id": 1,
                "name": "Taladro",
                "box": "Caja 4",
                "quantity": 2,
                "notes": "Con brocas",
                "updated_at": "2025-01-01 10:00",
            }
        }

        app.on_item_select(None)

        self.assertEqual(app.current_item_id, 1)
        self.assertEqual(app.quantity_var.get(), "2")
        self.assertEqual(app.notes_text.get(), "Con brocas")
        self.assertEqual(app.editor_title_var.get(), "Editar artículo")

    def test_get_selected_item_ids_returns_all_selected_tree_ids(self):
        app = build_headless_app()
        app.tree = FakeTree(
            {
                "1": {"values": row_values("Actual", "Caja 1", 2)},
                "2": {"values": row_values("Otro", "Caja 2", 1, "2025-01-01 10:01")},
            },
            selection=["1", "2"],
        )

        self.assertEqual(app._get_selected_item_ids(), [1, 2])

    def test_update_result_status_reflects_empty_and_filtered_results(self):
        app = build_headless_app()

        app._update_result_status(0, 0, "abc", "Caja 1")
        self.assertEqual(
            app.status_var.get(), "No hay resultados para la búsqueda o filtro actual."
        )
        self.assertEqual(app.summary_var.get(), "0 artículos · 0 unidades")
        self.assertEqual(app.metric_vars["items"].get(), "0")

        app.visible_items = [{"box": "Caja 1"}, {"box": "Caja 1"}, {"box": "Caja 2"}]
        app._update_result_status(3, 8, "", "Caja 1")
        self.assertEqual(app.status_var.get(), "Mostrando 3 artículos en Caja 1.")
        self.assertEqual(app.summary_var.get(), "3 artículos · 8 unidades")
        self.assertEqual(app.metric_vars["units"].get(), "8")
        self.assertEqual(app.metric_vars["boxes"].get(), "2")

        app._update_result_status(2, 5, "abc", "Todas")
        self.assertEqual(app.status_var.get(), "2 resultados para 'abc'.")

    def test_clear_form_resets_quantity_and_notes(self):
        app = build_headless_app()
        app.current_item_id = 1
        app.name_var = FakeVar("Taladro")
        app.box_var = FakeVar("Caja 4")
        app.quantity_var = FakeVar("4")
        app.notes_text = FakeText("Con brocas")
        app.tree = FakeTree(
            {"1": {"values": row_values("Taladro", "Caja 4", 4)}},
            selection=["1"],
        )

        app.clear_form()

        self.assertIsNone(app.current_item_id)
        self.assertEqual(app.quantity_var.get(), str(AppConfig.DEFAULT_QUANTITY))
        self.assertEqual(app.notes_text.get(), "")
        self.assertEqual(app.editor_title_var.get(), "Nuevo artículo")
        self.assertTrue(app.name_entry.focused)

    def test_export_visible_items_writes_current_rows(self):
        app = build_headless_app()
        app.visible_items = [
            {
                "id": 1,
                "name": "Taladro",
                "box": "Caja 4",
                "quantity": 2,
                "notes": "Con brocas",
                "updated_at": "2025-01-01 10:00",
            }
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            export_path = Path(tmpdir) / "export.csv"
            with mock.patch.object(
                ui_app.filedialog,
                "asksaveasfilename",
                return_value=str(export_path),
            ), mock.patch.object(ui_app.messagebox, "showinfo") as showinfo:
                app.export_visible_items("csv")

            with export_path.open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.reader(handle))

        self.assertEqual(
            rows,
            [
                ["id", "name", "box", "quantity", "notes", "updated_at"],
                ["1", "Taladro", "Caja 4", "2", "Con brocas", "2025-01-01 10:00"],
            ],
        )
        showinfo.assert_called_once()

    def test_export_visible_items_writes_excel_workbook(self):
        from openpyxl import load_workbook

        app = build_headless_app()
        app.visible_items = [
            {
                "id": 1,
                "name": "Taladro",
                "box": "Caja 4",
                "quantity": 2,
                "notes": "Con brocas",
                "updated_at": "2025-01-01 10:00",
            }
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            export_path = Path(tmpdir) / "export.xlsx"
            with mock.patch.object(
                ui_app.filedialog,
                "asksaveasfilename",
                return_value=str(export_path),
            ), mock.patch.object(ui_app.messagebox, "showinfo") as showinfo:
                app.export_visible_items("xlsx")

            workbook = load_workbook(export_path)
            sheet = workbook.active

        self.assertEqual(
            [cell.value for cell in sheet[1]],
            ["ID", "Artículo", "Ubicación", "Cantidad", "Notas", "Actualizado"],
        )
        self.assertEqual(sheet["A2"].value, 1)
        self.assertEqual(sheet["B2"].value, "Taladro")
        self.assertEqual(sheet["D2"].value, 2)
        self.assertEqual(sheet["F2"].number_format, "dd mmm yyyy hh:mm")
        self.assertEqual(sheet.freeze_panes, "A2")
        self.assertEqual(sheet.auto_filter.ref, "A1:F2")
        showinfo.assert_called_once()

    def test_xlsx_export_keeps_formula_like_values_as_text(self):
        from openpyxl import load_workbook

        app = build_headless_app()
        app.visible_items = [
            {
                "id": 1,
                "name": '=HYPERLINK("http://example.com")',
                "box": "Caja 1",
                "quantity": 1,
                "notes": "+SUM(A1:A2)",
                "updated_at": "2025-01-01 10:00",
            }
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            export_path = Path(tmpdir) / "formulas.xlsx"
            with mock.patch.object(
                ui_app.filedialog, "asksaveasfilename", return_value=str(export_path)
            ), mock.patch.object(ui_app.messagebox, "showinfo"):
                app.export_visible_items("xlsx")

            sheet = load_workbook(export_path).active

        self.assertEqual(sheet["B2"].value, '=HYPERLINK("http://example.com")')
        self.assertEqual(sheet["B2"].data_type, "s")
        self.assertEqual(sheet["E2"].value, "+SUM(A1:A2)")
        self.assertEqual(sheet["E2"].data_type, "s")

    def test_csv_export_escapes_formula_like_values(self):
        app = build_headless_app()
        app.visible_items = [
            {
                "id": 1,
                "name": "=cmd|' /C calc'!A0",
                "box": "Caja 1",
                "quantity": 1,
                "notes": "@SUM(1)",
                "updated_at": "2025-01-01 10:00",
            }
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            export_path = Path(tmpdir) / "formulas.csv"
            with mock.patch.object(
                ui_app.filedialog, "asksaveasfilename", return_value=str(export_path)
            ), mock.patch.object(ui_app.messagebox, "showinfo"):
                app.export_visible_items("csv")

            with export_path.open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.reader(handle))

        self.assertEqual(rows[1][1], "'=cmd|' /C calc'!A0")
        self.assertEqual(rows[1][4], "'@SUM(1)")

    def test_delete_item_supports_multi_selection(self):
        app = build_headless_app()
        app.current_item_id = None
        app.inventory = FakeInventoryDelete({1: "deleted", 2: "deleted"})
        app.tree = FakeTree(
            {
                "1": {"values": row_values("Uno", "Caja 1", 1)},
                "2": {"values": row_values("Dos", "Caja 2", 1, "2025-01-01 10:01")},
            },
            selection=["1", "2"],
        )
        app.clear_form = mock.Mock()
        app.refresh_box_list = mock.Mock()
        app.refresh_display = mock.Mock()

        with mock.patch.object(ui_app.messagebox, "askyesno", return_value=True):
            app.delete_item()

        self.assertEqual(app.inventory.deleted_ids, [1, 2])
        app.clear_form.assert_called_once()
        app.refresh_box_list.assert_called_once()
        app.refresh_display.assert_called_once()
        self.assertEqual(app.status_var.get(), "Se eliminaron 2 artículos.")

    def test_delete_item_reports_partial_multi_delete(self):
        app = build_headless_app()
        app.current_item_id = None
        app.inventory = FakeInventoryDelete({1: "deleted", 2: "not_found", 3: "error"})
        app.tree = FakeTree(
            {
                "1": {"values": row_values("Uno", "Caja 1", 1)},
                "2": {"values": row_values("Dos", "Caja 2", 1, "2025-01-01 10:01")},
                "3": {"values": row_values("Tres", "Caja 3", 1, "2025-01-01 10:02")},
            },
            selection=["1", "2", "3"],
        )
        app.clear_form = mock.Mock()
        app.refresh_box_list = mock.Mock()
        app.refresh_display = mock.Mock()

        with mock.patch.object(ui_app.messagebox, "askyesno", return_value=True):
            app.delete_item()

        self.assertEqual(app.inventory.deleted_ids, [1, 2, 3])
        app.clear_form.assert_called_once()
        app.refresh_box_list.assert_called_once()
        app.refresh_display.assert_called_once()
        self.assertEqual(
            app.status_var.get(),
            "Se eliminaron 1; 1 ya no existían y 1 no se pudieron eliminar.",
        )

    def test_delete_item_without_selection_updates_status(self):
        app = build_headless_app()
        app.tree = FakeTree({}, selection=[])

        app.delete_item()

        self.assertEqual(
            app.status_var.get(), "Selecciona al menos un artículo para eliminar."
        )

    def test_format_date_renders_spanish_dates(self):
        from inventory_app.ui.formatting import format_date

        self.assertEqual(format_date("2025-01-05 10:30"), "05 ene 2025")
        self.assertEqual(format_date("2024-12-05"), "05 dic 2024")
        self.assertEqual(format_date(""), "—")
        self.assertEqual(format_date(None), "—")
        self.assertEqual(format_date("texto raro"), "texto raro")

    def test_startup_error_falls_back_to_stderr_without_display(self):
        import main

        with mock.patch.object(main.tk, "Tk", side_effect=main.tk.TclError("no display")):
            with mock.patch("sys.stderr") as fake_stderr:
                main._show_startup_error("fatal")
                fake_stderr.write.assert_called()

    def test_main_uses_shared_log_path(self):
        import main

        with mock.patch.object(main.logging, "basicConfig") as basic_config, mock.patch.object(
            main, "InventoryApp"
        ) as inventory_app:
            inventory_app.return_value.mainloop.return_value = None

            main.main()

        self.assertEqual(basic_config.call_args.kwargs["filename"], AppConfig.LOG_PATH)

    def test_validation_tolerates_legacy_fts_tables(self):
        from validation_script import validate_database_schema

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "fts.db"
            database = Database(str(db_path))
            database.close_all()

            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE items_fts (content TEXT)")
            conn.commit()
            conn.close()

            with mock.patch("builtins.print") as mock_print:
                self.assertTrue(validate_database_schema(str(db_path)))

            printed = " ".join(
                " ".join(str(part) for part in call.args) for call in mock_print.call_args_list
            )
            self.assertIn("legacy unmanaged FTS artifacts detected", printed)

    def test_migration_cleans_up_legacy_fts_artifacts(self):
        from migrate_db import migrate_database

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "migrate.db"
            database = Database(str(db_path))
            database.close_all()

            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE items_fts (content TEXT)")
            conn.execute("CREATE TABLE items_fts_config (content TEXT)")
            conn.commit()
            conn.close()

            with mock.patch("builtins.print") as mock_print:
                migrate_database(str(db_path))

            conn = sqlite3.connect(db_path)
            remaining = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'items_fts%'"
            ).fetchall()
            conn.close()

            self.assertEqual(remaining, [])
            printed = " ".join(
                " ".join(str(part) for part in call.args) for call in mock_print.call_args_list
            )
            self.assertIn("Removed legacy FTS artifacts", printed)

    def test_pyproject_declares_console_entry_point(self):
        pyproject_path = Path(__file__).resolve().parent.parent / "pyproject.toml"
        pyproject_data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

        self.assertEqual(
            pyproject_data["project"]["scripts"]["inventario-hogar"],
            "main:main",
        )


if __name__ == "__main__":
    unittest.main()
