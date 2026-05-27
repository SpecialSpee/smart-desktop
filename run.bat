@echo off
setlocal EnableDelayedExpansion

set "APP_NAME=Smart Desktop"
set "APP_SCRIPT=desktop_manager.py"
set "REQUIREMENTS=requirements.txt"
set "LOG_FILE=launcher.log"

echo.
echo ════════════════════════════════════════
echo   %APP_NAME% - Launcher
echo ════════════════════════════════════════
echo.

:: Проверка Python
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found! Install Python 3.10+ from python.org
    pause
    exit /b 1
)

:: Проверка зависимостей
echo [1/3] Checking Python...
python --version

echo [2/3] Checking dependencies...
if exist "%REQUIREMENTS%" (
    python -m pip install -r "%REQUIREMENTS%" -q
)

echo [3/3] Launching %APP_NAME%...
echo.
echo ✅ Application started! Check system tray.
echo 💡 Press F1 to open panel
echo.

:: Запуск через pythonw (без консоли)
where pythonw >nul 2>&1
if !errorlevel! equ 0 (
    start "" pythonw "%APP_SCRIPT%"
) else (
    start "" python "%APP_SCRIPT%"
)

:: Скрыть консоль через 2 секунды
timeout /t 2 /nobreak >nul
exit /b 0