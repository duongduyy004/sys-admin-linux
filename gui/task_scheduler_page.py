import tkinter as tk
from tkinter import ttk, messagebox

from gui.dialogs import ProgressDialog, parse_json_output, show_error, show_info
from gui.i18n import tr
from gui.main_window import ShellResult, run_shell_async


SCHEDULE_TYPES = (
    "Every N...",
    "Hourly",
    "Daily",
    "Weekly",
    "Monthly",
    "Custom cron expression",
)
EVERY_N_UNITS = ("Seconds", "Minutes", "Hours", "Day of month", "Month", "Day of week")
DAY_OPTIONS = [
    ("Sunday", "0"),
    ("Monday", "1"),
    ("Tuesday", "2"),
    ("Wednesday", "3"),
    ("Thursday", "4"),
    ("Friday", "5"),
    ("Saturday", "6"),
]


def normalize_schedule_type(value: str) -> str:
    text = (value or "").strip().lower().replace("-", " ").replace("_", " ")
    if text in {"every n", "every n...", "every few minutes"}:
        return "every_n"
    if text in {"every n minutes"}:
        return "every_n_minutes"
    if text == "every n hours":
        return "every_n_hours"
    if text == "every n days":
        return "every_n_days"
    if text == "every n months":
        return "every_n_months"
    if text == "hourly":
        return "hourly"
    if text == "daily":
        return "daily"
    if text == "weekly":
        return "weekly"
    if text == "monthly":
        return "monthly"
    if text == "custom cron expression":
        return "custom"
    return text


def every_n_unit_key(value: str) -> str:
    text = (value or "").strip().lower()
    if text == "seconds":
        return "seconds"
    if text == "day of month":
        return "day_of_month"
    if text == "day of week":
        return "day_of_week"
    if text == "month":
        return "month"
    if text == "hours":
        return "hours"
    return "minutes"


def day_name(value: str) -> str:
    mapping = {
        "0": tr("Sunday"),
        "1": tr("Monday"),
        "2": tr("Tuesday"),
        "3": tr("Wednesday"),
        "4": tr("Thursday"),
        "5": tr("Friday"),
        "6": tr("Saturday"),
        "7": tr("Sunday"),
    }
    return mapping.get(str(value).strip(), tr("Unknown"))


def format_clock(hour: str, minute: str) -> str:
    try:
        return f"{int(hour):02d}:{int(minute):02d}"
    except (TypeError, ValueError):
        return f"{hour}:{minute}"


def describe_schedule_values(
    schedule_type: str,
    minute: str,
    hour: str,
    day_of_month: str,
    day_of_week: str,
    interval: str,
    month_interval: str = "1",
    custom_expr: str = "",
    every_n_unit: str = "Minutes",
) -> str:
    normalized = normalize_schedule_type(schedule_type)
    unit = every_n_unit_key(every_n_unit)
    if normalized in {"every_n", "every_n_minutes"} and unit == "seconds":
        return tr("Every {interval} seconds", interval=interval or "?")
    if normalized in {"every_n", "every_n_minutes"} and unit == "minutes":
        return tr("Every {interval} minutes", interval=interval or "?")
    if normalized in {"every_n", "every_n_hours"} and unit == "hours":
        return tr("Every {interval} hours at minute {minute}", interval=interval or "?", minute=f"{int(minute):02d}" if str(minute).isdigit() else minute)
    if normalized in {"every_n", "every_n_day_of_month", "every_n_days"} and unit == "day_of_month":
        return tr("Every {interval} day-of-month steps at {time}", interval=interval or "?", time=format_clock(hour, minute))
    if normalized in {"every_n", "every_n_month", "every_n_months"} and unit == "month":
        return tr("Every {interval} months on day {day} at {time}", interval=month_interval or "?", day=day_of_month, time=format_clock(hour, minute))
    if normalized in {"every_n", "every_n_day_of_week"} and unit == "day_of_week":
        return tr("Every {interval} day-of-week steps at {time}", interval=interval or "?", time=format_clock(hour, minute))
    if normalized == "hourly":
        return tr("Every hour at minute {minute}", minute=f"{int(minute):02d}" if str(minute).isdigit() else minute)
    if normalized == "daily":
        return tr("Every day at {time}", time=format_clock(hour, minute))
    if normalized == "weekly":
        return tr("Every week on {day} at {time}", day=day_name(day_of_week), time=format_clock(hour, minute))
    if normalized == "monthly":
        return tr("Every month on day {day} at {time}", day=day_of_month, time=format_clock(hour, minute))
    if normalized == "custom":
        return tr("Custom cron expression: {expr}", expr=custom_expr or tr("Unknown"))
    return tr("Custom schedule")


