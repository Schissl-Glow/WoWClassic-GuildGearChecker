@echo off
setlocal EnableExtensions
for %%I in ("%~dp0..\..") do set "REPO_ROOT=%%~fI"
cd /d "%REPO_ROOT%"
set "INCARNATION_PYTHON=%~1"
set "INCARNATION_ROOT=%~2"
if not defined INCARNATION_ROOT set "INCARNATION_ROOT=%REPO_ROOT%"
if defined INCARNATION_PYTHON goto :RUN
call "%INCARNATION_ROOT%\tools\_FIND_MINIFORGE.cmd"
if not defined GGC_PYTHON goto :NO_PYTHON
set "INCARNATION_PYTHON=%GGC_PYTHON%"
:RUN
set "GGC_DISABLE_ICON_DOWNLOAD=1"
set "PYTHONOPTIMIZE="
"%INCARNATION_PYTHON%" -B -X utf8 "%REPO_ROOT%\tests\name_incarnation_tests.py" --repo-root "%INCARNATION_ROOT%"
exit /b %errorlevel%
:NO_PYTHON
echo Kein geeignetes Python gefunden. MINIFORGE_DIAGNOSE.bat verwenden.
exit /b 2
