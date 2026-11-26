import logging
import sys
import tkinter as tk
from tkinter import messagebox

from inventory_app import AppConfig
from inventory_app.ui.app import InventoryApp


def _show_startup_error(message: str) -> None:
    """Best-effort fatal error reporting that works without a live app window."""
    try:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Error Fatal", message, parent=root)
        root.destroy()
    except tk.TclError:
        print(message, file=sys.stderr)


def main() -> None:
    logging.basicConfig(
        filename=AppConfig.LOG_PATH,
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    try:
        app = InventoryApp()
        app.mainloop()
    except Exception as exc:  # pylint: disable=broad-except
        logging.critical("Application failed to start: %s", exc, exc_info=True)
        _show_startup_error(
            "La aplicación no pudo iniciarse. Por favor, revise los logs para más detalles."
        )
        raise


if __name__ == "__main__":
    main()
