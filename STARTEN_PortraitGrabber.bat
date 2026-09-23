@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Guild Portrait Grabber v0.11.3-test3 Tester - Qt

call "%~dp0tools\_FIND_QT_PYTHON.cmd"
if not defined GGC_QT_PYTHON goto :NO_QT_PYTHON

set "PATH=%GGC_QT_ENV%;%GGC_QT_ENV%Scripts;%GGC_QT_ENV%Library\bin;%SystemRoot%\System32;%SystemRoot%;%SystemRoot%\System32\Wbem"
set "PYTHONHOME="
set "PYTHONPATH="
set "QT_PLUGIN_PATH="

echo ============================================================
echo   Guild Portrait Grabber v0.11.3-test3 Tester - Qt
echo ============================================================
echo.
"%GGC_QT_PYTHON%" "%~dp0app\GuildPortraitGrabberQt.py" %*
exit /b %errorlevel%

:NO_QT_PYTHON
echo.
echo Keine funktionsfaehige PySide6-Umgebung gefunden:
echo   %LOCALAPPDATA%\GuildGearChecker\qt_env
echo.
echo Bitte zuerst INSTALLIEREN.bat ausfuehren.
pause
exit /b 2
