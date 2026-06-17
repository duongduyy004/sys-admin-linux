#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

export MOCK_MODE=1
TMP_DIR="$(mktemp -d)"
export SYSADMIN_GUI_MOCK_ROOT="$TMP_DIR"
export SYSADMIN_GUI_MOCK_CRONTAB="$TMP_DIR/crontab"
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
[[ "$(bash sh/task_scheduler.sh build_cron_expression hourly 30 0 1 1 5)" == "30 * * * *" ]]
[[ "$(bash sh/task_scheduler.sh build_cron_expression daily 0 8 1 1 5)" == "0 8 * * *" ]]
[[ "$(bash sh/task_scheduler.sh build_cron_expression weekly 0 9 1 1 5)" == "0 9 * * 1" ]]
[[ "$(bash sh/task_scheduler.sh build_cron_expression monthly 0 0 1 1 5)" == "0 0 1 * *" ]]

bash sh/task_scheduler.sh add_cron_job "Demo Task" "*/5 * * * *" "echo demo" >/dev/null
bash sh/task_scheduler.sh list_cron_jobs | grep -q "Demo Task"
bash sh/task_scheduler.sh remove_cron_job "Demo Task" >/dev/null

echo "Shell function tests passed."
