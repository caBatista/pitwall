#!/usr/bin/env bash
# Preview com o simulador (iRacing só roda no Windows): ./run.sh --mock
cd "$(dirname "$0")"
[ -d .venv ] || { python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt; }
exec .venv/bin/python -m pitwall "$@"
