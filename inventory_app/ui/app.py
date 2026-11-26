import csv
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from ..cache import Cache
from ..config import AppConfig
from ..db import Database
from ..manager import InventoryManager
from .formatting import format_date
from .theme import (
    ACCENT,
    BORDER,
    HEADER,
    INK,
    MUTED,
    SURFACE,
    SURFACE_ALT,
    apply_theme,
)
from .treeview import SortableTreeview


class InventoryApp(tk.Tk):
    """Inventory management desktop application."""

    SEARCH_PLACEHOLDER = "Buscar por nombre, nota o ubicación..."

    def __init__(self) -> None:
        super().__init__()

        self.db = Database()
        self.cache = Cache()
        self.inventory = InventoryManager(self.db, self.cache)

        self.search_after_id: Optional[str] = None
        self.current_item_id: Optional[int] = None
        self.visible_items: list[dict] = []
        self.visible_item_map: dict[int, dict] = {}
        self._search_placeholder_active = False
        self.font_family = "DejaVu Sans"

        self.setup_window()
        self.create_styles()
        self.create_widgets()
        self.setup_bindings()

        self.refresh_box_list()
        self.refresh_display()
        self.name_entry.focus_set()

    # ------------------------------------------------------------------
    # Window and theme
    # ------------------------------------------------------------------
    def setup_window(self) -> None:
        """Configure the main window."""
        self.title("Inventario Hogar")
        self.geometry(AppConfig.WINDOW_SIZE)
        self.minsize(*AppConfig.MIN_WINDOW_SIZE)
        self.configure(bg=SURFACE_ALT)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self._set_window_icon()

    def _set_window_icon(self) -> None:
        icon_path = Path(__file__).resolve().parent.parent / "assets" / "icon.png"
        if not icon_path.exists():
            return
        try:
            self._window_icon = tk.PhotoImage(file=str(icon_path))
            self.iconphoto(True, self._window_icon)
        except tk.TclError:
            pass

    def create_styles(self) -> None:
        """Apply the visual theme and remember the resolved font family."""
        self.font_family = apply_theme(self)
        self.style = ttk.Style(self)

    # ------------------------------------------------------------------
    # Widget construction
    # ------------------------------------------------------------------
    def create_widgets(self) -> None:
        """Create and arrange the application widgets."""
        self._build_header()
        self._build_metrics()
        self._build_content()
        self._build_status_bar()

        self._setup_search_placeholder()
        self._set_editor_mode(None)

    def _build_header(self) -> None:
        header = ttk.Frame(self, style="Header.TFrame", padding=(20, 14))
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(1, weight=1)

        logo = tk.Canvas(
            header,
            width=42,
            height=42,
            bg=HEADER,
            highlightthickness=0,
            bd=0,
        )
        logo.grid(row=0, column=0, rowspan=2, padx=(0, 14), sticky="w")
        logo.create_rectangle(0, 0, 42, 42, fill=ACCENT, outline="")
        logo.create_rectangle(10, 13, 32, 30, outline="#FFFFFF", width=2)
        logo.create_line(10, 19, 32, 19, fill="#FFFFFF", width=2)
        logo.create_line(21, 13, 21, 30, fill="#FFFFFF", width=2)

        ttk.Label(
            header, text="Inventario Hogar", style="HeaderTitle.TLabel"
        ).grid(row=0, column=1, sticky="sw")
        ttk.Label(
            header,
            text="Control de artículos y ubicaciones",
            style="HeaderSub.TLabel",
        ).grid(row=1, column=1, sticky="nw", pady=(2, 0))

        actions = ttk.Frame(header, style="Header.TFrame")
        actions.grid(row=0, column=2, rowspan=2, sticky="e")

        ttk.Button(
            actions,
            text="Exportar",
            style="HeaderGhost.TButton",
            command=self.export_visible_items,
        ).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(
            actions,
            text="+  Nuevo artículo",
            style="Accent.TButton",
            command=self.clear_form,
        ).pack(side=tk.LEFT)

    def _build_metrics(self) -> None:
        wrap = ttk.Frame(self, style="TFrame")
        wrap.grid(row=1, column=0, sticky="ew", padx=16, pady=(14, 6))
        for column in range(3):
            wrap.grid_columnconfigure(column, weight=1, uniform="metric")

        self.metric_vars: dict[str, tk.StringVar] = {}
        specs = (
            ("items", "Artículos"),
            ("units", "Unidades"),
            ("boxes", "Ubicaciones"),
        )

        for column, (key, label) in enumerate(specs):
            if column == 0:
                padx = (0, 6)
            elif column == 2:
                padx = (6, 0)
            else:
                padx = (6, 6)

            card = tk.Frame(
                wrap,
                bg=SURFACE,
                bd=0,
                highlightbackground=BORDER,
                highlightcolor=BORDER,
                highlightthickness=1,
            )
            card.grid(row=0, column=column, sticky="ew", padx=padx)

            inner = ttk.Frame(card, style="Surface.TFrame", padding=(16, 12))
            inner.pack(fill=tk.BOTH, expand=True)

            value_var = tk.StringVar(value="0")
            ttk.Label(
                inner, textvariable=value_var, style="MetricValue.TLabel"
            ).pack(anchor="w")
            ttk.Label(inner, text=label, style="MetricLabel.TLabel").pack(
                anchor="w", pady=(2, 0)
            )
            self.metric_vars[key] = value_var

    def _build_content(self) -> None:
        content = ttk.Frame(self, style="TFrame")
        content.grid(row=2, column=0, sticky="nsew", padx=16, pady=(6, 4))
        content.grid_columnconfigure(0, weight=1, minsize=520)
        content.grid_columnconfigure(1, weight=0, minsize=340)
        content.grid_rowconfigure(0, weight=1)

        table_card = self._make_card(content)
        table_card.grid(row=0, column=0, sticky="nsew", padx=(0, 12))

        editor_card = self._make_card(content)
        editor_card.grid(row=0, column=1, sticky="nsew")

        self._build_table_card(table_card)
        self._build_editor_card(editor_card)

    @staticmethod
    def _make_card(parent: tk.Misc) -> tk.Frame:
        return tk.Frame(
            parent,
            bg=SURFACE,
            bd=0,
            highlightbackground=BORDER,
            highlightcolor=BORDER,
            highlightthickness=1,
        )

    def _build_table_card(self, card: tk.Frame) -> None:
        inner = ttk.Frame(card, style="Surface.TFrame", padding=(16, 14, 12, 12))
        inner.pack(fill=tk.BOTH, expand=True)
        inner.grid_columnconfigure(0, weight=1)
        inner.grid_rowconfigure(1, weight=1)

        toolbar = ttk.Frame(inner, style="Surface.TFrame")
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        toolbar.grid_columnconfigure(0, weight=1)

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self.on_search_changed)
        self.search_entry = ttk.Entry(
            toolbar, textvariable=self.search_var, style="Placeholder.TEntry"
        )
        self.search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 12))

        filter_frame = ttk.Frame(toolbar, style="Surface.TFrame")
        filter_frame.grid(row=0, column=1, sticky="e")

        ttk.Label(
            filter_frame, text="Ubicación", style="SurfaceMuted.TLabel"
        ).pack(side=tk.LEFT, padx=(0, 8))

        self.box_filter_var = tk.StringVar(value="Todas")
        self.box_filter_combo = ttk.Combobox(
            filter_frame,
            textvariable=self.box_filter_var,
            width=20,
            state="readonly",
        )
        self.box_filter_combo.pack(side=tk.LEFT)

        tree_wrap = ttk.Frame(inner, style="Surface.TFrame")
        tree_wrap.grid(row=1, column=0, sticky="nsew")
        tree_wrap.grid_columnconfigure(0, weight=1)
        tree_wrap.grid_rowconfigure(0, weight=1)

        columns = ("name", "box", "quantity", "updated")
        self.tree = SortableTreeview(
            tree_wrap,
            columns=columns,
            show="headings",
            height=AppConfig.ROWS_PER_PAGE,
            selectmode="extended",
        )

        column_configs = {
            "name": ("Artículo", AppConfig.COLUMN_WIDTH_NAME, tk.W, True),
            "box": ("Ubicación", AppConfig.COLUMN_WIDTH_BOX, tk.W, False),
            "quantity": (
                "Cantidad",
                AppConfig.COLUMN_WIDTH_QUANTITY,
                tk.CENTER,
                False,
            ),
            "updated": (
                "Actualizado",
                AppConfig.COLUMN_WIDTH_UPDATED,
                tk.CENTER,
                False,
            ),
        }

        for column, (heading, width, anchor, stretch) in column_configs.items():
            self.tree.heading(column, text=heading, anchor=anchor)
            self.tree.column(
                column,
                width=width,
                minwidth=70,
                anchor=anchor,
                stretch=stretch,
            )

        self.tree.tag_configure("even", background=SURFACE)
        self.tree.tag_configure("odd", background=SURFACE_ALT)

        scrollbar = ttk.Scrollbar(
            tree_wrap,
            orient=tk.VERTICAL,
            command=self.tree.yview,
            style="Modern.Vertical.TScrollbar",
        )
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns", padx=(6, 0))

        self.empty_state = tk.Frame(tree_wrap, bg=SURFACE)
        tk.Label(
            self.empty_state,
            text="Sin artículos para mostrar",
            bg=SURFACE,
            fg=INK,
            font=(self.font_family, AppConfig.FONT_LARGE, "bold"),
        ).pack()
        tk.Label(
            self.empty_state,
            text="Prueba con otra búsqueda o agrega tu primer artículo.",
            bg=SURFACE,
            fg=MUTED,
            font=(self.font_family, AppConfig.FONT_SMALL),
        ).pack(pady=(4, 0))

        self.summary_var = tk.StringVar(value="0 artículos · 0 unidades")
        ttk.Label(
            inner, textvariable=self.summary_var, style="SurfaceMuted.TLabel"
        ).grid(row=2, column=0, sticky="w", pady=(10, 0))

    def _build_editor_card(self, card: tk.Frame) -> None:
        inner = ttk.Frame(card, style="Surface.TFrame", padding=(16, 14, 16, 14))
        inner.pack(fill=tk.BOTH, expand=True)
        inner.grid_columnconfigure(0, weight=1)
        inner.grid_rowconfigure(8, weight=1)

        self.editor_title_var = tk.StringVar(value="Nuevo artículo")
        self.editor_meta_var = tk.StringVar(value="Completa los datos para agregarlo")

        ttk.Label(
            inner, textvariable=self.editor_title_var, style="CardTitle.TLabel"
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            inner,
            textvariable=self.editor_meta_var,
            style="SurfaceMuted.TLabel",
            wraplength=300,
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(2, 12))

        ttk.Label(inner, text="Nombre", style="SurfaceMuted.TLabel").grid(
            row=2, column=0, sticky="w"
        )
        self.name_var = tk.StringVar()
        self.name_entry = ttk.Entry(inner, textvariable=self.name_var)
        self.name_entry.grid(row=3, column=0, sticky="ew", pady=(4, 10))

        ttk.Label(inner, text="Ubicación", style="SurfaceMuted.TLabel").grid(
            row=4, column=0, sticky="w"
        )
        self.box_var = tk.StringVar()
        self.box_entry = ttk.Combobox(inner, textvariable=self.box_var, width=30)
        self.box_entry.grid(row=5, column=0, sticky="ew", pady=(4, 10))

        quantity_row = ttk.Frame(inner, style="Surface.TFrame")
        quantity_row.grid(row=6, column=0, sticky="ew", pady=(0, 10))
        ttk.Label(
            quantity_row, text="Cantidad", style="SurfaceMuted.TLabel"
        ).pack(side=tk.LEFT)

        self.quantity_var = tk.StringVar(value=str(AppConfig.DEFAULT_QUANTITY))
        self.quantity_entry = ttk.Spinbox(
            quantity_row,
            from_=1,
            to=9999,
            textvariable=self.quantity_var,
            width=8,
            style="TSpinbox",
        )
        self.quantity_entry.pack(side=tk.LEFT, padx=(12, 0))

        ttk.Label(inner, text="Notas", style="SurfaceMuted.TLabel").grid(
            row=7, column=0, sticky="w"
        )

        self.notes_text = tk.Text(
            inner,
            width=30,
            height=6,
            wrap="word",
            bd=0,
            bg=SURFACE_ALT,
            fg=INK,
            insertbackground=INK,
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=ACCENT,
            font=(self.font_family, AppConfig.FONT_NORMAL),
            padx=8,
            pady=8,
        )
        self.notes_text.grid(row=8, column=0, sticky="nsew", pady=(4, 6))

        self.error_var = tk.StringVar()
        ttk.Label(
            inner,
            textvariable=self.error_var,
            style="Error.TLabel",
            wraplength=300,
            justify="left",
        ).grid(row=9, column=0, sticky="w")

        self.save_button = ttk.Button(
            inner,
            text="Guardar artículo",
            style="Accent.TButton",
            command=self.save_item,
        )
        self.save_button.grid(row=10, column=0, sticky="ew", pady=(10, 8))

        secondary = ttk.Frame(inner, style="Surface.TFrame")
        secondary.grid(row=11, column=0, sticky="ew")
        secondary.grid_columnconfigure(0, weight=1)
        secondary.grid_columnconfigure(1, weight=1)

        ttk.Button(
            secondary,
            text="Cancelar",
            style="Ghost.TButton",
            command=self.clear_form,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 4))

        self.delete_button = ttk.Button(
            secondary,
            text="Eliminar",
            style="Danger.TButton",
            command=self.delete_item,
        )
        self.delete_button.grid(row=0, column=1, sticky="ew", padx=(4, 0))
        self.delete_button.state(["disabled"])

    def _build_status_bar(self) -> None:
        bar = ttk.Frame(self, style="TFrame")
        bar.grid(row=3, column=0, sticky="ew", padx=20, pady=(2, 10))
        bar.grid_columnconfigure(0, weight=1)

        self.status_var = tk.StringVar(value="Listo")
        ttk.Label(
            bar, textvariable=self.status_var, style="Status.TLabel"
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            bar,
            text="Ctrl+N nuevo  ·  Ctrl+F buscar  ·  Supr eliminar",
            style="Status.TLabel",
        ).grid(row=0, column=1, sticky="e")

    # ------------------------------------------------------------------
    # Bindings and placeholder handling
    # ------------------------------------------------------------------
    def setup_bindings(self) -> None:
        """Set up event bindings."""
        self.tree.bind("<<TreeviewSelect>>", self.on_item_select)
        self.tree.bind("<Double-1>", self._on_row_double_click)
        self.tree.bind("<Delete>", lambda _event: self.delete_item())
        self.tree.bind("<<SortChanged>>", lambda _event: self.refresh_display())
        self.box_filter_combo.bind("<<ComboboxSelected>>", self.on_box_filter_changed)

        self.search_entry.bind("<FocusIn>", self._hide_search_placeholder)
        self.search_entry.bind("<FocusOut>", self._restore_search_placeholder)

        self.bind("<Control-n>", lambda _event: self.clear_form())
        self.bind("<Control-s>", lambda _event: self.save_item())
        self.bind("<Control-f>", self._focus_search)
        self.bind("<Control-e>", lambda _event: self.export_visible_items())
        self.bind("<Escape>", lambda _event: self.clear_form())

        self.name_entry.bind("<Return>", lambda _event: self.save_item())
        self.box_entry.bind("<Return>", lambda _event: self.save_item())
        self.quantity_entry.bind("<Return>", lambda _event: self.save_item())

    def _setup_search_placeholder(self) -> None:
        self._show_search_placeholder()

    def _show_search_placeholder(self) -> None:
        self._search_placeholder_active = True
        self.search_var.set(self.SEARCH_PLACEHOLDER)
        self.search_entry.configure(style="Placeholder.TEntry")

    def _hide_search_placeholder(self, _event=None) -> None:
        if not self._search_placeholder_active:
            return
        self._search_placeholder_active = False
        self.search_var.set("")
        self.search_entry.configure(style="TEntry")

    def _restore_search_placeholder(self, _event=None) -> None:
        if not self.search_var.get().strip():
            self._show_search_placeholder()

    def _focus_search(self, _event=None) -> None:
        self._hide_search_placeholder()
        self.search_entry.focus_set()
        self.search_entry.selection_range(0, tk.END)

    def _on_row_double_click(self, _event=None) -> None:
        self.name_entry.focus_set()

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------
    def refresh_display(self) -> None:
        """Refresh the treeview with the current filters and sorting."""
        self.tree.delete(*self.tree.get_children())

        items = self._get_visible_items()
        self.visible_items = items
        self.visible_item_map = {item["id"]: item for item in items}

        for index, item in enumerate(items):
            tags = ("odd",) if index % 2 else ("even",)
            self.tree.insert(
                "",
                "end",
                iid=str(item["id"]),
                values=(
                    item["name"],
                    item["box"],
                    item["quantity"],
                    format_date(item["updated_at"]),
                ),
                tags=tags,
            )

        self._sync_selection_with_visible_items()
        self._update_result_status(
            len(items),
            sum(item["quantity"] for item in items),
            self._active_search_query(),
            self.box_filter_var.get(),
        )
        self._toggle_empty_state(not items)

    def _toggle_empty_state(self, visible: bool) -> None:
        empty_state = self.__dict__.get("empty_state")
        if empty_state is None:
            return
        if visible:
            empty_state.place(relx=0.5, rely=0.45, anchor="center")
            empty_state.lift()
        else:
            empty_state.place_forget()

    def clear_form(self) -> None:
        """Reset the editor for a new item."""
        self.current_item_id = None
        self.name_var.set("")
        self.box_var.set("")
        self.quantity_var.set(str(AppConfig.DEFAULT_QUANTITY))
        self._set_notes_input("")
        self._clear_error()
        self._set_editor_mode(None)
        self.name_entry.focus_set()
        self.tree.selection_remove(*self.tree.selection())
        self._set_status("Formulario listo para un nuevo artículo.")

    def validate_input(self) -> bool:
        """Validate the form and show the first problem inline."""
        name = self.name_var.get().strip()
        box = self.box_var.get().strip()

        if not name:
            self._set_error("El nombre del artículo no puede estar vacío.")
            self.name_entry.focus_set()
            return False

        if not box:
            self._set_error("La ubicación no puede estar vacía.")
            self.box_entry.focus_set()
            return False

        return True

    def save_item(self) -> None:
        """Create or update the item currently in the editor."""
        self._clear_error()
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
                    self.refresh_box_list()
                    self.refresh_display()
                    self.clear_form()
                    self._set_status("Artículo actualizado correctamente.")
                elif status == "duplicate":
                    self._set_error(
                        "Ya existe un artículo con ese nombre en la misma ubicación."
                    )
                elif status == "not_found":
                    self.clear_form()
                    self.refresh_display()
                    self._set_status(
                        "El artículo seleccionado ya no existe. Se limpió la selección."
                    )
                else:
                    self._set_error(
                        "Ocurrió un problema inesperado al actualizar el artículo."
                    )
            else:
                status = self.inventory.add_item_status(name, box, quantity, notes)
                if status == "created":
                    self.refresh_box_list()
                    self.refresh_display()
                    self.clear_form()
                    self._set_status("Artículo agregado correctamente.")
                elif status == "duplicate":
                    self._set_error(
                        "Ese artículo ya existe en la ubicación seleccionada."
                    )
                else:
                    self._set_error(
                        "Ocurrió un problema inesperado al agregar el artículo."
                    )

        except ValueError as exc:
            self._set_error(str(exc))

    def delete_item(self) -> None:
        """Delete one or more selected items."""
        selected_item_ids = self._get_selected_item_ids()
        if not selected_item_ids:
            self._set_status("Selecciona al menos un artículo para eliminar.")
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
            self.refresh_box_list()
            self.refresh_display()
            self.clear_form()

        if deleted_count == selection_count:
            message = (
                "Artículo eliminado correctamente."
                if deleted_count == 1
                else f"Se eliminaron {deleted_count} artículos."
            )
            self._set_status(message)
        elif deleted_count and not error_count:
            self._set_status(
                f"Se eliminaron {deleted_count}; {missing_count} ya no existían."
            )
        elif deleted_count:
            self._set_status(
                f"Se eliminaron {deleted_count}; {missing_count} ya no existían y "
                f"{error_count} no se pudieron eliminar."
            )
        elif missing_count and not error_count:
            self.clear_form()
            self.refresh_display()
            self._set_status("Los artículos seleccionados ya no existen.")
        else:
            self._set_status(
                "Ocurrió un problema inesperado al eliminar los artículos."
            )

    # ------------------------------------------------------------------
    # Selection and data flow
    # ------------------------------------------------------------------
    def on_item_select(self, _event=None) -> None:
        """Populate the editor with the selected row."""
        selection = self.tree.selection()
        if not selection:
            return

        if len(selection) > 1:
            self.current_item_id = None
            self.name_var.set("")
            self.box_var.set("")
            self.quantity_var.set(str(AppConfig.DEFAULT_QUANTITY))
            self._set_notes_input("")
            self._clear_error()
            self._set_editor_mode(None, selection_count=len(selection))
            self._set_status(f"{len(selection)} artículos seleccionados.")
            return

        try:
            item_id = int(selection[0])
        except (TypeError, ValueError):
            return

        item = self.visible_item_map.get(item_id)
        if item is None:
            return

        self.current_item_id = item_id
        self.name_var.set(item["name"])
        self.box_var.set(item["box"])
        self.quantity_var.set(str(item["quantity"]))
        self._set_notes_input(item.get("notes", ""))
        self._clear_error()
        self._set_editor_mode(item)

    def on_box_filter_changed(self, _event=None) -> None:
        """Re-render when the location filter changes."""
        self.refresh_display()

    def on_search_changed(self, *_args) -> None:
        """Debounce search input."""
        if self.__dict__.get("_search_placeholder_active", False):
            return

        if self.search_after_id:
            self.after_cancel(self.search_after_id)
            self.search_after_id = None

        self.search_after_id = self.after(
            AppConfig.SEARCH_DEBOUNCE_MS, self._run_debounced_search
        )

    def _run_debounced_search(self) -> None:
        self.search_after_id = None
        self.refresh_display()

    def refresh_box_list(self) -> None:
        """Sync the location filter and editor suggestions."""
        boxes = self.inventory.get_unique_boxes()
        self.box_filter_combo["values"] = boxes

        filter_value = self.box_filter_var.get()
        if filter_value not in boxes:
            self.box_filter_var.set("Todas" if "Todas" in boxes else "")

        entry_values = [box for box in boxes if box != "Todas"]
        self.box_entry["values"] = entry_values

        current_entry = self.box_var.get()
        if current_entry and current_entry not in entry_values:
            self.box_var.set("")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _active_search_query(self) -> str:
        if self.__dict__.get("_search_placeholder_active", False):
            return ""
        return self.search_var.get().strip()

    def _set_status(self, message: str) -> None:
        self.status_var.set(message)

    def _set_error(self, message: str) -> None:
        error_var = self.__dict__.get("error_var")
        if error_var is not None:
            error_var.set(message)

    def _clear_error(self) -> None:
        self._set_error("")

    def _set_editor_mode(
        self, item: Optional[dict], selection_count: int = 0
    ) -> None:
        if item is None and not selection_count:
            self.editor_title_var.set("Nuevo artículo")
            self.editor_meta_var.set("Completa los datos para agregarlo")
            self._set_delete_enabled(False)
        elif item is None:
            self.editor_title_var.set("Selección múltiple")
            self.editor_meta_var.set(f"{selection_count} artículos seleccionados")
            self._set_delete_enabled(True)
        else:
            self.editor_title_var.set("Editar artículo")
            meta = f"#{item['id']:04d}"
            updated = format_date(item.get("updated_at", ""))
            if updated != "—":
                meta += f" · Actualizado {updated}"
            self.editor_meta_var.set(meta)
            self._set_delete_enabled(True)

    def _set_delete_enabled(self, enabled: bool) -> None:
        button = self.__dict__.get("delete_button")
        if button is None:
            return
        button.state(["!disabled"] if enabled else ["disabled"])

    @staticmethod
    def _plural(count: int, singular: str, plural: str) -> str:
        return f"{count} {singular if count == 1 else plural}"

    def _set_notes_input(self, notes: str) -> None:
        self.notes_text.delete("1.0", tk.END)
        self.notes_text.insert("1.0", notes)

    def _get_notes_input(self) -> str:
        return self.notes_text.get("1.0", tk.END).strip()

    def _get_visible_items(self) -> list[dict]:
        """Resolve visible items from search, sorting and location filter."""
        query = self._active_search_query()
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
        """Clear stale editor state when the selected item is filtered out."""
        visible_ids = set(self.tree.get_children())

        if self.current_item_id is None:
            return

        if str(self.current_item_id) not in visible_ids:
            self.current_item_id = None
            self.name_var.set("")
            self.box_var.set("")
            self.quantity_var.set(str(AppConfig.DEFAULT_QUANTITY))
            self._set_notes_input("")
            self._clear_error()
            self._set_editor_mode(None)
            self.tree.selection_remove(*self.tree.selection())

    def _get_selected_item_ids(self) -> list[int]:
        item_ids = []
        for selection_id in self.tree.selection():
            try:
                item_ids.append(int(selection_id))
            except (TypeError, ValueError):
                continue
        return item_ids

    def _update_result_status(
        self,
        item_count: int,
        total_quantity: int,
        query: str,
        selected_box: str,
    ) -> None:
        """Update metrics, footer summary and the status line."""
        box_count = len({item["box"] for item in self.visible_items})
        metric_vars = self.__dict__.get("metric_vars")
        if metric_vars is not None:
            metric_vars["items"].set(str(item_count))
            metric_vars["units"].set(str(total_quantity))
            metric_vars["boxes"].set(str(box_count))

        self.summary_var.set(
            f"{self._plural(item_count, 'artículo', 'artículos')} · "
            f"{self._plural(total_quantity, 'unidad', 'unidades')}"
        )

        if item_count == 0:
            if query or (selected_box and selected_box != "Todas"):
                self._set_status("No hay resultados para la búsqueda o filtro actual.")
            else:
                self._set_status("No hay artículos registrados.")
            return

        if query and selected_box and selected_box != "Todas":
            self._set_status(
                f"{self._plural(item_count, 'resultado', 'resultados')} en "
                f"{selected_box} para '{query}'."
            )
        elif query:
            self._set_status(
                f"{self._plural(item_count, 'resultado', 'resultados')} para '{query}'."
            )
        elif selected_box and selected_box != "Todas":
            self._set_status(
                f"Mostrando {self._plural(item_count, 'artículo', 'artículos')} "
                f"en {selected_box}."
            )
        else:
            self._set_status(
                f"Mostrando {self._plural(item_count, 'artículo', 'artículos')}."
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
