#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

cron_file_override() {
  local file="${ADMINDESK_CRONTAB_FILE:-}"
  [[ -n "$file" ]] || return 1
  mkdir -p "$(dirname -- "$file")"
  touch "$file"
  printf '%s\n' "$file"
}

timer_store_override() {
  local file="${ADMINDESK_TIMER_STORE_FILE:-}"
  [[ -n "$file" ]] || return 1
  mkdir -p "$(dirname -- "$file")"
  touch "$file"
  printf '%s\n' "$file"
}

systemd_user_dir() {
  printf '%s\n' "${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
}

systemd_state_dir() {
  printf '%s\n' "${XDG_STATE_HOME:-$HOME/.local/state}/admindesk/timers"
}

timer_unit_name() {
  local task_name="$1"
  local slug
  slug="$(printf '%s' "$task_name" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/-/g; s/-\{2,\}/-/g; s/^-//; s/-$//')"
  [[ -n "$slug" ]] || slug="task"
  printf 'admindesk-%s' "$slug"
}

read_cron() {
  if cron_file_override >/dev/null; then
    cat "$(cron_file_override)"
    return
  fi
  crontab -l 2>/dev/null || true
}

write_cron_file() {
  local file="$1"
  if cron_file_override >/dev/null; then
    cp -- "$file" "$(cron_file_override)"
    return
  fi
  crontab "$file"
}

validate_no_newline() {
  local value="$1"
  local label="$2"
  [[ "$value" != *$'\n'* && "$value" != *$'\r'* ]] || error_exit "$label cannot contain new lines."
}

validate_cron_expr() {
  local expr="$1"
  validate_not_empty "$expr" "Cron expression"
  validate_no_newline "$expr" "Cron expression"
  local field_count
  field_count="$(awk '{print NF}' <<< "$expr")"
  [[ "$field_count" == "5" ]] || error_exit "Cron expression must have five fields."
}

validate_interval_seconds() {
  local seconds="$1"
  validate_not_empty "$seconds" "Seconds interval"
  is_number "$seconds" || error_exit "Seconds interval must be a number."
  (( seconds >= 1 )) || error_exit "Seconds interval must be at least 1."
}

