import tkinter as tk
from tkinter import ttk


class AboutPage(ttk.Frame):
    def __init__(self, parent: tk.Widget, app) -> None:
        super().__init__(parent, style="Page.TFrame", padding=18)
        self.app = app
        self._build()

    def _build(self) -> None:
        ttk.Label(self, text=self.app.tr("About"), style="Header.TLabel").pack(anchor="w")
        ttk.Label(self, text=self.app.tr("SysAdmin GUI is a Python desktop application backed by safe shell scripts."), style="Subtitle.TLabel").pack(anchor="w", pady=(2, 18))

        body = ttk.Frame(self, style="Card.TFrame", padding=18)
        body.pack(fill="x")
        text = (
            self.app.tr("SysAdmin GUI provides friendly screens for common Ubuntu administration tasks.")
            + "\n\n"
            + self.app.tr("The window, sidebar, forms, tables, confirmations, progress views, and validation are handled by Python and Tkinter.")
            + " "
            + self.app.tr("System actions are delegated to shell scripts through argument lists, stdout, stderr, and exit codes.")
            + "\n\n"
            + self.app.tr("Destructive and privileged actions ask for confirmation before they run.")
        )
        ttk.Label(body, text=text, wraplength=680, justify="left").pack(anchor="w")
