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
from queue import Empty, Full
from secrets import compare_digest, token_urlsafe
from threading import Lock, Thread
from tempfile import NamedTemporaryFile
from urllib.parse import parse_qs, urlsplit

from app_channel import APP_NAME, NAMESPACE
from calibration import DEFAULT_LIMIT, MIN_IMAGE_LIMIT, MAX_IMAGES, search_region
from meter_learning import GEOMETRY_REPAIR_FAILURES
from checks import (DEFAULT_INTERVAL_MINUTES, MAX_INTERVAL_MINUTES, WARNING_DETAIL_AFTER, meter_prefix,
                    LAST_DIGIT_NOTICE, LAST_DIGIT_PASS, REFLECTION_SUGGEST_AFTER, STANDALONE_PENDING, STANDALONE_REJECTED_NOTICE,
                    STANDALONE_VERIFIED_NOTICE, last_check_at, reschedule_next_check,
                    valid_interval_minutes)
from consumption import DEFAULT_FLOW_LPH, format_cubic_metres, parse_flow_limit
from i18n import EN_UI, english_progress, english_result, translate_page
from language import MODES, SUPPORTED, USER_ID, browser_locale, profile_script
from layout import MANUAL_ROW_UNCLEAR, RAW_ROW_UNCLEAR, crop_coordinates, digit_box_settings
from notification_settings import notification_rules
from source_settings import source_rules

SUPERVISOR_ADDRESS = "172.30.32.2"
MAX_MANUAL_IMAGE_BYTES = 3_000_000
MAX_MULTIPART_OVERHEAD = 16_384

