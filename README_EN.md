<p align="center">
  <a href="README.md">🇩🇪 Deutsch</a> · <strong>🇬🇧 English</strong>
</p>

<p align="center">
  <img src="assets/checker_banner.png" alt="WoWClassic-GuildGearChecker" width="100%">
</p>

<h1 align="center"><a href="https://github.com/Schissl-Glow/WoWClassic-GuildGearChecker"><strong>WoWClassic-GuildGearChecker</strong></a></h1>

<p align="center">
  Guild management and raid organization for World of Warcraft Classic.
</p>

<p align="center">
  <img alt="Platform" src="https://img.shields.io/badge/Platform-Windows-0078D4">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.12%2B-3776AB">
  <img alt="GUI" src="https://img.shields.io/badge/GUI-PySide6-41CD52">
  <img alt="Status" src="https://img.shields.io/badge/Status-Active%20Development-orange">
</p>

<p align="center">
  <a href="#features">Features</a> ·
  <a href="#portrait--character-info-grabber">Portrait Grabber</a> ·
  <a href="#installation-and-start">Installation</a> ·
  <a href="#firefox-add-on--wowloghelper">Firefox Add-on</a> ·
  <a href="CHANGELOG.md">Changelog</a> ·
  <a href="#installation-and-start">Download & Installation</a>
</p>

---

## About WoWClassic-GuildGearChecker

[**WoWClassic-GuildGearChecker**](https://github.com/Schissl-Glow/WoWClassic-GuildGearChecker) combines the tools needed to manage a WoW Classic guild in a single desktop application. Members, characters, rosters, raids, attendance, raid points, DKP, rewards, portraits, and the graveyard are managed within one shared project data set.

The current desktop client is based on **Python 3.12+ and PySide6/Qt** and is developed for Windows.

## Current Status

- **Latest stable base:** 0.11.2
- **Current development version:** 0.11.3-test3
- **Main branch:** `main`

Details about changes are available in the [Changelog](CHANGELOG.md).

## Features

| Area | Included |
| --- | --- |
| **Members & Characters** | Member management, main/alt assignment, player and character data |
| **Roster** | Role-based roster view, class information, and portraits |
| **Raids & Attendance** | Raid management, Warcraft Logs CSV import, attendance, and raid statistics |
| **Raid Points & DKP** | Raid points, manual adjustments, and CLM/DKP support |
| **Rewards** | Point-based badges and portrait frames for characters and players |
| **Portraits** | Integrated portrait creation and management of character portraits |
| **Graveyard** | Historical characters, gravestones, portrait positioning, and review workflow |
| **Language** | German and English user interface |

## Portrait + Character Info Grabber

<p align="center">
  <img src="assets/grabber_banner.png" alt="WoWClassic-GuildGearChecker – Portrait + Character Info Grabber" width="100%">
</p>

The **Portrait + Character Info Grabber** is the companion tool for [**WoWClassic-GuildGearChecker**](https://github.com/Schissl-Glow/WoWClassic-GuildGearChecker) and works with the same project data.

It supports, among other things:

- creating and updating character portraits
- editing portrait crop, position, and zoom
- retrieving available character information such as **race and class** from the configured character source
- passing project-related data to [**WoWClassic-GuildGearChecker**](https://github.com/Schissl-Glow/WoWClassic-GuildGearChecker)
- handling missing portraits and character information
- portrait and graveyard workflows for existing characters

On Windows, the Grabber is started with **`STARTEN_PortraitGrabber.bat`**.

## Firefox Add-on – WoWLogHelper

<p align="center">
  <img src="assets/csvhelper_banner.png" alt="WoWLogHelper – CSV Download Helper" width="100%">
</p>

A separate Firefox add-on is available for raid imports. **WoWLogHelper** helps download the required Warcraft Logs CSV files.

➡️ **[Open WoWLogHelper on Firefox Add-ons](https://addons.mozilla.org/de/developers/addon/wowloghelper/versions)**

The add-on is not bundled inside the [**WoWClassic-GuildGearChecker**](https://github.com/Schissl-Glow/WoWClassic-GuildGearChecker) repository. This allows the browser extension to be updated independently and avoids keeping outdated add-on packages in the project.

## Installation and Start

### Prerequisites

- Windows
- Miniforge / Conda
- Internet access for the initial dependency setup

At the moment, no standalone EXE is distributed. The included installer creates a local Python/Qt environment under the current Windows user profile.

### First-time Installation

1. Clone the repository or download it completely.
2. Run **`INSTALLIEREN.bat`**.
3. After a successful installation, optionally run **`tests\bat\TESTEN_ALLES.bat`**.
4. Start **`STARTEN_GuildGearChecker.bat`**.

The installer sets up Python 3.12, PySide6, Pillow, and the required browser components used by the included tools.

## Downloads

Ready-to-use versions will be provided through **GitHub Releases** in the future. Only the current stable version, the previous stable version, and, when needed, one current test version are intended to be maintained there.

## Project Structure

```text
WoWClassic-GuildGearChecker/
├─ app/        Application and domain logic
├─ assets/     Banners, class icons, fonts, gravestones, and rewards
├─ config/     Local application settings
├─ data/       Local projects, portraits, backups, and runtime data
├─ docs/       Technical documentation and references
├─ tests/      Automated tests
│  └─ bat/     Test launchers including TESTEN_ALLES.bat
├─ tools/      Required helper and runtime tools
├─ INSTALLIEREN.bat
├─ STARTEN_GuildGearChecker.bat
└─ STARTEN_PortraitGrabber.bat
```

Local projects, portraits, logs, backups, temporary files, and build/release output are kept out of the repository through `.gitignore`.

## Tests

For a complete local test run:

```text
tests\bat\TESTEN_ALLES.bat
```

The full test suite covers, among other things, core logic, project management, roster handling, raid attendance, raid points, DKP/CLM, portraits, the graveyard, localization, and the Qt user interface.

## Publication

This public repository contains only released snapshots from the private development repository. Development, experiment, and backup branches are not published here.

---

<p align="center">
  <a href="https://github.com/Schissl-Glow/WoWClassic-GuildGearChecker"><strong>WoWClassic-GuildGearChecker</strong></a><br>
  WoW Classic Guild Management
</p>
