"""Home Assistant ingress panel for optical gas meter checks."""

import html
import json
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from queue import Empty, Full
from secrets import compare_digest, token_urlsafe
from threading import Lock, Thread
from urllib.parse import parse_qs, urlsplit

SUPERVISOR_ADDRESS = "172.30.32.2"

PAGE = """<!doctype html>
<html lang="de"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Gaszähler OCR-Kontrolle</title>
<style>
:root{{color-scheme:light dark;font:15px system-ui,-apple-system,sans-serif;--edge:light-dark(#dfe6ec,#34424d);--surface:light-dark(#fff,#1b252e);--muted:light-dark(#536475,#aebcc8);--accent:#158765;--page:light-dark(#f4f7f9,#111a22)}}
*{{box-sizing:border-box}}
body{{max-width:62rem;margin:0 auto;padding:1.5rem 1rem 3rem;background:var(--page);color:light-dark(#162b3b,#e8f0f5);line-height:1.45}}
h1{{font-size:clamp(1.5rem,4vw,2rem);letter-spacing:-.03em;margin:.2rem 0 .25rem}}
h2{{font-size:1rem;margin:0 0 .85rem;letter-spacing:-.01em}}
.intro{{max-width:48rem;color:var(--muted);margin:.25rem 0 1.4rem}}
.panel{{background:var(--surface);border:1px solid var(--edge);border-radius:1rem;padding:1.15rem 1.25rem;margin:0 0 1rem;box-shadow:0 3px 14px light-dark(#162b3b09,#0002)}}
form{{display:flex;flex-wrap:wrap;align-items:end;gap:.8rem}}
label{{display:grid;gap:.3rem;font-weight:600;font-size:.85rem;color:var(--muted)}}
select,button{{font:inherit;border-radius:.55rem;padding:.62rem .8rem;min-height:2.55rem}}
select{{background:var(--surface);border:1px solid var(--edge);color:inherit}}
button{{border:1px solid light-dark(#b2c4d1,#667988);background:light-dark(#dce6ed,#354b5a);color:light-dark(#28445a,#e9f4fc);font-weight:650;padding:.62rem 1.1rem;cursor:pointer;transition:background .15s}}
button:not(:disabled):hover{{background:light-dark(#ccdce6,#445e70)}}
button:disabled{{opacity:.65;cursor:wait}}
button:focus-visible,select:focus-visible,input:focus-visible,summary:focus-visible{{outline:3px solid #65bcaf;outline-offset:2px}}
input{{font:inherit;border-radius:.55rem;padding:.62rem .8rem;min-height:2.55rem;max-width:100%;background:var(--surface);border:1px solid var(--edge);color:inherit}}
.manual-panel summary{{display:flex;align-items:center;justify-content:space-between;gap:1rem;cursor:pointer;list-style:none}}
.manual-panel summary::-webkit-details-marker{{display:none}}
.manual-panel summary::after{{content:"▾";font-size:1.2rem;color:var(--muted)}}
.manual-panel[open] summary::after{{content:"▴"}}
.manual-content{{margin-top:1.2rem;padding-top:1rem;border-top:1px solid var(--edge)}}
.manual-panel summary small{{font-weight:400;color:var(--muted)}}
.settings-note{{font-size:.85rem;color:var(--muted);margin:.7rem 0 0}}
.save-notice{{font-size:.88rem;color:light-dark(#1e7650,#8ad4a9);margin:.7rem 0 0}}
.crop-fields{{display:flex;gap:.8rem;flex-wrap:wrap;margin-top:.7rem}}
.crop-fields label:first-child{{flex:2 1 17rem}}.crop-fields label:last-child{{flex:1 1 10rem}}
.crop-fields[hidden]{{display:none}}
.hint{{font-size:.85rem;color:var(--muted);margin:1rem 0 0;line-height:1.55}}
.test-box{{border:1px solid var(--edge);background:light-dark(#f6faf9,#192e2c);border-radius:.8rem;padding:.95rem 1rem;margin:1rem 0 0;display:grid;gap:.35rem}}
.test-box strong{{font-size:.94rem;color:inherit}}
.test-box[data-result="match"]{{border-color:light-dark(#9dceb2,#40785f);background:light-dark(#f0f8f2,#1b3029)}}
.test-box[data-result="match"] strong{{color:light-dark(#1e7650,#8ad4a9)}}
.test-box[data-result="fail"]{{border-color:light-dark(#dfb4b4,#854e55);background:light-dark(#fdf5f5,#342227)}}
.test-box[data-result="fail"] strong{{color:light-dark(#a13b46,#ed9fa6)}}
.help{{margin:.7rem 0 0;font-size:.87rem;color:var(--muted)}}
.help summary{{width:max-content;max-width:100%;cursor:help;padding:.2rem 0;list-style:none}}
.help summary::-webkit-details-marker{{display:none}}
.help summary:hover{{text-decoration:underline}}
.help p{{max-width:50rem;margin:.5rem 0 0;line-height:1.55}}
.test-result{{padding-top:.4rem;border-top:1px solid var(--edge);font-size:.93rem}}
.test-result p{{margin:.25rem 0}}
.test-box p{{margin:0}} .test-box small{{color:var(--muted);font-variant-numeric:tabular-nums}}
.test-box progress{{width:100%;height:.7rem;margin:.45rem 0;border:0;border-radius:99px;overflow:hidden;accent-color:var(--accent)}}
.test-box progress::-webkit-progress-bar{{background:light-dark(#e1e9e7,#354842);border-radius:99px}}
.test-box progress::-webkit-progress-value{{background:var(--accent);border-radius:99px}}

dl{{display:grid;grid-template-columns:minmax(8rem,11rem) minmax(0,1fr);gap:.5rem 1rem;margin:0}}
dt{{color:var(--muted);font-size:.9rem}}
dd{{margin:0;min-width:0;overflow-wrap:anywhere;font-variant-numeric:tabular-nums;font-weight:550}}
section{{display:grid;gap:1rem;grid-template-columns:repeat(auto-fit,minmax(min(100%,18rem),1fr));margin-top:1rem}}
section>div{{background:var(--surface);border:1px solid var(--edge);border-radius:1rem;padding:1rem;overflow:hidden}}
section img{{width:100%;height:auto;display:block;border-radius:.55rem}}
.stamp,#countdown{{font-variant-numeric:tabular-nums}}
@media(max-width:500px){{body{{padding:.8rem .7rem 2rem}}.panel{{padding:.9rem}}dl{{grid-template-columns:7.4rem minmax(0,1fr)}}form label{{flex:1 1 9rem}}button{{width:100%}}}}
</style>
<h1>Gaszähler OCR-Kontrolle</h1>
<p class="intro">Unabhängiger Bildabgleich deines Gaszählerstands mit der vorhandenen Messung. Die OCR liest die Ziffern erneut direkt aus dem Kamerabild – ohne den vom ESP erkannten Wert einfach zu übernehmen.</p>
<div class="panel"><h2>Automatische Prüfung – Einstellungen</h2>
<form method="post" action="automatik" id="auto-form">
<input type="hidden" name="csrf" value="{csrf}">
<label>Vergleich
<select name="decimals">{auto_decimal_options}</select></label>
<label>Max. OCR-Versuche
<select name="attempts">{auto_attempt_options}</select></label>
<button type="submit">Speichern</button>
</form>
<p class="settings-note">Diese Einstellungen gelten dauerhaft für alle zukünftigen automatischen Prüfungen. Bereits gespeicherte Prüfungen werden nicht rückwirkend geändert.</p>
{auto_saved_notice}
</div>
<details class="panel manual-panel" id="manual-panel">
<summary><strong>Manuellen Test öffnen</strong><small>Zusätzliche Bild- und OCR-Einstellungen</small></summary>
<div class="manual-content">
<h2>Manueller Bildtest</h2>
<form method="post" action="pruefen" id="manual-form">
<input type="hidden" name="csrf" value="{csrf}">
<label>Ziffernfarbe
<select name="polarity">{polarity_options}</select></label>
<label>Vergleichsgenauigkeit
<select name="decimals">{decimal_options}</select></label>
<label>Max. OCR-Versuche
<select name="attempts">{attempt_options}</select></label>
<label>Bildbereich
<select name="crop_mode" id="crop-mode">{crop_mode_options}</select></label>
<div class="crop-fields" id="crop-fields" hidden>
<label>Manueller Ausschnitt (links, oben, rechts, unten)
<input name="crop" type="text" value="{crop_value}" maxlength="30" placeholder="52,56,564,132"></label>
<label>Breite der Vorkommastellen
<input name="width" type="number" min="1" max="1920" value="{width_value}"></label>
</div>
<button id="start-check">Jetzt prüfen</button>
</form>
<details class="help"><summary title="Informationen zum manuellen Bildtest">ⓘ Was passiert bei „Jetzt prüfen“?</summary>
<p>Die App verwendet das letzte vorhandene Zählerbild, ohne eine neue Aufnahme zu starten. Sie liest die Zahlen aus dem Bild und vergleicht sie mit dem Referenzwert. Sobald die Werte übereinstimmen, stoppt die Prüfung. Andernfalls werden höchstens so viele OCR-Versuche durchgeführt wie eingestellt (1–10). Der Test verändert die automatische Trefferzahl nicht.</p></details>
<div class="test-box" id="test-box" data-phase="idle" data-result="neutral" role="status" aria-live="polite">
<strong id="test-head">Aktueller Schritt: Bereit</strong>
<p id="test-status">{request_status}</p>
<progress id="test-progress" max="{default_attempts}" value="0" aria-label="OCR-Versuche" hidden></progress>
<small id="test-meta">Bereit für den manuellen Test.</small>
<div class="test-result" id="test-result" hidden>
<p id="test-result-detail"></p>
<small id="test-result-stamp"></small>
</div>
</div></div></details>
<div class="panel"><h2>Automatische Kontrolle</h2>
<dl><dt>Nächste Prüfung</dt><dd id="countdown">–</dd>
<dt>Vergleich</dt><dd>{auto_rule_description}</dd>
<dt>Erkannter Stand</dt><dd>{ocr}</dd>
<dt>Referenz</dt><dd>{reference}</dd>
<dt>Prüfergebnis</dt><dd>{detail}</dd>
<dt>Bildzeit</dt><dd class="stamp" data-epoch="{image_time}">–</dd></dl></div>
<section><div><h2>Aktuelles Bild</h2>{current}</div>
<div><h2>Letzter Treffer</h2>{good}</div></section>
<script>
const next = {next_check};

let currentPhase = 'idle';
const manualPanel = document.querySelector('#manual-panel');
const manualForm = document.querySelector('#manual-form');
const cropMode = document.querySelector('#crop-mode');
const cropFields = document.querySelector('#crop-fields');
function showCropFields() {{
  cropFields.hidden = cropMode.value !== 'manual';
}}
cropMode.addEventListener('change', showCropFields);
showCropFields();
async function refreshTestStatus() {{
  try {{
    const response = await fetch('status', {{cache: 'no-store'}});
    if (!response.ok) throw new Error('Status nicht abrufbar');
    const job = await response.json();
    currentPhase = job.phase;
    const box = document.querySelector('#test-box');
    const bar = document.querySelector('#test-progress');
    const button = document.querySelector('#start-check');
    const detail = document.querySelector('#test-result');
    const active = ['queued', 'running', 'ocr'].includes(job.phase);
    const outcome = job.phase === 'done' ? job.outcome : null;
    box.dataset.phase = job.phase;
    box.dataset.result = outcome === 'match' ? 'match' : (outcome && outcome !== 'ocr_only' ? 'fail' : 'neutral');
    button.disabled = active;
    button.textContent = active ? 'Prüfung läuft …' : 'Jetzt prüfen';

    const title = job.phase === 'queued' ? 'Anfrage angenommen' :
      job.phase === 'running' ? 'Bild und Messwerte' :
      job.phase === 'ocr' ? 'OCR-Auswertung' :
      job.phase === 'done' && outcome === 'match' ? 'Test erfolgreich' :
      job.phase === 'done' && outcome === 'ocr_only' ? 'Bild gelesen – ohne Vergleich' :
      job.phase === 'done' && outcome === 'difference' ? 'Test beendet – Abweichung erkannt' :
      job.phase === 'done' && outcome === 'ocr_unclear' ? 'Test beendet – Ziffern nicht sicher erkannt' :
      job.phase === 'done' && outcome === 'slfork_unclear' ? 'Test beendet – Referenzwert unklar' :
      job.phase === 'done' ? 'Test nicht erfolgreich' : 'Bereit';
    document.querySelector('#test-head').textContent = title;
    document.querySelector('#test-status').textContent = active ? (job.message || 'Prüfung läuft …') : '';
    const max = Math.min(10, Math.max(1, Number(job.max_attempts) || Number({default_attempts})));
    const done = Math.min(Number(job.attempts) || 0, max);
    bar.hidden = !active;
    bar.max = max;
    if (job.phase !== 'ocr') bar.removeAttribute('value');
    else bar.value = done;
    document.querySelector('#test-meta').textContent = active && job.phase === 'ocr' ?
      'Versuche abgeschlossen: ' + done + ' / ' + max :
      active ? 'Prüfung läuft …' :
      job.phase === 'done' ? (done === 1 ? '1 OCR-Versuch' : done + ' OCR-Versuche') : 'Bereit für den manuellen Test.';

    if (job.phase === 'done') {{
      detail.hidden = false;
      document.querySelector('#test-result-detail').textContent = job.detail || job.message || 'Kein Ergebnis.';
      document.querySelector('#test-result-stamp').textContent = job.checked_at ?
        new Intl.DateTimeFormat('de-DE', {{day:'2-digit', month:'2-digit', year:'2-digit', hour:'2-digit', minute:'2-digit'}}).format(new Date(job.checked_at*1000)) : '';
    }} else {{
      detail.hidden = true;
    }}
  }} catch (_) {{
    document.querySelector('#test-meta').textContent = 'Status nicht erreichbar – Verbindung prüfen.';
  }}
}}
refreshTestStatus();
setInterval(refreshTestStatus, 1000);
function tick() {{
  const out = document.querySelector('#countdown');
  if (!next) return;
  const seconds = Math.max(0, Math.ceil(next - Date.now() / 1000));
  out.textContent = seconds ? Math.floor(seconds / 60) + ':' + String(seconds % 60).padStart(2,'0') + ' min' : 'Jetzt fällig';
}}
for (const el of document.querySelectorAll('.stamp')) {{
  const epoch = Number(el.dataset.epoch);
  if (epoch) el.textContent = new Intl.DateTimeFormat('de-DE', {{day:'2-digit', month:'2-digit', year:'2-digit', hour:'2-digit', minute:'2-digit'}}).format(new Date(epoch * 1000));
}}
if (location.search === '?test=queued') {{
  manualPanel.open = true;
  history.replaceState(null, '', location.pathname);
}}
let edited = false;
manualForm.addEventListener('change', () => {{ edited = true; }});
document.querySelector('#auto-form').addEventListener('change', () => {{ edited = true; }});
manualForm.addEventListener('submit', () => {{
  const button = document.querySelector('#start-check');
  button.disabled = true;
  button.textContent = 'Prüfung läuft …';
}});
tick(); setInterval(tick, 1000);
setInterval(() => {{
  if (!edited && !['queued','running','ocr'].includes(currentPhase) &&
      !manualPanel.open && !document.querySelector('#auto-form').contains(document.activeElement)) location.reload();
}}, 15000);
</script></html>"""


