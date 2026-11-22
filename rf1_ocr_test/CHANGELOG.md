# Changelog

## 0.5.8

- **Zwischenschritte der Einrichtung werden wieder sauber angezeigt.** In 0.5.7 rutschten die Unterpunkte in die schmale Spalte der Zeitleiste und standen Wort für Wort untereinander. Sie nutzen jetzt die volle Breite.
- *English:* The setup's intermediate steps use the full width again instead of being squeezed into the timeline's marker column.

## 0.5.7

- **Nach einer gröberen Prüfung schaut die App schnell noch einmal hin.** Drehte sich bei der Gegenprüfung gerade die letzte Rolle, bestätigt die App den Stand mit einer Nachkommastelle weniger. Bisher wartete sie dann das volle Prüfintervall. Jetzt holt sie nach etwa 45 Sekunden ein neues Bildpaar, wenn die Rolle wieder steht, damit schnell der volle Wert dasteht – vor allem direkt nach der Einrichtung. Das passiert einmal pro Serie, damit ein laufender Zähler nicht doppelt so oft geprüft wird. Unter dem Zählerstand steht, warum die App so kurz wartet.
- **Häkchen „Hintergrundarbeit anzeigen“ auf der Übersicht.** Ist es gesetzt, zeigt die Übersicht alles, was die App neben der automatischen Prüfung tut: Feinsuche der letzten Stelle, Wartezeit-Arbeit, Schattenmodus und Nacharbeit – jeweils mit Zustand (läuft, wartet, fertig), Schritt, Bild, gelesenem Wert, Fortschritt und Ergebnis. Die Anzeige aktualisiert sich alle paar Sekunden.
- **Zwischenschritte in der Einrichtung.** Der laufende Punkt der Schrittliste klappt auf und zeigt seine kleinen Schritte, z. B. Bild angefordert, Licht geprüft, Zählwerk gesucht, gelesener Kandidat, Bestätigung 1 von 3 oder „Kein neues Kamerabild – wird wiederholt“. Erledigte Punkte lassen sich wieder aufklappen.
- **Schattenmodus: Stillstand per Bildvergleich.** Die App vergleicht jede Rolle mit derselben Rolle der vorigen Prüfung und schreibt die Differenz ins Debug-Protokoll (`stationary`). Sie entscheidet damit noch nichts, erst werden echte Werte gesammelt.
- *English:* A check that was one decimal coarser because the last roller was turning now gets a new picture pair after about 45 seconds (once per series) instead of waiting the full interval; the overview says why. New box “Show background work” on the overview lists fine search, waiting-time work, shadow mode and follow-up live with state, step, picture, reading, progress and result. The running setup step unfolds its intermediate steps. Shadow mode logs a per-roller picture comparison with the previous check (`stationary`).

## 0.5.6

- **Die Suche nach der letzten Rolle blockiert nichts mehr.** Im Hintergrund suchte die App bisher immer weiter nach der achten Ziffer und brauchte dafür nach jeder Prüfung bis zu einer halben Minute Rechenzeit. Der Schattenmodus fiel deshalb fast immer wegen Auslastung aus, und die Nacharbeit in der Wartezeit lief gar nicht. Jetzt haben Schattenmodus und Nacharbeit Vorrang. Die Suche läuft nur noch, wenn das Gerät Luft hat.
- **Nach sechs Stunden ohne Erfolg gibt die App die Suche auf.** Die Automatik prüft dann weiter mit einer Nachkommastelle weniger, auch im Präzisionsmodus. Ein Hinweis sagt, warum: Entweder ist die Bildqualität zu schlecht, oder die letzte Ziffer ließ sich trotz mehrerer Versuche nicht lesen. Eine neue Einrichtung startet die Suche erneut.
- **Präzisionsmodus mit doppelter Bestätigung.** Beim Einschalten fragt die App nach, ob du ihn wirklich willst. Die Beschreibung erklärt jetzt auch, was passiert, wenn die letzte Ziffer nicht lesbar ist.
- *English:* The background search for the last roller no longer blocks shadow experiments and waiting-time work; it only runs with spare CPU capacity. After six hours without success it stops, checks continue with one decimal place less (also in precision mode), and a note explains why. Switching on precision mode now asks for a second confirmation.

## 0.5.5

- **Keine falsche Fehlermeldung mehr während der Feinsuche im Hintergrund.** Sucht die App im Hintergrund noch die dritte Nachkommastelle, bekommt sie nur die Bilder der normalen Prüfungen (etwa alle 11 Minuten). Der Einrichtungsstatus meldete dazwischen „Kein neues Kamerabild“ (rot), obwohl die Suche ganz normal weiterlief. Jetzt steht dort „Optimierung läuft“ mit der restlichen Rechenzeit.
- *English:* The setup status no longer shows a red “no new camera image” while the background search for the third decimal waits for the next routine check; it shows “optimisation running” instead.

## 0.5.4

- **Der Zählerstand springt nicht mehr kurz zurück.** Dreht sich gerade die hintere Rolle, prüft die App eine Runde lang mit einer Nachkommastelle weniger. Der Sensor zeigte dann z. B. 10507.8 nach 10507.86 – scheinbar weniger als vorher. Jetzt bleibt der genauere letzte Wert stehen, solange der gröbere dazu passt. Die Verbrauchsbuchung war davon nicht betroffen.
- *English:* The meter reading no longer steps back briefly when one check has to use one decimal fewer (e.g. 10507.8 after 10507.86); the more precise previous value is kept as long as the coarser one agrees with it.

## 0.5.3

- **Das Licht bleibt an, bis wirklich ein helles Bild da ist.** Ein Bild zu verwerfen (0.5.2) reichte nicht: Die Kamera gab nach dem Einschalten teils mehrere Sekunden lang noch Bilder von vorher heraus. Die App lässt das Licht jetzt an und holt im Sekundentakt weitere Bilder (bis zu sechs), bis eines hell ist. Nach einem Neustart der App, wenn sie die übliche Helligkeit noch nicht kennt, endet das Warten, sobald ein Bild deutlich heller ist als das erste.
- Die Kamera-Verstärkung wird erst erhöht, wenn auch nach diesem Warten alle Bilder dunkel bleiben. Vorher wurde sie wegen der alten, dunklen Bilder unnötig hochgedreht.

## 0.5.2

- **Kein Bild mehr „ohne Blitz“.** Die Kamera liefert auf eine Anfrage zuerst ihr zuletzt gespeichertes Bild, und das war oft noch vor dem Einschalten des Lichts aufgenommen. Die App holt nach dem Einschalten jetzt ein Bild und verwirft es; erst das nächste wird ausgewertet. Bisher wurde ein dunkles Bild nur erkannt, wenn die App schon wusste, wie hell ein Bild mit Licht ist – nach einem Neustart der App nicht, dann wurde das dunkle Bild benutzt und sogar als Maßstab gemerkt.

## 0.5.1

Nachkontrolle direkt nach 0.5.0 am echten Zähler.

- **Eine laufende Einrichtung bricht nicht mehr ab, wenn du einen Hinweis ausblendest.** Der neue Knopf „Hinweis ausblenden“ (Bildqualität) änderte eine Einstellung, und die Einrichtung hielt das für eine geänderte Konfiguration: Sie endete nach dem ersten Bild als „abgebrochen“, obwohl das Zählwerk gelesen und bestätigt war. Reine Anzeige-Einstellungen zählen jetzt nicht mehr als Änderung.

## 0.5.0

Beta. Großer Umbau in einem Stück: Die App ist in Bereiche aufgeteilt, liest im Normalbetrieb weniger und zeigt mehr von dem, was sie tut. Bitte nach dem Update einmal die Übersicht ansehen.

**Lesen und Prüfen**

