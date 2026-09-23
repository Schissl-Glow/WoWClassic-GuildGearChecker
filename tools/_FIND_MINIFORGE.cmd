@echo off
set "GGC_PYTHON="

if defined CONDA_PREFIX call :TRY "%CONDA_PREFIX%\python.exe"
if defined GGC_PYTHON goto :EOF
if defined CONDA_PYTHON_EXE call :TRY "%CONDA_PYTHON_EXE%"
if defined GGC_PYTHON goto :EOF

call :TRY "%USERPROFILE%\miniforge3\python.exe"
if defined GGC_PYTHON goto :EOF
call :TRY "%USERPROFILE%\Miniforge3\python.exe"
if defined GGC_PYTHON goto :EOF
call :TRY "%LOCALAPPDATA%\miniforge3\python.exe"
if defined GGC_PYTHON goto :EOF
call :TRY "%LOCALAPPDATA%\Miniforge3\python.exe"
if defined GGC_PYTHON goto :EOF
call :TRY "%LOCALAPPDATA%\Programs\miniforge3\python.exe"
if defined GGC_PYTHON goto :EOF
call :TRY "%PROGRAMDATA%\miniforge3\python.exe"
if defined GGC_PYTHON goto :EOF
call :TRY "%PROGRAMFILES%\miniforge3\python.exe"
if defined GGC_PYTHON goto :EOF
call :TRY "C:\miniforge3\python.exe"
if defined GGC_PYTHON goto :EOF
call :TRY "C:\Miniforge3\python.exe"
if defined GGC_PYTHON goto :EOF
call :TRY "%USERPROFILE%\mambaforge\python.exe"
if defined GGC_PYTHON goto :EOF

for /f "delims=" %%P in ('where python.exe 2^>nul') do call :TRY "%%P"
if defined GGC_PYTHON goto :EOF

for /f "usebackq delims=" %%B in (`conda info --base 2^>nul`) do call :TRY "%%B\python.exe"
goto :EOF

:TRY
if defined GGC_PYTHON goto :EOF
if not exist "%~1" goto :EOF
"%~1" -c "import sys; raise SystemExit(0 if sys.version_info >= (3,12) else 1)" >nul 2>&1
if errorlevel 1 goto :EOF
set "GGC_PYTHON=%~1"
goto :EOF