def describe_cron_expression(expr: str) -> str:
    parts = (expr or "").split()
    if len(parts) != 5:
        return expr or tr("Unknown")
    minute, hour, day_of_month, _month, day_of_week = parts
    if minute.startswith("*/") and hour == "*" and day_of_month == "*" and day_of_week == "*":
        return describe_schedule_values("Every N...", "0", "0", "1", "1", minute[2:] or "?", "1", "", "Minutes")
    if hour.startswith("*/") and day_of_month == "*" and day_of_week == "*":
        return describe_schedule_values("Every N...", minute, "0", "1", "1", hour[2:] or "?", "1", "", "Hours")
    if day_of_month.startswith("*/") and _month == "*" and day_of_week == "*":
        return describe_schedule_values("Every N...", minute, hour, "1", "1", day_of_month[2:] or "?", "1", "", "Day of month")
    if _month.startswith("*/") and day_of_week == "*":
        return describe_schedule_values("Every N...", minute, hour, day_of_month, "1", "5", _month[2:] or "?", "", "Month")
    if day_of_week.startswith("*/") and day_of_month == "*":
        return describe_schedule_values("Every N...", minute, hour, "1", "1", day_of_week[2:] or "?", "1", "", "Day of week")
    if hour == "*" and day_of_month == "*" and day_of_week == "*":
        return describe_schedule_values("Hourly", minute, "0", "1", "1", "5")
    if day_of_month == "*" and day_of_week == "*":
        return describe_schedule_values("Daily", minute, hour, "1", "1", "5")
    if day_of_month == "*" and day_of_week != "*":
        return describe_schedule_values("Weekly", minute, hour, "1", day_of_week, "5")
    if day_of_month != "*" and day_of_week == "*":
        return describe_schedule_values("Monthly", minute, hour, day_of_month, "1", "5")
    return expr


