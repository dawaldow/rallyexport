@echo off
setlocal

cd /d "%~dp0"

echo Rally Stories and Matched Tasks Export
echo ======================================
echo.

where py >nul 2>nul

if %errorlevel%==0 (
    py -3 rally_export.py
) else (
    python rally_export.py
)

if errorlevel 1 (
    echo.
    echo Export failed. Review the error above.
) else (
    echo.
    echo Export completed successfully.
)

echo.
pause

endlocal