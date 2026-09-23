@echo off
set "GGC_QT_PYTHON="
set "GGC_QT_ENV="

REM Use only the short, per-user Qt environment created by INSTALLIEREN.bat.
set "GGC_QT_ROOT=%LOCALAPPDATA%\GuildGearChecker\qt_env"
call :TRY "%GGC_QT_ROOT%\python.exe"

goto :EOF

:TRY
if defined GGC_QT_PYTHON goto :EOF
if not exist "%~1" goto :EOF

setlocal
set "CANDIDATE=%~1"
set "ENVROOT=%~dp1"
set "PATH=%ENVROOT%;%ENVROOT%Scripts;%ENVROOT%Library\bin;%SystemRoot%\System32;%SystemRoot%;%SystemRoot%\System32\Wbem"
set "PYTHONHOME="
set "PYTHONPATH="
set "QT_PLUGIN_PATH="

"%CANDIDATE%" -c "import sys; from PySide6.QtCore import QCoreApplication; from PySide6.QtWidgets import QApplication; from PIL import Image; raise SystemExit(0 if sys.version_info >= (3,12) else 1)" >nul 2>&1
if errorlevel 1 (
    endlocal
    goto :EOF
)

endlocal & set "GGC_QT_PYTHON=%~1" & set "GGC_QT_ENV=%~dp1"
goto :EOF
