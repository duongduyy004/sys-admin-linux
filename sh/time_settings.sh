#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

need_timedatectl() {
  if [[ "${MOCK_MODE:-0}" == "1" ]]; then
    return 0
  fi
  require_command timedatectl
}

normalize_toggle_state() {
  local value="${1:-}"
  case "${value,,}" in
    yes|true|1|enabled) echo "enabled" ;;
    no|false|0|disabled) echo "disabled" ;;
    *) echo "disabled" ;;
  esac
}

get_info() {
  if [[ "${MOCK_MODE:-0}" == "1" ]]; then
    printf '{"local_time":"2026-01-01 12:00:00 UTC","date":"2026-01-01","timezone":"UTC","time_sync":"enabled","utc_time":"2026-01-01 12:00:00 UTC"}\n'
    return
  fi
  need_timedatectl
  local local_time date_value timezone sync_enabled sync_fallback utc_time
  local_time="$(date '+%Y-%m-%d %H:%M:%S %Z')"
  date_value="$(date '+%Y-%m-%d')"
  timezone="$(timedatectl show -p Timezone --value 2>/dev/null || true)"
  sync_enabled="$(timedatectl show -p NTP --value 2>/dev/null || true)"
  sync_fallback="$(timedatectl show -p NTPSynchronized --value 2>/dev/null || true)"
  utc_time="$(date -u '+%Y-%m-%d %H:%M:%S UTC')"
  printf '{"local_time":"%s","date":"%s","timezone":"%s","time_sync":"%s","utc_time":"%s"}\n' \
    "$(json_escape "$local_time")" \
    "$(json_escape "$date_value")" \
    "$(json_escape "${timezone:-Unknown}")" \
    "$(json_escape "$(normalize_toggle_state "${sync_enabled:-$sync_fallback}")")" \
    "$(json_escape "$utc_time")"
}

list_timezones() {
  if [[ "${MOCK_MODE:-0}" == "1" ]]; then
    printf '["UTC","Asia/Ho_Chi_Minh","America/New_York"]\n'
    return
  fi
  need_timedatectl
  printf '['
  local first=1 zone
  while IFS= read -r zone; do
    [[ -n "$zone" ]] || continue
    if (( first == 0 )); then printf ','; fi
    printf '"%s"' "$(json_escape "$zone")"
    first=0
  done < <(timedatectl list-timezones)
  printf ']\n'
}

set_timezone() {
  local timezone="$1"
  validate_not_empty "$timezone" "Timezone"
  validate_no_newline_time "$timezone" "Timezone"
  if [[ "${MOCK_MODE:-0}" == "1" ]]; then
    log_action "time.set_timezone" "mocked" "$timezone"
    echo "Mock mode: timezone would be changed to $timezone"
    return
  fi
  need_timedatectl
  timedatectl set-timezone "$timezone"
  log_action "time.set_timezone" "succeeded" "$timezone"
  echo "Timezone changed to: $timezone"
}

toggle_ntp() {
  local state="$1"
  case "$state" in
    on|true|enabled) state=true ;;
    off|false|disabled) state=false ;;
    *) error_exit "Time sync value must be on or off." ;;
  esac
  if [[ "${MOCK_MODE:-0}" == "1" ]]; then
    log_action "time.toggle_ntp" "mocked" "$state"
    echo "Mock mode: time sync would be set to $state"
    return
  fi
  need_timedatectl
  timedatectl set-ntp "$state"
  log_action "time.toggle_ntp" "succeeded" "$state"
  echo "Time sync updated."
}

validate_no_newline_time() {
  local value="$1"
  local label="$2"
  [[ "$value" != *$'\n'* && "$value" != *$'\r'* ]] || error_exit "$label cannot contain new lines."
}

set_datetime() {
  local datetime="$1"
  validate_not_empty "$datetime" "Date and time"
  validate_no_newline_time "$datetime" "Date and time"
  [[ "$datetime" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}[[:space:]][0-9]{2}:[0-9]{2}:[0-9]{2}$ ]] || error_exit "Use date and time format: YYYY-MM-DD HH:MM:SS"
  if [[ "${MOCK_MODE:-0}" == "1" ]]; then
    log_action "time.set_datetime" "mocked" "$datetime"
    echo "Mock mode: date and time would be changed to $datetime"
    return
  fi
  need_timedatectl
  timedatectl set-time "$datetime"
  log_action "time.set_datetime" "succeeded" "$datetime"
  echo "Date and time changed to: $datetime"
}

ACTION="${1:-}"
shift || true

case "$ACTION" in
  get_info) get_info ;;
  list_timezones) list_timezones ;;
  set_timezone) set_timezone "${1:-}" ;;
  toggle_ntp) toggle_ntp "${1:-}" ;;
  set_datetime) set_datetime "${1:-}" ;;
  *) error_exit "Unknown action: $ACTION" ;;
esac
