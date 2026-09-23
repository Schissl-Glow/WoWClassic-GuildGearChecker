@echo off
set "GGC_CONDA="

REM Locate a real Conda/Miniforge installation without relying on a specific
REM Windows user name or machine path.
if defined CONDA_EXE call :TRY "%CONDA_EXE%"
if defined GGC_CONDA goto :EOF

if defined CONDA_PREFIX (
    call :TRY "%CONDA_PREFIX%\Scripts\conda.exe"
    if defined GGC_CONDA goto :EOF
    call :TRY "%CONDA_PREFIX%\..\Scripts\conda.exe"
    if defined GGC_CONDA goto :EOF
)

call :TRY "%USERPROFILE%\miniforge3\Scripts\conda.exe"
if defined GGC_CONDA goto :EOF
call :TRY "%USERPROFILE%\Miniforge3\Scripts\conda.exe"
if defined GGC_CONDA goto :EOF
call :TRY "%LOCALAPPDATA%\miniforge3\Scripts\conda.exe"
if defined GGC_CONDA goto :EOF
call :TRY "%LOCALAPPDATA%\Miniforge3\Scripts\conda.exe"
if defined GGC_CONDA goto :EOF
call :TRY "%LOCALAPPDATA%\Programs\miniforge3\Scripts\conda.exe"
if defined GGC_CONDA goto :EOF
call :TRY "%PROGRAMDATA%\miniforge3\Scripts\conda.exe"
if defined GGC_CONDA goto :EOF
call :TRY "%PROGRAMFILES%\miniforge3\Scripts\conda.exe"
if defined GGC_CONDA goto :EOF
call :TRY "C:\miniforge3\Scripts\conda.exe"
if defined GGC_CONDA goto :EOF
call :TRY "C:\Miniforge3\Scripts\conda.exe"
if defined GGC_CONDA goto :EOF
call :TRY "%USERPROFILE%\mambaforge\Scripts\conda.exe"
if defined GGC_CONDA goto :EOF

for /f "delims=" %%C in ('where conda.exe 2^>nul') do call :TRY "%%C"
if defined GGC_CONDA goto :EOF
for /f "delims=" %%C in ('where conda.bat 2^>nul') do call :TRY "%%C"
if defined GGC_CONDA goto :EOF

goto :EOF

:TRY
if defined GGC_CONDA goto :EOF
if not exist "%~1" goto :EOF
set "GGC_CONDA=%~1"
goto :EOF
