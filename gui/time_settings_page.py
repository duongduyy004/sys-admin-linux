import re
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Callable

from gui.dialogs import ProgressDialog, ask_form, parse_json_output, show_error, show_info
from gui.main_window import ShellResult, run_shell_async


def format_utc_offset(offset_seconds: float | int | None) -> str:
    if offset_seconds is None:
        return "UTC"
    total_minutes = int(offset_seconds // 60)
    sign = "+" if total_minutes >= 0 else "-"
    total_minutes = abs(total_minutes)
    hours, minutes = divmod(total_minutes, 60)
    return f"UTC {sign} {hours:02d}:{minutes:02d}"


def format_timezone_label(timezone_name: str) -> str:
    if not timezone_name or timezone_name == "Unknown":
        return timezone_name or "Unknown"
    try:
        offset = datetime.now(ZoneInfo(timezone_name)).utcoffset()
    except Exception:
        return timezone_name
    offset_label = format_utc_offset(offset.total_seconds() if offset is not None else None)
    return f"{timezone_name} ({offset_label})"


def timezone_offset_seconds(timezone_name: str) -> int | None:
    if not timezone_name or timezone_name == "Unknown":
        return None
    try:
        offset = datetime.now(ZoneInfo(timezone_name)).utcoffset()
    except Exception:
        return None
    if offset is None:
        return None
    return int(offset.total_seconds())


def timezone_sort_key(timezone_name: str) -> tuple[int, str]:
    offset_seconds = timezone_offset_seconds(timezone_name)
    offset_minutes = offset_seconds // 60 if offset_seconds is not None else 24 * 60
    return (int(offset_minutes), timezone_name.casefold())


class TimeSettingsPage(ttk.Frame):
    def __init__(self, parent: tk.Widget, app) -> None:
        super().__init__(parent, style="Page.TFrame", padding=18)
        self.app = app
        self.values: dict[str, tk.StringVar] = {}
        self.timezone_choices: list[str] = []
        self.current_timezone_id = "Unknown"
        self._clock_after_id: str | None = None
        self._build()
        self._schedule_live_clock()

    def _build(self) -> None:
        summary = ttk.Frame(self, style="Card.TFrame", padding=12)
        summary.pack(fill="x", pady=(0, 12))
        ttk.Label(summary, text=self.app.tr("Time overview"), style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(
            summary,
            text=self.app.tr("Refresh first if the clock looks stale, then use the actions below to change timezone, sync, or manual time."),
            style="Hint.TLabel",
            wraplength=920,
            justify="left",
        ).pack(anchor="w", pady=(4, 0))

        info = ttk.Frame(self, style="Card.TFrame", padding=16)
        info.pack(fill="x", pady=(0, 12))
        fields = [("local_time", "Local Time"), ("date", "Date"), ("timezone", "Timezone"), ("time_sync", "Time Sync Status"), ("utc_time", "UTC Time")]
        for index, (key, label) in enumerate(fields):
            self.values[key] = tk.StringVar(value=self.app.tr("Loading..."))
            ttk.Label(info, text=self.app.tr(label), font=("DejaVu Sans", 10, "bold")).grid(row=index, column=0, sticky="w", pady=5, padx=(0, 18))
            ttk.Label(info, textvariable=self.values[key]).grid(row=index, column=1, sticky="w", pady=5)
        info.columnconfigure(1, weight=1)

        buttons = ttk.Frame(self, style="Card.TFrame", padding=12)
        buttons.pack(fill="x")
        ttk.Label(buttons, text=self.app.tr("Actions"), style="CardTitle.TLabel").pack(anchor="w", pady=(0, 8))
        ttk.Button(buttons, text=self.app.tr("Refresh"), command=self.refresh).pack(side="left")
        ttk.Button(buttons, text=self.app.tr("Change Time Zone"), command=self.change_timezone).pack(side="left", padx=(8, 0))
        self.sync_button = ttk.Button(buttons, text=self.app.tr("Turn Automatic Time On"), command=self.toggle_sync)
        self.sync_button.pack(side="left", padx=(8, 0))
        ttk.Button(buttons, text=self.app.tr("Set Date and Time"), command=self.set_datetime).pack(side="left", padx=(8, 0))

    def on_show(self) -> None:
        self.refresh()
        self._schedule_live_clock()

    def destroy(self) -> None:
        self._cancel_live_clock()
        super().destroy()

    def run_action(self, title: str, action: str, args: list[str], on_success: Callable[[ShellResult], None] | None = None, require_root: bool = False) -> None:
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

    def refresh(self, status_message: str | None = None) -> None:
        def update(result: ShellResult) -> None:
            if not result.success:
                show_error(self, self.app.tr("Refresh"), result.stderr)
                return
            data = parse_json_output(result.stdout, {})
            for key, var in self.values.items():
                value = str(data.get(key, "Unknown"))
                if key == "timezone":
                    self.current_timezone_id = value
                    var.set(format_timezone_label(value))
                else:
                    var.set(self.app.tr(value) if key == "time_sync" or value == "Unknown" else value)
            self._apply_live_clock()
            self.update_sync_button()
            self.app.set_status(status_message or self.app.tr("Date and time information refreshed."))

        run_shell_async("time_settings.sh", "get_info", [], False, lambda result: self.after(0, lambda: update(result)))

    def _timezone_info(self) -> ZoneInfo | None:
        if not self.current_timezone_id or self.current_timezone_id == "Unknown":
            return None
        try:
            return ZoneInfo(self.current_timezone_id)
        except Exception:
            return None

    def _apply_live_clock(self) -> None:
        timezone = self._timezone_info()
        now_utc = datetime.now(ZoneInfo("UTC"))
        now_local = now_utc.astimezone(timezone) if timezone is not None else datetime.now().astimezone()
        self.values["local_time"].set(now_local.strftime("%Y-%m-%d %H:%M:%S %Z"))
        self.values["date"].set(now_local.strftime("%Y-%m-%d"))
        self.values["utc_time"].set(now_utc.strftime("%Y-%m-%d %H:%M:%S UTC"))

    def _cancel_live_clock(self) -> None:
        if self._clock_after_id is not None:
            self.after_cancel(self._clock_after_id)
            self._clock_after_id = None

    def _schedule_live_clock(self) -> None:
        self._cancel_live_clock()

        def tick() -> None:
            self._clock_after_id = None
            self._apply_live_clock()
            self._schedule_live_clock()

        self._clock_after_id = self.after(1000, tick)

    def change_timezone(self) -> None:
        def show_timezone_selector(result: ShellResult) -> None:
            if not result.success:
                show_error(self, self.app.tr("Change Time Zone"), result.stderr)
                return
            choices = parse_json_output(result.stdout, [])
            if not choices:
                show_error(self, self.app.tr("Change Time Zone"), self.app.tr("No time zones are available right now."))
                return
            self.timezone_choices = sorted((str(choice) for choice in choices), key=timezone_sort_key)
            labeled_choices = [format_timezone_label(choice) for choice in self.timezone_choices]
            timezone_by_label = dict(zip(labeled_choices, self.timezone_choices))
            default_timezone = format_timezone_label(self.current_timezone_id) if self.current_timezone_id in self.timezone_choices else labeled_choices[0]
            values = ask_form(
                self,
                self.app.tr("Change Time Zone"),
                [{"key": "timezone", "label": self.app.tr("Time zone"), "choices": labeled_choices, "value": default_timezone}],
            )
            if not values or not values["timezone"]:
                return
            selected_timezone = timezone_by_label.get(values["timezone"], values["timezone"])
            message = (
                f"{self.app.tr('Change the system time zone to this value?')}\n\n{values['timezone']}\n\n"
                f"{self.app.tr('Ubuntu may ask for your administrator password.')}"
            )
            if messagebox.askyesno(self.app.tr("Change Time Zone"), message, parent=self):
                self.run_action(self.app.tr("Change Time Zone"), "set_timezone", [selected_timezone], require_root=True)

        run_shell_async("time_settings.sh", "list_timezones", [], False, lambda result: self.after(0, lambda: show_timezone_selector(result)))

    def toggle_sync(self) -> None:
        current = self.values["time_sync"].get().lower()
        next_state = "off" if "enabled" in current or self.app.tr("enabled").lower() in current else "on"
        state_text = self.app.tr("off") if next_state == "off" else self.app.tr("on")
        message = (
            f"{self.app.tr('Turn automatic time {state}?', state=state_text)}\n\n"
            f"{self.app.tr('Ubuntu may ask for your administrator password.')}"
        )
        if messagebox.askyesno(self.app.tr("Automatic Time"), message, parent=self):
            self.run_action(
                self.app.tr("Automatic Time"),
                "toggle_ntp",
                [next_state],
                on_success=lambda result: self.refresh(result.stdout.strip() or self.app.tr("Time settings updated.")),
                require_root=True,
            )

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