- **Nur noch die Ziffern, die gebraucht werden.** Die Routineprüfung liest die Nachkommarollen jenseits der Vergleichsgenauigkeit nicht mehr; die letzte, ständig drehende Rolle war die langsamste.
- **Vordere drei Stellen werden übernommen statt gelesen**, sobald eine vollständige Prüfung sie bestätigt hat. Spätestens nach 10 Prüfungen oder einer Stunde liest die App wieder alles, bei einer Abweichung sofort.
- **Arbeit in der Wartezeit:** Zwischen zwei Prüfungen holt die App kein neues Bild und schaltet kein Licht. Sie schaut nur mit dem Bild der letzten Prüfung nochmals hin, wenn es einen Anlass gibt (Ziffern unklar, Experiment wegen Auslastung übersprungen), höchstens sechs Lesungen je Pause und nur auf einem ruhigen Gerät. Gemerkt wird die Nacharbeit der letzten zwei Prüfungen (Prüfung und Gegenprüfung); solange etwas offen ist, steht das dezent im Status. Das Ergebnis steht im Debug-Protokoll und ändert nie den Zählerstand.
- **Von Hand gesetzte Rahmen bleiben, wie du sie gesetzt hast.** Die App richtet sie nicht mehr nach und speichert keine eigene Feinkorrektur darüber. Von der Selbsteinrichtung gefundene Rahmen werden weiter nachgeführt.
- **Einrichtung:** Eine Bestätigung zählt nicht mehr, wenn derselbe Rahmen danach einen kleineren Stand liest. Teil-Treffer stehen im Einrichtungsstatus.
- **Nach einem Werksreset** springt der Sensor nicht mehr auf den alten gebuchten Stand zurück.
- **Verbrauchsstatistik:** Zeiträume über einen Wechsel der Genauigkeit hinweg gelten als geschätzt; das Diagramm nennt die Auflösung und beschriftet die Spitze.

**Oberfläche**

- **Manueller Test:** „Jetzt prüfen“ steht oben im Testbereich. Während des Lesens zeigt die App, was sie bisher gelesen hat. Nach dem Test lässt sich der Ziffernrahmen direkt am Bild dieses Tests korrigieren, auch an einem hochgeladenen.
- **Ziffernrahmen getrennt speichern:** „Für Automatik speichern“ oder „Für manuellen Test speichern“. Der zweite Knopf ändert nur den Test und startet keine automatische Prüfung.
- **Zähler-Demo mit echten Bildern:** vier echte Kamerabilder eines Gaszählers, gelesen wie bei der automatischen Prüfung. Zu sehen ist nur das Zählwerk, alles andere ist übermalt.
- **Schattenmodus sichtbar:** Unter Werkzeuge zeigt „Schattenmodus und Arbeit im Hintergrund“, wie oft ein Experiment lief und ob es dasselbe gelesen hat wie die normale Prüfung, dazu die Bildhinweise der Prüfungen (zu dunkel, zu hell, wenig Kontrast), wie sie bisher nur die Einrichtung zeigte.
- **Experimente haben Stufen:** Aus oder Schattenmodus. „Aktiv testen“ ist sichtbar, aber in dieser Version noch für kein Experiment freigegeben.
- **Neues Experiment „Digitalanzeige: Segmente direkt lesen“** für Zähler mit Sieben-Segment-Anzeige, nur im Schattenmodus.
- **Systemauslastung** unter Werkzeuge: Prozessor, Arbeitsspeicher, Anteil der App und Temperatur, soweit das Gerät sie meldet.
- **Kamera nicht verfügbar:** Meldet Home Assistant die gewählte Kamera als nicht verfügbar oder gibt es sie nicht mehr, sagt die App genau das. Nicht verfügbare Kameras stehen in der Auswahl hinten.
- Nach „Ausschnitt übernehmen“ landest du mit Bestätigung auf der Übersicht. Der Hinweis zur Bildqualität lässt sich ausblenden. Die Demo wartet auf ein beschäftigtes Gerät, statt sofort zu scheitern.
- Kontakt für Rückmeldungen: amr@eifel-layer.de.

**Unter der Haube**

- Regeln, Einrichtungsspeicher, Einrichtungsablauf, Statusanzeige, Systemwerte, Leseplan, Wartezeit-Arbeit und Auswertung des Schattenmodus liegen in eigenen Modulen mit eigenen Tests. Die Abläufe selbst bleiben in `run.py`.
- Eine Einrichtung wird in den Tests auf echten, übermalten Kamerabildern nachgespielt.

**Noch nicht enthalten:** „Aktiv testen“ für Experimente, die neue Kandidatenbewertung mit zwei Prozentwerten, die Digitalanzeige in der Selbsteinrichtung, Infrarot-Nachtsicht als Blitz, die neu geordneten Einstellungen und das überarbeitete Handbuch mit Bildschirmfotos.

## 0.4.4

Nachkontrolle direkt nach 0.4.3: Die Einrichtung lief weiter den strengen Weg.

- **Die einfache Einrichtung gilt jetzt bei jeder Vergleichsgenauigkeit.** Steht sie auf „Volle Kubikmeter“ oder einer Nachkommastelle, verlangte die Einrichtung ohne Referenzwert trotzdem alle drei Nachkommastellen, also auch die schnell laufende letzte Rolle. Sie bestätigte dann nie. Jetzt genügen bei jeder Einrichtung und Selbstreparatur eines Zählers mit drei Nachkommarollen die ersten zwei Nachkommastellen; die Korrekturen aus 0.4.2 und 0.4.3 greifen damit auch hier.
- **Debug-Protokoll:** Der Start einer Einrichtung zeigt die Vergleichsgenauigkeit und die Art der Einrichtung.

## 0.4.3

Nachkontrolle direkt nach 0.4.2: Die Einrichtung las das Zählwerk richtig („10501.50?“), bestätigte es aber nicht.

- **Die Korrekturen aus 0.4.2 gelten auch, wenn zwei Nachkommastellen verglichen werden.** Das ist die Voreinstellung nach einem Werksreset. Bisher bekam nur die Einstellung mit drei Nachkommastellen die einfache Einrichtung, mit zwei lief der strenge Weg: 15 Lesungen je Bild und keine Bestätigung.
- **Gespeicherte Rahmen früherer Läufe werden bei einer neuen Einrichtung nicht mehr verwendet.** Nach dem Umhängen der Kamera lasen sie nur Unsinn oder wurden sogar wieder gewählt. Rahmen einer älteren App-Version werden nie übernommen.
- **Rahmen bleiben bei dem Winkel, für den sie eingepasst wurden.** Der Winkelvergleich bevorzugte bei gleicher Lesung die kleinere Drehung (z. B. −9° statt −12°). Die Rahmen blieben dabei stehen und saßen an den äußeren Rollen eine halbe Ziffer zu hoch oder zu tief.
- **Debug-Protokoll zeigt je Einrichtungsbild, welcher Rahmen was gelesen hat** (bis zu 24 Lesungen mit Verfahren, Ausschnitt, Winkel, Leseprofil), dazu Teil-Treffer und die Art der Einrichtung.

## 0.4.2

Ausgelöst am 21.11.2026: Nach einem Werksreset lief die Einrichtung in den Timeout, die Automatik las nichts mehr. Nachgestellt mit echten Kamerabildern.

