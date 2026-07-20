#!/usr/bin/env bash
# Bifrost - Python server venv setup (Linux / macOS)
# Run once from the server/ directory:  ./setup_venv.sh

set -e
VENV=".venv"

if [ ! -d "$VENV" ]; then
    echo "Creating venv..."
    python3 -m venv "$VENV"
fi

echo "Installing dependencies..."
"$VENV/bin/pip" install -r requirements.txt

echo ""
echo "Done. To start the server:"
echo "  source .venv/bin/activate"
echo "  python main.py"
echo ""
echo "Or without activating:"
echo "  ./.venv/bin/python main.py"
