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

has_command() {
  command -v "$1" >/dev/null 2>&1
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

package_description() {
  local package="$1"
  apt-cache show "$package" 2>/dev/null | awk -F': ' '/^Description: / {print $2; exit}'
}

search_package_names() {
  local query="$1"
  apt-cache pkgnames 2>/dev/null | awk -v query="$query" '
    BEGIN {
      lower_query = tolower(query)
    }
    {
      if (lower_query == "" || index(tolower($0), lower_query) > 0) {
        print $0
      }
    }
  '
}

search_packages() {
  local query="$1"
  if [[ "${MOCK_MODE:-0}" == "1" ]]; then
    printf '[{"name":"demo-package","version":"1.0","status":"Available","description":"Mock package result for %s","manager":"APT"}]\n' "$(json_escape "$query")"
    return
  fi
  require_command apt-cache
  require_command dpkg-query
  printf '['
  local first=1 count=0 name desc version status
  while IFS= read -r name; do
    [[ -n "$name" ]] || continue
    version="$(package_version "$name" || true)"
    desc="$(package_description "$name" || true)"
    status="$(package_status "$name")"
    if (( first == 0 )); then printf ','; fi
    printf '{"name":"%s","version":"%s","status":"%s","description":"%s","manager":"APT"}' \
      "$(json_escape "$name")" \
      "$(json_escape "${version:-Unknown}")" \
      "$(json_escape "$status")" \
      "$(json_escape "$desc")"
    first=0
    count=$((count + 1))
    (( count >= 50 )) && break
  done < <(search_package_names "$query")
  printf ']\n'
  log_action "apt.search_packages" "succeeded" "$query"
}

list_installed() {
  if [[ "${MOCK_MODE:-0}" == "1" ]]; then
    printf '[{"name":"python3","version":"3.x","status":"Installed","description":"Mock APT package","manager":"APT"},{"name":"snap-store","version":"1.x","status":"Installed","description":"Mock Snap package","manager":"Snap"}]\n'
    return
  fi
  printf '['
  local first=1 line name version desc tracking publisher notes
  local -A apt_descriptions=()

  if has_command dpkg-query; then
    while IFS=$'\t' read -r name desc; do
      [[ -n "$name" ]] || continue
      apt_descriptions["$name"]="$desc"
    done < <(dpkg-query -W -f='${binary:Package}\t${Description}\n' 2>/dev/null)
  fi

  if has_command apt; then
    while IFS= read -r line; do
      [[ -n "$line" ]] || continue
      name="${line%%/*}"
      version="${line#* }"
      version="${version%% *}"
      desc="${apt_descriptions[$name]:-}"
      if (( first == 0 )); then printf ','; fi
      printf '{"name":"%s","version":"%s","status":"Installed","description":"%s","manager":"APT"}' \
        "$(json_escape "$name")" \
        "$(json_escape "$version")" \
        "$(json_escape "$desc")"
      first=0
    done < <(apt list --installed 2>/dev/null | tail -n +2)
  fi

  if has_command snap; then
    while IFS=$'\t' read -r name version tracking publisher notes; do
      [[ -n "$name" ]] || continue
      desc="Track: ${tracking:-unknown}"
      [[ -n "${publisher:-}" ]] && desc="$desc | Publisher: $publisher"
      [[ -n "$name" ]] || continue
      if (( first == 0 )); then printf ','; fi
      printf '{"name":"%s","version":"%s","status":"Installed","description":"%s","manager":"Snap"}' \
        "$(json_escape "$name")" \
        "$(json_escape "$version")" \
        "$(json_escape "$desc")"
      first=0
    done < <(snap list 2>/dev/null | awk 'NR>1 {print $1 "\t" $2 "\t" $4 "\t" $5 "\t" $6}')
  fi

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
  local manager="${1:-APT}"
  local package="${2:-}"
  validate_package_name "$package"
  if [[ "${MOCK_MODE:-0}" == "1" ]]; then
    log_action "pkg.remove_package" "mocked" "$manager:$package"
    echo "Mock mode: package would be removed from $manager: $package"
    return
  fi
  case "${manager^^}" in
    APT)
      require_command apt
      DEBIAN_FRONTEND=noninteractive apt remove -y -- "$package"
      ;;
    SNAP)
      require_command snap
      snap remove -- "$package"
      ;;
    *)
      error_exit "Unknown package source: $manager"
      ;;
  esac
  log_action "pkg.remove_package" "succeeded" "$manager:$package"
  echo "Removed package from $manager: $package"
}

ACTION="${1:-}"
shift || true

case "$ACTION" in
  apt_update_if_needed) apt_update_if_needed ;;
  search_packages) search_packages "${1:-}" ;;
  list_installed) list_installed ;;
  install_package) install_package "${1:-}" ;;
  remove_package) remove_package "${1:-APT}" "${2:-}" ;;
  *) error_exit "Unknown action: $ACTION" ;;
esac
