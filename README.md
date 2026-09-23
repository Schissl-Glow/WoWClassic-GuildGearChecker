<p align="center">
  <img src="assets/checker_banner.png" alt="Bierstuben – GuildGearChecker" width="100%">
</p>

<h1 align="center">Bierstuben – GuildGearChecker</h1>

<p align="center">
  Guild-Management und Raid-Organisation für World of Warcraft Classic.
</p>

<p align="center">
  <img alt="Platform" src="https://img.shields.io/badge/Platform-Windows-0078D4">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.12%2B-3776AB">
  <img alt="GUI" src="https://img.shields.io/badge/GUI-PySide6-41CD52">
  <img alt="Status" src="https://img.shields.io/badge/Status-Active%20Development-orange">
</p>

<p align="center">
  <a href="#funktionen">Funktionen</a> ·
  <a href="#portrait--charakter-info-grabber">Portrait Grabber</a> ·
  <a href="#installation-und-start">Installation</a> ·
  <a href="#firefox-addon--wowloghelper">Firefox Add-on</a> ·
  <a href="CHANGELOG.md">Changelog</a> ·
  <a href="#installation-und-start">Download & Installation</a>
</p>

---

## Über Bierstuben

**Bierstuben – GuildGearChecker** bündelt die Werkzeuge für die Verwaltung einer WoW-Classic-Gilde in einer Desktop-Anwendung. Mitglieder, Charaktere, Roster, Raids, Attendance, Raidpunkte, DKP, Rewards, Portraits und der Friedhof werden innerhalb eines gemeinsamen Projektbestands verwaltet.

Der aktuelle Desktop-Client basiert auf **Python 3.12+ und PySide6/Qt** und wird für Windows entwickelt.

## Aktueller Stand

- **Letzte stabile Basis:** 0.11.2
- **Aktueller Entwicklungsstand:** 0.11.3-test3
- **Hauptbranch:** `main`

Details zu den Änderungen stehen im [Changelog](CHANGELOG.md).

## Funktionen

| Bereich | Enthalten |
| --- | --- |
| **Member & Charaktere** | Mitgliederverwaltung, Main-/Twink-Zuordnung, Spieler- und Charakterdaten |
| **Roster** | Rollenbasierte Roster-Ansicht, Klasseninformationen und Portraits |
| **Raids & Attendance** | Raidverwaltung, Warcraft-Logs-CSV-Import, Anwesenheit und Raidstatistik |
| **Raidpunkte & DKP** | Raidpunkte, manuelle Anpassungen und CLM-/DKP-Unterstützung |
| **Rewards** | Punktbasierte Badges und Rahmen für Charaktere und Spieler |
| **Portraits** | Integrierte Portrait-Erstellung und Verwaltung der Charakterportraits |
| **Friedhof** | Historische Charaktere, Grabsteine, Portraitpositionierung und Review-Workflow |
| **Sprache** | Deutsche und englische Oberfläche |

## Portrait + Charakter Info Grabber

<p align="center">
  <img src="assets/grabber_banner.png" alt="Bierstuben – Portrait + Charakter Info Grabber" width="100%">
</p>

Der **Portrait + Charakter Info Grabber** ist das ergänzende Werkzeug zum GuildGearChecker und arbeitet mit demselben Projektbestand.

Er unterstützt insbesondere:

- Erstellen und Aktualisieren von Charakterportraits
- Bearbeiten von Portraitausschnitt, Position und Zoom
- Ermitteln verfügbarer Charakterinformationen wie **Rasse und Klasse** aus der verwendeten Charakterquelle
- projektbezogene Übergabe der ermittelten Daten an den GuildGearChecker
- Bearbeitung fehlender Portraits und Charakterinformationen
- Portrait- und Friedhofs-Workflows für bestehende Charaktere

Der Grabber wird unter Windows über **`STARTEN_PortraitGrabber.bat`** gestartet.

## Firefox Add-on – WoWLogHelper

Für den Raid-Import steht ein separates Firefox-Add-on zur Verfügung. **WoWLogHelper** unterstützt das Herunterladen der benötigten Warcraft-Logs-CSV-Dateien.

➡️ **[WoWLogHelper bei Firefox Add-ons öffnen](https://addons.mozilla.org/de/developers/addon/wowloghelper/versions)**

Das Add-on wird nicht im GuildGearChecker-Repository mitgeführt. Dadurch bleibt die Browser-Erweiterung unabhängig aktualisierbar und es werden keine veralteten Add-on-Pakete im Projekt abgelegt.

## Installation und Start

### Voraussetzungen

- Windows
- Miniforge / Conda
- Internetzugang für die erstmalige Einrichtung der Abhängigkeiten

Aktuell wird keine eigenständige EXE ausgeliefert. Die mitgelieferte Installation richtet eine lokale Python-/Qt-Umgebung unter dem Benutzerprofil ein.

### Erstinstallation

1. Repository klonen oder vollständig herunterladen.
2. **`INSTALLIEREN.bat`** starten.
3. Nach erfolgreicher Installation optional **`tests\bat\TESTEN_ALLES.bat`** ausführen.
4. **`STARTEN_GuildGearChecker.bat`** starten.

Der Installer richtet Python 3.12, PySide6, Pillow und die benötigten Browser-Komponenten für die vorhandenen Werkzeuge ein.

## Downloads

Fertige Versionen sollen künftig über **GitHub Releases** bereitgestellt werden. Dabei werden nur die aktuelle stabile Version, die vorherige stabile Version und bei Bedarf ein aktueller Teststand gepflegt.

## Projektstruktur

```text
WOW-GuildGearChecker/
├─ app/        Anwendung und Fachlogik
├─ assets/     Banner, Klassenicons, Fonts, Grabsteine und Rewards
├─ config/     lokale Anwendungseinstellungen
├─ data/       lokale Projekte, Portraits, Backups und Laufzeitdaten
├─ docs/       technische Dokumentation und Referenzen
├─ tests/      automatisierte Tests
│  └─ bat/     Teststarter inklusive TESTEN_ALLES.bat
├─ tools/      Hilfs- und Entwicklungswerkzeuge
│  └─ bat/     Wartungs-, Diagnose- und Entwicklerstarter
├─ INSTALLIEREN.bat
├─ STARTEN_GuildGearChecker.bat
└─ STARTEN_PortraitGrabber.bat
```

Lokale Projekte, Portraits, Logs, Backups, temporäre Dateien und Build-/Release-Ausgaben werden über `.gitignore` vom Repository getrennt.

## Tests

Für einen vollständigen lokalen Testlauf:

```text
tests\bat\TESTEN_ALLES.bat
```

Der Gesamttest prüft unter anderem Kernlogik, Projektverwaltung, Roster, Raid Attendance, Raidpunkte, DKP/CLM, Portraits, Friedhof, Lokalisierung und die Qt-Oberfläche.

## Veröffentlichung

Dieses öffentliche Repository enthält ausschließlich freigegebene Stände aus dem privaten Entwicklungsrepository. Entwicklungs-, Experiment- und Backup-Branches werden hier nicht veröffentlicht.

---

<p align="center">
  <strong>Bierstuben – GuildGearChecker</strong><br>
  WoW Classic Guild Management
</p>
