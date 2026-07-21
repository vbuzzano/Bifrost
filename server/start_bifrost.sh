#!/usr/bin/env bash
# Launches Bifrost server, output redirected to bifrost.log.
#
# This script doesn't register itself anywhere - to auto-start at login,
# point your OS's own login-item/startup mechanism at it (see README.md).
cd "$(dirname "$0")"
if [ -x ".venv/bin/python" ]; then
    exec ".venv/bin/python" -u main.py >> bifrost.log 2>&1
else
    exec python3 -u main.py >> bifrost.log 2>&1
fi
