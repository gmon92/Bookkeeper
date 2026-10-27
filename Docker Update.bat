@echo off
setlocal
cd /d "%~dp0"

echo Updating Local Bookkeeper Docker container...
echo Building from the files in:
echo %CD%
echo.

docker compose up -d --build
if errorlevel 1 (
    echo.
    echo Docker update failed. Check that Docker Desktop is running and review the error above.
    pause
    exit /b 1
)

echo.
echo Update complete. The container is running with the rebuilt app.
pause
