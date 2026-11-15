"""Home Assistant ingress panel for optical gas meter checks."""

import html
import json
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
:root{{color-scheme:light dark;font:16px system-ui}}
body{{max-width:64rem;margin:2rem auto;padding:0 1rem}}
form{{display:flex;flex-wrap:wrap;align-items:end;gap:.75rem}} label{{display:grid;gap:.3rem}}
select,button{{font:inherit}} button{{padding:.55rem 1rem}} dl{{display:grid;grid-template-columns:max-content 1fr;gap:.4rem 1rem}}
dd{{margin:0;overflow-wrap:anywhere}} section{{display:grid;gap:1rem;grid-template-columns:repeat(auto-fit,minmax(min(100%,18rem),1fr))}}
img{{width:100%;height:auto}} h2{{font-size:1rem}}
.intro,.hint{{line-height:1.5;max-width:56rem}} .hint{{font-size:.92rem;opacity:.85}}
.test-box{{border:1px solid #7a8b9a;border-radius:.7rem;padding:1rem;margin:1rem 0 1.5rem;display:grid;gap:.5rem}}
.test-box p{{margin:.15rem 0}} .test-box progress{{width:100%;height:1.2rem;accent-color:#168664}}
.test-box small{{opacity:.8}} .test-box[data-phase="done"]{{border-color:#168664}}
.test-box[data-phase="queued"],.test-box[data-phase="running"],.test-box[data-phase="ocr"]{{border-style:dashed}}
</style>
<h1>Gaszähler OCR-Kontrolle</h1>
<p class="intro">Unabhängiger Bildabgleich deines Gaszählerstands mit der vorhandenen Messung. Die OCR liest die Ziffern erneut direkt aus dem Kamerabild – ohne den vom ESP erkannten Wert einfach zu übernehmen.</p>
<form method="post" action="pruefen">
<input type="hidden" name="csrf" value="{csrf}">
<label>Ziffernfarbe
<select name="polarity">{polarity_options}</select></label>
<label>Vergleichsgenauigkeit
<select name="decimals">{decimal_options}</select></label>
<button>Jetzt prüfen</button>
</form>
<p class="hint"><strong>Was passiert bei „Jetzt prüfen“?</strong> Die App lädt das letzte verfügbare Zählerbild (sie löst am ESP keine neue Aufnahme aus), liest die Ziffern lokal mit Tesseract und vergleicht sie mit dem Referenzstand. Falls die erste Lesung unklar ist oder abweicht, folgen bis zu vier weitere OCR-Aufbereitungen desselben Bilds. Das kann einen Moment dauern. Der manuelle Test verändert weder den automatischen Prüfplan noch den Zählerstand oder die 24-Stunden-Trefferzahl.</p>
<div class="test-box" id="test-box" data-phase="idle" role="status" aria-live="polite">
<strong id="test-head">Manueller OCR-Test</strong>
<p id="test-status">{request_status}</p>
<progress id="test-progress" max="5" value="0" aria-label="OCR-Durchläufe" hidden></progress>
<small id="test-meta">Der aktuelle Bearbeitungsstand wird automatisch aktualisiert.</small>
</div>
<h2>Letzter abgeschlossener manueller Test</h2>
<dl><dt>Getestet um</dt><dd class="stamp" data-epoch="{manual_checked_at}">–</dd>
<dt>Bildzeit</dt><dd class="stamp" data-epoch="{manual_image_time}">–</dd>
<dt>Erkannter Stand</dt><dd>{manual_ocr}</dd>
<dt>Referenz</dt><dd>{manual_reference}</dd>
<dt>Testergebnis</dt><dd>{manual_detail}</dd>{manual_slfork}</dl>
<h2>Automatische Kontrollmessung</h2>
<dl><dt>Nächste Prüfung</dt><dd id="countdown">–</dd>
<dt>Erkannter Stand</dt><dd>{ocr}</dd>
<dt>Referenz</dt><dd>{reference}</dd>
<dt>Prüfergebnis</dt><dd>{detail}</dd>
{slfork}
<dt>Bildzeit</dt><dd class="stamp" data-epoch="{image_time}">–</dd>
<dt>Letzter Treffer</dt><dd class="stamp" data-epoch="{last_good}">–</dd></dl>
<section><div><h2>Aktuelles Bild</h2>{current}</div>
<div><h2>Letzter Treffer</h2>{good}</div></section>
<script>
const next = {next_check};
const lastRenderedManual = Number({manual_checked_at});
let currentPhase = 'idle';
async function refreshTestStatus() {{
  try {{
    const response = await fetch('status', {{cache: 'no-store'}});
    if (!response.ok) throw new Error('Status nicht abrufbar');
    const job = await response.json();
    currentPhase = job.phase;
    const box = document.querySelector('#test-box');
    const bar = document.querySelector('#test-progress');
    const active = ['queued', 'running', 'ocr'].includes(job.phase);
    box.dataset.phase = job.phase;
    document.querySelector('#test-status').textContent = job.message || 'Noch kein manueller Test gestartet.';
    document.querySelector('form button').disabled = active;
    bar.hidden = job.phase === 'idle';
    const done = Math.min(Number(job.attempts) || 0, 5);
    bar.max = 5;
    if (job.phase === 'queued' || job.phase === 'running') bar.removeAttribute('value');
    else bar.value = job.phase === 'done' ? 5 : done;
    const seconds = job.started_at ? Math.floor(Math.max(0, Date.now()/1000 - job.started_at)) : 0;
    let meta = active ? 'Verstrichen: ' + seconds + ' s · keine verlässliche Restzeit möglich' : '';
    if (job.phase === 'ocr') meta = 'OCR-Aufbereitungen: ' + done + '/5 · ' + meta;
    if (job.phase === 'done') meta = 'Test beendet; OCR-Durchläufe: ' + done + '/5. Ergebnis unten.';
    if (job.phase === 'idle') meta = 'Bereit für einen manuellen Test.';
    document.querySelector('#test-meta').textContent = meta;
    if (job.phase === 'done' && Number(job.checked_at) > lastRenderedManual + .001) {{
      location.reload();
    }}
  }} catch (_) {{
    document.querySelector('#test-meta').textContent = 'Live-Status nicht erreichbar. Verbindung zur App prüfen.';
  }}
}}
refreshTestStatus();
setInterval(refreshTestStatus, 1000);
function tick() {{
  const out = document.querySelector('#countdown');
  if (!next) return;
  const seconds = Math.max(0, Math.ceil(next - Date.now() / 1000));
  out.textContent = seconds ? Math.floor(seconds / 60) + ':' + String(seconds % 60).padStart(2,'0') + ' min' : 'Prüfung fällig';
}}
for (const el of document.querySelectorAll('.stamp')) {{
  const epoch = Number(el.dataset.epoch);
  if (epoch) el.textContent = new Date(epoch * 1000).toLocaleString('de-DE');
}}
if (location.search === '?test=queued') history.replaceState(null, '', location.pathname);
let edited = false;
document.querySelector('form').addEventListener('change', () => {{ edited = true; }});
tick(); setInterval(tick, 1000);
setInterval(() => {{
  if (!edited && !['queued','running','ocr'].includes(currentPhase) &&
      !document.querySelector('form').contains(document.activeElement)) location.reload();
}}, 15000);
</script></html>"""


POLARITIES = {"auto": "Automatisch", "light": "Hell", "dark": "Dunkel"}
DECIMALS = {"0": "Volle Kubikmeter", "1": "1 Nachkommastelle", "2": "2 Nachkommastellen", "3": "3 Nachkommastellen"}


def select_options(choices, chosen):
    return "".join(
        f'<option value="{value}"{" selected" if value == chosen else ""}>{label}</option>'
        for value, label in choices.items()
    )


def diagnostic_rows(data):
    fields = (
        ("slfork_value_status", "AI on the Edge · Wertstatus"),
        ("slfork_process_status", "Messbetrieb"),
        ("slfork_process_state", "Messphase"),
        ("slfork_process_error", "Prozessfehlercode"),
        ("slfork_last_processed_timestamp", "Letzte Messung am ESP"),
        ("slfork_last_valid_timestamp", "Zeit des letzten gültigen Stands"),
    )
    return "".join(
        f"<dt>{label}</dt><dd>{html.escape(str(data[key]))}</dd>"
        for key, label in fields if data.get(key) not in (None, "")
    )


def start_panel(history_path, current_image, good_image, requested, default_decimals):
    images = {"/aktuell.jpg": current_image, "/treffer.jpg": good_image}
    csrf_token = token_urlsafe(32)
    request_lock = Lock()
    progress = {
        "request_id": 0, "phase": "idle", "message": "Noch kein manueller Test gestartet.",
        "attempts": 0, "started_at": 0, "checked_at": 0,
    }

    def update_progress(request_id, phase, message, attempts=0, checked_at=0):
        """Only the newest request may update the visible status."""
        with request_lock:
            if progress["request_id"] != request_id:
                return
            progress.update(phase=phase, message=message, attempts=attempts,
                            checked_at=checked_at)

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
                manual_detail += " Die Bildzeit liegt außerhalb des Zeitfensters für automatische Prüfungen."
            settings = manual.get("settings", {})
            request_status = (
                "Test angenommen. Die Bearbeitung wird hier live angezeigt."
                if url.query == "test=queued" else "Status wird geladen …"
            )
            self.reply(PAGE.format(**values,
                request_status=request_status,
                polarity_options=select_options(POLARITIES, settings.get("polarity", "auto")),
                decimal_options=select_options(DECIMALS, str(settings.get("decimals", default_decimals))),
                manual_checked_at=manual.get("checked_at", 0),
                manual_image_time=manual.get("image_time", 0),
                manual_ocr=html.escape(str(manual.get("ocr") or "–")),
                manual_reference=html.escape(str(manual.get("reference") or "–")),
                manual_detail=html.escape(manual_detail),
                manual_slfork=diagnostic_rows(manual.get("slfork_diagnostics", {})),
                slfork=diagnostic_rows(history.get("slfork_diagnostics", {})),
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
            if urlsplit(self.path).path != "/pruefen":
                self.send_error(404)
                return
            # Ingress and companion webviews need not forward Fetch Metadata headers.
            if self.headers.get_content_type() != "application/x-www-form-urlencoded":
                self.send_error(403)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 256:
                    raise ValueError("Invalid form length")
                form = parse_qs(self.rfile.read(length).decode("ascii"), max_num_fields=4)
            except ValueError:
                self.send_error(400)
                return
            supplied = form.get("csrf", [])
            if len(supplied) != 1 or not compare_digest(supplied[0].encode(), csrf_token.encode()):
                self.send_error(403)
                return
            polarity = form.get("polarity", ["auto"])
            decimals = form.get("decimals", [str(default_decimals)])
            if len(polarity) != 1 or polarity[0] not in POLARITIES or len(decimals) != 1 or decimals[0] not in DECIMALS:
                self.send_error(400)
                return
            settings = {"polarity": polarity[0], "decimals": int(decimals[0])}
            with request_lock:
                request_id = progress["request_id"] + 1
                settings["request_id"] = request_id
                progress.update(request_id=request_id, phase="queued",
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
