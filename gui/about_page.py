import tkinter as tk
from tkinter import ttk


class AboutPage(ttk.Frame):
    def __init__(self, parent: tk.Widget, app) -> None:
        super().__init__(parent, style="Page.TFrame", padding=18)
        self.app = app
        self._build()

    def _build(self) -> None:
        body = ttk.Frame(self, style="Card.TFrame", padding=18)
        body.pack(fill="x", pady=(0, 12))
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

        safety = ttk.LabelFrame(self, text=self.app.tr("Safety reminders"), padding=14)
        safety.pack(fill="x")
        for line in [
            "The app stays open after successful or failed actions.",
            "Shell scripts receive argument lists instead of ad-hoc shell strings.",
            "Actions that need elevated access ask Ubuntu for permission at run time.",
        ]:
            ttk.Label(safety, text=f"• {self.app.tr(line)}", style="Hint.TLabel", wraplength=760, justify="left").pack(anchor="w", pady=2)
