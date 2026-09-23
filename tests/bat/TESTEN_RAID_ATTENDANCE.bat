@echo off
setlocal EnableExtensions
for %%I in ("%~dp0..\..") do set "REPO_ROOT=%%~fI"
cd /d "%REPO_ROOT%"
set "RAID_TEST_PYTHON=%~1"
set "RAID_TEST_ROOT=%~2"
if not defined RAID_TEST_ROOT set "RAID_TEST_ROOT=%REPO_ROOT%"
if defined RAID_TEST_PYTHON goto :RUN
call "%RAID_TEST_ROOT%\tools\_FIND_MINIFORGE.cmd"
if not defined GGC_PYTHON goto :NO_PYTHON
set "RAID_TEST_PYTHON=%GGC_PYTHON%"
:RUN
set "GGC_DISABLE_ICON_DOWNLOAD=1"
set "PYTHONOPTIMIZE="
"%RAID_TEST_PYTHON%" -B -X utf8 "%REPO_ROOT%\tests\raid_attendance_tests.py" --repo-root "%RAID_TEST_ROOT%"
exit /b %errorlevel%
:NO_PYTHON
echo Kein geeignetes Python gefunden. MINIFORGE_DIAGNOSE.bat verwenden.
exit /b 2
