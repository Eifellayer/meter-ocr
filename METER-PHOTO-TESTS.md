# Vergleichstests mit Zählerfotos

## Zehn Fotos von Wikimedia Commons

Getestet mit der OCR von Meter OCR und Tesseract 5.5.0. In der Automatik lieferte keines der zehn Fotos einen übernehmbaren Stand. Bei einem Wasserzähler gelang die manuelle Ablesung der vollen Kubikmeter nach einem engeren Zuschnitt.

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

## Zehn Aufnahmen aus der AI-on-the-Edge-Community

Keiner der zehn Ausschnitte ergab einen vollständigen, mehrheitlich gelesenen Stand. Bei einem Gaszähler las ein einzelnes Profil die fünf Vorkommastellen richtig. Die automatische Rahmenerkennung fand in keinem der verfügbaren Forenbilder die erwartete Ziffernreihe. Neun Aufnahmen enthielten bereits eingezeichnete ROI-Rahmen. Zwei Anzeigen hatten mehr als fünf Vorkommastellen. Die Wasserzähler mit Zeigern wurden am Rollenfenster geprüft.

| Sichtbares Ziffernfenster | Größe in Pixeln | Ausschnitt · Vorkommabreite | OCR nach fünf Profilen | Original |
| --- | --- | --- | --- | --- |
| Gas `37778.08?` | 660 × 568 | `165,244,638,334` · 289 | `?????.??2` | [Issue #570, erstes Bild](https://github.com/jomjol/AI-on-the-edge-device/issues/570) |
| Strom `031204` kWh, sechs volle Stellen | 1003 × 633 | `229,349,487,423` · 208 | `?????.?5?` | [Issue #692, zweites Bild](https://github.com/jomjol/AI-on-the-edge-device/issues/692) |
| Wasser `0055?` m³, letzte Rolle im Übergang | 1009 × 906 | `216,307,373,369` · 157 | `?????.???` | [Issue #786, Ziffernkonfiguration](https://github.com/jomjol/AI-on-the-edge-device/issues/786) |
| Wasser-LCD `000033.828` m³, sechs volle Stellen | 640 × 480 | `139,193,449,252` · 219 | `?????.?25` | [Issue #658, Originalaufnahme](https://github.com/jomjol/AI-on-the-edge-device/issues/658) |
| Gas `52719.5?` | 836 × 475 | `130,3,824,111` · 493 | `?????.???` | [Issue #423](https://github.com/jomjol/AI-on-the-edge-device/issues/423) |
| Wasser `02074` m³ plus Zeiger | 433 × 378 | `97,52,317,116` · 220 | `?????.???` | [Issue #4112, Zählerbild](https://github.com/jomjol/AI-on-the-edge-device/issues/4112) |
| Gas `37631.86?` | 1282 × 636 | `10,10,957,187` · 574 | `?????.???` | [Diskussion #1375, erster Bildausschnitt](https://github.com/jomjol/AI-on-the-edge-device/discussions/1375) |
| Gas `10442.64` | 640 × 480 | `25,133,634,250` · 440 | `?????.??4`. Ein Profil las `10442.??4`. | [Diskussion #3551, erster Beitrag](https://github.com/jomjol/AI-on-the-edge-device/discussions/3551) |
| Wasser `01391` m³ plus Zeiger | 690 × 466 | `194,184,332,230` · 138 | `?????.???` | [Home Assistant Community, TobiasGJ](https://community.home-assistant.io/t/ai-solution-for-analog-water-meter/378457/1) |
| Wasser `01405` m³ plus Zeiger | 566 × 500 | `135,93,314,154` · 179 | `?????.???` | [Home Assistant Community, johandijkstra](https://community.home-assistant.io/t/ai-solution-for-analog-water-meter/378457/10) |

Die Ausschnitte und die erwarteten Ziffern wurden vor den OCR-Durchläufen am Foto festgelegt. Getestet wurde mit Meter OCR und Tesseract 5.5.0, automatischer Ziffernfarbe und fünf OCR-Profilen ohne Referenzwert. Für den Test der Rahmenerkennung diente das verfügbare Forumsbild zusätzlich als Rahmenbild. Bei vier Gaszählern wurde auch die lesbare Nachkommagenauigkeit getestet. Keiner der Zusatzdurchläufe erreichte die erforderliche Übereinstimmung. Die Aufnahmen bleiben bei ihren Quellen.
