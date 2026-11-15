"""Home Assistant ingress panel for optical gas meter checks."""

import html
from email.parser import BytesParser
from email.policy import default as email_policy
import json
import os
import re
from datetime import datetime
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from queue import Full
from secrets import compare_digest, token_urlsafe
from threading import Lock, Thread
from tempfile import NamedTemporaryFile
from urllib.parse import parse_qs, urlsplit

from app_channel import APP_NAME, NAMESPACE
from checks import (DEFAULT_INTERVAL_MINUTES, MAX_INTERVAL_MINUTES, WARNING_DETAIL_AFTER, meter_prefix,
                    last_check_at, reschedule_next_check, valid_interval_minutes)
from consumption import DEFAULT_FLOW_LPH, format_cubic_metres, parse_flow_limit
from i18n import EN_UI, english_progress, english_result, translate_page
from language import MODES, SUPPORTED, USER_ID, browser_locale, profile_script
from layout import ROTATIONS, crop_coordinates
from notification_settings import notification_rules
from source_settings import SOURCE_MODES, source_rules

SUPERVISOR_ADDRESS = "172.30.32.2"
MAX_MANUAL_IMAGE_BYTES = 3_000_000
MAX_MULTIPART_OVERHEAD = 16_384

PAGE = """<!doctype html>
<html lang="{language}"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>{app_name}</title>
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
.main-tabs{{display:flex;gap:.45rem;padding:.35rem;margin:0 0 1rem;border:1px solid var(--edge);border-radius:.85rem;background:var(--surface)}}
.main-tabs button{{flex:1;min-height:2.8rem;background:transparent;border-color:transparent;color:var(--muted)}}
.main-tabs button[aria-selected="true"]{{background:light-dark(#e7f0f5,#293b48);border-color:var(--edge);color:inherit}}
.setup-dialog{{width:min(46rem,calc(100vw - 1.2rem));max-height:min(90dvh,52rem);overflow:auto;padding:1rem 1.2rem;border:1px solid var(--edge);border-radius:1rem;background:var(--surface);color:inherit;box-shadow:0 1rem 3rem #0004}}
.setup-dialog::backdrop{{background:#07121dcc;backdrop-filter:blur(2px)}}
.setup-dialog .manual-content{{margin-top:.5rem}}
.dialog-heading{{display:flex;align-items:center;justify-content:space-between;gap:.75rem;margin-bottom:.5rem}}
.dialog-heading h2{{margin:0}}
.tab-content[hidden]{{display:none}}
.automatic-images{{margin:1rem 0}}
.check-option{{display:flex;align-items:center;gap:.5rem;grid-column:1/-1}}
.check-option input{{min-height:1.15rem;width:1.15rem;margin:0}}
.notification-form input{{width:100%}}
.notification-form .check-option input{{width:1.15rem}}
.automatic-banner{{display:flex;align-items:flex-start;gap:.6rem;margin:0 0 1rem;padding:.8rem .9rem;border:1px solid var(--edge);border-radius:.75rem}}
.automatic-banner[data-tone="ok"]{{border-color:#65a986;background:light-dark(#edf8f0,#183a2a);color:light-dark(#155d39,#a2e5bc)}}
.automatic-banner[data-tone="warning"], .test-box[data-result="warning"]{{border-color:#b58b38;background:light-dark(#fff8df,#3b311d);color:light-dark(#704c08,#ffdf8a)}}
.automatic-banner[data-tone="problem"]{{border-color:#c67a7a;background:light-dark(#fff2f1,#46282c);color:light-dark(#8d282e,#ffc0c1)}}
.automatic-banner-icon{{font-weight:750;font-size:1.15rem;line-height:1.2}}
.automatic-banner p{{margin:.2rem 0 0;overflow-wrap:anywhere}}
.automatic-banner p:empty{{display:none}}
.automatic-banner button{{margin-left:auto;padding:.35rem .7rem;min-height:2.75rem}}
@media(max-width:500px){{.automatic-banner{{flex-wrap:wrap}}.automatic-banner-text{{flex:1;min-width:0}}}}
.notification-help li + li{{margin-top:.35rem}}
.automatic-images > summary{{cursor:pointer;color:var(--muted)}}
.dashboard-help{{margin:.8rem 0;color:var(--muted)}}
.dashboard-help summary{{cursor:pointer}}
.dashboard-help pre{{overflow:auto;padding:.75rem;border-radius:.6rem;background:light-dark(#edf1f4,#202b34);color:inherit;font-size:.85rem}}
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
.setup-step{{display:none;border:0;border-top:1px solid var(--edge);padding:1rem 0 0;margin:0;min-width:0}}
.setup-step.active{{display:grid;gap:.8rem;grid-template-columns:repeat(auto-fit,minmax(min(100%,13rem),1fr))}}
.setup-step legend{{font-weight:700;padding:0 .4rem 0 0;color:inherit}}
.setup-controls{{display:flex;align-items:center;justify-content:space-between;gap:.6rem;grid-column:1/-1}}
.setup-help{{grid-column:1/-1}}
.setup-help summary{{cursor:help;color:var(--muted);font-size:.88rem}}
.setup-help p{{margin:.4rem 0 0;color:var(--muted);font-size:.88rem}}
.setup-warning{{padding:.7rem .8rem;border-radius:.6rem;background:light-dark(#fff7e6,#3b321c);color:light-dark(#72540e,#e7d28a);grid-column:1/-1}}
.settings-item{{border-top:1px solid var(--edge)}}
.settings-item summary{{min-height:2.75rem;padding:.45rem 0}}
.settings-item .manual-content{{margin:0;padding:0 0 1rem;border-top:0}}
.check-card-heading{{display:flex;align-items:center;justify-content:space-between;gap:.65rem;flex-wrap:wrap;margin-bottom:.8rem}}
.check-card-heading h2{{margin:0}}
.check-actions{{display:flex;align-items:center;gap:.5rem;flex-wrap:wrap}}
.manual-test-heading{{display:flex;align-items:center;justify-content:space-between;gap:.65rem;flex-wrap:wrap}}
.manual-test-heading h2{{margin:0}}
.manual-reference-entry{{display:flex;align-items:end;gap:.75rem;flex-wrap:wrap;margin-top:1rem;padding-top:1rem;border-top:1px solid var(--edge)}}
.manual-reference-entry label{{flex:1 1 15rem}}
.manual-reference-entry p{{flex:2 1 18rem;margin:0 0 .55rem;color:var(--muted);font-size:.85rem}}
#manual-panel{{margin-top:.8rem}}
.settings-note{{font-size:.85rem;color:var(--muted);margin:.7rem 0 0}}
.save-notice{{font-size:.88rem;color:light-dark(#1e7650,#8ad4a9);margin:.7rem 0 0}}
.crop-fields{{display:flex;gap:.8rem;flex-wrap:wrap;margin-top:.7rem}}
.crop-fields label{{flex:1 1 10rem}}.crop-fields label:first-child{{flex-grow:2;flex-basis:16rem}}
.crop-fields .settings-note{{flex-basis:100%;margin:0}}
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
.about-project{{margin-top:.5rem}}
.about-project summary{{cursor:pointer;min-height:2.5rem;padding:.45rem}}
.about-project p{{max-width:34rem;margin:.35rem auto}}
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
.reference-note{{display:block;color:var(--muted);font-weight:400}}
section{{display:grid;gap:1rem;grid-template-columns:repeat(auto-fit,minmax(min(100%,18rem),1fr));margin-top:1rem}}
section>div{{background:var(--surface);border:1px solid var(--edge);border-radius:1rem;padding:1rem;overflow:hidden}}
section img{{width:100%;height:auto;display:block;border-radius:.55rem}}
.stamp,#countdown{{font-variant-numeric:tabular-nums}}
@media(max-width:500px){{body{{padding:.8rem .7rem 2rem}}.panel{{padding:.9rem}}dl{{grid-template-columns:minmax(5.5rem,1fr) minmax(0,1.7fr);gap:.5rem .85rem}}form:not(.language-bar) button{{width:100%;min-height:2.75rem}}}}
</style>
<header>
<h1>{app_name}</h1>
<button type="button" id="open-setup">Einrichtung öffnen</button>
<form method="post" action="sprache" class="language-bar" id="language-form">
<input type="hidden" name="csrf" value="{csrf}">
<label for="language-select">Sprache / Language</label>
<select id="language-select" name="mode">{language_options}</select>
<noscript><button type="submit">Speichern</button></noscript>
</form>
</header>
<nav class="main-tabs" role="tablist" aria-label="Hauptmenü">
<button type="button" role="tab" id="tab-overview" aria-controls="view-overview" aria-selected="true">Übersicht</button>
<button type="button" role="tab" id="tab-settings" aria-controls="view-settings" aria-selected="false" tabindex="-1">Einstellungen</button>
</nav>
<main>
<div class="tab-content" id="view-overview" role="tabpanel" aria-labelledby="tab-overview" {overview_hidden}>
<div class="panel" id="check-overview">
<div class="check-card-heading"><h2>Automatische Kontrolle</h2>
<div class="check-actions">
<button type="button" id="open-manual-settings">Test einstellen</button>
<button id="start-check" type="submit" form="manual-form">Test starten</button>
</div></div>
<div class="automatic-banner" id="automatic-banner" data-tone="{automatic_tone}"
 data-incident="{automatic_incident}" data-preference-key="{banner_preference_key}">
<span class="automatic-banner-icon" aria-hidden="true">{automatic_icon}</span>
<div class="automatic-banner-text" role="status" aria-live="polite">
<strong id="automatic-status-heading">{automatic_heading}</strong>
<p id="automatic-result">{detail}</p>
</div>
<button id="ignore-automatic-warning" type="button" {ignore_hidden}
 title="Blendet diesen Hinweis hier aus. Prüfungen und Benachrichtigungen laufen weiter.">Ignorieren</button>
</div>
<dl><dt>Erkannter Stand</dt><dd id="automatic-ocr">{ocr}</dd>
<dt>Referenz</dt><dd><span id="automatic-reference">{reference}</span>
<small id="automatic-reference-note" class="reference-note" data-epoch="{reference_time}"
 data-fallback="{reference_is_fallback}" hidden></small></dd>
<dt>Bildzeit</dt><dd id="automatic-image-time" class="stamp" data-epoch="{image_time}">–</dd>
<dt>Letzte automatische Prüfung</dt><dd id="automatic-last-check" class="stamp" data-epoch="{last_check}">–</dd>
<dt>Letzter bestätigter Abgleich</dt><dd id="automatic-last-match" class="stamp" data-epoch="{last_match}">–</dd>
<dt>Nächste Prüfung</dt><dd id="countdown">–</dd></dl>
<details class="ocr-details" id="automatic-ocr-details" hidden>
<summary>Mehr Infos: Was wurde bei den OCR-Versuchen gelesen?</summary>
<p class="ocr-scope"></p>
<p>? steht für eine unklare Ziffer.</p>
<table><thead><tr><th>Versuch</th><th>Erkannter Stand</th></tr></thead><tbody></tbody></table>
</details>
<details class="dashboard-help">
<summary>Stand im Home-Assistant-Dashboard anzeigen</summary>
<p>Wenn Meter OCR selbst aus einer ESPHome- oder Home-Assistant-Kamera liest, kannst du den Sensor „OCR-Zählerstand“ zum Dashboard hinzufügen. Seine Entitäts-ID lautet <code>sensor.rf1_ocr_zaehlerstand</code>.</p>
<p>Oder füge diese kurze YAML-Konfiguration in eine manuelle Karte ein:</p>
<pre><code>type: entity
entity: sensor.rf1_ocr_zaehlerstand
name: Zählerstand (OCR)</code></pre>
</details>
<details class="automatic-images" id="automatic-images"><summary>Erkennungsbild</summary>
<div class="preview" id="test-preview" data-auto-src="{automatic_preview_src}" data-auto-version="{automatic_preview_version}" data-auto-available="{automatic_preview_available}" {automatic_preview_hidden}>
<h2 id="preview-heading">Letzte automatische Erkennung</h2>
<img id="test-preview-image" src="{automatic_preview_src}" alt="Zählerbild mit grün markierten erkannten Ziffern und rot markierten unklaren Stellen">
<p class="legend"><span class="green-key">Grün:</span> Ziffer wurde gelesen · <span class="red-key">Rot:</span> Ziffer unklar. Die Farbrahmen zeigen die OCR-Erkennung, nicht die Übereinstimmung mit dem Referenzstand. Ohne automatisch erkannte Ziffernrahmen sind die Bereiche nur näherungsweise aufgeteilt.</p>
</div>
</details>
<div class="manual-test-area" id="manual-test-area" {manual_area_hidden}>
<div class="manual-test-heading"><h2>Manueller Test</h2>
<button type="button" id="close-manual-test">Schließen</button></div>
<div class="test-box" id="test-box" data-phase="idle" data-result="neutral" tabindex="-1" {test_hidden} role="status" aria-live="polite">
<strong id="test-head">Aktueller Schritt: Bereit</strong>
<p id="test-status">{request_status}</p>
<progress id="test-progress" max="{default_attempts}" value="0" aria-label="OCR-Versuche" hidden></progress>
<small id="test-meta">Bereit für den manuellen Test.</small>
<div class="test-result" id="test-result" hidden>
<p id="test-result-detail"></p>
<dl id="manual-readings" hidden><dt>Erkannter Stand</dt><dd id="manual-ocr"></dd>
<dt>Referenz</dt><dd><span id="manual-reference"></span><small id="manual-reference-note" class="reference-note" hidden></small></dd>
<dt>Bildzeit</dt><dd id="manual-image-time">–</dd></dl>
<small id="test-result-stamp"></small>
<details class="ocr-details" id="ocr-details" hidden>
<summary>Mehr Infos: Was wurde bei den OCR-Versuchen gelesen?</summary>
<p class="ocr-scope"></p>
<p>? steht für eine unklare Ziffer.</p>
<table><thead><tr><th>Versuch</th><th>Erkannter Stand</th></tr></thead>
<tbody></tbody></table>
</details>
</div>
{test_source_preview}
<div class="manual-reference-entry">
<label for="manual-reference-entry">Fallback-Wert für diesen Test (optional)
<input id="manual-reference-entry" name="manual_reference" form="manual-form" value="{manual_reference}" inputmode="decimal" maxlength="16" placeholder="z. B. 10446,337"></label>
<p>Am markierten Bild ablesen und hier eintragen. Der Wert wird nur mit dem manuellen Test verglichen und nicht als automatische Referenz gespeichert.</p>
</div>
<form method="post" action="ausschnitt-uebernehmen" id="apply-crop-form" class="apply-crop" hidden>
<input type="hidden" name="checked_at" id="tested-crop-id">
<input type="hidden" name="lang" value="{language}">
<input type="hidden" name="mode" value="{language_mode}">
<input type="hidden" name="csrf" value="{csrf}">
<button type="submit">Getesteten Ausschnitt für die Automatik übernehmen</button>
</form>
</div>
<details class="manual-panel settings-item" id="manual-panel" {manual_open}>
<summary><strong>Testeinstellungen</strong></summary>
<div class="manual-content">
<form method="post" action="pruefen" id="manual-form" enctype="multipart/form-data">
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
<label>Bilddrehung im Uhrzeigersinn
<select name="rotation">{rotation_options}</select></label>
<label>Breite der Vorkommastellen
<input name="width" type="number" min="1" max="9999" value="{width_value}"></label>
<p class="settings-note">Wähle den Ausschnitt im Originalbild. Die Vorkommabreite gilt nach der Drehung.</p>
</div>
<label>Eigenes Testbild (optional, JPG oder PNG)
<input type="file" name="image" accept="image/jpeg,image/png"></label>
<p class="settings-note">Ein ausgewähltes Bild wird nur für diesen manuellen Test verwendet (max. 3 MB).</p>
<button id="start-check-with-options" type="submit">Jetzt prüfen</button>
</form>
<details class="help"><summary title="Informationen zum manuellen Bildtest">ⓘ Was passiert bei „Jetzt prüfen“?</summary>
<p>Die App verwendet das letzte vorhandene Zählerbild oder ein ausgewähltes eigenes JPG-/PNG-Testbild (bis 3 MB). Sie liest die Zahlen aus dem Bild und vergleicht sie mit dem Referenzwert. Sobald die Werte übereinstimmen, stoppt die Prüfung. Andernfalls werden höchstens so viele OCR-Versuche durchgeführt wie eingestellt (1–10). Der Test verändert die automatische Trefferzahl nicht.</p></details>
</div></details>
</div>
</div>
</div>
<div class="tab-content" id="view-settings" role="tabpanel" aria-labelledby="tab-settings" {settings_hidden}>
<div class="panel" id="settings"><h2>Einstellungen</h2>
<dialog class="setup-dialog" id="setup-dialog" aria-labelledby="setup-title" data-first-run="{setup_first_run}">
<div class="dialog-heading"><h2 id="setup-title">Einrichtungsassistent</h2>
<form method="post" action="einrichtung-ueberspringen" id="setup-skip-form">
<input type="hidden" name="lang" value="{language}"><input type="hidden" name="mode" value="{language_mode}">
<input type="hidden" name="csrf" value="{csrf}">
<button type="submit" id="setup-skip">Später einrichten</button></form></div>
<p class="settings-note">Du kannst die Einrichtung jederzeit über „Einrichtung öffnen“ erneut starten.</p>
<div class="manual-content">
<p class="settings-note">Einmal Schritt für Schritt einrichten oder später einzelne Angaben ändern. Deine aktuellen Einstellungen sind vorausgefüllt.</p>
<form method="post" action="einrichtung" id="setup-form">
<input type="hidden" name="lang" value="{language}"><input type="hidden" name="mode" value="{language_mode}">
<input type="hidden" name="csrf" value="{csrf}">
<fieldset class="setup-step active" data-step="0"><legend>1. Bildquelle</legend>
<label>Woher kommt das Zählerbild?<select name="source_mode" id="wizard-source-mode">{wizard_source_options}</select></label>
<label id="wizard-source-url">SLFork-Adresse<input name="url" value="{source_url}" maxlength="150" placeholder="http://esp-gaszaehler.local"></label>
<label id="wizard-source-camera">Home-Assistant-Kamera<input name="camera" value="{source_camera}" maxlength="80" placeholder="camera.gaszaehler"></label>
<label id="wizard-source-reference">Vergleichssensor (optional)<input name="reference" value="{source_reference}" maxlength="80" placeholder="sensor.gaszaehler"></label>
<details class="setup-help"><summary>ⓘ Welcher Weg passt?</summary><p>SLFork liefert Bild und Messwert. Die Livebild-Quelle ruft bei jeder Prüfung ein aktuelles Standbild deiner Home-Assistant-Kamera ab; ein Video wird nicht dauerhaft ausgewertet. Du kannst dazu einen Zählerstandssensor – etwa von AI on the Edge – als Vergleich eintragen. Ohne Referenzsensor liest Meter OCR selbst und prüft die Werte auf Plausibilität.</p></details>
<details class="setup-help"><summary>ⓘ Hinweis zum Teststand</summary><p>Für reale Tests nutze ich ausschließlich AI on the Edge. Die übrigen Kamera- und Zählermodi sind bisher nur mit simulierten Bildern und automatisierten Tests geprüft.</p></details>
<div class="setup-controls"><span class="setup-count"></span><button type="button" class="setup-next">Weiter</button></div>
</fieldset>
<fieldset class="setup-step" data-step="1"><legend>2. Zähleranzeige</legend>
<label>Anzeigeart<select name="meter_display">{meter_display_options}</select></label>
<label>Ziffern vor dem Komma<select name="integer_digits">{integer_digit_options}</select></label>
<label>Nachkommastellen auf dem Zähler<select name="fraction_digits">{fraction_digit_options}</select></label>
<label>Verglichen wird bis<select name="decimals">{wizard_decimal_options}</select></label>
<p class="settings-note setup-help">Die Vergleichsgenauigkeit darf kleiner sein als die angezeigte Stellenzahl. Kleine Zeiger werden nicht automatisch gelesen; bei Rollen und Zeigern bitte nur die Ziffernrollen einstellen.</p>
<label>Fallback-Zählerstand (optional)<input name="fallback_value" value="{fallback_value}" inputmode="decimal" maxlength="16" placeholder="z. B. 10446,337"></label>
<label>Stand abgelesen am<input name="fallback_time" type="datetime-local" value="{fallback_time}"></label>
<details class="setup-help"><summary>ⓘ Wie wird der Fallback verwendet?</summary><p>Er ist ein Startwert, solange noch keine sichere automatische Ablesung gespeichert ist. Meter OCR prüft die erste Ablesung gegen den Zeitabstand und den maximalen Durchfluss. Danach wird der letzte bestätigte Stand als Referenz genutzt. Ohne Fallback beginnt die Plausibilitätsprüfung mit der ersten sicheren Ablesung.</p></details>
<div class="setup-controls"><button type="button" class="setup-back">Zurück</button><span class="setup-count"></span><button type="button" class="setup-next">Weiter</button></div>
</fieldset>
<fieldset class="setup-step" data-step="2"><legend>3. Bildausschnitt und Prüfplan</legend>
<label>Bildbereich<select name="crop_mode">{wizard_crop_options}</select></label>
<label>OCR-Versuche pro Bild<select name="attempts">{auto_attempt_options}</select></label>
<label>Ziffernfarbe<select name="polarity">{auto_polarity_options}</select></label>
<label>Prüfintervall (Minuten)<input type="number" name="interval_minutes" min="5" max="1440" value="{interval_minutes}" required></label>
<label>Maximaler Durchfluss (m³/h)<input name="max_flow" type="text" inputmode="decimal" maxlength="10" value="{max_flow}" required></label>
<div class="crop-fields setup-help" id="wizard-crop-fields">
<label>Bildbereich (links, oben, rechts, unten)<input name="crop" value="{auto_crop_value}" maxlength="30" placeholder="52,56,564,132"></label>
<label>Bilddrehung im Uhrzeigersinn<select name="rotation">{auto_rotation_options}</select></label>
<label>Breite des Vorkomma-Bereichs in Pixeln<input name="width" type="number" min="1" max="9999" value="{auto_width_value}"></label>
</div>
<details class="setup-help"><summary>ⓘ Bild einrichten</summary><p>Die automatische Erkennung versucht, den Ziffernrahmen zu finden. Wenn sie das nicht schafft, öffne den manuellen Test: Dort wird das aktuelle Bild mit den erkannten Ziffern angezeigt. Einen getesteten Ausschnitt kannst du danach ausdrücklich für die Automatik übernehmen. Beim Livebild kann Meter OCR bis zu 10 frische Standbilder innerhalb von höchstens 20 Sekunden prüfen.</p></details>
<div class="setup-controls"><button type="button" class="setup-back">Zurück</button><span class="setup-count"></span><button type="button" class="setup-next">Weiter</button></div>
</fieldset>
<fieldset class="setup-step" data-step="3"><legend>4. Hinweise und speichern</legend>
<label class="check-option"><input type="checkbox" name="notifications_enabled" value="1" {notifications_enabled}> Bei anhaltenden Problemen benachrichtigen</label>
<label>Hinweis nach (Minuten)<input type="number" name="review_minutes" min="1" max="2880" value="{notification_review}" required></label>
<label>Push oder E-Mail nach weiteren Stunden<input type="number" name="delivery_hours" min="0" max="168" value="{notification_delay}" required></label>
<label>Handy-Push (optional)<input name="push" value="{notification_push}" maxlength="80" placeholder="notify.mobile_app_mein_handy"></label>
<label>E-Mail oder anderes Ziel (optional)<input name="target" value="{notification_target}" maxlength="80" placeholder="notify.meine_email"></label>
<details class="setup-help"><summary>ⓘ Keine Benachrichtigung nötig?</summary><p>Entferne das Häkchen. Das Statusfeld in der Übersicht bleibt sichtbar; ein manueller Test löst keinen Push oder keine E-Mail aus.</p></details>
<details class="setup-help setup-dashboard-help"><summary>ⓘ Stand und Verbrauch im Dashboard anzeigen</summary>
<p>Für den erkannten Zählerstand im ESPHome- oder Kameramodus: <code>sensor.rf1_ocr_zaehlerstand</code>.</p>
<p>Für den Home-Assistant-Energieverbrauch: <code>sensor.rf1_verbrauch_gesamt</code>. Diese Entität erscheint nach dem ersten gültigen Messwert und kann im Energie-Dashboard als Gasverbrauch ausgewählt werden.</p>
<p>So fügst du den Zählerstand einer einfachen Dashboard-Karte hinzu:</p>
<pre><code>type: entity
entity: sensor.rf1_ocr_zaehlerstand
name: Zählerstand (OCR)</code></pre>
</details>
<div class="setup-controls"><button type="button" class="setup-back">Zurück</button><span class="setup-count"></span><button type="submit">Speichern und Test öffnen</button></div>
</fieldset>
<div id="setup-error" class="setup-warning" hidden></div>
</form>

</div>
</dialog>
{wizard_saved_notice}
<details class="manual-panel settings-item" id="source-settings" {source_open}>
<summary><strong>Bildquelle</strong></summary>
<div class="manual-content">
{source_intro}
<form method="post" action="bildquelle" id="source-form">
<input type="hidden" name="lang" value="{language}">
<input type="hidden" name="mode" value="{language_mode}">
<input type="hidden" name="csrf" value="{csrf}">
<label title="Wähle, woher das Zählerbild und gegebenenfalls der Vergleichswert kommen.">Betriebsmodus
<select name="source_mode" id="source-mode">{source_options}</select></label>
<label id="source-url" title="Die Adresse deines SLFork-Geräts im Heimnetz.">SLFork-Adresse
<input name="url" value="{source_url}" placeholder="http://esp-gaszaehler.local" maxlength="150"></label>
<label id="source-camera" title="Die Entitäts-ID der Kamera in Home Assistant.">Kamera in Home Assistant
<input name="camera" value="{source_camera}" placeholder="camera.gaszaehler" maxlength="80"></label>
<label id="source-reference" title="Optionaler Sensor mit aktuellem Zählerstand in Kubikmetern.">Vergleichssensor (optional)
<input name="reference" value="{source_reference}" placeholder="sensor.gaszaehler" maxlength="80"></label>
<button type="submit">Speichern</button>
</form>
<details class="help"><summary title="Erklärung zu den verfügbaren Modi">ⓘ Welcher Modus passt?</summary>
<ul>
<li><strong>SLFork:</strong> Das Gerät liefert Foto und Vergleichswert.</li>
<li><strong>Home-Assistant-Kamera:</strong> Die App liest das Bild und vergleicht es mit einem Sensor, falls einer eingetragen ist.</li>
<li><strong>ESPHome oder Kamera mit lokaler OCR:</strong> Die Kamera liefert das Foto, die App liest den Stand und stellt ihn als eigenen Sensor bereit.</li>
</ul></details>
{source_saved_notice}
</div></details>
<details class="manual-panel settings-item" id="automatic-settings" {settings_open}>
<summary><strong>Automatische Prüfung</strong></summary>
<div class="manual-content">
<form method="post" action="automatik" id="auto-form">
<input type="hidden" name="lang" value="{language}">
<input type="hidden" name="mode" value="{language_mode}">
<input type="hidden" name="csrf" value="{csrf}">
<label>Vergleich
<select name="decimals">{auto_decimal_options}</select></label>
<label title="Zeit nach einer erfolgreichen Prüfung. Bei einem Fehler erfolgt der nächste Versuch spätestens nach fünf Minuten.">Prüfintervall (Minuten)
<input name="interval_minutes" type="number" min="1" max="{max_interval_minutes}" value="{interval_minutes}" required></label>
<label>Max. OCR-Versuche
<select name="attempts">{auto_attempt_options}</select></label>
<label title="Qmax steht auf deinem Zähler. Die Vorgabe für einen G4 beträgt 6 m³/h.">Maximaler Durchfluss (m³/h)
<input name="max_flow" type="text" inputmode="decimal" maxlength="10" value="{max_flow}" required></label>
<label>Ziffernfarbe
<select name="polarity">{auto_polarity_options}</select></label>
<label>Bildbereich
<select name="crop_mode" id="auto-crop-mode">{auto_crop_mode_options}</select></label>
<div class="crop-fields" id="auto-crop-fields" hidden>
<label>Bildbereich (links, oben, rechts, unten)
<input name="crop" type="text" value="{auto_crop_value}" maxlength="30" placeholder="52,56,564,132"></label>
<label>Bilddrehung im Uhrzeigersinn
<select name="rotation">{auto_rotation_options}</select></label>
<label>Breite der Vorkommastellen
<input name="width" type="number" min="1" max="9999" value="{auto_width_value}"></label>
<p class="settings-note">Wähle den Ausschnitt im Originalbild. Die Vorkommabreite gilt nach der Drehung.</p>
</div>
<button type="submit">Speichern</button>
</form>
<p class="settings-note">Das Prüfintervall gilt auch für die bereits geplante nächste Prüfung. Bei geänderter Vergleichsgenauigkeit beginnt die Trefferzählung neu.</p>
</div></details>
{auto_saved_notice}
<details class="manual-panel settings-item" id="notification-settings" {notifications_open}>
<summary><strong>Benachrichtigungen</strong></summary>
<div class="manual-content">
<form class="notification-form" method="post" action="benachrichtigungen">
<input type="hidden" name="lang" value="{language}">
<input type="hidden" name="mode" value="{language_mode}">
<input type="hidden" name="csrf" value="{csrf}">
<label class="check-option" title="Gilt für die automatische Kontrolle. Ein manueller Test löst keinen Versand aus.">
<input type="checkbox" name="enabled" value="1" {notifications_enabled}>
Bei anhaltenden Problemen benachrichtigen
</label>
<label title="So lange muss die automatische Kontrolle ohne Erfolg bleiben, bevor Home Assistant einen Hinweis anzeigt.">Hinweis nach (Minuten)
<input type="number" name="review_minutes" min="1" max="2880" value="{notification_review}" required></label>
<label title="Wartezeit für Handy-Push und E-Mail, nachdem der Hinweis erschienen ist. Bei 0 werden beide sofort gesendet.">Push und E-Mail nach weiteren Stunden
<input type="number" name="delivery_hours" min="0" max="168" value="{notification_delay}" required></label>
<label title="Optionaler Dienst deiner Home Assistant Companion App, zum Beispiel notify.mobile_app_mein_handy.">Handy-Push (optional)
<input name="push" value="{notification_push}" maxlength="80" placeholder="notify.mobile_app_mein_handy" autocapitalize="off" spellcheck="false"></label>
<label title="Optionales Benachrichtigungsziel in Home Assistant, zum Beispiel eine SMTP-Empfänger-Entität.">E-Mail oder anderes Ziel (optional)
<input name="target" value="{notification_target}" maxlength="80" placeholder="notify.meine_email" autocapitalize="off" spellcheck="false"></label>
<button type="submit">Speichern</button>
</form>
<details class="help notification-help"><summary title="Beispiele und Erklärung zu den Benachrichtigungen">ⓘ Wie funktioniert der Versand?</summary>
<ul>
<li>Nur einen Hinweis in Home Assistant erhalten? Lass beide optionalen Felder leer.</li>
<li>Für E-Mail richte zuerst die SMTP-Integration in Home Assistant ein und trage hier die Entitäts-ID des Empfängers ein. Andere Benachrichtigungs-Entitäten funktionieren ebenfalls.</li>
<li>Wenn die Prüfung wieder gelingt oder du den Hinweis schließt, entfallen noch ausstehende Nachrichten. Je Ziel wird pro Störung eine Nachricht gesendet.</li>
</ul></details>
{notification_saved_notice}
</div></details>
<details class="settings-item reset-section">
<summary><strong>App-Daten zurücksetzen</strong></summary>
<div class="manual-content">
<p class="settings-note">Setzt die Meter-OCR-Einstellungen und Prüfhistorie auf Standardwerte zurück und entfernt gespeicherte Testbilder. Die Home-Assistant-App-Konfiguration und vorhandenen Entitäten bleiben erhalten.</p>
<button type="button" id="open-reset">Auf Werkseinstellungen zurücksetzen</button>
</div></details>
{reset_notice}
</div>
<dialog class="setup-dialog" id="reset-dialog" aria-labelledby="reset-title">
<h2 id="reset-title">Werkseinstellungen wiederherstellen?</h2>
<p>Gespeicherte Bildquelle, OCR- und Benachrichtigungseinstellungen, Prüfhistorie und Testbilder werden zurückgesetzt. Home-Assistant-App-Konfiguration und Entitätsnamen bleiben erhalten.</p>
<form method="post" action="werkreset" id="reset-form">
<input type="hidden" name="lang" value="{language}"><input type="hidden" name="mode" value="{language_mode}">
<input type="hidden" name="csrf" value="{csrf}">
<button type="button" id="cancel-reset">Abbrechen</button>
<button type="submit">Jetzt zurücksetzen</button>
</form>
</dialog>
</div>
</main>

<footer class="page-footer">Kostenloses Hobbyprojekt
<details class="about-project"><summary>Über Meter OCR</summary><p><a href="https://github.com/Eifellayer" target="_blank" rel="noopener noreferrer">Projekt von EifelLayer auf GitHub</a></p><p>KI-unterstützt entwickelt. Keine geeichte Messung oder Gewähr für OCR-Ergebnisse. Bitte Zählerstände bei Bedarf direkt am Gerät prüfen.</p><p><a href="https://www.paypal.com/donate/?hosted_button_id=FG4Q7VKQJ9BW8" target="_blank" rel="noopener noreferrer">Freiwillig mit PayPal unterstützen</a></p></details></footer>
<script>
let next = {next_check};
const lang = '{language}';
const searchPrefs = new URLSearchParams(location.search);
const tabs = [...document.querySelectorAll('[role="tab"]')];
const views = [...document.querySelectorAll('.tab-content')];
function activateTab(name, updateUrl = true) {{
  const selected = name === 'settings' ? 'settings' : 'overview';
  tabs.forEach(tab => {{
    const active = tab.id === `tab-${{selected}}`;
    tab.setAttribute('aria-selected', String(active));
    tab.tabIndex = active ? 0 : -1;
  }});
  views.forEach(view => view.hidden = view.id !== `view-${{selected}}`);
  if (updateUrl) {{
    const url = new URL(location.href);
    if (selected === 'settings') url.searchParams.set('ui', 'settings');
    else url.searchParams.delete('ui');
    history.replaceState(null, '', url.pathname + (url.searchParams.size ? '?' + url.searchParams : ''));
  }}
}}
tabs.forEach((tab, index) => {{
  tab.addEventListener('click', () => activateTab(tab.id === 'tab-settings' ? 'settings' : 'overview'));
  tab.addEventListener('keydown', event => {{
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    const next = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length;
    tabs[next].focus();
    tabs[next].click();
  }});
}});
const settingsSections = ['#source-settings', '#automatic-settings', '#notification-settings'];
const settingsOpen = searchPrefs.get('ui') === 'settings' || ['setup', 'crop'].includes(searchPrefs.get('saved')) || settingsSections.some(selector => document.querySelector(selector).open);
activateTab(settingsOpen ? 'settings' : 'overview', false);
const setupDialog = document.querySelector('#setup-dialog');
// Keep the first-run modal outside the tab panel so its hidden ancestor cannot hide it.
document.body.appendChild(setupDialog);
const setupDismissKey = 'meter-ocr-setup-dismissed';
function dismissSetup() {{
  if (setupDialog.open) setupDialog.close();
  localStorage.setItem(setupDismissKey, '1');
}}
setupDialog.addEventListener('close', () => localStorage.setItem(setupDismissKey, '1'));
document.querySelector('#setup-skip-form').addEventListener('submit', () => localStorage.setItem(setupDismissKey, '1'));
document.querySelector('#open-setup').addEventListener('click', () => {{
  activateTab('settings');
  showSetupStep(0);
  if (!setupDialog.open) setupDialog.showModal();
}});
if (searchPrefs.get('reset') === 'done') localStorage.removeItem(setupDismissKey);
if (searchPrefs.get('reset') === 'pending') {{
  searchPrefs.delete('reset');
  history.replaceState(null, '', location.pathname + (searchPrefs.size ? '?' + searchPrefs : ''));
  setTimeout(() => location.reload(), 5000);
}}
if (setupDialog.dataset.firstRun === 'true' && localStorage.getItem(setupDismissKey) !== '1') {{
  activateTab('settings', false);
  setupDialog.showModal();
}}
const resetDialog = document.querySelector('#reset-dialog');
document.querySelector('#open-reset').addEventListener('click', () => resetDialog.showModal());
document.querySelector('#cancel-reset').addEventListener('click', () => resetDialog.close());
const setupForm = document.querySelector('#setup-form');
const setupSteps = [...setupForm.querySelectorAll('.setup-step')];
let setupStep = 0;
function showSetupStep(index) {{
  setupStep = Math.max(0, Math.min(index, setupSteps.length - 1));
  setupSteps.forEach((step, i) => {{
    step.classList.toggle('active', i === setupStep);
    step.querySelector('.setup-count').textContent = `${{setupStep + 1}} von ${{setupSteps.length}}`;
  }});
  document.querySelector('#setup-error').hidden = true;
}}
setupForm.querySelectorAll('.setup-next').forEach(button => button.addEventListener('click', () => {{
  const invalid = [...setupSteps[setupStep].querySelectorAll('input,select')].find(field => !field.checkValidity());
  if (invalid) {{ invalid.reportValidity(); return; }}
  showSetupStep(setupStep + 1);
}}));
setupForm.querySelectorAll('.setup-back').forEach(button => button.addEventListener('click', () => showSetupStep(setupStep - 1)));
const wizardSourceMode = document.querySelector('#wizard-source-mode');
let previousWizardSource = wizardSourceMode.value;
function showWizardSource() {{
  const mode = wizardSourceMode.value;
  document.querySelector('#wizard-source-url').hidden = mode !== 'slfork';
  document.querySelector('#wizard-source-camera').hidden = mode === 'slfork';
  document.querySelector('#wizard-source-reference').hidden = mode !== 'camera';
  const attemptChoice = setupForm.querySelector('[name="attempts"]');
  if (mode === 'camera' && previousWizardSource !== 'camera' && attemptChoice.value === '5') {{
    attemptChoice.value = '10';
  }}
  previousWizardSource = mode;
}}
wizardSourceMode.addEventListener('change', showWizardSource); showWizardSource();
const wizardCropMode = setupForm.querySelector('[name="crop_mode"]');
function showWizardCrop() {{ document.querySelector('#wizard-crop-fields').hidden = wizardCropMode.value !== 'manual'; }}
wizardCropMode.addEventListener('change', showWizardCrop); showWizardCrop();
setupForm.querySelector('[name="fraction_digits"]').addEventListener('change', event => {{
  const maximum = Number(event.target.value);
  const precision = setupForm.querySelector('[name="decimals"]');
  [...precision.options].forEach(option => option.disabled = Number(option.value) > maximum);
  if (Number(precision.value) > maximum) precision.value = String(maximum);
}});
document.querySelector('#close-manual-test').addEventListener('click', () => {{
  manualTestArea.hidden = true;
}});
document.querySelector('#language-select').addEventListener('change', () => {{
  const url = new URL(document.querySelector('#language-form').action);
  if (document.querySelector('#manual-panel').open) url.searchParams.set('test', 'open');
  if (document.querySelector('#view-settings').hidden === false) url.searchParams.set('ui', 'settings');
  document.querySelector('#language-form').action = url;
  document.querySelector('#language-form').submit();
}});

let sendingCheck = false;
let statusPending = false;
const manualPanel = document.querySelector('#manual-panel');
const manualForm = document.querySelector('#manual-form');
const testBox = document.querySelector('#test-box');
const testButtons = [document.querySelector('#start-check'), document.querySelector('#start-check-with-options')];
function setTestActive(active) {{
  for (const [index, button] of testButtons.entries()) {{
    button.disabled = active;
    button.textContent = active ? 'Prüfung läuft …' : (index === 0 ? 'Test starten' : 'Jetzt prüfen');
  }}
}}
const cropMode = document.querySelector('#crop-mode');
const cropFields = document.querySelector('#crop-fields');
const autoCropMode = document.querySelector('#auto-crop-mode');
const autoCropFields = document.querySelector('#auto-crop-fields');
const sourceMode = document.querySelector('#source-mode');
function showSourceFields() {{
  const mode = sourceMode.value;
  for (const [selector, show] of [['#source-url', mode === 'slfork'],
      ['#source-camera', mode !== 'slfork'], ['#source-reference', mode === 'camera']]) {{
    const field = document.querySelector(selector);
    field.hidden = !show;
    field.querySelector('input').disabled = !show;
  }}
}}
sourceMode.addEventListener('change', showSourceFields);
showSourceFields();
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
    const bar = document.querySelector('#test-progress');
    const detail = document.querySelector('#test-result');
    const preview = document.querySelector('#test-preview');
    const previewImage = document.querySelector('#test-preview-image');
    const previewHeading = document.querySelector('#preview-heading');
    const automaticImages = document.querySelector('#automatic-images');
    const sourcePreview = document.querySelector('#test-source-preview');
    const sourceImage = document.querySelector('#test-source-image');
    const sourceEmpty = document.querySelector('#test-source-empty');
    const apply = document.querySelector('#apply-crop-form');
    const extra = document.querySelector('#ocr-details');
    const active = ['queued', 'running', 'ocr'].includes(job.phase);
    const outcome = job.phase === 'done' ? job.outcome : null;
    testBox.hidden = job.phase === 'idle';
    testBox.dataset.phase = job.phase;
    testBox.dataset.result = outcome === 'match' ? 'match' : outcome === 'storage_error' ? 'fail' :
      outcome && outcome !== 'ocr_only' ? 'warning' : 'neutral';
    setTestActive(active);

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
      sourcePreview.hidden = false;
      sourceImage.hidden = false;
      sourceImage.onload = () => {{ sourceImage.hidden = false; sourceEmpty.hidden = true; }};
      sourceImage.onerror = () => {{ sourceImage.hidden = true; sourceEmpty.hidden = false; }};
      sourceImage.src = 'testbild.jpg?v=' + encodeURIComponent(String(job.checked_at));
      detail.hidden = false;
      document.querySelector('#manual-readings').hidden = !job.ocr && job.reference == null;
      document.querySelector('#manual-ocr').textContent = job.ocr ?? '–';
      document.querySelector('#manual-reference').textContent = job.reference ?? '–';
      renderReferenceNote('manual', job.reference_time, job.reference_is_fallback);
      document.querySelector('#manual-image-time').textContent = job.image_time ? formatStamp(job.image_time) : '–';
      document.querySelector('#test-result-detail').textContent = job.detail || job.message || 'Kein Ergebnis.';
      document.querySelector('#test-result-stamp').textContent = job.checked_at ?
        new Intl.DateTimeFormat(lang === 'en' ? 'en-GB' : 'de-DE', {{day:'2-digit', month:'2-digit', year:'2-digit', hour:'2-digit', minute:'2-digit'}}).format(new Date(job.checked_at*1000)) : '';
      renderAttempts(extra, job.readings, job.comparison_decimals);
    }} else {{
      sourcePreview.hidden = true;
      detail.hidden = true;
      extra.hidden = true;
    }}
    if (job.phase === 'done' && job.preview) {{
      preview.hidden = false;
      previewHeading.textContent = 'Manueller Test';
      const url = 'testvorschau.jpg?v=' + encodeURIComponent(String(job.checked_at));
      if (previewImage.getAttribute('src') !== url) previewImage.setAttribute('src', url);
      automaticImages.open = true;
    }} else if (!active) {{
      const version = Number(job.automatic_preview || 0);
      if (version) {{
        preview.dataset.autoVersion = String(version);
        preview.dataset.autoAvailable = 'true';
        preview.dataset.autoSrc = 'automatikvorschau.jpg?v=' + encodeURIComponent(String(version));
      }}
      const available = preview.dataset.autoAvailable === 'true';
      preview.hidden = !available;
      previewHeading.textContent = 'Letzte automatische Erkennung';
      if (available && previewImage.getAttribute('src') !== preview.dataset.autoSrc) {{
        previewImage.setAttribute('src', preview.dataset.autoSrc);
      }}
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
function formatStamp(epoch) {{
  return new Intl.DateTimeFormat(lang === 'en' ? 'en-GB' : 'de-DE', {{day:'2-digit', month:'2-digit', year:'2-digit', hour:'2-digit', minute:'2-digit'}}).format(new Date(epoch * 1000));
}}
function renderReferenceNote(kind, epoch, fallback) {{
  const note = document.querySelector('#' + kind + '-reference-note');
  note.hidden = !epoch && !fallback;
  const time = epoch ? formatStamp(epoch) : 'Zeitpunkt unbekannt';
  note.textContent = fallback ? 'ESP-Ersatzwert · ' + time : time;
}}
const initialReference = document.querySelector('#automatic-reference-note').dataset;
renderReferenceNote('automatic', Number(initialReference.epoch), initialReference.fallback === '1');
for (const el of document.querySelectorAll('.stamp')) {{
  const epoch = Number(el.dataset.epoch);
  if (epoch) el.textContent = formatStamp(epoch);
}}
const manualTestArea = document.querySelector('#manual-test-area');
document.querySelector('#open-manual-settings').addEventListener('click', () => {{
  manualTestArea.hidden = false;
  manualPanel.open = true;
  manualPanel.scrollIntoView({{block: 'nearest'}});
}});
manualTestArea.hidden = testBox.hidden;
const testRequest = searchPrefs.get('test');
if (['queued', 'open', 'busy', 'ready'].includes(testRequest)) {{
  manualTestArea.hidden = false;
  if (testRequest === 'open' || testRequest === 'ready') manualPanel.open = true;
  else if (!testBox.hidden) testBox.focus();
  if (testRequest === 'ready') {{
    document.querySelector('#manual-test').scrollIntoView({{block: 'start'}});
    manualForm.querySelector('[name="image"]').focus({{preventScroll: true}});
  }}
  searchPrefs.delete('test');
  history.replaceState(null, '', location.pathname + (searchPrefs.size ? '?' + searchPrefs : ''));
}}
manualForm.addEventListener('submit', event => {{
  if (sendingCheck) {{
    event.preventDefault();
    return;
  }}
  sendingCheck = true;
  manualTestArea.hidden = false;
  testBox.hidden = false;
  testBox.dataset.phase = 'queued';
  testBox.dataset.result = 'neutral';
  document.querySelector('#test-head').textContent = 'Anfrage wird gesendet';
  document.querySelector('#test-status').textContent = 'Prüfung läuft …';
  document.querySelector('#test-result').hidden = true;
  document.querySelector('#ocr-details').hidden = true;
  document.querySelector('#test-preview').hidden = true;
  document.querySelector('#apply-crop-form').hidden = true;
  setTestActive(true);
}});
manualForm.addEventListener('invalid', () => {{
  manualPanel.open = true;
}}, true);
tick(); setInterval(tick, 1000);
const automaticBanner = document.querySelector('#automatic-banner');
const ignoreWarning = document.querySelector('#ignore-automatic-warning');
const preferenceKey = automaticBanner.dataset.preferenceKey;
const anonymousPreferenceKey = '{anonymous_banner_key}';
let ignoredIncident = '';
try {{
  ignoredIncident = (preferenceKey ? localStorage : sessionStorage).getItem(preferenceKey || anonymousPreferenceKey) || '';
}} catch (_) {{ /* Storage is optional. */ }}
function updateBannerVisibility() {{
  automaticBanner.hidden = Boolean(automaticBanner.dataset.incident) &&
    automaticBanner.dataset.incident === ignoredIncident;
}}
ignoreWarning.addEventListener('click', () => {{
  ignoredIncident = automaticBanner.dataset.incident;
  try {{
    (preferenceKey ? localStorage : sessionStorage).setItem(preferenceKey || anonymousPreferenceKey, ignoredIncident);
  }} catch (_) {{ /* Keep the choice for the current view. */ }}
  updateBannerVisibility();
}});
updateBannerVisibility();

async function refreshAutomatic() {{
  try {{
    const response = await fetch('automatic?lang=' + lang, {{cache: 'no-store'}});
    if (!response.ok) throw new Error();
    const sample = await response.json();
    next = sample.next_check;
    automaticBanner.dataset.tone = sample.tone;
    automaticBanner.dataset.incident = sample.incident;
    ignoreWarning.hidden = !sample.incident;
    const heading = document.querySelector('#automatic-status-heading');
    const icon = automaticBanner.querySelector('.automatic-banner-icon');
    const detail = document.querySelector('#automatic-result');
    if (heading.textContent !== sample.heading) heading.textContent = sample.heading;
    if (icon.textContent !== sample.icon) icon.textContent = sample.icon;
    if (detail.textContent !== sample.detail) detail.textContent = sample.detail;
    updateBannerVisibility();
    document.querySelector('#automatic-ocr').textContent = sample.ocr;
    document.querySelector('#automatic-reference').textContent = sample.reference;
    renderReferenceNote('automatic', sample.reference_time, sample.reference_is_fallback);
    renderAttempts(document.querySelector('#automatic-ocr-details'), sample.readings, sample.decimals);
    for (const [id, value] of [['image-time', sample.image_time], ['last-check', sample.last_check],
        ['last-match', sample.last_match]]) {{
      document.querySelector('#automatic-' + id).textContent = value ? formatStamp(value) : '–';
    }}
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


ROTATION_OPTIONS = {str(angle): f"{angle}°" for angle in ROTATIONS}
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
    load_language_modes, save_language_modes, get_delivery, save_delivery, get_source, save_source,
    wake_worker=None, *, address=("0.0.0.0", 8099), test_source_image=None, automatic_preview=None,
    request_factory_reset=None, skip_setup=None,
):
    images = {"/aktuell.jpg": current_image, "/treffer.jpg": good_image,
              "/testvorschau.jpg": test_image}
    if automatic_preview is not None:
        images["/automatikvorschau.jpg"] = automatic_preview
    if test_source_image is not None:
        images["/testbild.jpg"] = test_source_image
    manual_settings_path = history_path.with_name("manual-test-settings.json")
    csrf_token = token_urlsafe(32)
    request_lock = Lock()
    preferences_lock = Lock()
    rules_lock = Lock()
    delivery_lock = Lock()
    def read_auto_rules():
        return {"integer_digits": 5, "fraction_digits": 3, "meter_display": "rollers",
                "fallback_value": "", "fallback_time": "", **get_auto_rules()}

    def load_manual_settings():
        try:
            value = json.loads(manual_settings_path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def save_manual_settings(values):
        manual_settings_path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile("w", encoding="utf-8", dir=manual_settings_path.parent,
                                prefix=".manual-test-", delete=False) as temporary:
            temporary.write(json.dumps(values, ensure_ascii=False))
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_name = temporary.name
        os.chmod(temporary_name, 0o600)
        os.replace(temporary_name, manual_settings_path)
    source_lock = Lock()
    progress = {
        "request_id": 0, "phase": "idle", "message": "Noch kein manueller Test gestartet.",
        "attempts": 0, "max_attempts": default_attempts,
        "started_at": 0, "checked_at": 0, "outcome": None, "detail": "",
        "preview": False, "can_apply_crop": False, "readings": [],
        "comparison_decimals": default_decimals, "ocr": None, "reference": None,
        "reference_time": None, "reference_is_fallback": False, "image_time": None,
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
                reference_time=previous.get("reference_time"),
                reference_is_fallback=previous.get("reference_is_fallback", False),
                image_time=previous.get("image_time"),
                readings=previous.get("readings", []),
                comparison_decimals=previous.get("settings", {}).get("decimals", default_decimals),
            )
    except (OSError, ValueError, AttributeError, TypeError):
        pass

    def update_progress(request_id, phase, message, attempts=0, checked_at=0, outcome=None,
                        detail="", preview=False, can_apply_crop=False, readings=None,
                        ocr=None, reference=None, reference_time=None,
                        reference_is_fallback=False, image_time=None):
        """Only the newest request may update the visible status."""
        with request_lock:
            if progress["request_id"] != request_id:
                return
            progress.update(phase=phase, message=message, attempts=attempts,
                            checked_at=checked_at, outcome=outcome, detail=detail,
                            preview=preview, can_apply_crop=can_apply_crop, ocr=ocr, reference=reference,
                            reference_time=reference_time, reference_is_fallback=reference_is_fallback,
                            image_time=image_time,
                            readings=readings if readings is not None else progress["readings"])

    def reset_progress_state():
        with request_lock:
            progress.update(
                request_id=progress["request_id"] + 1, phase="idle",
                message="Noch kein manueller Test gestartet.", attempts=0,
                checked_at=0, outcome=None, detail="", preview=False,
                can_apply_crop=False, readings=[], ocr=None, reference=None,
                reference_time=None, reference_is_fallback=False, image_time=None,
            )

    def read_history():
        try:
            history = json.loads(history_path.read_text(encoding="utf-8"))
            return history if isinstance(history, dict) else {}
        except (OSError, ValueError):
            return {}

    def automatic_summary(history, language, auto_rules):
        reschedule_next_check(history, auto_rules.get("interval_minutes", DEFAULT_INTERVAL_MINUTES))
        detail = history.get("check_detail")
        precision_pending = any(history.get(key, value) != value for key, value in (
            ("comparison_decimals", auto_rules["decimals"]),
            ("comparison_integer_digits", auto_rules["integer_digits"]),
            ("comparison_fraction_digits", auto_rules["fraction_digits"]),
        ))
        if precision_pending:
            detail = ("Neue Zählereinstellungen gespeichert. Die nächste automatische "
                      "Prüfung zeigt das erste Ergebnis mit diesen Angaben.")
        if language == "en" and detail:
            detail = english_result(
                detail, history.get("check_status") or history.get("status"),
                history.get("comparison_decimals", default_decimals), history.get("ocr_readings"),
            )
        status = history.get("check_status") or history.get("status")
        tone = "neutral"
        heading = "Automatischer Prüfstatus"
        icon = ""
        incident = ""
        show_attempts = False
        if not precision_pending and status == "match":
            tone, heading, icon = "ok", "Zählerstand bestätigt", "✓"
        elif not precision_pending and status in (
            "difference", "ocr_unclear", "slfork_unclear", "stale_sample", "capture_unavailable",
        ):
            now = time.time()
            failure_since = history.get("failure_since")
            prolonged = failure_since is not None and now - failure_since >= WARNING_DETAIL_AFTER
            tone, heading, icon = "warning", "Letzte Prüfung fehlgeschlagen", "!"
            if prolonged:
                heading = "Zählerstand bitte prüfen"
                capture_failure_since = history.get("capture_failure_since", failure_since)
                if (status == "capture_unavailable" and capture_failure_since is not None
                        and now - capture_failure_since >= WARNING_DETAIL_AFTER):
                    tone = "problem"
                incident = str(failure_since) if tone == "warning" else f"critical-{failure_since}"
                show_attempts = status == "ocr_unclear"
            else:
                detail = ""
        if language == "en":
            heading = EN_UI[heading]
        return {
            "detail": (detail if detail is not None else
                       "No automatic result yet." if language == "en" else "Noch kein automatisches Prüfergebnis."),
            "tone": tone, "heading": heading, "icon": icon,
            "incident": incident,
            "ocr": str(history["ocr_value"]) if history.get("ocr_value") is not None else "–",
            "reference": str(history["last_reference"]) if history.get("last_reference") is not None else "–",
            "reference_time": history.get("last_reference_time"),
            "reference_is_fallback": history.get("last_reference_is_fallback", False),
            "image_time": history.get("last_epoch") or 0,
            "next_check": history.get("next_check_at"),
            "last_check": last_check_at(history),
            "last_match": history.get("last_match_at"),
            "readings": history.get("ocr_readings", []) if show_attempts else [],
            "decimals": history.get("comparison_decimals", default_decimals),
            "current": current_image.stat().st_mtime_ns if current_image.exists() else None,
            "good": good_image.stat().st_mtime_ns if good_image.exists() else None,
            "automatic_preview": automatic_preview.stat().st_mtime_ns if automatic_preview is not None and automatic_preview.exists() else None,
            "automatic_preview": automatic_preview.stat().st_mtime_ns if automatic_preview is not None and automatic_preview.exists() else None,
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

        def reply(self, content, media_type, status=200):
            self.send_response(status)
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
                snapshot["automatic_preview"] = (
                    automatic_preview.stat().st_mtime_ns
                    if automatic_preview is not None and automatic_preview.exists() else None
                )
                if language == "en":
                    snapshot["message"] = english_progress(snapshot.get("message"))
                    if snapshot.get("detail"):
                        snapshot["detail"] = english_result(
                            snapshot["detail"], snapshot.get("outcome"),
                            snapshot.get("comparison_decimals", default_decimals),
                            snapshot.get("readings"),
                        )
                self.reply(json.dumps(snapshot).encode("utf-8"), "application/json; charset=utf-8")
                return
            if path not in ("/", "/automatic"):
                self.send_error(404)
                return
            history = read_history()
            auto_rules = read_auto_rules()
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
            delivery = get_delivery()
            source, setup_pending = get_source()
            source_choices = (
                {"slfork": "SLFork / AI on the Edge", "camera": "Home Assistant camera (snapshot per check)",
                 "esphome": "ESPHome or camera with local OCR"} if language == "en" else
                {"slfork": "SLFork / AI on the Edge", "camera": "Home-Assistant-Kamera (Livebild, Standbild je Prüfung)",
                 "esphome": "ESPHome oder Kamera mit lokaler OCR"}
            )
            intro = ("Choose a source to start automatic checks." if language == "en" else
                     "Wähle eine Bildquelle, um die automatische Kontrolle zu starten.")
            values = {name: html.escape(summary[name]) for name in ("ocr", "reference", "detail")}
            manual_saved = load_manual_settings()
            settings = {**auto_rules, **history.get("manual_result", {}).get("settings", {}), **manual_saved}
            decimals_by_language = DECIMALS_EN if language == "en" else DECIMALS
            comparable_decimals = {key: label for key, label in decimals_by_language.items()
                                   if int(key) <= auto_rules["fraction_digits"]}
            manual_precision = min(int(settings.get("decimals", auto_rules["decimals"])),
                                   auto_rules["fraction_digits"])
            saved = query.get("saved", [""])[0]
            settings_tab_active = (
                query.get("ui", [""])[0] == "settings"
                or saved in ("setup", "1", "crop", "notifications", "source")
                or setup_pending
            )
            saved_message = (
                "Einrichtung gespeichert." if saved == "setup" else
                "Automatische Prüfregeln gespeichert." if saved == "1" else
                "Getesteten Bildausschnitt für die Automatik übernommen." if saved == "crop" else
                "Benachrichtigungen gespeichert." if saved == "notifications" else
                "Bildquelle gespeichert." if saved == "source" else ""
            )
            if language == "en" and saved_message:
                saved_message = EN_UI.get(saved_message, saved_message)
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
                test_visible = progress["phase"] != "idle"
            test_source_version = (test_source_image.stat().st_mtime_ns
                                   if test_source_image is not None and test_source_image.exists() else 0)
            test_source_preview = (
                '<details class="source-image" id="test-source-preview" {test_source_visible}>'
                '<summary>Originalbild zum Ablesen</summary>'
                f'<img id="test-source-image" src="testbild.jpg?v={test_source_version}" alt="Aktuelles Kamerabild für den manuellen Test">'
                '<p class="legend" id="test-source-empty" hidden>Kein Bild vorhanden. Bitte Bildquelle und Verbindung prüfen und den manuellen Test erneut starten.</p>'
                '</details>'
            )
            page = translate_page(PAGE) if language == "en" else PAGE
            self.reply(page.format(**values,
                language=language,
                app_name=APP_NAME,
                language_mode=mode,
                automatic_tone=summary["tone"], automatic_heading=summary["heading"],
                automatic_icon=summary["icon"], automatic_incident=html.escape(summary["incident"]),
                banner_preference_key=f"{NAMESPACE}-ignored-warning-{user}" if user else "",
                anonymous_banner_key=f"{NAMESPACE}-ignored-warning",
                ignore_hidden="" if summary["incident"] else "hidden",
                profile_script=scripts,
                overview_hidden="hidden" if settings_tab_active else "",
                settings_hidden="" if settings_tab_active else "hidden",
                language_options=select_options({"auto": automatic, "de": "Deutsch", "en": "English"}, mode),
                settings_open="open" if saved in ("1", "crop") else "",
                setup_first_run=str(bool(setup_pending)).lower(),
                wizard_source_options=select_options(source_choices, source["mode"]),
                meter_display_options=select_options({
                    "rollers": "Number rollers" if language == "en" else "Ziffernrollen",
                    "digital": "Digital numeric display" if language == "en" else "Digitales Zifferndisplay",
                    "mixed": "Number rollers plus pointers" if language == "en" else "Ziffernrollen plus Zeiger",
                }, auto_rules["meter_display"]),
                integer_digit_options=select_options({str(value): str(value) for value in range(1, 10)},
                                                     str(auto_rules["integer_digits"])),
                fraction_digit_options=select_options({str(value): str(value) for value in range(0, 4)},
                                                      str(auto_rules["fraction_digits"])),
                wizard_decimal_options=select_options(
                    {key: label for key, label in (DECIMALS_EN if language == "en" else DECIMALS).items()
                     if int(key) <= auto_rules["fraction_digits"]}, str(auto_rules["decimals"])),
                wizard_crop_options=select_options(
                    CROP_MODES_EN if language == "en" else CROP_MODES, auto_rules["crop_mode"]),
                fallback_value=html.escape(auto_rules["fallback_value"], quote=True),
                fallback_time=html.escape(auto_rules["fallback_time"], quote=True),
                wizard_saved_notice=auto_saved_notice if saved == "setup" else "",
                manual_open="open" if test == "open" else "",
                test_hidden="" if test_visible or test in ("queued", "busy") else "hidden",
                test_source_visible="" if test_visible else "hidden",
                notifications_open="open" if saved == "notifications" else "",
                source_open="open" if setup_pending or saved == "source" else "",
                source_intro=f'<p class="settings-note">{intro}</p>' if setup_pending else "",
                source_options=select_options(source_choices, source["mode"]),
                source_url=html.escape(source["url"]), source_camera=html.escape(source["camera"]),
                source_reference=html.escape(source["reference"]),
                source_saved_notice=auto_saved_notice if saved == "source" else "",
                notifications_enabled="checked" if delivery["enabled"] else "",
                notification_review=delivery["review_minutes"], notification_delay=delivery["delivery_hours"],
                notification_push=html.escape(delivery["push"]), notification_target=html.escape(delivery["target"]),
                notification_saved_notice=auto_saved_notice if saved == "notifications" else "",
                request_status=request_status,
                polarity_options=select_options(
                    POLARITIES_EN if language == "en" else POLARITIES,
                    settings.get("polarity", "auto"),
                ),
                decimal_options=select_options(
                    comparable_decimals, str(manual_precision),
                ),
                auto_decimal_options=select_options(
                    comparable_decimals, str(auto_rules["decimals"]),
                ),
                auto_attempt_options=select_options(
                    {value: label for value, label in ATTEMPTS.items()
                     if source["mode"] != "esphome" or value != "1"},
                    str(max(2, auto_rules["attempts"]) if source["mode"] == "esphome" else auto_rules["attempts"]),
                ),
                auto_polarity_options=select_options(
                    POLARITIES_EN if language == "en" else POLARITIES, auto_rules["polarity"],
                ),
                auto_crop_mode_options=select_options(
                    CROP_MODES_EN if language == "en" else CROP_MODES, auto_rules["crop_mode"],
                ),
                auto_crop_value=html.escape(auto_rules["crop"], quote=True),
                auto_width_value=auto_rules["width"],
                max_flow=format_cubic_metres(auto_rules.get("max_flow_lph", DEFAULT_FLOW_LPH)),
                max_interval_minutes=MAX_INTERVAL_MINUTES,
                interval_minutes=auto_rules.get("interval_minutes", DEFAULT_INTERVAL_MINUTES),
                auto_rotation_options=select_options(ROTATION_OPTIONS, str(auto_rules.get("rotation", 0))),
                auto_saved_notice=auto_saved_notice if saved in ("1", "crop") else "",
                manual_reference=html.escape(str(settings.get("manual_reference", auto_rules["fallback_value"])),
                                             quote=True),
                test_source_preview=test_source_preview,
                automatic_preview_src=(
                    f'automatikvorschau.jpg?v={summary["automatic_preview"]}'
                    if summary["automatic_preview"] else 'automatikvorschau.jpg?v=0'
                ),
                automatic_preview_version=summary["automatic_preview"] or 0,
                automatic_preview_available=str(bool(summary["automatic_preview"])).lower(),
                automatic_preview_hidden='' if summary["automatic_preview"] else 'hidden',
                reset_notice=(
                    '<p class="save-notice" role="status">' + html.escape({
                        "done": "Werkseinstellungen wiederhergestellt. Die Einrichtung öffnet sich erneut.",
                        "pending": "Werkreset läuft noch. Bitte die Seite in Kürze neu laden.",
                        "failed": "Werkreset konnte nicht vollständig ausgeführt werden.",
                    }.get(query.get("reset", [""])[0], "")) + '</p>'
                    if query.get("reset", [""])[0] in ("done", "pending", "failed") else ""
                ),
                manual_area_hidden='' if test in ("queued", "busy", "open") else 'hidden',
                crop_mode_options=select_options(
                    CROP_MODES_EN if language == "en" else CROP_MODES,
                    settings.get("crop_mode", "auto"),
                ),
                crop_value=html.escape(str(settings.get("crop", default_crop)), quote=True),
                width_value=int(settings.get("width", default_width)),
                rotation_options=select_options(ROTATION_OPTIONS, str(settings.get("rotation", 0))),

                attempt_options=select_options(ATTEMPTS, str(settings.get("attempts", auto_rules["attempts"]))),
                default_attempts=default_attempts,
                csrf=csrf_token,
                reference_time=summary["reference_time"] or 0,
                reference_is_fallback=int(summary["reference_is_fallback"]),
                image_time=summary["image_time"],
                last_check=summary["last_check"] or 0,
                last_match=summary["last_match"] or 0,
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
            if path not in ("/pruefen", "/automatik", "/ausschnitt-uebernehmen", "/sprache",
                            "/benachrichtigungen", "/bildquelle", "/einrichtung",
                            "/einrichtung-ueberspringen", "/werkreset"):
                self.send_error(404)
                return
            fallback = browser_locale(self.headers.get("Accept-Language", ""))
            language = fallback
            keep_mode = ""

            def problem(code, german=None, english=None):
                if german is None:
                    german, english = {
                        400: ("Bitte die Formulareingaben prüfen.", "Check the form values."),
                        403: ("Bitte die App erneut öffnen und das Formular nochmals absenden.",
                              "Reopen the app and submit the form again."),
                        503: ("Die Einstellungen konnten nicht gespeichert werden.",
                              "Could not save the settings."),
                    }[code]
                message, back = ((english, "Back to the checks") if language == "en"
                                 else (german, "Zurück zur Kontrolle"))
                again = "./" + ("?" + keep_mode[1:] if keep_mode else "")
                content = (f'<!doctype html><html lang="{language}"><meta charset="utf-8">'
                           '<meta name="viewport" content="width=device-width">'
                           f'<title>{html.escape(message)}</title>'
                           '<style>body{font:1rem system-ui;max-width:40rem;margin:2rem auto;'
                           'padding:0 1rem}a{display:inline-block;padding:.5rem 0}</style>'
                           f'<main><p>{html.escape(message)}</p><a href="{again}">{back}</a></main></html>')
                self.reply(content.encode("utf-8"), "text/html; charset=utf-8", code)

            # Ingress and companion webviews need not forward Fetch Metadata headers.
            image_upload = None
            content_type = self.headers.get_content_type()
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if content_type == "application/x-www-form-urlencoded":
                    if not 0 < length <= 4096:
                        raise ValueError("Invalid form length")
                    form = parse_qs(self.rfile.read(length).decode("ascii"), keep_blank_values=True,
                                    max_num_fields=40)
                elif content_type == "multipart/form-data" and path == "/pruefen":
                    if not 0 < length <= MAX_MANUAL_IMAGE_BYTES + MAX_MULTIPART_OVERHEAD:
                        raise ValueError("Invalid upload length")
                    body = self.rfile.read(length)
                    envelope = (b"Content-Type: " + self.headers.get("Content-Type", "").encode("ascii")
                                + b"\r\nMIME-Version: 1.0\r\n\r\n" + body)
                    message = BytesParser(policy=email_policy).parsebytes(envelope)
                    if not message.is_multipart():
                        raise ValueError("Invalid multipart form")
                    form = {}
                    found_image = False
                    for part in message.iter_parts():
                        name = part.get_param("name", header="content-disposition")
                        filename = part.get_filename()
                        payload = part.get_payload(decode=True) or b""
                        if filename is not None:
                            if not filename and not payload:
                                continue
                            if (name != "image" or found_image
                                    or part.get_content_type() not in ("image/jpeg", "image/png")
                                    or len(payload) > MAX_MANUAL_IMAGE_BYTES):
                                raise ValueError("Unsupported test image")
                            found_image = True
                            image_upload = payload
                        elif name:
                            form.setdefault(name, []).append(payload.decode("utf-8"))
                    if not form:
                        raise ValueError("Empty multipart form")
                else:
                    problem(403)
                    return
            except (ValueError, UnicodeDecodeError, UnicodeEncodeError, LookupError):
                problem(400)
                return
            user = self.user_id()
            mode = form.get("mode", ["auto"])
            form_language = form.get("lang", [fallback])
            if len(mode) != 1 or mode[0] not in MODES or len(form_language) != 1 or form_language[0] not in SUPPORTED:
                problem(400)
                return
            language = form_language[0]
            mode = mode[0]
            keep_mode = "&mode=" + mode if not user and mode != "auto" else ""
            supplied = form.get("csrf", [])
            if len(supplied) != 1 or not compare_digest(supplied[0].encode(), csrf_token.encode()):
                problem(403)
                return
            if path == "/einrichtung-ueberspringen":
                try:
                    if skip_setup is not None:
                        skip_setup()
                except OSError:
                    problem(503, "Die Einrichtung konnte nicht übersprungen werden.",
                            "Setup could not be skipped.")
                    return
                self.redirect("?saved=skip" + keep_mode)
                return
            if path == "/werkreset":
                result = request_factory_reset() if request_factory_reset is not None else "failed"
                if result == "done":
                    reset_progress_state()
                if result not in ("done", "pending", "failed"):
                    result = "failed"
                self.redirect("?reset=" + result + "&ui=settings" + keep_mode)
                return
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
                        if mode in SUPPORTED:
                            language = mode
                        problem(503, "Die Spracheinstellung konnte nicht gespeichert werden.",
                                "Could not save the language setting.")
                        return
                test_open = parse_qs(urlsplit(self.path).query).get("test") == ["open"]
                params = (["test=open"] if test_open else []) + (
                    ["mode=" + mode] if keep_mode else [])
                self.redirect("?" + "&".join(params) if params else "")
                return
            def field(name, default=""):
                value, = form.get(name, [default])
                return value

            if path == "/einrichtung":
                try:
                    source_values = source_rules({
                        "mode": field("source_mode"), "url": field("url"),
                        "camera": field("camera"), "reference": field("reference"),
                    })
                    old_rules = read_auto_rules()
                    integer_digits = int(field("integer_digits"))
                    fraction_digits = int(field("fraction_digits"))
                    decimals = int(field("decimals"))
                    attempts = int(field("attempts"))
                    interval_minutes = int(field("interval_minutes"))
                    polarity = field("polarity")
                    crop_mode = field("crop_mode")
                    meter_display = field("meter_display")
                    if (not 1 <= integer_digits <= 9 or not 0 <= fraction_digits <= 3
                            or not 0 <= decimals <= fraction_digits or not 1 <= attempts <= 10
                            or not valid_interval_minutes(interval_minutes)
                            or polarity not in POLARITIES or crop_mode not in CROP_MODES
                            or meter_display not in ("rollers", "digital", "mixed")):
                        raise ValueError("Prüfe Ziffernzahl, Vergleichsgenauigkeit und Prüfintervall.")
                    crop = field("crop", old_rules["crop"])
                    width = int(field("width", str(old_rules["width"])))
                    rotation = int(field("rotation", str(old_rules.get("rotation", 0))))
                    crop_coordinates(crop, width, rotation)
                    max_flow = parse_flow_limit(field("max_flow"))
                    fallback_value = field("fallback_value").strip()
                    fallback_time = field("fallback_time").strip()
                    if fallback_value:
                        reading = re.fullmatch(r"([0-9]{1,9})(?:[.,]([0-9]{1,3}))?", fallback_value)
                        if (not reading or len(reading[2] or "") > fraction_digits
                                or meter_prefix(fallback_value, decimals, integer_digits) is None
                                or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}", fallback_time)):
                            raise ValueError("Fallback-Wert und Ablesezeit passen nicht zur Zähleranzeige.")
                        datetime.fromisoformat(fallback_time)
                    else:
                        fallback_time = ""
                    enabled = field("notifications_enabled") == "1"
                    delivery_values = notification_rules({
                        "enabled": enabled, "review_minutes": int(field("review_minutes")),
                        "delivery_hours": int(field("delivery_hours")),
                        "push": field("push"), "target": field("target"),
                    })
                    rules_values = {
                        **old_rules, "decimals": decimals, "attempts": attempts,
                        "polarity": polarity, "crop_mode": crop_mode, "crop": crop,
                        "width": width, "rotation": rotation, "max_flow_lph": max_flow,
                        "interval_minutes": interval_minutes, "integer_digits": integer_digits,
                        "fraction_digits": fraction_digits, "meter_display": meter_display,
                        "fallback_value": fallback_value, "fallback_time": fallback_time,
                    }
                    with source_lock:
                        save_source(source_values)
                    with rules_lock:
                        save_auto_rules(rules_values)
                    with delivery_lock:
                        save_delivery(delivery_values)
                except (ValueError, TypeError):
                    problem(400, "Bitte prüfe Bildquelle, Ziffernaufteilung und Fallback-Wert.",
                            "Check the image source, digit layout and fallback reading.")
                    return
                except OSError:
                    problem(503)
                    return
                self.redirect("?saved=setup&test=ready&ui=overview" + keep_mode)
                return

            if path == "/bildquelle":
                try:
                    with source_lock:
                        current, _ = get_source()
                        values = source_rules({
                            "mode": field("source_mode"),
                            **{key: field(key, current[key]) for key in ("url", "camera", "reference")},
                        })
                        save_source(values)
                    if wake_worker is not None:
                        wake_worker()
                except ValueError:
                    problem(400, "Bitte prüfe die Adresse oder die Entitäts-ID der Bildquelle.",
                            "Check the address or entity ID of the image source.")
                    return
                except OSError:
                    problem(503)
                    return
                self.redirect("?saved=source" + keep_mode)
                return
            if path == "/benachrichtigungen":
                try:
                    values = notification_rules({
                        "enabled": field("enabled") == "1",
                        "review_minutes": int(field("review_minutes")),
                        "delivery_hours": int(field("delivery_hours")),
                        "push": field("push"),
                        "target": field("target"),
                    })
                    with delivery_lock:
                        save_delivery(values)
                except ValueError:
                    problem(400, "Bitte Wartezeiten und Benachrichtigungsziele prüfen.",
                            "Check the notification delays and destinations.")
                    return
                except OSError:
                    problem(503)
                    return
                self.redirect("?saved=notifications" + keep_mode)
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
                            problem(409, "Bitte den Ausschnitt erneut testen.", "Run the crop test again.")
                            return
                        current = read_auto_rules()
                        current.update(crop_mode="manual", crop=settings["crop"], width=settings["width"],
                                       rotation=settings.get("rotation", 0))
                        save_auto_rules(current)
                except (OSError, ValueError, KeyError, TypeError):
                    problem(503, "Der Ausschnitt konnte nicht gespeichert werden.",
                            "Could not save the image crop.")
                    return
                self.redirect("?saved=crop&ui=settings" + keep_mode)
                return
            if path == "/automatik":
                decimals = form.get("decimals", [])
                attempts = form.get("attempts", [])
                polarity = form.get("polarity", [])
                crop_mode = form.get("crop_mode", [])
                if (len(decimals) != 1 or decimals[0] not in DECIMALS
                        or len(attempts) != 1 or attempts[0] not in ATTEMPTS
                        or len(polarity) != 1 or polarity[0] not in POLARITIES
                        or len(crop_mode) != 1 or crop_mode[0] not in CROP_MODES):
                    problem(400)
                    return
                try:
                    with rules_lock:
                        old_rules = read_auto_rules()
                        if int(decimals[0]) > old_rules["fraction_digits"]:
                            raise ValueError("Vergleichsgenauigkeit übersteigt die Nachkommastellen.")
                        crop = old_rules["crop"]
                        width = old_rules["width"]
                        rotation = old_rules.get("rotation", 0)
                        if crop_mode[0] == "manual":
                            crop = field("crop", crop)
                            width = int(field("width", str(width)))
                            rotation = int(field("rotation", str(rotation)))
                            crop_coordinates(crop, width, rotation)
                        max_flow = parse_flow_limit(field(
                            "max_flow", format_cubic_metres(old_rules.get("max_flow_lph", DEFAULT_FLOW_LPH))
                        ))
                        interval_minutes = int(field(
                            "interval_minutes", str(old_rules.get("interval_minutes", DEFAULT_INTERVAL_MINUTES))
                        ))
                        if not valid_interval_minutes(interval_minutes):
                            raise ValueError("Ungültiges Prüfintervall")
                        save_auto_rules({"decimals": int(decimals[0]), "attempts": int(attempts[0]),
                                         "polarity": polarity[0], "crop_mode": crop_mode[0],
                                         "crop": crop, "width": width, "rotation": rotation,
                                         "max_flow_lph": max_flow, "interval_minutes": interval_minutes})
                except ValueError:
                    problem(400, "Bitte Prüfintervall, Bildbereich und Durchfluss prüfen.",
                            "Check the interval, image region, and maximum flow.")
                    return
                except OSError:
                    problem(503)
                    return
                self.redirect("?saved=1" + keep_mode)
                return
            auto_rules = read_auto_rules()
            polarity = form.get("polarity", ["auto"])
            decimals = form.get("decimals", [str(auto_rules["decimals"])])
            attempts = form.get("attempts", [str(auto_rules["attempts"])])
            crop_mode = form.get("crop_mode", ["auto"])
            if (len(polarity) != 1 or polarity[0] not in POLARITIES or len(decimals) != 1
                    or decimals[0] not in DECIMALS or len(attempts) != 1 or attempts[0] not in ATTEMPTS):
                problem(400)
                return
            if len(crop_mode) != 1 or crop_mode[0] not in CROP_MODES:
                problem(400)
                return
            if int(decimals[0]) > auto_rules["fraction_digits"]:
                problem(400, "Die Vergleichsgenauigkeit übersteigt die eingestellten Nachkommastellen.",
                        "Comparison precision exceeds the configured decimal places.")
                return
            crop_value = default_crop
            width_value = default_width
            rotation = 0
            if crop_mode[0] == "manual":
                try:
                    crop_value = field("crop", default_crop)
                    width_value = int(field("width", str(default_width)))
                    rotation = int(field("rotation", "0"))
                    boundaries = crop_coordinates(crop_value, width_value, rotation)
                    crop_value = ",".join(map(str, boundaries))
                except ValueError:
                    problem(400)
                    return
            settings = {"polarity": polarity[0], "decimals": int(decimals[0]),
                        "attempts": int(attempts[0]), "crop_mode": crop_mode[0],
                        "crop": crop_value, "width": width_value, "rotation": rotation}
            manual_reference = field("manual_reference").strip()
            if manual_reference:
                reading = re.fullmatch(r"([0-9]{1,9})(?:[.,]([0-9]{1,3}))?", manual_reference)
                if (not reading or len(reading[2] or "") > auto_rules["fraction_digits"]
                        or meter_prefix(manual_reference, int(decimals[0]), auto_rules["integer_digits"]) is None):
                    problem(400, "Fallback-Wert passt nicht zur eingestellten Zähleranzeige.",
                            "Fallback reading does not match the configured meter display.")
                    return
            settings["manual_reference"] = manual_reference
            try:
                save_manual_settings({key: value for key, value in settings.items() if key not in ("request_id", "image")})
                if test_source_image is not None:
                    test_source_image.unlink(missing_ok=True)
                test_image.unlink(missing_ok=True)
            except OSError:
                problem(503, "Die Testeinstellungen konnten nicht gespeichert werden.",
                        "Could not save the manual test settings.")
                return
            with request_lock:
                if progress["phase"] in ("queued", "running", "ocr"):
                    self.redirect("?test=busy" + keep_mode)
                    return
                request_id = progress["request_id"] + 1
                settings["request_id"] = request_id
                if image_upload is not None:
                    settings["image"] = image_upload
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
                                ocr=None, reference=None, reference_time=None,
                                reference_is_fallback=False, image_time=None)
            if wake_worker is not None:
                wake_worker()
            self.redirect("?test=queued" + keep_mode)

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(address, Handler)
    Thread(target=server.serve_forever, daemon=True).start()
    return server, update_progress
