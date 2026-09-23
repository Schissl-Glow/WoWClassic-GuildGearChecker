# Gravestone Review Tool v0.7.0

Standalone-Prüftool für neue Grabstein-Assets von [**WoWClassic-GuildGearChecker**](https://github.com/Schissl-Glow/WoWClassic-GuildGearChecker).

## Review-Workflow

Neue Review-Daten werden ausschließlich unter `assets/graveyard/` angelegt:

- `_candidates/` – ungeprüfte Kandidaten
- `_approved_new/` – freigegebene Master für eine spätere Version
- `_approved_new/compressed/` – automatisch erzeugte 537×732-PNGs
- `_rejected/` – abgelehnte Kandidaten
- `_review_logs/` – aktuelle und archivierte Logs

`gravestone_placeholder.png` im Wurzelordner ist eine Sonderdatei. Das Review Tool verändert oder nummeriert sie nicht.

`_approved_new` ist ausdrücklich nur eine Staging-/Warteschlange. Das Tool erzeugt **keine** finalen `gravestone_XXX.png` und führt **keine** produktive Übernahme oder Release-Erstellung durch.

## v0.7.0

- Pfadstruktur auf `assets/graveyard/` umgestellt.
- Alte `assets/gaveyard/`-Struktur wird nur zur kontrollierten Projekterkennung erkannt; neue Review-Ordner werden dort nicht angelegt.
- Statusanzeige für Kandidaten, Freigaben und Ablehnungen.
- Adaptive Portraitprüfung aus v0.6 bleibt erhalten.
- Diagnose-Overlay bleibt erhalten.
- Accept erzeugt weiterhin Master + 537×732-PNG mit Alpha.
- Accept ist robuster: schlägt die kleine PNG fehl, wird der Master nach Möglichkeit nach `_candidates` zurückgerollt.
- Review-Kernlogik wurde aus der GUI in `gravestone_review_core.py` ausgelagert.
- Standalone-GUI und späterer Grabber können dieselbe Kernlogik verwenden.

## Start

`START_GRAVESTONE_REVIEW.bat`

Die vorhandene Miniforge-Installation wird weiterhin automatisch gesucht. Eine zusätzliche Python-Installation ist nicht erforderlich.

## Self-Test

```bat
python tools\gravestone_review\gravestone_review_tool.py --self-test
```

Der Self-Test verändert keinen produktiven Bestand von [**WoWClassic-GuildGearChecker**](https://github.com/Schissl-Glow/WoWClassic-GuildGearChecker); er arbeitet in einem temporären Testprojekt.
