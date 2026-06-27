#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

resolve_log_file() {
  if [[ "$PROJECT_DIR" == "/opt/admindesk" ]]; then
    if touch /var/log/admindesk.log 2>/dev/null; then
      echo "/var/log/admindesk.log"
      return
    fi
  fi
  mkdir -p "$PROJECT_DIR/logs"
  echo "$PROJECT_DIR/logs/admindesk.log"
}

LOG_FILE="${ADMINDESK_LOG:-$(resolve_log_file)}"

timestamp_utc() {
  date -u '+%Y-%m-%dT%H:%M:%SZ'
}

log_action() {
  local action="${1:-unknown}"
  local status="${2:-info}"
  local detail="${3:-}"
  mkdir -p "$(dirname "$LOG_FILE")"
  printf '%s action=%s status=%s detail=%s\n' "$(timestamp_utc)" "$action" "$status" "$detail" >> "$LOG_FILE" 2>/dev/null || true
}

error_exit() {
  local message="${1:-Operation failed}"
  echo "$message" >&2
  log_action "error" "failed" "$message"
  exit 1
}

validate_not_empty() {
  local value="${1:-}"
  local label="${2:-value}"
  [[ -n "$value" ]] || error_exit "$label is required."
}

validate_path_exists() {
  local path="${1:-}"
  validate_not_empty "$path" "Path"
  [[ -e "$path" ]] || error_exit "Path does not exist: $path"
}

canonical_path() {
  local path="${1:-}"
  realpath -m -- "$path" 2>/dev/null || printf '%s\n' "$path"
}

validate_safe_delete_path() {
  local path="${1:-}"
  validate_path_exists "$path"
  local full
  full="$(canonical_path "$path")"
  case "$full" in
    /|/bin|/boot|/dev|/etc|/lib|/lib64|/proc|/root|/run|/sbin|/sys|/usr|/var|/opt)
      error_exit "Refusing to delete protected system path: $full"
      ;;
  esac
}

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

require_command() {
  local cmd="${1:-}"
  validate_not_empty "$cmd" "Command"
  command_exists "$cmd" || error_exit "Required command is not available: $cmd"
}

json_escape() {
  local input="${1:-}"
  input="${input//\\/\\\\}"
  input="${input//\"/\\\"}"
  input="${input//$'\n'/\\n}"
  input="${input//$'\r'/\\r}"
  input="${input//$'\t'/\\t}"
  printf '%s' "$input"
}

json_bool() {
  [[ "${1:-}" == "true" ]] && printf 'true' || printf 'false'
}
