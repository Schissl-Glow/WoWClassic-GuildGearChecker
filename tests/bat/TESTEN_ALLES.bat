@echo off
setlocal EnableExtensions EnableDelayedExpansion
for %%I in ("%~dp0..\..") do set "REPO_ROOT=%%~fI"
cd /d "%REPO_ROOT%"
set "TEST_BAT_DIR=%REPO_ROOT%\tests\bat"

set "RESULT_DIR=%REPO_ROOT%\test_results"
set "FAILURE_REPORT=%RESULT_DIR%\CODEX_FAILURE_REPORT.md"
if not exist "%RESULT_DIR%" mkdir "%RESULT_DIR%"
del /q "%RESULT_DIR%\group_*.log" >nul 2>&1

set /a TEST_TOTAL=0
set /a TEST_PASS=0
set /a TEST_FAIL=0
set /a TEST_SKIP=0
set "GGC_DISABLE_ICON_DOWNLOAD=1"

>"%FAILURE_REPORT%" echo # GuildGearChecker - Codex Failure Report
>>"%FAILURE_REPORT%" echo.
>>"%FAILURE_REPORT%" echo Vollstaendiger Lauf: %DATE% %TIME%
>>"%FAILURE_REPORT%" echo.

call "%REPO_ROOT%\tools\_FIND_QT_PYTHON.cmd"
if not defined GGC_QT_PYTHON goto :NO_PYTHON

set "GGC_PYTHON=%GGC_QT_PYTHON%"
set "PATH=%GGC_QT_ENV%;%GGC_QT_ENV%Scripts;%GGC_QT_ENV%Library\bin;%SystemRoot%\System32;%SystemRoot%;%SystemRoot%\System32\Wbem"
set "PYTHONHOME="
set "PYTHONPATH="
set "QT_PLUGIN_PATH="

echo ============================================================
echo WoWClassic-GuildGearChecker v0.11.3 Tester - Gesamttest
echo ============================================================
echo Python:
echo   %GGC_PYTHON%
echo Umgebung:
echo   %GGC_QT_ENV%
echo.

set "TEST_ENTRY=Python 3.12+, PySide6, Pillow, Tkinter und Playwright"
set "TEST_COMMAND="%GGC_PYTHON%" -B -X utf8 -c "import sys, tkinter, PySide6, PIL, playwright; assert sys.version_info[:2] ^>= (3, 12); print('Python:', sys.version.split()[0]); print('PySide6:', PySide6.__version__); print('Pillow:', PIL.__version__); print('Tkinter: OK'); print('Playwright-Modul: OK')""
call :RUN_TEST "Umgebung und Voraussetzungen"
if not "!TEST_LAST_RC!"=="0" goto :SUMMARY

set "TEST_ENTRY=Alle Python-Dateien unter app, tests und tools/gravestone_review"
set "TEST_COMMAND="%GGC_PYTHON%" -B -X utf8 -c "from pathlib import Path; roots=(Path('app'),Path('tests'),Path('tools/gravestone_review')); files=sorted(p for root in roots for p in root.rglob('*.py')); reference=Path('docs/reference/GuildPortraitGrabber_v0.1.2_ORIGINAL.py'); files.append(reference); [compile(p.read_text(encoding='utf-8-sig'), str(p), 'exec') for p in files]; print('Compile: OK -', len(files), 'Dateien')""
call :RUN_TEST "Syntax und Compile"

set "TEST_ENTRY=tests/suite_tests.py --core"
set "TEST_COMMAND="%GGC_PYTHON%" -B -X utf8 "%REPO_ROOT%\tests\suite_tests.py" --core"
call :RUN_TEST "Core und App-Self-Tests"

set "TEST_ENTRY=tests\bat\TESTEN_SPIELER_MODELL.bat"
set "TEST_COMMAND="%TEST_BAT_DIR%\TESTEN_SPIELER_MODELL.bat" "%GGC_PYTHON%" "%REPO_ROOT%"
call :RUN_TEST "Spieler-Modell"

set "TEST_ENTRY=tests\bat\TESTEN_NAMENSINKARNATIONEN.bat"
set "TEST_COMMAND="%TEST_BAT_DIR%\TESTEN_NAMENSINKARNATIONEN.bat" "%GGC_PYTHON%" "%REPO_ROOT%"
call :RUN_TEST "Namensinkarnationen"

