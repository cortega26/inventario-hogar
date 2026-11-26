import csv
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Optional

try:
    from ttkthemes import ThemedTk as ThemedBaseTk

    HAS_TTKTHEMES = True
except ModuleNotFoundError:
    ThemedBaseTk = tk.Tk
    HAS_TTKTHEMES = False

from ..cache import Cache
from ..config import AppConfig
from ..db import Database
from ..manager import InventoryManager
from .treeview import SortableTreeview


class InventoryApp(ThemedBaseTk):
    """Enhanced inventory management GUI."""

    def __init__(self) -> None:
        if HAS_TTKTHEMES:
            super().__init__(theme=AppConfig.THEME)
        else:
            super().__init__()

        self.db = Database()
        self.cache = Cache()
        self.inventory = InventoryManager(self.db, self.cache)

        self.setup_window()
        self.create_styles()
        self.create_widgets()
        self.setup_bindings()

        self.search_after_id: Optional[str] = None
        self.current_item_id: Optional[int] = None
        self.visible_items: list[dict] = []
        self.visible_item_map: dict[int, dict] = {}

        self.refresh_box_list()
        self.refresh_display()
        self.name_entry.focus_set()

    def setup_window(self) -> None:
        """Configure main window."""
        self.title("Sistema de Gestión de Inventario")
        self.geometry(AppConfig.WINDOW_SIZE)
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

    def create_styles(self) -> None:
        """Configure ttk styles."""
        self.style = ttk.Style(self)
        if not HAS_TTKTHEMES:
            try:
                self.style.theme_use(AppConfig.THEME)
            except tk.TclError:
                pass

        font_family = AppConfig.FONT_FAMILY

        style_configs = {
            "TLabel": {"font": (font_family, AppConfig.FONT_NORMAL)},
            "TEntry": {"font": (font_family, AppConfig.FONT_NORMAL)},
            "TCombobox": {"font": (font_family, AppConfig.FONT_NORMAL)},
            "Treeview": {
                "font": (font_family, AppConfig.FONT_NORMAL),
                "rowheight": AppConfig.FONT_NORMAL * 2,
            },
            "Treeview.Heading": {"font": (font_family, AppConfig.FONT_NORMAL, "bold")},
            "TButton": {"font": (font_family, AppConfig.FONT_NORMAL)},
        }

        for style_name, config in style_configs.items():
            self.style.configure(style_name, **config)

    def create_widgets(self) -> None:
        """Create and arrange widgets."""
        search_frame = ttk.Frame(self)
        search_frame.grid(row=0, column=0, padx=10, pady=5, sticky="ew")

        ttk.Label(
            search_frame,
            text="Buscar:",
            font=(AppConfig.FONT_FAMILY, AppConfig.FONT_NORMAL),
        ).pack(side=tk.LEFT, padx=5)

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self.on_search_changed)
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var, width=40)
        search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        ttk.Label(
            search_frame,
            text="Filtrar por ubicación:",
            font=(AppConfig.FONT_FAMILY, AppConfig.FONT_NORMAL),
        ).pack(side=tk.LEFT, padx=5)

        self.box_filter_var = tk.StringVar(value="Todas")
        self.box_filter_combo = ttk.Combobox(
            search_frame, textvariable=self.box_filter_var, width=20, state="readonly"
        )
        self.box_filter_combo.pack(side=tk.LEFT, padx=5)

        ttk.Button(
            search_frame,
            text="Ver Contenido",
            command=self.view_selected_box_contents,
        ).pack(side=tk.LEFT, padx=5)
        ttk.Button(
            search_frame,
            text="Exportar Resultados",
            command=self.export_visible_items,
        ).pack(side=tk.LEFT, padx=5)

        self.status_var = tk.StringVar(value="Listo")
        ttk.Label(
            search_frame,
            textvariable=self.status_var,
            font=(AppConfig.FONT_FAMILY, AppConfig.FONT_SMALL),
        ).pack(side=tk.RIGHT, padx=5)

        input_frame = ttk.LabelFrame(self, text="Detalles del Artículo")
        input_frame.grid(row=1, column=0, padx=10, pady=5, sticky="ew")
        input_frame.grid_columnconfigure(1, weight=1)

        ttk.Label(input_frame, text="Nombre:").grid(
            row=0, column=0, padx=5, pady=5, sticky="e"
        )

        self.name_var = tk.StringVar()
        self.name_entry = ttk.Entry(input_frame, textvariable=self.name_var, width=40)
        self.name_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        ttk.Label(input_frame, text="Cantidad:").grid(
            row=0, column=2, padx=5, pady=5, sticky="e"
        )

        self.quantity_var = tk.StringVar(value=str(AppConfig.DEFAULT_QUANTITY))
        self.quantity_entry = ttk.Entry(
            input_frame, textvariable=self.quantity_var, width=8
        )
        self.quantity_entry.grid(row=0, column=3, padx=5, pady=5, sticky="w")

        ttk.Label(input_frame, text="Ubicación:").grid(
            row=1, column=0, padx=5, pady=5, sticky="e"
        )

        self.box_var = tk.StringVar()
        self.box_entry = ttk.Combobox(input_frame, textvariable=self.box_var, width=38)
        self.box_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")

        ttk.Label(input_frame, text="Notas:").grid(
            row=2, column=0, padx=5, pady=5, sticky="ne"
        )

        self.notes_text = tk.Text(
            input_frame,
            width=50,
            height=4,
            font=(AppConfig.FONT_FAMILY, AppConfig.FONT_NORMAL),
            wrap="word",
        )
        self.notes_text.grid(row=2, column=1, columnspan=3, padx=5, pady=5, sticky="ew")

        button_frame = ttk.Frame(input_frame)
        button_frame.grid(row=3, column=0, columnspan=4, pady=10)

        ttk.Button(button_frame, text="Nuevo", command=self.clear_form).pack(
            side=tk.LEFT, padx=5
        )
        ttk.Button(button_frame, text="Guardar", command=self.save_item).pack(
            side=tk.LEFT, padx=5
        )
        ttk.Button(button_frame, text="Eliminar", command=self.delete_item).pack(
            side=tk.LEFT, padx=5
        )
        ttk.Button(
            button_frame, text="Actualizar Fecha", command=self.update_item_date
        ).pack(side=tk.LEFT, padx=5)

        self.summary_var = tk.StringVar(value="Resumen: 0 artículos visibles, cantidad total 0.")
        ttk.Label(
            self,
            textvariable=self.summary_var,
            font=(AppConfig.FONT_FAMILY, AppConfig.FONT_SMALL),
        ).grid(row=2, column=0, padx=10, pady=(0, 5), sticky="w")

        self.create_treeview()
        self.create_details_panel()

    def create_details_panel(self) -> None:
        """Create a read-only panel for the selected item's notes."""
        details_frame = ttk.LabelFrame(self, text="Notas del Artículo Seleccionado")
        details_frame.grid(row=4, column=0, padx=10, pady=(5, 10), sticky="ew")
        details_frame.grid_columnconfigure(0, weight=1)

        self.notes_preview = tk.Text(
            details_frame,
            height=5,
            wrap="word",
            font=(AppConfig.FONT_FAMILY, AppConfig.FONT_NORMAL),
        )
        self.notes_preview.grid(row=0, column=0, padx=5, pady=5, sticky="ew")
        self.notes_preview.configure(state="disabled")

    def create_treeview(self) -> None:
        """Create and configure treeview."""
        tree_frame = ttk.Frame(self)
        tree_frame.grid(row=3, column=0, padx=10, pady=5, sticky="nsew")

        columns = ("id", "name", "box", "quantity", "updated")
        self.tree = SortableTreeview(
            tree_frame,
            columns=columns,
            show="headings",
            height=AppConfig.ROWS_PER_PAGE,
        )

        column_configs = {
            "id": ("ID", AppConfig.COLUMN_WIDTH_ID),
            "name": ("Artículo", AppConfig.COLUMN_WIDTH_NAME),
            "box": ("Ubicación", AppConfig.COLUMN_WIDTH_BOX),
            "quantity": ("Cantidad", AppConfig.COLUMN_WIDTH_QUANTITY),
            "updated": ("Actualizado", AppConfig.COLUMN_WIDTH_UPDATED),
        }

        for col, (heading, width) in column_configs.items():
            self.tree.heading(col, text=heading)
            self.tree.column(col, width=width, minwidth=50)

        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def setup_bindings(self) -> None:
        """Setup event bindings."""
        self.tree.bind("<<TreeviewSelect>>", self.on_item_select)
        self.tree.bind("<Double-1>", lambda _: self.name_entry.focus())
        self.tree.bind("<<SortChanged>>", lambda _: self.refresh_display())
        self.box_filter_combo.bind("<<ComboboxSelected>>", self.on_box_filter_changed)

        self.bind("<Control-n>", lambda _: self.clear_form())
        self.bind("<Control-s>", lambda _: self.save_item())
        self.bind("<Control-f>", lambda _: self.search_var.set(""))
        self.bind("<Control-e>", lambda _: self.export_visible_items())
        self.bind("<Escape>", lambda _: self.clear_form())

        self.name_entry.bind("<Return>", lambda _: self.save_item())
        self.box_entry.bind("<Return>", lambda _: self.save_item())
        self.quantity_entry.bind("<Return>", lambda _: self.save_item())

    def refresh_display(self) -> None:
        """Refresh treeview display with filtering and sorting."""
        self.tree.delete(*self.tree.get_children())

        items = self._get_visible_items()
        self.visible_items = items
        self.visible_item_map = {item["id"]: item for item in items}

        for item in items:
            self.tree.insert(
                "",
                "end",
                values=(
                    item["id"],
                    item["name"],
                    item["box"],
                    item["quantity"],
                    item["updated_at"],
                ),
            )

        self._sync_selection_with_visible_items()
        self._update_result_status(
            len(items),
            sum(item["quantity"] for item in items),
            self.search_var.get().strip(),
            self.box_filter_var.get(),
        )

    def clear_form(self) -> None:
        """Clear input form."""
        self.current_item_id = None
        self.name_var.set("")
        self.box_var.set("")
        self.quantity_var.set(str(AppConfig.DEFAULT_QUANTITY))
        self._set_notes_input("")
        self._set_notes_preview("")
        self.name_entry.focus()
        self.tree.selection_remove(*self.tree.selection())
        self._set_status("Formulario listo para un nuevo artículo.")

    def validate_input(self) -> bool:
        """Validate form input."""
        name = self.name_var.get().strip()
        box = self.box_var.get().strip()

        if not name:
            messagebox.showerror("Error", "El nombre del artículo no puede estar vacío")
            self.name_entry.focus()
            return False

        if not box:
            messagebox.showerror("Error", "La ubicación no puede estar vacía")
            self.box_entry.focus()
            return False

        return True

    def save_item(self) -> None:
        """Save or update item."""
        if not self.validate_input():
            return

        try:
            name = self.name_var.get().strip()
            box = self.box_var.get().strip()
            quantity = self.quantity_var.get().strip()
            notes = self._get_notes_input()

            if self.current_item_id:
                status = self.inventory.update_item_status(
                    self.current_item_id, name, box, quantity, notes
                )
                if status == "updated":
                    messagebox.showinfo("Éxito", "Artículo actualizado correctamente")
                    self.refresh_box_list()
                    self.refresh_display()
                    self.clear_form()
                elif status == "duplicate":
                    messagebox.showerror(
                        "Error",
                        "Ya existe un artículo con ese nombre en la misma ubicación.",
                    )
                elif status == "not_found":
                    self.clear_form()
                    self.refresh_display()
                    messagebox.showerror(
                        "Error",
                        "El artículo seleccionado ya no existe. Se limpió la selección actual.",
                    )
                else:
                    messagebox.showerror(
                        "Error",
                        "Ocurrió un problema inesperado al actualizar el artículo.",
                    )
            else:
                status = self.inventory.add_item_status(name, box, quantity, notes)
                if status == "created":
                    messagebox.showinfo("Éxito", "Artículo agregado correctamente")
                    self.refresh_box_list()
                    self.refresh_display()
                    self.clear_form()
                elif status == "duplicate":
                    messagebox.showerror(
                        "Error",
                        "Ese artículo ya existe en la ubicación seleccionada.",
                    )
                else:
                    messagebox.showerror(
                        "Error",
                        "Ocurrió un problema inesperado al agregar el artículo.",
                    )

        except ValueError as exc:
            messagebox.showerror("Error", str(exc))

    def delete_item(self) -> None:
        """Delete one or more selected items."""
        selected_item_ids = self._get_selected_item_ids()
        if not selected_item_ids:
            messagebox.showwarning(
                "Advertencia", "Por favor seleccione al menos un artículo para eliminar"
            )
            return

        selection_count = len(selected_item_ids)
        confirm_message = (
            "¿Está seguro de que desea eliminar este artículo?"
            if selection_count == 1
            else f"¿Está seguro de que desea eliminar estos {selection_count} artículos?"
        )
        if not messagebox.askyesno("Confirmar", confirm_message):
            return

        deleted_count = 0
        missing_count = 0
        error_count = 0
        for item_id in selected_item_ids:
            status = self.inventory.delete_item_status(item_id)
            if status == "deleted":
                deleted_count += 1
            elif status == "not_found":
                missing_count += 1
            else:
                error_count += 1

        if deleted_count:
            self.clear_form()
            self.refresh_box_list()
            self.refresh_display()

        if deleted_count == selection_count:
            success_message = (
                "Artículo eliminado correctamente"
                if deleted_count == 1
                else f"Se eliminaron correctamente {deleted_count} artículos."
            )
            messagebox.showinfo("Éxito", success_message)
        elif deleted_count and not error_count:
            messagebox.showwarning(
                "Advertencia",
                f"Se eliminaron {deleted_count} artículo(s), pero {missing_count} ya no existían.",
            )
        elif deleted_count:
            messagebox.showwarning(
                "Advertencia",
                f"Se eliminaron {deleted_count} artículo(s), "
                f"{missing_count} ya no existían y {error_count} no pudieron eliminarse.",
            )
        elif missing_count and not error_count:
            self.clear_form()
            self.refresh_display()
            messagebox.showerror(
                "Error",
                "Los artículos seleccionados ya no existen. Se limpió la selección actual.",
            )
        else:
            messagebox.showerror(
                "Error",
                "Ocurrió un problema inesperado al eliminar los artículos seleccionados.",
            )

    def update_item_date(self) -> None:
        """Update the selected item's timestamp."""
        if not self.current_item_id:
            messagebox.showwarning(
                "Advertencia", "Por favor seleccione un artículo para actualizar su fecha"
            )
            return

        status = self.inventory.touch_item_status(self.current_item_id)
        if status == "updated":
            messagebox.showinfo("Éxito", "Fecha actualizada correctamente")
            self.refresh_display()
        elif status == "not_found":
            self.clear_form()
            self.refresh_display()
            messagebox.showerror(
                "Error",
                "El artículo seleccionado ya no existe. Se limpió la selección actual.",
            )
        else:
            messagebox.showerror(
                "Error",
                "Ocurrió un problema inesperado al actualizar la fecha del artículo.",
            )

    def on_item_select(self, _event) -> None:
        """Handle item selection."""
        selection = self.tree.selection()
        if not selection:
            return

        if len(selection) > 1:
            self.current_item_id = None
            self.name_var.set("")
            self.box_var.set("")
            self.quantity_var.set(str(AppConfig.DEFAULT_QUANTITY))
            self._set_notes_input("")
            self._set_notes_preview("")
            self._set_status(f"{len(selection)} artículo(s) seleccionados.")
            return

        item = self.tree.item(selection[0])
        values = item["values"]

        self.current_item_id = values[0]
        self.name_var.set(values[1])
        self.box_var.set(values[2])
        self.quantity_var.set(str(values[3]))
        notes = self.visible_item_map.get(self.current_item_id, {}).get("notes", "")
        self._set_notes_input(notes)
        self._set_notes_preview(notes)

    def on_box_filter_changed(self, _event=None) -> None:
        """Handle box filter selection."""
        self.refresh_display()

    def view_selected_box_contents(self) -> None:
        """Focus the list view on the currently selected box filter."""
        selected_box = self.box_filter_var.get()
        if not selected_box or selected_box == "Todas":
            messagebox.showwarning(
                "Advertencia",
                "Seleccione una ubicación específica para ver su contenido.",
            )
            return

        self.refresh_display()
        self.tree.focus_set()
        self._set_status(f"Viendo el contenido de {selected_box}.")

    def on_search_changed(self, *_args) -> None:
        """Handle search input with debouncing."""
        if self.search_after_id:
            self.after_cancel(self.search_after_id)
            self.search_after_id = None

        self.search_after_id = self.after(
            AppConfig.SEARCH_DEBOUNCE_MS, self._run_debounced_search
        )

    def _run_debounced_search(self) -> None:
        """Execute debounced search callback safely."""
        self.search_after_id = None
        self.refresh_display()

    def refresh_box_list(self) -> None:
        """Update the box filter combobox and box entry combobox."""
        boxes = self.inventory.get_unique_boxes()
        self.box_filter_combo["values"] = boxes

        filter_value = self.box_filter_var.get()
        if filter_value not in boxes:
            default_filter = "Todas" if "Todas" in boxes else (boxes[0] if boxes else "")
            self.box_filter_var.set(default_filter)

        entry_values = [box for box in boxes if box != "Todas"]
        self.box_entry["values"] = entry_values

        current_entry = self.box_var.get()
        if current_entry and current_entry not in entry_values:
            self.box_var.set("")

    def _set_status(self, message: str) -> None:
        """Update the lightweight UI status message."""
        self.status_var.set(message)

    def _set_summary(self, item_count: int, total_quantity: int, selected_box: str) -> None:
        """Update the box/content summary line."""
        if selected_box and selected_box != "Todas":
            self.summary_var.set(
                f"Resumen de {selected_box}: {item_count} artículo(s), cantidad total {total_quantity}."
            )
        else:
            self.summary_var.set(
                f"Resumen: {item_count} artículo(s) visibles, cantidad total {total_quantity}."
            )

    def _set_notes_preview(self, notes: str) -> None:
        """Render read-only notes for the selected item."""
        self.notes_preview.configure(state="normal")
        self.notes_preview.delete("1.0", tk.END)
        self.notes_preview.insert("1.0", notes or "Sin notas para este artículo.")
        self.notes_preview.configure(state="disabled")

    def _set_notes_input(self, notes: str) -> None:
        """Update the editable notes field."""
        self.notes_text.delete("1.0", tk.END)
        self.notes_text.insert("1.0", notes)

    def _get_notes_input(self) -> str:
        """Return the current editable notes text."""
        return self.notes_text.get("1.0", tk.END).strip()

    def _get_visible_items(self) -> list[dict]:
        """Resolve the current list of visible items from search, sort, and box filter state."""
        query = self.search_var.get().strip()
        sort_column = self.tree.sort_column
        sort_descending = self.tree.sort_descending

        items = (
            self.inventory.search_items(query, sort_column, sort_descending)
            if query
            else self.inventory.get_all_items(sort_column, sort_descending)
        )

        selected_box = self.box_filter_var.get()
        if selected_box and selected_box != "Todas":
            items = [item for item in items if item["box"] == selected_box]
        return items

    def _sync_selection_with_visible_items(self) -> None:
        """Clear stale selection state when the selected item is no longer visible."""
        visible_ids = {
            self.tree.item(item_id)["values"][0]
            for item_id in self.tree.get_children()
            if self.tree.item(item_id)["values"]
        }

        if self.current_item_id is None:
            return

        if self.current_item_id not in visible_ids:
            self.current_item_id = None
            self.name_var.set("")
            self.box_var.set("")
            self.quantity_var.set(str(AppConfig.DEFAULT_QUANTITY))
            self._set_notes_input("")
            self._set_notes_preview("")
            self.tree.selection_remove(*self.tree.selection())

    def _get_selected_item_ids(self) -> list[int]:
        """Return the inventory item ids represented by the current tree selection."""
        item_ids = []
        for selection_id in self.tree.selection():
            values = self.tree.item(selection_id).get("values", [])
            if values:
                item_ids.append(values[0])
        return item_ids

    def _update_result_status(
        self,
        item_count: int,
        total_quantity: int,
        query: str,
        selected_box: str,
    ) -> None:
        """Reflect the visible search/filter state to the user."""
        self._set_summary(item_count, total_quantity, selected_box)

        if item_count == 0:
            if query or (selected_box and selected_box != "Todas"):
                self._set_status("No hay resultados para la búsqueda o filtro actual.")
            else:
                self._set_status("No hay artículos registrados.")
            return

        if query and selected_box and selected_box != "Todas":
            self._set_status(
                f"Mostrando {item_count} resultado(s) para '{query}' en {selected_box} (cantidad total {total_quantity})."
            )
        elif query:
            self._set_status(
                f"Mostrando {item_count} resultado(s) para '{query}' (cantidad total {total_quantity})."
            )
        elif selected_box and selected_box != "Todas":
            self._set_status(
                f"Mostrando {item_count} artículo(s) en {selected_box} (cantidad total {total_quantity})."
            )
        else:
            self._set_status(
                f"Mostrando {item_count} artículo(s) (cantidad total {total_quantity})."
            )

    def export_visible_items(self) -> None:
        """Export the currently visible items to a CSV file."""
        if not self.visible_items:
            messagebox.showwarning(
                "Advertencia",
                "No hay resultados visibles para exportar.",
            )
            return

        filename = filedialog.asksaveasfilename(
            title="Exportar resultados",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
            initialfile="inventario_exportado.csv",
        )
        if not filename:
            return

        with open(filename, "w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["id", "name", "box", "quantity", "notes", "updated_at"])
            for item in self.visible_items:
                writer.writerow(
                    [
                        item["id"],
                        item["name"],
                        item["box"],
                        item["quantity"],
                        item["notes"],
                        item["updated_at"],
                    ]
                )

        messagebox.showinfo(
            "Éxito",
            f"Se exportaron {len(self.visible_items)} artículo(s) a {filename}.",
        )

    def on_closing(self) -> None:
        """Handle application closing."""
        if messagebox.askokcancel("Salir", "¿Está seguro de que desea salir?"):
            if self.search_after_id:
                self.after_cancel(self.search_after_id)
                self.search_after_id = None
            self.db.close_all()
            self.quit()
