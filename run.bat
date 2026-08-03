@echo off
setlocal EnableDelayedExpansion
title BrowserVault Demo Data Populator
color 0B

echo.
echo  ========================================
echo   BrowserVault Demo Data Populator
echo  ========================================
echo.

:: ── Check Python ─────────────────────────────────────────────────────────
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH.
    echo         Please install Python 3.10+ from https://python.org
    echo         Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

:: Verify Python version >= 3.10
for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PYVER=%%v
for /f "tokens=1,2 delims=." %%a in ("%PYVER%") do (
    if %%a LSS 3 (
        echo [ERROR] Python 3.10+ required, found %PYVER%
        pause
        exit /b 1
    )
    if %%a EQU 3 if %%b LSS 10 (
        echo [ERROR] Python 3.10+ required, found %PYVER%
        pause
        exit /b 1
    )
)
echo [OK] Python %PYVER% detected.

:: ── Create virtual environment if needed ─────────────────────────────────
if not exist ".venv\Scripts\activate.bat" (
    echo [..] Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created.
)

:: ── Activate venv ────────────────────────────────────────────────────────
call .venv\Scripts\activate.bat

:: ── Install / upgrade dependencies ───────────────────────────────────────
echo [..] Checking dependencies...
pip install -q -r requirements.txt >nul 2>&1
if errorlevel 1 (
    echo [WARN] pip install had issues, retrying with --upgrade...
    pip install --upgrade -r requirements.txt
)
echo [OK] Dependencies ready.

:: ── Create output directories ────────────────────────────────────────────
if not exist "logs" mkdir logs
if not exist "output" mkdir output

:: ── Run the populator ────────────────────────────────────────────────────
echo.
echo  ─── Starting population ───
echo.
python main.py %*

:: ── Done ─────────────────────────────────────────────────────────────────
echo.
echo  ========================================
echo   Complete. Check output\ for reports.
echo  ========================================
echo.
pause
