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
from gui.time_settings_page import TimeSettingsPage
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
assert describe_cron_expression("*/15 * * * *") == "Every 15 minutes"
assert describe_cron_expression("0 8 * * *") == "Every day at 08:00"
set_language("vi")
assert tr("Language") == "Ngôn ngữ"
PY

echo "Python syntax and imports passed."
