#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

export MOCK_MODE=1
TMP_DIR="$(mktemp -d)"
export SYSADMIN_GUI_MOCK_ROOT="$TMP_DIR"
export SYSADMIN_GUI_MOCK_CRONTAB="$TMP_DIR/crontab"
export SYSADMIN_GUI_MOCK_TIMERS="$TMP_DIR/timers.tsv"
trap 'rm -rf -- "$TMP_DIR"' EXIT

bash -n sh/*.sh

bash sh/file_manager.sh create_file "$TMP_DIR/file.txt" >/dev/null
[[ -f "$TMP_DIR/file.txt" ]]
printf 'hello world' > "$TMP_DIR/file.txt"
file_size="$(bash sh/file_manager.sh get_stat "$TMP_DIR/file.txt" | python3 -c 'import json, sys; print(json.load(sys.stdin)["size"])')"
[[ "$file_size" == "11" ]]
bash sh/file_manager.sh create_dir "$TMP_DIR/folder" >/dev/null
[[ -d "$TMP_DIR/folder" ]]
printf 'folder content' > "$TMP_DIR/folder/inside.txt"
listing_json="$(bash sh/file_manager.sh browse_folder "$TMP_DIR")"
LISTING_JSON="$listing_json" python3 - <<'PY'
import json
import os

rows = json.loads(os.environ["LISTING_JSON"])
by_name = {row["name"]: row for row in rows}
assert by_name["file.txt"]["size"] == 11
assert by_name["folder"]["size"] is None
PY
folder_size="$(bash sh/file_manager.sh get_stat "$TMP_DIR/folder" | python3 -c 'import json, sys; print(json.load(sys.stdin)["size"])')"
expected_folder_size="$(du -sb -- "$TMP_DIR/folder" | cut -f1)"
[[ "$folder_size" == "$expected_folder_size" ]]
bash sh/file_manager.sh rename_path "$TMP_DIR/file.txt" "$TMP_DIR/renamed.txt" >/dev/null
[[ -f "$TMP_DIR/renamed.txt" ]]
bash sh/file_manager.sh copy_path "$TMP_DIR/renamed.txt" "$TMP_DIR/copy.txt" >/dev/null
[[ -f "$TMP_DIR/copy.txt" ]]
bash sh/file_manager.sh move_path "$TMP_DIR/copy.txt" "$TMP_DIR/moved.txt" >/dev/null
[[ -f "$TMP_DIR/moved.txt" ]]
bash sh/file_manager.sh create_tar_gz "$TMP_DIR/folder" "$TMP_DIR/folder.tar.gz" >/dev/null
[[ -f "$TMP_DIR/folder.tar.gz" ]]
mkdir -p "$TMP_DIR/tar_extract"
bash sh/file_manager.sh extract_tar_gz "$TMP_DIR/folder.tar.gz" "$TMP_DIR/tar_extract" >/dev/null
[[ -d "$TMP_DIR/tar_extract/folder" ]]
bash sh/file_manager.sh create_zip "$TMP_DIR/folder" "$TMP_DIR/folder.zip" >/dev/null
[[ -f "$TMP_DIR/folder.zip" ]]
mkdir -p "$TMP_DIR/zip_extract"
bash sh/file_manager.sh extract_zip "$TMP_DIR/folder.zip" "$TMP_DIR/zip_extract" >/dev/null
[[ -d "$TMP_DIR/zip_extract/folder" ]]
bash sh/file_manager.sh delete_path "$TMP_DIR/moved.txt" >/dev/null
[[ ! -e "$TMP_DIR/moved.txt" ]]

[[ "$(bash sh/task_scheduler.sh build_cron_expression every_n_minutes 0 0 1 1 5)" == "*/5 * * * *" ]]
[[ "$(bash sh/task_scheduler.sh build_cron_expression every_n_hours 15 0 1 1 4)" == "15 */4 * * *" ]]
[[ "$(bash sh/task_scheduler.sh build_cron_expression every_n_day_of_month 10 6 1 1 3)" == "10 6 */3 * *" ]]
[[ "$(bash sh/task_scheduler.sh build_cron_expression every_n_month 20 7 5 1 5 2)" == "20 7 5 */2 *" ]]
[[ "$(bash sh/task_scheduler.sh build_cron_expression every_n_day_of_week 30 9 1 1 2)" == "30 9 * * */2" ]]
[[ "$(bash sh/task_scheduler.sh build_cron_expression hourly 30 0 1 1 5)" == "30 * * * *" ]]
[[ "$(bash sh/task_scheduler.sh build_cron_expression daily 0 8 1 1 5)" == "0 8 * * *" ]]
[[ "$(bash sh/task_scheduler.sh build_cron_expression weekly 0 9 1 1 5)" == "0 9 * * 1" ]]
[[ "$(bash sh/task_scheduler.sh build_cron_expression monthly 0 0 1 1 5)" == "0 0 1 * *" ]]
[[ "$(bash sh/task_scheduler.sh build_cron_expression custom 0 0 1 1 5 1 '*/20 9-17 * * 1-5')" == "*/20 9-17 * * 1-5" ]]

bash sh/task_scheduler.sh add_cron_job "Demo Task" "*/5 * * * *" "echo demo" >/dev/null
bash sh/task_scheduler.sh list_cron_jobs | grep -q "Demo Task"
bash sh/task_scheduler.sh remove_cron_job "Demo Task" >/dev/null

