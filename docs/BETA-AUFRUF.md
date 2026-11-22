# Beta-Aufruf (Entwurf)

Erst veröffentlichen, wenn eine Version mindestens 1–2 Tage stabil läuft (keine verworfene Einrichtung, Fehlquote ≤ 25 %).
Bilder: Vorher/Nachher – schräges, gespiegeltes Kamerabild links, gelesener Zählerstand rechts (nur ausgeschnittener Ziffernstreifen, keine Seriennummer).

## Deutsch (simon42 Community, akkudoktor.net)

**Titel:** AI Meter Reader – Gaszähler lokal ablesen, auch wenn AI on the Edge an Spiegelung oder Schräglage scheitert (Beta-Tester gesucht)

Hallo zusammen,

ich entwickle eine Home-Assistant-App (früher „Add-on“), die mechanische Gaszähler lokal per Kamera abliest: **AI Meter Reader**.

- **Richtet sich selbst ein:** findet das Zählwerk, die Drehung und die Ziffernrahmen allein – auch bei schräg hängender Kamera, gespiegeltem Bild oder Blitzreflex auf einer Ziffer.
- **Läuft komplett lokal:** Texterkennung auf deinem Home-Assistant-Rechner, keine Cloud.
- **Nutzt vorhandene Hardware:** ESP mit AI on the Edge (auch nur als Kamera), eine ESPHome-Kamera oder jede Kamera in Home Assistant; Blitz/Licht wird bei jeder Aufnahme kurz geschaltet.
- **Liefert Zählerstand und Verbrauch** für das Energie-Dashboard, prüft Werte gegen und lernt im Betrieb nach.

Ich suche **Beta-Tester mit mechanischem Gaszähler** (Rollenzählwerk). Fehler meldest du direkt in der App über „Fehler melden“; das Debug-Protokoll enthält keine Bilder und keine Zugangsdaten.

Installation: Repository in Home Assistant unter *Einstellungen → Apps → App-Store → Repositories* hinzufügen: `https://github.com/Eifellayer/meter-ocr`

Ich freue mich über Rückmeldungen – gerade von Leuten, bei denen AI on the Edge wegen Reflexionen nicht klappen wollte.

## English (Home Assistant Community „Share your Projects!“, Reddit r/homeassistant, Discord)

**Title:** AI Meter Reader – local gas meter reading that sets itself up, even with a tilted or mirrored camera (beta testers wanted)

Hi all,

I'm building a Home Assistant app (formerly “add-on”) that reads mechanical gas meters locally from a camera image: **AI Meter Reader**.

- **Self-setup:** finds the register, rotation and digit boxes on its own – also with a tilted camera, a mirrored image or a flash reflection on one digit.
- **Fully local:** OCR runs on your Home Assistant host, no cloud.
- **Uses what you have:** an ESP with AI on the Edge (camera only is fine), an ESPHome camera or any Home Assistant camera; a flash/light is switched on briefly for every capture.
- **Provides meter reading and consumption** for the Energy dashboard, cross-checks values and keeps learning while running.

Looking for **beta testers with a mechanical (roller) gas meter**. Report problems right from the app via “Report a bug”; the debug log contains no images and no credentials.

Install: add the repository in *Settings → Apps → App store → Repositories*: `https://github.com/Eifellayer/meter-ocr`

Feedback very welcome – especially if AI on the Edge never worked for you because of reflections.

## Wo posten (Reihenfolge)

1. GitHub jomjol/AI-on-the-edge-device → Discussions (freundlich als Alternative bei Reflexionsproblemen, nicht als Konkurrenz)
2. community.home-assistant.io → Share your Projects! (EN)
3. community.simon42.com (DE)
4. akkudoktor.net (DE)
5. Reddit r/homeassistant (EN, mit GIF/Screenshot)
6. Home Assistant Discord, Projekt-/Add-on-Kanal
