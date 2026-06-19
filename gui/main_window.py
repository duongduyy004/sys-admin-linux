from __future__ import annotations

import os
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import tkinter as tk
from tkinter import ttk

from gui.i18n import LANGUAGE_OPTIONS, get_language, set_language, tr
from gui.styles import COLORS, configure_styles, make_sidebar_button


PROJECT_DIR = Path(__file__).resolve().parent.parent
SH_DIR = PROJECT_DIR / "sh"


@dataclass(slots=True)
class ShellResult:
    success: bool
    stdout: str
    stderr: str
    returncode: int
    command: list[str]


def run_shell(script_name: str, action: str, args: list[str] | None = None, require_root: bool = False) -> tuple[bool, str, str, int]:
    """
    Runs a shell backend script safely.

    script_name: file_manager.sh, task_scheduler.sh, and similar backend files
    action: backend action name
    args: list of arguments
    require_root: whether pkexec is needed

    Returns:
        success, stdout, stderr, returncode
    """
    script_path = SH_DIR / script_name
    command = ["bash", str(script_path), action, *(args or [])]
    if require_root and os.environ.get("MOCK_MODE") != "1":
        command = ["pkexec", *command]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        cwd=str(PROJECT_DIR),
        env=os.environ.copy(),
    )
    return result.returncode == 0, result.stdout, result.stderr, result.returncode


def run_shell_async(
    script_name: str,
    action: str,
    args: list[str] | None,
    require_root: bool,
    on_done: Callable[[ShellResult], None],
) -> None:
    script_path = SH_DIR / script_name
    command = ["bash", str(script_path), action, *(args or [])]
    if require_root and os.environ.get("MOCK_MODE") != "1":
        command = ["pkexec", *command]

    def worker() -> None:
        success, stdout, stderr, returncode = run_shell(script_name, action, args, require_root)
        result = ShellResult(success, stdout, stderr, returncode, command)
        on_done(result)

    threading.Thread(target=worker, daemon=True).start()


