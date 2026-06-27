#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

parent_must_exist() {
  local path="$1"
  local parent
  parent="$(dirname -- "$path")"
  [[ -d "$parent" ]] || error_exit "Parent folder does not exist: $parent"
}

path_type() {
  local path="$1"
  if [[ -d "$path" ]]; then
    printf 'folder'
  elif [[ -f "$path" ]]; then
    printf 'file'
  else
    printf 'other'
  fi
}

path_size_bytes() {
  local path="$1"
  local size_output size
  if [[ -d "$path" ]]; then
    if size_output="$(du -sb -- "$path" 2>/dev/null)"; then
      size="${size_output%%[^0-9]*}"
      if [[ -n "$size" ]]; then
        printf '%s' "$size"
        return
      fi
    fi
  fi
  stat -c '%s' -- "$path" 2>/dev/null || printf '0'
}

path_entry_size_bytes() {
  local path="$1"
  stat -c '%s' -- "$path" 2>/dev/null || printf '0'
}

create_file() {
  local path="$1"
  validate_not_empty "$path" "File path"
  parent_must_exist "$path"
  [[ ! -e "$path" ]] || error_exit "A file or folder already exists at: $path"
  : > "$path"
  log_action "file.create_file" "succeeded" "$path"
  echo "Created file: $path"
}

create_dir() {
  local path="$1"
  validate_not_empty "$path" "Folder path"
  parent_must_exist "$path"
  [[ ! -e "$path" ]] || error_exit "A file or folder already exists at: $path"
  mkdir -- "$path"
  log_action "file.create_dir" "succeeded" "$path"
  echo "Created folder: $path"
}

delete_path() {
  local path="$1"
  validate_safe_delete_path "$path"
  if command_exists gio; then
    gio trash -- "$path"
    log_action "file.delete_path" "succeeded" "$path"
    echo "Moved to Trash: $path"
    return
  fi
  error_exit "Trash is not available on this system. Nothing was deleted."
}

rename_path() {
  local old_path="$1"
  local new_path="$2"
  validate_path_exists "$old_path"
  validate_not_empty "$new_path" "New path"
  parent_must_exist "$new_path"
  [[ ! -e "$new_path" ]] || error_exit "Destination already exists: $new_path"
  mv -- "$old_path" "$new_path"
  log_action "file.rename_path" "succeeded" "$old_path -> $new_path"
  echo "Renamed to: $new_path"
}

copy_path() {
  local src="$1"
  local dest="$2"
  validate_path_exists "$src"
  validate_not_empty "$dest" "Destination"
  parent_must_exist "$dest"
  [[ ! -e "$dest" ]] || error_exit "Destination already exists: $dest"
  cp -a -- "$src" "$dest"
  log_action "file.copy_path" "succeeded" "$src -> $dest"
  echo "Copied to: $dest"
}

move_path() {
  local src="$1"
  local dest="$2"
  validate_path_exists "$src"
  validate_not_empty "$dest" "Destination"
  parent_must_exist "$dest"
  [[ ! -e "$dest" ]] || error_exit "Destination already exists: $dest"
  mv -- "$src" "$dest"
  log_action "file.move_path" "succeeded" "$src -> $dest"
  echo "Moved to: $dest"
}

emit_path_json() {
  local path="$1"
  local size_mode="${2:-recursive}"
  local type size perms modified
  type="$(path_type "$path")"
  if [[ "$size_mode" == "files_only" && "$type" != "file" ]]; then
    size="null"
  elif [[ "$size_mode" == "entry" ]]; then
    size="$(path_entry_size_bytes "$path")"
  else
    size="$(path_size_bytes "$path")"
  fi
  perms="$(stat -c '%A' -- "$path" 2>/dev/null || printf '')"
  modified="$(stat -c '%y' -- "$path" 2>/dev/null | cut -d'.' -f1 || true)"
  printf '{"path":"%s","name":"%s","type":"%s","size":%s,"permissions":"%s","modified":"%s"}' \
    "$(json_escape "$path")" \
    "$(json_escape "$(basename -- "$path")")" \
    "$(json_escape "$type")" \
    "$size" \
    "$(json_escape "$perms")" \
    "$(json_escape "$modified")"
}

search_files() {
  local base_dir="$1"
  local query="$2"
  local search_type="${3:-all}"
  validate_path_exists "$base_dir"
  [[ -d "$base_dir" ]] || error_exit "Search location must be a folder."
  validate_not_empty "$query" "Search text"

  local find_type=()
  case "$search_type" in
    file|files) find_type=(-type f) ;;
    folder|folders|dir|dirs) find_type=(-type d) ;;
    all|"") find_type=() ;;
    *) error_exit "Unknown search type: $search_type" ;;
  esac

  printf '['
  local first=1 count=0 item
  while IFS= read -r -d '' item; do
    if (( first == 0 )); then printf ','; fi
    emit_path_json "$item" files_only
    first=0
    count=$((count + 1))
    (( count >= 200 )) && break
  done < <(find "$base_dir" -maxdepth 5 "${find_type[@]}" -iname "*$query*" -print0 2>/dev/null)
  printf ']\n'
  log_action "file.search_files" "succeeded" "$base_dir query=$query"
}

