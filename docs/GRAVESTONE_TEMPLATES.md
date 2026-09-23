# Grabstein-Vorlagen

Die Friedhofsansicht lädt ihre Rahmen aus `assets/graveyard/`. Unterstützt werden lesbare Dateien mit dem Präfix `gravestone_` und den Endungen PNG, JPG/JPEG oder WebP, sofern sie im Referenzmanifest `assets/graveyard/gravestones_manifest.json` registriert sind.

Neue Designs werden außerhalb der Anwendung erstellt und anschließend als Assets in diesen Ordner gelegt. Codex soll keine neuen Grabstein-Grafiken erzeugen. Die Designs dürfen optisch stark variieren und transparente Außenbereiche besitzen. Technisch müssen jedoch alle Vorlagen dieselbe Canvas-Größe und identischen Textbereiche verwenden. Die Portraitöffnung darf in Größe, Form und Position variieren, solange sie als zusammenhängende transparente Öffnung im oberen Grabsteinbereich technisch erkennbar bleibt.

## Referenzmanifest und stabile Identität

Jede bestätigte Vorlage besitzt im JSON-Manifest drei Angaben:

- `graveTemplateId`: stabile, vom Dateinamen unabhängige Identität, zum Beispiel `grave-template-0001`
- `filename`: ausschließlich ein portabler Dateiname relativ zu `assets/graveyard/`
- `sha256`: SHA-256-Prüfsumme des bestätigten Dateiinhalts

Der normale Programmstart liest und prüft dieses Manifest, verändert es aber niemals automatisch. Dadurch werden neue, geänderte, fehlende, umbenannte, beschädigte oder inhaltsgleiche doppelte Dateien erkannt, ohne bestehende Projekte still auf einen anderen Bildinhalt umzubiegen. Eine reine Umbenennung wird anhand der identischen Prüfsumme wiedererkannt; eine inhaltlich veränderte Datei gilt dagegen nicht mehr als die bestätigte Vorlage. Beschädigte, nicht registrierte und doppelte Dateien werden nicht zur Vergabe angeboten. Fehlt das Manifest oder ist es ungültig, startet die Anwendung weiter und zeigt den sicheren Zustand ohne verfügbare Vorlage.

Die bewusste Wartungsaktion `GENERIEREN_GRABSTEIN_MANIFEST.bat` registriert den aktuell geprüften Bestand. Sie bewahrt IDs für identische Inhalte und vergibt nur für neue eindeutige Inhalte neue IDs. Diese Aktion ist vom normalen App-Start getrennt und muss ausdrücklich ausgeführt werden.

## Technische Ebenen

Eine Karte wird ausschließlich im Arbeitsspeicher aufgebaut:

1. Der Renderer erkennt in der konkreten PNG-Vorlage die geschlossene transparente Portraitöffnung.
2. Das Charakterportrait wird mit `object-fit: cover` proportional auf die tatsächliche Bounding-Box dieser Öffnung zugeschnitten und mit der realen Öffnungsform maskiert. Kreis, Oval, unregelmäßige Kontur, Größe und Position dürfen dadurch je Grabstein variieren.
3. Die unveränderte PNG-Vorlage wird als transparente Rahmenebene darübergelegt.
4. Charaktername, Klasse und Todesdatum werden programmgesteuert an zentral definierten Positionen gezeichnet.
5. Das Ergebnis wird als ungefähr 220 × 300 Pixel große Tkinter-Grafik angezeigt.

Kann keine technisch brauchbare geschlossene Portraitöffnung erkannt werden, verwendet der Checker aus Kompatibilitätsgründen die bisherige Master-Ellipse als sicheren Fallback. Die Quelldatei wird dabei niemals verändert.

Die Quelldateien werden dabei nur gelesen und niemals beschrieben. Die Mastergröße kompatibler Vorlagen ist 1074 × 1464 Pixel. Öffnung und Textpositionen werden relativ zu dieser Mastergröße skaliert.

## Verbindliche Geometrie

Alle Koordinaten beziehen sich auf die gemeinsame Masterfläche von 1074 × 1464 Pixeln und werden proportional auf die sichtbare Kachel skaliert:

