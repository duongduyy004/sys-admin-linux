import tkinter as tk
from tkinter import ttk


FEATURES = [
    (
        "Files & Folders",
        "📁",
        "Create, copy, move, search, compress, and safely delete files.",
    ),
    (
        "Scheduled Tasks",
        "⏰",
        "Add, review, and remove automatic jobs created by this app.",
    ),
    (
        "Date & Time",
        "🕐",
        "View or update the system clock, timezone, and automatic sync.",
    ),
    (
        "Software Manager",
        "📦",
        "Search Ubuntu packages and install or remove selected software.",
    ),
]


class DashboardPage(ttk.Frame):
    def __init__(self, parent: tk.Widget, app) -> None:
        super().__init__(parent, style="Page.TFrame", padding=18)
        self.app = app
        self._build()

    def _build(self) -> None:
        ttk.Label(self, text=self.app.tr("SysAdmin GUI"), style="Header.TLabel").pack(anchor="w")
        ttk.Label(
            self,
            text=self.app.tr("A friendly place to manage common Ubuntu system tasks."),
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(2, 18))

        grid = ttk.Frame(self, style="Page.TFrame")
        grid.pack(fill="both", expand=True)
        for index, (page_name, icon, description) in enumerate(FEATURES):
            card = ttk.Frame(grid, style="Card.TFrame", padding=16)
            card.grid(row=index // 2, column=index % 2, sticky="nsew", padx=8, pady=8)
            ttk.Label(card, text=icon, font=("DejaVu Sans", 22), background="#ffffff").pack(anchor="w")
            ttk.Label(card, text=self.app.tr(page_name), font=("DejaVu Sans", 13, "bold"), background="#ffffff").pack(anchor="w", pady=(8, 4))
            ttk.Label(card, text=self.app.tr(description), wraplength=310, background="#ffffff").pack(anchor="w", fill="x")
            ttk.Button(
                card,
                text=self.app.tr("Open {name}", name=self.app.tr(page_name)),
                command=lambda name=page_name: self.app.show_page(name),
                style="Accent.TButton",
            ).pack(anchor="w", pady=(14, 0))

        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)
        grid.rowconfigure(0, weight=1)
        grid.rowconfigure(1, weight=1)

    def on_show(self) -> None:
        self.app.set_status(self.app.tr("Home is open. Choose a task to get started."))
