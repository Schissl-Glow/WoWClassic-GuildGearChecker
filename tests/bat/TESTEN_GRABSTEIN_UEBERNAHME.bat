@echo off
setlocal EnableExtensions
for %%I in ("%~dp0..\..") do set "REPO_ROOT=%%~fI"
cd /d "%REPO_ROOT%"
set "GGC_PYTHON=%~1"
if not defined GGC_PYTHON call "%REPO_ROOT%\tools\_FIND_MINIFORGE.cmd"
if not defined GGC_PYTHON exit /b 1
"%GGC_PYTHON%" -B -X utf8 "%REPO_ROOT%\tests\gravestone_promotion_tests.py" --repo-root "%REPO_ROOT%"
exit /b %ERRORLEVEL%