POLARITIES = {"auto": "Automatisch", "light": "Hell", "dark": "Dunkel"}
DECIMALS = {"0": "Volle Kubikmeter", "1": "1 Nachkommastelle", "2": "2 Nachkommastellen", "3": "3 Nachkommastellen"}
ATTEMPTS = {str(value): str(value) for value in range(1, 11)}
CROP_MODES = {"auto": "Automatisch erkennen", "manual": "Ausschnitt selbst festlegen"}


def select_options(choices, chosen):
    return "".join(
        f'<option value="{value}"{" selected" if value == chosen else ""}>{label}</option>'
        for value, label in choices.items()
    )


def start_panel(
    history_path, current_image, good_image, requested, default_decimals, default_attempts,
    get_auto_rules, save_auto_rules, default_crop, default_width,
):
    images = {"/aktuell.jpg": current_image, "/treffer.jpg": good_image}
    csrf_token = token_urlsafe(32)
    request_lock = Lock()
    progress = {
        "request_id": 0, "phase": "idle", "message": "Noch kein manueller Test gestartet.",
        "attempts": 0, "max_attempts": default_attempts,
        "started_at": 0, "checked_at": 0, "outcome": None, "detail": "",
    }
    try:
        saved_history = json.loads(history_path.read_text(encoding="utf-8"))
        previous = saved_history.get("manual_result", {})
        if previous.get("checked_at") and previous.get("status"):
            progress.update(
                phase="done", message="Letzter manueller Test",
                attempts=previous.get("ocr_attempts", 0),
                max_attempts=previous.get("settings", {}).get("attempts", default_attempts),
                checked_at=previous["checked_at"],
                outcome=previous.get("status") or "ocr_unclear",
                detail=previous.get("detail", "Kein Prüfergebnis gespeichert."),
            )
    except (OSError, ValueError, AttributeError, TypeError):
        pass

    def update_progress(request_id, phase, message, attempts=0, checked_at=0, outcome=None, detail=""):
        """Only the newest request may update the visible status."""
        with request_lock:
            if progress["request_id"] != request_id:
                return
            progress.update(phase=phase, message=message, attempts=attempts,
                            checked_at=checked_at, outcome=outcome, detail=detail)

    class Handler(BaseHTTPRequestHandler):
        def authorized(self):
            if self.client_address[0] == SUPERVISOR_ADDRESS:
                return True
            self.send_error(403)
            return False

        def reply(self, content, media_type):
            self.send_response(200)
            self.send_header("Content-Type", media_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(content)

        def do_GET(self):
            if not self.authorized():
                return
            url = urlsplit(self.path)
            path = url.path
            if path in images:
                try:
                    content = images[path].read_bytes()
                except OSError:
                    self.send_error(404)
                else:
                    self.reply(content, "image/jpeg")
                return
            if path == "/status":
                with request_lock:
                    snapshot = dict(progress)
                self.reply(json.dumps(snapshot).encode("utf-8"), "application/json; charset=utf-8")
                return
            if path != "/":
                self.send_error(404)
                return
            try:
                history = json.loads(history_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                history = {}
            values = {name: html.escape(str(history.get(key) or "–")) for name, key in (
                ("ocr", "ocr_value"), ("reference", "last_reference"), ("detail", "check_detail"),
            )}
            manual = history.get("manual_result", {})
            manual_detail = manual.get("detail", "Noch kein manueller Test.")
            if manual.get("already_checked"):
                manual_detail += " Dieses Bild wurde bereits ausgewertet."
            if manual.get("outside_window"):
                manual_detail += " Das Bild ist für eine neue automatische Bestätigung zu alt."
            settings = manual.get("settings", {})
            auto_rules = get_auto_rules()
            auto_saved_notice = ('<p class="save-notice" role="status">Automatische Prüfregeln gespeichert.</p>'
                                 if url.query == "saved=1" else "")
            rule_label = ("Volle m³" if auto_rules["decimals"] == 0
                          else f'{auto_rules["decimals"]} Nachkommastelle(n)')
            auto_rule_description = f'{rule_label} · max. {auto_rules["attempts"]} OCR-Versuche'
            request_status = (
                "Test angenommen. Die Bearbeitung wird hier live angezeigt."
                if url.query == "test=queued" else "Status wird geladen …"
            )
            self.reply(PAGE.format(**values,
                request_status=request_status,
                polarity_options=select_options(POLARITIES, settings.get("polarity", "auto")),
                decimal_options=select_options(DECIMALS, str(settings.get("decimals", auto_rules["decimals"]))),
                auto_decimal_options=select_options(DECIMALS, str(auto_rules["decimals"])),
                auto_attempt_options=select_options(ATTEMPTS, str(auto_rules["attempts"])),
                auto_saved_notice=auto_saved_notice,
                auto_rule_description=html.escape(auto_rule_description),
                crop_mode_options=select_options(CROP_MODES, settings.get("crop_mode", "auto")),
                crop_value=html.escape(str(settings.get("crop", default_crop)), quote=True),
                width_value=int(settings.get("width", default_width)),

                attempt_options=select_options(ATTEMPTS, str(settings.get("attempts", auto_rules["attempts"]))),
                default_attempts=default_attempts,
                manual_checked_at=manual.get("checked_at", 0),
                manual_image_time=manual.get("image_time", 0),
                manual_ocr=html.escape(str(manual.get("ocr") or "–")),
                manual_reference=html.escape(str(manual.get("reference") or "–")),
                manual_detail=html.escape(manual_detail),
                csrf=csrf_token,
                last_good=history.get("last_match_at") or 0,
                image_time=history.get("last_epoch") or 0,
                next_check=json.dumps(history.get("next_check_at")),
                current='<img src="aktuell.jpg" alt="Aktuelles Kontrollbild">' if current_image.exists() else 'Noch kein Kontrollbild.',
                good='<img src="treffer.jpg" alt="Kontrollbild des letzten Treffers">' if good_image.exists() else 'Noch kein bestätigtes Bild.',
            ).encode("utf-8"), "text/html; charset=utf-8")

        def do_POST(self):
            if not self.authorized():
                return
            path = urlsplit(self.path).path
            if path not in ("/pruefen", "/automatik"):
                self.send_error(404)
                return
            # Ingress and companion webviews need not forward Fetch Metadata headers.
            if self.headers.get_content_type() != "application/x-www-form-urlencoded":
                self.send_error(403)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 512:
                    raise ValueError("Invalid form length")
                form = parse_qs(self.rfile.read(length).decode("ascii"), max_num_fields=8)
            except ValueError:
                self.send_error(400)
                return
            supplied = form.get("csrf", [])
            if len(supplied) != 1 or not compare_digest(supplied[0].encode(), csrf_token.encode()):
                self.send_error(403)
                return
            if path == "/automatik":
                decimals = form.get("decimals", [])
                attempts = form.get("attempts", [])
                if (len(decimals) != 1 or decimals[0] not in DECIMALS
                        or len(attempts) != 1 or attempts[0] not in ATTEMPTS):
                    self.send_error(400)
                    return
                try:
                    save_auto_rules({"decimals": int(decimals[0]), "attempts": int(attempts[0])})
                except (OSError, ValueError):
                    self.send_error(503)
                    return
                self.send_response(303)
                self.send_header("Location", "./?saved=1")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            auto_rules = get_auto_rules()
            polarity = form.get("polarity", ["auto"])
            decimals = form.get("decimals", [str(auto_rules["decimals"])])
            attempts = form.get("attempts", [str(auto_rules["attempts"])])
            crop_mode = form.get("crop_mode", ["auto"])
            crop_text = form.get("crop", [default_crop])
            whole_width = form.get("width", [str(default_width)])
            if (len(polarity) != 1 or polarity[0] not in POLARITIES or len(decimals) != 1
                    or decimals[0] not in DECIMALS or len(attempts) != 1 or attempts[0] not in ATTEMPTS):
                self.send_error(400)
                return
            if len(crop_mode) != 1 or crop_mode[0] not in CROP_MODES:
                self.send_error(400)
                return
            if len(crop_text) != 1 or len(whole_width) != 1:
                self.send_error(400)
                return
            crop_value = default_crop
            width_value = default_width
            if crop_mode[0] == "manual":
                if not re.fullmatch(r"\d{1,4}\s*,\s*\d{1,4}\s*,\s*\d{1,4}\s*,\s*\d{1,4}", crop_text[0]):
                    self.send_error(400)
                    return
                boundaries = [int(number.strip()) for number in crop_text[0].split(",")]
                if not (0 <= boundaries[0] < boundaries[2] <= 1920
                        and 0 <= boundaries[1] < boundaries[3] <= 1920
                        and whole_width[0].isdigit() and 1 <= int(whole_width[0]) <= 1920):
                    self.send_error(400)
                    return
                crop_value = ",".join(map(str, boundaries))
                width_value = int(whole_width[0])
            settings = {"polarity": polarity[0], "decimals": int(decimals[0]),
                        "attempts": int(attempts[0]), "crop_mode": crop_mode[0],
                        "crop": crop_value, "width": width_value}
            with request_lock:
                request_id = progress["request_id"] + 1
                settings["request_id"] = request_id
                progress.update(request_id=request_id, max_attempts=settings["attempts"], outcome=None, detail="", phase="queued",
                                message="Anfrage angenommen – warte auf die Bildprüfung.",
                                attempts=0, started_at=time.time(), checked_at=0)
                try:
                    requested.put_nowait(settings)
                except Full:
                    # The worker may have taken the pending request in the meantime.
                    try:
                        requested.get_nowait()
                    except Empty:
                        pass
                    requested.put_nowait(settings)
            self.send_response(303)
            self.send_header("Location", "./?test=queued")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("0.0.0.0", 8099), Handler)
    Thread(target=server.serve_forever, daemon=True).start()
    return update_progress