CALIBRATION_PREVIEW_HTML = """<details class="calibration-photo-panel" open hidden>
<summary>Bilder der Selbsteinrichtung</summary>
<div class="calibration-photo-grid">
<figure>
<div class="calibration-photo-frame">
<img data-image="frame" alt="Kamerabild der Selbsteinrichtung" decoding="async">
<span class="calibration-crop-region" hidden></span>
</div>
<figcaption>Aktuelles Kamerabild</figcaption>
</figure>
<figure class="calibration-crop-figure" hidden>
<img data-image="crop" alt="Geprüfter Bildausschnitt mit einzelnen Ziffernrahmen" decoding="async">
<figcaption>Geprüfter Ausschnitt <span class="calibration-preview-angle"></span></figcaption>
<p class="calibration-preview-reading"></p>
</figure>
</div>
<p class="calibration-preview-reason" hidden></p>
<p class="calibration-preview-help">Die App sucht in diesem Bild nach der Ziffernreihe.</p>
</details>"""

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
.main-menu{{display:flex;align-items:center;gap:.45rem;padding:.35rem;margin:0 0 1rem;border:1px solid var(--edge);border-radius:.85rem;background:var(--surface)}}
.main-tabs{{display:flex;flex:1;min-width:0;gap:.45rem}}
.main-tabs button{{flex:1;min-height:2.8rem;background:transparent;border-color:transparent;color:var(--muted)}}
.main-tabs button[aria-selected="true"]{{background:light-dark(#e7f0f5,#293b48);border-color:var(--edge);color:inherit}}
.main-guide{{display:flex;align-items:center;justify-content:center;align-self:stretch;padding:.45rem .65rem;border-radius:.55rem;color:inherit;font-size:.9rem}}
@media(max-width:400px){{.main-menu,.main-tabs{{gap:.2rem}}.main-tabs button,.main-guide{{padding-inline:.3rem}}}}
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
.automatic-interval-hint{{display:flex;align-items:center;gap:.6rem;margin:.6rem 0 1rem;color:var(--muted)}}
.automatic-interval-hint[hidden]{{display:none}}
.failure-recovery{{margin:.5rem 0;padding:.65rem .75rem;border:1px solid #b58b38;border-radius:.65rem;background:light-dark(#fff8df,#3b311d);color:light-dark(#704c08,#ffdf8a);font-size:.9rem}}
.failure-recovery[hidden]{{display:none}}
.reflection-suggestion{{margin:.65rem 0;color:var(--muted);font-size:.92rem}}
.reflection-actions{{display:flex;align-items:center;gap:.65rem;flex-wrap:wrap}}
.reflection-actions form{{display:inline}}
.reflection-settings{{padding:.75rem .9rem;border:1px solid var(--edge);border-radius:.65rem}}
.reflection-settings > label{{color:inherit;font-size:.95rem}}
.reflection-settings .help{{margin:.35rem 0 0 1.65rem}}
.reflection-estimate mark{{background:light-dark(#ffdc72,#ffcf53);color:#302100;font-weight:700;padding:0 .16em}}
.failure-recovery[data-state="waiting"]{{font-weight:650}}
.activity-status{{margin:.15rem 0 0;color:var(--muted);font-size:.9rem;overflow-wrap:anywhere}}
.activity-status[data-state="queued"], .activity-status[data-state="working"]{{margin:0 0 .75rem;padding:.7rem .85rem;border:1px solid var(--edge);border-radius:.75rem;color:inherit;font-size:1rem}}
.activity-status p{{margin:0}}
#setup-image-test{{margin:.4rem 0 .8rem}}
.setup-progress{{display:block;width:100%;height:.8rem;margin:.45rem 0;border:0;border-radius:99px;overflow:hidden;accent-color:#c28a25}}
.setup-progress[value]::-webkit-progress-bar{{background:light-dark(#eee6d1,#473d29)}}
.setup-progress[value]::-webkit-progress-value{{background:#c28a25;border-radius:99px}}
.setup-progress[hidden]{{display:none}}
.activity-status[data-offline="pending"]{{color:light-dark(#704c08,#ffdf8a)}}
.activity-status[data-offline="true"]{{color:light-dark(#8d282e,#ffc0c1);font-weight:650}}
.connection-status{{margin:.35rem 0;color:var(--muted);font-size:.9rem}}
.connection-status[data-state="connected"]{{color:light-dark(#155d39,#a2e5bc)}}
.connection-status[data-state="stale"]{{color:light-dark(#704c08,#ffdf8a)}}
.connection-status[data-state="error"]{{color:light-dark(#8d282e,#ffc0c1)}}
.paused-notice{{margin:0 0 1rem;padding:1rem;border:2px solid #c28a25;border-radius:.85rem;background:light-dark(#fff3c4,#453718);color:light-dark(#654400,#ffe29a);font-size:1.05rem}}
.paused-notice strong{{display:block;font-size:1.15rem;margin-bottom:.25rem}}
.paused-notice p{{margin:.15rem 0 .7rem}}
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
.wizard-crop-options{{margin:0;padding:0;border:0;min-width:0}}
.wizard-crop-options legend{{margin:0 0 .45rem;padding:0;font-size:.9rem}}
.wizard-crop-choices{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,10rem),1fr));gap:.5rem}}
.wizard-crop-choices label{{display:flex;align-items:center;gap:.5rem;padding:.65rem;border:1px solid var(--edge);border-radius:.55rem;cursor:pointer}}
.wizard-crop-choices label:has(:checked){{border-color:#65bcaf;color:inherit}}
.wizard-crop-choices input{{margin:0;min-height:auto;flex-shrink:0}}
.calibration-card{{display:block;border-color:light-dark(#83aaa2,#4b786e)}}
.calibration-card h2{{font-size:1.15rem}}
.calibration-card p{{margin:.55rem 0}}
.calibration-live{{padding:.75rem .9rem;margin:0 0 .8rem;border:1px solid var(--edge);border-radius:.7rem}}
.calibration-live p{{margin:0}}
#calibration-state[data-tone]:not([data-tone=""]){{padding:.75rem .9rem;border:1px solid;border-radius:.7rem}}
.calibration-live[data-tone="ok"],#calibration-state[data-tone="ok"]{{color:light-dark(#185d35,#9ce5b5);background:light-dark(#e9f8ee,#17382a);font-size:1.12rem;font-weight:750}}
.calibration-live[data-tone="error"],#calibration-state[data-tone="error"]{{color:light-dark(#86272d,#ffb6bb);background:light-dark(#fff0f0,#46252b);font-size:1.12rem;font-weight:750}}
.calibration-live progress,.calibration-card progress{{display:block;width:100%;margin:.55rem 0;accent-color:#bb861b}}
.calibration-card form{{margin-top:.75rem}}
#calibration-region{{padding:.75rem;border:1px solid var(--edge);border-radius:.65rem}}
#calibration-region summary{{font-weight:700;cursor:pointer}}
#calibration-open-region{{margin-top:.65rem}}
.calibration-photo-panel{{margin:.75rem 0 0;color:light-dark(#243b4b,#e5edf5);font-size:.9rem;font-weight:400}}
.calibration-photo-panel summary{{cursor:pointer;font-weight:650}}
.calibration-photo-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,17rem),1fr));gap:.8rem;margin:.7rem 0}}
.calibration-photo-grid figure{{margin:0;min-width:0}}
.calibration-photo-grid img{{display:block;max-width:100%;height:auto;border-radius:.4rem}}
.calibration-photo-frame{{position:relative;width:fit-content;max-width:100%}}
.calibration-crop-region{{position:absolute;border:2px solid #ffcd60;border-radius:.1rem;box-shadow:0 0 0 1px #151c23;pointer-events:none}}
.calibration-photo-grid figcaption{{margin-top:.35rem;color:var(--muted)}}
.calibration-photo-panel .calibration-preview-help{{font-size:.83rem;color:var(--muted);margin:.35rem 0 0}}
.calibration-photo-panel .calibration-preview-reading{{overflow-wrap:anywhere;font-weight:650;font-variant-numeric:tabular-nums;margin:.25rem 0 0}}
.source-mode-guide{{grid-column:1/-1;display:grid;gap:.75rem;grid-template-columns:repeat(auto-fit,minmax(min(100%,14rem),1fr))}}
.source-mode-guide ul{{padding-inline-start:1.25rem;margin:0}}
.source-mode-guide li + li{{margin-top:.35rem}}
.crop-draw{{grid-column:1/-1;padding:.85rem;border:1px solid var(--edge);border-radius:.65rem}}
.crop-draw > p{{margin:.3rem 0 .7rem}}
.crop-actions{{grid-column:1/-1;display:flex;flex-wrap:wrap;gap:.55rem}}
.crop-reset{{background:transparent}}
.crop-draw-image{{position:relative;max-width:700px;touch-action:none;user-select:none;cursor:crosshair}}
.crop-draw-image img{{display:block;width:100%;height:auto;pointer-events:none}}
.crop-live-preview{{margin:.85rem 0 0}}
.crop-live-preview figcaption{{margin:0 0 .4rem;color:var(--muted);font-size:.85rem}}
.crop-live-preview canvas{{display:block;max-width:100%;height:auto;border-radius:.5rem;background:#10161b}}
.digit-editor{{position:relative;display:table;max-width:100%;touch-action:none}}
.digit-layer{{position:absolute;inset:0}}
.digit-frame{{position:absolute;min-height:0;padding:0;border:1px solid #77d4cc;border-radius:0;background:#17383728;color:#fff;cursor:move;text-shadow:0 1px 3px #000}}
.digit-frame[data-active="true"]{{border-width:2px;z-index:1}}
.digit-frame span{{display:block;position:absolute;right:0;bottom:0;width:min(12px,44%);height:min(12px,42%);background:#77d4cc;cursor:nwse-resize}}
.crop-draw-outline{{position:absolute;box-sizing:border-box;border:3px solid #ffcf53;background:#ffcf5320;pointer-events:none}}
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
.yellow-key{{color:light-dark(#916509,#f1b836);font-weight:700}}
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
<nav class="main-menu" aria-label="Hauptmenü">
<div class="main-tabs" role="tablist" aria-label="Ansichten">
<button type="button" role="tab" id="tab-overview" aria-controls="view-overview" aria-selected="true">Übersicht</button>
<button type="button" role="tab" id="tab-settings" aria-controls="view-settings" aria-selected="false" tabindex="-1">Einstellungen</button>
</div>
<a id="open-user-guide" class="main-guide" href="https://github.com/Eifellayer/meter-ocr/blob/main/docs/Bedienungsanleitung-AI-Meter-Reader.pdf" target="_blank" rel="noopener noreferrer" title="Bebilderte Bedienungsanleitung (PDF)">Anleitung</a>
</nav>
<main>
<div class="tab-content" id="view-overview" role="tabpanel" aria-labelledby="tab-overview" {overview_hidden}>
<div class="panel" id="check-overview">
<div class="check-card-heading"><h2>Automatische Kontrolle</h2>
<div class="check-actions">
<button type="button" id="open-calibration" {calibration_hidden}>Selbsteinrichtung</button>
<button type="button" id="open-manual-settings">Test einstellen</button>
<button id="start-check" type="submit" form="manual-form">Test starten</button>
</div></div>
<div class="activity-status" data-state="{automatic_activity_state}">
<p role="status" aria-live="polite"><strong>Automatik:</strong> <span id="automatic-activity">{automatic_activity}</span></p>
<progress id="automatic-progress" class="setup-progress" aria-label="Fortschritt der automatischen Prüfung" {automatic_progress_hidden}></progress>
</div>
<div id="calibration-overview" class="calibration-live" hidden>
<p id="calibration-overview-state" role="status"></p>
<button type="button" id="calibration-open-region">Ziffernfeld manuell markieren</button>
<progress id="calibration-overview-progress" aria-label="Verstrichene Zeit der Selbsteinrichtung"></progress>
{calibration_preview_html}
</div>
{wizard_saved_notice}
<div class="paused-notice" id="paused-notice" {paused_notice_hidden} role="status" aria-live="polite"><strong>Automatik pausiert</strong><p>Es starten keine neuen automatischen Prüfungen. Ein bereits laufender Durchlauf darf noch enden. Manuelle Tests bleiben verfügbar.</p><form method="post" action="automatik-pause" id="resume-auto-form"><input type="hidden" name="lang" value="{language}"><input type="hidden" name="mode" value="{language_mode}"><input type="hidden" name="csrf" value="{csrf}"><input type="hidden" name="paused" value="0"><button type="submit">Automatik fortsetzen</button></form></div>
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
<div class="automatic-interval-hint" id="automatic-interval-hint" hidden><span>Wiederholte Fehlablesung? Ein kürzeres Prüfintervall kann helfen, wenn sich der Zähler nach einer Weile wieder klarer ablesen lässt.</span><button type="button" id="open-interval-settings">Prüfintervall ändern</button></div>
<form method="post" action="automatik-pause" id="pause-auto-form" {pause_button_hidden}><input type="hidden" name="lang" value="{language}"><input type="hidden" name="mode" value="{language_mode}"><input type="hidden" name="csrf" value="{csrf}"><input type="hidden" name="paused" value="1"><button type="submit">Automatik pausieren</button></form>
<p class="connection-status" id="source-connection" data-state="{source_connection_state}">Quelle: {source_connection}</p>
<dl><dt>Erkannter Stand</dt><dd id="automatic-ocr">{ocr}</dd>
<dt title="Stand aus der ersten Aufnahme oder aus einer externen Quelle">Vergleichswert</dt><dd><span id="automatic-reference">{reference}</span>
<small id="automatic-reference-note" class="reference-note" data-epoch="{reference_time}"
 data-fallback="{reference_is_fallback}" hidden></small></dd>
<dt>Bildzeit</dt><dd id="automatic-image-time" class="stamp" data-epoch="{image_time}">–</dd>
<dt>Letzte Prüfung</dt><dd id="automatic-last-check" class="stamp" data-epoch="{last_check}">–</dd>
<dt>Letzter bestätigter Abgleich</dt><dd id="automatic-last-match" class="stamp" data-epoch="{last_match}">–</dd>
<dt>Nächste Prüfung</dt><dd id="countdown">–</dd></dl>
<p class="failure-recovery" id="geometry-repair-warning" {geometry_warning_hidden}>{geometry_warning_text}</p>
<p class="failure-recovery" id="automatic-recovery" data-state="retrying" {recovery_hidden}>{recovery_notice}</p>
<p class="failure-recovery" id="reflection-live" hidden>
<strong>Vorläufig ergänzt</strong> <span id="reflection-live-reading"></span>
<small>Gelb markierte Ziffern sind berechnet. Der Wert dient der Orientierung.</small>
</p>
<div id="reflection-estimate" class="reflection-estimate" {reflection_estimate_hidden}>
<strong>Eindeutig ergänzter Zwischenstand</strong>
<p><span id="reflection-value-left">{reflection_left}</span><mark id="reflection-value-digit" title="Berechnete Ziffer">{reflection_digit}</mark><span id="reflection-value-right">{reflection_right}</span>
<small id="reflection-time" class="stamp" data-epoch="{reflection_time}"></small></p>
</div>
<div class="reflection-suggestion" id="reflection-approval" {reflection_approval_hidden}>
<p>Für eine unlesbare Ziffer gibt es einen eindeutigen Vorschlag. Wähle die Ziffer aus, um den Zwischenstand zu übernehmen.</p>
<form method="post" action="ergaenzte-ziffer-bestaetigen" class="reflection-actions">
<input type="hidden" name="lang" value="{language}"><input type="hidden" name="mode" value="{language_mode}">
<input type="hidden" name="csrf" value="{csrf}"><input type="hidden" id="reflection-approval-id" name="estimate_id" value="{reflection_approval_id}">
<label>Berechnete Ziffer
<select id="reflection-approval-digit" name="digit" required>
<option value="">Ziffer auswählen …</option>{reflection_digits_option}</select></label>
<button type="submit">Zwischenstand übernehmen</button>
</form></div>
<div id="reflection-suggestion" class="reflection-suggestion" {reflection_suggestion_hidden}>
<p>Dieselbe Ziffer ist wiederholt unlesbar. Bei Spiegelungen kannst du sie aus der vorherigen und der nächsten sicheren Ablesung ergänzen lassen.</p>
<div class="reflection-actions">
<button type="button" id="open-reflection-settings">Zur Einstellung</button>
<form method="post" action="spiegelungs-hinweis-ausblenden">
<input type="hidden" name="lang" value="{language}"><input type="hidden" name="mode" value="{language_mode}">
<input type="hidden" name="csrf" value="{csrf}">
<button type="submit">Vorschlag dauerhaft ausblenden</button>
</form></div></div>
<details class="ocr-details" id="automatic-ocr-details" hidden>
<summary>Mehr Infos: Was wurde bei den OCR-Versuchen gelesen?</summary>
<p class="ocr-scope"></p>
<p>? steht für eine unklare Ziffer.</p>
<table><thead><tr><th>Versuch</th><th>Erkannter Stand</th></tr></thead><tbody></tbody></table>
</details>
<details class="dashboard-help">
<summary>Stand im Home-Assistant-Dashboard anzeigen</summary>
<p>Wenn AI Meter Reader selbst aus einer ESPHome- oder Home-Assistant-Kamera liest, kannst du den Sensor „Zählerstand“ zum Dashboard hinzufügen. Seine Entitäts-ID lautet <code>sensor.rf1_ocr_zaehlerstand</code>.</p>
<p>Oder füge diese kurze YAML-Konfiguration in eine manuelle Karte ein:</p>
<pre><code>type: entity
entity: sensor.rf1_ocr_zaehlerstand
name: Zählerstand (OCR)</code></pre>
</details>
<details class="automatic-images" id="automatic-images" open><summary>Letztes Testbild</summary>
<p id="preview-empty" class="legend" {preview_empty_hidden}>Noch kein Testbild verfügbar.</p>
<div class="preview" id="test-preview" {automatic_preview_hidden}>
<h2 id="preview-heading">Letztes Testbild</h2>
<img id="test-preview-image"{automatic_preview_src} alt="Letztes Testbild">
<p class="legend" id="preview-legend" {preview_legend_hidden}><span class="green-key">Grün:</span> Ziffer gelesen · <span class="yellow-key">Gelb:</span> Ziffer schwankte zwischen OCR-Versuchen oder wurde aus mehreren Versuchen zusammengesetzt · <span class="red-key">Rot:</span> Ziffer weiterhin unklar. Die Farben zeigen OCR-Sicherheit, nicht die Übereinstimmung mit dem Referenzstand. Ohne automatisch erkannte Ziffernrahmen sind die Bereiche nur näherungsweise aufgeteilt.</p>
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
{manual_saved_notice}
<form method="post" action="pruefen" id="manual-form" enctype="multipart/form-data">
<input type="hidden" name="lang" value="{language}">
<input type="hidden" name="mode" value="{language_mode}">
<input type="hidden" name="csrf" value="{csrf}">
<input type="hidden" name="crop_revision" value="{manual_crop_revision}">
<label>Ziffernfarbe
<select name="polarity">{polarity_options}</select></label>
<label>Vergleichsgenauigkeit
<select name="decimals">{decimal_options}</select></label>
<label>Max. OCR-Versuche
<select name="attempts">{attempt_options}</select></label>
<label>Bildbereich
<select name="crop_mode" id="crop-mode">{crop_mode_options}</select></label>
<div class="crop-draw" id="crop-draw" hidden>
<p class="settings-note">Ziehe mit Maus oder Finger einen Rahmen um die gesamte Ziffernreihe.</p>
<div class="crop-draw-image" id="crop-draw-area" hidden>
<img alt="Originalbild zum Einstellen des Ausschnitts" draggable="false">
<span class="crop-draw-outline" hidden></span>
</div>
<figure class="crop-live-preview" hidden>
<figcaption>Vorschau mit Bilddrehung</figcaption>
<div class="digit-editor">
<canvas role="img" aria-label="Vorschau mit Bilddrehung"></canvas>
<div class="digit-layer"></div>
</div>
<p class="settings-note">Rahmen einzeln ziehen oder an der unteren Ecke vergrößern. Mit den Pfeiltasten verschieben, mit Umschalt und Pfeiltaste skalieren.</p>
<button type="button" class="clear-digit-boxes">Einzelrahmen zurücksetzen</button>
</figure>
<p class="settings-note" role="status">Kamerabild wird geladen …</p>
</div>
<div class="crop-fields" id="crop-fields" hidden>
<input type="hidden" name="digit_boxes" value="{manual_digit_boxes}">
<label>Manueller Ausschnitt (links, oben, rechts, unten)
<input name="crop" type="text" value="{crop_value}" maxlength="30" placeholder="52,56,564,132"></label>
<label>Bilddrehung (°)
<input name="rotation" type="number" min="-180" max="180" step="1" value="{rotation_value}"></label>
<label>Breite der Vorkommastellen
<input name="width" type="number" min="1" max="9999" value="{width_value}"></label>
<p class="settings-note">Wähle den Ausschnitt im Originalbild. Positive Winkel drehen nach rechts, negative nach links. Die Vorkommabreite gilt nach der Drehung.</p>
</div>
<label>Eigenes Testbild (optional, JPG oder PNG)
<input type="file" name="image" accept="image/jpeg,image/png"></label>
<p class="settings-note">Ein ausgewähltes Bild wird nur für diesen manuellen Test verwendet (max. 3 MB).</p>
<div class="crop-actions">
<button id="start-check-with-options" type="submit">Jetzt prüfen</button>
<button id="save-manual-crop" type="submit" name="save_settings" value="1" hidden>Ausschnitt und Drehung speichern</button>
<button type="button" id="reset-manual-crop" class="crop-reset" data-default-crop="{default_crop_value}"
        data-default-width="{default_crop_width}" hidden>Ausschnitt zurücksetzen</button>
</div>
</form>
<details class="help"><summary title="Informationen zum manuellen Bildtest">ⓘ Was passiert bei „Jetzt prüfen“?</summary>
<p>Die App verwendet das letzte vorhandene Zählerbild oder ein ausgewähltes eigenes JPG-/PNG-Testbild (bis 3 MB). Sie liest die Zahlen aus dem Bild und vergleicht sie mit dem Referenzwert. Sobald die Werte übereinstimmen, stoppt die Prüfung. Andernfalls werden höchstens so viele OCR-Versuche durchgeführt wie eingestellt (1–10). Der Test verändert die automatische Trefferzahl nicht.</p></details>
</div></details>
</div>
</div>
</div>
<div class="tab-content" id="view-settings" role="tabpanel" aria-labelledby="tab-settings" {settings_hidden}>
{reset_notice}
<section class="panel calibration-card" id="calibration-settings" aria-labelledby="calibration-title" {calibration_hidden}>
<h2 id="calibration-title" tabindex="-1">Selbsteinrichtung für Ausschnitt und Drehung</h2>
<p>Die App tastet sich mit unterschiedlichen Bildern an einen passenden Rahmen und Winkel heran. Nach drei bestätigten Ablesungen prüft sie den gefundenen Rahmen mit einem weiteren Bild und übernimmt ihn dann. Nach 15 Minuten endet der Versuch automatisch.</p>
<p>Ohne externen Vergleichswert hilft ein von Hand abgelesener Startwert. Ohne Startwert wartet die App zusätzlich auf einen plausiblen Zähleranstieg.</p>
{calibration_saved_notice}
<p id="calibration-state" role="status" hidden></p>
<button type="button" id="calibration-proposal" hidden>Gefundenen Rahmen im Test prüfen</button>
<progress id="calibration-progress" aria-label="Verstrichene Zeit der Selbsteinrichtung" hidden></progress>
{calibration_preview_html}
<form method="post" action="selbsteinrichtung">
<input type="hidden" name="lang" value="{language}">
<input type="hidden" name="mode" value="{language_mode}">
<input type="hidden" name="csrf" value="{csrf}">
<label id="calibration-limit-label">Höchstens so viele unterschiedliche Bilder
<input id="calibration-limit" name="image_limit" type="number" min="{calibration_min}" max="{calibration_max}" value="{calibration_limit}" required></label>
<p id="calibration-region-hint" hidden>Mehrere Ziffernfelder gefunden.
<button type="button" id="calibration-show-choices">Ziffernfelder ansehen</button></p>
<details class="setup-help" id="calibration-region">
<summary>Suchbereich im Kamerabild eingrenzen</summary>
<p>Ziehe einen Rahmen um das Ziffernfeld. Lass etwas Rand und spare die Seriennummer aus.</p>
<div class="crop-draw-image" id="calibration-region-picker" hidden>
<img id="calibration-region-image" alt="Kamerabild zur Auswahl des Suchbereichs" draggable="false">
<span class="crop-draw-outline" id="calibration-region-outline" hidden></span>
<div id="calibration-region-choices"></div>
</div>
<p id="calibration-region-empty" hidden>Kamerabild fehlt. Starte eine Prüfung oder die Selbsteinrichtung, um ein Bild zu laden.</p>
<input type="hidden" id="calibration-region-value" name="region">
<div class="crop-actions">
<button type="submit" name="action" value="start" id="calibration-guided-start" disabled>Im markierten Bereich suchen</button>
<button type="button" id="calibration-region-reset">Markierung löschen</button>
</div>
</details>
<div class="crop-actions">
<button id="calibration-start" type="submit" name="action" value="start">Selbsteinrichtung starten</button>
<button id="calibration-restore" type="submit" name="action" value="restore" formnovalidate {calibration_restore_hidden}>Gesicherten Ausschnitt wiederherstellen</button>
<button id="calibration-cancel" type="submit" name="action" value="cancel" formnovalidate hidden>Selbsteinrichtung stoppen</button>
</div>
</form>
</section>
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
<div class="source-mode-guide">
<label>Woher kommt das Zählerbild?<select name="source_mode" id="wizard-source-mode" required>{wizard_source_options}</select></label>
<ul class="settings-note" aria-label="Erklärung der Bildquellen">
<li><strong>ESPHome / Kamera:</strong> Empfohlen für den Einstieg mit einer Kamera. Die App liest den Stand selbst.</li>
<li><strong>Home-Assistant-Kamera mit Vergleichswert:</strong> Die App holt pro Prüfung ein Standbild und kann den Wert mit einem vorhandenen Sensor abgleichen.</li>
<li><strong>AI on the Edge / SLFork:</strong> Die App prüft den ESP-Messwert. Du kannst den ESP auch nur als Kamera verwenden.</li>
</ul>
</div>
<label id="wizard-discovered-sources" class="setup-help" hidden>In Home Assistant gefunden
<select id="wizard-discovered-source"><option value="">Gerät auswählen …</option></select></label>
<label id="wizard-source-url">ESP-Adresse<input name="url" value="{source_url}" maxlength="150" placeholder="http://esp-gaszaehler.local"></label>
<div id="wizard-esp-camera-only" class="setup-help" hidden>
<label class="check-option"><input type="checkbox" name="esp_camera_only" value="1" {esp_camera_only_checked}> ESP nur als Kamera verwenden</label>
<p>Wenn der ESP den Zähler nicht zuverlässig liest, kann die App das Bild direkt abrufen und selbst ablesen.</p>
</div>
<label id="wizard-source-camera">Home-Assistant-Kamera<input name="camera" value="{source_camera}" maxlength="80" placeholder="camera.gaszaehler"></label>
<label id="wizard-source-reference">Vergleichssensor (optional)<input name="reference" value="{source_reference}" maxlength="80" placeholder="sensor.gaszaehler"></label>
<div class="setup-help">
<label>Zählerstand kurz selbst ablesen (optional)<input name="fallback_value" value="{fallback_value}" inputmode="decimal" maxlength="16" placeholder="z. B. 12345,67"></label>
<p class="settings-note">Der Stand hilft der App beim Einrichten. Zum Überspringen leer lassen und auf „Weiter“ klicken.</p>
<button type="button" id="wizard-load-reading-image">Kamerabild zum Ablesen laden</button>
<p id="wizard-reading-image-status" role="status" hidden></p>
<img id="wizard-reading-image" alt="Zählerbild zum Ablesen" style="width:100%;max-width:42rem;height:auto;margin:.6rem 0" hidden>
<details><summary>Ablesezeit ändern</summary>
<label>Stand abgelesen am<input name="fallback_time" type="datetime-local" value="{fallback_time}"></label>
</details>
</div>
<details class="setup-help"><summary>ⓘ Hinweis zum Teststand</summary><p>Für reale Tests nutze ich ausschließlich AI on the Edge. Die übrigen Kamera- und Zählermodi sind bisher nur mit simulierten Bildern und automatisierten Tests geprüft.</p></details>
<div class="setup-controls"><span class="setup-count"></span><button type="button" class="setup-next">Weiter</button></div>
</fieldset>
<fieldset class="setup-step" data-step="1"><legend>2. Zähleranzeige</legend>
<label>Anzeigeart<select name="meter_display">{meter_display_options}</select></label>
<label>Ziffern vor dem Komma<select name="integer_digits">{integer_digit_options}</select></label>
<label>Nachkommastellen auf dem Zähler<select name="fraction_digits">{fraction_digit_options}</select></label>
<label>Verglichen wird bis<select name="decimals">{wizard_decimal_options}</select></label>
<div class="settings-note setup-help" data-precision-options {precision_hidden}>
<p>Die letzte Stelle kann beim Weiterdrehen schwer lesbar sein. Das kann zu Fehlmeldungen führen.</p>
<label class="check-option"><input type="checkbox" name="precision_mode" value="1" {precision_checked}> Präzisionsmodus: Alle drei Nachkommastellen müssen stimmen</label>
</div>
<p class="settings-note setup-help">Die Vergleichsgenauigkeit darf kleiner sein als die angezeigte Stellenzahl. Kleine Zeiger werden nicht automatisch gelesen; bei Rollen und Zeigern bitte nur die Ziffernrollen einstellen.</p>
<div class="setup-controls"><button type="button" class="setup-back">Zurück</button><span class="setup-count"></span><button type="button" class="setup-next">Weiter</button></div>
</fieldset>
<fieldset class="setup-step" data-step="2"><legend>3. Bildausschnitt und Prüfplan</legend>
<fieldset class="wizard-crop-options setup-help" id="wizard-crop-options">
<legend>Bildbereich</legend>
<div class="wizard-crop-choices">{wizard_crop_options}</div>
</fieldset>
<div id="wizard-calibration-options" class="setup-help" hidden>
<label>Höchstens so viele unterschiedliche Bilder
<input name="image_limit" type="number" min="{calibration_min}" max="{calibration_max}" value="{calibration_limit}" required disabled></label>
<p class="settings-note">Startet nach dem Speichern und endet spätestens nach 15 Minuten. Die App übernimmt den Rahmen nach drei Bestätigungen und einer abschließenden Gegenprüfung.</p>
</div>
<div class="setup-help">
<label class="check-option"><input type="checkbox" name="self_repair_enabled" value="1" {wizard_self_repair_checked}> Selbstreparatur bei wiederholten Fehlmessungen</label>
<p class="settings-note">Nach zehn unterschiedlichen Fehlmessungen sichert die App den bisherigen Rahmen und versucht einmal, ihn zu verbessern. Ohne sichere Gegenprobe bleibt der bisherige Rahmen gültig.</p>
</div>
<label>OCR-Versuche pro Bild<select name="attempts">{auto_attempt_options}</select></label>
<label>Ziffernfarbe<select name="polarity">{auto_polarity_options}</select></label>
<label>Prüfintervall (Minuten)<input type="number" name="interval_minutes" min="5" max="1440" value="{interval_minutes}" required></label>
<details class="setup-help"><summary>ⓘ Warum das Prüfintervall ändern?</summary><p>Nach einem fehlgeschlagenen automatischen Test folgen bis zu zwei weitere Prüfungen im Abstand von fünf Minuten. Sind alle drei erfolglos, wartet die App eine Stunde und prüft dann erneut. Nach Erfolg gilt wieder dein eingestelltes Intervall. Ein kürzeres Intervall kann helfen, wenn sich der Zähler beim Weiterdrehen vorübergehend schlecht lesen lässt.</p></details>
<label>Maximaler Durchfluss (m³/h)<input name="max_flow" type="text" inputmode="decimal" maxlength="10" value="{max_flow}" required></label>
<div class="crop-fields setup-help" id="wizard-crop-fields">
<label>Bildbereich (links, oben, rechts, unten)<input name="crop" value="{auto_crop_value}" maxlength="30" placeholder="52,56,564,132"></label>
<label>Bilddrehung (°)<input name="rotation" type="number" min="-180" max="180" step="1" value="{auto_rotation_value}"></label>
<label>Breite des Vorkomma-Bereichs in Pixeln<input name="width" type="number" min="1" max="9999" value="{auto_width_value}"></label>
</div>
<details class="setup-help"><summary>ⓘ Bild einrichten</summary><p>Die automatische Erkennung versucht, den Ziffernrahmen zu finden. Bei einer unsicheren Ablesung folgen bis zu zehn zusätzliche Bildauswertungen; die App setzt einzelne Ziffern nur bei einer strikten Mehrheit zusammen. Nach drei fehlgeschlagenen automatischen Prüfungen mit unterschiedlichen Bildabrufen wartet sie eine Stunde auf ein neues Bild oder einen höheren Zählerstand. Prüfe bei wiederholten Fehlern auch Beleuchtung, Abstand und Fokus. Beim Livebild kann AI Meter Reader bis zu 10 frische Standbilder innerhalb von höchstens 20 Sekunden prüfen.</p></details>
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
<div class="setup-controls"><button type="button" class="setup-back">Zurück</button><span class="setup-count"></span><button type="submit">Speichern und prüfen</button></div>
</fieldset>
<div id="setup-error" class="setup-warning" hidden></div>
<div id="setup-saving" hidden><p role="status">Einstellungen werden gespeichert …</p><progress class="setup-progress" aria-label="Einstellungen werden gespeichert …"></progress></div>
</form>

</div>
</dialog>
<details class="manual-panel settings-item" id="source-settings" {source_open}>
<summary><strong>Bildquelle</strong></summary>
<div class="manual-content">
{source_intro}
<form method="post" action="bildquelle" id="source-form">
<input type="hidden" name="lang" value="{language}">
<input type="hidden" name="mode" value="{language_mode}">
<input type="hidden" name="csrf" value="{csrf}">
<label title="Wähle, woher das Zählerbild und gegebenenfalls der Vergleichswert kommen.">Betriebsmodus
<select name="source_mode" id="source-mode" required>{source_options}</select></label>
<label id="source-url" title="Die Adresse deines ESP-Geräts im Heimnetz.">ESP-Adresse
<input name="url" value="{source_url}" placeholder="http://esp-gaszaehler.local" maxlength="150"></label>
<div id="esp-camera-only" hidden>
<label class="check-option"><input type="checkbox" name="esp_camera_only" value="1" {esp_camera_only_checked}> ESP nur als Kamera verwenden</label>
<p class="settings-note">Wenn der ESP den Zähler nicht zuverlässig liest, kann die App das Bild direkt abrufen und selbst ablesen.</p>
</div>
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
<form method="post" action="automatik" id="auto-form" data-saved-crop-mode="{saved_auto_crop_mode}">
<input type="hidden" name="lang" value="{language}">
<input type="hidden" name="mode" value="{language_mode}">
<input type="hidden" name="csrf" value="{csrf}">
<label>Vergleich
<select name="decimals">{auto_decimal_options}</select></label>
<div class="settings-note" data-precision-options {precision_hidden}>
<p>Die letzte Stelle kann beim Weiterdrehen schwer lesbar sein. Das kann zu Fehlmeldungen führen.</p>
<label class="check-option"><input type="checkbox" name="precision_mode" value="1" {precision_checked}> Präzisionsmodus: Alle drei Nachkommastellen müssen stimmen</label>
</div>
<label title="Nach einer unklaren Ablesung folgt ein zusätzlicher Versuch nach fünf Minuten. Schlägt auch der fehl, gilt wieder dieses Intervall.">Prüfintervall (Minuten)
<input name="interval_minutes" type="number" min="1" max="{max_interval_minutes}" value="{interval_minutes}" required>
<small {slfork_interval_hidden}>Bei AI on the Edge / SLFork liegen reguläre Prüfungen mindestens fünf Minuten auseinander.</small></label>
<label>Max. OCR-Versuche
<select name="attempts">{auto_attempt_options}</select></label>
<label title="Qmax steht auf deinem Zähler. Die Vorgabe für einen G4 beträgt 6 m³/h.">Maximaler Durchfluss (m³/h)
<input name="max_flow" type="text" inputmode="decimal" maxlength="10" value="{max_flow}" required></label>
<label>Ziffernfarbe
<select name="polarity">{auto_polarity_options}</select></label>
<details class="help setup-help">
<summary>ⓘ Automatik im Hintergrund verbessern</summary>
<label class="check-option"><input type="checkbox" name="fine_alignment_enabled" value="1" {fine_alignment_checked}> Ziffernrahmen langfristig feinjustieren</label>
<label class="check-option"><input type="checkbox" name="self_repair_enabled" value="1" {self_repair_checked}> Selbstreparatur bei wiederholten Fehlmessungen</label>
<p>Nach zehn unterschiedlichen Fehlmessungen sichert die App den bisherigen Rahmen und versucht einmal, ihn zu verbessern. Ohne sichere Gegenprobe bleibt der bisherige Rahmen gültig.</p>
<label class="check-option"><input type="checkbox" name="adaptive_interval_enabled" value="1" {adaptive_interval_checked}> Prüfintervall bei erwarteten Rollenwechseln verkürzen (SLFork)</label>
</details>
<div class="reflection-settings setup-help" id="reflection-settings">
<label class="check-option"><input type="checkbox" name="reflection_estimate_enabled" value="1" {reflection_enabled_checked}> Verdeckte Ziffern ergänzen</label>
<details class="help" id="reflection-settings-help">
<summary>ⓘ Spiegelungen und verdeckte Ziffern</summary>
<p>Die App kann je eine verdeckte Stelle vor und nach dem Komma ergänzen, wenn nur ein Ergebnis zum bisherigen Stand und zum maximalen Durchfluss passt. Berechnete Ziffern bleiben gelb. Ein datierter Startwert kann als erster Vergleichswert dienen.</p>
<label class="check-option"><input type="checkbox" name="reflection_suggestion_hidden" value="1" {reflection_hide_checked}> Vorschlag bei wiederholt unlesbarer Ziffer ausblenden</label>
</details>
</div>
<label>Bildbereich
<select name="crop_mode" id="auto-crop-mode">{auto_crop_mode_options}</select></label>
<div class="crop-draw" id="auto-crop-draw" hidden>
<p class="settings-note">Ziehe mit Maus oder Finger einen Rahmen um die gesamte Ziffernreihe.</p>
<div class="crop-draw-image" id="auto-crop-draw-area" hidden>
<img alt="Originalbild zum Einstellen des Ausschnitts" draggable="false">
<span class="crop-draw-outline" hidden></span>
</div>
<figure class="crop-live-preview" hidden>
<figcaption>Vorschau mit Bilddrehung</figcaption>
<div class="digit-editor">
<canvas role="img" aria-label="Vorschau mit Bilddrehung"></canvas>
<div class="digit-layer"></div>
</div>
<p class="settings-note">Rahmen einzeln ziehen oder an der unteren Ecke vergrößern. Mit den Pfeiltasten verschieben, mit Umschalt und Pfeiltaste skalieren.</p>
<button type="button" class="clear-digit-boxes">Einzelrahmen zurücksetzen</button>
</figure>
<p class="settings-note" role="status">Kamerabild wird geladen …</p>
</div>
<div class="crop-fields" id="auto-crop-fields" hidden>
<input type="hidden" name="digit_boxes" value="{automatic_digit_boxes}">
<label>Bildbereich (links, oben, rechts, unten)
<input name="crop" type="text" value="{auto_crop_value}" maxlength="30" placeholder="52,56,564,132"></label>
<label>Bilddrehung (°)
<input name="rotation" type="number" min="-180" max="180" step="1" value="{auto_rotation_value}"></label>
<label>Breite der Vorkommastellen
<input name="width" type="number" min="1" max="9999" value="{auto_width_value}"></label>
<p class="settings-note">Wähle den Ausschnitt im Originalbild. Die Vorkommabreite gilt nach der Drehung.</p>
</div>
<div class="crop-actions">
<button type="submit" id="save-auto-settings">Speichern</button>
<button type="submit" id="reset-auto-crop" class="crop-reset" form="reset-auto-crop-form"
        name="reset_crop" value="1" hidden>Ausschnitt zurücksetzen</button>
</div>
</form>
<form method="post" action="automatik" id="reset-auto-crop-form" hidden>
<input type="hidden" name="lang" value="{language}">
<input type="hidden" name="mode" value="{language_mode}">
<input type="hidden" name="csrf" value="{csrf}">
</form>
<div class="manual-content">
<h3>Fallback-Zählerstand</h3>
<p class="settings-note">Trage den selbst abgelesenen Stand und die Ablesezeit ein. Die App nutzt ihn als Startwert, solange noch keine sichere automatische Ablesung vorliegt.</p>
<form method="post" action="fallback" id="fallback-form">
<input type="hidden" name="lang" value="{language}">
<input type="hidden" name="mode" value="{language_mode}">
<input type="hidden" name="csrf" value="{csrf}">
<label>Fallback-Zählerstand (optional)<input name="fallback_value" value="{fallback_value}" inputmode="decimal" maxlength="16"></label>
<label>Stand abgelesen am<input name="fallback_time" type="datetime-local" value="{fallback_time}"></label>
<button type="submit">Fallback-Wert speichern</button>
</form>
{fallback_saved_notice}
</div>
<p class="settings-note">Nach zwei Fehlprüfungen mit kurzem Abstand gilt wieder dein eingestelltes Prüfintervall. Bei geänderter Vergleichsgenauigkeit beginnt die Trefferzählung neu.</p>
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
<p class="settings-note">Setzt die AI-Meter-Reader-Einstellungen und Prüfhistorie auf Standardwerte zurück und entfernt gespeicherte Testbilder. Die Home-Assistant-App-Konfiguration und vorhandenen Entitäten bleiben erhalten.</p>
<button type="button" id="open-reset">Auf Werkseinstellungen zurücksetzen</button>
</div></details>
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
<p id="reset-progress" class="settings-note" role="status" hidden>Werkreset angefordert. Eine laufende Prüfung kann den Reset verzögern. Bitte warte, bis sich die Einrichtung öffnet.</p>
</dialog>
</div>
</main>

<footer class="page-footer">Kostenloses Hobbyprojekt · <a href="https://www.paypal.com/donate/?hosted_button_id=FG4Q7VKQJ9BW8" target="_blank" rel="noopener noreferrer">Freiwillig mit PayPal unterstützen</a>
<details class="about-project"><summary>Über AI Meter Reader</summary><p><a href="https://github.com/Eifellayer" target="_blank" rel="noopener noreferrer">Projekt von EifelLayer auf GitHub</a></p><p>KI-unterstützt entwickelt. Keine geeichte Messung oder Gewähr für OCR-Ergebnisse. Bitte Zählerstände bei Bedarf direkt am Gerät prüfen.</p></details></footer>
<script>
let next = {next_check};
const lang = '{language}';
let automaticStatusFailures = 0;
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
const selectedTab = searchPrefs.get('ui');
const settingsOpen = selectedTab ? selectedTab === 'settings' :
  searchPrefs.get('saved') === 'crop' || settingsSections.some(selector => document.querySelector(selector).open);
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
  loadSourceSuggestions();
}});
document.querySelector('#open-calibration').addEventListener('click', () => {{
  activateTab('settings');
  document.querySelector('#calibration-title').focus({{preventScroll: true}});
  document.querySelector('#calibration-settings').scrollIntoView({{block: 'start'}});
}});
document.querySelector('#open-interval-settings').addEventListener('click', () => {{
  activateTab('settings');
  document.querySelector('#automatic-settings').open = true;
  document.querySelector('#automatic-settings').scrollIntoView({{behavior: 'smooth', block: 'start'}});
}});
document.querySelector('#open-reflection-settings').addEventListener('click', () => {{
  activateTab('settings');
  document.querySelector('#automatic-settings').open = true;
  const section = document.querySelector('#reflection-settings');
  document.querySelector('#reflection-settings-help').open = true;
  section.scrollIntoView({{block: 'nearest'}});
}});
const resetState = '{reset_state}';
if (resetState === 'done') localStorage.removeItem(setupDismissKey);
if (resetState === 'pending') {{
  setTimeout(() => location.reload(), 2000);
}} else if (searchPrefs.has('reset')) {{
  searchPrefs.delete('reset');
  history.replaceState(null, '', location.pathname + (searchPrefs.size ? '?' + searchPrefs : ''));
}}
if (setupDialog.dataset.firstRun === 'true' && localStorage.getItem(setupDismissKey) !== '1') {{
  activateTab('settings', false);
  setupDialog.showModal();
}}
const resetDialog = document.querySelector('#reset-dialog');
const resetForm = document.querySelector('#reset-form');
const resetProgress = document.querySelector('#reset-progress');
document.querySelector('#open-reset').addEventListener('click', () => resetDialog.showModal());
document.querySelector('#cancel-reset').addEventListener('click', () => resetDialog.close());
resetDialog.addEventListener('cancel', event => {{
  if (!resetProgress.hidden) event.preventDefault();
}});
resetForm.addEventListener('submit', event => {{
  if (!resetProgress.hidden) {{
    event.preventDefault();
    return;
  }}
  resetProgress.hidden = false;
  resetForm.querySelectorAll('button').forEach(button => button.disabled = true);
}});
const setupForm = document.querySelector('#setup-form');
const wizardReading = setupForm.elements.fallback_value;
const wizardReadingTime = setupForm.elements.fallback_time;
const wizardImage = document.querySelector('#wizard-reading-image');
const wizardImageButton = document.querySelector('#wizard-load-reading-image');
const wizardImageStatus = document.querySelector('#wizard-reading-image-status');
const wizardSourceFields = ['source_mode', 'url', 'camera', 'esp_camera_only'];
let wizardPreviewRevision = 0;
let wizardImageUrl = '';
function clearWizardImage() {{
  wizardPreviewRevision++;
  wizardImage.hidden = true;
  wizardImage.removeAttribute('src');
  if (wizardImageUrl) URL.revokeObjectURL(wizardImageUrl);
  wizardImageUrl = '';
  wizardImageStatus.hidden = true;
}}
for (const name of wizardSourceFields) setupForm.elements[name].addEventListener('input', clearWizardImage);
document.querySelector('#wizard-discovered-source').addEventListener('change', clearWizardImage);
wizardImageButton.addEventListener('click', async () => {{
  clearWizardImage();
  const revision = wizardPreviewRevision;
  const body = new URLSearchParams();
  for (const name of [...wizardSourceFields, 'csrf', 'lang', 'mode']) {{
    const field = setupForm.elements[name];
    if (field.type !== 'checkbox' || field.checked) body.set(name, field.value);
  }}
  wizardImageButton.disabled = true;
  wizardImageStatus.hidden = false;
  wizardImageStatus.textContent = 'Kamerabild wird geladen …';
  try {{
    const response = await fetch('einrichtungsbild', {{method: 'POST', body, cache: 'no-store'}});
    if (!response.ok) throw new Error();
    const image = await response.blob();
    if (revision !== wizardPreviewRevision) return;
    wizardImageUrl = URL.createObjectURL(image);
    wizardImage.src = wizardImageUrl;
    wizardImage.hidden = false;
    wizardImageStatus.hidden = true;
  }} catch (_) {{
    if (revision === wizardPreviewRevision)
      wizardImageStatus.textContent = 'Kein Kamerabild verfügbar. Prüfe die Bildquelle oder lies direkt am Zähler ab.';
  }} finally {{
    wizardImageButton.disabled = false;
  }}
}});
let wizardTimeEdited = false;
wizardReadingTime.addEventListener('input', () => {{ wizardTimeEdited = true; }});
wizardReading.addEventListener('input', () => {{
  if (wizardTimeEdited) return;
  const now = new Date(Date.now() - new Date().getTimezoneOffset() * 60000);
  wizardReadingTime.value = wizardReading.value.trim() ? now.toISOString().slice(0, 16) : '';
}});
setupForm.addEventListener('submit', event => {{
  const saving = document.querySelector('#setup-saving');
  if (!saving.hidden) {{
    event.preventDefault();
    return;
  }}
  saving.hidden = false;
  setupForm.querySelector('button[type="submit"]').disabled = true;
}});
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
  const url = document.querySelector('#wizard-source-url');
  const camera = document.querySelector('#wizard-source-camera');
  url.hidden = mode !== 'slfork';
  document.querySelector('#wizard-esp-camera-only').hidden = url.hidden;
  camera.hidden = mode !== 'esphome' && mode !== 'camera';
  url.querySelector('input').required = !url.hidden;
  camera.querySelector('input').required = !camera.hidden;
  document.querySelector('#wizard-source-reference').hidden = mode !== 'camera';
  const attemptChoice = setupForm.querySelector('[name="attempts"]');
  if (mode === 'camera' && previousWizardSource !== 'camera' && attemptChoice.value === '5') {{
    attemptChoice.value = '10';
  }}
  previousWizardSource = mode;
}}
wizardSourceMode.addEventListener('change', showWizardSource); showWizardSource();
const discoveredSource = document.querySelector('#wizard-discovered-source');
let sourceSuggestions = [];
let loadingSourceSuggestions = false;
async function loadSourceSuggestions() {{
  if (loadingSourceSuggestions || sourceSuggestions.length) return;
  loadingSourceSuggestions = true;
  try {{
    const response = await fetch('bildquellen', {{cache: 'no-store'}});
    if (!response.ok) return;
    sourceSuggestions = await response.json();
    sourceSuggestions.forEach((source, index) => {{
      const type = source.mode === 'slfork' ? 'AI on the Edge' : (lang === 'en' ? 'Camera' : 'Kamera');
      discoveredSource.add(new Option(type + ' · ' + source.label, String(index)));
    }});
    document.querySelector('#wizard-discovered-sources').hidden = !sourceSuggestions.length;
  }} catch (_) {{
    // Manual entry remains available when Home Assistant cannot return suggestions.
  }} finally {{
    loadingSourceSuggestions = false;
  }}
}}
discoveredSource.addEventListener('change', () => {{
  if (discoveredSource.value === '') return;
  const source = sourceSuggestions[Number(discoveredSource.value)];
  if (source.mode === 'slfork') {{
    wizardSourceMode.value = 'slfork';
    setupForm.elements.url.value = source.url;
  }} else {{
    if (wizardSourceMode.value !== 'camera') wizardSourceMode.value = 'esphome';
    setupForm.elements.camera.value = source.camera;
  }}
  showWizardSource();
}});
if (setupDialog.open) loadSourceSuggestions();
const wizardCropMode = setupForm.elements.crop_mode;
function showWizardCrop() {{
  const manual = wizardCropMode.value === 'manual';
  const learn = wizardCropMode.value === 'learn';
  const fields = document.querySelector('#wizard-crop-fields');
  fields.hidden = !manual;
  fields.querySelectorAll('input').forEach(input => input.disabled = !manual);
  document.querySelector('#wizard-calibration-options').hidden = !learn;
  setupForm.elements.image_limit.disabled = !learn;
}}
document.querySelector('#wizard-crop-options').addEventListener('change', showWizardCrop);
showWizardCrop();
setupForm.querySelector('[name="fraction_digits"]').addEventListener('change', event => {{
  const maximum = Number(event.target.value);
  const precision = setupForm.querySelector('[name="decimals"]');
  [...precision.options].forEach(option => option.disabled = Number(option.value) > maximum);
  if (Number(precision.value) > maximum) precision.value = String(maximum);
  precision.dispatchEvent(new Event('change'));
}});
document.querySelectorAll('[data-precision-options]').forEach(options => {{
  const select = options.closest('form').querySelector('[name="decimals"]');
  const showPrecisionOptions = () => {{ options.hidden = select.value !== '3'; }};
  select.addEventListener('change', showPrecisionOptions);
  showPrecisionOptions();
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
let lastManualCropResetTime = 0;

function cropEditor(form, panel, fields, reset, save, emptyText) {{
  const mode = form.elements.crop_mode;
  const crop = form.elements.crop;
  const rotation = form.elements.rotation;
  const area = panel.querySelector('.crop-draw-image');
  const image = area.querySelector('img');
  const outline = area.querySelector('span');
  const preview = panel.querySelector('.crop-live-preview');
  const canvas = preview.querySelector('canvas');
  const context = canvas.getContext('2d');
  const frameLayer = preview.querySelector('.digit-layer');
  const boxField = form.elements.digit_boxes;
  const digitCount = {crop_digit_count};
  let frameDrag = null;
  let previewRequest = 0;
  const status = panel.querySelector('[role="status"]');
  const upload = form.elements.image;
  let currentVersion = '';
  let manualVersion = '';
  let displayedUrl = '';
  let drawnCrop = null;
  let drag = null;

  function updateWidth(box) {{
    const [left, top, right, bottom] = box;
    const width = right - left;
    const height = bottom - top;
    const angle = Math.abs(Number(rotation.value)) % 180;
    const radians = angle * Math.PI / 180;
    const span = width * Math.abs(Math.cos(radians)) + height * Math.abs(Math.sin(radians));
    const turned = angle === 0 ? width : angle === 90 ? height :
      Math.ceil((width + span) / 2) - Math.floor((width - span) / 2);
    form.elements.width.value = Math.min(9999, Math.max(1, Math.round(turned * {crop_whole_ratio})));
  }}
  function currentDigitBoxes() {{
    const boxes = JSON.parse(boxField.value || '[]');
    if (boxes.length === digitCount) return boxes;
    const width = Number(form.elements.width.value);
    const total = Number(canvas.dataset.cropWidth);
    const edge = {crop_integer_digits};
    const whole = digitCount === edge ? 1000 : Math.max(edge * 12, Math.min(1000 - (digitCount - edge) * 12,
      Math.round(1000 * width / total)));
    const ends = Array.from({{length: digitCount + 1}}, (_, index) => index <= edge ?
      Math.round(whole * index / edge) : Math.round(whole + (1000 - whole) * (index - edge) / (digitCount - edge)));
    return ends.slice(1).map((right, index) => [ends[index], 0, right, 1000]);
  }}
  const frames = Array.from({{length: digitCount}}, (_, index) => {{
    const frame = document.createElement('button');
    frame.type = 'button';
    frame.className = 'digit-frame';
    frame.setAttribute('aria-label', 'Ziffernrahmen ' + (index + 1));
    frame.textContent = index + 1;
    const handle = document.createElement('span');
    handle.setAttribute('aria-hidden', 'true');
    frame.append(handle);
    frame.addEventListener('pointerdown', event => {{
      if (event.button !== 0 || frameDrag) return;
      event.preventDefault();
      frame.focus({{preventScroll: true}});
      frame.setPointerCapture(event.pointerId);
      frame.dataset.active = 'true';
      const rect = frameLayer.getBoundingClientRect();
      frameDrag = {{id: event.pointerId, index, resize: event.target === handle,
        x: event.clientX, y: event.clientY, width: rect.width, height: rect.height,
        original: currentDigitBoxes()}};
    }});
    frame.addEventListener('pointermove', event => {{
      if (frameDrag?.id !== event.pointerId) return;
      editDigitBox(frameDrag.original, index,
        Math.round((event.clientX - frameDrag.x) * 1000 / frameDrag.width),
        Math.round((event.clientY - frameDrag.y) * 1000 / frameDrag.height), frameDrag.resize);
    }});
    for (const type of ['pointerup', 'pointercancel', 'lostpointercapture']) frame.addEventListener(type, () => {{
      frameDrag = null;
      frame.dataset.active = 'false';
    }});
    frame.addEventListener('keydown', event => {{
      const arrows = {{ArrowLeft: [-10, 0], ArrowRight: [10, 0], ArrowUp: [0, -10], ArrowDown: [0, 10]}};
      const delta = arrows[event.key];
      if (!delta) return;
      event.preventDefault();
      editDigitBox(currentDigitBoxes(), index, ...delta, event.shiftKey);
    }});
    frameLayer.append(frame);
    return frame;
  }});
  function paintDigitBoxes(boxes) {{
    boxes.forEach(([left, top, right, bottom], index) => {{
      const style = frames[index].style;
      style.left = left / 10 + '%';
      style.top = top / 10 + '%';
      style.width = (right - left) / 10 + '%';
      style.height = (bottom - top) / 10 + '%';
    }});
  }}
  function editDigitBox(original, index, dx, dy, resize) {{
    const box = original[index];
    const [left, top, right, bottom] = box;
    const bound = (value, low, high) => Math.max(low, Math.min(high, value));
    const x = bound(dx, resize ? 10 - (right - left) : -left, 1000 - right);
    const y = bound(dy, resize ? 25 - (bottom - top) : -top, 1000 - bottom);
    const next = resize ? [left, top, right + x, bottom + y] : [left + x, top + y, right + x, bottom + y];
    const midpoint = next[0] + next[2];
    if ((index && midpoint <= original[index - 1][0] + original[index - 1][2]) ||
        (index + 1 < digitCount && midpoint >= original[index + 1][0] + original[index + 1][2])) return;
    const boxes = original.map((item, position) => position === index ? next : item);
    boxField.value = JSON.stringify(boxes);
    paintDigitBoxes(boxes);
  }}
  preview.querySelector('.clear-digit-boxes').addEventListener('click', () => {{
    boxField.value = '[]';
    paintDigitBoxes(currentDigitBoxes());
  }});
  function drawRotationPreview(left, top, right, bottom) {{
    const angle = Number(rotation.value) * Math.PI / 180;
    const width = right - left;
    const height = bottom - top;
    const turnedWidth = Math.ceil(width * Math.abs(Math.cos(angle)) + height * Math.abs(Math.sin(angle)));
    const turnedHeight = Math.ceil(width * Math.abs(Math.sin(angle)) + height * Math.abs(Math.cos(angle)));
    const scale = Math.min(1, 700 / turnedWidth, 420 / turnedHeight);
    canvas.width = Math.max(1, Math.round(scale * turnedWidth));
    canvas.height = Math.max(1, Math.round(scale * turnedHeight));
    canvas.dataset.rotation = rotation.value || '0';
    canvas.dataset.cropWidth = turnedWidth;
    context.translate(canvas.width / 2, canvas.height / 2);
    context.rotate(angle);
    context.drawImage(image, left, top, width, height,
      -width * scale / 2, -height * scale / 2, width * scale, height * scale);
    paintDigitBoxes(currentDigitBoxes());
    preview.hidden = false;
  }}
  function paint(box) {{
    const [left, top, right, bottom] = box;
    const w = image.naturalWidth;
    const h = image.naturalHeight;
    outline.hidden = !w || !h || box.length !== 4 || !box.every(Number.isFinite) ||
      left < 0 || top < 0 || left >= right || top >= bottom || right > w || bottom > h;
    cancelAnimationFrame(previewRequest);
    if (outline.hidden) {{ preview.hidden = true; return; }}
    previewRequest = requestAnimationFrame(() => drawRotationPreview(left, top, right, bottom));
    outline.style.left = left / w * 100 + '%';
    outline.style.top = top / h * 100 + '%';
    outline.style.width = (right - left) / w * 100 + '%';
    outline.style.height = (bottom - top) / h * 100 + '%';
  }}
  function paintSaved() {{ paint(crop.value.split(',').map(Number)); }}
  function loadImage() {{
    if (displayedUrl.startsWith('blob:')) URL.revokeObjectURL(displayedUrl);
    const file = upload?.files[0];
    displayedUrl = file ? URL.createObjectURL(file) : 'aktuell.jpg?v=' + encodeURIComponent(currentVersion || Date.now());
    area.hidden = true;
    preview.hidden = true;
    cancelAnimationFrame(previewRequest);
    status.hidden = false;
    status.textContent = 'Kamerabild wird geladen …';
    image.src = displayedUrl;
  }}
  image.addEventListener('load', () => {{
    area.hidden = false;
    status.hidden = true;
    paintSaved();
  }});
  image.addEventListener('error', () => {{
    if (upload && !upload.files[0] && manualVersion && !displayedUrl.startsWith('testbild.jpg')) {{
      displayedUrl = 'testbild.jpg?v=' + encodeURIComponent(manualVersion);
      image.src = displayedUrl;
      return;
    }}
    status.textContent = emptyText;
  }});
  function syncMode() {{
    const manual = mode.value === 'manual';
    panel.hidden = fields.hidden = !manual;
    reset.hidden = !manual && (!save || form.dataset.savedCropMode !== 'manual');
    if (save) save.textContent = manual ? 'Ausschnitt, Drehung und Einstellungen speichern' : 'Einstellungen speichern';
    else form.querySelector('#save-manual-crop').hidden = !manual;
    if (manual) loadImage();
  }}
  function rectangle(event) {{
    const rect = image.getBoundingClientRect();
    const point = (value, offset, size, pixels) => Math.round(Math.max(0, Math.min(pixels, (value - offset) * pixels / size)));
    const x = point(event.clientX, rect.left, rect.width, image.naturalWidth);
    const y = point(event.clientY, rect.top, rect.height, image.naturalHeight);
    return [Math.min(drag.x, x), Math.min(drag.y, y), Math.max(drag.x, x), Math.max(drag.y, y)];
  }}
  area.addEventListener('pointerdown', event => {{
    if (event.button !== 0 || drag || !image.naturalWidth) return;
    event.preventDefault();
    const rect = image.getBoundingClientRect();
    drag = {{id: event.pointerId,
      x: Math.round((event.clientX - rect.left) * image.naturalWidth / rect.width),
      y: Math.round((event.clientY - rect.top) * image.naturalHeight / rect.height)}};
    area.setPointerCapture(event.pointerId);
  }});
  area.addEventListener('pointermove', event => {{
    if (drag?.id === event.pointerId) paint(rectangle(event));
  }});
  area.addEventListener('pointerup', event => {{
    if (drag?.id !== event.pointerId) return;
    const box = rectangle(event);
    drag = null;
    if (box[2] - box[0] >= 8 && box[3] - box[1] >= 8) {{
      drawnCrop = box;
      crop.value = box.join(',');
      updateWidth(box);
    }}
    paintSaved();
  }});
  area.addEventListener('pointercancel', () => {{ drag = null; paintSaved(); }});
  rotation.addEventListener('input', () => {{
    if (drawnCrop && crop.value === drawnCrop.join(',')) updateWidth(drawnCrop);
    paintSaved();
  }});
  crop.addEventListener('input', paintSaved);
  form.elements.width.addEventListener('input', paintSaved);
  upload?.addEventListener('change', () => {{ if (!panel.hidden) loadImage(); }});
  mode.addEventListener('change', syncMode);
  if (!save) reset.addEventListener('click', () => {{
    drawnCrop = drag = null;
    lastManualCropResetTime = Date.now() / 1000;
    document.querySelector('#apply-crop-form').hidden = true;
    crop.value = reset.dataset.defaultCrop;
    form.elements.width.value = reset.dataset.defaultWidth;
    rotation.value = '0';
    boxField.value = '[]';
    mode.value = 'auto';
    syncMode();
    mode.focus();
  }});
  syncMode();
  return (version, testVersion = '') => {{
    if (version === currentVersion && testVersion === manualVersion) return;
    currentVersion = version;
    manualVersion = testVersion;
    if (!panel.hidden && area.hidden && !upload?.files[0]) loadImage();
  }};
}}
const updateManualCropImage = cropEditor(manualForm, document.querySelector('#crop-draw'),
  document.querySelector('#crop-fields'), document.querySelector('#reset-manual-crop'), null,
  'Kein Kamerabild verfügbar. Wähle ein eigenes Bild oder starte einen Test.');
const updateAutoCropImage = cropEditor(document.querySelector('#auto-form'), document.querySelector('#auto-crop-draw'),
  document.querySelector('#auto-crop-fields'), document.querySelector('#reset-auto-crop'),
  document.querySelector('#save-auto-settings'),
  'Kein Kamerabild verfügbar. Prüfe die Bildquelle oder warte auf die nächste automatische Prüfung.');
const sourceMode = document.querySelector('#source-mode');
function showSourceFields() {{
  const mode = sourceMode.value;
  document.querySelector('#esp-camera-only').hidden = mode !== 'slfork';
  for (const [selector, show] of [['#source-url', mode === 'slfork'],
      ['#source-camera', mode === 'esphome' || mode === 'camera'], ['#source-reference', mode === 'camera']]) {{
    const field = document.querySelector(selector);
    field.hidden = !show;
    field.querySelector('input').disabled = !show;
  }}
}}
sourceMode.addEventListener('change', showSourceFields);
showSourceFields();
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
const calibrationProposal = document.querySelector('#calibration-proposal');
let proposedCrop = null;
calibrationProposal.addEventListener('click', () => {{
  if (!proposedCrop) return;
  for (const name of ['crop_mode', 'crop', 'width', 'rotation']) manualForm.elements[name].value = proposedCrop[name];
  manualForm.elements.digit_boxes.value = JSON.stringify(proposedCrop.digit_boxes || []);
  manualForm.elements.crop_mode.dispatchEvent(new Event('change'));
  activateTab('overview');
  document.querySelector('#open-manual-settings').click();
}});

const regionDetails = document.querySelector('#calibration-region');
const regionPicker = document.querySelector('#calibration-region-picker');
const regionPhoto = document.querySelector('#calibration-region-image');
const regionOutline = document.querySelector('#calibration-region-outline');
const regionValue = document.querySelector('#calibration-region-value');
const regionStartButton = document.querySelector('#calibration-guided-start');
const regionEmpty = document.querySelector('#calibration-region-empty');
const regionChoices = document.querySelector('#calibration-region-choices');
const regionHint = document.querySelector('#calibration-region-hint');
document.querySelector('#calibration-open-region').addEventListener('click', () => {{
  activateTab('settings');
  regionDetails.open = true;
  showRegionPhoto();
  const summary = regionDetails.querySelector('summary');
  summary.scrollIntoView({{block: 'center'}});
  summary.focus({{preventScroll: true}});
}});
document.querySelector('#calibration-show-choices').addEventListener('click', () => {{
  regionDetails.open = true;
  showRegionPhoto();
  regionChoices.querySelector('button')?.focus();
}});
let recentCalibrationImage = '';
let recentCurrentImage = '';
let regionDrag = null;
function showRegionPhoto() {{
  if (!regionDetails.open || regionValue.value || regionDrag) return;
  const url = recentCalibrationImage || 'aktuell.jpg?v=' + encodeURIComponent(recentCurrentImage);
  if (regionPhoto.getAttribute('src') !== url) regionPhoto.src = url;
}}
regionPhoto.onload = () => {{ regionPicker.hidden = false; regionEmpty.hidden = true; }};
regionPhoto.onerror = () => {{
  const fallback = 'aktuell.jpg?v=' + encodeURIComponent(recentCurrentImage);
  if (regionPhoto.getAttribute('src') !== fallback) {{ regionPhoto.src = fallback; return; }}
  regionPicker.hidden = true;
  regionEmpty.hidden = false;
}};
regionDetails.addEventListener('toggle', showRegionPhoto);
function regionRect(event) {{
  const rect = regionPhoto.getBoundingClientRect();
  const axis = (value, origin, size) => Math.round(1000 * Math.max(0, Math.min(1, (value - origin) / size)));
  return [axis(event.clientX, rect.left, rect.width), axis(event.clientY, rect.top, rect.height)];
}}
function paintRegion(box) {{
  regionOutline.hidden = !box;
  if (!box) return;
  const [l, t, r, b] = box;
  ['left', 'top', 'width', 'height'].forEach((key, i) => {{
    regionOutline.style[key] = [l, t, r - l, b - t][i] / 10 + '%';
  }});
}}
function showRegionChoices(boxes) {{
  const values = regionValue.value || regionDrag ? [] : boxes || [];
  const key = JSON.stringify(values);
  if (key === regionChoices.dataset.boxes) return;
  regionChoices.dataset.boxes = key;
  regionChoices.replaceChildren();
  regionHint.hidden = !values.length;
  values.forEach(([l, t, r, b], index) => {{
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = String(index + 1);
    button.setAttribute('aria-label', 'Ziffernfeld auswählen ' + (index + 1));
    button.style.cssText = 'position:absolute;padding:0;border:2px solid #48b6ff;background:#05142188;min-height:0';
    Object.assign(button.style, {{left: l / 10 + '%', top: t / 10 + '%',
      width: (r - l) / 10 + '%', height: (b - t) / 10 + '%'}});
    button.addEventListener('pointerdown', event => event.stopPropagation());
    button.addEventListener('click', () => {{
      const box = [Math.max(0, l - 12), Math.max(0, t - 18), Math.min(1000, r + 12), Math.min(1000, b + 18)];
      regionValue.value = box.join(',');
      paintRegion(box);
      regionStartButton.disabled = false;
      regionStartButton.form.requestSubmit(regionStartButton);
    }});
    regionChoices.append(button);
  }});
}}
function selectedRegion(event) {{
  const [x, y] = regionRect(event);
  return [Math.min(x, regionDrag.x), Math.min(y, regionDrag.y), Math.max(x, regionDrag.x), Math.max(y, regionDrag.y)];
}}
regionPicker.addEventListener('pointerdown', event => {{
  if (event.button !== 0 || regionDrag) return;
  const [x, y] = regionRect(event);
  regionDrag = {{id: event.pointerId, x, y}};
  regionPicker.setPointerCapture(event.pointerId);
  event.preventDefault();
}});
regionPicker.addEventListener('pointermove', event => {{
  if (regionDrag?.id === event.pointerId) paintRegion(selectedRegion(event));
}});
regionPicker.addEventListener('pointerup', event => {{
  if (regionDrag?.id !== event.pointerId) return;
  const box = selectedRegion(event);
  regionDrag = null;
  if (box[2] - box[0] >= 20 && box[3] - box[1] >= 20) regionValue.value = box.join(',');
  paintRegion(regionValue.value ? regionValue.value.split(',').map(Number) : null);
  regionStartButton.disabled = !regionValue.value;
}});
regionPicker.addEventListener('pointercancel', () => {{
  regionDrag = null;
  paintRegion(regionValue.value ? regionValue.value.split(',').map(Number) : null);
}});
document.querySelector('#calibration-region-reset').addEventListener('click', () => {{
  regionValue.value = '';
  regionStartButton.disabled = true;
  paintRegion(null);
  showRegionPhoto();
}});

function refreshCalibrationImages(preview) {{
  const reasons = {{
    no_region: 'In diesem Bild wurde kein Ziffernbereich gefunden.',
    unreadable: 'Der Ausschnitt ließ sich nicht auswerten.',
    unclear: 'Mindestens eine benötigte Ziffer blieb unklar.',
    disagree: 'Die OCR-Versuche lieferten unterschiedliche Ziffern.',
    reference_unavailable: 'Kein gültiger Vergleichswert zu diesem Bild.',
    reference_mismatch: 'Der gelesene Stand weicht vom Vergleichswert ab.',
    position_error: 'Die Ziffernreihe scheint gegenüber der Referenz um eine Stelle verschoben.',
    implausible: 'Der Stand passt zeitlich nicht zur letzten sicheren Ablesung.',
    await_movement: 'Der Rahmen ist lesbar. Die App wartet auf einen plausiblen Zähleranstieg.',
    accepted: 'Dieser Rahmen wurde auf dem aktuellen Bild bestätigt.',
    verified: 'Die abschließende Gegenprobe war erfolgreich.',
  }};
  for (const section of document.querySelectorAll('.calibration-photo-panel')) {{
    section.hidden = !preview?.frame;
    if (section.hidden) continue;
    const frame = section.querySelector('[data-image="frame"]');
    const crop = section.querySelector('[data-image="crop"]');
    const region = section.querySelector('.calibration-crop-region');
    const hasCrop = Boolean(preview.crop);
    section.querySelector('.calibration-crop-figure').hidden = !hasCrop;
    for (const [kind, img] of [['frame', frame], ['crop', crop]]) {{
      const revision = preview[kind];
      if (!revision) continue;
      const url = 'lernvorschau.jpg?bild=' + kind + '&v=' + encodeURIComponent(revision);
      if (img.getAttribute('src') !== url) {{
        img.hidden = true;
        img.onload = () => {{ img.hidden = false; }};
        img.onerror = () => {{ img.hidden = true; img.removeAttribute('src'); }};
        img.src = url;
      }}
    }}
    region.hidden = !hasCrop || !Array.isArray(preview.region);
    if (!region.hidden) {{
      ['left', 'top', 'width', 'height'].forEach((part, index) => {{
        region.style[part] = preview.region[index] * 100 + '%';
      }});
    }}
    section.querySelector('.calibration-preview-angle').textContent = hasCrop ? ' · ' + preview.angle + '°' : '';
    section.querySelector('.calibration-preview-reading').textContent = preview.reading ?
      'OCR gelesen: ' + preview.reading : 'Ziffern werden gelesen …';
    const reason = section.querySelector('.calibration-preview-reason');
    reason.textContent = reasons[preview.reason] || '';
    reason.hidden = !reason.textContent;
    section.querySelector('.calibration-preview-help').textContent = !hasCrop ?
      (reason.hidden ? 'Die App sucht in diesem Bild nach der Ziffernreihe.' : '') : preview.reading ?
      'Grün: gelesen. Gelb: OCR-Versuche weichen ab. Rot: unklar.' :
      'Die blauen Rahmen zeigen, welche Stellen die App gerade prüft.';
    if (hasCrop && preview.method === 'neighbours') section.querySelector('.calibration-preview-help').append(
      ' Die Rahmen wurden aus sichtbaren Ziffern und ihren Abständen abgeleitet.');
    else if (hasCrop && preview.approximate) section.querySelector('.calibration-preview-help').append(
      ' Die Position der Ziffernrahmen ist angenähert.');
  }}
}}

function refreshCalibration(status) {{
  refreshCalibrationImages(status?.preview);
  if (!status) return;
  const active = status.state === 'waiting' || status.state === 'testing';
  const label = document.querySelector('#calibration-state');
  const progress = document.querySelector('#calibration-progress');
  label.hidden = false;
  const messages = {{
    waiting: 'Warte auf ein neues Kamerabild …',
    testing: 'Prüfe Ausschnitt und Drehung …',
    saved: 'Erfolgreich eingerichtet. Ausschnitt und Drehung sind übernommen.',
    failed: 'Selbsteinrichtung fehlgeschlagen. Prüfe Bildausschnitt, Kamerawinkel und Beleuchtung.',
    image_timeout: 'Kein neues Kamerabild erhalten. Prüfe die Bildquelle.',
    timeout: status.automatic ? 'Nachjustierung nach vier Minuten beendet. Der bisherige Rahmen bleibt gültig.' :
      'Selbsteinrichtung nach 15 Minuten beendet. Keine Einstellung sicher bestätigt.',
    cancelled: 'Selbsteinrichtung gestoppt.',
    save_failed: 'Ausschnitt und Drehung konnten nicht gespeichert werden.',
  }};
  const clock = Math.floor(status.seconds / 60) + ':' + String(status.seconds % 60).padStart(2, '0');
  const stages = {{
    queued: 'Selbsteinrichtung startet, sobald die laufende Prüfung beendet ist …',
    capture: 'Kamerabild wird abgerufen …',
    search: 'Grobkalibrierung: Suche nach der Ziffernreihe …',
    angle: 'Drehung wird geprüft. Der Winkel steht am Vorschaubild.',
    refine: status.preview?.weak_positions?.length ?
      'Einzelziffernsuche. Offene Stellen von links: ' + status.preview.weak_positions.join(', ') + '.' :
      'Feinkalibrierung: Prüfe Rahmen und Drehung am vorhandenen Bild …',
    verify_wait: 'Rahmen gefunden. Warte auf ein frisches Bild zur Gegenprüfung …',
    verify: 'Gefundenen Rahmen mit der normalen Prüfung gegenprüfen …',
    ocr: status.preview?.crop && status.preview.angle !== status.rotation ?
      'Prüfe den nächsten Rahmen …' :
      'Prüfe Rahmen ' + status.variant + ' mit Drehung ' + status.rotation + '° …',
  }};
  const reason = status.preview?.reason;
  let message = active && stages[status.stage] ? stages[status.stage] : messages[status.state] || '';
  if (status.state === 'waiting' && status.stage !== 'queued') {{
    if (reason === 'await_movement') {{
      message = 'Ziffernfeld lesbar. Die App wartet auf einen höheren Zählerstand oder einen abgelesenen Startwert.';
    }} else if (status.confirmations > 0) {{
      message = 'Ziffernfeld bestätigt. Die App prüft mit dem nächsten neuen Bild weiter.';
    }} else if (reason === 'no_region') {{
      message = status.tested >= 2 ?
        'Ziffernfeld nicht gefunden. Grenze das Ziffernfeld im Kamerabild ein.' :
        'Noch kein Ziffernbereich gefunden. Warte auf ein neues Bild …';
    }} else if (reason === 'reference_unavailable') {{
      message = 'Kein gültiger Vergleichswert für dieses Bild. Die App wartet auf eine neue Messung.';
    }}
  }}
  if (status.state === 'failed' && ['reference_mismatch', 'position_error'].includes(reason)) {{
    message = 'Der gelesene Bereich passt nicht zum Vergleichswert. Prüfe den Vergleichswert und markiere das Ziffernfeld.';
  }}
  const detail = 'Bilder geprüft: ' + status.tested +
    ' · Rahmen getestet: ' + status.attempts +
    ' · Bestätigungen: ' + status.confirmations + '/' + status.required +
    (active ? ' · Rechenzeit übrig: ' + clock + ' min' : '');
  const tone = status.state === 'saved' ? 'ok' : ['failed', 'timeout', 'image_timeout', 'save_failed'].includes(status.state) ? 'error' : '';
  label.textContent = (status.automatic ? 'Automatische Nachjustierung · ' : '') + message + ' ' + detail;
  label.dataset.tone = tone;
  document.querySelector('#calibration-overview').dataset.tone = tone;
  document.querySelector('#calibration-overview').hidden = false;
  document.querySelector('#calibration-overview-state').textContent = label.textContent;
  document.querySelector('.activity-status').hidden = active;
  for (const bar of [progress, document.querySelector('#calibration-overview-progress')]) {{
    bar.hidden = !active;
    bar.max = status.duration;
    const elapsed = status.duration - status.seconds;
    if (elapsed > 0) bar.value = elapsed;
    else bar.removeAttribute('value');
  }}
  if (status.state === 'saved' && status.settings?.crop_revision &&
      manualForm.elements.crop_revision.value !== status.settings.crop_revision) {{
    const autoForm = document.querySelector('#auto-form');
    for (const form of [autoForm, manualForm]) {{
      for (const name of ['crop_mode', 'crop', 'width', 'rotation']) form.elements[name].value = status.settings[name];
      form.elements.digit_boxes.value = JSON.stringify(status.settings.digit_boxes || []);
      if (form === autoForm) form.dataset.savedCropMode = status.settings.crop_mode;
      form.elements.crop_mode.dispatchEvent(new Event('change'));
    }}
    manualForm.elements.crop_revision.value = status.settings.crop_revision;
  }}
  document.querySelector('#calibration-limit-label').hidden = active;
  proposedCrop = status.proposal || null;
  calibrationProposal.hidden = !proposedCrop;
  document.querySelector('#calibration-start').hidden = active;
  document.querySelector('#calibration-cancel').hidden = !active;
}}
async function refreshTestStatus() {{
  if (statusPending || sendingCheck) return;
  statusPending = true;
  try {{
    const response = await fetch('status?lang=' + lang, {{cache: 'no-store'}});
    if (!response.ok) throw new Error();
    const job = await response.json();
    if (sendingCheck) return;
    const frameRevision = job.calibration?.preview?.frame;
    recentCalibrationImage = frameRevision ? 'lernvorschau.jpg?bild=frame&v=' + encodeURIComponent(frameRevision) : '';
    recentCurrentImage = job.current_image || '';
    showRegionPhoto();
    showRegionChoices(job.calibration?.preview?.regions);
    refreshCalibration(job.calibration);
    const calibrating = ['waiting', 'testing'].includes(job.calibration?.state);
    document.querySelector('#calibration-restore').hidden = !job.calibration_backup || calibrating;
    const bar = document.querySelector('#test-progress');
    const detail = document.querySelector('#test-result');
    const preview = document.querySelector('#test-preview');
    const previewImage = document.querySelector('#test-preview-image');
    const previewEmpty = document.querySelector('#preview-empty');
    const previewLegend = document.querySelector('#preview-legend');
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
      job.phase === 'done' && outcome === 'match_with_warning' ? 'Test bestanden mit Hinweis' :
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
    updateManualCropImage(job.current_image, job.manual_source_image);
    updateAutoCropImage(job.current_image);
    const automaticVersion = job.automatic_preview || job.current_image;
    const showManual = job.phase === 'done' && job.preview &&
      (!automaticVersion || job.checked_at * 1e9 >= Number(automaticVersion));
    const marked = showManual || Boolean(job.automatic_preview);
    const version = showManual ? job.checked_at : automaticVersion;
    const file = showManual ? 'testvorschau.jpg' : job.automatic_preview ? 'automatikvorschau.jpg' : 'aktuell.jpg';
    previewLegend.hidden = !marked;
    if (!version) {{
      preview.hidden = true;
      previewEmpty.hidden = false;
      previewImage.removeAttribute('src');
    }} else {{
      const url = file + '?v=' + encodeURIComponent(String(version));
      previewImage.onload = () => {{ preview.hidden = false; previewEmpty.hidden = true; }};
      previewImage.onerror = () => {{ preview.hidden = true; previewEmpty.hidden = false; }};
      if (previewImage.getAttribute('src') !== url) {{
        previewImage.setAttribute('src', url);
        if (showManual) automaticImages.open = true;
      }}
    }}
    apply.hidden = !(job.phase === 'done' && job.can_apply_crop && job.checked_at > lastManualCropResetTime);
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
document.querySelector('#setup-image-test')?.addEventListener('click', () => {{
  document.querySelector('#open-manual-settings').click();
  manualForm.querySelector('[name="image"]').focus();
}});
manualTestArea.hidden = testBox.hidden;
const testRequest = searchPrefs.get('test');
if (['queued', 'open', 'busy'].includes(testRequest)) {{
  manualTestArea.hidden = false;
  if (testRequest === 'open') manualPanel.open = true;
  else if (!testBox.hidden) testBox.focus();
  searchPrefs.delete('test');
  history.replaceState(null, '', location.pathname + (searchPrefs.size ? '?' + searchPrefs : ''));
}}
manualForm.addEventListener('submit', event => {{
  if (event.submitter?.name === 'save_settings') return;
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
  let refreshDelay = 15000;
  try {{
    const response = await fetch('automatic?lang=' + lang, {{cache: 'no-store'}});
    if (!response.ok) throw new Error();
    const sample = await response.json();
    automaticStatusFailures = 0;
    next = sample.next_check;
    document.querySelector('#paused-notice').hidden = !sample.paused;
    document.querySelector('#pause-auto-form').hidden = sample.paused;
    automaticBanner.dataset.tone = sample.tone;
    automaticBanner.dataset.incident = sample.incident;
    document.querySelector('#automatic-interval-hint').hidden = !(sample.failure_attempts > 0 && sample.tone !== 'ok');
    ignoreWarning.hidden = !sample.incident;
    const heading = document.querySelector('#automatic-status-heading');
    const icon = automaticBanner.querySelector('.automatic-banner-icon');
    const detail = document.querySelector('#automatic-result');
    if (heading.textContent !== sample.heading) heading.textContent = sample.heading;
    if (icon.textContent !== sample.icon) icon.textContent = sample.icon;
    if (detail.textContent !== sample.detail) detail.textContent = sample.detail;
    updateBannerVisibility();
    document.querySelector('#automatic-ocr').textContent = sample.ocr;
    const activityStatus = document.querySelector('.activity-status');
    activityStatus.dataset.offline = 'false';
    activityStatus.dataset.state = sample.activity_state;
    const activityText = document.querySelector('#automatic-activity');
    if (activityText.textContent !== sample.activity) activityText.textContent = sample.activity;
    const progress = document.querySelector('#automatic-progress');
    progress.hidden = !['queued', 'working'].includes(sample.activity_state);
    if (!progress.hidden) {{
      refreshDelay = 2000;
      if (sample.activity_total > 0 && sample.activity_completed != null) {{
        progress.max = sample.activity_total;
        progress.value = sample.activity_completed;
      }} else {{
        progress.removeAttribute('value');
      }}
    }} else if (!sample.paused && next) {{
      refreshDelay = Math.min(15000, Math.max(1000, next * 1000 - Date.now()));
    }}
    const geometryStatus = document.querySelector('#geometry-repair-warning');
    geometryStatus.hidden = !sample.geometry_warning;
    geometryStatus.textContent = sample.geometry_warning;
    const recovery = document.querySelector('#automatic-recovery');
    recovery.hidden = !sample.failure_attempts;
    recovery.dataset.state = sample.retry_suppressed ? 'waiting' : 'retrying';
    recovery.textContent = sample.recovery_notice;
    const live = sample.reflection_live_estimate;
    document.querySelector('#reflection-live').hidden = !live;
    if (live) {{
      const reading = document.querySelector('#reflection-live-reading');
      reading.replaceChildren(...Array.from(live.reading, (digit, index) => {{
        if (!live.positions.includes(index)) return document.createTextNode(digit);
        const mark = document.createElement('mark');
        mark.textContent = digit;
        return mark;
      }}));
    }}
    const estimate = sample.reflection_estimate;
    const pendingEstimate = estimate && !estimate.confirmed;
    const approvalId = document.querySelector('#reflection-approval-id');
    const approvalDigits = document.querySelector('#reflection-approval-digit');
    document.querySelector('#reflection-approval').hidden = !pendingEstimate;
    if (pendingEstimate && approvalId.value !== estimate.id) {{
      approvalId.value = estimate.id;
      approvalDigits.options.length = 1;
      approvalDigits.add(new Option(estimate.digit, estimate.digit));
      approvalDigits.value = '';
    }}
    document.querySelector('#reflection-suggestion').hidden = !sample.reflection_suggestion;
    document.querySelector('#reflection-estimate').hidden = !estimate?.confirmed;
    if (estimate?.confirmed) {{
      document.querySelector('#reflection-value-left').textContent = estimate.left;
      document.querySelector('#reflection-value-digit').textContent = estimate.digit;
      document.querySelector('#reflection-value-right').textContent = estimate.right;
      document.querySelector('#reflection-time').textContent = formatStamp(estimate.time);
    }}
    document.querySelector('#source-connection').textContent = 'Quelle: ' + sample.source_connection;
    document.querySelector('#source-connection').dataset.state = sample.source_connection_state;
    document.querySelector('#automatic-reference').textContent = sample.reference;
    renderReferenceNote('automatic', sample.reference_time, sample.reference_is_fallback);
    renderAttempts(document.querySelector('#automatic-ocr-details'), sample.readings, sample.decimals);
    for (const [id, value] of [['image-time', sample.image_time], ['last-check', sample.last_check],
        ['last-match', sample.last_match]]) {{
      document.querySelector('#automatic-' + id).textContent = value ? formatStamp(value) : '–';
    }}
  }} catch (_) {{
    automaticStatusFailures += 1;
    const status = document.querySelector('.activity-status');
    document.querySelector('#automatic-progress').hidden = true;
    status.dataset.state = 'unknown';
    const unavailable = automaticStatusFailures >= 3;
    status.dataset.offline = unavailable ? 'true' : 'pending';
    document.querySelector('#automatic-activity').textContent = lang === 'en'
      ? unavailable
        ? 'App status has not responded for about 45 seconds. Retrying…'
        : 'App status refresh failed temporarily. Retrying…'
      : unavailable
        ? 'Der App-Status antwortet seit etwa 45 Sekunden nicht. Neuer Versuch läuft …'
        : 'Statusaktualisierung kurz fehlgeschlagen. Neuer Versuch läuft …';
  }}
  setTimeout(refreshAutomatic, refreshDelay);
}}
refreshAutomatic();
</script></html>"""


def editable_rotation(values):
    angle = values.get("rotation", 0)
    if type(angle) is not int:
        return 0
    return -90 if angle == 270 else angle if -180 <= angle <= 180 else 0
POLARITIES = {"auto": "Automatisch", "light": "Hell", "dark": "Dunkel"}
DECIMALS = {"0": "Volle Kubikmeter", "1": "1 Nachkommastelle", "2": "2 Nachkommastellen", "3": "3 Nachkommastellen"}
ATTEMPTS = {str(value): str(value) for value in range(1, 11)}
CROP_MODES = {"auto": "Automatisch erkennen", "manual": "Rahmen ziehen"}
POLARITIES_EN = {"auto": "Automatic", "light": "Light digits", "dark": "Dark digits"}
DECIMALS_EN = {"0": "Whole cubic meters", "1": "1 decimal place",
               "2": "2 decimal places", "3": "3 decimal places"}
CROP_MODES_EN = {"auto": "Detect automatically", "manual": "Draw a frame"}


def select_options(choices, chosen):
    return "".join(
        f'<option value="{value}"{" selected" if value == chosen else ""}>{label}</option>'
        for value, label in choices.items()
    )


def fallback_options(value, stamp, decimals, integer_digits, fraction_digits):
    value, stamp = value.strip(), stamp.strip()
    if not value:
        return "", ""
    reading = re.fullmatch(r"([0-9]{1,9})(?:[.,]([0-9]{1,3}))?", value)
    if (not reading or len(reading[2] or "") > fraction_digits
            or meter_prefix(value, decimals, integer_digits) is None
            or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}", stamp)):
        raise ValueError("Fallback-Wert und Ablesezeit passen nicht zur Zähleranzeige.")
    datetime.fromisoformat(stamp)
    return value, stamp


def radio_options(name, choices, chosen):
    return "".join(
        f'<label><input type="radio" name="{name}" value="{value}"'
        f'{" checked" if value == chosen else ""}>{label}</label>'
        for value, label in choices.items()
    )


def start_panel(
    history_path, current_image, good_image, requested, default_decimals, default_attempts,
    get_auto_rules, save_auto_rules, default_crop, default_width, test_image,
    load_language_modes, save_language_modes, get_delivery, save_delivery, get_source, save_source,
    wake_worker=None, *, address=("0.0.0.0", 8099), test_source_image=None, automatic_preview=None,
    request_factory_reset=None, get_reset_status=None, skip_setup=None, get_activity=None,
    get_auto_paused=None, save_auto_paused=None, discover_sources=None,
    settings_lock=None, get_calibration=None, control_calibration=None, get_calibration_image=None,
    has_calibration_backup=None, get_wizard_image=None,
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
    rules_lock = settings_lock if settings_lock is not None else Lock()
    delivery_lock = Lock()
    wizard_image_lock = Lock()
    def read_auto_rules():
        return {"integer_digits": 5, "fraction_digits": 3, "meter_display": "rollers",
                "fallback_value": "", "fallback_time": "", "digit_boxes": [], **get_auto_rules()}

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
    source_lock = settings_lock if settings_lock is not None else Lock()
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
            try:
                requested.get_nowait()
            except Empty:
                pass
            progress.update(
                request_id=progress["request_id"] + 1, phase="idle",
                message="Noch kein manueller Test gestartet.", attempts=0,
                started_at=0, checked_at=0, outcome=None, detail="", preview=False,
                can_apply_crop=False, readings=[], ocr=None, reference=None,
                reference_time=None, reference_is_fallback=False, image_time=None,
            )

    def read_history():
        try:
            history = json.loads(history_path.read_text(encoding="utf-8"))
            return history if isinstance(history, dict) else {}
        except (OSError, ValueError):
            return {}

    def image_version(path):
        if path is None:
            return None
        try:
            return path.stat().st_mtime_ns
        except FileNotFoundError:
            return None

    def reflection_result(history, auto_rules):
        estimate = history.get("reflection_estimate")
        if not estimate or not auto_rules.get("reflection_estimate_enabled", False):
            return None
        estimate_id = f"{estimate['time']}:{estimate['left']}{estimate['digit']}{estimate['right']}"
        return {**estimate, "id": estimate_id, "confirmed": auto_rules.get("reflection_confirmed_id") == estimate_id}

    def geometry_warning(history, auto_rules, language):
        recovery = history.get("geometry_recovery", {})
        if recovery.get("scheduled_at"):
            message = "Zehn Fehlmessungen. Bitte Bildausschnitt prüfen."
            return EN_UI[message] if language == "en" else message
        failures = recovery.get("failures", 0)
        if not failures:
            return ""
        if not auto_rules.get("self_repair_enabled"):
            message = "Automatische Neukalibrierung ist ausgeschaltet."
            return EN_UI[message] if language == "en" else message
        remaining = GEOMETRY_REPAIR_FAILURES - failures
        if language == "en":
            return f"Automatic recalibration after {remaining} more failed readings." if remaining != 1 else "Automatic recalibration after one more failed reading."
        return f"Neukalibrierung nach {remaining} weiteren Fehlmessungen." if remaining != 1 else "Neukalibrierung nach einer weiteren Fehlmessung."

    def automatic_summary(history, language, auto_rules):
        reschedule_next_check(history, auto_rules.get("interval_minutes", DEFAULT_INTERVAL_MINUTES))
        paused = bool(get_auto_paused()) if get_auto_paused else False
        detail = history.get("check_detail")
        precision_pending = any(history.get(key, value) != value for key, value in (
            ("comparison_decimals", auto_rules["decimals"]),
            ("comparison_integer_digits", auto_rules["integer_digits"]),
            ("comparison_fraction_digits", auto_rules["fraction_digits"]),
            ("precision_mode", auto_rules.get("precision_mode", False)),
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
        elif not precision_pending and status == STANDALONE_PENDING:
            heading = "Zweite Aufnahme steht aus"
        elif (not precision_pending and status == "ocr_only"
              and history.get("check_detail") == STANDALONE_VERIFIED_NOTICE):
            tone, heading, icon = "ok", "Zählerstand gegengeprüft", "✓"
        elif not precision_pending and status == "match_with_warning":
            tone, heading, icon = "warning", "Prüfung bestanden mit Hinweis", "!"
            if history.get("check_detail") == LAST_DIGIT_PASS:
                explanation = "Für den Verbrauch verwendet die App den plausiblen Vergleichswert."
                detail = f"{detail} {EN_UI[explanation] if language == 'en' else explanation}"
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
            elif status in ("stale_sample", "capture_unavailable") and not history.get("last_epoch"):
                heading = "Noch kein aktuelles Zählerbild"
                detail = ("Waiting for a current meter image. The app will retry automatically."
                          if language == "en" else
                          "Warte auf ein aktuelles Zählerbild. Die App versucht es automatisch erneut.")
            else:
                detail = ""
            if str(history.get("check_detail", "")).startswith(STANDALONE_REJECTED_NOTICE):
                heading = "Aufnahmen stimmen nicht plausibel überein"
                detail = (history["check_detail"] if language == "de" else
                          english_result(history["check_detail"], status))
            elif history.get("check_detail") in (RAW_ROW_UNCLEAR, MANUAL_ROW_UNCLEAR):
                detail = history["check_detail"] if language == "de" else EN_UI[history["check_detail"]]
            elif history.get("check_detail") == LAST_DIGIT_NOTICE:
                heading = "Letzte Nachkommastelle unsicher"
                detail = LAST_DIGIT_NOTICE if language == "de" else EN_UI[LAST_DIGIT_NOTICE]
            elif status == "difference":
                heading = "Ablesung und Vergleichswert weichen ab" if not prolonged else heading
                instructions = ("Vergleiche beide Werte mit dem Stand direkt am Zähler."
                                if prolonged or paused else
                                "Die App prüft automatisch erneut. Bleibt der Unterschied, vergleiche beide Werte mit dem Stand direkt am Zähler.")
                detail = instructions if language == "de" else EN_UI[instructions]
        if language == "en":
            heading = EN_UI[heading]
        adjustment = history.get("ocr_rotation_adjustment", 0)
        if not precision_pending and status in ("match", "ocr_only") and type(adjustment) is int and adjustment:
            rotation_note = (f"Read with an image rotation of {adjustment:+d}°."
                             if language == "en" else f"Mit Bilddrehung von {adjustment:+d}° gelesen.")
            detail = " ".join(part for part in (detail, rotation_note) if part)
        try:
            failure_attempts = max(0, int(history.get("failure_attempts", 0) or 0))
        except (TypeError, ValueError):
            failure_attempts = 0
        retry_suppressed = bool(history.get("retry_suppressed"))
        if failure_attempts and paused:
            recovery_notice = (f"Previous failed checks: {failure_attempts}. Automatic checks are paused."
                               if language == "en" else
                               f"Bisherige Fehlprüfungen: {failure_attempts}. Die Automatik ist pausiert.")
        elif failure_attempts and retry_suppressed:
            recovery_notice = (
                f"{failure_attempts} automatic checks failed. Waiting for a higher meter reading or a new image."
                if language == "en" else
                f"{failure_attempts} automatische Prüfungen fehlgeschlagen. Es wird auf einen höheren Zählerstand "
                "oder ein neues Bild gewartet."
            )
        elif failure_attempts:
            recovery_notice = (
                f"Failed checks: {failure_attempts} of 3. The app will check again automatically."
                if language == "en" else
                f"Fehlprüfungen: {failure_attempts} von 3. Die App prüft automatisch erneut."
            )
        else:
            recovery_notice = ""
        activity = get_activity() if get_activity else {"detail": "Wartet auf die nächste automatische Prüfung."}
        if language == "en":
            from i18n import english_activity
            activity = {**activity, "detail": english_activity(activity.get("state"), activity.get("detail"))}
            source_connection = EN_UI.get(
                history.get("source_connection_detail", ""), "No image has been fetched yet."
            )
        else:
            source_connection = history.get("source_connection_detail", "Noch kein Bildabruf erfolgt.")
        reflection_enabled = auto_rules.get("reflection_estimate_enabled", False)
        reflection_estimate = reflection_result(history, auto_rules) if not precision_pending else None
        reflection_suggestion = (not reflection_enabled and not precision_pending
                                 and not auto_rules.get("reflection_suggestion_hidden", False)
                                 and status == "ocr_unclear"
                                 and history.get("reflection_streak", {}).get("count", 0) >= REFLECTION_SUGGEST_AFTER)
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
            "failure_attempts": failure_attempts,
            "retry_suppressed": retry_suppressed,
            "recovery_notice": recovery_notice,
            "geometry_warning": geometry_warning(history, auto_rules, language),
            "reflection_estimate": reflection_estimate,
            "reflection_live_estimate": (history.get("reflection_live_estimate")
                                        if auto_rules.get("reflection_estimate_enabled") else None),
            "reflection_suggestion": reflection_suggestion,
            "activity": activity.get("detail", "Wartet auf die nächste automatische Prüfung."),
            "activity_state": activity.get("state", "waiting"),
            "activity_completed": activity.get("completed"),
            "activity_total": activity.get("total"),
            "paused": paused,
            "source_connection": source_connection,
            "source_connection_state": history.get("source_connection_status", "unknown"),
            "decimals": history.get("comparison_decimals", default_decimals),
            "current": image_version(current_image),
            "good": image_version(good_image),
            "automatic_preview": image_version(automatic_preview),
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
            if path == "/lernvorschau.jpg":
                kind = query.get("bild", [""])[0]
                version = query.get("v", [""])[0]
                content = (get_calibration_image(kind, version)
                           if get_calibration_image is not None and kind in ("frame", "crop") else None)
                if content is None:
                    self.send_error(404)
                else:
                    self.reply(content, "image/jpeg")
                return
            if path == "/bildquellen":
                sources = discover_sources() if discover_sources else []
                self.reply(json.dumps(sources).encode("utf-8"), "application/json; charset=utf-8")
                return
            if path == "/status":
                with request_lock:
                    snapshot = dict(progress)
                snapshot["preview"] = snapshot["preview"] and test_image.is_file()
                snapshot["can_apply_crop"] = snapshot["can_apply_crop"] and snapshot["preview"]
                snapshot["crop_id"] = str(snapshot["checked_at"]) if snapshot["can_apply_crop"] else ""
                snapshot["automatic_preview"] = image_version(automatic_preview)
                snapshot["current_image"] = image_version(current_image)
                snapshot["manual_source_image"] = image_version(test_source_image)
                snapshot["calibration"] = get_calibration() if get_calibration else None
                snapshot["calibration_backup"] = bool(has_calibration_backup and has_calibration_backup())
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
            profile = query.get("ha_language", query.get("ui", [""]))[0] if user and mode == "auto" else ""
            language = mode if mode in SUPPORTED else profile if profile in SUPPORTED else fallback
            source_name = {"de": "Deutsch", "en": "English"}.get(profile)
            automatic = "Automatic" if language == "en" else "Automatisch"
            automatic += f" (Home Assistant: {source_name})" if source_name else " (Home Assistant)"
            scripts = f"<script>{profile_script(user)}</script>" if user and mode == "auto" else ""
            summary = automatic_summary(history, language, auto_rules)
            delivery = get_delivery()
            source, setup_pending = get_source()
            source_selected = source.get("selected", not setup_pending)
            esp_camera_only = source["mode"] == "slfork_camera"
            source_option = "slfork" if esp_camera_only else source["mode"]
            source_choices = (
                {"": "Choose an image source", "esphome": "ESPHome / camera",
                 "camera": "Home Assistant camera with reference reading", "slfork": "AI on the Edge / SLFork"}
                if language == "en" else
                {"": "Bildquelle auswählen", "esphome": "ESPHome / Kamera",
                 "camera": "Home-Assistant-Kamera mit Vergleichswert", "slfork": "AI on the Edge / SLFork"}
            )
            intro = ("Choose a source to start automatic checks." if language == "en" else
                     "Wähle eine Bildquelle, um die automatische Kontrolle zu starten.")
            values = {name: html.escape(summary[name]) for name in ("ocr", "reference", "detail")}
            values["automatic_activity"] = html.escape(summary["activity"])
            values["automatic_activity_state"] = html.escape(summary["activity_state"])
            values["recovery_notice"] = html.escape(summary["recovery_notice"])
            values["source_connection"] = html.escape(summary["source_connection"])
            values["source_connection_state"] = html.escape(summary["source_connection_state"])
            manual_saved = load_manual_settings()
            settings = {**auto_rules, **history.get("manual_result", {}).get("settings", {}), **manual_saved}
            crop_revision = auto_rules.get("crop_revision", "")
            manual_crop = {**history.get("manual_result", {}).get("settings", {}), **manual_saved}
            if crop_revision and manual_crop.get("crop_revision") != crop_revision:
                settings.update({key: auto_rules[key] for key in ("crop_mode", "crop", "width", "rotation", "digit_boxes")})
            try:
                manual_boxes = digit_box_settings(settings.get("digit_boxes"),
                                                  auto_rules["integer_digits"] + auto_rules["fraction_digits"])
            except ValueError:
                manual_boxes = []
            decimals_by_language = DECIMALS_EN if language == "en" else DECIMALS
            comparable_decimals = {key: label for key, label in decimals_by_language.items()
                                   if int(key) <= auto_rules["fraction_digits"]}
            manual_precision = min(int(settings.get("decimals", auto_rules["decimals"])),
                                   auto_rules["fraction_digits"])
            saved = query.get("saved", [""])[0]
            calibration = get_calibration() if get_calibration else None
            reset_state = query.get("reset", [""])[0]
            if reset_state == "pending" and get_reset_status is not None:
                reset_state = get_reset_status()
                if reset_state not in ("pending", "done", "failed"):
                    reset_state = "failed"
            if reset_state not in ("pending", "done", "failed"):
                reset_state = ""
            reset_message = {
                "done": "Werkseinstellungen wiederhergestellt. Die Einrichtung öffnet sich erneut.",
                "pending": "Werkreset läuft noch. Die Einrichtung öffnet sich, sobald er fertig ist.",
                "failed": "Werkreset konnte nicht vollständig ausgeführt werden.",
            }.get(reset_state, "")
            if language == "en" and reset_message:
                reset_message = EN_UI[reset_message]
            selected_tab = query.get("ui", [""])[0]
            settings_tab_active = (selected_tab == "settings" if selected_tab in ("settings", "overview") else
                                   saved in ("1", "crop", "notifications", "source", "setup-calibration") or setup_pending)
            saved_message = (
                "Ausschnitt und Drehung für manuelle Tests gespeichert." if saved == "manual-crop" else
                "Einrichtung gespeichert." if saved in ("setup", "setup-calibration") else
                "Gesicherter Ausschnitt wiederhergestellt." if saved == "crop-restored" else
                "Fallback-Wert gespeichert." if saved == "fallback" else
                "Automatische Prüfregeln gespeichert." if saved == "1" else
                "Getesteten Bildausschnitt für die Automatik übernommen." if saved == "crop" else
                "Ausschnitt zurückgesetzt. Die Automatik sucht die Ziffernreihe wieder selbst." if saved == "crop-reset" else
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
            estimate = summary["reflection_estimate"] or {}
            pending_estimate = estimate if estimate and not estimate["confirmed"] else {}
            preview_file = "automatikvorschau.jpg" if summary["automatic_preview"] else "aktuell.jpg"
            preview_version = summary["automatic_preview"] or summary["current"]
            self.reply(page.format(**values,
                language=language,
                app_name=APP_NAME,
                language_mode=mode,
                automatic_progress_hidden="" if summary["activity_state"] in ("queued", "working") else "hidden",
                automatic_tone=summary["tone"], automatic_heading=summary["heading"],
                automatic_icon=summary["icon"], automatic_incident=html.escape(summary["incident"]),
                banner_preference_key=f"{NAMESPACE}-ignored-warning-{user}" if user else "",
                anonymous_banner_key=f"{NAMESPACE}-ignored-warning",
                ignore_hidden="" if summary["incident"] else "hidden",
                profile_script=scripts,
                overview_hidden="hidden" if settings_tab_active else "",
                settings_hidden="" if settings_tab_active else "hidden",
                language_options=select_options({"auto": automatic, "de": "Deutsch", "en": "English"}, mode),
                settings_open="open" if saved in ("1", "crop", "crop-reset", "fallback") else "",
                fallback_saved_notice=auto_saved_notice if saved == "fallback" else "",
                calibration_preview_html=(translate_page(CALIBRATION_PREVIEW_HTML) if language == "en"
                                          else CALIBRATION_PREVIEW_HTML),
                calibration_saved_notice=auto_saved_notice if saved in ("setup-calibration", "crop-restored") else "",
                calibration_hidden="" if control_calibration else "hidden",
                geometry_warning_hidden="" if summary["geometry_warning"] else "hidden",
                geometry_warning_text=html.escape(summary["geometry_warning"]),
                calibration_restore_hidden="" if has_calibration_backup and has_calibration_backup() else "hidden",
                self_repair_checked="checked" if auto_rules.get("self_repair_enabled") else "",
                wizard_self_repair_checked="checked" if setup_pending or auto_rules.get("self_repair_enabled") else "",
                calibration_min=MIN_IMAGE_LIMIT, calibration_max=MAX_IMAGES,
                calibration_limit=calibration["limit"] if calibration else DEFAULT_LIMIT,
                setup_first_run=str(bool(setup_pending or reset_state == "done")).lower(),
                precision_hidden="" if auto_rules["decimals"] == 3 else "hidden",
                precision_checked="checked" if auto_rules.get("precision_mode") else "",
                reflection_enabled_checked="checked" if auto_rules.get("reflection_estimate_enabled") else "",
                fine_alignment_checked="checked" if auto_rules.get("fine_alignment_enabled") else "",
                adaptive_interval_checked="checked" if auto_rules.get("adaptive_interval_enabled") else "",
                reflection_hide_checked="checked" if auto_rules.get("reflection_suggestion_hidden") else "",
                reflection_suggestion_hidden="" if summary["reflection_suggestion"] else "hidden",
                reflection_estimate_hidden="" if estimate.get("confirmed") else "hidden",
                reflection_approval_hidden="" if pending_estimate else "hidden",
                reflection_approval_id=html.escape(str(pending_estimate.get("id", ""))),
                reflection_digits_option=(select_options({pending_estimate["digit"]: pending_estimate["digit"]}, "")
                                          if pending_estimate else ""),
                reflection_left=html.escape(str(estimate.get("left", ""))),
                reflection_digit=html.escape(str(estimate.get("digit", ""))),
                reflection_right=html.escape(str(estimate.get("right", ""))),
                reflection_time=html.escape(str(estimate.get("time", 0))),
                wizard_source_options=select_options(
                    source_choices, source_option if source_selected and not setup_pending else ""
                ),
                esp_camera_only_checked="checked" if esp_camera_only else "",
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
                wizard_crop_options=radio_options("crop_mode", {
                    "auto": CROP_MODES_EN["auto"] if language == "en" else CROP_MODES["auto"],
                    **({"learn": "Learn crop and rotation" if language == "en"
                        else "Ausschnitt und Drehung lernen"} if control_calibration else {}),
                    "manual": "Enter crop coordinates" if language == "en" else "Bildkoordinaten eingeben",
                }, "learn" if setup_pending and control_calibration else auto_rules["crop_mode"]),
                fallback_value=html.escape(auto_rules["fallback_value"], quote=True),
                fallback_time=html.escape(auto_rules["fallback_time"], quote=True),
                wizard_saved_notice=(
                    auto_saved_notice + '<button type="button" id="setup-image-test">' +
                    ("Test your own image" if language == "en" else "Eigenes Bild testen") + '</button>'
                    if saved == "setup" else ""
                ),
                manual_open="open" if test == "open" else "",
                manual_saved_notice=auto_saved_notice if saved == "manual-crop" else "",
                test_hidden="" if test_visible or test in ("queued", "busy") else "hidden",
                test_source_visible="" if test_visible else "hidden",
                notifications_open="open" if saved == "notifications" else "",
                source_open="open" if setup_pending or saved == "source" else "",
                source_intro=f'<p class="settings-note">{intro}</p>' if not source_selected or setup_pending else "",
                source_options=select_options(source_choices, source_option if source_selected else ""),
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
                     if source["mode"] not in ("esphome", "slfork_camera") or value != "1"},
                    str(max(2, auto_rules["attempts"]) if source["mode"] in ("esphome", "slfork_camera")
                        else auto_rules["attempts"]),
                ),
                auto_polarity_options=select_options(
                    POLARITIES_EN if language == "en" else POLARITIES, auto_rules["polarity"],
                ),
                saved_auto_crop_mode=auto_rules["crop_mode"],
                auto_crop_mode_options=select_options(
                    CROP_MODES_EN if language == "en" else CROP_MODES, auto_rules["crop_mode"],
                ),
                auto_crop_value=html.escape(auto_rules["crop"], quote=True),
                auto_width_value=auto_rules["width"],
                max_flow=format_cubic_metres(auto_rules.get("max_flow_lph", DEFAULT_FLOW_LPH)),
                max_interval_minutes=MAX_INTERVAL_MINUTES,
                slfork_interval_hidden="" if source["mode"] == "slfork" else "hidden",
                interval_minutes=auto_rules.get("interval_minutes", DEFAULT_INTERVAL_MINUTES),
                auto_rotation_value=editable_rotation(auto_rules),
                auto_saved_notice=auto_saved_notice if saved in ("1", "crop", "crop-reset") else "",
                manual_reference=html.escape(str(settings.get("manual_reference", auto_rules["fallback_value"])),
                                             quote=True),
                test_source_preview=test_source_preview,
                automatic_preview_src=f' src="{preview_file}?v={preview_version}"' if preview_version else "",
                automatic_preview_hidden="" if preview_version else "hidden",
                preview_empty_hidden="hidden" if preview_version else "",
                preview_legend_hidden="" if summary["automatic_preview"] else "hidden",
                reset_notice=(
                    '<p class="failure-recovery" role="status">' + html.escape(reset_message) + '</p>'
                    if reset_message else ""
                ),
                reset_state=reset_state,
                manual_area_hidden='' if test in ("queued", "busy", "open") else 'hidden',
                crop_mode_options=select_options(
                    CROP_MODES_EN if language == "en" else CROP_MODES,
                    settings.get("crop_mode", "auto"),
                ),
                crop_value=html.escape(str(settings.get("crop", default_crop)), quote=True),
                manual_crop_revision=html.escape(crop_revision, quote=True),
                default_crop_value=html.escape(default_crop, quote=True),
                default_crop_width=default_width,
                manual_digit_boxes=html.escape(json.dumps(manual_boxes), quote=True),
                automatic_digit_boxes=html.escape(json.dumps(auto_rules["digit_boxes"]), quote=True),
                crop_integer_digits=auto_rules["integer_digits"],
                crop_digit_count=auto_rules["integer_digits"] + auto_rules["fraction_digits"],
                crop_whole_ratio=auto_rules["integer_digits"] /
                    (auto_rules["integer_digits"] + auto_rules["fraction_digits"]),
                width_value=int(settings.get("width", default_width)),
                rotation_value=editable_rotation(settings),

                attempt_options=select_options(ATTEMPTS, str(settings.get("attempts", auto_rules["attempts"]))),
                default_attempts=default_attempts,
                csrf=csrf_token,
                paused_notice_hidden="" if summary["paused"] else "hidden",
                pause_button_hidden="hidden" if summary["paused"] else "",
                reference_time=summary["reference_time"] or 0,
                reference_is_fallback=int(summary["reference_is_fallback"]),
                image_time=summary["image_time"],
                last_check=summary["last_check"] or 0,
                last_match=summary["last_match"] or 0,
                next_check=json.dumps(summary["next_check"]),
                recovery_hidden="hidden" if not summary["failure_attempts"] else "",
            ).encode("utf-8"), "text/html; charset=utf-8")

        def do_POST(self):
            if not self.authorized():
                return
            path = urlsplit(self.path).path
            if path not in ("/pruefen", "/automatik", "/ausschnitt-uebernehmen", "/sprache",
                            "/benachrichtigungen", "/bildquelle", "/einrichtung",
                            "/einrichtung-ueberspringen", "/werkreset", "/automatik-pause",
                            "/spiegelungs-hinweis-ausblenden", "/ergaenzte-ziffer-bestaetigen", "/selbsteinrichtung", "/fallback"):
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
            if path == "/automatik-pause":
                target = form.get("paused", [])
                if len(target) != 1 or target[0] not in ("0", "1") or save_auto_paused is None:
                    problem(400)
                    return
                try:
                    with rules_lock:
                        save_auto_paused(target[0] == "1")
                except (OSError, ValueError):
                    problem(503, "Der Pausenzustand konnte nicht gespeichert werden.",
                            "Could not save the pause state.")
                    return
                self.redirect("?paused=" + target[0] + keep_mode)
                return
            if path == "/werkreset":
                result = request_factory_reset() if request_factory_reset is not None else "failed"
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

            def selected_source_mode(default=""):
                selected = field("source_mode", default)
                return "slfork_camera" if selected == "slfork" and field("esp_camera_only") == "1" else selected

            if path == "/einrichtungsbild":
                try:
                    source = source_rules({"mode": selected_source_mode(), "url": field("url"),
                                           "camera": field("camera"), "reference": ""})
                except ValueError:
                    problem(400, "Bitte zuerst eine Bildquelle auswählen.", "Select a camera source first.")
                    return
                if get_wizard_image is None or not wizard_image_lock.acquire(blocking=False):
                    problem(503)
                    return
                try:
                    content = get_wizard_image(source)
                except (OSError, ValueError):
                    problem(503, "Das Kamerabild konnte nicht geladen werden.", "Could not load the camera image.")
                else:
                    self.reply(content, "image/jpeg")
                finally:
                    wizard_image_lock.release()
                return

            if path == "/spiegelungs-hinweis-ausblenden":
                try:
                    with rules_lock:
                        save_auto_rules({**read_auto_rules(), "reflection_suggestion_hidden": True})
                except (OSError, ValueError):
                    problem(503)
                    return
                self.redirect("?ui=overview" + keep_mode)
                return

            if path == "/ergaenzte-ziffer-bestaetigen":
                try:
                    with rules_lock:
                        rules = read_auto_rules()
                        estimate = reflection_result(read_history(), rules)
                        if (not estimate or field("estimate_id") != estimate["id"]
                                or field("digit") != estimate["digit"]):
                            problem(409, "Bitte den aktuellen Vorschlag auswählen.",
                                    "Select the current suggestion.")
                            return
                        save_auto_rules({**rules, "reflection_confirmed_id": estimate["id"]})
                except (OSError, ValueError):
                    problem(503)
                    return
                self.redirect("?ui=overview" + keep_mode)
                return

            if path == "/einrichtung":
                try:
                    source_values = source_rules({
                        "mode": selected_source_mode(), "url": field("url"),
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
                    learn_crop = crop_mode == "learn" and control_calibration is not None
                    if learn_crop:
                        image_limit = int(field("image_limit", str(DEFAULT_LIMIT)))
                        if not MIN_IMAGE_LIMIT <= image_limit <= MAX_IMAGES:
                            raise ValueError("Invalid calibration image limit")
                        crop_mode = old_rules["crop_mode"]
                    meter_display = field("meter_display")
                    if (not 1 <= integer_digits <= 9 or not 0 <= fraction_digits <= 3
                            or not 0 <= decimals <= fraction_digits or not 1 <= attempts <= 10
                            or not valid_interval_minutes(interval_minutes)
                            or polarity not in POLARITIES or crop_mode not in CROP_MODES
                            or meter_display not in ("rollers", "digital", "mixed")):
                        raise ValueError("Prüfe Ziffernzahl, Vergleichsgenauigkeit und Prüfintervall.")
                    crop, width, rotation = old_rules["crop"], old_rules["width"], old_rules.get("rotation", 0)
                    if not learn_crop:
                        crop = field("crop", crop)
                        width = int(field("width", str(width)))
                        rotation = int(field("rotation", str(rotation)))
                        crop_coordinates(crop, width, rotation)
                    max_flow = parse_flow_limit(field("max_flow"))
                    fallback_value, fallback_time = fallback_options(
                        field("fallback_value"), field("fallback_time"), decimals, integer_digits, fraction_digits,
                    )
                    enabled = field("notifications_enabled") == "1"
                    delivery_values = notification_rules({
                        "enabled": enabled, "review_minutes": int(field("review_minutes")),
                        "delivery_hours": int(field("delivery_hours")),
                        "push": field("push"), "target": field("target"),
                    })
                    rules_values = {
                        **old_rules, "decimals": decimals, "attempts": attempts,
                        "polarity": polarity, "crop_mode": crop_mode, "crop": crop,
                        "width": width, "rotation": rotation,
                        "digit_boxes": old_rules["digit_boxes"] if (
                            crop_mode == old_rules["crop_mode"] and crop == old_rules["crop"]
                            and rotation == old_rules.get("rotation", 0) and width == old_rules["width"]
                            and integer_digits == old_rules["integer_digits"] and fraction_digits == old_rules["fraction_digits"]
                        ) else [], "max_flow_lph": max_flow,
                        "precision_mode": field("precision_mode") == "1",
                        "self_repair_enabled": field("self_repair_enabled") == "1",
                        "interval_minutes": interval_minutes, "integer_digits": integer_digits,
                        "fraction_digits": fraction_digits, "meter_display": meter_display,
                        "fallback_value": fallback_value, "fallback_time": fallback_time,
                    }
                    with source_lock, rules_lock:
                        if learn_crop and get_auto_paused and get_auto_paused():
                            problem(409, "Setze die Automatik fort und starte dann die Selbsteinrichtung.",
                                    "Resume automatic checks before starting automatic setup.")
                            return
                        save_source(source_values)
                        with delivery_lock:
                            save_delivery(delivery_values)
                        save_auto_rules(rules_values)
                        if learn_crop:
                            control_calibration("start", image_limit)
                except (ValueError, TypeError):
                    problem(400, "Bitte prüfe Bildquelle, Ziffernaufteilung und Fallback-Wert.",
                            "Check the image source, digit layout and fallback reading.")
                    return
                except OSError:
                    problem(503)
                    return
                if learn_crop:
                    self.redirect("?saved=setup-calibration&ui=settings" + keep_mode + "#calibration-settings")
                else:
                    self.redirect("?saved=setup&ui=overview" + keep_mode)
                return

            if path == "/bildquelle":
                try:
                    with source_lock:
                        current, _ = get_source()
                        values = source_rules({
                            "mode": selected_source_mode(),
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
                                       rotation=settings.get("rotation", 0), digit_boxes=settings.get("digit_boxes", []))
                        save_auto_rules(current)
                except (OSError, ValueError, KeyError, TypeError):
                    problem(503, "Der Ausschnitt konnte nicht gespeichert werden.",
                            "Could not save the image crop.")
                    return
                self.redirect("?saved=crop&ui=settings" + keep_mode)
                return
            if path == "/fallback":
                try:
                    with rules_lock:
                        rules = read_auto_rules()
                        value, stamp = fallback_options(
                            field("fallback_value"), field("fallback_time"), rules["decimals"],
                            rules["integer_digits"], rules["fraction_digits"],
                        )
                        save_auto_rules({**rules, "fallback_value": value, "fallback_time": stamp})
                except ValueError:
                    problem(400, "Bitte Zählerstand und Ablesezeit prüfen.", "Check the meter reading and its time.")
                    return
                except OSError:
                    problem(503)
                    return
                self.redirect("?saved=fallback&ui=settings" + keep_mode + "#fallback-form")
                return
            if path == "/selbsteinrichtung":
                if control_calibration is None:
                    self.send_error(404)
                    return
                try:
                    action = field("action")
                    if action not in ("start", "cancel", "restore"):
                        raise ValueError("Invalid calibration action")
                    limit = int(field("image_limit", str(DEFAULT_LIMIT))) if action == "start" else 0
                    if action == "start" and not MIN_IMAGE_LIMIT <= limit <= MAX_IMAGES:
                        raise ValueError("Invalid calibration image limit")
                    region = search_region(field("region")) if action == "start" else None
                    if region:
                        control_calibration(action, limit, region=region)
                    else:
                        control_calibration(action, limit)
                except ValueError:
                    problem(400, "Bitte Bildquelle einrichten, die Automatik fortsetzen und das Bildlimit prüfen.",
                            "Set up an image source, resume automatic checks and check the image limit.")
                    return
                except OSError:
                    problem(503)
                    return
                saved = "crop-restored" if action == "restore" else "calibration"
                self.redirect(f"?saved={saved}&ui=settings" + keep_mode)
                return
            if path == "/automatik":
                if form.get("reset_crop") == ["1"]:
                    try:
                        with rules_lock:
                            save_auto_rules({**read_auto_rules(), "crop_mode": "auto", "crop": default_crop,
                                             "width": default_width, "rotation": 0})
                    except (OSError, ValueError):
                        problem(503, "Der Bildausschnitt konnte nicht zurückgesetzt werden.",
                                "Could not reset the image crop.")
                        return
                    self.redirect("?saved=crop-reset&ui=settings" + keep_mode)
                    return
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
                        boxes = []
                        if crop_mode[0] == "manual":
                            crop = field("crop", crop)
                            boxes = digit_box_settings(json.loads(field("digit_boxes", "[]")),
                                                      old_rules["integer_digits"] + old_rules["fraction_digits"])
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
                                         "precision_mode": field("precision_mode") == "1",
                                         "reflection_estimate_enabled": field("reflection_estimate_enabled") == "1",
                                         "fine_alignment_enabled": field("fine_alignment_enabled") == "1",
                                         "self_repair_enabled": field("self_repair_enabled") == "1",
                                         "adaptive_interval_enabled": field("adaptive_interval_enabled") == "1",
                                         "reflection_suggestion_hidden": field("reflection_suggestion_hidden") == "1",
                                         "polarity": polarity[0], "crop_mode": crop_mode[0],
                                         "crop": crop, "width": width, "rotation": rotation, "digit_boxes": boxes,
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
            boxes = []
            crop_revision = auto_rules.get("crop_revision", "")
            if crop_revision and field("crop_revision") != crop_revision:
                crop_mode = [auto_rules["crop_mode"]]
                crop_value, width_value, rotation = auto_rules["crop"], auto_rules["width"], auto_rules["rotation"]
                boxes = auto_rules["digit_boxes"]
            elif crop_mode[0] == "manual":
                try:
                    crop_value = field("crop", default_crop)
                    width_value = int(field("width", str(default_width)))
                    rotation = int(field("rotation", "0"))
                    boxes = digit_box_settings(json.loads(field("digit_boxes", "[]")),
                                              auto_rules["integer_digits"] + auto_rules["fraction_digits"])
                    boundaries = crop_coordinates(crop_value, width_value, rotation)
                    crop_value = ",".join(map(str, boundaries))
                except ValueError:
                    problem(400)
                    return
            settings = {"polarity": polarity[0], "decimals": int(decimals[0]),
                        "attempts": int(attempts[0]), "crop_mode": crop_mode[0],
                        "crop": crop_value, "width": width_value, "rotation": rotation, "digit_boxes": boxes}
            if crop_revision:
                settings["crop_revision"] = crop_revision
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
                if form.get("save_settings") != ["1"]:
                    if test_source_image is not None:
                        test_source_image.unlink(missing_ok=True)
                    test_image.unlink(missing_ok=True)
            except OSError:
                problem(503, "Die Testeinstellungen konnten nicht gespeichert werden.",
                        "Could not save the manual test settings.")
                return
            if form.get("save_settings") == ["1"]:
                self.redirect("?test=open&saved=manual-crop&ui=overview" + keep_mode)
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
    return server, update_progress, reset_progress_state
