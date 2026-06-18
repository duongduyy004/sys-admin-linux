#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

python3 -m py_compile app.py gui/*.py
python3 - <<'PY'
from gui.main_window import MainWindow, run_shell
from gui.dashboard_page import DashboardPage
from gui.file_manager_page import FileManagerPage, format_size
from gui.task_scheduler_page import TaskSchedulerPage, describe_cron_expression, describe_schedule_values
from gui.time_settings_page import TimeSettingsPage, format_timezone_label, format_utc_offset, timezone_sort_key
from gui.package_manager_page import PackageManagerPage
from gui.about_page import AboutPage
from gui.i18n import tr, set_language

assert MainWindow
assert DashboardPage
assert FileManagerPage
assert TaskSchedulerPage
assert TimeSettingsPage
assert PackageManagerPage
assert AboutPage
assert run_shell
assert format_size(1536) == "1.50 KB"
assert format_size(1048576) == "1.00 MB"
assert format_size(1073741824) == "1.00 GB"
assert describe_schedule_values("Weekly", "30", "9", "1", "1", "5") == "Every week on Monday at 09:30"
assert describe_schedule_values("Every N...", "0", "0", "1", "1", "30", "1", "", "Seconds") == "Every 30 seconds"
assert describe_schedule_values("Every N...", "15", "0", "1", "1", "4", "1", "", "Hours") == "Every 4 hours at minute 15"
assert describe_schedule_values("Every N...", "20", "7", "5", "1", "5", "2", "", "Month") == "Every 2 months on day 5 at 07:20"
assert describe_cron_expression("*/15 * * * *") == "Every 15 minutes"
assert describe_cron_expression("15 */4 * * *") == "Every 4 hours at minute 15"
assert describe_cron_expression("10 6 */3 * *") == "Every 3 day-of-month steps at 06:10"
assert describe_cron_expression("20 7 5 */2 *") == "Every 2 months on day 5 at 07:20"
assert describe_cron_expression("30 9 * * */2") == "Every 2 day-of-week steps at 09:30"
assert describe_cron_expression("0 8 * * *") == "Every day at 08:00"
assert format_utc_offset(25200) == "UTC + 07:00"
assert format_utc_offset(19800) == "UTC + 05:30"
assert format_timezone_label("Asia/Ho_Chi_Minh").endswith("(UTC + 07:00)")
assert sorted(["Asia/Ho_Chi_Minh", "UTC", "Asia/Kolkata"], key=timezone_sort_key) == ["UTC", "Asia/Kolkata", "Asia/Ho_Chi_Minh"]
set_language("vi")
assert tr("Language") == "Ngôn ngữ"
PY

echo "Python syntax and imports passed."