- **Rahmen folgen dem Zähler statt einem gleichmäßigen Raster:** Die roten Nachkommarollen stehen weiter auseinander als die schwarzen, und eine schräg hängende Kamera vergrößert den Abstand zusätzlich. Die Rahmen bekommen jetzt ein eigenes Raster mit wachsendem Ziffernabstand, werden nach rechts breiter und folgen einer leicht ansteigenden Zeile. Rollen ohne lesbare Ziffer (Spiegelung, Rolle dreht gerade) setzt das Raster, nicht mehr ein gleichmäßiger Abstand.
- **Letzte Rolle nicht mehr am Bildrand:** Der Ausschnitt des Zählwerks endete genau an der letzten Rolle, ihr Rahmen saß auf der Kante. Der Ausschnitt lässt jetzt links und rechts Platz.
- **Rahmen sitzen in der Höhe auf den Ziffern:** Ein zu hoch sitzender Rahmen zeigte die helle Fensterkante über einer unten abgeschnittenen Ziffer. Die Texterkennung las dann eine 1 als 4 („40501“ statt „10501“, im Protokoll der Nacht vielfach zu sehen). Die Höhe jedes Rahmens wird jetzt an den Ziffernstrichen ausgerichtet.
- **Einrichtung, während eine Rolle dreht oder zwischen zwei Ziffern steht:** Fließt Gas (oder bleibt die zweite Nachkommarolle genau zwischen zwei Ziffern stehen), zählt ein Bild trotzdem, wenn alle anderen Stellen übereinstimmen. Nach vier solchen Bildern wird der Ausschnitt vorläufig gespeichert, statt nach 20 Minuten abzubrechen.
- **Kein verschobener Rahmen mehr durch drehende Rollen:** Las die Einrichtung eine Stelle erst in einem leicht verschobenen Rahmen, wurde dieser verschobene Rahmen gespeichert. Bei einer drehenden Rolle zeigte er die nächste Ziffer und saß danach dauerhaft daneben. Die gelesene Ziffer zählt weiter, der Rahmen bleibt an seinem Platz.
- **Einrichtung deutlich schneller:** Die Ziffern einer Zeile werden nebeneinander gelesen (je Prozessorkern eine, höchstens vier). Liest das gefundene Zählwerk vollständig, entfallen die übrigen Kandidaten und der Winkelvergleich für dieses Bild (vorher 18 Lesungen je Bild, jetzt 5).
- **Zählwerk wird auch gefunden, wenn zwei oder drei Nachkommarollen gerade drehen.**
- **Unmögliche führende Ziffer wird nicht mehr geglaubt:** Zwischen dem letzten bestätigten Stand und dem höchstmöglichen Stand stehen die vorderen Ziffern fest. Liest die Texterkennung dort genau eine andere Ziffer und stimmen mindestens zwei weitere, wird die Stelle aus dem möglichen Bereich ergänzt.
- **Selbstreparatur, die auf kleinen Rechnern wirklich fertig wird:** Sie startet nach 40 Minuten fehlgeschlagener Lesungen (vorher zwei Stunden), hat zehn Minuten und 40 Versuche (vorher vier Minuten und 20, das waren zwei Bilder), bestätigt wie die Einrichtung mit zwei Nachkommastellen und versucht es alle zwei Stunden erneut, solange die Lesungen scheitern.
- **Ein besserer Rahmen behält seinen besten Wert:** Las derselbe Rahmen auf einem späteren Bild schlechter, wurde sein früherer, besserer Prozentwert überschrieben (z. B. auf 75 %) und er rutschte in der Kandidatenliste nach hinten oder fiel heraus. Jetzt zählt der beste Wert über alle Bilder; nur die Zusatzprüfung mit weiteren Leseprofilen auf demselben Bild darf ihn noch senken.
- **Treffer auch mit einer Nachkommastelle weniger:** Lesen beide Leseprofile alle Vorkommastellen und eine Nachkommastelle gleich (z. B. 10494,2), zählt das als Treffer für das Zählwerk in der Kandidatenliste und bei der Wahl des besten Rahmens.
- **Kein Dauer-Warnhinweis im 7-Ziffern-Betrieb:** Solange die 8. Ziffer im Hintergrund gesucht wird, gilt der Vergleich von zwei der drei Nachkommastellen als Normalbetrieb.

## 0.4.1

- **Kandidatenliste zeigt jedes Zählwerk mit Treffern:** Rahmen mit Treffern fielen aus der Liste, sobald fünf andere Rahmen mit höherem Prozentwert (aber ohne Treffer) kamen – die Liste wurde nur aus diesen fünf Plätzen gebaut. Jetzt steht jedes Zählwerk mit Treffern immer in der Liste, mit seinem besten Rahmen, Winkel und zuletzt gelesenem Wert. Sortiert wird nach Treffern, dann nach Prozent.

## 0.4.0

- **Einrichtung misst die Schräglage zuerst:** Vor jeder Texterkennung bestimmt die App die Neigung des Zählwerks im Bild (ca. 0,2 s) und sucht zuerst dort und ±1°/±2° daneben. Ein um −14° gedrehter Zähler wird so gleich auf dem ersten Bild gefunden, statt dass das Winkelraster ihn erst nach vielen Bildern erreicht.
- **Ein Zählwerk, ein Eintrag:** Rahmen desselben Zählwerks (höchstens ±2° Unterschied, mindestens 80 % Überlappung) werden zusammengefasst. Ihre Treffer zählen pro Bild gemeinsam, die Kandidatenliste zeigt „n Treffer“ und „n ähnliche Rahmen zusammengefasst“. Ein Rahmen mit Treffern fällt nicht mehr aus der Liste, und der gerade bestätigte Rahmen steht immer darin.
- **Der beste Rahmen wird gespeichert, nicht der erste:** Lesen mehrere Rahmen desselben Zählwerks über mindestens zwei Bilder unterschiedlich gut, speichert die Einrichtung den mit den meisten sicher gelesenen Stellen (z. B. −14° statt −12°).
- **Schwache Kandidaten nur als Suchhilfe:** Rahmen unter der Bestätigungsschwelle (z. B. 70–75 %) werden nicht mehr einzeln bestätigt, sobald ein anderer Rahmen die Schwelle erreicht; sie stehen als „nur Suchhilfe“ in der Liste.
- **Gemeinsamer Vorfilter, schnellere Auswertung:** Sobald die Größe des Zählwerks bekannt ist (bewährter Rahmen, bestätigter Kandidat oder zwei Treffer), werden viel kleinere Zeilen (Seriennummer, Kleingedrucktes) und weit verdrehte Rahmen ohne Texterkennung verworfen und unter „Verworfen (n)“ mit Grund angezeigt. Vierteldrehungen werden nur noch ohne bekannte Größe probiert. Liest das erste Leseprofil kaum Ziffern, entfällt das zweite, und der Winkelvergleich läuft nur für lesbare Kandidaten – das spart auf langsamen Rechnern viele Sekunden je Bild.
- **Automatik-Nachprüfung dreht zuerst, dann verschiebt sie senkrecht:** Bleiben hintere Stellen unklar, prüft die App auf dem schon vorhandenen Bild zuerst den gespeicherten Winkel ±1° und ±2°, danach die Rahmen der Nachkommastellen 2–6 px nach oben und unten. Was auf einem Bild nicht mehr fertig wird, setzt sie beim nächsten Automatikbild fort; die Anzeige sagt z. B. „Winkel −1° (3 von 10, wird beim nächsten Bild fortgesetzt)“.
- **Zeitbudget nach diesem Rechner:** Die Nachprüfung misst die Dauer je Lesung (gleitender Mittelwert) und plant danach 25–60 s und die Zahl der Versuche je Bild. Im Debug-Protokoll stehen `budget`, `read_s` und der Plan (`plan`).
- **Stille Selbstverbesserung:** Liest ein anderer Winkel oder eine senkrecht verschobene Rahmenlage über mindestens drei Bilder messbar besser (im Mittel mehr sicher gelesene Stellen, auf mindestens zwei Bildern besser, nie ein widersprechender Wert), wird sie dauerhaft gespeichert. Die bisherige Einstellung bleibt als Rückfallebene; nach zwei Fehlprüfungen kehrt die App zu ihr zurück. Debug-Protokoll: `optimize_saved` (alt/neu, Grund) und `optimize_rollback`.
- **Eigene Ziffernbibliothek (Experiment 2):** Aus jeder bestätigten Ablesung merkt sich die App die Form der sicher gelesenen Ziffern dieses Zählers. Bleibt eine Stelle (z. B. die erste Nachkommastelle „8“) unklar, wird sie nur ergänzt, wenn sie eindeutig einer gelernten Ziffer gleicht und die allgemeinen Vorlagen nicht widersprechen; Gegenprüfung mit zweitem Bild und Durchfluss-Plausibilität bleiben. Keine Extrabilder. Die Bibliothek wird beim Werksreset gelöscht. Debug-Protokoll: `library`.
- **Oberfläche:** Experimentelle Funktionen (Schattenbetrieb) jetzt auch im Einrichtungsassistenten; „Die letzten Leseversuche“ bleiben nach der Prüfung offen sichtbar, bis die nächste beginnt; Einstellungen „Automatische Prüfung“ als gleichmäßiges Raster mit Hilfetexten unter den Feldern; Aufklappbereiche mit drehendem Pfeil und Hover-Stil klar erkennbar; Kandidatenliste mit Treffern, Zusammenfassung, „nur Suchhilfe“ und „Verworfen (n)“.
- **Debug-Protokoll:** Ein Werksreset wird jetzt vermerkt (`factory_reset`).