bash sh/task_scheduler.sh add_timer_job "Second Task" "30" "echo tick" >/dev/null
scheduled_json="$(bash sh/task_scheduler.sh list_scheduled_jobs)"
SCHEDULED_JSON="$scheduled_json" python3 - <<'PY'
import json
import os

rows = json.loads(os.environ["SCHEDULED_JSON"])
second_task = next(row for row in rows if row["task_name"] == "Second Task")
assert second_task["backend"] == "systemd"
assert second_task["schedule_text"] == "Every 30 seconds"
PY
bash sh/task_scheduler.sh remove_timer_job "Second Task" >/dev/null

real_timer_root="$TMP_DIR/real-timers"
mkdir -p "$real_timer_root/systemd/user"
cat > "$real_timer_root/systemd/user/sysadmin-gui-second-task.service" <<'EOF'
# SYSADMIN_GUI_TASK_NAME=Real Second Task
# SYSADMIN_GUI_COMMAND=echo real tick
[Service]
Type=oneshot
ExecStart=/bin/true
EOF
cat > "$real_timer_root/systemd/user/sysadmin-gui-second-task.timer" <<'EOF'
# SYSADMIN_GUI_TASK_NAME=Real Second Task
# SYSADMIN_GUI_INTERVAL_SECONDS=45
[Timer]
OnUnitActiveSec=45s
Unit=sysadmin-gui-second-task.service
EOF
real_scheduled_json="$(XDG_CONFIG_HOME="$real_timer_root" MOCK_MODE=0 bash sh/task_scheduler.sh list_scheduled_jobs)"
REAL_SCHEDULED_JSON="$real_scheduled_json" python3 - <<'PY'
import json
import os

rows = json.loads(os.environ["REAL_SCHEDULED_JSON"])
second_task = next(row for row in rows if row["task_name"] == "Real Second Task")
assert second_task["backend"] == "systemd"
assert second_task["schedule_text"] == "Every 45 seconds"
assert second_task["command"] == "echo real tick"
PY

fake_bin="$TMP_DIR/fake-bin"
mkdir -p "$fake_bin"
cat > "$fake_bin/apt-cache" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
case "${1:-}" in
  pkgnames)
    printf 'alpha-tool\nbeta-app\n'
    ;;
  policy)
    case "${2:-}" in
      alpha-tool) printf 'Candidate: 1.2.3\n' ;;
      beta-app) printf 'Candidate: 4.5.6\n' ;;
    esac
    ;;
  show)
    case "${2:-}" in
      alpha-tool) printf 'Description: Alpha utility package\n' ;;
      beta-app) printf 'Description: Beta desktop application\n' ;;
    esac
    ;;
esac
EOF
chmod +x "$fake_bin/apt-cache"
cat > "$fake_bin/dpkg-query" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "-W" && -z "${3:-}" ]]; then
  printf 'alpha-tool\tAlpha utility package\n'
  printf 'beta-app\tBeta desktop application\n'
  exit 0
fi
if [[ "${1:-}" == "-W" && "${3:-}" == "beta-app" ]]; then
  case "${2:-}" in
    -f=\$\{Status\}) printf 'install ok installed' ;;
    -f=\$\{Version\}) printf '4.5.6' ;;
  esac
  exit 0
fi
exit 1
EOF
chmod +x "$fake_bin/dpkg-query"
search_json="$(PATH="$fake_bin:$PATH" MOCK_MODE=0 bash sh/package_manager.sh search_packages app)"
SEARCH_JSON="$search_json" python3 - <<'PY'
import json
import os

rows = json.loads(os.environ["SEARCH_JSON"])
assert rows == [
    {
        "name": "beta-app",
        "version": "4.5.6",
        "status": "Installed",
        "description": "Beta desktop application",
        "manager": "APT",
    }
]
PY

all_search_json="$(PATH="$fake_bin:$PATH" MOCK_MODE=0 bash sh/package_manager.sh search_packages '')"
ALL_SEARCH_JSON="$all_search_json" python3 - <<'PY'
import json
import os

rows = json.loads(os.environ["ALL_SEARCH_JSON"])
assert [row["name"] for row in rows] == ["alpha-tool", "beta-app"]
PY

cat > "$fake_bin/apt" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "list" && "${2:-}" == "--installed" ]]; then
  printf 'Listing...\n'
  printf 'alpha-tool/stable,now 1.2.3 amd64 [installed]\n'
fi
EOF
chmod +x "$fake_bin/apt"
cat > "$fake_bin/snap" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "list" ]]; then
  printf 'Name Version Rev Tracking Publisher Notes\n'
  printf 'snap-store 2.0 10 latest/stable canonical** -\n'
fi
EOF
chmod +x "$fake_bin/snap"
list_json="$(PATH="$fake_bin:$PATH" MOCK_MODE=0 bash sh/package_manager.sh list_installed)"
LIST_JSON="$list_json" python3 - <<'PY'
import json
import os

rows = json.loads(os.environ["LIST_JSON"])
assert rows == [
    {
        "name": "alpha-tool",
        "version": "1.2.3",
        "status": "Installed",
        "description": "Alpha utility package",
        "manager": "APT",
    },
    {
        "name": "snap-store",
        "version": "2.0",
        "status": "Installed",
        "description": "Track: latest/stable | Publisher: canonical**",
        "manager": "Snap",
    },
]
PY

echo "Shell function tests passed."
