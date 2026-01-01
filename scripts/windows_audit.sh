#!/bin/bash
set -e

HOST="${HOST:-medical-mechanica}"
WIN_DIR="${WIN_DIR:-D:\\afs_training\\scripts}"

usage() {
  echo "Usage: $0 [--host HOST] [--win-dir DIR]"
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
    -h|--help)
      usage
      ;;
    *)
      echo "Unknown option: $1"
      usage
      ;;
  esac
done

ssh "$HOST" "powershell -NoProfile -File ${WIN_DIR}\\\\afs_audit.ps1"