## 0.3.4

- **Einrichtung sucht feiner um den passenden Winkel:** Das Winkelraster reicht jetzt in kleinen Schritten bis ±20° (bisher Sprung von 12° auf 18°, −14° fehlte), und rund um den Winkel, der schon am besten las (z. B. −12°), sucht die Einrichtung in 1°-Schritten weiter (−13°, −14°). Die Suche nach dem dunklen Ziffernfenster läuft im ganzen Bereich bis ±20°.
- **Keine ±90°/180°-Rahmen mehr, wenn das Zählwerk schon gefunden ist:** Rechte Winkel gehören nicht mehr zum normalen Suchraster. Die Einrichtung probiert sie beim ersten Bild nur noch, wenn kein aufrechter Rahmen die Ziffern schon weitgehend las (bei Kameras ohne Vergleichswert) – vorher kostete das bei drehender letzter Rolle viele Minuten.

## 0.3.3

- **Auch die zweite Nachkommastelle wird ergänzt:** Bei drei Nachkommastellen ergänzt die App wie in 0.3.2 nun auch eine unklare zweite Nachkommastelle (heute 18:31 „10493,1?3“ drei Minuten nach bestätigten 10493,193), wenn mit dem gelernten Durchfluss nur ein Wert möglich ist. Die schnellste, zuletzt verglichene Rolle und die Vorkommastellen werden nie so ergänzt.
- **„Experimentell · Mehrere Zähler“ entfernt:** Das Textfeld beobachtete nur andere Home-Assistant-Sensoren und rechnete daraus Verbrauch – das kann Home Assistant selbst (Verbrauchszähler-Helfer, Energie-Dashboard), und es hatte nichts mit weiteren Kamera-Zählern zu tun. Feld, Abfrage und Hintergrunddienst sind weg; frühere Einträge werden nicht mehr beachtet und beim Zurücksetzen auf Werkseinstellungen gelöscht. Echte mehrere Zähler (eigene Kamera, eigene Rahmen und Historie) bleiben Ziel für Version 1.0 und bekommen dann einen Assistenten.

## 0.3.2

- **Hintergrundsuche ohne Extrabilder:** Die Suche nach der 8. Ziffer, die Rahmen-Nachsuche und die Feinjustierung nach der Einrichtung werten jetzt nur noch die Bilder der normalen automatischen Prüfungen mit aus. Sie fordern keine eigenen Bilder (und keinen zusätzlichen Blitz) mehr an – bisher kam nach der Einrichtung alle 13 Sekunden ein Extrabild. Die Restzeit-Anzeige („noch höchstens … min“) und der Zeitbalken entfallen; stattdessen steht dort „läuft nebenbei mit den normalen Prüfbildern mit“.
- **Erste Nachkommastelle zuverlässiger:** Ist nur die erste Nachkommastelle unklar (z. B. „10492,?5“) und kommt seit dem zuletzt bestätigten Stand (10492,80) mit dem gelernten Durchfluss nur ein Wert in Frage, ergänzt die App die Stelle (10492,85). Der Durchfluss wird aus den bestätigten Ablesungen der letzten 7 Tage gelernt (doppelter Höchstwert, mindestens 1,5 m³/h, nie über der eingestellten Grenze) und erst nach 12 Messungen genutzt. Die Gegenprüfung mit einem zweiten Bild bleibt. Debug-Protokoll: `method: slow_roller`.
- **„Letzter bestätigter Abgleich“ bleibt gefüllt:** Er zählt jetzt auch Ablesungen, die mit einem zweiten Bild gegengeprüft wurden, und die Bestätigung aus der Einrichtung. Ein vorübergehender Wechsel der verglichenen Nachkommastellen löscht ihn nicht mehr. Steht dort „–“, erklärt ein Hinweis beim Darüberfahren den Grund.

## 0.3.1

- **Einrichtung bestätigt das gefundene Zählwerk wieder (kritisch):** Jede fein nachjustierte Fassung desselben Rahmens (z. B. −12° statt −13°, Ziffernrahmen leicht verschoben) galt bisher als neuer Kandidat und setzte die Bestätigungen zurück – heute 16 Bilder mit richtiger Lesung (10492,09 → 10492,18 …), aber 0 von 3 Bestätigungen und Abbruch nach 20 Minuten. Jetzt zählt jedes Bild desselben Zählwerks (Außenrahmen ≥ 80 % deckungsgleich, Drehung ±2°, gleiche Ziffernzahl) als Bestätigung; die Zählerstandsfolge muss weiterhin zum möglichen Durchfluss passen, sodass ein versetzter Rahmen nicht bestätigt wird.
- **Abgebrochene Einrichtung startet nach dem Update von selbst neu:** Ist die letzte Selbsteinrichtung am Zeitlimit gescheitert und hat die Automatik seitdem nichts sicher gelesen, beginnt die App nach dem Update einmal selbst eine neue Einrichtung – auch wenn noch ein alter Rahmen gespeichert ist. Niemand muss etwas antippen.
- **Keine 30-Minuten-Pause mehr, während die Lesefehler-Korrektur sammelt:** Liegt eine Ablesung nur unter einem vermutlich falsch gebuchten Stand und passt zur laufenden Korrektur, zählt sie nicht mehr als Fehlprüfung. Die Automatik prüft im normalen kurzen Takt weiter und schließt die Korrektur nach 15 Minuten ab, statt eine halbe Stunde zu pausieren (heute 13:57–14:41).
- **Schutz gegen falsche „Korrekturen“:** Ein niedrigerer Stand wird nur dann als Korrektur gesammelt, wenn er höchstens 2 m³ oder das Doppelte des möglichen Durchflusses seit dem gespeicherten Stand darunter liegt. Ein um eine Stelle versetzter Rahmen („04912…“ statt „10491…“) kann so nie den Zählerstand ersetzen; solche Ablesungen bleiben normale Fehlprüfungen.
- **Bewährter Rahmen aus älteren Versionen bleibt Startpunkt:** Ein vor 0.2.10 gespeicherter Rahmen wird auch dann zuerst geprüft, wenn sich seitdem eine Einstellung ohne Einfluss auf das Bild geändert hat (passende Ziffernzahl vorausgesetzt). Die Einrichtung bestätigt ihn wie bisher an frischen Bildern. Neue Einträge merken sich zusätzlich die Kamera.

## 0.3.0

- **„So weit ist die Einrichtung“:** Während der Selbsteinrichtung zeigt die Übersicht oben eine senkrechte Fortschrittsliste aller Arbeitsschritte: Kamerabild holen · Zählwerk finden · Rahmen und Drehung prüfen · Rahmen bestätigen (n/3) · Einrichtung speichern · im Hintergrund: letzte Stelle verfeinern (optional). Erledigte Schritte bekommen ein Häkchen und ein kurzes Ergebnis (z. B. „2 Bilder“, „beste Übereinstimmung 88 %“), der laufende Schritt ist hervorgehoben und nennt in Klartext, was gerade passiert („Rahmen 2 von 4 · Drehung −13° · 1 von 3 Bestätigungen“), ausstehende Schritte sind grau. Darunter eine kleine Statistik (Bilder, getestete Rahmen, bisherige Dauer, beste Übereinstimmung). Ohne Animation bei „Bewegung reduzieren“.
- **Gefundene Rahmen immer sichtbar:** Die Kandidatenliste steht während der Einrichtung aufgeklappt unter der Fortschrittsliste – je Rahmen Nummer, Drehung, Übereinstimmung und letzte Lesung; der gerade geprüfte Rahmen ist hervorgehoben.
- **Prüfdetails ausgeklappt mit Ziffern je Versuch:** Während einer automatischen Prüfung sind die Prüfdetails aufgeklappt (wer sie zuklappt, behält das) und zeigen eine kleine Tabelle: Spalten = Ziffernstellen (Vorkomma/Nachkomma getrennt, nicht verglichene Stellen blass), Zeilen = Versuche, darunter das Ergebnis je Stelle (grün einig, gelb abweichend, rot unklar). Auf dem Handy seitlich scrollbar.
## 0.2.10

