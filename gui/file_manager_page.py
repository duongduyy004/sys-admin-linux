import os
import re
import tempfile
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from gui.dialogs import ProgressDialog, ask_form, ask_permission_form, parse_json_output, show_error, show_info
from gui.main_window import ShellResult, run_shell_async


DANGEROUS_DELETE_PATHS = {
    "/",
    "/bin",
    "/boot",
    "/dev",
    "/etc",
    "/lib",
    "/lib64",
    "/proc",
    "/root",
    "/run",
    "/sbin",
    "/sys",
    "/usr",
    "/var",
    "/opt",
}

MAX_PREVIEW_BYTES = 1024 * 1024


def format_size(value) -> str:
    try:
        size = float(value)
    except (TypeError, ValueError):
        return ""
    if size < 0:
        return ""
    units = ("B", "KB", "MB", "GB", "TB")
    unit_index = 0
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1
    if unit_index == 0:
        return f"{int(size):,} B"
    if size >= 100:
        amount = f"{size:,.0f}"
    elif size >= 10:
        amount = f"{size:,.1f}"
    else:
        amount = f"{size:,.2f}"
    return f"{amount} {units[unit_index]}"


def canonical(path: str) -> str:
    return os.path.realpath(os.path.expanduser(path))


def is_protected_path(path: str) -> bool:
    return canonical(path) in DANGEROUS_DELETE_PATHS


def is_inside_protected_area(path: str) -> bool:
    full = canonical(path)
    return any(full == protected or full.startswith(f"{protected}/") for protected in DANGEROUS_DELETE_PATHS if protected != "/")


class FilePreviewWindow(tk.Toplevel):
    def __init__(self, parent: tk.Widget, path: str) -> None:
        super().__init__(parent)
        self.tr = parent.app.tr
        self.path = path
        self.title(self.tr("Preview: {name}", name=Path(path).name))
        self.geometry("760x520")
        self.minsize(560, 360)
        self.transient(parent)

        body = ttk.Frame(self, padding=14)
        body.pack(fill="both", expand=True)

        ttk.Label(body, text=Path(path).name, style="Header.TLabel").pack(anchor="w")
        ttk.Label(body, text=path, style="Subtitle.TLabel", wraplength=700).pack(anchor="w", pady=(2, 10))

        self.message_var = tk.StringVar(value=self.tr("Loading preview..."))
        ttk.Label(body, textvariable=self.message_var, style="Subtitle.TLabel").pack(anchor="w", pady=(0, 8))

        text_frame = ttk.Frame(body)
        text_frame.pack(fill="both", expand=True)
        self.text = tk.Text(text_frame, wrap="word", state="disabled")
        yscroll = ttk.Scrollbar(text_frame, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=yscroll.set)
        self.text.pack(side="left", fill="both", expand=True)
        yscroll.pack(side="right", fill="y")

        ttk.Button(body, text=self.tr("Close"), command=self.destroy).pack(anchor="e", pady=(10, 0))

    def set_content(self, message: str, content: str = "") -> None:
        self.message_var.set(message)
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        if content:
            self.text.insert("1.0", content)
        self.text.configure(state="disabled")


class FileEditWindow(tk.Toplevel):
    def __init__(self, parent: "FileManagerPage", path: str) -> None:
        super().__init__(parent)
        self.parent_page = parent
        self.tr = parent.app.tr
        self.path = path
        self.title(self.tr("Edit File: {name}", name=Path(path).name))
        self.geometry("820x580")
        self.minsize(620, 420)
        self.transient(parent)

        body = ttk.Frame(self, padding=14)
        body.pack(fill="both", expand=True)

        ttk.Label(body, text=Path(path).name, style="Header.TLabel").pack(anchor="w")
        ttk.Label(body, text=path, style="Subtitle.TLabel", wraplength=760).pack(anchor="w", pady=(2, 10))

        self.message_var = tk.StringVar(value=self.tr("Loading file..."))
        ttk.Label(body, textvariable=self.message_var, style="Subtitle.TLabel").pack(anchor="w", pady=(0, 8))

        text_frame = ttk.Frame(body)
        text_frame.pack(fill="both", expand=True)
        self.text = tk.Text(text_frame, wrap="none", undo=True)
        yscroll = ttk.Scrollbar(text_frame, orient="vertical", command=self.text.yview)
        xscroll = ttk.Scrollbar(text_frame, orient="horizontal", command=self.text.xview)
        self.text.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set, state="disabled")
        self.text.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        text_frame.rowconfigure(0, weight=1)
        text_frame.columnconfigure(0, weight=1)

        buttons = ttk.Frame(body)
        buttons.pack(fill="x", pady=(10, 0))
        ttk.Button(buttons, text=self.tr("Close"), command=self.destroy).pack(side="right", padx=(8, 0))
        self.save_button = ttk.Button(buttons, text=self.tr("Save"), command=self.save, style="Accent.TButton", state="disabled")
        self.save_button.pack(side="right")

    def set_content(self, message: str, content: str = "", editable: bool = False) -> None:
        self.message_var.set(message)
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        if content:
            self.text.insert("1.0", content)
        self.text.edit_reset()
        self.text.configure(state="normal" if editable else "disabled")
        self.save_button.configure(state="normal" if editable else "disabled")

    def save(self) -> None:
        content = self.text.get("1.0", "end-1c")
        self.parent_page.save_file_content(self.path, content, self)

    def mark_saved(self) -> None:
        self.message_var.set(self.tr("Saved."))
        self.text.edit_modified(False)


