import re
import tkinter as tk
from tkinter import ttk, messagebox

from gui.dialogs import ProgressDialog, parse_json_output, show_error, show_info
from gui.main_window import ShellResult, run_shell_async


class PackageManagerPage(ttk.Frame):
    def __init__(self, parent: tk.Widget, app) -> None:
        super().__init__(parent, style="Page.TFrame", padding=18)
        self.app = app
        self._build()

    def _build(self) -> None:
        ttk.Label(self, text=self.app.tr("Software Manager"), style="Header.TLabel").pack(anchor="w")
        ttk.Label(
            self,
            text=self.app.tr("Search Ubuntu software packages and install or remove selected items."),
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(2, 14))

        search = ttk.Frame(self)
        search.pack(fill="x", pady=(0, 10))
        ttk.Label(search, text=self.app.tr("Search for software")).pack(side="left", padx=(0, 8))
        self.search_var = tk.StringVar()
        ttk.Entry(search, textvariable=self.search_var).pack(side="left", fill="x", expand=True)
        ttk.Button(search, text=self.app.tr("Search"), command=self.search_packages, style="Accent.TButton").pack(side="left", padx=(8, 0))
        ttk.Button(search, text=self.app.tr("Installed Software"), command=self.list_installed).pack(side="left", padx=(8, 0))

        actions = ttk.Frame(self)
        actions.pack(fill="x", pady=(0, 10))
        self.install_button = ttk.Button(actions, text=self.app.tr("Install"), command=self.install_selected, state="disabled")
        self.install_button.pack(side="left")
        self.remove_button = ttk.Button(actions, text=self.app.tr("Remove"), command=self.remove_selected, style="Danger.TButton", state="disabled")
        self.remove_button.pack(side="left", padx=(8, 0))

        table = ttk.Frame(self)
        table.pack(fill="both", expand=True)
        columns = ("name", "version", "status", "description")
        self.tree = ttk.Treeview(table, columns=columns, show="headings")
        for column, heading, width in [
            ("name", self.app.tr("Name"), 170),
            ("version", self.app.tr("Version"), 160),
            ("status", self.app.tr("Status"), 100),
            ("description", self.app.tr("Description"), 420),
        ]:
            self.tree.heading(column, text=heading)
            self.tree.column(column, width=width, anchor="w")
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self.update_action_states())
        yscroll = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        xscroll = ttk.Scrollbar(table, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        table.rowconfigure(0, weight=1)
        table.columnconfigure(0, weight=1)
        self.update_action_states()

    def update_action_states(self) -> None:
        item = self.tree.focus()
        if not item:
            self.install_button.configure(state="disabled")
            self.remove_button.configure(state="disabled")
            return
        values = self.tree.item(item, "values")
        status = values[2] if len(values) > 2 else ""
        self.install_button.configure(state="disabled" if status == self.app.tr("Installed") else "normal")
        self.remove_button.configure(state="normal" if status == self.app.tr("Installed") else "disabled")

    def run_action(self, title: str, action: str, args: list[str], on_success=None, require_root: bool = False, show_output: bool = True) -> None:
        progress = ProgressDialog(self, title, self.app.tr("Working with software packages..."))

        def done(result: ShellResult) -> None:
            self.after(0, lambda: self._finish(progress, title, action, result, on_success, show_output))

        run_shell_async("package_manager.sh", action, args, require_root, done)

    def _finish(self, progress: ProgressDialog, title: str, action: str, result: ShellResult, on_success, show_output: bool) -> None:
        progress.finish(result.success, result.stdout, result.stderr, show_output=show_output)
        if result.success:
            self.app.set_status(result.stdout.strip()[:160] or self.app.tr("Package action completed."))
            if on_success:
                on_success(result)
            if action in {"install_package", "remove_package"}:
                show_info(self, title, result.stdout)
        else:
            self.app.set_status(self.app.tr("Package action failed."))
            show_error(self, title, result.stderr)

    def populate(self, rows: list[dict]) -> None:
        self.tree.delete(*self.tree.get_children())
        for row in rows:
            status = row.get("status", "")
            self.tree.insert("", "end", values=(row.get("name", ""), row.get("version", ""), self.app.tr(status), row.get("description", "")))
        self.update_action_states()

    def search_packages(self) -> None:
        query = self.search_var.get().strip()
        if not query:
            messagebox.showwarning(self.app.tr("Search text required"), self.app.tr("Enter a software name or keyword."), parent=self)
            return
        self.run_action(self.app.tr("Search"), "search_packages", [query], lambda result: self.populate(parse_json_output(result.stdout, [])), show_output=False)

    def list_installed(self) -> None:
        self.run_action(self.app.tr("Installed Software"), "list_installed", [], lambda result: self.populate(parse_json_output(result.stdout, [])), show_output=False)

    def selected_package(self) -> str:
        item = self.tree.focus()
        if not item:
            return ""
        values = self.tree.item(item, "values")
        return values[0] if values else ""

    def selected_status(self) -> str:
        item = self.tree.focus()
        if not item:
            return ""
        values = self.tree.item(item, "values")
        return values[2] if len(values) > 2 else ""

    def validate_package(self, package: str) -> bool:
        if not package:
            messagebox.showwarning(self.app.tr("No package selected"), self.app.tr("Choose a package first."), parent=self)
            return False
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9+._:-]*", package):
            messagebox.showwarning(self.app.tr("Invalid package name"), self.app.tr("The package name contains unsupported characters."), parent=self)
            return False
        return True

    def install_selected(self) -> None:
        package = self.selected_package()
        if not self.validate_package(package):
            return
        if self.selected_status() == self.app.tr("Installed"):
            messagebox.showinfo(self.app.tr("Already installed"), self.app.tr("{package} is already installed.", package=package), parent=self)
            return
        message = (
            f"{self.app.tr('Install this software package?')}\n\n{package}\n\n"
            f"{self.app.tr('Ubuntu may ask for your administrator password.')}"
        )
        if messagebox.askyesno(self.app.tr("Install Software"), message, parent=self):
            self.run_action(self.app.tr("Install Software"), "install_package", [package], require_root=True)

    def remove_selected(self) -> None:
        package = self.selected_package()
        if not self.validate_package(package):
            return
        if self.selected_status() != self.app.tr("Installed"):
            messagebox.showinfo(self.app.tr("Not installed"), self.app.tr("{package} is not installed, so it cannot be removed.", package=package), parent=self)
            return
        message = (
            f"{self.app.tr('Remove this software package?')}\n\n{package}\n\n"
            f"{self.app.tr('Ubuntu may ask for your administrator password. Automatic cleanup will not be run.')}"
        )
        if messagebox.askyesno(self.app.tr("Remove Software"), message, parent=self):
            self.run_action(self.app.tr("Remove Software"), "remove_package", [package], require_root=True)