- **Kein falscher Kubikmeter mehr bei uneinigen Lesungen:** Heute Mittag lasen 3 von 5 Lesungen eines Bildes 10491,4 und 2 von 5 10490,4 – die App nahm die Mehrheit, der Zähler stand aber bei 10490,6. Widersprechen sich Lesungen bei einer Vorkommastelle mit mindestens zwei Stimmen je Ziffer, bleibt die Stelle jetzt offen (lieber unklar als falsch). Ausnahme: eine Rolle, die gerade weiterdreht (rechts daneben steht 9 oder 0). Der zu hohe Stand korrigiert sich über die vorhandene Lesefehler-Korrektur (nach drei stimmigen niedrigeren Ablesungen über mindestens 15 Minuten); dafür werden niedrigere Ziffern nicht mehr als „unmöglich“ ausgeblendet, wenn der gespeicherte Stand selbst falsch ist; zu viel gebuchter Verbrauch wird nicht doppelt gezählt, die nächsten Buchungen gleichen ihn aus.
- **Kamera zu dunkel eingestellt? Die App regelt nach:** Bleibt das Bild auch mit eingeschaltetem Blitz deutlich dunkler als gewohnt, erhöht die App die Verstärkung der Kamera (ESPHome-Regler am selben Gerät, z. B. „Verstärkung“) in kleinen Schritten, höchstens alle 5 Minuten und höchstens bis 20. Debug-Protokoll: `exposure_adjust`. Vorher wartet sie nach einem dunklen Bild ein zweites Mal etwas länger auf den Blitz.
- **Zählerstand-Sensor bleibt nach einer Einrichtung verfügbar:** Bis zur ersten neuen Ablesung zeigt `sensor.rf1_ocr_zaehlerstand` den zuletzt gebuchten Stand (`is_fallback: true`) statt „nicht verfügbar“.
- **Bewährter Rahmen geht nicht mehr verloren:** Der zuletzt bewährte Rahmen gilt jetzt für dieselbe Kamera und dieselbe Ziffernzahl – unabhängig von Bildquellen-Modus, Vergleichssensor, Licht, Ziffernfarbe oder Anzeigeart. Bisher reichte eine solche Änderung im Assistenten, und die nächste Einrichtung begann wieder bei „Ziffernreihe finden“ (`known_good: false`).
## 0.2.9

- **Bilder ohne Blitz erkennen und neu aufnehmen:** Die App merkt sich, wie hell Bilder mit Blitz normalerweise sind. Ist ein Bild deutlich dunkler (Licht noch nicht an oder kurz vorher von außen ausgeschaltet, z. B. durch einen „Blitz dauerhaft an“-Schalter am ESP), schaltet sie das Licht ein, wartet und nimmt sofort ein neues Bild. So wird aus einem dunklen Bild keine Fehlprüfung („1????.???“) mehr. Das gilt für Prüfungen, Einrichtung und Vorschau.
- **Funktionierender Rahmen bleibt Ausgangspunkt:** Jede mit einem zweiten Bild bestätigte Prüfung merkt sich den Rahmen als „bewährt“. Wird die Einrichtung erneut gestartet (auch über den Assistenten), prüft sie diesen Rahmen zuerst, statt bei null zu beginnen. Bisher geschah das nur nach bestimmten Einrichtungen, darum begann die Einrichtung heute früh wieder mit „Ziffernreihe finden“.
- **Debug-Protokoll:** Jeder Start einer Einrichtung oder Hintergrundsuche wird mit Auslöser protokolliert (`setup_start`: Nutzer, Update, Wiederholung, Selbstreparatur, 8. Ziffer, Rahmen-Nachsuche), dunkle Bilder als `dark_picture`.
## 0.2.8

- **Neu-suchen-Knopf auf dem Handy wieder klein:** Im Einrichtungsassistenten zog eine Regel für schmale Bildschirme den Knopf ↻ neben „In Home Assistant gefunden“ auf volle Breite; die Auswahlliste war kaum noch zu sehen. Der Knopf ist jetzt immer 44 × 44 px groß, die Liste nutzt den Rest der Zeile.
## 0.2.7

- **Geräte neu suchen:** Im Einrichtungsassistenten steht neben „In Home Assistant gefunden“ ein kleiner Knopf ↻ („Neu suchen“). Antwortet Home Assistant gerade nicht (z. B. direkt nach einem Neustart) oder ist die Liste leer, sucht die App nach einigen Sekunden einmal selbst erneut und sagt, wenn Home Assistant nicht erreichbar ist.
## 0.2.6

- **Versionsnummer unten auf jeder Seite:** Übersicht, Einstellungen, Werkzeuge und Einrichtung zeigen unten dezent „AI Meter Reader 0.2.6“ mit Link zu den Änderungen.
## 0.2.5

- **Lieber unklar als falsch:** Am Kamerabild von heute Nacht liest die Texterkennung eine unscharfe 6 in mehreren Einstellungen übereinstimmend als 5 und eine unscharfe 7 als 4. Die Ziffernvorlagen sahen jeweils die richtige Ziffer vorn, wurden aber überstimmt. Jetzt gilt: Liegt die gelesene Ziffer in den Vorlagen deutlich hinter der besten (bzw. bei 5/6 schon knapp), bleibt die Stelle offen. Auch die Rahmenverschiebung übernimmt eine Ziffer nur noch, wenn die Vorlagen keine andere Ziffer klar bevorzugen (1/7 ausgenommen, die verwechseln die Vorlagen selbst).
## 0.2.4

- **Unklare Nachkommastellen werden wieder per Rahmenverschiebung gerettet:** Bei Kameras galt für die ganze Prüfung ein Zeitfenster von 20 Sekunden. Seit die Ziffernvorlagen mitlesen, war es nach zwei, drei Lesungen aufgebraucht, und die Verschiebung einzelner Rahmen startete gar nicht mehr („Versuch 5 von 15“). Sie liest das schon aufgenommene Bild und bekommt jetzt ein eigenes Budget von 25 Sekunden. Rahmen der Nachkommastellen werden dabei weiter seitlich verschoben (bis zu einem Viertel der Rahmenbreite), und der rote Rand des Nachkommafelds gilt nicht mehr als „abgeschnittene Ziffer“. Am Kamerabild von heute Nacht wird die 1 an der 7. Stelle so gelesen, die vorher nie erkannt wurde.
- **Keine 7 statt 1:** Die Ziffernvorlagen halten die 1 dieses Zählers (mit langer Fahne) leicht für eine 7. Zwischen 1 und 7 übernimmt die App eine Vorlage jetzt nur noch bei deutlichem Abstand.
- **Debug-Protokoll:** Neues Feld `recovery` je Prüfung – ob die Rahmenverschiebung versucht wurde, warum nicht, mit welchem Ergebnis und wie lange.
## 0.2.3

- **Funktionierende Einrichtung bleibt erhalten:** Ein Tippen auf einen vorgeschlagenen Ziffernbereich im Vorschaubild startet die Selbsteinrichtung nicht mehr sofort neu, sondern markiert den Bereich nur; gestartet wird erst mit dem Knopf darunter. Startet eine neue Einrichtung trotzdem, prüft sie den zuletzt bestätigten Rahmen immer zuerst – auch wenn ein anderer Suchbereich gewählt ist. So setzt sich kein Rahmen auf dem Gehäuserand durch, solange der alte Rahmen weiter liest.
- **Richtige Stelle im Hinweis:** „Die Suche nach der 8. Ziffer wird automatisch wiederholt“ statt „1. Ziffer“, wenn gerade nur eine Ziffer im Hintergrund gelesen wird.
## 0.2.2

- **Blitzreflex nie als Ziffer lesen:** Die erste Automatik nach der Einrichtung zeigte, dass die Texterkennung in der überstrahlten Stelle eine 7 oder 5 „erfindet“. Eine Stelle unter dem Reflex wird jetzt gar nicht mehr gelesen und nur aus dem letzten bekannten Stand ergänzt. Der Reflex wird zusätzlich auch bei eng gezeichneten Ziffernrahmen erkannt.
## 0.2.1