set "TEST_ENTRY=tests\bat\TESTEN_PROJEKT_SPEICHERUNG.bat"
set "TEST_COMMAND="%TEST_BAT_DIR%\TESTEN_PROJEKT_SPEICHERUNG.bat" "%GGC_PYTHON%"
call :RUN_TEST "Projekt-Storage und Recovery"

set "TEST_ENTRY=tests/project_handoff_tests.py"
set "TEST_COMMAND="%GGC_PYTHON%" -B -X utf8 "%REPO_ROOT%\tests\project_handoff_tests.py" --repo-root "%REPO_ROOT%"
call :RUN_TEST "Projekt-Handoff"

set "TEST_ENTRY=tests\bat\TESTEN_PROJEKT_PORTRAITS.bat"
set "TEST_COMMAND="%TEST_BAT_DIR%\TESTEN_PROJEKT_PORTRAITS.bat" "%GGC_PYTHON%" "%REPO_ROOT%"
call :RUN_TEST "Projekt-Portraits"

set "TEST_ENTRY=tests\bat\TESTEN_SORTIERUNG.bat"
set "TEST_COMMAND="%TEST_BAT_DIR%\TESTEN_SORTIERUNG.bat" "%GGC_PYTHON%" "%REPO_ROOT%"
call :RUN_TEST "Sortierung"

set "TEST_ENTRY=tests\bat\TESTEN_ROSTER.bat"
set "TEST_COMMAND="%TEST_BAT_DIR%\TESTEN_ROSTER.bat" "%GGC_PYTHON%" "%REPO_ROOT%"
call :RUN_TEST "Roster"

set "TEST_ENTRY=tests\bat\TESTEN_BLOCK4.bat"
set "TEST_COMMAND="%TEST_BAT_DIR%\TESTEN_BLOCK4.bat" "%GGC_PYTHON%"
call :RUN_TEST "Fenster, Roster-Zoom und PNG-Export"

set "TEST_ENTRY=tests\bat\TESTEN_V061_FUNKTIONEN.bat"
set "TEST_COMMAND="%TEST_BAT_DIR%\TESTEN_V061_FUNKTIONEN.bat" "%GGC_PYTHON%"
call :RUN_TEST "Leere Projekte, Verwaltung und Armory-Daten"

set "TEST_ENTRY=tests\bat\TESTEN_RAID_ATTENDANCE.bat"
set "TEST_COMMAND="%TEST_BAT_DIR%\TESTEN_RAID_ATTENDANCE.bat" "%GGC_PYTHON%" "%REPO_ROOT%"
call :RUN_TEST "Raid Attendance"

set "TEST_ENTRY=tests/clm_history_tests.py"
set "TEST_COMMAND="%GGC_PYTHON%" -B -X utf8 "%REPO_ROOT%\tests\clm_history_tests.py""
call :RUN_TEST "CLM-Raidhistorie und Eternal DKP"

set "TEST_ENTRY=tests\bat\TESTEN_GEAR_RECHECK.bat"
set "TEST_COMMAND="%TEST_BAT_DIR%\TESTEN_GEAR_RECHECK.bat" "%GGC_PYTHON%"
call :RUN_TEST "Gear-Recheck"

set "TEST_ENTRY=tests\bat\TESTEN_GILDENABGLEICH.bat"
set "TEST_COMMAND="%TEST_BAT_DIR%\TESTEN_GILDENABGLEICH.bat" "%GGC_PYTHON%"
call :RUN_TEST "Gildenabgleich"

set "TEST_ENTRY=tests\bat\TESTEN_CHARACTER_CACHE.bat"
set "TEST_COMMAND="%TEST_BAT_DIR%\TESTEN_CHARACTER_CACHE.bat" "%GGC_PYTHON%"
call :RUN_TEST "Character Cache"

set "TEST_ENTRY=tests\bat\TESTEN_GRABBER_UI.bat"
set "TEST_COMMAND="%TEST_BAT_DIR%\TESTEN_GRABBER_UI.bat" "%GGC_PYTHON%"
call :RUN_TEST "Portrait Grabber UI"

set "TEST_ENTRY=tests\bat\TESTEN_PROMPT3.bat"
set "TEST_COMMAND="%TEST_BAT_DIR%\TESTEN_PROMPT3.bat" "%GGC_PYTHON%"
call :RUN_TEST "Portraitimport und Review-Integration"

set "TEST_ENTRY=tests\bat\TESTEN_ARMORY_STABILITAET.bat"
set "TEST_COMMAND="%TEST_BAT_DIR%\TESTEN_ARMORY_STABILITAET.bat" "%GGC_PYTHON%" "%REPO_ROOT%"
call :RUN_TEST "Armory-Stabilitaet"

