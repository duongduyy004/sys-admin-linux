#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

mock_cron_file() {
  local file="${SYSADMIN_GUI_MOCK_CRONTAB:-${SYSADMIN_GUI_MOCK_ROOT:-/tmp}/sysadmin_gui_mock_crontab}"
  mkdir -p "$(dirname -- "$file")"
  touch "$file"
  printf '%s\n' "$file"
}

read_cron() {
  if [[ "${MOCK_MODE:-0}" == "1" ]]; then
    cat "$(mock_cron_file)"
  else
    crontab -l 2>/dev/null || true
  fi
}

write_cron_file() {
  local file="$1"
  if [[ "${MOCK_MODE:-0}" == "1" ]]; then
    cp -- "$file" "$(mock_cron_file)"
  else
    crontab "$file"
  fi
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

list_cron_jobs() {
  local lines
  lines="$(read_cron)"
  printf '['
  local first=1 pending_name="" line expr command_text managed name
  while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ "$line" == "# SYSADMIN_GUI: "* ]]; then
      pending_name="${line#"# SYSADMIN_GUI: "}"
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
  marker="# SYSADMIN_GUI: $task_name"
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
  marker="# SYSADMIN_GUI: $task_name"
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
  list_cron_jobs) list_cron_jobs ;;
  add_cron_job) add_cron_job "${1:-}" "${2:-}" "${3:-}" ;;
  remove_cron_job) remove_cron_job "${1:-}" ;;
  build_cron_expression) build_cron_expression "${1:-}" "${2:-0}" "${3:-0}" "${4:-1}" "${5:-1}" "${6:-5}" "${7:-1}" "${8:-}" ;;
  *) error_exit "Unknown action: $ACTION" ;;
esac