- **Unscharfe Ziffern lesen (Härtetest mit absichtlich unscharfer, schräger Kamera und Blitzreflex):** Neben der Texterkennung vergleicht die App jede Ziffer mit unscharf gerechneten Ziffernvorlagen. Liest Tesseract eine Stelle nicht, übernimmt die App die Vorlage nur bei klarem Abstand zur zweitbesten Ziffer; widerspricht die Vorlage einer gelesenen Ziffer deutlich, bleibt die Stelle offen. An den Kamerabildern des Härtetests werden die 0 und die 8 jetzt gelesen, die vorher nie erkannt wurden.
- **Verdeckte und unsichere Vorkommastellen aus dem letzten bekannten Stand:** Fehlen danach noch Vorkommastellen (z. B. unter dem Blitzreflex), ergänzt die App sie aus dem zuletzt bekannten Zählerstand und dem maximalen Durchfluss – nur wenn genau ein Wert passt oder die Vorlagen einen Wert klar bevorzugen. Das hilft der Selbsteinrichtung und der Automatik; die übliche Gegenprüfung mit zwei Bildern bleibt.
## 0.2.0

- **Ziffernrahmen auf die Ziffer zentriert:** Die Einrichtung rückt jeden Rahmen seitlich auf die hellen Striche der Ziffer. Bisher konnte ein Lichtreflex den Rahmen so verschieben, dass eine 8 halb abgeschnitten war.
- **Spiegelung selbst erkennen (Fire and Forget):** Überstrahlt der Blitz dauerhaft dieselbe Ziffer, schließt die Selbsteinrichtung mit den übrigen Ziffern ab und merkt sich die verdeckte Stelle wie eine markierte Spiegelung. Die Automatik ergänzt sie aus dem letzten bestätigten Stand, wenn nur ein Wert zum maximalen Durchfluss passt; sonst fragt die Übersicht einmal nach dem aktuellen Zählerstand.
- **Experimentelle Funktionen im Schattenbetrieb:** Neuer Schalter (standardmäßig aus) mit Häkchen je Experiment. Erstes Experiment: Perspektivkorrektur (Kippung). Gelesen wird nur bei freier Rechenleistung, es zählt nur das bewährte Ergebnis; das Debug-Protokoll speichert beide (`experiment`). Endpunkt `/testbild-streifen` (nur mit Experimentiermodus) liefert den ausgeschnittenen Ziffernstreifen als Base64.
- **Fehler melden:** Knopf unter Werkzeuge → Debug-Protokoll und Link im Hinweis bei wiederholten Fehlprüfungen; öffnet ein vorausgefülltes GitHub-Issue ohne private Daten. Issue-Vorlage im Repository.

## 0.1.26

- Fire and Forget: Findet die Selbsteinrichtung nach drei schnellen Wiederholungen noch keinen sicheren Rahmen, versucht die App es danach stündlich von selbst erneut, statt stehen zu bleiben. Wird die Kamera später scharfgestellt oder die Spiegelung des Blitzes beseitigt, richtet sich die App ohne Antippen ein. Der Hinweis nennt die häufigsten Ursachen (unscharfes Bild, Spiegelung auf den Ziffern).

## 0.1.25

- Zählwerk mit ESPHome-Kameras finden: Die Selbsteinrichtung sucht das Zählwerkfenster jetzt zuerst über die hellen Ziffern selbst (lokaler Kontrast) statt nur über ein dunkles Fenster. Ein Lichtreflex auf einer Ziffer, der rote Nachkommabereich, ein Strichcode oder die Seriennummer darunter stören nicht mehr. Die Schräglage der Ziffernreihe wird gemessen und das Bild vor dem Lesen gerade gedreht.
- Ziffernrahmen im gefundenen Fenster werden auch bei dunklem, ungleichmäßig beleuchtetem Bild an die Ziffern angepasst.
- Fire and Forget: Nach einem App-Update startet die Selbsteinrichtung einmal von selbst neu, wenn noch kein bestätigter Rahmen vorliegt. Eine laufende Automatik bleibt unberührt.

## 0.1.24

- Blitz der Kamera standardmäßig an: Bei ESPHome- und Home-Assistant-Kameras sucht die App selbst das Licht, das zum selben Gerät gehört (z. B. die Blitz-LED des ESP), und schaltet es für jede Aufnahme ein. Neuer Schalter „Blitz der Kamera verwenden“ (Standard an). Ein eingetragenes externes Licht hat Vorrang.

## 0.1.23

- „Licht für die Aufnahme“: Der Beispieltext im leeren Feld sah wie ein eingetragener Wert aus („light.esp_gaszaehler_blitz“). Jetzt steht dort „leer = ohne Licht, z. B. light.kamera_blitz“.

## 0.1.22

- Licht für die Aufnahme bleibt nicht mehr an: Nach dem Ausschalten liest die App den Zustand zurück und wiederholt den Befehl bis zu viermal, wenn das Licht noch „an“ meldet. Ein ausgelasteter Kamera-ESP hatte „Licht aus“ verzögert oder gar nicht umgesetzt.
- Anleitung: ESPHome-Beispiel mit Abschaltung nach 30 Sekunden im ESP selbst, aktueller Bildrate (Standbilder höchstens eine Sekunde alt) und ohne Drehung/Spiegelung durch ESPHome.

## 0.1.21

- Blitzlicht für Home-Assistant- und ESPHome-Kameras: Neues Feld „Licht für die Aufnahme“ bei der Bildquelle (Assistent und Einstellungen). Die App schaltet das Licht wie AI on the Edge für jede Aufnahme kurz ein, wartet 1,5 Sekunden, holt das Bild und schaltet es wieder aus – auch wenn der Abruf fehlschlägt. Ein Licht, das vorher schon an war, bleibt an.
- Anleitung: ESPHome-Konfiguration für die ESP32-CAM mit Blitz-LED als Licht-Entität.

## 0.1.20

- Laufendes Gas: Sind die Vorkommastellen und die erste Nachkommastelle sicher und nur die letzten zwei verglichenen Stellen unklar (z. B. „10482.8??“), bestätigt die App diese Prüfung mit zwei Nachkommastellen weniger, statt sie scheitern zu lassen. Gebucht wird nur bis zur bestätigten Stelle. Scheitert die Prüfung trotzdem, zählt sie wie bei einer drehenden letzten Rolle nicht für die Pause.
- Adaptives Prüfintervall für alle Bildquellen: Die App lernt den Durchfluss jetzt auch aus Ständen, die mit einem zweiten Bild bestätigt wurden, und prüft früher, wenn eine Rolle bald umspringt. Bisher nur bei AI on the Edge / SLFork. Neue Installationen und Werksresets haben es eingeschaltet; bestehende Einstellungen bleiben.

## 0.1.19

- Einrichtung schneller und ohne Unsinn: Liest ein Kandidat das Zählwerk schon gut (mindestens die eingestellte Übereinstimmung, z. B. 88 %), prüft die App Kandidaten ohne Erkennung (0 %) oder mit mehr als 40 Prozentpunkten Abstand nicht mehr intensiv nach, etwa um 90° gedrehtes Kleingedrucktes oder die Seriennummer.
- Hinweis zur Grobprüfung: „Grobprüfung: Die App testet mehrere feste Rahmen und Winkel und schaltet danach auf die Feinjustierung um …“.

## 0.1.18

- Winkel nach der Einrichtung: Misst die Einrichtung eine Schräglage über ±0,5°, behält sie wie bisher höchstens ±0,5° als Feinwinkel und gibt den Rest als Startwert an die laufende Schräglagenkorrektur. Die ersten automatischen Prüfungen arbeiten so sofort mit dem gemessenen Winkel, statt sich über viele Prüfungen heranzutasten (Beobachtung: −0,5° gespeichert, −1,5° gemessen, die 8 wurde als 6 gelesen).
- Nachprüfung lernt mit: Rettet ein leicht verschobener Rahmen eine Prüfung, wird diese Verschiebung als Kandidat an die lokale Feinausrichtung übergeben. Gespeichert wird sie wie dort erst nach drei frischen Bildern mit zwei verschiedenen Zählerständen; bei Fehlprüfungen nimmt die App sie zurück.
- Einrichtung ohne Ergebnis: Endet eine selbst gestartete Einrichtung ergebnislos, startet die App sie nach 5 Minuten automatisch neu (höchstens dreimal), statt dauerhaft auf „wartet auf Einrichtung“ zu stehen.
- Hinweis bei der Suche nach der 8. Ziffer: „(noch höchstens 4 min)“ statt „Noch höchstens 4 von 4 min“.

