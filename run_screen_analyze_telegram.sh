#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
exec bash "scripts/run_screen_analyze_telegram.sh" "$@"
