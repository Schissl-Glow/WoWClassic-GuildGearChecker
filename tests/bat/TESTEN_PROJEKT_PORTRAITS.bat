@echo off
setlocal EnableExtensions
for %%I in ("%~dp0..\..") do set "REPO_ROOT=%%~fI"
cd /d "%REPO_ROOT%"
set "PROJECT_PORTRAIT_PYTHON=%~1"
set "PROJECT_PORTRAIT_ROOT=%~2"
if not defined PROJECT_PORTRAIT_ROOT set "PROJECT_PORTRAIT_ROOT=%REPO_ROOT%"
if defined PROJECT_PORTRAIT_PYTHON goto :RUN
call "%PROJECT_PORTRAIT_ROOT%\tools\_FIND_MINIFORGE.cmd"
if not defined GGC_PYTHON goto :NO_PYTHON
set "PROJECT_PORTRAIT_PYTHON=%GGC_PYTHON%"
:RUN
set "GGC_DISABLE_ICON_DOWNLOAD=1"
set "PYTHONOPTIMIZE="
"%PROJECT_PORTRAIT_PYTHON%" -B -X utf8 "%REPO_ROOT%\tests\project_portrait_tests.py" --repo-root "%PROJECT_PORTRAIT_ROOT%"
exit /b %errorlevel%
:NO_PYTHON
echo Kein geeignetes Python gefunden. MINIFORGE_DIAGNOSE.bat verwenden.
exit /b 2
