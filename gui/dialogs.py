import json
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


def friendly_error_message(stderr: str) -> str:
    raw = (stderr or "").strip()
    lower = raw.lower()
    if not raw:
        return tr("The action could not be completed. Please try again.")
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
