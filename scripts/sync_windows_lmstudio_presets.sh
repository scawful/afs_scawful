#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AFS_SCAWFUL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LAB_ROOT="$(cd "$AFS_SCAWFUL_ROOT/.." && pwd)"
SCAWFULBOT_ROOT="$LAB_ROOT/scawfulbot"

HOST="${HOST:-medical-mechanica}"
WIN_DIR="D:/afs_training/lmstudio"

usage() {
  cat <<'USAGE'
Usage: sync_windows_lmstudio_presets.sh [--host HOST] [--win-dir DIR]

Copies the local LM Studio preset bundle to the Windows host. The staged bundle
lands under D:/afs_training/lmstudio by default.
USAGE
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)
      HOST="$2"
      shift 2
      ;;
    --win-dir)
      WIN_DIR="$2"
      shift 2
      ;;
    -h|--help)
      usage
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      ;;
  esac
done

copy_text_file() {
  local source_path="$1"
  local relative_path="$2"
  local remote_path="${WIN_DIR}/${relative_path}"
  local remote_dir

  if [[ ! -f "$source_path" ]]; then
    echo "Missing source file: $source_path" >&2
    exit 1
  fi

  remote_dir="$(dirname "$remote_path")"
  ssh "$HOST" "powershell -NoProfile -Command \"[IO.Directory]::CreateDirectory('${remote_dir}') | Out-Null; \$content = [Console]::In.ReadToEnd(); \$utf8 = [System.Text.UTF8Encoding]::new(\$false); [IO.File]::WriteAllText('${remote_path}', \$content, \$utf8)\"" < "$source_path"
  echo "Synced $(basename "$source_path") -> ${remote_path}"
}

copy_text_file "$SCAWFULBOT_ROOT/scawfulbot_runtime.py" "scawfulbot/scawfulbot_runtime.py"
copy_text_file "$SCAWFULBOT_ROOT/config/registry.json" "scawfulbot/config/registry.json"
copy_text_file "$SCAWFULBOT_ROOT/config/system_prompt.md" "scawfulbot/config/system_prompt.md"
copy_text_file "$SCAWFULBOT_ROOT/config/system_prompt_lmstudio.md" "scawfulbot/config/system_prompt_lmstudio.md"
copy_text_file "$SCAWFULBOT_ROOT/config/system_prompt_lmstudio_tight.md" "scawfulbot/config/system_prompt_lmstudio_tight.md"
copy_text_file "$SCAWFULBOT_ROOT/scripts/load_lmstudio_profile.py" "scawfulbot/scripts/load_lmstudio_profile.py"
copy_text_file "$SCAWFULBOT_ROOT/scripts/windows_lmstudio_ctl.py" "scawfulbot/scripts/windows_lmstudio_ctl.py"
copy_text_file "$AFS_SCAWFUL_ROOT/config/oracle_tools_lmstudio.json" "afs-scawful/config/oracle_tools_lmstudio.json"
copy_text_file "$AFS_SCAWFUL_ROOT/config/chat_registry.toml" "afs-scawful/config/chat_registry.toml"

echo "LM Studio preset bundle synced to ${HOST}:${WIN_DIR}"