set "TEST_ENTRY=tests\bat\TESTEN_LIFECRAFT.bat"
set "TEST_COMMAND="%TEST_BAT_DIR%\TESTEN_LIFECRAFT.bat" "%GGC_PYTHON%" "%REPO_ROOT%"
call :RUN_TEST "LifeCraft-Fonts"

set "TEST_ENTRY=tests\bat\TESTEN_FRIEDHOF_KARTEN.bat"
set "TEST_COMMAND="%TEST_BAT_DIR%\TESTEN_FRIEDHOF_KARTEN.bat" "%GGC_PYTHON%"
call :RUN_TEST "Friedhofskarten"

set "TEST_ENTRY=tests\bat\TESTEN_FRIEDHOF_TEMPLATE_SYSTEM.bat"
set "TEST_COMMAND="%TEST_BAT_DIR%\TESTEN_FRIEDHOF_TEMPLATE_SYSTEM.bat" "%GGC_PYTHON%"
call :RUN_TEST "Friedhof-Template-System"

set "TEST_ENTRY=tests/graveyard_placeholder_tests.py"
set "TEST_COMMAND="%GGC_PYTHON%" -B -X utf8 "%REPO_ROOT%\tests\graveyard_placeholder_tests.py""
call :RUN_TEST "Friedhof-Placeholder"

set "TEST_ENTRY=tests/gravestone_category_tests.py"
set "TEST_COMMAND="%GGC_PYTHON%" -B -X utf8 "%REPO_ROOT%\tests\gravestone_category_tests.py""
call :RUN_TEST "Grabstein-Kategorien"

set "TEST_ENTRY=tests\bat\TESTEN_GRABSTEIN_UEBERNAHME.bat"
set "TEST_COMMAND="%TEST_BAT_DIR%\TESTEN_GRABSTEIN_UEBERNAHME.bat" "%GGC_PYTHON%"
call :RUN_TEST "Grabstein-Promotion"

set "TEST_ENTRY=tests\bat\TESTEN_GRABSTEIN_REVIEW_UI.bat"
rem Der Review-UI-Test ist ein Tkinter-Test.  Ohne erzwungenen Qt-Python-Pfad
rem wählt sein vorhandener Starter die vollständige Miniforge-Tk-Umgebung.
set "TEST_COMMAND="%TEST_BAT_DIR%\TESTEN_GRABSTEIN_REVIEW_UI.bat"
call :RUN_TEST "Gravestone Review UI"

set "TEST_ENTRY=tests/gravestone_review_alpha_tests.py"
set "TEST_COMMAND="%GGC_PYTHON%" -B -X utf8 "%REPO_ROOT%\tests\gravestone_review_alpha_tests.py""
call :RUN_TEST "Gravestone Review Alpha"

set "TEST_ENTRY=tools/gravestone_review/gravestone_review_tool.py --self-test"
set "TEST_COMMAND="%GGC_PYTHON%" -B -X utf8 "%REPO_ROOT%\tools\gravestone_review\gravestone_review_tool.py" --self-test"
call :RUN_TEST "Gravestone Review Self-Test"

set "TEST_ENTRY=tests\bat\TESTEN_I18N.bat"
set "TEST_COMMAND="%TEST_BAT_DIR%\TESTEN_I18N.bat" "%GGC_PYTHON%" "%REPO_ROOT%"
call :RUN_TEST "Deutsch und Englisch"

set "TEST_ENTRY=tests/qt_checker_smoke.py"
set "TEST_COMMAND=set QT_QPA_PLATFORM=offscreen ^&^& "%GGC_PYTHON%" -B -X utf8 "%REPO_ROOT%\tests\qt_checker_smoke.py""
call :RUN_TEST "Qt-Offscreen-Smoke"

set "TEST_ENTRY=tests/suite_tests.py --ui"
set "TEST_COMMAND="%GGC_PYTHON%" -B -X utf8 "%REPO_ROOT%\tests\suite_tests.py" --ui"
call :RUN_TEST "Tk-UI und Scroll-Smoke"

set "TEST_ENTRY=tests/suite_tests.py --playwright"
set "TEST_COMMAND="%GGC_PYTHON%" -B -X utf8 "%REPO_ROOT%\tests\suite_tests.py" --playwright"
call :RUN_TEST "Playwright-Browser-Smoke"

