import re
import time
import tkinter as tk
from tkinter import ttk, messagebox

from gui.dialogs import ProgressDialog, parse_json_output, show_error, show_info
from gui.main_window import ShellResult, run_shell_async


class PackageManagerPage(ttk.Frame):
    SEARCH_DEBOUNCE_MS = 250
    INSTALLED_CACHE_TTL_SECONDS = 20.0
    PACKAGE_PAGE_SIZE = 100

    def __init__(self, parent: tk.Widget, app) -> None:
        super().__init__(parent, style="Page.TFrame", padding=18)
        self.app = app
        self.last_loaded_action = "list_installed"
        self.last_search_query = ""
        self.selected_details: dict[str, tk.StringVar] = {}
        self._search_after_id: str | None = None
        self._installed_cache_rows: list[dict] = []
        self._installed_cache_timestamp = 0.0
        self._all_rows: list[dict] = []
        self._visible_row_count = 0
        self._build()

    def _build(self) -> None:
        summary = ttk.Frame(self, style="Card.TFrame", padding=12)
        summary.pack(fill="x", pady=(0, 12))
        summary.columnconfigure(2, weight=1)
        tk.Label(summary, text="📦", bg="#ffffff", fg="#1d4ed8", font=("DejaVu Sans", 24)).grid(row=0, column=0, rowspan=2, sticky="nw", padx=(4, 12))
        ttk.Label(summary, text=self.app.tr("Software Manager"), style="CardTitle.TLabel").grid(row=0, column=1, sticky="w")
        self.result_summary_var = tk.StringVar(value=self.app.tr("Open Installed Software to see what is already on this computer."))
        self.selection_summary_var = tk.StringVar(value=self.app.tr("Choose a package to see its details and available actions."))
        ttk.Label(summary, textvariable=self.result_summary_var, style="Section.TLabel").grid(row=0, column=2, sticky="w", padx=(8, 0))
        ttk.Label(summary, textvariable=self.selection_summary_var, style="Hint.TLabel", wraplength=880, justify="left").grid(row=1, column=2, sticky="w", padx=(8, 0), pady=(6, 0))

        controls_wrap = ttk.Frame(self, style="Card.TFrame", padding=12)
        controls_wrap.pack(fill="x", pady=(0, 12))
        controls_wrap.columnconfigure(1, weight=1)
        controls_wrap.columnconfigure(5, weight=1)
        controls_wrap.columnconfigure(6, weight=1)
        ttk.Label(controls_wrap, text=self.app.tr("Search and source"), style="CardTitle.TLabel").grid(row=0, column=0, columnspan=5, sticky="w", pady=(0, 8))
        ttk.Label(controls_wrap, text=self.app.tr("Package actions"), style="CardTitle.TLabel").grid(row=0, column=5, columnspan=2, sticky="w", padx=(14, 0), pady=(0, 8))
        ttk.Label(controls_wrap, text=self.app.tr("Search for software")).grid(row=1, column=0, sticky="w", padx=(0, 8))
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(controls_wrap, textvariable=self.search_var)
        self.search_entry.grid(row=1, column=1, sticky="ew")
        self.search_var.trace_add("write", self._schedule_search)
        self.search_entry.bind("<Return>", lambda _event: self._run_search_now())
        ttk.Button(controls_wrap, text=self.app.tr("Installed Software"), command=self.list_installed).grid(row=1, column=2, sticky="ew", padx=(8, 0))
        ttk.Button(controls_wrap, text=self.app.tr("Refresh Package Index"), command=self.refresh_package_index).grid(row=1, column=3, sticky="ew", padx=(8, 0))
        self.install_button = ttk.Button(controls_wrap, text=self.app.tr("Install"), command=self.install_selected, state="disabled")
        self.install_button.grid(row=1, column=5, sticky="ew", padx=(14, 0))
        self.remove_button = ttk.Button(controls_wrap, text=self.app.tr("Remove"), command=self.remove_selected, style="Danger.TButton", state="disabled")
        self.remove_button.grid(row=1, column=6, sticky="ew", padx=(8, 0))
        ttk.Label(
            controls_wrap,
            text=self.app.tr("Search Ubuntu software packages and install or remove selected items."),
            style="Hint.TLabel",
            wraplength=540,
            justify="left",
        ).grid(row=2, column=0, columnspan=5, sticky="w", pady=(8, 0))
        ttk.Label(
            controls_wrap,
            text=self.app.tr("Choose a package to see its details and available actions."),
            style="Hint.TLabel",
            wraplength=300,
            justify="left",
        ).grid(row=2, column=5, columnspan=2, sticky="w", padx=(14, 0), pady=(8, 0))

        content = ttk.Frame(self, style="Page.TFrame")
        content.pack(fill="both", expand=True)
        content.columnconfigure(0, weight=3)
        content.columnconfigure(1, weight=2)
        content.rowconfigure(0, weight=1)

        table = ttk.Frame(content, style="Card.TFrame", padding=12)
        table.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        ttk.Label(table, text=self.app.tr("Packages"), style="CardTitle.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 2))
        ttk.Label(table, text=self.app.tr("Search results stay ordered and load in pages as you scroll."), style="Hint.TLabel").grid(row=1, column=0, sticky="w", pady=(0, 8))
        columns = ("name", "version", "source", "status", "description")
        self.tree = ttk.Treeview(table, columns=columns, show="headings")
        for column, heading, width in [
            ("name", self.app.tr("Name"), 170),
            ("version", self.app.tr("Version"), 160),
            ("source", self.app.tr("Source"), 90),
            ("status", self.app.tr("Status"), 100),
            ("description", self.app.tr("Description"), 360),
        ]:
            self.tree.heading(column, text=heading)
            self.tree.column(column, width=width, anchor="w")
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self.update_action_states())
        self.tree.bind("<Double-1>", lambda _event: self.run_preferred_action())
        self.tree.bind("<MouseWheel>", self._on_mousewheel, add="+")
        self.tree.bind("<Button-4>", self._on_mousewheel_linux, add="+")
        self.tree.bind("<Button-5>", self._on_mousewheel_linux, add="+")
        yscroll = ttk.Scrollbar(table, orient="vertical", command=self._on_tree_scroll)
        xscroll = ttk.Scrollbar(table, orient="horizontal", command=self.tree.xview)
        self._yscroll = yscroll
        self.tree.configure(yscrollcommand=self._on_tree_yscroll, xscrollcommand=xscroll.set)
        self.tree.grid(row=2, column=0, sticky="nsew")
        yscroll.grid(row=2, column=1, sticky="ns")
        xscroll.grid(row=3, column=0, sticky="ew")
        table.rowconfigure(2, weight=1)
        table.columnconfigure(0, weight=1)

        details = ttk.Frame(content, style="Card.TFrame", padding=14)
        details.grid(row=0, column=1, sticky="nsew")
        details.columnconfigure(0, weight=1)
        ttk.Label(details, text=self.app.tr("Package details"), style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            details,
            text=self.app.tr("Selected package"),
            style="Hint.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(4, 10))
        self.selected_details = {
            "name": tk.StringVar(value="—"),
            "version": tk.StringVar(value="—"),
            "source": tk.StringVar(value="—"),
            "status": tk.StringVar(value="—"),
            "description": tk.StringVar(value=self.app.tr("Choose a package to see its details and available actions.")),
            "next_action": tk.StringVar(value=self.app.tr("No package selected.")),
        }
        info_grid = ttk.Frame(details, style="Surface.TFrame")
        info_grid.grid(row=2, column=0, sticky="ew")
        info_grid.columnconfigure(0, weight=1)
        for label_key, var_key in [("Name", "name"), ("Version", "version"), ("Source", "source"), ("Status", "status")]:
            row = ttk.Frame(info_grid, style="Surface.TFrame")
            row.pack(fill="x", pady=(10 if label_key == "Name" else 8, 0))
            ttk.Label(row, text=self.app.tr(label_key), width=10, font=("DejaVu Sans", 10, "bold")).pack(side="left", anchor="nw")
            ttk.Label(row, textvariable=self.selected_details[var_key], wraplength=270, justify="left").pack(side="left", fill="x", expand=True)

        ttk.Label(details, text=self.app.tr("Description"), style="Section.TLabel").grid(row=3, column=0, sticky="w", pady=(14, 0))
        ttk.Label(details, textvariable=self.selected_details["description"], wraplength=320, justify="left").grid(row=4, column=0, sticky="w", pady=(4, 0))
        ttk.Label(details, text=self.app.tr("Suggested action"), style="Section.TLabel").grid(row=5, column=0, sticky="w", pady=(14, 0))
        ttk.Label(details, textvariable=self.selected_details["next_action"], wraplength=320, justify="left").grid(row=6, column=0, sticky="w", pady=(4, 0))

        self.update_action_states()

    def on_show(self) -> None:
        self.refresh_current_view()

    def destroy(self) -> None:
        self._cancel_pending_search()
        super().destroy()

    def update_action_states(self) -> None:
        item = self.tree.focus()
        if not item:
            self.install_button.configure(state="disabled")
            self.remove_button.configure(state="disabled")
            self.selection_summary_var.set(self.app.tr("Choose a package to see its details and available actions."))
            self._set_selected_details()
            return
        values = self.tree.item(item, "values")
        source = values[2] if len(values) > 2 else ""
        status = values[3] if len(values) > 3 else ""
        can_install = source == self.app.tr("APT") and status != self.app.tr("Installed")
        can_remove = source in {self.app.tr("APT"), self.app.tr("Snap")} and status == self.app.tr("Installed")
        self.install_button.configure(state="normal" if can_install else "disabled")
        self.remove_button.configure(state="normal" if can_remove else "disabled")
        package = values[0] if values else ""
        self.selection_summary_var.set(self.app.tr("Selected package: {package}", package=package))
        self._set_selected_details(
            package,
            values[1] if len(values) > 1 else "",
            source,
            status,
            values[4] if len(values) > 4 else "",
        )

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
            if action in {"install_package", "remove_package", "apt_update_if_needed"}:
                show_info(self, title, result.stdout)
        else:
            self.app.set_status(self.app.tr("Package action failed."))
            show_error(self, title, result.stderr)

    def _ordered_rows(self, rows: list[dict]) -> list[dict]:
        return sorted(
            rows,
            key=lambda row: (
                0 if row.get("status", "") == "Installed" else 1,
                str(row.get("name", "")).casefold(),
            ),
        )

    def _row_values(self, row: dict) -> tuple[str, str, str, str, str]:
        status = row.get("status", "")
        manager = row.get("manager", "APT")
        return (
            row.get("name", ""),
            row.get("version", ""),
            self.app.tr(manager),
            self.app.tr(status),
            row.get("description", ""),
        )

    def _append_next_page(self) -> None:
        if self._visible_row_count >= len(self._all_rows):
            return
        next_count = min(self._visible_row_count + self.PACKAGE_PAGE_SIZE, len(self._all_rows))
        for row in self._all_rows[self._visible_row_count:next_count]:
            self.tree.insert("", "end", values=self._row_values(row))
        self._visible_row_count = next_count
        self._update_result_summary()

    def _update_result_summary(self) -> None:
        total_count = len(self._all_rows)
        shown_count = self._visible_row_count
        if self.last_loaded_action == "search_packages":
            query = self.last_search_query or self.search_var.get().strip()
            if query:
                self.result_summary_var.set(
                    self.app.tr(
                        "Showing {shown} of {total} packages for “{query}”.",
                        shown=shown_count,
                        total=total_count,
                        query=query,
                    )
                )
            else:
                self.result_summary_var.set(
                    self.app.tr("Showing {shown} of {total} available packages.", shown=shown_count, total=total_count)
                )
        else:
            self.result_summary_var.set(
                self.app.tr("Showing {shown} of {total} installed packages.", shown=shown_count, total=total_count)
            )

    def _maybe_load_more(self) -> None:
        if not self._all_rows or self._visible_row_count >= len(self._all_rows):
            return
        first, last = self.tree.yview()
        if last >= 0.98:
            self._append_next_page()

    def _on_tree_scroll(self, *args) -> None:
        self.tree.yview(*args)
        self._maybe_load_more()

    def _on_tree_yscroll(self, first: str, last: str) -> None:
        self._yscroll.set(first, last)
        self._maybe_load_more()

    def _on_mousewheel(self, _event) -> None:
        self.after_idle(self._maybe_load_more)

    def _on_mousewheel_linux(self, _event) -> None:
        self.after_idle(self._maybe_load_more)

    def populate(self, rows: list[dict]) -> None:
        self.tree.delete(*self.tree.get_children())
        self._all_rows = self._ordered_rows(rows)
        self._visible_row_count = 0
        self._append_next_page()
        if self._all_rows:
            first_item = self.tree.get_children()[0]
            self.tree.focus(first_item)
            self.tree.selection_set(first_item)
        self.update_action_states()
        if not self._all_rows:
            if self.last_loaded_action == "search_packages":
                self.selection_summary_var.set(self.app.tr("No packages matched this search."))
                self._set_selected_details(description=self.app.tr("Try a broader package name or load Installed Software instead."))
            else:
                self.selection_summary_var.set(self.app.tr("No installed packages were returned."))
                self._set_selected_details(description=self.app.tr("Try Refresh Package Index or search for a package by name."))

    def _set_selected_details(self, name: str = "—", version: str = "—", source: str = "—", status: str = "—", description: str = "", next_action: str = "") -> None:
        self.selected_details["name"].set(name or "—")
        self.selected_details["version"].set(version or "—")
        self.selected_details["source"].set(source or "—")
        self.selected_details["status"].set(status or "—")
        self.selected_details["description"].set(description or self.app.tr("Choose a package to see its details and available actions."))
        if not next_action:
            if status == self.app.tr("Installed"):
                if source == self.app.tr("Snap"):
                    next_action = self.app.tr("This Snap package is installed. You can remove it from this screen.")
                else:
                    next_action = self.app.tr("This package is installed. You can remove it from this screen.")
            elif name and name != "—":
                next_action = self.app.tr("This package is available. You can install it from this screen.")
            else:
                next_action = self.app.tr("No package selected.")
        self.selected_details["next_action"].set(next_action)

    def _has_fresh_installed_cache(self) -> bool:
        return bool(self._installed_cache_rows) and (time.monotonic() - self._installed_cache_timestamp) < self.INSTALLED_CACHE_TTL_SECONDS

    def _store_installed_cache(self, rows: list[dict]) -> None:
        self._installed_cache_rows = list(rows)
        self._installed_cache_timestamp = time.monotonic()

    def _clear_installed_cache(self) -> None:
        self._installed_cache_rows = []
        self._installed_cache_timestamp = 0.0

    def refresh_current_view(self) -> None:
        if self.last_loaded_action == "search_packages":
            self.run_action(
                self.app.tr("Search"),
                "search_packages",
                [self.last_search_query],
                lambda result: self.populate(parse_json_output(result.stdout, [])),
                show_output=False,
            )
            return
        self.list_installed()

    def _cancel_pending_search(self) -> None:
        if self._search_after_id is not None:
            self.after_cancel(self._search_after_id)
            self._search_after_id = None

    def _schedule_search(self, *_args) -> None:
        self._cancel_pending_search()

        def trigger() -> None:
            self._search_after_id = None
            self.search_packages()

        self._search_after_id = self.after(self.SEARCH_DEBOUNCE_MS, trigger)

    def _run_search_now(self) -> None:
        self._cancel_pending_search()
        self.search_packages()

    def search_packages(self) -> None:
        query = self.search_var.get().strip()
        self.last_loaded_action = "search_packages"
        self.last_search_query = query
        self.run_action(self.app.tr("Search"), "search_packages", [query], lambda result: self.populate(parse_json_output(result.stdout, [])), show_output=False)

    def list_installed(self, force: bool = False) -> None:
        self._cancel_pending_search()
        self.last_loaded_action = "list_installed"
        if not force and self._has_fresh_installed_cache():
            self.populate(self._installed_cache_rows)
            self.app.set_status(self.app.tr("Showing cached installed packages."))
            return

        def finish(result: ShellResult) -> None:
            rows = parse_json_output(result.stdout, [])
            self._store_installed_cache(rows)
            self.populate(rows)

        self.run_action(self.app.tr("Installed Software"), "list_installed", [], finish, show_output=False)

    def refresh_package_index(self) -> None:
        message = (
            f"{self.app.tr('Refresh the Ubuntu package index now?')}\n\n"
            f"{self.app.tr('This helps the search results stay current. Ubuntu may ask for your administrator password.')}"
        )
        if messagebox.askyesno(self.app.tr("Refresh Package Index"), message, parent=self):
            self._clear_installed_cache()
            self.run_action(
                self.app.tr("Refresh Package Index"),
                "apt_update_if_needed",
                [],
                on_success=lambda _result: self.refresh_current_view(),
                require_root=True,
            )

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
        return values[3] if len(values) > 3 else ""

    def selected_source(self) -> str:
        item = self.tree.focus()
        if not item:
            return ""
        values = self.tree.item(item, "values")
        return values[2] if len(values) > 2 else ""

    def run_preferred_action(self) -> None:
        package = self.selected_package()
        if not package:
            return
        if self.selected_status() == self.app.tr("Installed"):
            self.remove_selected()
        else:
            self.install_selected()

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
        if self.selected_source() != self.app.tr("APT"):
            messagebox.showinfo(self.app.tr("Install unavailable"), self.app.tr("Only APT search results can be installed from this screen right now."), parent=self)
            return
        message = (
            f"{self.app.tr('Install this software package?')}\n\n{package}\n\n"
            f"{self.app.tr('Ubuntu may ask for your administrator password.')}"
        )
        if messagebox.askyesno(self.app.tr("Install Software"), message, parent=self):
            self._clear_installed_cache()
            self.run_action(
                self.app.tr("Install Software"),
                "install_package",
                [package],
                on_success=lambda _result: self.refresh_current_view(),
                require_root=True,
            )

    def remove_selected(self) -> None:
        package = self.selected_package()
        if not self.validate_package(package):
            return
        if self.selected_status() != self.app.tr("Installed"):
            messagebox.showinfo(self.app.tr("Not installed"), self.app.tr("{package} is not installed, so it cannot be removed.", package=package), parent=self)
            return
        source = self.selected_source() or self.app.tr("APT")
        message = (
            f"{self.app.tr('Remove this software package?')}\n\n{package}\n{self.app.tr('Source')}: {source}\n\n"
            f"{self.app.tr('Ubuntu may ask for your administrator password. Automatic cleanup will not be run.')}"
        )
        if messagebox.askyesno(self.app.tr("Remove Software"), message, parent=self):
            self._clear_installed_cache()
            self.run_action(
                self.app.tr("Remove Software"),
                "remove_package",
                ["snap" if source == self.app.tr("Snap") else "apt", package],
                on_success=lambda _result: self.refresh_current_view(),
                require_root=True,
            )
