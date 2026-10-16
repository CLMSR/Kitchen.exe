#!/bin/bash
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is required. Install it, then double-click start.command again."
  read -r -p "Press Enter to close..."
  exit 1
fi
python3 server.py
