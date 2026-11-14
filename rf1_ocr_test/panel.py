"""Home Assistant ingress panel for RF1 diagnostics."""

import html
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import urlsplit

SUPERVISOR_ADDRESS = "172.30.32.2"

PAGE = """<!doctype html>
<html lang="de"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>RF1 Kontrollmessung</title>
<style>
:root{{color-scheme:light dark;font:16px system-ui}}
body{{max-width:64rem;margin:2rem auto;padding:0 1rem}}
button{{font:inherit;padding:.55rem 1rem}} dl{{display:grid;grid-template-columns:max-content 1fr;gap:.4rem 1rem}}
dd{{margin:0;overflow-wrap:anywhere}} section{{display:grid;gap:1rem;grid-template-columns:repeat(auto-fit,minmax(min(100%,18rem),1fr))}}
img{{width:100%;height:auto}} h2{{font-size:1rem}}
</style>
<h1>RF1 Kontrollmessung</h1>
<form method="post" action="pruefen"><button>Jetzt prüfen</button></form>
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
tick(); setInterval(tick, 1000); setTimeout(() => location.reload(), 15000);
</script></html>"""


def start_panel(history_path, current_image, good_image, requested):
    images = {"/aktuell.jpg": current_image, "/treffer.jpg": good_image}

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
            path = urlsplit(self.path).path
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
            self.reply(PAGE.format(**values,
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
            if self.headers.get("Sec-Fetch-Site") not in ("same-origin", "none"):
                self.send_error(403)
                return
            requested.set()
            self.send_response(303)
            self.send_header("Location", "./")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("0.0.0.0", 8099), Handler)
    Thread(target=server.serve_forever, daemon=True).start()
