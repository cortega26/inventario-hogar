from tkinter import ttk


class SortableTreeview(ttk.Treeview):
    """Extended Treeview with sorting capability."""

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self._sort_column = None
        self._sort_descending = False

        for col in self["columns"]:
            self.heading(
                col,
                text=self.heading(col)["text"],
                command=lambda c=col: self.toggle_sort(c),
            )

    def toggle_sort(self, column: str) -> None:
        """Toggle sort order and update heading text."""
        if self._sort_column == column:
            self._sort_descending = not self._sort_descending
        else:
            self._sort_column = column
            self._sort_descending = False

        for col in self["columns"]:
            text = self.heading(col)["text"].rstrip(" ↑↓")
            if col == self._sort_column:
                text += " ↓" if self._sort_descending else " ↑"
            self.heading(col, text=text)

        self.event_generate("<<SortChanged>>")

    @property
    def sort_column(self):
        return self._sort_column

    @property
    def sort_descending(self):
        return self._sort_descending

