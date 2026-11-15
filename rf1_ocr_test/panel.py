"""Home Assistant ingress panel for optical gas meter checks."""

import html
import json
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from queue import Full
from secrets import compare_digest, token_urlsafe
from threading import Lock, Thread
from urllib.parse import parse_qs, urlsplit

from i18n import EN_UI, english_progress, english_result, translate_page
from language import MODES, SUPPORTED, USER_ID, browser_locale, profile_script

SUPERVISOR_ADDRESS = "172.30.32.2"

PAGE = """<!doctype html>
<html lang="{language}"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Gaszähler OCR-Kontrolle</title>
<style>.resolving-language body{{visibility:hidden}}</style>
{profile_script}
<style>
:root{{color-scheme:light dark;font:15px system-ui,-apple-system,sans-serif;--edge:light-dark(#dfe6ec,#34424d);--surface:light-dark(#fff,#1b252e);--muted:light-dark(#536475,#aebcc8);--page:light-dark(#f4f7f9,#111a22)}}
*{{box-sizing:border-box}}
body{{max-width:62rem;margin:0 auto;padding:1.5rem 1rem 3rem;background:var(--page);color:light-dark(#162b3b,#e8f0f5);line-height:1.45}}
h1{{font-size:clamp(1.5rem,4vw,2rem);letter-spacing:-.03em;margin:.2rem 0 .25rem}}
h2{{font-size:1rem;margin:0 0 .85rem;letter-spacing:-.01em}}
.language-bar{{display:flex;align-items:center;justify-content:flex-end;gap:.45rem;margin:0 0 .5rem}}
.language-bar label{{display:block;font-size:.8rem;font-weight:500}}
.language-bar select{{min-height:2rem;padding:.25rem .5rem;font-size:.85rem}}
.panel{{background:var(--surface);border:1px solid var(--edge);border-radius:1rem;padding:1.15rem 1.25rem;margin:0 0 1rem;box-shadow:0 3px 14px light-dark(#162b3b09,#0002)}}
form{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,10.5rem),1fr));align-items:end;gap:.8rem}}
form > button{{justify-self:start}}
form > .crop-fields{{grid-column:1/-1}}
form label,form select,form input{{min-width:0}}
header{{display:flex;align-items:baseline;justify-content:space-between;gap:.5rem 1rem;flex-wrap:wrap;margin-bottom:1rem}}
.language-bar{{display:flex;flex-wrap:wrap}}
.language-bar select,.language-bar button{{min-height:2.75rem}}
.automatic-images{{margin:1rem 0}}
.automatic-images > summary{{cursor:pointer;color:var(--muted)}}
.test-box :where(p,small){{overflow-wrap:anywhere}}
label{{display:grid;gap:.3rem;font-weight:600;font-size:.85rem;color:var(--muted)}}
select,button{{font:inherit;border-radius:.55rem;padding:.62rem .8rem;min-height:2.55rem}}
select{{background:var(--surface);border:1px solid var(--edge);color:inherit}}
button{{border:1px solid light-dark(#b2c4d1,#667988);background:light-dark(#dce6ed,#354b5a);color:light-dark(#28445a,#e9f4fc);font-weight:650;padding:.62rem 1.1rem;cursor:pointer;transition:background .15s}}
button:not(:disabled):hover{{background:light-dark(#ccdce6,#445e70)}}
button:disabled{{opacity:.65;cursor:wait}}
button:focus-visible,select:focus-visible,input:focus-visible,summary:focus-visible{{outline:3px solid #65bcaf;outline-offset:2px}}
input{{font:inherit;border-radius:.55rem;padding:.62rem .8rem;min-height:2.55rem;max-width:100%;background:var(--surface);border:1px solid var(--edge);color:inherit}}
.manual-panel > summary{{display:flex;align-items:center;justify-content:space-between;gap:1rem;cursor:pointer;list-style:none}}
.manual-panel > summary::-webkit-details-marker{{display:none}}
.manual-panel > summary::after{{content:"▾";font-size:1.2rem;color:var(--muted)}}
.manual-panel[open] > summary::after{{content:"▴"}}
.manual-content{{margin-top:1.2rem;padding-top:1rem;border-top:1px solid var(--edge)}}
.settings-note{{font-size:.85rem;color:var(--muted);margin:.7rem 0 0}}
.save-notice{{font-size:.88rem;color:light-dark(#1e7650,#8ad4a9);margin:.7rem 0 0}}
.crop-fields{{display:flex;gap:.8rem;flex-wrap:wrap;margin-top:.7rem}}
.crop-fields label:first-child{{flex:2 1 17rem}}.crop-fields label:last-child{{flex:1 1 10rem}}
.crop-fields[hidden]{{display:none}}
.preview{{margin-top:1rem;padding-top:1rem;border-top:1px solid var(--edge)}}
.preview img{{display:block;width:100%;max-width:740px;height:auto;border-radius:.5rem;border:1px solid var(--edge)}}
.preview .legend{{margin:.45rem 0 0;font-size:.86rem;color:var(--muted)}}
.green-key{{color:light-dark(#13824c,#7bcfa3);font-weight:700}}
.red-key{{color:light-dark(#b43c44,#eda2a8);font-weight:700}}
.apply-crop{{margin-top:.8rem}}
.ocr-details{{margin:.7rem 0;font-size:.9rem}}
.ocr-details summary{{cursor:pointer;color:var(--muted);font-weight:600;padding:.35rem 0}}
.ocr-details table{{border-collapse:collapse;width:100%;margin-top:.5rem;max-width:30rem}}
.ocr-details th,.ocr-details td{{padding:.35rem .5rem;border-bottom:1px solid var(--edge);text-align:left}}
.ocr-details th{{color:var(--muted);font-weight:600}}
.ocr-details td:last-child{{font-family:ui-monospace,SFMono-Regular,monospace;font-variant-numeric:tabular-nums}}
.page-footer{{margin:1.6rem 0 .3rem;text-align:center;font-size:.8rem;color:var(--muted)}}
.page-footer a{{color:inherit;text-underline-offset:3px}}
.page-footer a:hover{{color:light-dark(#1c5d77,#9bcbe8)}}
[hidden]{{display:none!important}}
.hint{{font-size:.85rem;color:var(--muted);margin:1rem 0 0;line-height:1.55}}
.test-box{{border:1px solid var(--edge);background:light-dark(#f5f7f9,#1d2832);border-radius:.8rem;padding:.95rem 1rem;margin:1rem 0 0;display:grid;gap:.35rem}}
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
.test-box progress{{width:100%;height:.7rem;margin:.45rem 0;border:0;border-radius:99px;overflow:hidden;accent-color:light-dark(#718fa3,#819aab)}}
.test-box progress::-webkit-progress-bar{{background:light-dark(#e1e9e7,#354842);border-radius:99px}}
.test-box progress::-webkit-progress-value{{background:light-dark(#718fa3,#819aab);border-radius:99px}}

dl{{display:grid;grid-template-columns:minmax(8rem,11rem) minmax(0,1fr);gap:.5rem 1rem;margin:0}}
dt{{color:var(--muted);font-size:.9rem}}
dd{{margin:0;min-width:0;overflow-wrap:anywhere;font-variant-numeric:tabular-nums;font-weight:550}}
section{{display:grid;gap:1rem;grid-template-columns:repeat(auto-fit,minmax(min(100%,18rem),1fr));margin-top:1rem}}
section>div{{background:var(--surface);border:1px solid var(--edge);border-radius:1rem;padding:1rem;overflow:hidden}}
section img{{width:100%;height:auto;display:block;border-radius:.55rem}}
.stamp,#countdown{{font-variant-numeric:tabular-nums}}
@media(max-width:500px){{body{{padding:.8rem .7rem 2rem}}.panel{{padding:.9rem}}dl{{grid-template-columns:minmax(5.5rem,1fr) minmax(0,1.7fr);gap:.5rem .85rem}}form:not(.language-bar) button{{width:100%;min-height:2.75rem}}}}
</style>
<header>
<h1>Gaszähler OCR-Kontrolle</h1>
<form method="post" action="sprache" class="language-bar" id="language-form">
<input type="hidden" name="csrf" value="{csrf}">
<label for="language-select">Sprache / Language</label>
<select id="language-select" name="mode">{language_options}</select>
<noscript><button type="submit">Speichern</button></noscript>
</form>
</header>
<div class="panel"><h2>Automatische Kontrolle</h2>
<dl><dt>Prüfergebnis</dt><dd id="automatic-result">{detail}</dd>
<dt>Erkannter Stand</dt><dd id="automatic-ocr">{ocr}</dd>
<dt>Referenz</dt><dd id="automatic-reference">{reference}</dd>
<dt>Bildzeit</dt><dd id="automatic-image-time" class="stamp" data-epoch="{image_time}">–</dd>
<dt>Nächste Prüfung</dt><dd id="countdown">–</dd></dl>
<details class="ocr-details" id="automatic-ocr-details" hidden>
<summary>Mehr Infos: Was wurde bei den OCR-Versuchen gelesen?</summary>
<p class="ocr-scope"></p>
<p>? steht für eine unklare Ziffer.</p>
<table><thead><tr><th>Versuch</th><th>Erkannter Stand</th></tr></thead><tbody></tbody></table>
</details>
<details class="automatic-images"><summary>Kontrollbilder</summary>
<section><div><h2>Aktuelles Bild</h2><div id="automatic-current">{current}</div></div>
<div><h2>Letzter Treffer</h2><div id="automatic-good">{good}</div></div></section>
</details>
</div>
<details class="panel manual-panel" id="automatic-settings" {settings_open}>
<summary><strong>Automatische Prüfung – Einstellungen</strong></summary>
<div class="manual-content">
<form method="post" action="automatik" id="auto-form">
<input type="hidden" name="lang" value="{language}">
<input type="hidden" name="mode" value="{language_mode}">
<input type="hidden" name="csrf" value="{csrf}">
<label>Vergleich
<select name="decimals">{auto_decimal_options}</select></label>
<label>Max. OCR-Versuche
<select name="attempts">{auto_attempt_options}</select></label>
<label>Ziffernfarbe
<select name="polarity">{auto_polarity_options}</select></label>
<label>Bildbereich
<select name="crop_mode" id="auto-crop-mode">{auto_crop_mode_options}</select></label>
<div class="crop-fields" id="auto-crop-fields" hidden>
<label>Bildbereich (links, oben, rechts, unten)
<input name="crop" type="text" value="{auto_crop_value}" maxlength="30" placeholder="52,56,564,132"></label>
<label>Breite der Vorkommastellen
<input name="width" type="number" min="1" max="1920" value="{auto_width_value}"></label>
</div>
<button type="submit">Speichern</button>
</form>
<p class="settings-note">Gilt dauerhaft ab der nächsten automatischen Prüfung. Bei geänderter Vergleichsgenauigkeit beginnt die Trefferzählung neu.</p>
{auto_saved_notice}
</div></details>
<details class="panel manual-panel" id="manual-panel" {manual_open}>
<summary><strong>Manuellen Test öffnen</strong></summary>
<div class="manual-content">
<form method="post" action="pruefen" id="manual-form">
<input type="hidden" name="lang" value="{language}">
<input type="hidden" name="mode" value="{language_mode}">
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
<dl id="manual-readings" hidden><dt>Erkannter Stand</dt><dd id="manual-ocr"></dd><dt>Referenz</dt><dd id="manual-reference"></dd></dl>
<small id="test-result-stamp"></small>
<details class="ocr-details" id="ocr-details" hidden>
<summary>Mehr Infos: Was wurde bei den OCR-Versuchen gelesen?</summary>
<p class="ocr-scope"></p>
<p>? steht für eine unklare Ziffer.</p>
<table><thead><tr><th>Versuch</th><th>Erkannter Stand</th></tr></thead>
<tbody></tbody></table>
</details>
</div>
<div class="preview" id="test-preview" hidden>
<h2>OCR-Testbild mit erkannten Stellen</h2>
<img id="test-preview-image" alt="Zählerbild mit grün markierten erkannten Ziffern und rot markierten unklaren Stellen">
<p class="legend"><span class="green-key">Grün:</span> Ziffer wurde gelesen · <span class="red-key">Rot:</span> Ziffer unklar. Die Farbrahmen zeigen die OCR-Erkennung, nicht die Übereinstimmung mit dem Referenzstand. Ohne automatisch erkannte Ziffernrahmen sind die Bereiche nur näherungsweise aufgeteilt.</p>
</div>
<form method="post" action="ausschnitt-uebernehmen" id="apply-crop-form" class="apply-crop" hidden>
<input type="hidden" name="checked_at" id="tested-crop-id">
<input type="hidden" name="lang" value="{language}">
<input type="hidden" name="mode" value="{language_mode}">
<input type="hidden" name="csrf" value="{csrf}">
<button type="submit">Getesteten Ausschnitt für die Automatik übernehmen</button>
</form>
</div></div></details>

<footer class="page-footer">Kostenloses Hobbyprojekt · <a href="https://www.paypal.com/donate/?hosted_button_id=FG4Q7VKQJ9BW8" target="_blank" rel="noopener noreferrer">Freiwillig unterstützen (PayPal)</a></footer>
<script>
let next = {next_check};
const lang = '{language}';
const searchPrefs = new URLSearchParams(location.search);
if (searchPrefs.has('ui')) {{
  searchPrefs.delete('ui');
  history.replaceState(null, '', location.pathname + (searchPrefs.size ? '?' + searchPrefs : ''));
}}
document.querySelector('#language-select').addEventListener('change', () => {{
  const url = new URL(document.querySelector('#language-form').action);
  if (document.querySelector('#manual-panel').open) url.searchParams.set('test', 'open');
  document.querySelector('#language-form').action = url;
  document.querySelector('#language-form').submit();
}});

let sendingCheck = false;
let statusPending = false;
const manualPanel = document.querySelector('#manual-panel');
const manualForm = document.querySelector('#manual-form');
const cropMode = document.querySelector('#crop-mode');
const cropFields = document.querySelector('#crop-fields');
const autoCropMode = document.querySelector('#auto-crop-mode');
const autoCropFields = document.querySelector('#auto-crop-fields');
function showAutoCropFields() {{
  autoCropFields.hidden = autoCropMode.value !== 'manual';
}}
autoCropMode.addEventListener('change', showAutoCropFields);
showAutoCropFields();
function showCropFields() {{
  cropFields.hidden = cropMode.value !== 'manual';
}}
cropMode.addEventListener('change', showCropFields);
showCropFields();
function renderAttempts(details, readings, decimals) {{
  details.hidden = !Array.isArray(readings) || !readings.length;
  if (details.hidden) return;
  details.querySelector('.ocr-scope').textContent = decimals === 0 ?
    'Verglichen wurden nur die vollen Kubikmeter (ohne Nachkommastellen).' :
    'Verglichen wurden die vollen Kubikmeter und ' + decimals + ' Nachkommastelle(n).';
  const body = details.querySelector('tbody');
  const key = JSON.stringify(readings);
  if (body.dataset.values === key) return;
  body.replaceChildren();
  readings.slice(0, 10).forEach((value, index) => {{
    const row = body.insertRow();
    row.insertCell().textContent = String(index + 1);
    row.insertCell().textContent = String(value ?? '?');
  }});
  body.dataset.values = key;
}}
async function refreshTestStatus() {{
  if (statusPending || sendingCheck) return;
  statusPending = true;
  try {{
    const response = await fetch('status?lang=' + lang, {{cache: 'no-store'}});
    if (!response.ok) throw new Error();
    const job = await response.json();
    if (sendingCheck) return;
    const box = document.querySelector('#test-box');
    const bar = document.querySelector('#test-progress');
    const button = document.querySelector('#start-check');
    const detail = document.querySelector('#test-result');
    const preview = document.querySelector('#test-preview');
    const apply = document.querySelector('#apply-crop-form');
    const extra = document.querySelector('#ocr-details');
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
      document.querySelector('#manual-readings').hidden = !job.ocr && job.reference == null;
      document.querySelector('#manual-ocr').textContent = job.ocr ?? '–';
      document.querySelector('#manual-reference').textContent = job.reference ?? '–';
      document.querySelector('#test-result-detail').textContent = job.detail || job.message || 'Kein Ergebnis.';
      document.querySelector('#test-result-stamp').textContent = job.checked_at ?
        new Intl.DateTimeFormat(lang === 'en' ? 'en-GB' : 'de-DE', {{day:'2-digit', month:'2-digit', year:'2-digit', hour:'2-digit', minute:'2-digit'}}).format(new Date(job.checked_at*1000)) : '';
      renderAttempts(extra, job.readings, job.comparison_decimals);
    }} else {{
      detail.hidden = true;
      extra.hidden = true;
    }}
    preview.hidden = !(job.phase === 'done' && job.preview);
    if (!preview.hidden) {{
      const image = document.querySelector('#test-preview-image');
      const url = 'testvorschau.jpg?v=' + encodeURIComponent(String(job.checked_at));
      if (image.getAttribute('src') !== url) image.setAttribute('src', url);
    }}
    apply.hidden = !(job.phase === 'done' && job.can_apply_crop);
    document.querySelector('#tested-crop-id').value = job.crop_id || '';
  }} catch (_) {{
    document.querySelector('#test-meta').textContent = 'Status nicht erreichbar – Verbindung prüfen.';
  }} finally {{
    statusPending = false;
  }}
}}
refreshTestStatus();
setInterval(refreshTestStatus, 1000);
function tick() {{
  const out = document.querySelector('#countdown');
  if (!next) {{
    out.textContent = '–';
    return;
  }}
  const seconds = Math.max(0, Math.ceil(next - Date.now() / 1000));
  out.textContent = seconds ? Math.floor(seconds / 60) + ':' + String(seconds % 60).padStart(2,'0') + ' min' : 'Jetzt fällig';
}}
const formatStamp = epoch => new Intl.DateTimeFormat(lang === 'en' ? 'en-GB' : 'de-DE', {{day:'2-digit', month:'2-digit', year:'2-digit', hour:'2-digit', minute:'2-digit'}}).format(new Date(epoch * 1000));
for (const el of document.querySelectorAll('.stamp')) {{
  const epoch = Number(el.dataset.epoch);
  if (epoch) el.textContent = formatStamp(epoch);
}}
if (['queued', 'open', 'busy'].includes(searchPrefs.get('test'))) {{
  manualPanel.open = true;
  searchPrefs.delete('test');
  history.replaceState(null, '', location.pathname + (searchPrefs.size ? '?' + searchPrefs : ''));
}}
manualForm.addEventListener('submit', event => {{
  if (sendingCheck) {{
    event.preventDefault();
    return;
  }}
  sendingCheck = true;
  const box = document.querySelector('#test-box');
  box.dataset.phase = 'queued';
  box.dataset.result = 'neutral';
  document.querySelector('#test-head').textContent = 'Anfrage wird gesendet';
  document.querySelector('#test-status').textContent = 'Prüfung läuft …';
  document.querySelector('#test-result').hidden = true;
  document.querySelector('#ocr-details').hidden = true;
  document.querySelector('#test-preview').hidden = true;
  document.querySelector('#apply-crop-form').hidden = true;
  const button = document.querySelector('#start-check');
  button.disabled = true;
  button.textContent = 'Prüfung läuft …';
}});
tick(); setInterval(tick, 1000);
async function refreshAutomatic() {{
  try {{
    const response = await fetch('automatic?lang=' + lang, {{cache: 'no-store'}});
    if (!response.ok) throw new Error();
    const sample = await response.json();
    next = sample.next_check;
    document.querySelector('#automatic-result').textContent = sample.detail;
    document.querySelector('#automatic-ocr').textContent = sample.ocr;
    document.querySelector('#automatic-reference').textContent = sample.reference;
    renderAttempts(document.querySelector('#automatic-ocr-details'), sample.readings, sample.decimals);
    const stamp = document.querySelector('#automatic-image-time');
    stamp.textContent = sample.image_time ? formatStamp(sample.image_time) : '–';
    for (const [name, file] of [['current', 'aktuell.jpg'], ['good', 'treffer.jpg']]) {{
      const timestamp = sample[name];
      if (!timestamp) continue;
      const container = document.querySelector('#automatic-' + name);
      const image = container.querySelector('img') || document.createElement('img');
      const url = file + '?v=' + timestamp;
      if (image.getAttribute('src') === url) continue;
      image.alt = name === 'current' ? 'Aktuelles Kontrollbild' : 'Kontrollbild des letzten Treffers';
      image.src = url;
      if (!image.parentNode) container.replaceChildren(image);
    }}
  }} catch (_) {{ /* Keep the last available result while reconnecting. */ }}
  setTimeout(refreshAutomatic, 15000);
}}
refreshAutomatic();
</script></html>"""