## 0.1.17

- Debug-Protokoll für die Selbsteinrichtung: Je ausgewertetem Bild ein Eintrag `setup_image` mit Anzahl der Bildanforderungen, verworfenen Doppelbildern, Abruffehlern, Abruf- und Auswertedauer, Bestätigungen und Lesestand; am Ende ein Eintrag `setup_end` mit Ergebnis und Dauer. Damit lässt sich klären, warum die Einrichtung manchmal nur alle paar Minuten ein neues Bild zählt.
- Texte überarbeitet (DE und EN): Statusmeldungen beschreiben, was die App tut, statt wie eine Aufforderung zu klingen („Nächstes Kamerabild wird angefordert …“ statt „Warte auf ein neues Kamerabild …“). Hinweise wie „Bitte … prüfen“ sind direkte Handlungshinweise („Prüfe …“).
- Veraltete Angabe korrigiert: Nach drei Fehlprüfungen pausiert die App für die eingestellte Zeit (Standard 30 Minuten), nicht mehr eine Stunde.
- Klarere Meldungen zur siebten Ziffer, zur gestörten Erkennung nach zwei Stunden, zum Zurücksetzen, zur Stundenverteilung im Verbrauch und zu Leseprofilen.

## 0.1.16

- Texte nach der Einrichtung: „In den nächsten 20 Minuten optimiert die App im Hintergrund noch Rahmen und Winkel.“ und „Optimierung läuft (noch höchstens X min): Alle Ziffern sind gelesen, die App verbessert noch Rahmen und Winkel.“ Die doppelte Minutenangabe entfällt; der Hinweis zu 2 von 3 Nachkommastellen steht jetzt am Ende.
- Texte überarbeitet: Statusmeldungen der Einrichtung als Zustand statt als Aufforderung („Ausschnitt und Drehung werden geprüft …“ statt „Prüfe …“), klarere Meldungen zu dritter Nachkommastelle, Rohbild-Fallback, Gegenprüfung und eingeschränkter Genauigkeit (DE und EN).

## 0.1.15

- **Schräglage pendelt sich dauerhaft ein:** Der gelernte Ausgleich bleibt erhalten, wenn die App einzelne Rahmen (z. B. die letzte Stelle) neu setzt; bisher begann er dann wieder bei null. Er korrigiert jetzt in kleineren Schritten (70 % der gemessenen Abweichung, ab 0,2°) und läuft dauerhaft weiter mit.
- **Mehr Messpunkte:** Gemessen wird über alle Ziffern bis zur vorletzten (bisher nur die Vorkommastellen). Ziffern, deren rechter Nachbar gerade 8 oder 9 zeigt, lässt die Messung aus – der Übertrag hebt sie schon leicht an.

## 0.1.14

- **Schneller wieder prüfen:** Nach einer Fehlprüfung prüft die App nach 2 statt 5 Minuten erneut, wenn der Rechner gerade Luft hat (Prozessorlast). Die Pause nach drei Fehlprüfungen ist jetzt einstellbar (Einstellungen → „Pause nach drei Fehlprüfungen“), Standard 30 statt 60 Minuten.
- **Keine Pause und kein „Bitte prüfen“, wenn nur die letzte Rolle unklar ist:** Dann war alles andere gelesen; die App schaut einfach bald wieder hin. Auch „Rahmen der letzten Stelle sitzt daneben“ ist kein gelber Warnhinweis mehr, weil die App das selbst behebt.
- **Ganze Rahmenreihe leicht verschieben:** Bleibt eine Prüfung unklar, versucht die App bis zu drei Mal, alle Rahmen gemeinsam ein Stück nach oben, unten oder zur Seite zu setzen. Übernommen wird ein Wert nur, wenn zwei Leseverfahren übereinstimmen, keine Ziffer angeschnitten ist und der Wert plausibel ist.
- **Hinweise führen zur Einstellung:** Ein Klick auf den Hinweis „… Fehlprüfungen … Nächster Versuch gegen …“ öffnet direkt die passende Einstellung.

## 0.1.13

- Meldung nach erfolgreicher Einrichtung: „Die Automatik läuft. In den nächsten 20 Minuten stimmt die App die Rahmen noch im Hintergrund fein ab.“ statt „… prüft sie häufiger“.
- **kWh im Einrichtungsassistenten:** Zustandszahl und Brennwert oder der fertige Umrechnungsfaktor lassen sich jetzt auch im Assistenten eintragen (aufklappbar, optional), nicht nur unter Einstellungen.
- Hinweis im Einrichtungsassistenten aktualisiert: Die dritte Nachkommastelle sucht die App nach der Einrichtung automatisch im Hintergrund und justiert die Rahmen selbst nach – nicht mehr „kann später intensiv gesucht oder manuell markiert werden“.

## 0.1.12

- **Schräglagenmessung korrigiert:** Sie misst nur noch innerhalb der Ziffernrahmen und erkennt helle Fensterkanten (Zeilen, die fast über den ganzen Rahmen leuchten) als solche. Vorher geriet die beleuchtete Kante des Zählwerkfensters mit in die Messung und ergab Werte wie 16°, die verworfen wurden – der Ausgleich blieb dadurch wirkungslos.

## 0.1.11

- **Neusuche des Rahmens wird angezeigt:** Sitzt der Rahmen der letzten Stelle neben der Rolle und sucht die App ihn im Hintergrund neu, steht das jetzt unter dem Zählerstand („… wird gerade im Hintergrund neu gesucht“, mit Restzeit). Danach steht dort zwei Stunden lang, wann der Rahmen automatisch neu gesetzt wurde.
- Debug-Protokoll: Die Schräglagenmessung schreibt jetzt bei jeder Prüfung den Messwert oder den Grund, warum nicht gemessen wurde.

## 0.1.10

- **Fehler behoben – Teiltreffer an der letzten Stelle:** Das Nachschieben fehlender Ziffern (0.1.5) konnte den Rahmen der letzten Rolle neben der Rolle lassen; eine angeschnittene 9 wurde als 4 gelesen und übernommen. Jetzt wird die letzte Rolle vor dem Nachschieben auf die Rollenmitte gesetzt (wie die Suche aus 0.1.4) und nur noch nach oben und unten verschoben.
- **Angeschnittene Ziffern werden nicht mehr gelesen:** Läuft eine Ziffer in einem verschobenen Rahmen an den linken oder rechten Rand, verwirft die App diese Lesung – beim Nachschieben, bei der Suche nach der 8. Ziffer und bei deren Neusuche.
- Die langfristige Feinjustierung der Rahmen verschiebt die letzte Rolle nicht mehr seitlich.

## 0.1.9

- **Selbsteinrichtung zählt stabiler hoch:** Findet die Einrichtung dieselbe Ziffernreihe auf dem nächsten Bild wieder, nur ein paar Pixel oder ein Grad anders, zählt das jetzt als Bestätigung. Bisher galt das als neuer Rahmen, und die Zählung sprang auf 1/3 zurück. Absichtlich nachjustierte Rahmen zählen weiterhin neu.

## 0.1.8

- **Feinwinkel schon in der Selbsteinrichtung:** Die grobe Suche findet die Ziffern weiterhin in ganzen Grad. Für jeden gefundenen Rahmen misst die Einrichtung auf den Einrichtungsbildern zusätzlich die Schräglage der Ziffernreihe und speichert den Mittelwert als Feinwinkel (bis ±0,5°) gleich mit. Was darüber hinausgeht, gleichen die normalen Prüfungen aus.

## 0.1.7

