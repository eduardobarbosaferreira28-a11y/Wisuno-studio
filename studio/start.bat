@echo off
:: Wisuno Studio — one-click launcher
:: This script finds the venv Python and runs launch.py

:: Get the directory this bat file is in (studio\)
set "STUDIO=%~dp0"
if "%STUDIO:~-1%"=="\" set "STUDIO=%STUDIO:~0,-1%"

:: Go one level up to find wisuno-carousel\
for %%I in ("%STUDIO%") do set "ROOT=%%~dpI"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

set "PYTHON=%ROOT%\.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
    echo.
    echo  ERROR: Cannot find Python venv at:
    echo         %PYTHON%
    echo.
    echo  Please make sure you have created the virtual environment.
    echo.
    pause
    exit /b 1
)

"%PYTHON%" "%STUDIO%\launch.py"
pause