POLARITIES = {"auto": "Automatisch", "light": "Hell", "dark": "Dunkel"}
DECIMALS = {"0": "Volle Kubikmeter", "1": "1 Nachkommastelle", "2": "2 Nachkommastellen", "3": "3 Nachkommastellen"}
ATTEMPTS = {str(value): str(value) for value in range(1, 11)}
CROP_MODES = {"auto": "Automatisch erkennen", "manual": "Ausschnitt selbst festlegen"}
POLARITIES_EN = {"auto": "Automatic", "light": "Light digits", "dark": "Dark digits"}
DECIMALS_EN = {"0": "Whole cubic meters", "1": "1 decimal place",
               "2": "2 decimal places", "3": "3 decimal places"}
CROP_MODES_EN = {"auto": "Detect automatically", "manual": "Specify crop"}


def select_options(choices, chosen):
    return "".join(
        f'<option value="{value}"{" selected" if value == chosen else ""}>{label}</option>'
        for value, label in choices.items()
    )


def start_panel(
    history_path, current_image, good_image, requested, default_decimals, default_attempts,
    get_auto_rules, save_auto_rules, default_crop, default_width, test_image,
    load_language_modes, save_language_modes, *, address=("0.0.0.0", 8099),
):
    images = {"/aktuell.jpg": current_image, "/treffer.jpg": good_image,
              "/testvorschau.jpg": test_image}
    csrf_token = token_urlsafe(32)
    request_lock = Lock()
    preferences_lock = Lock()
    rules_lock = Lock()
    progress = {
        "request_id": 0, "phase": "idle", "message": "Noch kein manueller Test gestartet.",
        "attempts": 0, "max_attempts": default_attempts,
        "started_at": 0, "checked_at": 0, "outcome": None, "detail": "",
        "preview": False, "can_apply_crop": False, "readings": [],
        "comparison_decimals": default_decimals, "ocr": None, "reference": None,
    }
    try:
        saved_history = json.loads(history_path.read_text(encoding="utf-8"))
        previous = saved_history.get("manual_result", {})
        if previous.get("checked_at"):
            progress.update(
                phase="done", message="Letzter manueller Test",
                attempts=previous.get("ocr_attempts", 0),
                max_attempts=previous.get("settings", {}).get("attempts", default_attempts),
                checked_at=previous["checked_at"],
                outcome=previous.get("status", "capture_unavailable"),
                detail=previous.get("detail", "Kein Prüfergebnis gespeichert."),
                preview=bool(previous.get("preview") and test_image.exists()),
                can_apply_crop=bool(previous.get("can_apply_crop") and test_image.exists()),
                ocr=previous.get("ocr"), reference=previous.get("reference"),
                readings=previous.get("readings", []),
                comparison_decimals=previous.get("settings", {}).get("decimals", default_decimals),
            )
    except (OSError, ValueError, AttributeError, TypeError):
        pass

    def update_progress(request_id, phase, message, attempts=0, checked_at=0, outcome=None,
                        detail="", preview=False, can_apply_crop=False, readings=None,
                        ocr=None, reference=None):
        """Only the newest request may update the visible status."""
        with request_lock:
            if progress["request_id"] != request_id:
                return
            progress.update(phase=phase, message=message, attempts=attempts,
                            checked_at=checked_at, outcome=outcome, detail=detail,
                            preview=preview, can_apply_crop=can_apply_crop, ocr=ocr, reference=reference,
                            readings=readings if readings is not None else progress["readings"])

    def read_history():
        try:
            history = json.loads(history_path.read_text(encoding="utf-8"))
            return history if isinstance(history, dict) else {}
        except (OSError, ValueError):
            return {}

    def automatic_summary(history, language, auto_rules):
        detail = history.get("check_detail")
        precision_pending = (history.get("comparison_decimals") is not None
                             and history["comparison_decimals"] != auto_rules["decimals"])
        if precision_pending:
            detail = ("Neue Vergleichsgenauigkeit gespeichert. Die nächste automatische "
                      "Prüfung zeigt das erste Ergebnis mit dieser Einstellung.")
        if language == "en" and detail:
            detail = english_result(
                detail, history.get("check_status") or history.get("status"),
                history.get("comparison_decimals", default_decimals), history.get("ocr_readings"),
            )
        return {
            "detail": detail or "–",
            "ocr": str(history["ocr_value"]) if history.get("ocr_value") is not None else "–",
            "reference": str(history["last_reference"]) if history.get("last_reference") is not None else "–",
            "image_time": history.get("last_epoch") or 0,
            "next_check": history.get("next_check_at"),
            "readings": (history.get("ocr_readings", []) if not precision_pending
                         and history.get("check_status") == "ocr_unclear" else []),
            "decimals": history.get("comparison_decimals", default_decimals),
            "current": current_image.stat().st_mtime_ns if current_image.exists() else None,
            "good": good_image.stat().st_mtime_ns if good_image.exists() else None,
        }

    class Handler(BaseHTTPRequestHandler):
        def authorized(self):
            if self.client_address[0] == SUPERVISOR_ADDRESS:
                return True
            self.send_error(403)
            return False

        def user_id(self):
            value = self.headers.get("X-Remote-User-Id", "")
            return value if USER_ID.fullmatch(value) else None

        def redirect(self, suffix=""):
            self.send_response(303)
            self.send_header("Location", "./" + suffix)
            self.send_header("Content-Length", "0")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()

        def reply(self, content, media_type):
            self.send_response(200)
            self.send_header("Content-Type", media_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(content)

        def do_GET(self):
            if not self.authorized():
                return
            url = urlsplit(self.path)
            path = url.path
            query = parse_qs(url.query)
            requested_lang = query.get("lang", [""])[0]
            fallback = browser_locale(self.headers.get("Accept-Language", ""))
            language = requested_lang if requested_lang in SUPPORTED else fallback
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
                snapshot["crop_id"] = str(snapshot["checked_at"]) if snapshot["can_apply_crop"] else ""
                if language == "en":
                    snapshot["message"] = english_progress(snapshot.get("message"))
                    if snapshot.get("detail"):
                        snapshot["detail"] = english_result(
                            snapshot["detail"], snapshot.get("outcome"),
                            snapshot.get("comparison_decimals", default_decimals),
                            snapshot.get("readings"), manual=True,
                        )
                self.reply(json.dumps(snapshot).encode("utf-8"), "application/json; charset=utf-8")
                return
            if path not in ("/", "/automatic"):
                self.send_error(404)
                return
            history = read_history()
            auto_rules = get_auto_rules()
            if path == "/automatic":
                payload = json.dumps(automatic_summary(history, language, auto_rules))
                self.reply(payload.encode("utf-8"), "application/json; charset=utf-8")
                return
            user = self.user_id()
            try:
                mode = (load_language_modes().get(user, "auto") if user else
                        query.get("mode", ["auto"])[0])
            except (OSError, ValueError):
                mode = "auto"
            if mode not in MODES:
                mode = "auto"
            profile = query.get("ui", [""])[0] if user and mode == "auto" else ""
            language = mode if mode in SUPPORTED else profile if profile in SUPPORTED else fallback
            source_name = {"de": "Deutsch", "en": "English"}.get(profile)
            automatic = "Automatic" if language == "en" else "Automatisch"
            automatic += f" (Home Assistant: {source_name})" if source_name else " (Home Assistant)"
            scripts = (f"<script>{profile_script(user)}</script>"
                       if user and mode == "auto" and not source_name else "")
            summary = automatic_summary(history, language, auto_rules)
            values = {name: html.escape(summary[name]) for name in ("ocr", "reference", "detail")}
            settings = history.get("manual_result", {}).get("settings", {})
            saved = query.get("saved", [""])[0]
            saved_message = (
                "Automatische Prüfregeln gespeichert." if saved == "1" else
                "Getesteten Bildausschnitt für die Automatik übernommen." if saved == "crop" else ""
            )
            if language == "en" and saved_message:
                saved_message = EN_UI[saved_message]
            auto_saved_notice = (
                '<p class="save-notice" role="status">' + html.escape(saved_message) + '</p>'
                if saved_message else ""
            )
            test = query.get("test", [""])[0]
            request_status = (
                "Test angenommen. Die Bearbeitung wird hier live angezeigt." if test == "queued" else
                "Ein manueller Test läuft bereits." if test == "busy" else "Status wird geladen …"
            )
            if language == "en":
                request_status = EN_UI.get(request_status, request_status)
            with request_lock:
                manual_open = progress["phase"] in ("queued", "running", "ocr")
            page = translate_page(PAGE) if language == "en" else PAGE
            self.reply(page.format(**values,
                language=language,
                language_mode=mode,
                profile_script=scripts,
                language_options=select_options({"auto": automatic, "de": "Deutsch", "en": "English"}, mode),
                settings_open="open" if saved else "",
                manual_open="open" if manual_open or test in ("queued", "busy", "open") else "",
                request_status=request_status,
                polarity_options=select_options(
                    POLARITIES_EN if language == "en" else POLARITIES,
                    settings.get("polarity", "auto"),
                ),
                decimal_options=select_options(
                    DECIMALS_EN if language == "en" else DECIMALS,
                    str(settings.get("decimals", auto_rules["decimals"])),
                ),
                auto_decimal_options=select_options(
                    DECIMALS_EN if language == "en" else DECIMALS, str(auto_rules["decimals"]),
                ),
                auto_attempt_options=select_options(ATTEMPTS, str(auto_rules["attempts"])),
                auto_polarity_options=select_options(
                    POLARITIES_EN if language == "en" else POLARITIES, auto_rules["polarity"],
                ),
                auto_crop_mode_options=select_options(
                    CROP_MODES_EN if language == "en" else CROP_MODES, auto_rules["crop_mode"],
                ),
                auto_crop_value=html.escape(auto_rules["crop"], quote=True),
                auto_width_value=auto_rules["width"],
                auto_saved_notice=auto_saved_notice,
                crop_mode_options=select_options(
                    CROP_MODES_EN if language == "en" else CROP_MODES,
                    settings.get("crop_mode", "auto"),
                ),
                crop_value=html.escape(str(settings.get("crop", default_crop)), quote=True),
                width_value=int(settings.get("width", default_width)),

                attempt_options=select_options(ATTEMPTS, str(settings.get("attempts", auto_rules["attempts"]))),
                default_attempts=default_attempts,
                csrf=csrf_token,
                image_time=summary["image_time"],
                next_check=json.dumps(summary["next_check"]),
                current=(
                    '<img src="aktuell.jpg?v={}" alt="'.format(summary["current"]) +
                    ("Latest check image" if language == "en" else "Aktuelles Kontrollbild") + '">'
                    if current_image.exists() else
                    ("No check image available yet." if language == "en" else "Noch kein Kontrollbild.")
                ),
                good=(
                    '<img src="treffer.jpg?v={}" alt="'.format(summary["good"]) +
                    ("Image from last match" if language == "en" else "Kontrollbild des letzten Treffers") + '">'
                    if good_image.exists() else
                    ("No confirmed image available yet." if language == "en" else "Noch kein bestätigtes Bild.")
                ),
            ).encode("utf-8"), "text/html; charset=utf-8")

        def do_POST(self):
            if not self.authorized():
                return
            path = urlsplit(self.path).path
            if path not in ("/pruefen", "/automatik", "/ausschnitt-uebernehmen", "/sprache"):
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
                form = parse_qs(self.rfile.read(length).decode("ascii"), max_num_fields=10)
            except ValueError:
                self.send_error(400)
                return
            supplied = form.get("csrf", [])
            if len(supplied) != 1 or not compare_digest(supplied[0].encode(), csrf_token.encode()):
                self.send_error(403)
                return
            user = self.user_id()
            mode = form.get("mode", ["auto"])
            language = form.get("lang", [browser_locale(self.headers.get("Accept-Language", ""))])
            if len(mode) != 1 or mode[0] not in MODES or len(language) != 1 or language[0] not in SUPPORTED:
                self.send_error(400)
                return
            language = language[0]
            mode = mode[0]
            keep_mode = "&mode=" + mode if not user and mode != "auto" else ""
            if path == "/sprache":
                if user:
                    try:
                        with preferences_lock:
                            preferences = load_language_modes()
                            if mode == "auto":
                                preferences.pop(user, None)
                            else:
                                preferences[user] = mode
                            save_language_modes(preferences)
                    except (OSError, ValueError):
                        self.send_error(503, ("Could not save the language setting." if mode == "en"
                                              else "Die Spracheinstellung konnte nicht gespeichert werden."))
                        return
                test_open = parse_qs(urlsplit(self.path).query).get("test") == ["open"]
                params = (["test=open"] if test_open else []) + (
                    ["mode=" + mode] if keep_mode else [])
                self.redirect("?" + "&".join(params) if params else "")
                return
            if path == "/ausschnitt-uebernehmen":
                try:
                    with request_lock, rules_lock:
                        previous = read_history().get("manual_result", {})
                        settings = previous.get("settings", {})
                        if (progress["phase"] != "done" or not progress["can_apply_crop"]
                                or form.get("checked_at") != [str(previous.get("checked_at"))]
                                or not previous.get("can_apply_crop") or not test_image.exists()
                                or settings.get("crop_mode") != "manual"):
                            self.send_error(409, ("Run the crop test again." if language == "en"
                                                  else "Bitte den Ausschnitt erneut testen."))
                            return
                        current = get_auto_rules()
                        current.update(crop_mode="manual", crop=settings["crop"], width=settings["width"])
                        save_auto_rules(current)
                except (OSError, ValueError, KeyError, TypeError):
                    self.send_error(503, ("Could not save the image crop." if language == "en"
                                          else "Ausschnitt konnte nicht gespeichert werden"))
                    return
                self.redirect("?saved=crop" + keep_mode)
                return
            if path == "/automatik":
                decimals = form.get("decimals", [])
                attempts = form.get("attempts", [])
                polarity = form.get("polarity", [])
                crop_mode = form.get("crop_mode", [])
                crop_text = form.get("crop", [get_auto_rules()["crop"]])
                width_text = form.get("width", [str(get_auto_rules()["width"])])
                if (len(decimals) != 1 or decimals[0] not in DECIMALS
                        or len(attempts) != 1 or attempts[0] not in ATTEMPTS
                        or len(polarity) != 1 or polarity[0] not in POLARITIES
                        or len(crop_mode) != 1 or crop_mode[0] not in CROP_MODES
                        or len(crop_text) != 1 or len(width_text) != 1):
                    self.send_error(400)
                    return
                if (crop_mode[0] == "manual" and
                        (not re.fullmatch(r"\d{1,4}\s*,\s*\d{1,4}\s*,\s*\d{1,4}\s*,\s*\d{1,4}", crop_text[0])
                         or not re.fullmatch(r"\d{1,4}", width_text[0]))):
                    self.send_error(400)
                    return
                try:
                    with rules_lock:
                        old_rules = get_auto_rules()
                        crop = crop_text[0] if crop_mode[0] == "manual" else old_rules["crop"]
                        width = int(width_text[0]) if crop_mode[0] == "manual" else old_rules["width"]
                        save_auto_rules({"decimals": int(decimals[0]), "attempts": int(attempts[0]),
                                         "polarity": polarity[0], "crop_mode": crop_mode[0],
                                         "crop": crop, "width": width})
                except ValueError:
                    self.send_error(400, ("Check the image region and whole-digit width." if language == "en"
                                          else "Bitte Bildbereich und Vorkommabreite prüfen."))
                    return
                except OSError:
                    self.send_error(503)
                    return
                self.redirect("?saved=1" + keep_mode)
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
                        and re.fullmatch(r"[0-9]{1,4}", whole_width[0])
                        and 1 <= int(whole_width[0]) <= boundaries[2] - boundaries[0]):
                    self.send_error(400)
                    return
                crop_value = ",".join(map(str, boundaries))
                width_value = int(whole_width[0])
            settings = {"polarity": polarity[0], "decimals": int(decimals[0]),
                        "attempts": int(attempts[0]), "crop_mode": crop_mode[0],
                        "crop": crop_value, "width": width_value}
            with request_lock:
                if progress["phase"] in ("queued", "running", "ocr"):
                    self.redirect("?test=busy" + keep_mode)
                    return
                request_id = progress["request_id"] + 1
                settings["request_id"] = request_id
                try:
                    requested.put_nowait(settings)
                except Full:
                    self.redirect("?test=busy" + keep_mode)
                    return
                progress.update(request_id=request_id, max_attempts=settings["attempts"], outcome=None,
                                detail="", preview=False, can_apply_crop=False, readings=[],
                                comparison_decimals=settings["decimals"], phase="queued",
                                message="Anfrage angenommen – warte auf die Bildprüfung.",
                                attempts=0, started_at=time.time(), checked_at=0,
                                ocr=None, reference=None)
            self.redirect("?test=queued" + keep_mode)

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(address, Handler)
    Thread(target=server.serve_forever, daemon=True).start()
    return server, update_progress
