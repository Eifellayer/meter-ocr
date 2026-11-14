"""Home Assistant ingress panel for RF1 diagnostics."""

import html
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from queue import Empty, Full
from secrets import compare_digest, token_urlsafe
from threading import Lock, Thread
from urllib.parse import parse_qs, urlsplit

SUPERVISOR_ADDRESS = "172.30.32.2"

PAGE = """<!doctype html>
<html lang="de"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>RF1 Kontrollmessung</title>
<style>
:root{{color-scheme:light dark;font:16px system-ui}}
body{{max-width:64rem;margin:2rem auto;padding:0 1rem}}
form{{display:flex;flex-wrap:wrap;align-items:end;gap:.75rem}} label{{display:grid;gap:.3rem}}
select,button{{font:inherit}} button{{padding:.55rem 1rem}} dl{{display:grid;grid-template-columns:max-content 1fr;gap:.4rem 1rem}}
dd{{margin:0;overflow-wrap:anywhere}} section{{display:grid;gap:1rem;grid-template-columns:repeat(auto-fit,minmax(min(100%,18rem),1fr))}}
img{{width:100%;height:auto}} h2{{font-size:1rem}}
</style>
<h1>RF1 Kontrollmessung</h1>
<form method="post" action="pruefen">
<input type="hidden" name="csrf" value="{csrf}">
<label>Ziffernfarbe
<select name="polarity">{polarity_options}</select></label>
<label>Vergleichsgenauigkeit
<select name="decimals">{decimal_options}</select></label>
<button>Jetzt prüfen</button>
</form>
{request_status}
<h2>Letzter manueller Test</h2>
<dl><dt>Getestet um</dt><dd class="stamp" data-epoch="{manual_checked_at}">–</dd>
<dt>Bildzeit</dt><dd class="stamp" data-epoch="{manual_image_time}">–</dd>
<dt>Erkannter Stand</dt><dd>{manual_ocr}</dd>
<dt>Referenz</dt><dd>{manual_reference}</dd>
<dt>Testergebnis</dt><dd>{manual_detail}</dd></dl>
<h2>Automatische Kontrollmessung</h2>
<dl><dt>Nächste Prüfung</dt><dd id="countdown">–</dd>
<dt>Erkannter Stand</dt><dd>{ocr}</dd>
<dt>Referenz</dt><dd>{reference}</dd>
<dt>Prüfergebnis</dt><dd>{detail}</dd>
<dt>Bildzeit</dt><dd class="stamp" data-epoch="{image_time}">–</dd>
<dt>Letzter Treffer</dt><dd class="stamp" data-epoch="{last_good}">–</dd></dl>
<section><div><h2>Aktuelles Bild</h2>{current}</div>
<div><h2>Letzter Treffer</h2>{good}</div></section>
<script>
const next = {next_check};
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
  if (!edited && !document.querySelector('form').contains(document.activeElement)) location.reload();
}}, 15000);
</script></html>"""


POLARITIES = {"auto": "Automatisch", "light": "Hell", "dark": "Dunkel"}
DECIMALS = {"0": "Volle Kubikmeter", "1": "1 Nachkommastelle", "2": "2 Nachkommastellen", "3": "3 Nachkommastellen"}


def select_options(choices, chosen):
    return "".join(
        f'<option value="{value}"{" selected" if value == chosen else ""}>{label}</option>'
        for value, label in choices.items()
    )


def start_panel(history_path, current_image, good_image, requested, default_decimals):
    images = {"/aktuell.jpg": current_image, "/treffer.jpg": good_image}
    csrf_token = token_urlsafe(32)
    request_lock = Lock()

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
                '<p role="status">Test angefordert. Das Ergebnis erscheint unten.</p>'
                if url.query == "test=queued" else ""
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