class MainWindow(ttk.Frame):
    def __init__(self, root: tk.Tk) -> None:
        super().__init__(root)
        self.root = root
        self.current_page = "Files & Folders"
        self.root.title(tr("SysAdmin GUI"))
        self.root.geometry("1180x760")
        self.root.minsize(980, 620)
        configure_styles(root)

        self.pack(fill="both", expand=True)
        self.sidebar = tk.Frame(self, width=238, bg=COLORS["sidebar"])
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        main_area = ttk.Frame(self, style="Page.TFrame")
        main_area.pack(side="right", fill="both", expand=True)

        self.content = ttk.Frame(main_area, style="Page.TFrame")
        self.content.pack(fill="both", expand=True, padx=16, pady=(16, 0))
        self.status_var = tk.StringVar(value=tr("Ready"))
        status_frame = ttk.Frame(main_area, style="Surface.TFrame", padding=(12, 10))
        status_frame.pack(fill="x", side="bottom", padx=16, pady=(12, 16))
        status_frame.columnconfigure(0, weight=1)
        ttk.Label(status_frame, textvariable=self.status_var, style="Status.TLabel").grid(row=0, column=0, sticky="ew")
        ttk.Label(
            status_frame,
            text=tr("Tip: use the sidebar to switch features without closing your current window."),
            style="Hint.TLabel",
        ).grid(row=0, column=1, sticky="e", padx=(12, 0))

        self.pages: dict[str, ttk.Frame] = {}
        self.buttons: dict[str, tk.Button] = {}
        self.sidebar_title: tk.Label | None = None
        self.sidebar_section_label: tk.Label | None = None
        self.language_label: ttk.Label | None = None
        self.language_combo: ttk.Combobox | None = None
        self.exit_button: tk.Button | None = None

        self._build_sidebar()
        self._load_pages()
        self.show_page(self.current_page)

    def _build_sidebar(self) -> None:
        title = tk.Label(
            self.sidebar,
            text=tr("SysAdmin GUI"),
            fg="#ffffff",
            bg=COLORS["sidebar"],
            font=("DejaVu Sans", 16, "bold"),
            anchor="w",
            padx=18,
            pady=18,
        )
        title.pack(fill="x")
        self.sidebar_title = title
        tk.Label(
            self.sidebar,
            text=tr("System tasks"),
            fg="#cbd5e1",
            bg=COLORS["sidebar"],
            font=("DejaVu Sans", 10),
            anchor="w",
            padx=18,
            pady=0,
        ).pack(fill="x", pady=(0, 10))
        self.sidebar_section_label = self.sidebar.winfo_children()[-1]

        items = [
            ("📁", "Files & Folders"),
            ("⏰", "Scheduled Tasks"),
            ("🕐", "Date & Time"),
            ("📦", "Software Manager"),
            ("⚙️", "About"),
        ]
        for icon, page_name in items:
            button = make_sidebar_button(self.sidebar, self.sidebar_text(icon, page_name), lambda name=page_name: self.show_page(name))
            button.pack(fill="x")
            self.buttons[page_name] = button

        spacer = tk.Frame(self.sidebar, bg=COLORS["sidebar"])
        spacer.pack(fill="both", expand=True)
        utility = ttk.Frame(self.sidebar, style="Surface.TFrame", padding=10)
        utility.pack(fill="x", padx=12, pady=(8, 10))
        self.language_label = ttk.Label(utility, text=tr("Language"), style="Hint.TLabel")
        self.language_label.pack(anchor="w", pady=(0, 4))
        self.language_var = tk.StringVar(value=LANGUAGE_OPTIONS[get_language()])
        self.language_combo = ttk.Combobox(
            utility,
            textvariable=self.language_var,
            values=list(LANGUAGE_OPTIONS.values()),
            state="readonly",
            width=12,
            style="SidebarUtility.TCombobox",
        )
        self.language_combo.pack(fill="x")
        self.language_combo.bind("<<ComboboxSelected>>", self.change_language)
        exit_button = make_sidebar_button(self.sidebar, f"❌ {tr('Exit')}", self.root.destroy)
        exit_button.pack(fill="x", side="bottom")
        self.exit_button = exit_button

    def _load_pages(self) -> None:
        from gui.about_page import AboutPage
        from gui.dashboard_page import DashboardPage
        from gui.file_manager_page import FileManagerPage
        from gui.package_manager_page import PackageManagerPage
        from gui.task_scheduler_page import TaskSchedulerPage
        from gui.time_settings_page import TimeSettingsPage

        self.pages = {
            "Home": DashboardPage(self.content, self),
            "Files & Folders": FileManagerPage(self.content, self),
            "Scheduled Tasks": TaskSchedulerPage(self.content, self),
            "Date & Time": TimeSettingsPage(self.content, self),
            "Software Manager": PackageManagerPage(self.content, self),
            "About": AboutPage(self.content, self),
        }
        for page in self.pages.values():
            page.grid(row=0, column=0, sticky="nsew")
        self.content.rowconfigure(0, weight=1)
        self.content.columnconfigure(0, weight=1)

    def show_page(self, name: str) -> None:
        self.current_page = name
        page = self.pages[name]
        page.tkraise()
        self.set_status(tr("{name} is open.", name=tr(name)))
        for page_name, button in self.buttons.items():
            button.configure(
                bg=COLORS["sidebar_active"] if page_name == name else COLORS["sidebar"],
                relief="sunken" if page_name == name else "flat",
            )
        if hasattr(page, "on_show"):
            page.on_show()

    def set_status(self, message: str) -> None:
        self.status_var.set(message)

    def tr(self, text: str, **kwargs) -> str:
        return tr(text, **kwargs)

    def sidebar_text(self, icon: str, page_name: str) -> str:
        return f"{icon} {tr(page_name)}"

    def change_language(self, _event=None) -> None:
        selected = self.language_var.get()
        for code, label in LANGUAGE_OPTIONS.items():
            if label == selected:
                self.set_language(code)
                break

    def set_language(self, language: str) -> None:
        if language == get_language():
            return
        set_language(language)
        page_name = self.current_page
        self.root.title(tr("SysAdmin GUI"))
        if self.language_label is not None:
            self.language_label.configure(text=tr("Language"))
        self.language_var.set(LANGUAGE_OPTIONS[get_language()])
        self.update_sidebar_text()
        self.rebuild_pages()
        self.show_page(page_name)

    def update_sidebar_text(self) -> None:
        if self.sidebar_title is not None:
            self.sidebar_title.configure(text=tr("SysAdmin GUI"))
        if self.sidebar_section_label is not None:
            self.sidebar_section_label.configure(text=tr("System tasks"))
        icons = {
            "Home": "🏠",
            "Files & Folders": "📁",
            "Scheduled Tasks": "⏰",
            "Date & Time": "🕐",
            "Software Manager": "📦",
            "About": "⚙️",
        }
        for page_name, button in self.buttons.items():
            button.configure(text=self.sidebar_text(icons[page_name], page_name))
        if self.exit_button is not None:
            self.exit_button.configure(text=f"❌ {tr('Exit')}")

    def rebuild_pages(self) -> None:
        for child in self.content.winfo_children():
            child.destroy()
        self.pages = {}
        self._load_pages()
