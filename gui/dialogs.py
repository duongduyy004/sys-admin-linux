import json
import re
import tkinter as tk
from tkinter import ttk, messagebox

from gui.i18n import tr


class ProgressDialog(tk.Toplevel):
    def __init__(self, parent: tk.Widget, title: str, message: str) -> None:
        super().__init__(parent)
        self.title(title)
        self.transient(parent)
        self.grab_set()
        self.resizable(True, True)
        self.geometry("560x330")
        self.protocol("WM_DELETE_WINDOW", lambda: None)

        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)
        self.message_var = tk.StringVar(value=message)
        ttk.Label(frame, textvariable=self.message_var, style="Subtitle.TLabel").pack(anchor="w")
        self.progress = ttk.Progressbar(frame, mode="indeterminate")
        self.progress.pack(fill="x", pady=(12, 10))
        self.progress.start(12)

        output_frame = ttk.Frame(frame)
        output_frame.pack(fill="both", expand=True)
        self.output = tk.Text(output_frame, height=10, wrap="word", state="disabled")
        scroll = ttk.Scrollbar(output_frame, orient="vertical", command=self.output.yview)
        self.output.configure(yscrollcommand=scroll.set)
        self.output.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        self.close_button = ttk.Button(frame, text=tr("Close"), command=self.destroy, state="disabled")
        self.close_button.pack(anchor="e", pady=(10, 0))

    def append(self, text: str) -> None:
        if not text:
            return
        self.output.configure(state="normal")
        self.output.insert("end", text)
        if not text.endswith("\n"):
            self.output.insert("end", "\n")
        self.output.see("end")
        self.output.configure(state="disabled")

    def finish(self, success: bool, stdout: str, stderr: str, show_output: bool = True) -> None:
        self.progress.stop()
        try:
            self.grab_release()
        except tk.TclError:
            pass
        try:
            self.destroy()
        except tk.TclError:
            pass


