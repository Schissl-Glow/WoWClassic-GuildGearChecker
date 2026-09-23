# [**WoWClassic-GuildGearChecker**](https://github.com/Schissl-Glow/WoWClassic-GuildGearChecker) – Rang-Assets

## Struktur

Das produktive Rangsystem besteht aus 35 Charakterrängen:

- Holz 1–5
- Eisen 1–5
- Bronze 1–5
- Silber 1–5
- Gold 1–5
- Platin 1–5
- Diamant 1–5

Die Dateinamen sind zugleich die technischen Rang-IDs, z. B. `Holz_1.png`,
`Platin_3.png` und `Diamant_5.png`.

```
assets/ranks/
├── master/   # 256 × 256 RGBA, unveränderte gelieferten Originale
├── 96/       # Detailansichten
└── 48/       # Standard-/Kompaktansichten
```

Eine noch kleinere UI-Darstellung verwendet das jeweilige 48-px-Asset und
skaliert es nur zur Laufzeit. Es gibt dafür keinen weiteren Asset-Satz.

## Fachliche Progression

- Raidpunkte: 80 Punkte je Rangstufe; Holz 1 ab 80, Diamant 5 ab 2800.
- Eternal-DKP: 100 DKP je Rangstufe; Holz 1 ab 100, Diamant 5 ab 3500.
- Rang ist charakterbezogen (`memberId`).
- Fehlt das benötigte Rang-Asset, bleibt die Symbolanzeige leer.
- Die bisherigen `honor_*`-Badges sind nicht Teil der produktiven
  Rangprogression.

## Größenregel

Die Masterdateien werden inhaltlich nicht verändert. 48- und 96-px-Dateien
werden ausschließlich proportional/lossless aus dem jeweiligen 256-px-Master
abgeleitet und als RGBA-PNG gespeichert.

## UI-Darstellung

- Roster-Kartenansicht: Rangsymbol klein oben rechts direkt auf dem Charakterportrait.
- Detailansichten: Rangsymbol nicht auf dem Portrait; stattdessen separat in 96 × 96 px direkt neben dem Profilbild.
- Fehlt das Rang-Asset, bleibt die jeweilige Symbolanzeige leer.

