# Changelog – [**WoWClassic-GuildGearChecker**](https://github.com/Schissl-Glow/WoWClassic-GuildGearChecker)

Dieses Changelog hält den aktuellen Entwicklungsstand kompakt. Ältere Einzel-Release-Notes wurden aus dem Repository-Root entfernt; ihre Inhalte bleiben weiterhin vollständig über die Git-Historie nachvollziehbar.

## 0.11.3 – stabile Version

- Raidpunkte können über alle Raids oder ab einem festgelegten Datum gewertet werden, inklusive Migration älterer Projektstände.
- Raidpunkte und Raidstatistik verwenden einen einheitlichen Rebuild.
- Der WarcraftLogs-Bulk-Import erlaubt die manuelle Korrektur des erkannten Raidtyps.
- Manuelle Raidpunkte bleiben bei Attendance-Statuswechseln, Speichern/Laden und Rebuild erhalten.
- Dialoge wurden für kleinere Bildschirme besser nutzbar gemacht.
- Neuer Checker-Look mit Anthrazit, Bronze und Gold; Roster-Galerie und Spielerprofil sind Standard, die Legacy-Ansichten bleiben erreichbar.
- Raid, Teilnahme und Einstellungen wurden überarbeitet; Tabellenbreiten sind in den relevanten Checker-Bereichen anpassbar.
- WarcraftLogs-Bulk-Import bietet stabile Alias-Zuordnung auf memberId sowie eine sortierte, durchsuchbare Charakterauswahl.
- Friedhof-Zoom bis 40 %, verbesserter Banner-Ausschnitt und eine DKP-Historie für Spieler und Charaktere.

## 0.11.2 – letzte stabile Release-Basis

### Performance und Reaktionszeit

- Optimierter Stand für Roster, Raids, Matrix, Friedhof, Grabstein-Editor, Handoff-Polling und Startpfad.
- Unveränderte Friedhofskarten und Grabstein-Vorschauen werden effizienter wiederverwendet.
- Roster-Listenansicht, Raid-Teilnehmer, Matrix-Relevanzprüfungen und Reward-Assetpfade vermeiden redundante Arbeit.
- Der normale Qt-Start überspringt den separaten DLL-Precheck; die Diagnose bleibt bei Fehlstarts verfügbar.

### Qualitätssicherung

- Der Performance-Stand wurde gegen den Ausgangsstand mit realen Gildendaten verglichen.
- Roster-, Raid-, Matrix-, Friedhof-, Editor- und Speicher-Snapshots blieben fachlich beziehungsweise pixelgleich.

## Frühere 0.11.x-Meilensteine

### 0.11.1

- 35 produktive Rangstufen von Holz bis Diamant.
- Erweiterte Attendance- und Raid-Matrix-Ansichten.
- Verbesserter Portrait-Grabber und Friedhof-Workflow.
- Responsivere Roster-Galerie und überarbeitete Charakterdetails.

### 0.11.0

- Stabile historische Zuordnung über `playerId` und `memberId`.
- Main-Tod, Main-Nachfolge und gleichnamige neue Inkarnationen sauber getrennt.
- Historische Attendance, Raidpunkte und Eternal-DKP bleiben an der ursprünglichen Charakterinstanz.
- Produktive Portraitpfade wurden auf `portraits/<memberId>.png` vereinheitlicht.
- Das bisherige Honor-Badge-System wurde durch das 35-stufige Rangsystem ersetzt.

---

Ältere Entwicklungsstände (0.9.x, 0.8.x und davor) werden nicht mehr als einzelne Dateien im aktuellen Root gepflegt. Bei Bedarf sind sie über die Git-Historie rekonstruierbar.
