#!/usr/bin/env bash
set -uo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

PASSED=0
FAILED=0

pass() {
  PASSED=$((PASSED + 1))
  printf 'PASS: %s\n' "$1"
}

fail() {
  FAILED=$((FAILED + 1))
  printf 'FAIL: %s\n' "$1"
}

run_group() {
  local name="$1"
  shift
  if "$@"; then
    pass "$name"
  else
    fail "$name"
  fi
}

group_python_syntax() {
  python3 -m py_compile app.py gui/*.py
}

group_shell_syntax() {
  bash -n sh/*.sh
}

group_required_files() {
  local files=(
    app.py
    gui/__init__.py
    gui/main_window.py
    gui/file_manager_page.py
    gui/task_scheduler_page.py
    gui/time_settings_page.py
    gui/package_manager_page.py
    gui/about_page.py
    gui/dialogs.py
    gui/i18n.py
    gui/styles.py
    sh/common.sh
    sh/file_manager.sh
    sh/task_scheduler.sh
    sh/time_settings.sh
    sh/package_manager.sh
    tests/self_test.sh
    tests/test_shell_functions.sh
    tests/test_python_syntax.sh
    logs/.gitkeep
    install.sh
    README.md
    SELF_TEST_REPORT.md
  )
  local file
  for file in "${files[@]}"; do
    [[ -e "$file" ]] || return 1
  done
}

group_executable_permissions() {
  [[ -x install.sh ]] || return 1
  [[ -x tests/self_test.sh ]] || return 1
  [[ -x tests/test_shell_functions.sh ]] || return 1
  [[ -x tests/test_python_syntax.sh ]] || return 1
  local script
  for script in sh/*.sh; do
    [[ -x "$script" ]] || return 1
  done
}

group_no_terminal_ui() {
  ! grep -R -E 'read -p|select|zenity|yad|whiptail|dialog' sh/*.sh >/dev/null
}

group_no_shell_true() {
  ! grep -R 'shell=True' app.py gui/*.py >/dev/null
}

group_file_operations() {
  bash tests/test_shell_functions.sh >/dev/null
}

group_cron_expressions() {
  local tmp
  tmp="$(mktemp -d)"
  export ADMINDESK_CRONTAB_FILE="$tmp/crontab"
  export ADMINDESK_TIMER_STORE_FILE="$tmp/timers.tsv"
  local status=0
  [[ "$(bash sh/task_scheduler.sh build_cron_expression every_n_minutes 0 0 1 1 5)" == "*/5 * * * *" ]] || status=1
  [[ "$(bash sh/task_scheduler.sh build_cron_expression hourly 30 0 1 1 5)" == "30 * * * *" ]] || status=1
  [[ "$(bash sh/task_scheduler.sh build_cron_expression daily 0 8 1 1 5)" == "0 8 * * *" ]] || status=1
  [[ "$(bash sh/task_scheduler.sh build_cron_expression weekly 0 9 1 1 5)" == "0 9 * * 1" ]] || status=1
  [[ "$(bash sh/task_scheduler.sh build_cron_expression monthly 0 0 1 1 5)" == "0 0 1 * *" ]] || status=1
  rm -rf -- "$tmp"
  unset ADMINDESK_CRONTAB_FILE ADMINDESK_TIMER_STORE_FILE
  return "$status"
}

group_required_python_symbols() {
  bash tests/test_python_syntax.sh >/dev/null
}

run_group "Python syntax" group_python_syntax
run_group "Shell syntax" group_shell_syntax
run_group "Required files exist" group_required_files
run_group "Executable permissions" group_executable_permissions
run_group "No terminal UI commands" group_no_terminal_ui
run_group "Python avoids shell strings" group_no_shell_true
run_group "Shell file operations" group_file_operations
run_group "Cron expression generation" group_cron_expressions
run_group "Required Python classes/functions" group_required_python_symbols

printf '══════════════════════════════════════════\n'
printf '  SELF-TEST RESULTS\n'
printf '══════════════════════════════════════════\n'
printf '  Passed: %s\n' "$PASSED"
printf '  Failed: %s\n' "$FAILED"
printf '──────────────────────────────────────────\n'
if (( FAILED == 0 )); then
  printf '  Final: READY FOR HANDOVER\n'
else
  printf '  Final: NOT READY\n'
fi
printf '══════════════════════════════════════════\n'

(( FAILED == 0 ))
