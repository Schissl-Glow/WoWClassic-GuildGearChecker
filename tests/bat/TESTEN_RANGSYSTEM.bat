@echo off
setlocal EnableExtensions
for %%I in ("%~dp0..\..") do set "REPO_ROOT=%%~fI"
cd /d "%REPO_ROOT%"
set "RANK_TEST_PYTHON=%~1"
set "RANK_TEST_ROOT=%~2"
if not defined RANK_TEST_ROOT set "RANK_TEST_ROOT=%REPO_ROOT%"
if defined RANK_TEST_PYTHON goto :RUN
call "%RANK_TEST_ROOT%\tools\_FIND_MINIFORGE.cmd"
if not defined GGC_PYTHON goto :NO_PYTHON
set "RANK_TEST_PYTHON=%GGC_PYTHON%"
:RUN
set "PYTHONOPTIMIZE="
"%RANK_TEST_PYTHON%" -B -X utf8 "%REPO_ROOT%\tests\rank_rewards_tests.py"
exit /b %errorlevel%
:NO_PYTHON
echo Kein geeignetes Python gefunden. MINIFORGE_DIAGNOSE.bat verwenden.
exit /b 2
