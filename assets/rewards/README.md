# [**WoWClassic-GuildGearChecker**](https://github.com/Schissl-Glow/WoWClassic-GuildGearChecker) – Reward Assets

## Inhalt

### Charakter-Ränge
- Die produktiven Charakter-Ränge liegen unter `assets/ranks/`.
- 35 Stufen: Holz/Eisen/Bronze/Silber/Gold/Platin/Diamant, jeweils 1–5.
- Die früheren `honor_*`-Badges sind nicht mehr Teil der produktiven Progression.

### Spieler-Portraitrahmen
- 7 finale Portraitrahmen: Holz, Eisen, Bronze, Silber, Gold, Platin, Diamant.
- PNG / RGBA mit echter Transparenz.
- Holz/Eisen/Bronze/Platin/Diamant: 941 × 1672 px.
- Silber/Gold: 948 × 1659 px.
- Dateinamen `frame_01.png` bis `frame_07.png` in genau dieser Reihenfolge.
- Die gelieferten Rahmen werden inhaltlich unverändert verwendet.
- Die Innenöffnungen sind je Rahmen aus der zentralen vollständig transparenten Alpha-Komponente bestimmt.

## Verbindliche Integrationsregeln

- Charakterfortschritt: automatisch nur den höchsten aktuell gültigen Rang anzeigen.
- Spielerfortschritt: automatisch nur den höchsten aktuell gültigen Portraitrahmen am aktuellen Main anzeigen.
- Bei Main-Wechsel wandert der Spielerrahmen automatisch auf den neuen Main.
- Bei deaktiviertem Punkte-/Belohnungssystem: weder Badge noch Belohnungsrahmen anzeigen.
- Keine manuelle Auswahl niedrigerer Ränge/Rahmen.
- Charakter-Ränge: Raidpunkte je 80 Punkte pro Stufe; Eternal-DKP je 100 Punkte pro Stufe.
- Spielerrahmen: 250, 500, 750, 1500, 2000, 3000 und 5000 Spieler-Raidpunkte.
- Frames als transparente Overlay-Assets verwenden; nicht in das Portrait dauerhaft hineinrendern.
- Rahmen proportional skalieren; nicht verzerren oder beschneiden.

## Schwellenprofile

Die zentrale Konfiguration liegt in `app/rewards.py`:

- Produktion Raidpunkte: Rang alle 80 Charakter-Raidpunkte; Rahmen bei 250, 500, 750,
  1500, 2000, 3000 und 5000 Spieler-Raidpunkten.
- Produktion Eternal-DKP: Rang alle 100 Charakter-DKP.
- Visueller Test: Rang alle 10 Charakterpunkte, Rahmen alle 20 Spielerpunkte.

`ACTIVE_REWARD_PROFILE = "production"` ist der produktive Standard. Die
niedrigen Testschwellen bleiben klar getrennt und sind nicht standardmäßig aktiv.
