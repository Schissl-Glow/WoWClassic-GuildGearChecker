@echo off
setlocal EnableExtensions
for %%I in ("%~dp0..\..") do set "REPO_ROOT=%%~fI"
cd /d "%REPO_ROOT%"
set "TEST_PYTHON=%~1"
if not defined TEST_PYTHON call "%REPO_ROOT%\tools\_FIND_MINIFORGE.cmd"
if not defined TEST_PYTHON set "TEST_PYTHON=%GGC_PYTHON%"
if not defined TEST_PYTHON exit /b 1
"%TEST_PYTHON%" "%REPO_ROOT%\tests\project_storage_tests.py" --repo-root "%REPO_ROOT%"
exit /b %errorlevel%
