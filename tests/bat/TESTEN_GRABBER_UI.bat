@echo off
setlocal EnableExtensions
for %%I in ("%~dp0..\..") do set "REPO_ROOT=%%~fI"
cd /d "%REPO_ROOT%"
set "TEST_PYTHON=%~1"
if not defined TEST_PYTHON set "TEST_PYTHON=C:\ProgramData\miniforge3\python.exe"
"%TEST_PYTHON%" "%REPO_ROOT%\tests\grabber_ui_tests.py" --repo-root "%REPO_ROOT%"
exit /b %errorlevel%
