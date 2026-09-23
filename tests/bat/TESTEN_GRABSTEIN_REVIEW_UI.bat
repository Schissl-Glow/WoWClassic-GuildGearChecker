@echo off
setlocal EnableExtensions
for %%I in ("%~dp0..\..") do set "REPO_ROOT=%%~fI"
cd /d "%REPO_ROOT%"
if not "%~1"=="" (
    set "GGC_PYTHON=%~1"
) else (
    call "%REPO_ROOT%\tools\_FIND_MINIFORGE.cmd"
)
if not defined GGC_PYTHON (
    echo TEST FEHLGESCHLAGEN: Miniforge/Python wurde nicht gefunden.
    exit /b 1
)
"%GGC_PYTHON%" "%REPO_ROOT%\tests\gravestone_review_queue_ui_tests.py"
set "RC=%ERRORLEVEL%"
endlocal & exit /b %RC%
