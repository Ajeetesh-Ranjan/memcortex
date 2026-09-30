@echo off
REM Unified Memory Stack — Windows Menubar Installer
REM Installs the Python system tray app with auto-start

setlocal enabledelayedexpansion

REM Colors (using ANSI if supported)
set GREEN=\033[0;32m
set YELLOW=\033[1;33m
set RED=\033[0;31m
set NC=\033[0m

REM Enable ANSI colors on Windows 10+
reg add HKCU\Console /v VirtualTerminalLevel /t REG_DWORD /d 1 /f >nul 2>&1

echo [install] Unified Memory Stack - Windows System Tray Installer

REM Get repo root
set REPO_ROOT=%~dp0..
set REPO_ROOT=%REPO_ROOT:\widgets\menubar\windows=%
set PYTHON_SCRIPT=%REPO_ROOT%\widgets\menubar\memory_menubar.py

echo [install] Repo: %REPO_ROOT%

REM Check Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [error] Python not found. Install from https://python.org
    exit /b 1
}

echo [install] Python found: 
python --version

REM Check pip
where pip >nul 2>&1
if %errorlevel% neq 0 (
    echo [error] pip not found
    exit /b 1
}

echo [install] Installing dependencies...
pip install pystray pillow requests --quiet

if %errorlevel% neq 0 (
    echo [error] Failed to install dependencies
    exit /b 1
}

echo [install] Dependencies installed

REM Create start menu shortcut
set STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
set SHORTCUT=%STARTUP_DIR%\Unified Memory Stack.lnk
set PYTHON_EXE=%~dp0python.exe
if not exist "%PYTHON_EXE%" set PYTHON_EXE=python

echo [install] Creating startup shortcut...

powershell -Command ^
    "$WshShell = New-Object -ComObject WScript.Shell; ^
    $Shortcut = $WshShell.CreateShortcut('%SHORTCUT%'); ^
    $Shortcut.TargetPath = '%PYTHON_EXE%'; ^
    $Shortcut.Arguments = '%PYTHON_SCRIPT%'; ^
    $Shortcut.WorkingDirectory = '%REPO_ROOT%'; ^
    $Shortcut.Description = 'Unified Memory Stack - System Tray'; ^
    $Shortcut.Save()"

if %errorlevel% neq 0 (
    echo [warn] Could not create startup shortcut automatically
    echo [info] You can manually create a shortcut to: %PYTHON_EXE% %PYTHON_SCRIPT%
) else (
    echo [install] Startup shortcut created
)

REM Create desktop shortcut
set DESKTOP_DIR=%USERPROFILE%\Desktop
set DESKTOP_SHORTCUT=%DESKTOP_DIR%\Unified Memory Stack.lnk

powershell -Command ^
    "$WshShell = New-Object -ComObject WScript.Shell; ^
    $Shortcut = $WshShell.CreateShortcut('%DESKTOP_SHORTCUT%'); ^
    $Shortcut.TargetPath = '%PYTHON_EXE%'; ^
    $Shortcut.Arguments = '%PYTHON_SCRIPT%'; ^
    $Shortcut.WorkingDirectory = '%REPO_ROOT%'; ^
    $Shortcut.Description = 'Unified Memory Stack - System Tray'; ^
    $Shortcut.Save()" 2>nul

if %errorlevel% equ 0 (
    echo [install] Desktop shortcut created
)

REM Set environment variables (user scope)
echo [install] Setting environment variables...

setx MEMORY_API_BASE "http://localhost:8080" >nul
setx MEMORY_REFRESH_SEC "30" >nul

echo [install] Environment variables set (restart terminal to take effect)

REM Test run
echo.
echo [install] Testing installation...
python "%PYTHON_SCRIPT%" --help 2>&1 | head -5

echo.
echo ============================================
echo [install] Installation complete!
echo ============================================
echo.
echo The Unified Memory Stack system tray app will:
echo   - Start automatically on login
echo   - Appear in system tray (bottom-right)
echo   - Show status: Green=healthy, Yellow=degraded, Red=unhealthy
echo   - Left-click: Open dashboard
echo   - Right-click: Menu (Refresh, Logs, Restart, Quit)
echo.
echo To run manually now:
echo   python "%PYTHON_SCRIPT%"
echo.
echo To uninstall:
echo   - Remove %SHORTCUT%
echo   - Remove %DESKTOP_SHORTCUT%
echo   - Run: pip uninstall pystray pillow requests
echo.
pause