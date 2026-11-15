# Vergleichstest mit zehn Zählerfotos

Getestet mit der OCR von Meter OCR 0.8.2 (Beta) und Tesseract 5.5.0. In der Automatik lieferte keines der zehn Fotos einen übernehmbaren Stand. Bei einem Wasserzähler gelang die manuelle Ablesung der vollen Kubikmeter nach einem engeren Zuschnitt.

## Ergebnisse

| Foto | Sichtbare Anzeige | Bildgröße | Ausschnitt und Vorkommabreite in Pixeln | Ergebnis nach fünf Versuchen |
| --- | --- | --- | --- | --- |
| [Wasserzähler mit vier Zeigern](https://commons.wikimedia.org/wiki/File:Vattenm%C3%A4tare_skala.jpg) | `01335` m³ und Zeiger für Bruchteile | 1600 × 1223 | `539,398,884,477` · 345 | `?????.???` |
| [Wasserzähler istameter II](https://commons.wikimedia.org/wiki/File:Water_meter_(aka).jpg) | `00070.812` m³ und ein Zeiger | 1500 × 1500 | `510,645,898,717` · 259 | `?????.??2` |
| [Mechanischer Wasserzähler mit unscharfem Fenster](https://commons.wikimedia.org/wiki/File:Contatore_meccanico_dell%27acqua.jpg) | `017?0` m³ und Zeiger. Eine Stelle ist im Foto verdeckt oder unscharf. | 1446 × 1600 | `660,586,951,668` · 291 | `?????.???` |
| [Master Meter mit Zeiger](https://commons.wikimedia.org/wiki/File:Water_meter_register.jpg) | Sechs Rollen `000001` in Gallonen | 478 × 510 | `72,132,365,187` · 293 | `?????.???` |
| [Apator G4 Gaszähler](https://commons.wikimedia.org/wiki/File:GaszaehlerH2a.jpg) | `02846.794` m³ | 1600 × 905 | `352,545,1232,644` · 534 | `?????.???`. Einzelne Versuche lasen die letzte Nachkommastelle als `4`. |
| [Gaszähler G2.5 mit geneigtem Fenster](https://commons.wikimedia.org/wiki/File:GasMeter1212.jpg) | `01971.514` m³ | 1212 × 1212 | `497,923,827,989` · 212 | `?????.???` |
| [Gaszähler mit reiner Zeigeranzeige](https://commons.wikimedia.org/wiki/File:Gas-Meter-1785.jpg) | Zeiger in ft³ | 1600 × 1064 | `340,258,1275,582` · 935 | `?????.???` |
| [Stromzähler mit sechs Rollen](https://commons.wikimedia.org/wiki/File:Electricity_Counter.jpg) | `019634.7` kWh | 484 × 176 | `21,15,374,101` · 353 | `?????.???` |
| [Stromzähler mit oben angeschnittenem Fenster](https://commons.wikimedia.org/wiki/File:Electricity_Meter_Closeup.jpg) | `80190` kWh | 1600 × 902 | `285,0,1285,151` · 1000 | `?????.???` |
| [Digitaler Stromzähler](https://commons.wikimedia.org/wiki/File:Digitalz%C3%A4hler.jpg) | `000000` kWh | 1600 × 1200 | `988,505,1103,538` · 115 | `?????.???` |

Die Fotos stammen von Wikimedia Commons. Die Bilddaten bleiben bei den verlinkten Quellen.

## Durchführung

Die Bildorientierung aus EXIF wurde angewendet. Fotos über 1600 Pixel Kantenlänge wurden proportional mit Lanczos verkleinert. Die gemeldeten Ausschnitte beziehen sich auf diese Bildgröße und verwenden die Reihenfolge links, oben, rechts, unten. Die App-Funktionen `select_register`, `read_visible_digits` und `read_with_retries` verarbeiteten die Ausschnitte mit automatischer Ziffernfarbe, ohne Referenzwert und mit fünf OCR-Profilen. Die Vorkommastellen waren entscheidend. Für istameter II und Apator G4 ergab auch ein zusätzlicher Durchlauf mit drei Nachkommastellen keine Freigabe.

Fünf Fotos wurden mit angepasstem Ausschnitt und Ziffernfarbe bis zu zehnmal ausgewertet. Beim istameter II ergab der Ausschnitt `510,641,763,718` mit dunklen Ziffern und 253 Pixeln Vorkommabreite in zwei Profilen den richtigen Stand `00070` m³. Im manuellen Test erschien er als OCR-Lesung ohne Referenz. Für den selbstständigen Betrieb waren zwei der zehn Profile zu wenig.

Meter OCR verarbeitet Ziffernfenster mit fünf Vorkommastellen. Zeigerstellungen und abweichende Einheiten wie kWh und Gallonen brauchen eine eigene Auswertung. Die Orientierungs- und Beleuchtungstests mit synthetischen Bildern prüfen gezielte Varianten. Die zehn Fotos zeigen zusätzlich, wie stark Ziffernschrift, Spiegelungen, Ausschnitt und Auflösung die Erkennung beeinflussen.