class SimpleFormDialog(tk.Toplevel):
    def __init__(self, parent: tk.Widget, title: str, fields: list[dict]) -> None:
        super().__init__(parent)
        self.title(title)
        self.transient(parent)
        self.grab_set()
        self.resizable(False, False)
        self.result: dict[str, str] | None = None
        self.entries: dict[str, tk.Widget] = {}

        body = ttk.Frame(self, padding=16)
        body.pack(fill="both", expand=True)

        row_index = 0
        for field in fields:
            label = field["label"]
            key = field["key"]
            value = field.get("value", "")
            choices = field.get("choices")
            ttk.Label(body, text=label).grid(row=row_index, column=0, sticky="w", padx=(0, 10), pady=6)
            if choices:
                var = tk.StringVar(value=value or choices[0])
                widget = ttk.Combobox(body, textvariable=var, values=choices, state="readonly", width=36)
                widget.var = var
            else:
                widget = ttk.Entry(body, width=40)
                widget.insert(0, value)
            widget.grid(row=row_index, column=1, sticky="ew", pady=6)
            self.entries[key] = widget
            row_index += 1
            if field.get("help"):
                ttk.Label(body, text=field["help"], style="Subtitle.TLabel").grid(row=row_index, column=1, sticky="w", pady=(0, 4))
                row_index += 1

        buttons = ttk.Frame(body)
        buttons.grid(row=row_index, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text=tr("Cancel"), command=self.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(buttons, text=tr("OK"), command=self._submit, style="Accent.TButton").pack(side="right")

        body.columnconfigure(1, weight=1)
        first_entry = next(iter(self.entries.values()), None)
        if first_entry is not None:
            first_entry.focus_set()
        self.bind("<Return>", lambda _event: self._submit())
        self.bind("<Escape>", lambda _event: self.destroy())

    def _submit(self) -> None:
        values: dict[str, str] = {}
        for key, widget in self.entries.items():
            if hasattr(widget, "var"):
                values[key] = widget.var.get().strip()
            else:
                values[key] = widget.get().strip()
        self.result = values
        self.destroy()


def ask_form(parent: tk.Widget, title: str, fields: list[dict]) -> dict[str, str] | None:
    dialog = SimpleFormDialog(parent, title, fields)
    parent.wait_window(dialog)
    return dialog.result


class PermissionFormDialog(tk.Toplevel):
    _ROLE_ORDER = ("owner", "group", "others")
    _BIT_ORDER = ("read", "write", "execute")
    _SYMBOLIC_INDEX = {
        ("owner", "read"): 0,
        ("owner", "write"): 1,
        ("owner", "execute"): 2,
        ("group", "read"): 3,
        ("group", "write"): 4,
        ("group", "execute"): 5,
        ("others", "read"): 6,
        ("others", "write"): 7,
        ("others", "execute"): 8,
    }
    _SPECIAL_EXECUTE_CHARS = {
        "owner": ("s", "S"),
        "group": ("s", "S"),
        "others": ("t", "T"),
    }
    _SPECIAL_ACTIVE_CHARS = {
        "owner": ("s",),
        "group": ("s",),
        "others": ("t",),
    }
    _SPECIAL_BITS = {"owner": 4, "group": 2, "others": 1}

    def __init__(self, parent: tk.Widget, title: str, path: str, current_permissions: str = "") -> None:
        super().__init__(parent)
        self.title(title)
        self.transient(parent)
        self.grab_set()
        self.resizable(False, False)
        self.result: dict[str, str] | None = None
        self.path = path
        self.mode_var = tk.StringVar()
        self.special_var = tk.StringVar(value="0")
        self.permission_vars: dict[tuple[str, str], tk.BooleanVar] = {}

        body = ttk.Frame(self, padding=16)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)

        ttk.Label(body, text=tr("File or folder")).grid(row=0, column=0, sticky="nw", padx=(0, 10), pady=(0, 6))
        ttk.Label(body, text=path, wraplength=420, style="Subtitle.TLabel").grid(row=0, column=1, sticky="w", pady=(0, 6))

        if current_permissions:
            ttk.Label(body, text=tr("Current permission")).grid(row=1, column=0, sticky="w", padx=(0, 10), pady=(0, 10))
            ttk.Label(body, text=current_permissions, style="Subtitle.TLabel").grid(row=1, column=1, sticky="w", pady=(0, 10))
            table_row = 2
        else:
            table_row = 1

        table = ttk.Frame(body)
        table.grid(row=table_row, column=0, columnspan=2, sticky="ew")
        ttk.Label(table, text="").grid(row=0, column=0, padx=(0, 12), pady=(0, 6))
        for column, bit in enumerate(self._BIT_ORDER, start=1):
            ttk.Label(table, text=tr(bit.title())).grid(row=0, column=column, padx=8, pady=(0, 6))

        for row_index, role in enumerate(self._ROLE_ORDER, start=1):
            ttk.Label(table, text=tr(role.title())).grid(row=row_index, column=0, sticky="w", padx=(0, 12), pady=4)
            for column, bit in enumerate(self._BIT_ORDER, start=1):
                var = tk.BooleanVar(value=False)
                var.trace_add("write", self._on_permission_change)
                self.permission_vars[(role, bit)] = var
                ttk.Checkbutton(table, variable=var).grid(row=row_index, column=column, padx=8, pady=4)

        ttk.Label(body, text=tr("Special bits")).grid(row=table_row + 1, column=0, sticky="w", padx=(0, 10), pady=(12, 6))
        special_box = ttk.Combobox(body, textvariable=self.special_var, values=[str(index) for index in range(8)], state="readonly", width=6)
        special_box.grid(row=table_row + 1, column=1, sticky="w", pady=(12, 6))
        self.special_var.trace_add("write", self._on_permission_change)

        ttk.Label(body, text=tr("0 = regular permissions, 4 = setuid, 2 = setgid, 1 = sticky."), style="Subtitle.TLabel", wraplength=420).grid(
            row=table_row + 2,
            column=1,
            sticky="w",
            pady=(0, 10),
        )

        ttk.Label(body, text=tr("Permission number")).grid(row=table_row + 3, column=0, sticky="w", padx=(0, 10), pady=(0, 6))
        ttk.Label(body, textvariable=self.mode_var, style="CardTitle.TLabel").grid(row=table_row + 3, column=1, sticky="w", pady=(0, 6))

        buttons = ttk.Frame(body)
        buttons.grid(row=table_row + 4, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text=tr("Cancel"), command=self.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(buttons, text=tr("Apply"), command=self._submit, style="Accent.TButton").pack(side="right")

        self._load_permissions(current_permissions)
        self._update_mode()
        self.bind("<Return>", lambda _event: self._submit())
        self.bind("<Escape>", lambda _event: self.destroy())

    def _load_permissions(self, current_permissions: str) -> None:
        mode = current_permissions.strip()
        if re.fullmatch(r"[0-7]{3,4}", mode):
            self._load_numeric_mode(mode)
            return

        symbolic = mode[-9:] if len(mode) >= 9 else ""
        if len(symbolic) != 9:
            self._load_numeric_mode("755")
            return

        special_digit = 0
        for role in self._ROLE_ORDER:
            for bit in ("read", "write"):
                index = self._SYMBOLIC_INDEX[(role, bit)]
                expected = bit[0]
                self.permission_vars[(role, bit)].set(symbolic[index] == expected)

            exec_index = self._SYMBOLIC_INDEX[(role, "execute")]
            exec_char = symbolic[exec_index]
            self.permission_vars[(role, "execute")].set(exec_char in ("x",) + self._SPECIAL_ACTIVE_CHARS[role])
            if exec_char in self._SPECIAL_EXECUTE_CHARS[role]:
                special_digit += self._SPECIAL_BITS[role]

        self.special_var.set(str(special_digit))

    def _load_numeric_mode(self, mode: str) -> None:
        digits = mode[-3:]
        special_digit = mode[:-3] or "0"
        for role, digit in zip(self._ROLE_ORDER, digits):
            number = int(digit)
            self.permission_vars[(role, "read")].set(bool(number & 4))
            self.permission_vars[(role, "write")].set(bool(number & 2))
            self.permission_vars[(role, "execute")].set(bool(number & 1))
        self.special_var.set(special_digit)

    def _on_permission_change(self, *_args) -> None:
        self._update_mode()

    def _update_mode(self) -> None:
        digits: list[str] = []
        for role in self._ROLE_ORDER:
            value = 0
            if self.permission_vars[(role, "read")].get():
                value += 4
            if self.permission_vars[(role, "write")].get():
                value += 2
            if self.permission_vars[(role, "execute")].get():
                value += 1
            digits.append(str(value))
        special = self.special_var.get().strip() or "0"
        self.mode_var.set(f"{special}{''.join(digits)}" if special != "0" else "".join(digits))

    def _submit(self) -> None:
        self.result = {"path": self.path, "mode": self.mode_var.get()}
        self.destroy()


def ask_permission_form(parent: tk.Widget, title: str, path: str, current_permissions: str = "") -> dict[str, str] | None:
    dialog = PermissionFormDialog(parent, title, path, current_permissions)
    parent.wait_window(dialog)
    return dialog.result


def _format_package_repository_error(raw: str) -> str | None:
    release_match = re.search(r"The repository '([^']+)' does not have a Release file\.", raw)
    missing_key_match = re.search(r"NO_PUBKEY\s+([A-F0-9]+)", raw)
    duplicate_matches = re.findall(r"configured multiple times in ([^ ]+) and ([^\s]+)", raw)

    if not (release_match or missing_key_match or duplicate_matches):
        return None

    lines = [tr("Ubuntu package refresh found repository problems:")]
    if release_match:
        lines.append(tr("Unsupported repository: {repo}", repo=release_match.group(1)))
        lines.append(tr("Disable or remove that repository before refreshing packages again."))
    if missing_key_match:
        lines.append(tr("Missing repository signing key: {key}", key=missing_key_match.group(1)))
        lines.append(tr("Install the missing key or remove that repository if you no longer use it."))
    if duplicate_matches:
        seen_pairs: set[tuple[str, str]] = set()
        for first, second in duplicate_matches:
            pair = tuple(sorted((first, second)))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            lines.append(tr("Duplicate package source entries: {first} and {second}", first=first, second=second))
        lines.append(tr("Keep only one source entry for each duplicate repository, then refresh again."))
    return "\n\n".join(lines)


def friendly_error_message(stderr: str) -> str:
    raw = (stderr or "").strip()
    lower = raw.lower()
    if not raw:
        return tr("The action could not be completed. Please try again.")
    package_repo_message = _format_package_repository_error(raw)
    if package_repo_message:
        return package_repo_message
    if "permission denied" in lower or "operation not permitted" in lower:
        return tr("You do not have permission to complete this action. Choose a folder you own or approve the Ubuntu permission prompt.")
    if "no such file or directory" in lower or "path does not exist" in lower:
        return tr("The selected file or folder no longer exists. Refresh the list and try again.")
    if "already exists" in lower or "destination exists" in lower:
        return tr("A file or folder already exists at the destination. Choose a different name or location.")
    if "protected system path" in lower or "refusing to delete" in lower:
        return tr("That system folder is protected, so nothing was deleted.")
    if "required command is not available" in lower or "command not found" in lower:
        return tr("A required system tool is missing. Install the missing dependency, then try again.")
    if "unsupported archive" in lower or "not a zip file" in lower or "gzip" in lower:
        return tr("The archive could not be opened. Check that the file type matches the selected archive format.")
    if "cancelled" in lower or "canceled" in lower or "dismissed" in lower:
        return tr("The action was cancelled. No changes were made.")
    if "cannot contain new lines" in lower:
        return tr("This field cannot contain multiple lines. Please enter a single-line value.")
    if "trash is not available" in lower:
        return tr("Trash is not available on this system, so nothing was deleted.")
    if "must be a number" in lower or "must be between" in lower:
        return raw
    return f"{tr('The action could not be completed.')}\n\n{tr('Details')}: {raw}"


def show_error(parent: tk.Widget, title: str, stderr: str) -> None:
    message = friendly_error_message(stderr)
    messagebox.showerror(title, message, parent=parent)


def show_info(parent: tk.Widget, title: str, stdout: str) -> None:
    messagebox.showinfo(title, stdout.strip() or tr("Action completed."), parent=parent)


def parse_json_output(stdout: str, fallback):
    try:
        return json.loads(stdout or "")
    except json.JSONDecodeError:
        return fallback
