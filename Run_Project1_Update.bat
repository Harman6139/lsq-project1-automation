@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
if /i "%~1"=="--scheduled" goto scheduled

py -m pip install -r requirements.txt
py scripts\update_project1_monthly.py --source spartan --output-dir "%CD%"
set EXITCODE=%ERRORLEVEL%
echo.
echo Finished. Open Project_1_May2026_Update.pdf or the newest generated PDF in this folder.
pause
exit /b %EXITCODE%

:scheduled
(
echo ===== %DATE% %TIME% =====
py -m pip install -r requirements.txt
py scripts\update_project1_monthly.py --source spartan --output-dir "%CD%"
set EXITCODE=!ERRORLEVEL!
echo Exit code: !EXITCODE!
) >> automation_last_run.log 2>&1
exit /b !EXITCODE!