- Äußere UI-Kachel: 220 × 300 Pixel
- Portrait-Referenzbereich/Fallback: `(304, 304)` bis `(770, 770)` auf der Masterfläche; in der UI ungefähr `(62, 62)` bis `(158, 158)`
- Portraitmaske: standardmäßig die aus dem Alpha-Kanal erkannte reale transparente Öffnung der jeweiligen Vorlage. Der Referenzbereich dient nur noch zur Suche nach der Öffnung und als Fallback, nicht als vorgeschriebene Ornamentform. Das Bild wird proportional per Cover-Zuschnitt auf die jeweilige Öffnungs-Bounding-Box gefüllt.
- Text-Safe-Area: `(250, 905)` bis `(824, 1090)` auf der Masterfläche; in der UI ungefähr `(51, 185)` bis `(169, 223)`
- Charaktername: Mittelpunkt `(537, 940)`
- Klasse: Mittelpunkt `(537, 995)`
- Todesdatum: Mittelpunkt `(537, 1050)`

Die Textzeilen verwenden immer diese gemeinsame Safe-Area und dieselben Positionen, unabhängig von der ausgewählten Vorlage. Ihre Maximalbreite entspricht der Breite der Safe-Area. Bei langen Inhalten wird die Schrift zunächst kontrolliert verkleinert und erst bei weiterhin zu breitem Text innerhalb der Safe-Area mit Ellipse gekürzt. Text wird niemals außerhalb der Safe-Area oder in die Vorlagen-PNG geschrieben.

## Manuelle Grabsteinkorrektur

Ein Klick auf eine Friedhofskarte öffnet die kompakte Funktion **Grabstein anpassen**. Der Rahmen bleibt in der Vorschau sichtbar. Das Portrait kann mit gedrückter linker Maustaste horizontal und vertikal verschoben und über den Zoom-Regler vergrößert werden. Im selben Dialog kann der Todestag ergänzt oder korrigiert werden. Die Vorschau wird ausschließlich im Arbeitsspeicher neu zusammengesetzt; weder Portrait noch Vorlage werden beschrieben.

Die optionalen Projektfelder sind:

- `portraitOffsetX`: horizontale, normalisierte Verschiebung von `-1.0` bis `1.0`
- `portraitOffsetY`: vertikale, normalisierte Verschiebung von `-1.0` bis `1.0`
- `portraitZoom`: Zoomfaktor von `1.0` bis `2.0`

Positive Offsetwerte verschieben das Bild nach rechts beziehungsweise unten. Der Wert `0.0` zentriert die jeweilige Achse. Zoom `1.0` verwendet den automatischen Cover-Zuschnitt der aktuell erkannten Portraitöffnung. Die Verschiebung bezieht sich damit auf die tatsächliche Öffnungsgröße des gewählten Grabsteins und wird immer auf den durch Cover und Zoom entstehenden Bildüberstand begrenzt, sodass keine leeren Ränder sichtbar werden.

Zusätzlich lässt sich der gesamte Textblock als Einheit verschieben und skalieren. Die optionalen Felder `textOffsetX` und `textOffsetY` liegen jeweils im Bereich `-1.0` bis `1.0`; `textScale` liegt zwischen `0.65` und `1.5`. Die normalisierten Offsets beziehen sich auf 28 Prozent der Kartenbreite beziehungsweise 40 Prozent der Kartenhöhe. Alle drei Textzeilen behalten ihre gemeinsame relative Geometrie und werden abschließend innerhalb der Karte begrenzt.

**Text zurücksetzen** stellt ausschließlich `(textOffsetX, textOffsetY, textScale)` auf `(0.0, 0.0, 1.0)` zurück. Portraitkorrektur, gewählte Vorlage und Todestag bleiben dabei unberührt. **Abbrechen** verwirft alle Entwurfsänderungen. **Übernehmen** validiert und schreibt Template, Portraitwerte, Textwerte und Todestag gemeinsam; bei einem Fehler wird nichts davon übernommen. Gültige Datumseingaben werden als `JJJJ-MM-TT` im bestehenden Feld `deathDate` gespeichert. Standardwerte werden beim regulären Projektspeichern nicht eigens serialisiert. Alte Projektdateien ohne diese Felder verwenden daher unverändert die automatische Darstellung.

