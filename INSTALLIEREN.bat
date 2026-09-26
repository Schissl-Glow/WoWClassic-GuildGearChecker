@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title WoWClassic-GuildGearChecker v0.12.1 - Installation

set "ENV_DIR=%LOCALAPPDATA%\GuildGearChecker\qt_env"
set "GGC_QT_PYTHON=%ENV_DIR%\python.exe"

call "%~dp0tools\_FIND_CONDA.cmd"
if not defined GGC_CONDA goto :NO_CONDA

echo ============================================================
echo   WoWClassic-GuildGearChecker v0.12.1 - lokale Qt-Installation
echo ============================================================
echo.
echo Diese Installation verwendet eine kurze benutzerspezifische Qt-Umgebung:
echo   %ENV_DIR%
echo.
echo Verwendetes Conda:
echo   %GGC_CONDA%
echo.

if exist "%GGC_QT_PYTHON%" goto :REPAIR_ENV

echo [1/8] Erstelle lokale Python-3.12-Umgebung ...
call "%GGC_CONDA%" create -y -p "%ENV_DIR%" python=3.12 pip
if errorlevel 1 goto :FAIL

goto :PIP

:REPAIR_ENV
echo [1/8] Lokale Umgebung vorhanden - pruefe/repariere Python 3.12 ...
call "%GGC_CONDA%" install -y -p "%ENV_DIR%" python=3.12 pip
if errorlevel 1 goto :FAIL

:PIP
echo.
echo [2/8] Aktualisiere pip ...
"%GGC_QT_PYTHON%" -m pip install --upgrade pip
if errorlevel 1 goto :FAIL

echo.
echo [3/8] Installiere Checker-Abhaengigkeiten ...
"%GGC_QT_PYTHON%" -m pip install --upgrade -r "%~dp0tools\requirements.txt"
if errorlevel 1 goto :FAIL

echo.
echo [4/8] Pruefe echte Qt-DLL-Imports ...
call :SET_LOCAL_DLL_PATH
call :QT_IMPORT_TEST
if not errorlevel 1 goto :ICONS

echo.
echo Qt-Import ist fehlgeschlagen. Repariere PySide6 einmal sauber ...
"%GGC_QT_PYTHON%" -m pip install --no-cache-dir --force-reinstall "PySide6==6.11.2"
if errorlevel 1 goto :FAIL
call :SET_LOCAL_DLL_PATH
call :QT_IMPORT_TEST
if errorlevel 1 goto :QT_FAIL

:ICONS
echo.
echo [5/8] Lade/aktualisiere WoW Class-Icons ...
"%GGC_QT_PYTHON%" "%~dp0app\download_class_icons.py" --force
if errorlevel 1 (
    echo HINWEIS: Nicht alle Class-Icons konnten geladen werden.
    echo Die Anwendung nutzt fuer fehlende Icons die Offline-Fallbacks.
)

echo.
echo [6/8] Installiere Playwright Chromium als Browser-Fallback ...
"%GGC_QT_PYTHON%" -m playwright install chromium
if errorlevel 1 (
    echo HINWEIS: Chromium-Fallback konnte nicht installiert werden.
    echo Edge/Chrome koennen trotzdem funktionieren.
)

echo.
echo [7/8] Teste QApplication im Offscreen-Modus ...
set "QT_QPA_PLATFORM=offscreen"
"%GGC_QT_PYTHON%" -c "from PySide6.QtWidgets import QApplication, QWidget; app=QApplication([]); w=QWidget(); print('QApplication: OK')"
set "QT_QPA_PLATFORM="
if errorlevel 1 goto :QT_FAIL

echo.
echo [8/8] Abschlusspruefung ...
"%GGC_QT_PYTHON%" -c "import sys, PySide6; from PySide6.QtCore import qVersion; from PIL import Image; print('Python:', sys.version.split()[0]); print('PySide6:', PySide6.__version__); print('Qt:', qVersion()); print('Pillow: OK')"
if errorlevel 1 goto :FAIL

echo.
echo ============================================================
echo   INSTALLATION ERFOLGREICH
echo ============================================================
echo.
echo Der Checker verwendet auf DIESEM Computer kuenftig automatisch:
echo   %GGC_QT_PYTHON%
echo.
echo Die Qt-Umgebung wird benutzerspezifisch unter diesem Pfad weiterverwendet:
echo   %ENV_DIR%
echo Danach kannst du tests\bat\TESTEN_QT.bat und STARTEN_GuildGearChecker.bat nutzen.
echo.
pause
exit /b 0

:SET_LOCAL_DLL_PATH
set "PATH=%ENV_DIR%;%ENV_DIR%\Scripts;%ENV_DIR%\Library\bin;%SystemRoot%\System32;%SystemRoot%;%SystemRoot%\System32\Wbem"
set "PYTHONHOME="
set "PYTHONPATH="
set "QT_PLUGIN_PATH="
exit /b 0

:QT_IMPORT_TEST
"%GGC_QT_PYTHON%" -c "import sys, PySide6; from PySide6.QtCore import QCoreApplication, qVersion; from PySide6.QtWidgets import QApplication; from PIL import Image; print('Python:', sys.executable); print('PySide6:', PySide6.__version__); print('Qt:', qVersion()); print('QtCore/QtWidgets/Pillow: OK')"
exit /b %ERRORLEVEL%

:NO_CONDA
echo ============================================================
echo   Miniforge / Conda wurde nicht gefunden.
echo ============================================================
echo.
echo Fuer diese Preview wird noch KEINE EXE ausgeliefert.
echo Deshalb muss auf diesem Computer Miniforge/Conda vorhanden sein.
echo.
echo Installiere Miniforge oder starte diese BAT aus einer Miniforge Prompt.
echo Danach INSTALLIEREN.bat erneut ausfuehren.
echo.
pause
exit /b 1

:QT_FAIL
echo.
echo ============================================================
echo   Qt konnte trotz Reparatur nicht geladen werden.
echo ============================================================
echo.
echo Die lokale Umgebung liegt hier:
echo   %ENV_DIR%
echo.
echo Wenn du sie komplett neu aufbauen willst, kannst du den Ordner
 echo   %ENV_DIR%
 echo loeschen und INSTALLIEREN.bat erneut starten.
echo.
pause
exit /b 3

:FAIL
echo.
echo ============================================================
echo   INSTALLATION FEHLGESCHLAGEN
echo ============================================================
echo.
echo Bitte die komplette Ausgabe senden.
echo.
pause
exit /b 2
