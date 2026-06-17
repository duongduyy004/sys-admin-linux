import re
import tkinter as tk
from tkinter import ttk, messagebox

from gui.dialogs import ProgressDialog, ask_form, parse_json_output, show_error, show_info
from gui.main_window import ShellResult, run_shell_async


class TimeSettingsPage(ttk.Frame):
    def __init__(self, parent: tk.Widget, app) -> None:
        super().__init__(parent, style="Page.TFrame", padding=18)
        self.app = app
        self.values: dict[str, tk.StringVar] = {}
        self._build()

    def _build(self) -> None:
        ttk.Label(self, text=self.app.tr("Date & Time"), style="Header.TLabel").pack(anchor="w")
        ttk.Label(self, text=self.app.tr("View time information and change timezone, sync, or manual time settings."), style="Subtitle.TLabel").pack(anchor="w", pady=(2, 14))

        info = ttk.Frame(self, style="Card.TFrame", padding=16)
        info.pack(fill="x", pady=(0, 12))
        fields = [("local_time", "Local Time"), ("date", "Date"), ("timezone", "Timezone"), ("time_sync", "Time Sync Status"), ("utc_time", "UTC Time")]
        for index, (key, label) in enumerate(fields):
            self.values[key] = tk.StringVar(value=self.app.tr("Loading..."))
            ttk.Label(info, text=self.app.tr(label), font=("DejaVu Sans", 10, "bold")).grid(row=index, column=0, sticky="w", pady=5, padx=(0, 18))
            ttk.Label(info, textvariable=self.values[key]).grid(row=index, column=1, sticky="w", pady=5)
        info.columnconfigure(1, weight=1)

        buttons = ttk.Frame(self)
        buttons.pack(fill="x")
        ttk.Button(buttons, text=self.app.tr("Refresh"), command=self.refresh).pack(side="left")
        ttk.Button(buttons, text=self.app.tr("Change Time Zone"), command=self.change_timezone).pack(side="left", padx=(8, 0))
        self.sync_button = ttk.Button(buttons, text=self.app.tr("Turn Automatic Time On"), command=self.toggle_sync)
        self.sync_button.pack(side="left", padx=(8, 0))
        ttk.Button(buttons, text=self.app.tr("Set Date and Time"), command=self.set_datetime).pack(side="left", padx=(8, 0))

    def on_show(self) -> None:
        self.refresh()

    def run_action(self, title: str, action: str, args: list[str], on_success=None, require_root: bool = False) -> None:
        progress = ProgressDialog(self, title, self.app.tr("Applying time settings..."))

        def done(result: ShellResult) -> None:
            self.after(0, lambda: self._finish(progress, title, action, result, on_success))

        run_shell_async("time_settings.sh", action, args, require_root, done)

    def _finish(self, progress: ProgressDialog, title: str, action: str, result: ShellResult, on_success) -> None:
        progress.finish(result.success, result.stdout, result.stderr)
        if result.success:
            if on_success:
                on_success(result)
            else:
                self.refresh()
            self.app.set_status(result.stdout.strip() or self.app.tr("Time settings updated."))
            if action != "get_info":
                show_info(self, title, result.stdout)
        else:
            self.app.set_status(self.app.tr("Time settings action failed."))
            show_error(self, title, result.stderr)

    def refresh(self) -> None:
        def update(result: ShellResult) -> None:
            if not result.success:
                show_error(self, self.app.tr("Refresh"), result.stderr)
                return
            data = parse_json_output(result.stdout, {})
            for key, var in self.values.items():
                value = str(data.get(key, "Unknown"))
                var.set(self.app.tr(value) if key == "time_sync" or value == "Unknown" else value)
            self.update_sync_button()
            self.app.set_status(self.app.tr("Date and time information refreshed."))

        run_shell_async("time_settings.sh", "get_info", [], False, lambda result: self.after(0, lambda: update(result)))

    def change_timezone(self) -> None:
        values = ask_form(self, self.app.tr("Change Time Zone"), [{"key": "timezone", "label": self.app.tr("Time zone"), "value": self.values["timezone"].get()}])
        if not values or not values["timezone"]:
            return
        if "\n" in values["timezone"] or "\r" in values["timezone"]:
            messagebox.showwarning(self.app.tr("Invalid time zone"), self.app.tr("Time zone must be a single line."), parent=self)
            return
        message = (
            f"{self.app.tr('Change the system time zone to this value?')}\n\n{values['timezone']}\n\n"
            f"{self.app.tr('Ubuntu may ask for your administrator password.')}"
        )
        if messagebox.askyesno(self.app.tr("Change Time Zone"), message, parent=self):
            self.run_action(self.app.tr("Change Time Zone"), "set_timezone", [values["timezone"]], require_root=True)

    def toggle_sync(self) -> None:
        current = self.values["time_sync"].get().lower()
        next_state = "off" if "enabled" in current or self.app.tr("enabled").lower() in current else "on"
        state_text = self.app.tr("off") if next_state == "off" else self.app.tr("on")
        message = (
            f"{self.app.tr('Turn automatic time {state}?', state=state_text)}\n\n"
            f"{self.app.tr('Ubuntu may ask for your administrator password.')}"
        )
        if messagebox.askyesno(self.app.tr("Automatic Time"), message, parent=self):
            self.run_action(self.app.tr("Automatic Time"), "toggle_ntp", [next_state], require_root=True)

    def set_datetime(self) -> None:
        current = self.values["local_time"].get()
        default_value = current[:19] if re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}.*", current) else ""
        values = ask_form(self, self.app.tr("Set Date and Time"), [{"key": "datetime", "label": self.app.tr("New date and time (YYYY-MM-DD HH:MM:SS)"), "value": default_value}])
        if not values:
            return
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", values["datetime"]):
            messagebox.showwarning(self.app.tr("Invalid format"), self.app.tr("Use YYYY-MM-DD HH:MM:SS."), parent=self)
            return
        message = (
            f"{self.app.tr('Set the system date and time to this value?')}\n\n{values['datetime']}\n\n"
            f"{self.app.tr('Changing system time can affect apps, files, and scheduled tasks. Ubuntu may ask for your administrator password.')}"
        )
        if messagebox.askyesno(self.app.tr("Set Date and Time"), message, parent=self):
            self.run_action(self.app.tr("Set Date and Time"), "set_datetime", [values["datetime"]], require_root=True)

    def update_sync_button(self) -> None:
        current = self.values["time_sync"].get().lower()
        if "enabled" in current or self.app.tr("enabled").lower() in current:
            self.sync_button.configure(text=self.app.tr("Turn Automatic Time Off"))
        else:
            self.sync_button.configure(text=self.app.tr("Turn Automatic Time On"))
