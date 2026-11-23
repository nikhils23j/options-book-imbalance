#!/bin/sh
# Invoked via sh; from anywhere inside or outside the checkout.
set -eu
cd "$(dirname "$0")/../.."
if [ "$#" -gt 1 ] || { [ "$#" -eq 1 ] && [ "$1" != "--offline" ]; }; then
  echo "Usage: sh research/archive/reproduce.sh [--offline]" >&2
  exit 2
fi
python3 research/archive/fetch.py "$@"
PYTHONPATH=src python3 -m unittest discover -s tests
python3 research/archive/study.py
python3 research/archive/audit.py
python3 research/archive/peer_control.py
python3 research/archive/heatmap.py
python3 research/archive/figures.py