list_cron_jobs_only() {
  local lines
  lines="$(read_cron)"
  printf '['
  local first=1 pending_name="" line expr command_text managed name
  while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ "$line" == "# ADMINDESK: "* ]]; then
      pending_name="${line#"# ADMINDESK: "}"
      continue
    fi
    [[ -n "$line" ]] || continue
    [[ "$line" == \#* ]] && continue
    expr="$(awk '{print $1" "$2" "$3" "$4" "$5}' <<< "$line")"
    command_text="$(cut -d' ' -f6- <<< "$line")"
    managed=false
    name="Manual cron job"
    if [[ -n "$pending_name" ]]; then
      managed=true
      name="$pending_name"
      pending_name=""
    fi
    if (( first == 0 )); then printf ','; fi
    printf '{"task_name":"%s","cron_expr":"%s","command":"%s","managed":%s}' \
      "$(json_escape "$name")" \
      "$(json_escape "$expr")" \
      "$(json_escape "$command_text")" \
      "$(json_bool "$managed")"
    first=0
  done <<< "$lines"
  printf ']\n'
}

list_timer_jobs_only() {
  printf '['
  local first=1
  if timer_store_override >/dev/null; then
    local line task_name interval_seconds command_text
    while IFS=$'\t' read -r task_name interval_seconds command_text || [[ -n "${task_name:-}" ]]; do
      [[ -n "${task_name:-}" ]] || continue
      if (( first == 0 )); then printf ','; fi
      printf '{"task_name":"%s","schedule_text":"%s","command":"%s","managed":true,"backend":"systemd","interval_seconds":"%s"}' \
        "$(json_escape "$task_name")" \
        "$(json_escape "Every $interval_seconds seconds")" \
        "$(json_escape "$command_text")" \
        "$(json_escape "$interval_seconds")"
      first=0
    done < "$(timer_store_override)"
    printf ']\n'
    return
  fi

  local dir service_file timer_file task_name command_text interval_seconds
  dir="$(systemd_user_dir)"
  shopt -s nullglob
  for timer_file in "$dir"/admindesk-*.timer; do
    service_file="${timer_file%.timer}.service"
    [[ -f "$service_file" ]] || continue
    task_name="$(grep '^# ADMINDESK_TASK_NAME=' "$service_file" | head -n1 | sed 's/^# ADMINDESK_TASK_NAME=//' || true)"
    command_text="$(grep '^# ADMINDESK_COMMAND=' "$service_file" | head -n1 | sed 's/^# ADMINDESK_COMMAND=//' || true)"
    interval_seconds="$(grep '^# ADMINDESK_INTERVAL_SECONDS=' "$timer_file" | head -n1 | sed 's/^# ADMINDESK_INTERVAL_SECONDS=//' || true)"
    [[ -n "$task_name" && -n "$interval_seconds" ]] || continue
    if (( first == 0 )); then printf ','; fi
    printf '{"task_name":"%s","schedule_text":"%s","command":"%s","managed":true,"backend":"systemd","interval_seconds":"%s"}' \
      "$(json_escape "$task_name")" \
      "$(json_escape "Every $interval_seconds seconds")" \
      "$(json_escape "$command_text")" \
      "$(json_escape "$interval_seconds")"
    first=0
  done
  shopt -u nullglob
  printf ']\n'
}

list_scheduled_jobs() {
  local cron_json timer_json
  cron_json="$(list_cron_jobs_only)"
  timer_json="$(list_timer_jobs_only)"
  CRON_JSON="$cron_json" TIMER_JSON="$timer_json" python3 - <<'PY'
import json
import os

cron_rows = json.loads(os.environ["CRON_JSON"] or "[]")
timer_rows = json.loads(os.environ["TIMER_JSON"] or "[]")
for row in cron_rows:
    row.setdefault("backend", "cron")
print(json.dumps(timer_rows + cron_rows, separators=(",", ":")))
PY
  log_action "cron.list_cron_jobs" "succeeded" "listed jobs"
}

add_cron_job() {
  local task_name="$1"
  local cron_expr="$2"
  local command_text="$3"
  validate_not_empty "$task_name" "Task name"
  validate_not_empty "$command_text" "Command"
  validate_no_newline "$task_name" "Task name"
  validate_no_newline "$command_text" "Command"
  validate_cron_expr "$cron_expr"

  local temp current marker
  temp="$(mktemp)"
  marker="# ADMINDESK: $task_name"
  current="$(read_cron)"
  awk -v marker="$marker" 'skip_next {skip_next=0; next} $0 == marker {skip_next=1; next} {print}' <<< "$current" > "$temp"
  {
    [[ -s "$temp" ]] && tail -c1 "$temp" | read -r _ || true
    printf '%s\n%s %s\n' "$marker" "$cron_expr" "$command_text"
  } >> "$temp"
  write_cron_file "$temp"
  rm -f -- "$temp"
  log_action "cron.add_cron_job" "succeeded" "$task_name"
  echo "Added scheduled task: $task_name"
}

remove_cron_job() {
  local task_name="$1"
  validate_not_empty "$task_name" "Task name"
  validate_no_newline "$task_name" "Task name"
  local temp current marker before after
  temp="$(mktemp)"
  marker="# ADMINDESK: $task_name"
  current="$(read_cron)"
  before="$(grep -Fxc "$marker" <<< "$current" || true)"
  awk -v marker="$marker" 'skip_next {skip_next=0; next} $0 == marker {skip_next=1; next} {print}' <<< "$current" > "$temp"
  after="$(grep -Fxc "$marker" "$temp" || true)"
  write_cron_file "$temp"
  rm -f -- "$temp"
  if [[ "$before" == "$after" ]]; then
    echo "No matching scheduled task was found: $task_name"
  else
    echo "Removed scheduled task: $task_name"
  fi
  log_action "cron.remove_cron_job" "succeeded" "$task_name"
}

add_timer_job() {
  local task_name="$1"
  local interval_seconds="$2"
  local command_text="$3"
  validate_not_empty "$task_name" "Task name"
  validate_not_empty "$command_text" "Command"
  validate_no_newline "$task_name" "Task name"
  validate_no_newline "$command_text" "Command"
  validate_interval_seconds "$interval_seconds"

  if timer_store_override >/dev/null; then
    local temp
    temp="$(mktemp)"
    awk -F $'\t' -v name="$task_name" '$1 != name {print}' "$(timer_store_override)" > "$temp" || true
    printf '%s\t%s\t%s\n' "$task_name" "$interval_seconds" "$command_text" >> "$temp"
    mv -- "$temp" "$(timer_store_override)"
    log_action "timer.add_timer_job" "succeeded" "$task_name"
    echo "Added second-based scheduled task: $task_name"
    return
  fi

  require_command systemctl
  local user_dir state_dir unit script_file service_file timer_file
  user_dir="$(systemd_user_dir)"
  state_dir="$(systemd_state_dir)"
  unit="$(timer_unit_name "$task_name")"
  script_file="$state_dir/$unit.sh"
  service_file="$user_dir/$unit.service"
  timer_file="$user_dir/$unit.timer"
  mkdir -p "$user_dir" "$state_dir"

  cat > "$script_file" <<EOF
#!/usr/bin/env bash
set -euo pipefail
$command_text
EOF
  chmod +x "$script_file"

  cat > "$service_file" <<EOF
# ADMINDESK_TASK_NAME=$task_name
# ADMINDESK_COMMAND=$command_text
[Unit]
Description=AdminDesk Task: $task_name

[Service]
Type=oneshot
ExecStart=$script_file
EOF

  cat > "$timer_file" <<EOF
# ADMINDESK_TASK_NAME=$task_name
# ADMINDESK_INTERVAL_SECONDS=$interval_seconds
[Unit]
Description=AdminDesk Timer: $task_name

[Timer]
OnBootSec=${interval_seconds}s
OnUnitActiveSec=${interval_seconds}s
Unit=$unit.service

[Install]
WantedBy=timers.target
EOF

  systemctl --user daemon-reload
  systemctl --user enable --now "$unit.timer" >/dev/null
  log_action "timer.add_timer_job" "succeeded" "$task_name"
  echo "Added second-based scheduled task: $task_name"
}

remove_timer_job() {
  local task_name="$1"
  validate_not_empty "$task_name" "Task name"
  validate_no_newline "$task_name" "Task name"

  if timer_store_override >/dev/null; then
    local temp
    temp="$(mktemp)"
    awk -F $'\t' -v name="$task_name" '$1 != name {print}' "$(timer_store_override)" > "$temp" || true
    mv -- "$temp" "$(timer_store_override)"
    log_action "timer.remove_timer_job" "succeeded" "$task_name"
    echo "Removed second-based scheduled task: $task_name"
    return
  fi

  require_command systemctl
  local unit user_dir state_dir script_file service_file timer_file
  unit="$(timer_unit_name "$task_name")"
  user_dir="$(systemd_user_dir)"
  state_dir="$(systemd_state_dir)"
  script_file="$state_dir/$unit.sh"
  service_file="$user_dir/$unit.service"
  timer_file="$user_dir/$unit.timer"

  systemctl --user disable --now "$unit.timer" >/dev/null 2>&1 || true
  rm -f -- "$script_file" "$service_file" "$timer_file"
  systemctl --user daemon-reload
  log_action "timer.remove_timer_job" "succeeded" "$task_name"
  echo "Removed second-based scheduled task: $task_name"
}

is_number() {
  [[ "${1:-}" =~ ^[0-9]+$ ]]
}

validate_range() {
  local value="$1"
  local label="$2"
  local min="$3"
  local max="$4"
  is_number "$value" || error_exit "$label must be a number."
  (( value >= min && value <= max )) || error_exit "$label must be between $min and $max."
}

build_cron_expression() {
  local schedule_type="$1"
  local minute="${2:-0}"
  local hour="${3:-0}"
  local day_of_month="${4:-1}"
  local day_of_week="${5:-1}"
  local interval="${6:-5}"
  local month_interval="${7:-1}"
  local custom_expr="${8:-}"
  case "$schedule_type" in
    "Every N day-of-month"|every_n_day_of_month)
      validate_range "$interval" "Interval" 1 31
      validate_range "$minute" "Minute" 0 59
      validate_range "$hour" "Hour" 0 23
      printf '%s %s */%s * *\n' "$minute" "$hour" "$interval"
      ;;
    "Every N day-of-week"|every_n_day_of_week)
      validate_range "$interval" "Interval" 1 7
      validate_range "$minute" "Minute" 0 59
      validate_range "$hour" "Hour" 0 23
      printf '%s %s * * */%s\n' "$minute" "$hour" "$interval"
      ;;
    "Every N month"|every_n_month)
      validate_range "$month_interval" "Month interval" 1 12
      validate_range "$minute" "Minute" 0 59
      validate_range "$hour" "Hour" 0 23
      validate_range "$day_of_month" "Day of month" 1 31
      printf '%s %s %s */%s *\n' "$minute" "$hour" "$day_of_month" "$month_interval"
      ;;
    "Every N minutes"|every_n_minutes)
      validate_range "$interval" "Interval" 1 59
      printf '*/%s * * * *\n' "$interval"
      ;;
    "Every N hours"|every_n_hours)
      validate_range "$interval" "Interval" 1 23
      validate_range "$minute" "Minute" 0 59
      printf '%s */%s * * *\n' "$minute" "$interval"
      ;;
    "Every N days"|every_n_days)
      validate_range "$interval" "Interval" 1 31
      validate_range "$minute" "Minute" 0 59
      validate_range "$hour" "Hour" 0 23
      printf '%s %s */%s * *\n' "$minute" "$hour" "$interval"
      ;;
    "Every N months"|every_n_months)
      validate_range "$month_interval" "Month interval" 1 12
      validate_range "$minute" "Minute" 0 59
      validate_range "$hour" "Hour" 0 23
      validate_range "$day_of_month" "Day of month" 1 31
      printf '%s %s %s */%s *\n' "$minute" "$hour" "$day_of_month" "$month_interval"
      ;;
    Hourly|hourly)
      validate_range "$minute" "Minute" 0 59
      printf '%s * * * *\n' "$minute"
      ;;
    Daily|daily)
      validate_range "$minute" "Minute" 0 59
      validate_range "$hour" "Hour" 0 23
      printf '%s %s * * *\n' "$minute" "$hour"
      ;;
    Weekly|weekly)
      validate_range "$minute" "Minute" 0 59
      validate_range "$hour" "Hour" 0 23
      validate_range "$day_of_week" "Day of week" 0 7
      printf '%s %s * * %s\n' "$minute" "$hour" "$day_of_week"
      ;;
    Monthly|monthly)
      validate_range "$minute" "Minute" 0 59
      validate_range "$hour" "Hour" 0 23
      validate_range "$day_of_month" "Day of month" 1 31
      printf '%s %s %s * *\n' "$minute" "$hour" "$day_of_month"
      ;;
    "Custom cron expression"|custom)
      validate_cron_expr "$custom_expr"
      printf '%s\n' "$custom_expr"
      ;;
    *) error_exit "Unknown schedule type: $schedule_type" ;;
  esac
}

ACTION="${1:-}"
shift || true

case "$ACTION" in
  list_cron_jobs|list_scheduled_jobs) list_scheduled_jobs ;;
  add_cron_job) add_cron_job "${1:-}" "${2:-}" "${3:-}" ;;
  remove_cron_job) remove_cron_job "${1:-}" ;;
  add_timer_job) add_timer_job "${1:-}" "${2:-}" "${3:-}" ;;
  remove_timer_job) remove_timer_job "${1:-}" ;;
  build_cron_expression) build_cron_expression "${1:-}" "${2:-0}" "${3:-0}" "${4:-1}" "${5:-1}" "${6:-5}" "${7:-1}" "${8:-}" ;;
  *) error_exit "Unknown action: $ACTION" ;;
esac
