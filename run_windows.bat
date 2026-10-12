@echo off
setlocal enabledelayedexpansion

echo ===================================================
echo Starting Learnlytics AI (Windows)
echo ===================================================
echo.

cd /d "%~dp0"

where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not found in PATH.
    echo Please download and install Python from https://www.python.org/
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment in .venv...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo Virtual environment created successfully.
)

echo Activating virtual environment and checking dependencies...
call .venv\Scripts\activate.bat

python -m pip install --quiet --upgrade pip
if exist "requirements.txt" (
    echo Installing required packages from requirements.txt...
    python -m pip install --quiet -r requirements.txt
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to install requirements.
        pause
        exit /b 1
    )
)

echo.
echo ===================================================
echo Launching Learnlytics AI web app...
echo Open http://localhost:8501 in your browser if it does not open automatically.
echo Press Ctrl+C in this window to stop the server.
echo ===================================================
echo.

python -m streamlit run app.py

pause
