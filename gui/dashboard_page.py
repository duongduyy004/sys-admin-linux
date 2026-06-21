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
        hero = ttk.Frame(self, style="Card.TFrame", padding=18)
        hero.pack(fill="x", pady=(0, 14))
        hero.columnconfigure(0, weight=3)
        hero.columnconfigure(1, weight=2)

        intro = ttk.Frame(hero, style="Card.TFrame")
        intro.grid(row=0, column=0, sticky="nsew", padx=(0, 18))
        ttk.Label(intro, text=self.app.tr("AdminDesk"), style="Header.TLabel").pack(anchor="w")
        ttk.Label(
            intro,
            text=self.app.tr("A simpler front door for common Ubuntu administration tasks."),
            style="Hint.TLabel",
            wraplength=520,
            justify="left",
        ).pack(anchor="w", pady=(4, 10))
        ttk.Label(
            intro,
            text=self.app.tr("Choose a feature card below or use the sidebar to move between tools without leaving the window."),
            style="Hint.TLabel",
            wraplength=520,
            justify="left",
        ).pack(anchor="w")

        tips = ttk.LabelFrame(hero, text=self.app.tr("Quick tips"), padding=12)
        tips.grid(row=0, column=1, sticky="nsew")
        for tip in [
            "Double-click folders in Files & Folders to open them.",
            "Package and task details appear when you select a row.",
            "Risky actions stay disabled until you pick an item.",
        ]:
            ttk.Label(tips, text=f"• {self.app.tr(tip)}", style="Hint.TLabel", wraplength=300, justify="left").pack(anchor="w", pady=2)

        ttk.Label(self, text=self.app.tr("Main tools"), style="CardTitle.TLabel").pack(anchor="w", pady=(0, 8))
        grid = ttk.Frame(self, style="Page.TFrame")
        grid.pack(fill="both", expand=True)
        for index, (page_name, icon, description) in enumerate(FEATURES):
            card = ttk.Frame(grid, style="Card.TFrame", padding=16)
            card.grid(row=index // 2, column=index % 2, sticky="nsew", padx=8, pady=8)
            ttk.Label(card, text=icon, font=("DejaVu Sans", 22), background="#ffffff").pack(anchor="w")
            ttk.Label(card, text=self.app.tr(page_name), style="CardTitle.TLabel").pack(anchor="w", pady=(8, 4))
            ttk.Label(card, text=self.app.tr(description), style="Hint.TLabel", wraplength=310, justify="left").pack(anchor="w", fill="x")
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