set "TEST_ENTRY=tests\bat\TESTEN_PROJEKT_PAKET.bat"
set "TEST_COMMAND="%TEST_BAT_DIR%\TESTEN_PROJEKT_PAKET.bat" "%GGC_PYTHON%"
call :RUN_TEST "Projektpaket und ZIP-Integritaet"

goto :SUMMARY

:RUN_TEST
set /a TEST_TOTAL+=1
set "TEST_LABEL=%~1"
set "TEST_LOG=%RESULT_DIR%\group_!TEST_TOTAL!.log"
echo [!TEST_TOTAL!] !TEST_LABEL!
cmd.exe /d /s /c "!TEST_COMMAND!" >"!TEST_LOG!" 2>&1
set "TEST_LAST_RC=!ERRORLEVEL!"
type "!TEST_LOG!"
if "!TEST_LAST_RC!"=="0" (
    set /a TEST_PASS+=1
    echo PASS: !TEST_LABEL!
) else (
    set /a TEST_FAIL+=1
    echo FAIL: !TEST_LABEL! ^(Exit-Code !TEST_LAST_RC!^)
    call :REMOVE_NO_FAILURES
    >>"%FAILURE_REPORT%" echo ## FAIL: !TEST_LABEL!
    >>"%FAILURE_REPORT%" echo.
    >>"%FAILURE_REPORT%" echo - Einstieg: `!TEST_ENTRY!`
    >>"%FAILURE_REPORT%" echo - Exit-Code: `!TEST_LAST_RC!`
    >>"%FAILURE_REPORT%" echo - Vollstaendige Ausgabe: `test_results/group_!TEST_TOTAL!.log`
    >>"%FAILURE_REPORT%" echo.
    >>"%FAILURE_REPORT%" echo Relevante Fehlermeldungen:
    >>"%FAILURE_REPORT%" echo.
    >>"%FAILURE_REPORT%" echo ```text
    findstr /i /c:"Traceback" /c:"Assertion" /c:"Exception" /c:"Error" /c:"FAIL" "!TEST_LOG!" >>"%FAILURE_REPORT%" 2>nul
    if errorlevel 1 >>"%FAILURE_REPORT%" echo Keine automatisch extrahierbare Fehlerzeile; vollstaendiges Gruppenlog verwenden.
    >>"%FAILURE_REPORT%" echo ```
    >>"%FAILURE_REPORT%" echo.
)
echo.
exit /b 0

:NO_PYTHON
set /a TEST_TOTAL=1
set /a TEST_FAIL=1
>>"%FAILURE_REPORT%" echo ## FAIL: Umgebung und Voraussetzungen
>>"%FAILURE_REPORT%" echo.
>>"%FAILURE_REPORT%" echo - Einstieg: `tools/_FIND_QT_PYTHON.cmd`
>>"%FAILURE_REPORT%" echo - Exit-Code: `2`
>>"%FAILURE_REPORT%" echo - Fehler: Keine funktionsfaehige Python-3.12+-Umgebung mit PySide6 und Pillow unter `%LOCALAPPDATA%/GuildGearChecker/qt_env` gefunden.
goto :SUMMARY

:SUMMARY
call :REMOVE_NO_FAILURES
if "%TEST_FAIL%"=="0" (
    >>"%FAILURE_REPORT%" echo NO FAILURES
)

echo ============================================================
echo GuildGearChecker - Gesamttest
echo.
echo Testgruppen: %TEST_TOTAL%
echo PASS: %TEST_PASS%
echo FAIL: %TEST_FAIL%
echo SKIP: %TEST_SKIP%
echo.
if not "%TEST_FAIL%"=="0" (
    echo FEHLGESCHLAGEN:
    findstr /b /c:"## FAIL:" "%FAILURE_REPORT%"
    echo.
    echo GESAMTSTATUS: FEHLGESCHLAGEN
    echo Fehlerbericht:
    echo   %FAILURE_REPORT%
    endlocal & exit /b 1
)

echo GESAMTSTATUS: BESTANDEN
echo Fehlerbericht:
echo   %FAILURE_REPORT%
endlocal & exit /b 0

:REMOVE_NO_FAILURES
if not exist "%FAILURE_REPORT%" exit /b 0
findstr /v /x /c:"NO FAILURES" "%FAILURE_REPORT%" > "%FAILURE_REPORT%.tmp"
move /y "%FAILURE_REPORT%.tmp" "%FAILURE_REPORT%" >nul
exit /b 0
