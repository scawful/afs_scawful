#!/bin/bash
set -e

HOST="${HOST:-medical-mechanica}"
WIN_DIR="${WIN_DIR:-D:\\afs_training\\scripts}"
ROOT="D:\\src"
FORCE=false

usage() {
  echo "Usage: $0 [--host HOST] [--win-dir DIR] [--root PATH] [--force]"
  exit 1
}

while [[ $# -gt 0 ]]; do
  case $1 in
    --host)
      HOST="$2"
      shift 2
      ;;
    --win-dir)
      WIN_DIR="$2"
      shift 2
      ;;
    --root)
      ROOT="$2"
      shift 2
      ;;
    --force)
      FORCE=true
      shift
      ;;
    -h|--help)
      usage
      ;;
    *)
      echo "Unknown option: $1"
      usage
      ;;
  esac
done

FORCE_FLAG=""
if $FORCE; then
  FORCE_FLAG="-Force"
fi

ssh "$HOST" "powershell -NoProfile -File ${WIN_DIR}\\\\afs_setup_src.ps1 -Root ${ROOT} ${FORCE_FLAG}"