class ScheduledTaskDialog(tk.Toplevel):
    def __init__(self, parent: tk.Widget, app) -> None:
        super().__init__(parent)
        self.app = app
        self.title(self.app.tr("Add Scheduled Task"))
        self.transient(parent)
        self.grab_set()
        self.geometry("700x640")
        self.minsize(640, 620)
        self.result: dict[str, str] | None = None

        self.name_var = tk.StringVar(value=self.app.tr("My scheduled task"))
        self.command_var = tk.StringVar(value="")
        self.type_var = tk.StringVar(value="Daily")
        self.every_n_unit_var = tk.StringVar(value="Minutes")
        self.interval_var = tk.StringVar(value="15")
        self.month_interval_var = tk.StringVar(value="1")
        self.minute_var = tk.StringVar(value="0")
        self.hour_var = tk.StringVar(value="8")
        self.day_of_week_var = tk.StringVar(value="1")
        self.day_of_month_var = tk.StringVar(value="1")
        self.custom_expr_var = tk.StringVar(value="")
        self.preview_var = tk.StringVar(value="")

        self._build()
        self._bind_updates()
        self._refresh_schedule_fields()
        self._update_preview()

    def _build(self) -> None:
        body = ttk.Frame(self, padding=16)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)

        ttk.Label(body, text=self.app.tr("Add Scheduled Task"), style="Header.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            body,
            text=self.app.tr("Friendly scheduling for recurring reminders, scripts, and maintenance tasks."),
            style="Subtitle.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(2, 12))

        info = ttk.LabelFrame(body, text=self.app.tr("Task details"), padding=12)
        info.grid(row=2, column=0, sticky="ew")
        info.columnconfigure(1, weight=1)

        ttk.Label(info, text=self.app.tr("Task name")).grid(row=0, column=0, sticky="w", padx=(0, 10), pady=6)
        name_entry = ttk.Entry(info, textvariable=self.name_var)
        name_entry.grid(row=0, column=1, sticky="ew", pady=6)

        ttk.Label(info, text=self.app.tr("Command")).grid(row=1, column=0, sticky="w", padx=(0, 10), pady=6)
        command_entry = ttk.Entry(info, textvariable=self.command_var)
        command_entry.grid(row=1, column=1, sticky="ew", pady=6)
        ttk.Label(
            info,
            text=self.app.tr("Paste a one-line command or script path. Example: bash ~/scripts/backup.sh"),
            style="Subtitle.TLabel",
        ).grid(row=2, column=1, sticky="w", pady=(0, 4))

        schedule = ttk.LabelFrame(body, text=self.app.tr("Schedule"), padding=12)
        schedule.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        schedule.columnconfigure(1, weight=1)

        ttk.Label(schedule, text=self.app.tr("Schedule type")).grid(row=0, column=0, sticky="w", padx=(0, 10), pady=6)
        self.type_combo = ttk.Combobox(schedule, textvariable=self.type_var, values=SCHEDULE_TYPES, state="readonly")
        self.type_combo.grid(row=0, column=1, sticky="ew", pady=6)
        ttk.Label(
            schedule,
            text=self.app.tr("Choose a simple repeat pattern, then fill in only the time fields you need."),
            style="Subtitle.TLabel",
        ).grid(row=1, column=1, sticky="w", pady=(0, 6))
        ttk.Label(
            schedule,
            text=self.app.tr("Minute-and-above schedules use cron. Second-based schedules use a user systemd timer."),
            style="Subtitle.TLabel",
            wraplength=520,
        ).grid(row=2, column=1, sticky="w", pady=(0, 6))

        self.schedule_rows: dict[str, tuple[tk.Widget, tk.Widget]] = {}
        self.schedule_order = ["every_n_unit", "interval", "month_interval", "minute", "hour", "day_of_week", "day_of_month", "custom_expr"]

        unit_label = ttk.Label(schedule, text=self.app.tr("Every N unit"))
        unit_input = ttk.Combobox(schedule, textvariable=self.every_n_unit_var, values=EVERY_N_UNITS, state="readonly", width=12)
        self.schedule_rows["every_n_unit"] = (unit_label, unit_input)

        interval_label = ttk.Label(schedule, text=self.app.tr("Repeat every N minutes"))
        interval_input = ttk.Combobox(schedule, textvariable=self.interval_var, values=("5", "10", "15", "30", "45"), state="readonly")
        self.schedule_rows["interval"] = (interval_label, interval_input)

        month_interval_label = ttk.Label(schedule, text=self.app.tr("Repeat every N months"))
        month_interval_input = ttk.Combobox(schedule, textvariable=self.month_interval_var, values=("1", "2", "3", "6", "12"), state="readonly")
        self.schedule_rows["month_interval"] = (month_interval_label, month_interval_input)

        minute_label = ttk.Label(schedule, text=self.app.tr("Minute (0-59)"))
        minute_input = ttk.Spinbox(schedule, from_=0, to=59, textvariable=self.minute_var, width=8)
        self.schedule_rows["minute"] = (minute_label, minute_input)

        hour_label = ttk.Label(schedule, text=self.app.tr("Hour (0-23)"))
        hour_input = ttk.Spinbox(schedule, from_=0, to=23, textvariable=self.hour_var, width=8)
        self.schedule_rows["hour"] = (hour_label, hour_input)

        dow_label = ttk.Label(schedule, text=self.app.tr("Day of week"))
        dow_input = ttk.Combobox(
            schedule,
            textvariable=self.day_of_week_var,
            values=[value for _label, value in DAY_OPTIONS],
            state="readonly",
            width=8,
        )
        self.schedule_rows["day_of_week"] = (dow_label, dow_input)
        self.day_of_week_name_var = tk.StringVar(value="")
        ttk.Label(schedule, textvariable=self.day_of_week_name_var, style="Subtitle.TLabel").grid(row=6, column=1, sticky="w", pady=(0, 4))

        dom_label = ttk.Label(schedule, text=self.app.tr("Day of month (1-31)"))
        dom_input = ttk.Spinbox(schedule, from_=1, to=31, textvariable=self.day_of_month_var, width=8)
        self.schedule_rows["day_of_month"] = (dom_label, dom_input)

        custom_label = ttk.Label(schedule, text=self.app.tr("Raw cron expression"))
        custom_input = ttk.Entry(schedule, textvariable=self.custom_expr_var, width=28)
        self.schedule_rows["custom_expr"] = (custom_label, custom_input)

        self.preview_frame = ttk.LabelFrame(body, text=self.app.tr("Schedule preview"), padding=12)
        self.preview_frame.grid(row=4, column=0, sticky="ew", pady=(12, 0))
        self.preview_frame.columnconfigure(0, weight=1)
        ttk.Label(self.preview_frame, textvariable=self.preview_var, wraplength=620).grid(row=0, column=0, sticky="w")

        buttons = ttk.Frame(body)
        buttons.grid(row=5, column=0, sticky="e", pady=(14, 0))
        ttk.Button(buttons, text=self.app.tr("Cancel"), command=self.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(buttons, text=self.app.tr("Add Task"), command=self._submit, style="Accent.TButton").pack(side="right")

        name_entry.focus_set()
        self.bind("<Return>", lambda _event: self._submit())
        self.bind("<Escape>", lambda _event: self.destroy())

    def _bind_updates(self) -> None:
        self.type_var.trace_add("write", lambda *_args: self._refresh_schedule_fields())
        for variable in [
            self.type_var,
            self.every_n_unit_var,
            self.interval_var,
            self.month_interval_var,
            self.minute_var,
            self.hour_var,
            self.day_of_week_var,
            self.day_of_month_var,
            self.custom_expr_var,
        ]:
            variable.trace_add("write", lambda *_args: self._update_preview())

    def _refresh_schedule_fields(self) -> None:
        normalized = normalize_schedule_type(self.type_var.get())
        visible_fields = {
            "every_n": {"every_n_unit", "interval"},
            "hourly": {"minute"},
            "daily": {"minute", "hour"},
            "weekly": {"minute", "hour", "day_of_week"},
            "monthly": {"minute", "hour", "day_of_month"},
            "custom": {"custom_expr"},
        }.get(normalized, {"minute", "hour"})

        interval_label, _interval_widget = self.schedule_rows["interval"]
        if normalized == "every_n":
            unit = every_n_unit_key(self.every_n_unit_var.get())
            if unit == "seconds":
                interval_label.configure(text=self.app.tr("Repeat every N seconds"))
            elif unit == "hours":
                visible_fields.update({"minute"})
                interval_label.configure(text=self.app.tr("Repeat every N hours"))
            elif unit == "day_of_month":
                visible_fields.update({"minute", "hour"})
                interval_label.configure(text=self.app.tr("Repeat every N day-of-month steps"))
            elif unit == "month":
                visible_fields.update({"month_interval", "minute", "hour", "day_of_month"})
                visible_fields.discard("interval")
                interval_label.configure(text=self.app.tr("Repeat every N minutes"))
            elif unit == "day_of_week":
                visible_fields.update({"minute", "hour"})
                interval_label.configure(text=self.app.tr("Repeat every N day-of-week steps"))
            else:
                interval_label.configure(text=self.app.tr("Repeat every N minutes"))
        else:
            interval_label.configure(text=self.app.tr("Repeat every N minutes"))

        base_row = 3
        current_row = base_row
        for key in self.schedule_order:
            label, widget = self.schedule_rows[key]
            if key in visible_fields:
                label.grid(row=current_row, column=0, sticky="w", padx=(0, 10), pady=6)
                widget.grid(row=current_row, column=1, sticky="w", pady=6)
                current_row += 1
            else:
                label.grid_remove()
                widget.grid_remove()

        self.day_of_week_name_var.set(self.app.tr("Runs on: {day}", day=day_name(self.day_of_week_var.get())) if "day_of_week" in visible_fields else "")
        self._update_preview()

    def _update_preview(self) -> None:
        self.preview_var.set(
            self.app.tr(
                "This task will run: {schedule}",
                schedule=describe_schedule_values(
                    self.type_var.get(),
                    self.minute_var.get(),
                    self.hour_var.get(),
                    self.day_of_month_var.get(),
                    self.day_of_week_var.get(),
                    self.interval_var.get(),
                    self.month_interval_var.get(),
                    self.custom_expr_var.get(),
                    self.every_n_unit_var.get(),
                ),
            )
        )
        self.day_of_week_name_var.set(self.app.tr("Runs on: {day}", day=day_name(self.day_of_week_var.get())) if normalize_schedule_type(self.type_var.get()) == "weekly" else "")

    def _submit(self) -> None:
        values = {
            "name": self.name_var.get().strip(),
            "command": self.command_var.get().strip(),
            "type": self.type_var.get().strip(),
            "every_n_unit": self.every_n_unit_var.get().strip(),
            "interval": self.interval_var.get().strip(),
            "month_interval": self.month_interval_var.get().strip(),
            "minute": self.minute_var.get().strip(),
            "hour": self.hour_var.get().strip(),
            "dow": self.day_of_week_var.get().strip(),
            "dom": self.day_of_month_var.get().strip(),
            "custom_expr": self.custom_expr_var.get().strip(),
        }
        if not values["name"] or not values["command"]:
            messagebox.showwarning(self.app.tr("Missing information"), self.app.tr("Task name and command are required."), parent=self)
            return
        self.result = values
        self.destroy()


class TaskSchedulerPage(ttk.Frame):
    def __init__(self, parent: tk.Widget, app) -> None:
        super().__init__(parent, style="Page.TFrame", padding=18)
        self.app = app
        self.row_data: dict[str, dict] = {}
        self.selected_task_name_var = tk.StringVar(value=self.app.tr("No scheduled task selected."))
        self.selected_schedule_var = tk.StringVar(value="")
        self.selected_cron_var = tk.StringVar(value="")
        self.selected_command_var = tk.StringVar(value="")
        self.selected_managed_var = tk.StringVar(value="")
        self.selected_note_var = tk.StringVar(value=self.app.tr("Choose a scheduled task first."))
        self._build()

    def _build(self) -> None:
        summary = ttk.Frame(self, style="Card.TFrame", padding=12)
        summary.pack(fill="x", pady=(0, 10))
        ttk.Label(summary, textvariable=self.selected_task_name_var, style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(
            summary,
            text=self.app.tr("Use Add Task for new jobs. Remove Task only applies to entries created by this app."),
            style="Hint.TLabel",
            wraplength=920,
            justify="left",
        ).pack(anchor="w", pady=(4, 0))

        controls = ttk.Frame(self, style="Card.TFrame", padding=12)
        controls.pack(fill="x", pady=(0, 10))
        ttk.Button(controls, text=self.app.tr("Add Task"), command=self.add_task, style="Accent.TButton").pack(side="left")
        self.remove_button = ttk.Button(controls, text=self.app.tr("Remove Task"), command=self.remove_task, style="Danger.TButton", state="disabled")
        self.remove_button.pack(side="left", padx=(8, 0))
        ttk.Button(controls, text=self.app.tr("Refresh"), command=self.load_jobs).pack(side="left", padx=(8, 0))
        ttk.Button(controls, text=self.app.tr("Open Activity Log"), command=self.view_logs).pack(side="left", padx=(8, 0))

        ttk.Label(
            self,
            text=self.app.tr("Tasks created here can be removed from this screen. Other cron jobs stay visible but read-only."),
            style="Subtitle.TLabel",
            wraplength=920,
        ).pack(anchor="w", pady=(0, 10))

        content = ttk.Frame(self)
        content.pack(fill="both", expand=True)
        content.columnconfigure(0, weight=3)
        content.columnconfigure(1, weight=2)
        content.rowconfigure(0, weight=1)

        table_frame = ttk.Frame(content, style="Card.TFrame", padding=12)
        table_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        ttk.Label(table_frame, text=self.app.tr("Scheduled jobs"), style="CardTitle.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 8))
        details_frame = ttk.Frame(content, style="Card.TFrame", padding=12)
        details_frame.grid(row=0, column=1, sticky="nsew")
        details_frame.columnconfigure(0, weight=1)

        columns = ("task_name", "schedule_text", "managed")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings")
        for column, heading, width in [
            ("task_name", self.app.tr("Task name"), 220),
            ("schedule_text", self.app.tr("Schedule"), 280),
            ("managed", self.app.tr("Created here"), 110),
        ]:
            self.tree.heading(column, text=heading)
            self.tree.column(column, width=width, anchor="w")
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self.update_action_states())
        yscroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=yscroll.set)
        self.tree.grid(row=1, column=0, sticky="nsew")
        yscroll.grid(row=1, column=1, sticky="ns")
        table_frame.rowconfigure(1, weight=1)
        table_frame.columnconfigure(0, weight=1)

        ttk.Label(details_frame, text=self.app.tr("Task details"), style="Header.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(details_frame, textvariable=self.selected_task_name_var).grid(row=1, column=0, sticky="w", pady=(8, 2))
        ttk.Label(details_frame, text=self.app.tr("Schedule"), style="Subtitle.TLabel").grid(row=2, column=0, sticky="w", pady=(10, 0))
        ttk.Label(details_frame, textvariable=self.selected_schedule_var, wraplength=340).grid(row=3, column=0, sticky="w")
        ttk.Label(details_frame, text=self.app.tr("Raw cron expression"), style="Subtitle.TLabel").grid(row=4, column=0, sticky="w", pady=(10, 0))
        ttk.Label(details_frame, textvariable=self.selected_cron_var, wraplength=340).grid(row=5, column=0, sticky="w")
        ttk.Label(details_frame, text=self.app.tr("Command"), style="Subtitle.TLabel").grid(row=6, column=0, sticky="w", pady=(10, 0))
        ttk.Label(details_frame, textvariable=self.selected_command_var, wraplength=340).grid(row=7, column=0, sticky="w")
        ttk.Label(details_frame, text=self.app.tr("Created here"), style="Subtitle.TLabel").grid(row=8, column=0, sticky="w", pady=(10, 0))
        ttk.Label(details_frame, textvariable=self.selected_managed_var, wraplength=340).grid(row=9, column=0, sticky="w")
        ttk.Label(details_frame, textvariable=self.selected_note_var, style="Subtitle.TLabel", wraplength=340).grid(row=10, column=0, sticky="w", pady=(14, 0))

    def on_show(self) -> None:
        if not self.tree.get_children():
            self.load_jobs()
        self.update_action_states()

    def selected_item_id(self) -> str:
        selected = self.tree.selection()
        return selected[0] if selected else ""

    def update_action_states(self) -> None:
        item = self.selected_item_id()
        if not item:
            self.remove_button.configure(state="disabled")
            self._show_empty_details()
            return
        row = self.row_data.get(item, {})
        managed = bool(row.get("managed"))
        self.remove_button.configure(state="normal" if managed else "disabled")
        self._show_details(row)

    def _show_empty_details(self) -> None:
        self.selected_task_name_var.set(self.app.tr("No scheduled task selected."))
        self.selected_schedule_var.set("")
        self.selected_cron_var.set("")
        self.selected_command_var.set("")
        self.selected_managed_var.set("")
        self.selected_note_var.set(self.app.tr("Choose a scheduled task first."))

    def _show_details(self, row: dict) -> None:
        managed = bool(row.get("managed"))
        self.selected_task_name_var.set(row.get("task_name", ""))
        self.selected_schedule_var.set(row.get("schedule_text", ""))
        self.selected_cron_var.set(row.get("cron_expr", ""))
        self.selected_command_var.set(row.get("command", ""))
        self.selected_managed_var.set(self.app.tr("Yes") if managed else self.app.tr("No"))
        self.selected_note_var.set(
            self.app.tr("This task can be removed here.") if managed else self.app.tr("This task was not created by this app, so it stays read-only here.")
        )

    def run_action(self, title: str, action: str, args: list[str], on_success=None, show_output: bool = True) -> None:
        progress = ProgressDialog(self, title, self.app.tr("Updating scheduled tasks..."))

        def done(result: ShellResult) -> None:
            self.after(0, lambda: self._finish(progress, title, action, result, on_success, show_output))

        run_shell_async("task_scheduler.sh", action, args, False, done, timeout_seconds=20)

    def _finish(self, progress: ProgressDialog, title: str, action: str, result: ShellResult, on_success, show_output: bool) -> None:
        progress.finish(result.success, result.stdout, result.stderr, show_output=show_output)
        if result.success:
            self.app.set_status(result.stdout.strip() or self.app.tr("Action completed."))
            if on_success:
                on_success(result)
            else:
                self.load_jobs(show_progress=False)
            if action != "list_cron_jobs":
                show_info(self, title, result.stdout)
        else:
            self.app.set_status(self.app.tr("Scheduled task action failed."))
            show_error(self, title, result.stderr)

    def load_jobs(self, show_progress: bool = True) -> None:
        def populate(result: ShellResult) -> None:
            rows = parse_json_output(result.stdout, [])
            self.tree.delete(*self.tree.get_children())
            self.row_data.clear()
            for index, row in enumerate(rows):
                row_copy = dict(row)
                row_copy["schedule_text"] = row.get("schedule_text") or describe_cron_expression(row.get("cron_expr", ""))
                item_id = f"task-{index}"
                self.row_data[item_id] = row_copy
                self.tree.insert(
                    "",
                    "end",
                    iid=item_id,
                    values=(
                        row_copy.get("task_name", ""),
                        row_copy.get("schedule_text", ""),
                        self.app.tr("Yes") if row_copy.get("managed") else self.app.tr("No"),
                    ),
                )
            self.update_action_states()

        if show_progress:
            self.run_action(self.app.tr("Load scheduled tasks"), "list_cron_jobs", [], populate, show_output=False)
        else:
            run_shell_async(
                "task_scheduler.sh",
                "list_cron_jobs",
                [],
                False,
                lambda result: self.after(0, lambda: populate(result)),
                timeout_seconds=20,
            )

    def add_task(self) -> None:
        dialog = ScheduledTaskDialog(self, self.app)
        self.wait_window(dialog)
        values = dialog.result
        if not values:
            return

        schedule_text = describe_schedule_values(
            values["type"],
            values["minute"],
            values["hour"],
            values["dom"],
            values["dow"],
            values["interval"],
            values["month_interval"],
            values["custom_expr"],
            values["every_n_unit"],
        )

        build_type = values["type"]
        backend = "cron"
        if normalize_schedule_type(values["type"]) == "every_n":
            unit = every_n_unit_key(values["every_n_unit"])
            build_type = {
                "seconds": "Every N seconds",
                "minutes": "Every N minutes",
                "hours": "Every N hours",
                "day_of_month": "Every N day-of-month",
                "month": "Every N month",
                "day_of_week": "Every N day-of-week",
            }[unit]
            if unit == "seconds":
                backend = "systemd"

        def after_expr(result: ShellResult) -> None:
            if not result.success:
                show_error(self, self.app.tr("Invalid schedule"), result.stderr)
                return
            cron_expr = result.stdout.strip()
            message = (
                f"{self.app.tr('Add this scheduled task?')}\n\n"
                f"{self.app.tr('Name')}: {values['name']}\n"
                f"{self.app.tr('Schedule')}: {schedule_text}\n"
                f"{self.app.tr('Scheduler backend')}: {self.app.tr('Cron') if backend == 'cron' else self.app.tr('Systemd user timer')}\n"
                f"{self.app.tr('Raw cron expression')}: {cron_expr}\n"
                f"{self.app.tr('Command')}: {values['command']}"
            )
            if messagebox.askyesno(self.app.tr("Confirm Scheduled Task"), message, parent=self):
                action = "add_timer_job" if backend == "systemd" else "add_cron_job"
                args = [values["name"], values["interval"], values["command"]] if backend == "systemd" else [values["name"], cron_expr, values["command"]]
                self.run_action(self.app.tr("Add Scheduled Task"), action, args)

        if backend == "systemd":
            self.after(
                0,
                lambda: after_expr(
                    ShellResult(
                        success=True,
                        stdout=f"Every {values['interval']} seconds",
                        stderr="",
                        returncode=0,
                        command=["systemd", "timer"],
                    )
                ),
            )
        else:
            run_shell_async(
                "task_scheduler.sh",
                "build_cron_expression",
                [
                    build_type,
                    values["minute"],
                    values["hour"],
                    values["dom"],
                    values["dow"],
                    values["interval"],
                    values["month_interval"],
                    values["custom_expr"],
                ],
                False,
                lambda result: self.after(0, lambda: after_expr(result)),
                timeout_seconds=10,
            )

    def remove_task(self) -> None:
        item = self.selected_item_id()
        if not item:
            messagebox.showwarning(self.app.tr("No task selected"), self.app.tr("Choose a scheduled task first."), parent=self)
            return
        row = self.row_data.get(item, {})
        task_name = row.get("task_name", "")
        backend = row.get("backend", "cron")
        managed = bool(row.get("managed"))
        if not managed:
            messagebox.showwarning(self.app.tr("Manual task"), self.app.tr("Only tasks created by this app can be removed here."), parent=self)
            return
        schedule_text = row.get("schedule_text", "")
        if messagebox.askyesno(
            self.app.tr("Remove Scheduled Task"),
            f"{self.app.tr('Remove this scheduled task?')}\n\n{task_name}\n\n{self.app.tr('Schedule')}: {schedule_text}",
            parent=self,
        ):
            action = "remove_timer_job" if backend == "systemd" else "remove_cron_job"
            self.run_action(self.app.tr("Remove Task"), action, [task_name])

    def view_logs(self) -> None:
        log_path = "logs/admindesk.log"
        try:
            with open(log_path, "r", encoding="utf-8") as handle:
                content = handle.read()[-12000:]
        except FileNotFoundError:
            content = self.app.tr("No log entries yet.")
        window = tk.Toplevel(self)
        window.title(self.app.tr("Activity Log"))
        window.geometry("720x420")
        text = tk.Text(window, wrap="word")
        scroll = ttk.Scrollbar(window, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        text.insert("1.0", content)
        text.configure(state="disabled")
        text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
