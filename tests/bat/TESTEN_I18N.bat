@echo off
setlocal EnableExtensions
for %%I in ("%~dp0..\..") do set "REPO_ROOT=%%~fI"
cd /d "%REPO_ROOT%"
set "TEST_PYTHON=%~1"
set "TEST_ROOT=%~2"
if not defined TEST_ROOT set "TEST_ROOT=%REPO_ROOT%"
if defined TEST_PYTHON goto :RUN
call "%TEST_ROOT%\tools\_FIND_MINIFORGE.cmd"
if not defined GGC_PYTHON exit /b 2
set "TEST_PYTHON=%GGC_PYTHON%"
:RUN
"%TEST_PYTHON%" -B -X utf8 "%REPO_ROOT%\tests\i18n_tests.py" --repo-root "%TEST_ROOT%"
exit /b %errorlevel%
