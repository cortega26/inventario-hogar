"""Visual design tokens and ttk styles for Inventario Hogar."""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

from ..config import AppConfig

# Palette (slate + teal)
BG = "#F1F5F9"
SURFACE = "#FFFFFF"
SURFACE_ALT = "#F8FAFC"
HEADER = "#0F172A"
INK = "#0F172A"
MUTED = "#64748B"
BORDER = "#E2E8F0"
BORDER_STRONG = "#CBD5E1"
ACCENT = "#0F766E"
ACCENT_HOVER = "#0B5E58"
ACCENT_SOFT = "#CCFBF1"
DANGER = "#B91C1C"
DANGER_SOFT = "#FEE2E2"
DANGER_BORDER = "#FECACA"
HEADER_TEXT = "#F8FAFC"
HEADER_MUTED = "#94A3B8"
HEADER_BORDER = "#475569"
DISABLED = "#94A3B8"

FONT_CANDIDATES = (
    "Inter",
    "Noto Sans",
    "Liberation Sans",
    "DejaVu Sans",
)


def resolve_font(root: tk.Misc) -> str:
    """Pick the first modern font available on this system."""
    available = set(tkfont.families(root))
    for candidate in FONT_CANDIDATES:
        if candidate in available:
            return candidate
    return "DejaVu Sans"