## Projektzuordnung und Altprojekte

Die Auswahl wird je verstorbenem Mitglied im optionalen Feld `graveTemplateId` gespeichert. Das ältere Feld `gravestoneTemplate` bleibt für die rückwärtskompatible Migration lesbar und kann als Dateihinweis mitgeführt werden. Die Projektformatversion bleibt unverändert.

Eine normale Vorlage darf gleichzeitig höchstens einem verstorbenen Mitglied zugeordnet sein. Der Editor zeigt deshalb nur die eigene aktuelle und freie Vorlagen. Beim Wechsel wird die bisherige Vorlage erst durch **Übernehmen** freigegeben; **Abbrechen** verändert keine Belegung. Reaktivierung oder Entfernen eines Mitglieds gibt seine Vorlage frei. Ist keine freie Vorlage vorhanden, bleibt der Eintrag sichtbar und zeigt einen verständlichen Hinweis statt einer zufälligen oder bereits belegten Ersatzvorlage.

Beim Laden eines älteren Projekts wird eine vorhandene `gravestoneTemplate` nur dann in eine stabile ID migriert, wenn Dateiname beziehungsweise Inhalt eindeutig einer bestätigten, noch freien Vorlage zugeordnet werden kann. Ein alter Eintrag ohne jegliche Vorlagenreferenz bleibt unverändert und zeigt den klaren Zustand ohne zugeordneten Grabstein; erst eine ausdrückliche Auswahl im Editor wird gespeichert. Mehrdeutige, fehlende oder bereits belegte Zuordnungen werden nicht geraten. Das Modell wird nur bei einer erfolgreichen eindeutigen Migration als geändert markiert; beim nächsten Speichern wird die stabile Zuordnung übernommen.

## Responsive Darstellung

Kartengröße, Innenabstände und Zwischenräume sind zentral definiert. Die Spaltenzahl wird aus der verfügbaren Canvas-Breite berechnet. Bei schmaleren Fenstern entstehen weniger Spalten, bei typischer Desktopbreite ungefähr fünf. Die vertikale Scrollfunktion sowie Suche und Filterung des Friedhof-Tabs bleiben bestehen. Die Karten werden standardmäßig nach `deathDate` absteigend angeordnet; Einträge ohne auswertbares Datum stehen am Ende. Nach dem Übernehmen eines geänderten Todestags wird das Raster neu aufgebaut und damit sofort neu sortiert. Der Klick auf eine Karte öffnet ausschließlich den kompakten bestehenden Grabstein-Editor, keine zusätzliche Detailansicht.

Als Friedhofshintergrund wird `assets/graveyard/Background_001.png` verwendet. Das Bild wird für die jeweilige sichtbare Canvas-Größe proportional im Cover-Verfahren zugeschnitten und weder gestreckt noch zusätzlich abgedunkelt. Die Quelldatei bleibt unverändert.

## Projekt- und Portrait-Export

Der normale `.ggc`-Export und die im Portraitpaket enthaltene `project.ggc` verwenden dieselbe Modellserialisierung. Dadurch bleiben für jeden Friedhofseintrag `lifeStatus`, `deathDate`, `graveTemplateId`, der kompatible Dateihinweis `gravestoneTemplate`, `portraitOffsetX`, `portraitOffsetY`, `portraitZoom`, `textOffsetX`, `textOffsetY` und `textScale` erhalten. Beim Laden gelten dieselben rückwärtskompatiblen Standardwerte wie bei regulären Projektdateien.

Der Export mit Portraits enthält zusätzlich vorhandene namensbasierte Portraits unter `portraits/` sowie historische ID-basierte Portraits verstorbener Charaktere unter `portraits/history/<Member-ID>.png`. Beim Entpacken des Pakets und Laden der enthaltenen `project.ggc` kann der Friedhof mit seinen gespeicherten Zuordnungen und Korrekturwerten wiederhergestellt werden.