browse_folder() {
  local base_dir="$1"
  validate_path_exists "$base_dir"
  [[ -d "$base_dir" ]] || error_exit "Browse location must be a folder."
  printf '['
  local first=1 item
  while IFS= read -r -d '' item; do
    if (( first == 0 )); then printf ','; fi
    emit_path_json "$item" files_only
    first=0
  done < <(find "$base_dir" -mindepth 1 -maxdepth 1 -print0 2>/dev/null | sort -z)
  printf ']\n'
  log_action "file.browse_folder" "succeeded" "$base_dir"
}

get_stat() {
  local path="$1"
  validate_path_exists "$path"
  local type size perms owner group modified
  type="$(path_type "$path")"
  size="$(path_size_bytes "$path")"
  perms="$(stat -c '%a' -- "$path")"
  owner="$(stat -c '%U' -- "$path")"
  group="$(stat -c '%G' -- "$path")"
  modified="$(stat -c '%y' -- "$path" | cut -d'.' -f1)"
  printf '{"path":"%s","name":"%s","type":"%s","size":%s,"permissions":"%s","owner":"%s","group":"%s","modified":"%s"}\n' \
    "$(json_escape "$path")" \
    "$(json_escape "$(basename -- "$path")")" \
    "$(json_escape "$type")" \
    "$size" \
    "$(json_escape "$perms")" \
    "$(json_escape "$owner")" \
    "$(json_escape "$group")" \
    "$(json_escape "$modified")"
}

chmod_path() {
  local mode="$1"
  local path="$2"
  [[ "$mode" =~ ^[0-7]{3,4}$ ]] || error_exit "Permission mode must be 3 or 4 octal digits."
  validate_path_exists "$path"
  chmod -- "$mode" "$path"
  log_action "file.chmod_path" "succeeded" "$mode $path"
  echo "Updated permissions for: $path"
}

create_tar_gz() {
  local src="$1"
  local dest="$2"
  validate_path_exists "$src"
  validate_not_empty "$dest" "Archive path"
  parent_must_exist "$dest"
  [[ ! -e "$dest" ]] || error_exit "Archive already exists: $dest"
  tar -czf "$dest" -C "$(dirname -- "$src")" "$(basename -- "$src")"
  log_action "file.create_tar_gz" "succeeded" "$src -> $dest"
  echo "Created archive: $dest"
}

extract_tar_gz() {
  local archive="$1"
  local dest_dir="$2"
  validate_path_exists "$archive"
  validate_not_empty "$dest_dir" "Destination folder"
  mkdir -p -- "$dest_dir"
  tar -xzf "$archive" -C "$dest_dir"
  log_action "file.extract_tar_gz" "succeeded" "$archive -> $dest_dir"
  echo "Extracted archive to: $dest_dir"
}

create_zip() {
  local src="$1"
  local dest="$2"
  validate_path_exists "$src"
  validate_not_empty "$dest" "Zip path"
  parent_must_exist "$dest"
  [[ ! -e "$dest" ]] || error_exit "Zip file already exists: $dest"
  local dest_abs
  dest_abs="$(canonical_path "$dest")"
  if command_exists zip; then
    (cd "$(dirname -- "$src")" && zip -qr "$dest_abs" "$(basename -- "$src")")
  else
    require_command python3
    python3 -m zipfile -c "$dest_abs" "$src"
  fi
  log_action "file.create_zip" "succeeded" "$src -> $dest"
  echo "Created zip file: $dest"
}

extract_zip() {
  local archive="$1"
  local dest_dir="$2"
  validate_path_exists "$archive"
  validate_not_empty "$dest_dir" "Destination folder"
  mkdir -p -- "$dest_dir"
  if command_exists unzip; then
    unzip -q "$archive" -d "$dest_dir"
  else
    require_command python3
    python3 -m zipfile -e "$archive" "$dest_dir"
  fi
  log_action "file.extract_zip" "succeeded" "$archive -> $dest_dir"
  echo "Extracted zip file to: $dest_dir"
}

ACTION="${1:-}"
shift || true

case "$ACTION" in
  create_file) create_file "${1:-}" ;;
  create_dir) create_dir "${1:-}" ;;
  delete_path) delete_path "${1:-}" ;;
  rename_path) rename_path "${1:-}" "${2:-}" ;;
  copy_path) copy_path "${1:-}" "${2:-}" ;;
  move_path) move_path "${1:-}" "${2:-}" ;;
  search_files) search_files "${1:-}" "${2:-}" "${3:-all}" ;;
  browse_folder) browse_folder "${1:-}" ;;
  get_stat) get_stat "${1:-}" ;;
  chmod_path) chmod_path "${1:-}" "${2:-}" ;;
  create_tar_gz) create_tar_gz "${1:-}" "${2:-}" ;;
  extract_tar_gz) extract_tar_gz "${1:-}" "${2:-}" ;;
  create_zip) create_zip "${1:-}" "${2:-}" ;;
  extract_zip) extract_zip "${1:-}" "${2:-}" ;;
  *) error_exit "Unknown action: $ACTION" ;;
esac
