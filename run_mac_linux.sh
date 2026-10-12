#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "==================================================="
echo "Starting Learnlytics AI (macOS / Linux)"
echo "==================================================="
echo ""

if command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_CMD="python"
else
    echo "[ERROR] Python is not installed or not in PATH."
    echo "Please install Python 3.9+ from https://www.python.org/ or your package manager."
    exit 1
fi

if [ ! -f ".venv/bin/python" ]; then
    echo "Creating virtual environment in .venv..."
    $PYTHON_CMD -m venv .venv
    echo "Virtual environment created successfully."
fi

echo "Activating virtual environment..."
source .venv/bin/activate

python -m pip install --quiet --upgrade pip
if [ -f "requirements.txt" ]; then
    echo "Installing required packages from requirements.txt..."
    python -m pip install --quiet -r requirements.txt
fi

echo ""
echo "==================================================="
echo "Launching Learnlytics AI web app..."
echo "Open http://localhost:8501 in your browser."
echo "Press Ctrl+C to stop the app."
echo "==================================================="
echo ""

python -m streamlit run app.py