class FileManagerPage(ttk.Frame):
    def __init__(self, parent: tk.Widget, app) -> None:
        super().__init__(parent, style="Page.TFrame", padding=18)
        self.app = app
        self.current_folder = str(Path.home())
        self.folder_history = [self.current_folder]
        self.folder_history_index = 0
        self.rows: list[dict] = []
        self.sort_column = "name"
        self.sort_reverse = False
        self.selected_action_buttons: list[ttk.Button] = []
        self.paste_button: ttk.Button | None = None
        self.clipboard_path = ""
        self.clipboard_mode = ""
        self.path_warning_var = tk.StringVar(value="")
        self.folder_summary_var = tk.StringVar(value="")
        self.selection_summary_var = tk.StringVar(value=self.app.tr("No item selected."))
        self._build()

    def _build(self) -> None:
        summary = ttk.Frame(self, style="Card.TFrame", padding=12)
        summary.pack(fill="x", pady=(0, 12))
        summary.columnconfigure(2, weight=1)
        tk.Label(summary, text="🗂", bg="#ffffff", fg="#1d4ed8", font=("DejaVu Sans", 24)).grid(row=0, column=0, rowspan=2, sticky="nw", padx=(4, 12))
        ttk.Label(summary, text=self.app.tr("Current folder:"), style="CardTitle.TLabel").grid(row=0, column=1, sticky="w")
        folder_row = ttk.Frame(summary, style="Card.TFrame")
        folder_row.grid(row=0, column=2, sticky="ew", padx=(8, 0))
        folder_row.columnconfigure(4, weight=1)
        self.back_folder_button = ttk.Button(folder_row, text=f"←  {self.app.tr('Back')}", command=self.go_back_folder, state="disabled")
        self.back_folder_button.grid(row=0, column=0, sticky="w")
        self.forward_folder_button = ttk.Button(folder_row, text=f"→  {self.app.tr('Forward')}", command=self.go_forward_folder, state="disabled")
        self.forward_folder_button.grid(row=0, column=1, sticky="w", padx=(6, 0))
        ttk.Button(folder_row, text=f"📁  {self.app.tr('Choose Folder')}", command=self.choose_folder).grid(row=0, column=2, sticky="w", padx=(6, 0))
        ttk.Label(folder_row, textvariable=self.folder_summary_var, style="Section.TLabel").grid(row=0, column=3, sticky="w", padx=(14, 8))
        self.folder_var = tk.StringVar(value=self.current_folder)
        path_entry = ttk.Entry(folder_row, textvariable=self.folder_var)
        path_entry.grid(row=0, column=4, sticky="ew")
        path_entry.bind("<Return>", lambda _event: self.go_to_typed_folder())
        ttk.Button(folder_row, text=self.app.tr("Go To"), command=self.go_to_typed_folder).grid(row=0, column=5, sticky="w", padx=(8, 0))
        ttk.Button(folder_row, text=f"↑  {self.app.tr('Up')}", command=self.go_up_folder).grid(row=0, column=6, sticky="w", padx=(8, 0))
        ttk.Button(folder_row, text=f"⟳  {self.app.tr('Refresh')}", command=self.refresh_folder).grid(row=0, column=7, sticky="w", padx=(8, 0))
        ttk.Label(summary, text=self.app.tr("Selected item:"), style="CardTitle.TLabel").grid(row=1, column=1, sticky="w", pady=(6, 0))
        ttk.Label(summary, textvariable=self.selection_summary_var, style="Hint.TLabel").grid(row=1, column=2, sticky="w", padx=(8, 0), pady=(6, 0))
        ttk.Label(summary, textvariable=self.path_warning_var, foreground="#b91c1c").grid(row=2, column=1, columnspan=2, sticky="w", pady=(8, 0))

        self._build_actions()
        self._build_table()
        self.update_action_states()
        self._update_folder_summary()

    def _build_actions(self) -> None:
        actions_wrap = ttk.Frame(self, style="Card.TFrame", padding=12)
        actions_wrap.pack(fill="x", pady=(0, 12))
        self._section_title(actions_wrap, "⚙", self.app.tr("Actions")).pack(anchor="w")
        ttk.Label(
            actions_wrap,
            text=self.app.tr("Create new items on the left, work with the selected item in the middle, and search or archive on the right."),
            style="Hint.TLabel",
            wraplength=920,
            justify="left",
        ).pack(anchor="w", pady=(2, 8))

        actions = ttk.Frame(actions_wrap, style="Surface.TFrame")
        actions.pack(fill="x", pady=(0, 12))

        create_group = ttk.LabelFrame(actions, text=self.app.tr("Create"), padding=8)
        selected_group = ttk.LabelFrame(actions, text=self.app.tr("Selected item"), padding=8)
        search_group = ttk.LabelFrame(actions, text=self.app.tr("Find and archive"), padding=8)
        create_group.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        selected_group.grid(row=0, column=1, sticky="nsew", padx=8)
        search_group.grid(row=0, column=2, sticky="nsew", padx=(8, 0))

        self._button(create_group, f"📄  {self.app.tr('New File')}", self.create_file).grid(row=0, column=0, sticky="ew", padx=3, pady=3)
        self._button(create_group, f"📁  {self.app.tr('New Folder')}", self.create_folder).grid(row=0, column=1, sticky="ew", padx=3, pady=3)

        self._button(selected_group, f"✎  {self.app.tr('Edit')}", self.edit_file, needs_selection=True).grid(row=0, column=0, sticky="ew", padx=3, pady=3)
        self._button(selected_group, f"↧  {self.app.tr('Rename')}", self.rename_item, needs_selection=True).grid(row=0, column=1, sticky="ew", padx=3, pady=3)
        self._button(selected_group, f"⧉  {self.app.tr('Copy')}", self.copy_item, needs_selection=True).grid(row=0, column=2, sticky="ew", padx=3, pady=3)
        self._button(selected_group, f"✂  {self.app.tr('Cut')}", self.cut_item, needs_selection=True).grid(row=1, column=0, sticky="ew", padx=3, pady=3)
        self._button(selected_group, f"ⓘ  {self.app.tr('Details')}", self.details_item, needs_selection=True).grid(row=1, column=1, sticky="ew", padx=3, pady=3)
        self._button(selected_group, f"🛡  {self.app.tr('Change Permissions')}", self.permissions, needs_selection=True).grid(row=1, column=2, sticky="ew", padx=3, pady=3)
        self.paste_button = self._button(selected_group, f"📋  {self.app.tr('Paste')}", self.paste_item)
        self.paste_button.grid(row=2, column=0, sticky="ew", padx=3, pady=3)
        self._button(selected_group, f"🗑  {self.app.tr('Delete')}", self.delete_item, needs_selection=True, style="Danger.TButton").grid(
            row=2,
            column=1,
            columnspan=2,
            sticky="ew",
            padx=3,
            pady=(3, 0),
        )

        self._button(search_group, f"⌕  {self.app.tr('Search')}", self.search_items).grid(row=0, column=0, sticky="ew", padx=3, pady=3)
        self._button(search_group, f"🗜  {self.app.tr('Compress')}", self.compress_item, needs_selection=True).grid(row=0, column=1, sticky="ew", padx=3, pady=3)
        self._button(search_group, f"📤  {self.app.tr('Extract')}", self.extract_item, needs_selection=True).grid(row=1, column=1, sticky="ew", padx=3, pady=3)

        for group in [create_group, selected_group, search_group]:
            for column in range(3):
                group.columnconfigure(column, weight=1)
        for column in range(3):
            actions.columnconfigure(column, weight=1)

    def _button(self, parent: tk.Widget, text: str, command, needs_selection: bool = False, style: str | None = None) -> ttk.Button:
        options = {"style": style} if style else {}
        button = ttk.Button(parent, text=text, command=command, **options)
        if needs_selection:
            self.selected_action_buttons.append(button)
        return button

    def _build_table(self) -> None:
        table_wrap = ttk.Frame(self, style="Card.TFrame", padding=12)
        table_wrap.pack(fill="both", expand=True)
        self._section_title(table_wrap, "🗂", self.app.tr("Folder contents")).pack(anchor="w")
        ttk.Label(
            table_wrap,
            text=self.app.tr("Select a row to enable item actions. Double-click a folder to open it or a file to preview it."),
            style="Hint.TLabel",
            wraplength=920,
            justify="left",
        ).pack(anchor="w", pady=(2, 10))

        table_frame = ttk.Frame(table_wrap, style="Card.TFrame")
        table_frame.pack(fill="both", expand=True)
        columns = ("name", "type", "size", "permissions", "modified", "path")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings")
        headings = {
            "name": self.app.tr("Name"),
            "type": self.app.tr("Type"),
            "size": self.app.tr("Size"),
            "permissions": self.app.tr("Permission"),
            "modified": self.app.tr("Modified"),
            "path": self.app.tr("Path"),
        }
        widths = {"name": 180, "type": 80, "size": 130, "permissions": 100, "modified": 150, "path": 360}
        for column in columns:
            self.tree.heading(column, text=headings[column], command=lambda name=column: self.sort_by_column(name))
            self.tree.column(column, width=widths[column], anchor="w")
        self.column_headings = headings
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self.update_action_states())
        self.tree.bind("<Double-1>", self.open_selected_item)
        yscroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        xscroll = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

    def _section_title(self, parent: tk.Widget, icon: str, text: str) -> ttk.Frame:
        frame = ttk.Frame(parent, style="Surface.TFrame")
        ttk.Label(frame, text=icon, style="Section.TLabel").pack(side="left")
        ttk.Label(frame, text=text, style="Section.TLabel").pack(side="left", padx=(6, 0))
        return frame

    def on_show(self) -> None:
        if not self.tree.get_children():
            self.refresh_folder()
        self.app.set_status(self.app.tr("Files & Folders is open. Current folder: {path}", path=self.current_folder))

    def go_to_folder(self, folder: str, remember: bool = True) -> None:
        folder = str(Path(folder).expanduser())
        if remember:
            self.remember_folder(folder)
        self.folder_var.set(folder)
        self.refresh_folder()

    def go_to_typed_folder(self) -> None:
        folder = self.folder_var.get().strip()
        if self.validate_path(folder, must_exist=True) and Path(folder).is_dir():
            self.go_to_folder(folder)
            return
            messagebox.showwarning(self.app.tr("Choose a folder"), self.app.tr("Enter a folder path, then choose Go To."), parent=self)

    def remember_folder(self, folder: str) -> None:
        if self.folder_history and self.folder_history[self.folder_history_index] == folder:
            self.update_navigation_buttons()
            return
        self.folder_history = self.folder_history[: self.folder_history_index + 1]
        self.folder_history.append(folder)
        self.folder_history_index = len(self.folder_history) - 1
        self.update_navigation_buttons()

    def go_back_folder(self) -> None:
        if self.folder_history_index <= 0:
            return
        self.folder_history_index -= 1
        self.go_to_folder(self.folder_history[self.folder_history_index], remember=False)

    def go_forward_folder(self) -> None:
        if self.folder_history_index >= len(self.folder_history) - 1:
            return
        self.folder_history_index += 1
        self.go_to_folder(self.folder_history[self.folder_history_index], remember=False)

    def go_up_folder(self) -> None:
        current = Path(self.folder_var.get().strip() or self.current_folder).expanduser()
        parent = current.parent
        if str(parent) == str(current):
            self.app.set_status(self.app.tr("Already at the top folder."))
            return
        self.go_to_folder(str(parent))

    def update_navigation_buttons(self) -> None:
        self.back_folder_button.configure(state="normal" if self.folder_history_index > 0 else "disabled")
        self.forward_folder_button.configure(state="normal" if self.folder_history_index < len(self.folder_history) - 1 else "disabled")

    def choose_folder(self) -> None:
        folder = filedialog.askdirectory(parent=self, initialdir=self.folder_var.get() or str(Path.home()))
        if folder:
            self.go_to_folder(folder)

    def selected_path(self) -> str:
        item = self.tree.focus()
        if not item:
            return ""
        values = self.tree.item(item, "values")
        return values[5] if len(values) > 5 else ""

    def selected_type(self) -> str:
        item = self.tree.focus()
        if not item:
            return ""
        values = self.tree.item(item, "values")
        return values[1] if len(values) > 1 else ""

    def require_selected_path(self) -> str:
        selected = self.selected_path()
        if not selected:
            messagebox.showwarning(self.app.tr("No item selected"), self.app.tr("Choose a file or folder from the table first."), parent=self)
        return selected

    def selected_row(self) -> dict | None:
        selected = self.selected_path()
        if not selected:
            return None
        return next((row for row in self.rows if row.get("path") == selected), None)

    def update_action_states(self) -> None:
        selected = self.selected_path()
        state = "normal" if selected else "disabled"
        for button in self.selected_action_buttons:
            button.configure(state=state)
        if self.paste_button:
            self.paste_button.configure(state="normal" if self.clipboard_path else "disabled")
        if selected:
            icon = "📁" if self.selected_type() == "folder" else "📄"
            self.selection_summary_var.set(f"{icon}  {Path(selected).name or selected}")
        else:
            self.selection_summary_var.set(self.app.tr("No item selected. Choose a file or folder from the table to enable item actions."))

    def open_selected_item(self, _event=None) -> None:
        selected = self.selected_path()
        if not selected:
            return
        if not self.validate_path(selected, must_exist=True):
            return
        path = Path(selected)
        item_type = self.selected_type()
        if path.is_dir() or item_type == "folder":
            self.go_to_folder(selected)
            return
        if path.is_file() or item_type == "file":
            self.preview_file(selected)
            return
        messagebox.showinfo(self.app.tr("Preview unavailable"), self.app.tr("This item type cannot be opened here."), parent=self)

    def preview_file(self, path: str) -> None:
        preview = FilePreviewWindow(self, path)
        self.app.set_status(self.app.tr("Opening preview: {path}", path=path))

        def worker() -> None:
            message, content = self.load_preview_content(path)
            self.after(0, lambda: self.show_preview_content(preview, path, message, content))

        threading.Thread(target=worker, daemon=True).start()

    def load_preview_content(self, path: str) -> tuple[str, str]:
        try:
            file_path = Path(path)
            size = file_path.stat().st_size
            with file_path.open("rb") as handle:
                data = handle.read(MAX_PREVIEW_BYTES + 1)
        except PermissionError:
            return self.app.tr("You do not have permission to preview this file."), ""
        except FileNotFoundError:
            return self.app.tr("This file no longer exists. Refresh and try again."), ""
        except OSError as exc:
            return self.app.tr("Unable to preview this file: {error}", error=str(exc)), ""

        truncated = len(data) > MAX_PREVIEW_BYTES
        data = data[:MAX_PREVIEW_BYTES]
        if b"\x00" in data:
            return self.app.tr("Preview is not available for this binary file. Size: {size}.", size=format_size(size)), ""
        try:
            content = data.decode("utf-8")
        except UnicodeDecodeError:
            try:
                content = data.decode("latin-1")
            except UnicodeDecodeError:
                return self.app.tr("Preview is not available for this file encoding. Size: {size}.", size=format_size(size)), ""

        message = self.app.tr("Showing text preview. Size: {size}.", size=format_size(size))
        if truncated:
            message = self.app.tr("Showing the first {preview_size} of this file. Full size: {size}.", preview_size=format_size(MAX_PREVIEW_BYTES), size=format_size(size))
        return message, content

    def show_preview_content(self, preview: FilePreviewWindow, path: str, message: str, content: str) -> None:
        if preview.winfo_exists():
            preview.set_content(message, content)
        self.app.set_status(self.app.tr("Preview opened: {path}", path=path))

    def edit_file(self) -> None:
        selected = self.require_selected_path()
        if not selected or not self.validate_path(selected, must_exist=True):
            return
        if self.selected_type() != "file" or not Path(selected).is_file():
            messagebox.showwarning(self.app.tr("Choose a file"), self.app.tr("Choose a regular file to edit."), parent=self)
            return

        editor = FileEditWindow(self, selected)
        self.app.set_status(self.app.tr("Opening editor: {path}", path=selected))

        def worker() -> None:
            message, content, editable = self.load_edit_content(selected)
            self.after(0, lambda: self.show_edit_content(editor, selected, message, content, editable))

        threading.Thread(target=worker, daemon=True).start()

    def load_edit_content(self, path: str) -> tuple[str, str, bool]:
        try:
            file_path = Path(path)
            size = file_path.stat().st_size
            with file_path.open("rb") as handle:
                data = handle.read(MAX_PREVIEW_BYTES + 1)
        except PermissionError:
            return self.app.tr("You do not have permission to edit this file."), "", False
        except FileNotFoundError:
            return self.app.tr("This file no longer exists. Refresh and try again."), "", False
        except OSError as exc:
            return self.app.tr("Unable to edit this file: {error}", error=str(exc)), "", False

        if len(data) > MAX_PREVIEW_BYTES:
            return self.app.tr("This file is too large to edit here. Size: {size}.", size=format_size(size)), "", False
        if b"\x00" in data:
            return self.app.tr("Binary files cannot be edited here. Size: {size}.", size=format_size(size)), "", False
        try:
            content = data.decode("utf-8")
        except UnicodeDecodeError:
            try:
                content = data.decode("latin-1")
            except UnicodeDecodeError:
                return self.app.tr("This file encoding cannot be edited here. Size: {size}.", size=format_size(size)), "", False
        return self.app.tr("Editing text file. Size: {size}.", size=format_size(size)), content, True

    def show_edit_content(self, editor: FileEditWindow, path: str, message: str, content: str, editable: bool) -> None:
        if editor.winfo_exists():
            editor.set_content(message, content, editable)
        self.app.set_status(self.app.tr("Editor opened: {path}", path=path))

    def save_file_content(self, path: str, content: str, editor: FileEditWindow) -> None:
        if not self.validate_path(path, must_exist=True) or not Path(path).is_file():
            return
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="", delete=False, dir="/tmp") as handle:
                handle.write(content)
                temp_path = handle.name
        except OSError as exc:
            messagebox.showerror(self.app.tr("Save failed"), self.app.tr("Unable to prepare file content: {error}", error=str(exc)), parent=self)
            return

        def finish(_result: ShellResult) -> None:
            editor.mark_saved()
            self.refresh_folder(show_progress=False)

        self.run_action(self.app.tr("Save File"), "save_file_from_temp", [temp_path, path], on_success=finish)

    def update_path_warning(self) -> None:
        folder = self.folder_var.get().strip()
        if folder and is_inside_protected_area(folder):
            self.path_warning_var.set(self.app.tr("System location: some actions may be blocked to protect Ubuntu."))
        else:
            self.path_warning_var.set("")

    def validate_path(self, path: str, must_exist: bool = False) -> bool:
        if not path:
            messagebox.showwarning(self.app.tr("Missing path"), self.app.tr("Enter or choose a file or folder path."), parent=self)
            return False
        if "\n" in path or "\r" in path:
            messagebox.showwarning(self.app.tr("Invalid path"), self.app.tr("Paths must be a single line."), parent=self)
            return False
        if must_exist and not Path(path).exists():
            messagebox.showwarning(self.app.tr("Missing item"), self.app.tr("The selected file or folder no longer exists. Refresh and try again."), parent=self)
            return False
        return True

    def validate_destination(self, path: str, label: str, must_not_exist: bool = True, folder_destination: bool = False) -> bool:
        if not self.validate_path(path):
            return False
        target = Path(path)
        if target.name in {"", ".", ".."}:
            messagebox.showwarning(self.app.tr("Invalid name"), self.app.tr("Choose a valid {label}.", label=label.lower()), parent=self)
            return False
        if folder_destination and target.exists() and not target.is_dir():
            messagebox.showwarning(self.app.tr("Invalid folder"), self.app.tr("Choose a folder, not a file."), parent=self)
            return False
        parent = target if folder_destination and target.exists() else target.parent
        if not parent.exists():
            messagebox.showwarning(self.app.tr("Missing folder"), self.app.tr("The destination folder does not exist."), parent=self)
            return False
        if must_not_exist and target.exists():
            messagebox.showwarning(self.app.tr("Already exists"), self.app.tr("A file or folder already exists there. Choose a different name."), parent=self)
            return False
        return True

    def destination_from_name(self, name: str, label: str) -> str:
        clean_name = name.strip()
        if not clean_name or clean_name in {".", ".."} or "/" in clean_name:
            messagebox.showwarning(self.app.tr("Invalid name"), self.app.tr("Choose a valid {label}.", label=label.lower()), parent=self)
            return ""
        folder = self.folder_var.get().strip() or self.current_folder
        if not self.validate_path(folder, must_exist=True) or not Path(folder).is_dir():
            messagebox.showwarning(self.app.tr("Choose a folder"), self.app.tr("The current path must be a folder."), parent=self)
            return ""
        return str(Path(folder) / clean_name)

    def run_action(
        self,
        title: str,
        action: str,
        args: list[str],
        on_success=None,
        require_root: bool = False,
        show_success: bool = True,
        show_output: bool = True,
    ) -> None:
        progress = ProgressDialog(self, title, self.app.tr("Working on your request..."))

        def done(result: ShellResult) -> None:
            self.after(0, lambda: self._finish_action(progress, title, action, result, on_success, show_success, show_output))

        run_shell_async("file_manager.sh", action, args, require_root, done)

    def _finish_action(self, progress: ProgressDialog, title: str, action: str, result: ShellResult, on_success, show_success: bool, show_output: bool) -> None:
        progress.finish(result.success, result.stdout, result.stderr, show_output=show_output)
        if result.success:
            if on_success:
                on_success(result)
            else:
                self.refresh_folder(show_progress=False)
            if action == "browse_folder":
                self.app.set_status(self.app.tr("Current folder: {path}", path=self.current_folder))
            elif action == "search_files":
                self.app.set_status(self.app.tr("Search results are shown."))
            else:
                self.app.set_status(result.stdout.strip() or self.app.tr("Action completed."))
            if show_success and action not in {"browse_folder", "search_files", "get_stat"}:
                show_info(self, title, result.stdout)
        else:
            self.app.set_status(self.app.tr("Action failed. No changes were made."))
            show_error(self, title, result.stderr)

    def refresh_folder(self, show_progress: bool = False) -> None:
        folder = self.folder_var.get().strip()
        if not self.validate_path(folder, must_exist=True):
            return
        if not Path(folder).is_dir():
            messagebox.showwarning(self.app.tr("Choose a folder"), self.app.tr("The current path must be a folder."), parent=self)
            return
        self.current_folder = folder
        self.update_path_warning()
        self.update_navigation_buttons()
        self._update_folder_summary()
        self.app.set_status(self.app.tr("Loading folder: {path}", path=folder))

        def update(result: ShellResult) -> None:
            if not result.success:
                self.app.set_status(self.app.tr("Could not load the folder."))
                show_error(self, self.app.tr("Browse Folder"), result.stderr)
                return
            rows = parse_json_output(result.stdout, [])
            self.populate(rows)
            self._update_folder_summary()
            self.app.set_status(self.app.tr("Current folder: {path}", path=self.current_folder))

        if show_progress:
            self.run_action("Browse Folder", "browse_folder", [folder], update, show_success=False, show_output=False)
        else:
            run_shell_async("file_manager.sh", "browse_folder", [folder], False, lambda result: self.after(0, lambda: update(result)))

    def populate(self, rows: list[dict], keep_sort: bool = True) -> None:
        self.rows = list(rows)
        if keep_sort:
            self.rows = self.sorted_rows(self.rows)
        self.render_rows()

    def render_rows(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for row in self.rows:
            item_type = row.get("type", "")
            icon = "📁" if item_type == "folder" else "📄" if item_type == "file" else "•"
            self.tree.insert(
                "",
                "end",
                values=(
                    f"{icon}  {row.get('name', '')}",
                    item_type,
                    format_size(row.get("size", "")),
                    row.get("permissions", ""),
                    row.get("modified", ""),
                    row.get("path", ""),
                ),
            )
        self.update_column_headings()
        self.update_action_states()
        self._update_folder_summary()

    def _update_folder_summary(self) -> None:
        count = len(self.rows)
        self.folder_summary_var.set(self.current_folder)
        self.selection_summary_var.set(
            self.selection_summary_var.get()
            if self.selected_path()
            else self.app.tr("Showing {count} items. Choose a file or folder to enable item actions.", count=count)
        )

    def sort_by_column(self, column: str) -> None:
        if self.sort_column == column:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_column = column
            self.sort_reverse = False
        self.rows = self.sorted_rows(self.rows)
        self.render_rows()

    def sorted_rows(self, rows: list[dict]) -> list[dict]:
        return sorted(rows, key=lambda row: self.sort_key(row, self.sort_column), reverse=self.sort_reverse)

    def sort_key(self, row: dict, column: str):
        if column == "size":
            try:
                return int(row.get("size", 0))
            except (TypeError, ValueError):
                return 0
        if column == "modified":
            return str(row.get("modified", ""))
        return str(row.get(column, "")).casefold()

    def update_column_headings(self) -> None:
        for column, label in self.column_headings.items():
            indicator = ""
            if column == self.sort_column:
                indicator = " ↓" if self.sort_reverse else " ↑"
            self.tree.heading(column, text=f"{label}{indicator}", command=lambda name=column: self.sort_by_column(name))

    def create_file(self) -> None:
        values = ask_form(
            self,
            self.app.tr("Create New File"),
            [{"key": "name", "label": self.app.tr("New file name"), "value": "new-file.txt"}],
        )
        if values:
            path = self.destination_from_name(values["name"], "file name")
            if path and self.validate_destination(path, "file name"):
                self.run_action(self.app.tr("Create New File"), "create_file", [path])

    def create_folder(self) -> None:
        values = ask_form(
            self,
            self.app.tr("Create New Folder"),
            [{"key": "name", "label": self.app.tr("New folder name"), "value": self.app.tr("New Folder")}],
        )
        if values:
            path = self.destination_from_name(values["name"], "folder name")
            if path and self.validate_destination(path, "folder name"):
                self.run_action(self.app.tr("Create New Folder"), "create_dir", [path])

    def delete_item(self) -> None:
        selected = self.require_selected_path()
        if not selected or not self.validate_path(selected, must_exist=True):
            return
        if is_protected_path(selected):
            messagebox.showerror(self.app.tr("Protected system folder"), self.app.tr("This Ubuntu system folder cannot be deleted."), parent=self)
            return

        path_obj = Path(selected)
        non_empty_folder = False
        if path_obj.is_dir():
            try:
                non_empty_folder = any(path_obj.iterdir())
            except PermissionError:
                non_empty_folder = True

        message = f"{self.app.tr('Are you sure you want to move this item to Trash?')}\n\n{selected}"
        if non_empty_folder:
            message += f"\n\n{self.app.tr('This folder contains files. Moving it to Trash will include everything inside it.')}"
        if is_inside_protected_area(selected):
            message += f"\n\n{self.app.tr('This is inside a system location. The app may block the action to protect Ubuntu.')}"
        if messagebox.askyesno(self.app.tr("Delete Confirmation"), message, parent=self):
            self.run_action(self.app.tr("Delete"), "delete_path", [selected])

    def rename_item(self) -> None:
        selected = self.require_selected_path()
        if not selected:
            return
        values = ask_form(
            self,
            self.app.tr("Rename Item"),
            [
                {"key": "old", "label": self.app.tr("Current path"), "value": selected},
                {"key": "new", "label": self.app.tr("New path"), "value": selected},
            ],
        )
        if values and self.validate_path(values["old"], True) and self.validate_destination(values["new"], "new path"):
            self.run_action(self.app.tr("Rename Item"), "rename_path", [values["old"], values["new"]])

    def copy_item(self) -> None:
        selected = self.require_selected_path()
        if not selected:
            return
        if not self.validate_path(selected, True):
            return
        self.clipboard_path = selected
        self.clipboard_mode = "copy"
        self.update_action_states()
        self.app.set_status(self.app.tr("Copied to clipboard: {path}", path=selected))

    def cut_item(self) -> None:
        selected = self.require_selected_path()
        if not selected:
            return
        if not self.validate_path(selected, True):
            return
        self.clipboard_path = selected
        self.clipboard_mode = "cut"
        self.update_action_states()
        self.app.set_status(self.app.tr("Ready to move: {path}", path=selected))

    def paste_item(self) -> None:
        if not self.clipboard_path or self.clipboard_mode not in {"copy", "cut"}:
            messagebox.showwarning(self.app.tr("Clipboard is empty"), self.app.tr("Choose Copy or Cut on a file or folder first."), parent=self)
            return
        if not self.validate_path(self.clipboard_path, True):
            self.clipboard_path = ""
            self.clipboard_mode = ""
            self.update_action_states()
            return
        destination_folder = self.paste_destination_folder()
        if not self.validate_destination(destination_folder, "destination folder", must_not_exist=False, folder_destination=True):
            return
        default = os.path.join(destination_folder, Path(self.clipboard_path).name)
        values = ask_form(
            self,
            self.app.tr("Paste Item"),
            [
                {"key": "src", "label": self.app.tr("Paste from"), "value": self.clipboard_path},
                {"key": "dest", "label": self.app.tr("Paste to"), "value": default},
            ],
        )
        if not values or not self.validate_path(values["src"], True) or not self.validate_destination(values["dest"], "paste destination"):
            return
        same_path = canonical(values["src"]) == canonical(values["dest"])
        if same_path:
            messagebox.showwarning(self.app.tr("Already exists"), self.app.tr("A file or folder already exists there. Choose a different name."), parent=self)
            return
        if self.clipboard_mode == "cut":
            if not messagebox.askyesno(
                self.app.tr("Move Confirmation"),
                f"{self.app.tr('Move this item?')}\n\n{values['src']}\n\n{self.app.tr('to')}\n\n{values['dest']}",
                parent=self,
            ):
                return
            self.run_action(
                self.app.tr("Paste Item"),
                "move_path",
                [values["src"], values["dest"]],
                on_success=lambda result: self._finish_paste(result, clear_clipboard=True),
            )
            return
        self.run_action(
            self.app.tr("Paste Item"),
            "copy_path",
            [values["src"], values["dest"]],
            on_success=lambda result: self._finish_paste(result, clear_clipboard=False),
        )

    def paste_destination_folder(self) -> str:
        selected = self.selected_path()
        selected_type = self.selected_type()
        if selected and selected_type == "folder":
            return selected
        return self.folder_var.get().strip() or self.current_folder

    def _finish_paste(self, result: ShellResult, clear_clipboard: bool) -> None:
        if clear_clipboard:
            self.clipboard_path = ""
            self.clipboard_mode = ""
        self.refresh_folder(show_progress=False)
        self.update_action_states()

    def search_items(self) -> None:
        values = ask_form(
            self,
            self.app.tr("Search Files and Folders"),
            [
                {"key": "base", "label": self.app.tr("Search in"), "value": self.folder_var.get()},
                {"key": "query", "label": self.app.tr("Name contains"), "value": ""},
                {"key": "type", "label": self.app.tr("Look for"), "choices": [self.app.tr("All items"), self.app.tr("Files only"), self.app.tr("Folders only")], "value": self.app.tr("All items")},
            ],
        )
        type_map = {self.app.tr("All items"): "all", self.app.tr("Files only"): "file", self.app.tr("Folders only"): "folder"}
        if values and self.validate_path(values["base"], True) and values["query"]:
            self.run_action(
                self.app.tr("Search"),
                "search_files",
                [values["base"], values["query"], type_map.get(values["type"], "all")],
                lambda result: self.populate(parse_json_output(result.stdout, [])),
                show_success=False,
                show_output=False,
            )

    def details_item(self) -> None:
        selected = self.require_selected_path()
        if selected and self.validate_path(selected, True):
            self.run_action(self.app.tr("Item Details"), "get_stat", [selected], self.show_details, show_success=False, show_output=False)

    def show_details(self, result: ShellResult) -> None:
        data = parse_json_output(result.stdout, {})
        details = (
            f"{self.app.tr('Name')}: {data.get('name', '')}\n"
            f"{self.app.tr('Type')}: {data.get('type', '')}\n"
            f"{self.app.tr('Size')}: {format_size(data.get('size', ''))}\n"
            f"{self.app.tr('Permission')}: {data.get('permissions', '')}\n"
            f"{self.app.tr('Owner')}: {data.get('owner', '')}\n"
            f"{self.app.tr('Group')}: {data.get('group', '')}\n"
            f"{self.app.tr('Modified')}: {data.get('modified', '')}\n\n"
            f"{self.app.tr('Path')}:\n{data.get('path', '')}"
        )
        show_info(self, self.app.tr("Item Details"), details)

    def permissions(self) -> None:
        selected = self.require_selected_path()
        if not selected:
            return
        selected_row = self.selected_row() or {}
        values = ask_permission_form(self, self.app.tr("Change Permissions"), selected, str(selected_row.get("permissions", "")))
        if not values:
            return
        if not re.fullmatch(r"[0-7]{3,4}", values["mode"]):
            messagebox.showwarning(self.app.tr("Invalid permissions"), self.app.tr("Use 3 or 4 digits from 0 to 7, for example 755."), parent=self)
            return
        if self.validate_path(values["path"], True):
            current_permission = str(selected_row.get("permissions", "")).strip()
            permission_summary = f"{self.app.tr('New permission')}: {values['mode']}"
            if current_permission:
                permission_summary = f"{self.app.tr('Current permission')}: {current_permission}\n{permission_summary}"
            if messagebox.askyesno(
                self.app.tr("Permission Confirmation"),
                f"{self.app.tr('Change permissions for this item?')}\n\n{values['path']}\n\n{permission_summary}",
                parent=self,
            ):
                self.run_action(self.app.tr("Change Permissions"), "chmod_path", [values["mode"], values["path"]])

    def compress_item(self) -> None:
        selected = self.require_selected_path()
        if not selected:
            return
        default_archive = f"{selected}.tar.gz"
        values = ask_form(
            self,
            self.app.tr("Compress Item"),
            [
                {"key": "src", "label": self.app.tr("File or folder"), "value": selected},
                {"key": "format", "label": self.app.tr("Archive type"), "choices": ["tar.gz", "zip"], "value": "tar.gz"},
                {"key": "dest", "label": self.app.tr("New archive path"), "value": default_archive},
            ],
        )
        if values and self.validate_path(values["src"], True) and self.validate_destination(values["dest"], "archive path"):
            action = "create_tar_gz" if values["format"] == "tar.gz" else "create_zip"
            self.run_action(self.app.tr("Compress Item"), action, [values["src"], values["dest"]])

    def extract_item(self) -> None:
        selected = self.require_selected_path()
        if not selected:
            return
        default_format = "zip" if selected.lower().endswith(".zip") else "tar.gz"
        values = ask_form(
            self,
            self.app.tr("Extract Archive"),
            [
                {"key": "archive", "label": self.app.tr("Archive file"), "value": selected},
                {"key": "format", "label": self.app.tr("Archive type"), "choices": ["tar.gz", "zip"], "value": default_format},
                {"key": "dest", "label": self.app.tr("Extract to folder"), "value": self.folder_var.get()},
            ],
        )
        if not values:
            return
        archive = values["archive"]
        archive_lower = archive.lower()
        expected_zip = values["format"] == "zip"
        if expected_zip and not archive_lower.endswith(".zip"):
            messagebox.showwarning(self.app.tr("Archive type mismatch"), self.app.tr("Choose ZIP only for files ending in .zip."), parent=self)
            return
        if not expected_zip and not (archive_lower.endswith(".tar.gz") or archive_lower.endswith(".tgz")):
            messagebox.showwarning(self.app.tr("Archive type mismatch"), self.app.tr("Choose tar.gz only for files ending in .tar.gz or .tgz."), parent=self)
            return
        if self.validate_path(archive, True) and self.validate_destination(values["dest"], "extract destination", must_not_exist=False, folder_destination=True):
            action = "extract_zip" if expected_zip else "extract_tar_gz"
            self.run_action(self.app.tr("Extract Archive"), action, [archive, values["dest"]])