- **Bilddrehung in 0,1°-Schritten:** z. B. −1,5° statt nur −1° oder −2°.
- **Schräglage automatisch ausgleichen:** Bei manuellem Ausschnitt misst die App bei jeder Prüfung, wie schief die Ziffernreihe liegt (Linie durch die Ziffernmitten, robust gegen eine drehende Rolle). Stimmen sieben Messungen überein und weichen sie um mindestens 0,3° ab, dreht sie das Bild fein nach (höchstens ±2°). Steht im Debug-Protokoll unter `tilt`.
- **Letzter Stand als Lesehilfe:** Vorkommastellen, die nach dem letzten bestätigten Stand und dem maximalen Durchfluss unmöglich sind, zählen nicht mehr mit. Beispiel 19.11.: `10478.65?` statt `1047?.65?`, weil die 8 manchmal als 6 gelesen wurde.
- **Verbrauch auch in kWh:** Unter Einstellungen Zustandszahl und Brennwert von der Gasabrechnung eintragen oder nur den fertigen Umrechnungsfaktor; dann gibt es zusätzlich `sensor.rf1_verbrauch_gesamt_kwh` für das Energie-Dashboard.
- **Kompaktere Formulare:** Auswahl- und Eingabefelder in Einstellungen, Werkzeugen und Einrichtung sind kleiner.
- **Ehrlicherer Fehlertext:** Sind nur einzelne Ziffern unklar, heißt es „Einzelne Ziffern waren nicht eindeutig lesbar. Die App versucht es automatisch weiter.“ statt des Rats, Kamera, Fokus und Licht zu prüfen.

## 0.1.6

- Nachschieben fehlender Ziffern jetzt für bis zu **drei** unklare Stellen (z. B. `1047?.?4?`). Kamera und Winkel ändern sich zwischen zwei Prüfungen praktisch nie; meist sitzen dann nur einzelne Rahmen leicht daneben. Weiterhin höchstens 10 zusätzliche Einzelziffer-Lesungen, und die übrigen Ziffern müssen sicher gelesen sein.

## 0.1.5

- **Fehlende Ziffern nachschieben:** Bleiben nach den OCR-Versuchen eine oder zwei Ziffern unklar (z. B. `10477.9??`), verschiebt die App nur deren Rahmen in kleinen Schritten und liest sie neu, bis beide mit zwei übereinstimmenden OCR-Profilen gelesen sind (höchstens 10 zusätzliche Einzelziffer-Lesungen). Übernommen wird der Wert nur, wenn er zum Vergleichs- bzw. Vorwert passt. Bisher ging das nur für genau eine Ziffer.
- **Präzisionsmodus als experimentell gekennzeichnet:** kurzer Hinweis, dass der Wert genau ist, die schnell laufende letzte Rolle aber oft nicht sicher erkannt wird.

## 0.1.4

- **8. Ziffer über die Rollenmitte:** Die Suche bestimmt zuerst waagerecht die Mitte der letzten Rolle (die etwas weiter entfernt sitzt als die übrigen Ziffern) und verschiebt den Rahmen danach nur noch nach oben und unten. Die Mitte wird nur verwendet, wenn das Verfahren auf demselben Bild die bekannte Nachbarziffer wiederfindet; sonst gelten die bisherigen Positionen.
- **Engerer Suchbereich:** keine Sprünge mehr um eine halbe Ziffernbreite zur Seite, die eine halbe Ziffer in den Rahmen holten und zu Teiltreffern führten.
- **Rahmen sitzt daneben:** Ist die letzte verglichene Stelle mehrmals hintereinander unklar, meldet die App nicht mehr „Rolle drehte sich gerade“, sondern „Rahmen der letzten Stelle sitzt daneben“ und sucht ihn im Hintergrund neu (höchstens einmal pro Stunde).
- **Ruhigere Hinweise:** Eine einzelne Fehlprüfung oder eine bestandene Prüfung mit Hinweis wird dezent angezeigt, ohne gelbe Warnung und ohne „Bitte prüfen“. Erst ab drei Fehlprüfungen in Folge wird der Hinweis deutlich.

## 0.1.3

- Restzeit der Hintergrundsuche nur noch einmal: „Noch höchstens 9 von 20 min“.
- Sieben-Ziffern-Modus gilt als normaler Betrieb: grünes „Alles OK. Die 8. Ziffer wird noch abgesichert.“ statt gelber Warnung; der doppelte Optimierungstext im Automatik-Kasten entfällt.
- Meldungen wie „Einrichtung gespeichert.“ verschwinden nach 10 Sekunden und kommen beim automatischen Neuladen nicht wieder.

## 0.1.2

- **Verbrauch erst nach Bestätigung buchen:** Ein neuer Stand zählt erst, wenn die nächste Prüfung (mindestens 4 Minuten später) ihn bestätigt. Ein zu hoher Lesefehler wird verworfen, bucht nichts und blockiert nichts – kein Warten mehr auf einen falschen Höchststand. Der Startwert der Einrichtung wird genauso bestätigt.
- **Debug-Protokoll** unter „Werkzeuge“: letzte Prüfungen mit allen OCR-Durchläufen, Entscheidung und Verbrauchsstand, zum Ansehen und Herunterladen.
- Hinweis zur 8. Ziffer zeigt jetzt die eingestellte und die vorübergehend verglichene Genauigkeit sowie den Start der Hintergrundsuche.
- Fehlprüfungen nennen den Grund (z. B. „Ablesung passt nicht zum letzten Stand“, „Rolle drehte sich gerade“); nach drei Fehlprüfungen steht die Uhrzeit des nächsten Versuchs dabei.
- Tipp zum Prüfintervall nur noch bei wirklich unlesbaren Ziffern; Status-Chip zeigt „Prüft …“ während einer Prüfung.
- Knöpfe für die dritte Nachkommastelle klein unter „Erweitert“; kompaktere Navigation auf dem Handy.
- **Genauigkeit vereinfacht:** Standard sind 2 Nachkommastellen; die dritte nur mit Präzisionsmodus. Der alte strenge Präzisionsmodus („alle drei Stellen müssen stimmen“) entfällt.
- **Drehende Rolle:** Ist nur die letzte verglichene Stelle unklar, bestätigt die App die Prüfung einmalig mit einer Nachkommastelle weniger, statt sie scheitern zu lassen.
- **Farbige Rollen:** Die OCR nutzt den Farbkanal mit dem stärksten Kontrast (z. B. für rote Nachkommarollen). Im Test mit öffentlichen Ziffernbildern verschiedener Zähler rund zehn Prozentpunkte mehr richtig erkannte Ziffern.
- README: Hinweis, dass bisher nur ein Gaszähler praktisch getestet ist.

## 0.1.1

- Nach der bestätigten Sieben-Ziffern-Einrichtung wird die separat laufende Suche nach der achten Ziffer nach App-Neustarts und erfolglosen Suchläufen automatisch wiederaufgenommen. Zwischen erneuten Starts liegt mindestens eine Stunde; eine laufende Suche wird nicht unterbrochen.
- Die Übersicht unterscheidet jetzt eindeutig zwischen **3 eingestellten Nachkommastellen** und **2 vorläufig verglichenen**. Die achte Ziffer bleibt unbestätigt, bis sie tatsächlich nachgeprüft wurde. Ein solcher Teilmodus wird nicht mehr fälschlich als vollständig grüner Erfolg dargestellt.
- Der vorläufige Zwei-Stellen-Vergleich prüft exakt die ersten sieben Ziffern **ohne Rundung anhand der unbestätigten achten Stelle**; er kann dadurch bei `10475.15?` und Referenz `10475.155` korrekt den siebenstelligen Präfix bestätigen. Regulär eingestellte Vergleichsgenauigkeiten behalten ihre Rundungsregel.
- Bestehender siebenstelliger Prüf- und Verbrauchsstand sowie gespeicherte Einstellungen bleiben unverändert. Tests decken Zeitplanung, Neustart, Geltungsbereich und den Anzeigezustand ab.

## 0.1.0

Neustart der Versionierung mit frischer Historie. Funktionsstand entspricht der bisherigen Entwicklung (Rückblick in [docs/HISTORY.md](../docs/HISTORY.md)), dazu:

- Hintergrundsuche heißt „Optimierung läuft“, sobald alle Ziffern gelesen sind, mit Höchstdauer und Restzeit.
- Veraltete Ansicht wird erkannt: „Nicht aktuell“ am Zählerstand, Neu-laden-Knopf, automatisches Neuladen nach App-Neustart. Anzeigefehler werden getrennt gemeldet und ins App-Protokoll geschrieben.
- Einrichtungsassistent im neuen Design mit Schrittanzeige; das Layout springt beim Aufklappen nicht mehr.
- Dokumentation neu und knapp geschrieben.
