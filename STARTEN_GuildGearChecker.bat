@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Guild Gear Checker v0.12.1 - Qt

call "%~dp0tools\_FIND_QT_PYTHON.cmd"
if not defined GGC_QT_PYTHON goto :NO_QT_PYTHON

set "PATH=%GGC_QT_ENV%;%GGC_QT_ENV%Scripts;%GGC_QT_ENV%Library\bin;%SystemRoot%\System32;%SystemRoot%;%SystemRoot%\System32\Wbem"
set "PYTHONHOME="
set "PYTHONPATH="
set "QT_PLUGIN_PATH="

echo ============================================================
echo   Guild Gear Checker v0.12.1 - Qt
echo ============================================================
echo.
echo Verwendetes Python:
echo   %GGC_QT_PYTHON%
echo Qt-Umgebung:
echo   %GGC_QT_ENV%
echo.

echo Starte PySide6-Startmenue ...
echo.
"%GGC_QT_PYTHON%" "%~dp0app\launcher_qt.py"
set "RC=%ERRORLEVEL%"

if "%RC%"=="0" exit /b 0

echo.
echo Pruefe QtCore/QtWidgets DLLs zur Fehlerdiagnose ...
"%GGC_QT_PYTHON%" -c "from PySide6.QtCore import QCoreApplication; from PySide6.QtWidgets import QApplication; import PySide6; print('PySide6:', PySide6.__version__); print('Qt DLL-Test: OK')"
if errorlevel 1 goto :DLL_FAIL

echo.
echo ============================================================
echo   START FEHLGESCHLAGEN - Exitcode %RC%
echo ============================================================
echo.
echo Falls oben ein Traceback steht, bitte die komplette Ausgabe senden.
echo Zusaetzlich pruefen:
echo   logs\qt_startup_error.log
echo.
pause
exit /b %RC%

:DLL_FAIL
echo.
echo ============================================================
echo   Qt-DLL-Test fehlgeschlagen.
echo ============================================================
echo.
echo Bitte INSTALLIEREN.bat erneut ausfuehren. Der Installer repariert die
 echo projektlokale Qt-Umgebung bei Bedarf.
echo.
pause
exit /b 3

:NO_QT_PYTHON
echo.
echo ============================================================
echo   Keine funktionsfaehige PySide6-Umgebung gefunden.
echo ============================================================
echo.
echo Unter dem erwarteten Pfad wurde noch keine lauffaehige Qt-Umgebung gefunden:
echo   %LOCALAPPDATA%\GuildGearChecker\qt_env
echo.
echo Bitte zuerst ausfuehren:
echo   INSTALLIEREN.bat
echo.
echo Der Installer erstellt automatisch eine benutzerspezifische Umgebung unter:
echo   %LOCALAPPDATA%\GuildGearChecker\qt_env
echo.
echo Dadurch wird der lange Release-Pfad nicht fuer die Qt-Umgebung verwendet.
echo.
pause
exit /b 2
