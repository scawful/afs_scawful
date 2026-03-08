#!/bin/bash
set -euo pipefail

# Wrapper to the canonical AFS-Scawful chat service script.
exec /Users/scawful/src/lab/afs-scawful/scripts/afs/chat-service.sh "$@"
