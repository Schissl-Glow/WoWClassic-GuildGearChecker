@echo off
setlocal EnableExtensions
for %%I in ("%~dp0..\..") do set "REPO_ROOT=%%~fI"
cd /d "%REPO_ROOT%"
set "PLAYER_TEST_PYTHON=%~1"
set "PLAYER_TEST_ROOT=%~2"
if not defined PLAYER_TEST_ROOT set "PLAYER_TEST_ROOT=%REPO_ROOT%"
if defined PLAYER_TEST_PYTHON goto :RUN
call "%PLAYER_TEST_ROOT%\tools\_FIND_MINIFORGE.cmd"
if not defined GGC_PYTHON goto :NO_PYTHON
set "PLAYER_TEST_PYTHON=%GGC_PYTHON%"
:RUN
set "GGC_DISABLE_ICON_DOWNLOAD=1"
set "PYTHONOPTIMIZE="
"%PLAYER_TEST_PYTHON%" -B -X utf8 "%REPO_ROOT%\tests\player_model_tests.py" --repo-root "%PLAYER_TEST_ROOT%"
exit /b %errorlevel%
:NO_PYTHON
echo Kein geeignetes Python gefunden. MINIFORGE_DIAGNOSE.bat verwenden.
exit /b 2
