#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

validate_package_name() {
  local package="$1"
  validate_not_empty "$package" "Package name"
  [[ "$package" =~ ^[a-zA-Z0-9][a-zA-Z0-9+._:-]*$ ]] || error_exit "Package name contains unsupported characters."
}

apt_update_if_needed() {
  if [[ "${MOCK_MODE:-0}" == "1" ]]; then
    log_action "apt.update_if_needed" "mocked" "mock update"
    echo "Mock mode: package index would be checked."
    return
  fi
  require_command apt
  local stamp="/var/lib/apt/periodic/update-success-stamp"
  if [[ -f "$stamp" ]] && find "$stamp" -mtime -1 -print -quit | grep -q .; then
    echo "Package index is recent."
    return
  fi
  apt update
  log_action "apt.update_if_needed" "succeeded" "apt update"
}

package_status() {
  local package="$1"
  if dpkg-query -W -f='${Status}' "$package" 2>/dev/null | grep -q "install ok installed"; then
    printf 'Installed'
  else
    printf 'Available'
  fi
}

package_version() {
  local package="$1"
  if dpkg-query -W -f='${Version}' "$package" 2>/dev/null; then
    return
  fi
  apt-cache policy "$package" 2>/dev/null | awk '/Candidate:/ {print $2; exit}'
}

search_packages() {
  local query="$1"
  validate_not_empty "$query" "Search text"
  if [[ "${MOCK_MODE:-0}" == "1" ]]; then
    printf '[{"name":"demo-package","version":"1.0","status":"Available","description":"Mock package result for %s"}]\n' "$(json_escape "$query")"
    return
  fi
  require_command apt-cache
  require_command dpkg-query
  printf '['
  local first=1 count=0 line name desc version status
  while IFS= read -r line; do
    [[ -n "$line" ]] || continue
    name="${line%% - *}"
    desc="${line#* - }"
    [[ "$name" == "$line" ]] && desc=""
    version="$(package_version "$name" || true)"
    status="$(package_status "$name")"
    if (( first == 0 )); then printf ','; fi
    printf '{"name":"%s","version":"%s","status":"%s","description":"%s"}' \
      "$(json_escape "$name")" \
      "$(json_escape "${version:-Unknown}")" \
      "$(json_escape "$status")" \
      "$(json_escape "$desc")"
    first=0
    count=$((count + 1))
    (( count >= 50 )) && break
  done < <(apt-cache search --names-only "$query" 2>/dev/null)
  printf ']\n'
  log_action "apt.search_packages" "succeeded" "$query"
}

list_installed() {
  if [[ "${MOCK_MODE:-0}" == "1" ]]; then
    printf '[{"name":"python3","version":"3.x","status":"Installed","description":"Mock installed package"}]\n'
    return
  fi
  require_command dpkg-query
  printf '['
  local first=1 count=0 line name version desc
  while IFS=$'\t' read -r name version desc; do
    [[ -n "$name" ]] || continue
    if (( first == 0 )); then printf ','; fi
    printf '{"name":"%s","version":"%s","status":"Installed","description":"%s"}' \
      "$(json_escape "$name")" \
      "$(json_escape "$version")" \
      "$(json_escape "$desc")"
    first=0
    count=$((count + 1))
    (( count >= 500 )) && break
  done < <(dpkg-query -W -f='${binary:Package}\t${Version}\t${Description}\n' 2>/dev/null)
  printf ']\n'
  log_action "apt.list_installed" "succeeded" "listed installed packages"
}

install_package() {
  local package="$1"
  validate_package_name "$package"
  if [[ "${MOCK_MODE:-0}" == "1" ]]; then
    log_action "apt.install_package" "mocked" "$package"
    echo "Mock mode: package would be installed: $package"
    return
  fi
  require_command apt
  DEBIAN_FRONTEND=noninteractive apt install -y -- "$package"
  log_action "apt.install_package" "succeeded" "$package"
  echo "Installed package: $package"
}

remove_package() {
  local package="$1"
  validate_package_name "$package"
  if [[ "${MOCK_MODE:-0}" == "1" ]]; then
    log_action "apt.remove_package" "mocked" "$package"
    echo "Mock mode: package would be removed: $package"
    return
  fi
  require_command apt
  DEBIAN_FRONTEND=noninteractive apt remove -y -- "$package"
  log_action "apt.remove_package" "succeeded" "$package"
  echo "Removed package: $package"
}

ACTION="${1:-}"
shift || true

case "$ACTION" in
  apt_update_if_needed) apt_update_if_needed ;;
  search_packages) search_packages "${1:-}" ;;
  list_installed) list_installed ;;
  install_package) install_package "${1:-}" ;;
  remove_package) remove_package "${1:-}" ;;
  *) error_exit "Unknown action: $ACTION" ;;
esac