def apply_theme(root: tk.Tk) -> str:
    """Apply the application theme and return the resolved font family."""
    family = resolve_font(root)
    style = ttk.Style(root)
    style.theme_use("clam")

    normal = (family, AppConfig.FONT_NORMAL)
    small = (family, AppConfig.FONT_SMALL)
    bold = (family, AppConfig.FONT_NORMAL, "bold")
    title = (family, AppConfig.FONT_TITLE, "bold")

    # Base surfaces -----------------------------------------------------
    style.configure(".", background=BG, foreground=INK, font=normal)
    style.configure("TFrame", background=BG)
    style.configure("Surface.TFrame", background=SURFACE)
    style.configure("Header.TFrame", background=HEADER)
    style.configure("TLabel", background=BG, foreground=INK)
    style.configure("Surface.TLabel", background=SURFACE, foreground=INK)
    style.configure("Muted.TLabel", background=BG, foreground=MUTED, font=small)
    style.configure(
        "SurfaceMuted.TLabel", background=SURFACE, foreground=MUTED, font=small
    )
    style.configure("CardTitle.TLabel", background=SURFACE, foreground=INK, font=title)
    style.configure(
        "MetricValue.TLabel",
        background=SURFACE,
        foreground=INK,
        font=(family, 22, "bold"),
    )
    style.configure("MetricLabel.TLabel", background=SURFACE, foreground=MUTED, font=small)
    style.configure(
        "HeaderTitle.TLabel", background=HEADER, foreground=HEADER_TEXT, font=title
    )
    style.configure(
        "HeaderSub.TLabel", background=HEADER, foreground=HEADER_MUTED, font=small
    )
    style.configure("Status.TLabel", background=BG, foreground=MUTED, font=small)
    style.configure("Error.TLabel", background=SURFACE, foreground=DANGER, font=small)

    # Inputs ------------------------------------------------------------
    style.configure(
        "TEntry",
        fieldbackground=SURFACE,
        foreground=INK,
        bordercolor=BORDER,
        lightcolor=BORDER,
        darkcolor=BORDER,
        padding=(8, 6),
    )
    style.map(
        "TEntry",
        bordercolor=[("focus", ACCENT)],
        lightcolor=[("focus", ACCENT)],
        darkcolor=[("focus", ACCENT)],
    )
    style.configure(
        "Placeholder.TEntry",
        fieldbackground=SURFACE,
        foreground=MUTED,
        bordercolor=BORDER,
        lightcolor=BORDER,
        darkcolor=BORDER,
        padding=(8, 6),
    )
    style.map(
        "Placeholder.TEntry",
        bordercolor=[("focus", ACCENT)],
        lightcolor=[("focus", ACCENT)],
        darkcolor=[("focus", ACCENT)],
    )
    style.configure(
        "TCombobox",
        fieldbackground=SURFACE,
        background=SURFACE,
        foreground=INK,
        arrowcolor=MUTED,
        bordercolor=BORDER,
        lightcolor=BORDER,
        darkcolor=BORDER,
        padding=(8, 6),
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", SURFACE)],
        foreground=[("readonly", INK)],
        selectbackground=[("readonly", SURFACE)],
        selectforeground=[("readonly", INK)],
        bordercolor=[("focus", ACCENT)],
        lightcolor=[("focus", ACCENT)],
        darkcolor=[("focus", ACCENT)],
    )
    style.configure(
        "TSpinbox",
        fieldbackground=SURFACE,
        foreground=INK,
        arrowcolor=MUTED,
        bordercolor=BORDER,
        lightcolor=BORDER,
        darkcolor=BORDER,
        padding=(8, 6),
    )
    style.map(
        "TSpinbox",
        bordercolor=[("focus", ACCENT)],
        lightcolor=[("focus", ACCENT)],
        darkcolor=[("focus", ACCENT)],
    )

    root.option_add("*TCombobox*Listbox.background", SURFACE)
    root.option_add("*TCombobox*Listbox.foreground", INK)
    root.option_add("*TCombobox*Listbox.selectBackground", ACCENT_SOFT)
    root.option_add("*TCombobox*Listbox.selectForeground", INK)
    root.option_add("*TCombobox*Listbox.font", normal)

    # Buttons -----------------------------------------------------------
    _configure_button(
        style,
        "Accent.TButton",
        background=ACCENT,
        foreground="#FFFFFF",
        bordercolor=ACCENT,
        active=ACCENT_HOVER,
        font=bold,
    )
    _configure_button(
        style,
        "Ghost.TButton",
        background=SURFACE,
        foreground=INK,
        bordercolor=BORDER,
        active=SURFACE_ALT,
        font=normal,
    )
    _configure_button(
        style,
        "Danger.TButton",
        background=SURFACE,
        foreground=DANGER,
        bordercolor=DANGER_BORDER,
        active=DANGER_SOFT,
        font=normal,
    )
    _configure_button(
        style,
        "HeaderGhost.TButton",
        background=HEADER,
        foreground=HEADER_TEXT,
        bordercolor=HEADER_BORDER,
        active=HEADER_BORDER,
        font=normal,
    )

    # Treeview ----------------------------------------------------------
    style.configure(
        "Treeview",
        background=SURFACE,
        fieldbackground=SURFACE,
        foreground=INK,
        borderwidth=0,
        relief="flat",
        rowheight=32,
        font=normal,
    )
    style.map(
        "Treeview",
        background=[("selected", ACCENT_SOFT)],
        foreground=[("selected", INK)],
    )
    style.configure(
        "Treeview.Heading",
        background=SURFACE_ALT,
        foreground=MUTED,
        font=(family, AppConfig.FONT_SMALL, "bold"),
        relief="flat",
        padding=(10, 9),
        bordercolor=BORDER,
    )
    style.map(
        "Treeview.Heading",
        background=[("active", "#F1F5F9")],
        relief=[("active", "flat")],
    )
    style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])

    # Slim scrollbar without arrow buttons
    style.layout(
        "Modern.Vertical.TScrollbar",
        [
            (
                "Vertical.Scrollbar.trough",
                {
                    "sticky": "ns",
                    "children": [
                        (
                            "Vertical.Scrollbar.thumb",
                            {"expand": "1", "sticky": "nswe"},
                        )
                    ],
                },
            )
        ],
    )
    style.configure(
        "Modern.Vertical.TScrollbar",
        background=BORDER_STRONG,
        troughcolor=SURFACE,
        bordercolor=SURFACE,
        lightcolor=BORDER_STRONG,
        darkcolor=BORDER_STRONG,
        width=9,
    )
    style.map(
        "Modern.Vertical.TScrollbar",
        background=[("active", MUTED)],
    )

    return family


def _configure_button(
    style: ttk.Style,
    name: str,
    *,
    background: str,
    foreground: str,
    bordercolor: str,
    active: str,
    font: tuple,
) -> None:
    """Configure a flat ttk button with consistent hover/pressed colors."""
    style.configure(
        name,
        background=background,
        foreground=foreground,
        bordercolor=bordercolor,
        lightcolor=background,
        darkcolor=background,
        focuscolor=background,
        focusthickness=0,
        relief="flat",
        padding=(14, 9),
        font=font,
    )
    style.map(
        name,
        background=[("pressed", active), ("active", active), ("disabled", BG)],
        lightcolor=[("pressed", active), ("active", active), ("disabled", BG)],
        darkcolor=[("pressed", active), ("active", active), ("disabled", BG)],
        bordercolor=[("active", background), ("pressed", background)],
        foreground=[("disabled", DISABLED)],
    )
