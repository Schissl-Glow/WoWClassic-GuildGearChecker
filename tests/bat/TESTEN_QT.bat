@echo off
setlocal EnableExtensions
for %%I in ("%~dp0..\..") do set "REPO_ROOT=%%~fI"
cd /d "%REPO_ROOT%"
title Guild Gear Checker v0.12.0 - Qt Kurztest
call "%REPO_ROOT%\tools\_FIND_QT_PYTHON.cmd"
if not defined GGC_QT_PYTHON goto :NO_PYTHON
set "PATH=%GGC_QT_ENV%;%GGC_QT_ENV%Scripts;%GGC_QT_ENV%Library\bin;%SystemRoot%\System32;%SystemRoot%;%SystemRoot%\System32\Wbem"
set "PYTHONHOME="
set "PYTHONPATH="
set "QT_PLUGIN_PATH="
echo Verwendetes Qt-Python:
echo   %GGC_QT_PYTHON%
echo Qt-Umgebung:
echo   %GGC_QT_ENV%
echo.
echo [1/8] Python / PySide6.QtCore / PySide6.QtWidgets / Pillow
"%GGC_QT_PYTHON%" -c "import sys, PySide6; from PySide6.QtCore import QCoreApplication; from PySide6.QtWidgets import QApplication; from PIL import Image; print('Python:', sys.executable); print('Version:', sys.version.split()[0]); print('PySide6:', PySide6.__version__); print('QtCore/QtWidgets: OK'); print('Pillow: OK')"
if errorlevel 1 goto :FAIL
echo.
echo [2/8] Tkinter-Kompatibilitaet der noch gemeinsam genutzten Legacy-Logik
"%GGC_QT_PYTHON%" -c "import tkinter; print('tkinter: OK')"
if errorlevel 1 goto :FAIL
echo.
echo [3/8] Compile Qt-Checker
"%GGC_QT_PYTHON%" -B -c "from pathlib import Path; compile(Path(r'%REPO_ROOT%\app\GuildGearCheckerQt.py').read_text(encoding='utf-8'), r'%REPO_ROOT%\app\GuildGearCheckerQt.py', 'exec'); print('Compile: OK')"
if errorlevel 1 goto :FAIL
echo.
echo [4/8] Import Qt-Checker
"%GGC_QT_PYTHON%" -c "import os, sys; sys.path.insert(0, os.getcwd()); import app.GuildGearCheckerQt; print('Qt-Checker Import: OK')"
if errorlevel 1 goto :FAIL
echo.
echo [5/8] Qt-Offscreen-Smoke
set "QT_QPA_PLATFORM=offscreen"
if exist "%SystemRoot%\Fonts" set "QT_QPA_FONTDIR=%SystemRoot%\Fonts"
"%GGC_QT_PYTHON%" "%REPO_ROOT%\tests\qt_checker_smoke.py"
if errorlevel 1 goto :FAIL
set "QT_QPA_PLATFORM="
set "QT_QPA_FONTDIR="
echo.
echo [6/8] Launcher-Offscreen-Tests
"%GGC_QT_PYTHON%" -B -X utf8 -m unittest tests.launcher_ui_tests
if errorlevel 1 goto :FAIL
echo.
echo [7/8] CLM-Erstimport und Roster-Auswahl
"%GGC_QT_PYTHON%" -B -X utf8 -m unittest tests.clm_v2_initialization_ui_tests
if errorlevel 1 goto :FAIL
echo.
echo [8/8] Legacy-Core-Selftest
"%GGC_QT_PYTHON%" "%REPO_ROOT%\app\GuildGearChecker.py" --self-test
if errorlevel 1 goto :FAIL
echo.
echo ============================================================
echo   Qt-Kurztest erfolgreich.
echo ============================================================
pause
exit /b 0
:NO_PYTHON
echo.
echo Keine funktionsfaehige Python-Umgebung mit PySide6 am erwarteten Pfad gefunden.
echo.
echo Bitte auf DIESEM Computer zuerst ausfuehren:
echo   INSTALLIEREN.bat
echo.
echo Der Installer legt die Umgebung benutzerspezifisch an:
echo   %LOCALAPPDATA%\GuildGearChecker\qt_env
echo.
pause
exit /b 1
:FAIL
set "QT_QPA_PLATFORM="
set "QT_QPA_FONTDIR="
echo.
echo ============================================================
echo   Qt-Kurztest fehlgeschlagen.
echo ============================================================
echo Bitte die komplette Ausgabe senden.
echo.
pause
exit /b 2
