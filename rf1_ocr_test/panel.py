"""Home Assistant ingress panel for optical gas meter checks."""

import base64
import html
from io import BytesIO
from email.parser import BytesParser
from email.policy import default as email_policy
import json
import os
import re
import subprocess
from datetime import datetime, timezone
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from queue import Empty, Full
from secrets import compare_digest, token_urlsafe
from threading import Lock, Thread
from tempfile import NamedTemporaryFile
from urllib.parse import parse_qs, urlsplit

from PIL import Image

from app_channel import APP_NAME, NAMESPACE
import debug_log

INSTANCE_ID = token_urlsafe(8)
from calibration import (
    DEFAULT_INTENSIVE_AGREEMENT, DEFAULT_LIMIT, MIN_IMAGE_LIMIT, MAX_IMAGES,
    layouts, search_region, valid_intensive_agreement,
)
from checks import (DEFAULT_INTERVAL_MINUTES, MAX_INTERVAL_MINUTES, WARNING_DETAIL_AFTER, meter_prefix,
                    OCR_PROFILES, crop_register, read_register, LAST_DIGIT_NOTICE, LAST_DIGIT_PASS, REFLECTION_SUGGEST_AFTER, STANDALONE_PENDING, STANDALONE_REJECTED_NOTICE,
                    STANDALONE_VERIFIED_NOTICE, last_check_at, recommended_comparison_decimals, reschedule_next_check,
                    setup_deadlines, setup_source_id, stabilization_interval, stationary_partial_active, valid_interval_minutes)
QUIET_FAILURES = 3
from checks import FRAME_OFF_NOTICE, FRAME_OFF_WAIT_NOTICE, MOVING_DIGIT_NOTICE
from consumption import (DEFAULT_FLOW_LPH, EXCESSIVE_INCREASE, LOWER_PENDING, LOWER_READING,
                         consumption_statistics, format_cubic_metres, parse_flow_limit)
from demo import run_demo
from i18n import EN_UI, english_progress, english_result, translate_page
from language import MODES, SUPPORTED, USER_ID, browser_locale, profile_script
from layout import MANUAL_ROW_UNCLEAR, RAW_ROW_UNCLEAR, crop_coordinates, digit_box_settings, scale_digit_boxes, turn_crop
from meter_learning import suggest_single_digit_box
from notification_settings import notification_rules
from source_settings import source_check_key, source_rules

SUPERVISOR_ADDRESS = "172.30.32.2"
MAX_MANUAL_IMAGE_BYTES = 3_000_000
MAX_MULTIPART_OVERHEAD = 16_384

CALIBRATION_SKIP_HTML = """<form method="post" action="selbsteinrichtung" class="calibration-skip" hidden>
<input type="hidden" name="lang" value="{language}">
<input type="hidden" name="mode" value="{mode}">
<input type="hidden" name="csrf" value="{csrf}">
<input type="hidden" name="verification_id">
<p><strong>Hinweis zur Genauigkeit.</strong> Ohne Gegenprobe kann der übernommene Rahmen spätere Ablesungen ungenauer machen.</p>
<button type="submit" name="action" value="skip-verification">Gegenprobe überspringen und Rahmen übernehmen</button>
</form>"""

CALIBRATION_PREVIEW_HTML = """<details class="calibration-photo-panel" open hidden>
<summary>Bilder der Selbsteinrichtung</summary>
<div class="calibration-photo-grid">
<figure>
<div class="calibration-photo-frame">
<img data-image="frame" alt="Kamerabild der Selbsteinrichtung" decoding="async">
<span class="calibration-crop-region" hidden></span>
</div>
<figcaption class="calibration-frame-caption">Aktuelles Kamerabild</figcaption>
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

REFLECTION_OFFER_SECONDS = 60 * 60

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
@media(max-width:340px){{.main-menu{{flex-wrap:wrap}}.main-tabs{{flex-basis:100%}}}}
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
.activity-details{{margin-top:.4rem;font-size:.9rem;color:var(--muted)}}
.activity-details p{{margin-top:.35rem}}
.setup-success{{display:grid;grid-template-columns:auto minmax(0,1fr);gap:.8rem;margin:0 0 1rem;padding:clamp(.95rem,4vw,1.4rem);border:1px solid #65a986;border-radius:.85rem;background:light-dark(#edf8f0,#183a2a);color:light-dark(#155d39,#a2e5bc)}}
.demo-grid{{display:grid;gap:.8rem;grid-template-columns:repeat(auto-fit,minmax(min(100%,13rem),1fr))}}
.demo-grid figure{{margin:0}}
.demo-grid img{{width:100%;background:#101b23;border-radius:.6rem}}
#experimental summary{{cursor:pointer;font-weight:650}}
#experimental-meter-list{{margin-top:1rem}}
.experimental-meter-card{{padding:.85rem;margin:.65rem 0;border:1px solid var(--edge);border-radius:.75rem}}
.experimental-meter-card p{{margin:.35rem 0}}
.experimental-hour-chart{{display:flex;gap:3px;align-items:end;height:4.5rem;margin-top:.6rem;border-bottom:1px solid var(--edge)}}
.experimental-hour-chart span{{flex:1;min-width:0;background:#64c8ac;border-radius:3px 3px 0 0}}
#experimental-form textarea{{display:block;width:100%;font:inherit;padding:.5rem;background:var(--surface);color:inherit;border:1px solid var(--edge);border-radius:.5rem}}
.setup-success-icon{{font-size:1.5rem;font-weight:750;line-height:1.25}}
.setup-success strong{{font-size:clamp(1.15rem,4vw,1.4rem)}}
.setup-success p{{margin:.35rem 0 0}}
#setup-duration{{font-variant-numeric:tabular-nums}}
.consumption-summary{{display:flex;gap:.75rem 1.8rem;flex-wrap:wrap;margin:.75rem 0}}
.consumption-summary dt{{font-size:.86rem;color:var(--muted)}}
.consumption-summary dd{{margin:.2rem 0 0;font-weight:700;font-variant-numeric:tabular-nums}}
.consumption-history{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,13rem),1fr));gap:.8rem}}
.consumption-history ol{{padding:0;margin:.4rem 0;list-style:none}}
.consumption-history li{{display:flex;justify-content:space-between;gap:.6rem;padding:.25rem 0;border-bottom:1px solid var(--edge);font-variant-numeric:tabular-nums}}
.consumption-history li span:last-child{{text-align:right}}
#recognition-tools{{margin-top:1rem;padding-top:.8rem;border-top:1px solid var(--edge)}}
#recognition-tools .check-actions{{margin-top:.65rem}}
#start-automatic-form{{margin:.55rem 0}}
#comparison-suggestion{{flex-wrap:wrap}}
#setup-image-test{{margin:.4rem 0 .8rem}}
.setup-progress{{display:block;width:100%;height:.8rem;margin:.45rem 0;border:0;border-radius:99px;overflow:hidden;accent-color:#c28a25}}
.setup-progress[value]::-webkit-progress-bar{{background:light-dark(#eee6d1,#473d29)}}
.setup-progress[value]::-webkit-progress-value{{background:#c28a25;border-radius:99px}}
.setup-progress[hidden]{{display:none}}
.activity-status[data-state="waiting"][data-routine-ok="true"]{{display:none}}
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
.setup-step details.setup-help{{border:1px solid var(--edge);border-radius:.7rem;padding:0 .7rem}}
.setup-step details.setup-help > summary{{cursor:pointer;min-height:2.8rem;padding:.7rem .2rem;color:inherit;font-weight:650}}
.setup-step select,#wizard-camera-search{{min-height:2.8rem}}
.setup-step .setup-controls button{{min-height:2.8rem}}
.setup-phase{{display:grid;gap:.45rem;margin:.7rem 0;grid-template-columns:repeat(auto-fit,minmax(min(100%,10rem),1fr))}}
.setup-phase div{{padding:.55rem .7rem;border:1px solid var(--edge);border-radius:.6rem}}
.setup-phase dt{{font-size:.85rem;color:var(--muted)}}
.setup-phase dd{{margin:.2rem 0 0;font-weight:650}}
#wizard-manual-draw{{margin:0}}
#wizard-crop-confirmation{{margin:.35rem 0}}
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
/* After seven digits are saved, show only a short background-check status on Overview. */
#calibration-overview.background-only > :not(#calibration-overview-state){{display:none!important}}
#calibration-state[data-tone]:not([data-tone=""]){{padding:.75rem .9rem;border:1px solid;border-radius:.7rem}}
.calibration-live[data-tone="ok"],#calibration-state[data-tone="ok"]{{color:light-dark(#185d35,#9ce5b5);background:light-dark(#e9f8ee,#17382a);font-size:1.12rem;font-weight:750}}
.calibration-skip,#calibration-state[data-tone="warning"],#calibration-overview-state[data-tone="warning"]{{margin:.6rem 0;padding:.75rem .9rem;border:1px solid light-dark(#9b6414,#af8039);border-radius:.7rem;color:light-dark(#704508,#ffe1a0);background:light-dark(#fff5db,#362b19)}}
.calibration-skip p{{margin:0 0 .55rem}}
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
.calibration-candidates{{font-variant-numeric:tabular-nums;padding-inline-start:1.8rem;margin:.45rem 0}}
.calibration-candidates li{{margin:.2rem 0}}
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
.digit-frame[data-reflection="true"]{{border:2px solid #ffcf53;background:#ffcf5333}}
.digit-frame[data-active="true"]{{border:2px solid #ffcf53;z-index:1}}
.digit-correction{{width:min(46rem,calc(100% - 1.25rem));max-height:calc(100dvh - 1.25rem);overflow:auto}}
.digit-adjustments{{display:grid;gap:.65rem;margin:.7rem 0}}
.digit-adjustments select{{width:100%;margin-top:.25rem}}
.digit-adjustments .crop-actions button{{min-height:2.75rem;min-width:2.75rem}}
.digit-correction .digit-editor{{display:block;width:100%}}
.digit-correction canvas{{width:100%}}
.digit-correction .digit-frame span{{width:min(17px,46%);height:min(17px,48%)}}
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
/* ---------- Design system 0.7: tokens ---------- */
:root{{font:15px/1.5 "Inter","Segoe UI Variable","Segoe UI",system-ui,-apple-system,sans-serif;
--page:light-dark(#eef2f5,#0b1117);--surface:light-dark(#ffffff,#141c24);--surface-2:light-dark(#f6f8fa,#1a242e);
--edge:light-dark(#e1e7ec,#26323d);--ink:light-dark(#0f1f2b,#e6edf3);--muted:light-dark(#5b6b78,#93a3b1);
--accent:light-dark(#0b8f7c,#38c9b0);--accent-ink:light-dark(#ffffff,#04201b);--accent-soft:light-dark(#e2f4f1,#123a34);
--ok:light-dark(#1d8a52,#5fd29a);--ok-soft:light-dark(#e6f6ed,#12301f);
--warn:light-dark(#a46a00,#f2c14e);--warn-soft:light-dark(#fff4d9,#33290f);
--bad:light-dark(#c0353f,#ff8a92);--bad-soft:light-dark(#fdecee,#3a1a1f);
--radius:1.1rem;--radius-sm:.7rem;--shadow:0 1px 2px light-dark(#0f1f2b0d,#0006),0 8px 24px light-dark(#0f1f2b0f,#0004)}}
body{{max-width:64rem;padding:1.25rem 1rem 3rem;background:var(--page);color:var(--ink)}}
h1{{font-size:1.35rem;letter-spacing:-.02em;margin:0;line-height:1.2}}
h2{{font-size:1.02rem;letter-spacing:-.01em}}
a{{color:var(--accent)}}
/* ---------- Header and navigation ---------- */
header{{align-items:center;margin-bottom:1rem}}
.brand{{display:flex;align-items:center;gap:.7rem;margin-right:auto;min-width:0}}
.brand-mark{{flex:none;width:2.6rem;height:2.6rem;border-radius:.8rem;display:grid;place-items:center;
background:linear-gradient(140deg,var(--accent),light-dark(#0a6f87,#2a8fb0));color:#fff;box-shadow:var(--shadow)}}
.brand-mark svg{{width:1.55rem;height:1.55rem}}
.brand-subtitle{{margin:.1rem 0 0;color:var(--muted);font-size:.82rem}}
#open-setup{{background:var(--surface);border-color:var(--edge);color:var(--ink)}}
.language-bar{{margin:0}}
.language-bar label{{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}}
.language-bar select{{min-height:2.55rem;border-radius:99px;padding-inline:.9rem}}
.main-menu{{padding:.3rem;border-radius:99px;background:var(--surface);box-shadow:var(--shadow);border-color:transparent}}
.main-tabs button{{border-radius:99px;font-weight:650}}
.main-tabs button[aria-selected="true"]{{background:var(--ink);color:var(--surface);border-color:transparent}}
.main-guide{{border-radius:99px;color:var(--muted);text-decoration:none;font-weight:600}}
.main-guide:hover{{color:var(--ink);background:var(--surface-2)}}
/* ---------- Surfaces and controls ---------- */
.panel{{border:1px solid var(--edge);border-radius:var(--radius);box-shadow:var(--shadow);padding:1.25rem 1.35rem}}
button{{border-radius:99px;border:1px solid var(--edge);background:var(--surface-2);color:var(--ink);font-weight:650;
transition:background .15s,transform .05s,box-shadow .15s}}
button:not(:disabled):hover{{background:light-dark(#e8edf1,#22303c)}}
button:not(:disabled):active{{transform:translateY(1px)}}
button:disabled{{opacity:.5;cursor:not-allowed}}
#start-automatic,#start-check-with-options,#save-digit-correction,form button[type="submit"]:not(.crop-reset){{background:var(--accent);border-color:transparent;color:var(--accent-ink)}}
#start-automatic:not(:disabled):hover,#start-check-with-options:not(:disabled):hover,form button[type="submit"]:not(.crop-reset):not(:disabled):hover{{background:light-dark(#097a6a,#5fd8c3)}}
select,input{{border-radius:var(--radius-sm);background:var(--surface);border:1px solid var(--edge)}}
button:focus-visible,select:focus-visible,input:focus-visible,summary:focus-visible,a:focus-visible{{outline:3px solid light-dark(#0b8f7c66,#38c9b088);outline-offset:2px}}
label{{color:var(--muted)}}
/* ---------- Meter hero ---------- */
.meter-hero{{position:relative;display:grid;gap:1rem;margin:-1.25rem -1.35rem 1.1rem;padding:1.4rem 1.35rem 1.2rem;
border-radius:var(--radius) var(--radius) 0 0;background:radial-gradient(120% 140% at 0% 0%,light-dark(#e3f3f0,#123430) 0%,transparent 60%),var(--surface-2);
border-bottom:1px solid var(--edge)}}
.meter-hero-top{{display:flex;align-items:center;justify-content:space-between;gap:.75rem;flex-wrap:wrap}}
.meter-hero-label{{margin:0;font-size:.78rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}}
.status-chip{{display:inline-flex;align-items:center;gap:.45rem;padding:.3rem .75rem;border-radius:99px;font-size:.85rem;font-weight:700;
background:var(--surface);border:1px solid var(--edge);color:var(--muted)}}
.status-chip::before{{content:"";width:.55rem;height:.55rem;border-radius:50%;background:currentColor}}
.status-chip[data-tone="ok"]{{color:var(--ok);background:var(--ok-soft);border-color:transparent}}
.status-chip[data-tone="notice"]{{color:var(--ok);background:var(--ok-soft);border-color:transparent}}
.status-chip[data-tone="ok"]::before{{box-shadow:0 0 0 0 currentColor;animation:pulse 2.4s infinite}}
.status-chip[data-tone="warning"]{{color:var(--warn);background:var(--warn-soft);border-color:transparent}}
.status-chip[data-tone="problem"]{{color:var(--bad);background:var(--bad-soft);border-color:transparent}}
@keyframes pulse{{0%{{box-shadow:0 0 0 0 color-mix(in srgb,currentColor 45%,transparent)}}70%{{box-shadow:0 0 0 .45rem transparent}}100%{{box-shadow:0 0 0 0 transparent}}}}
@media(prefers-reduced-motion:reduce){{.status-chip::before{{animation:none!important}}}}
.odometer{{display:flex;align-items:stretch;gap:.28rem;flex-wrap:nowrap;max-width:100%;overflow-x:auto;padding:.15rem 0 .3rem;
font:700 clamp(1.7rem,7.5vw,3rem)/1 ui-monospace,"SF Mono","Cascadia Mono",Menlo,Consolas,monospace;font-variant-numeric:tabular-nums}}
.odometer .roller{{position:relative;display:grid;place-items:center;min-width:1.02em;padding:.22em .08em;border-radius:.16em;
background:linear-gradient(#0d141a,#26323b 48%,#0d141a);color:#f4f7f9;box-shadow:inset 0 .08em .12em #0009,inset 0 -.08em .12em #0009,0 1px 0 light-dark(#fff,#ffffff14)}}
.odometer .roller::after{{content:"";position:absolute;inset:48% 0 auto;height:1px;background:#0006}}
.odometer .roller.fraction{{background:linear-gradient(#5d1116,#b3262e 48%,#5d1116)}}
.odometer .roller.unclear{{color:#ffcf53;background:linear-gradient(#3a2c06,#6d5410 48%,#3a2c06)}}
.odometer .separator{{align-self:end;padding:0 .02em;color:var(--muted)}}
.odometer .unit{{align-self:end;margin-left:.35rem;font:600 .38em/1.4 system-ui,sans-serif;color:var(--muted)}}
.odometer-empty{{color:var(--muted);font:600 1rem system-ui,sans-serif;align-self:center}}
.meter-hero-note{{margin:-.35rem 0 0;color:var(--muted);font-size:.85rem}}
.meter-hero-note::before{{content:"ⓘ ";}}
.meter-hero-note[data-state="searching"]{{color:var(--warn)}}
.meter-hero-note[data-state="optimizing"]{{color:var(--ok)}}
.meter-hero.is-stale .odometer,.meter-hero.is-stale .meter-hero-meta{{opacity:.45;filter:grayscale(1);transition:opacity .3s}}
.status-chip[data-tone="stale"]{{color:var(--muted);background:transparent;border-color:var(--line, currentColor)}}
.meter-hero-stale{{display:flex;flex-wrap:wrap;align-items:center;gap:.6rem;margin:0;color:var(--warn);font-size:.9rem}}
.meter-hero-note[data-state="searching"]::before{{content:"";display:inline-block;width:.7rem;height:.7rem;margin-right:.4rem;vertical-align:-.05rem;
border:2px solid currentColor;border-right-color:transparent;border-radius:50%;animation:spin 1s linear infinite}}
@keyframes spin{{to{{transform:rotate(360deg)}}}}
.hero-search-progress{{display:block;width:min(100%,22rem);height:.35rem;margin:-.55rem 0 0;border:0;border-radius:99px;overflow:hidden;accent-color:var(--warn);background:var(--edge)}}
.hero-search-progress::-webkit-progress-bar{{background:var(--edge);border-radius:99px}}
.hero-search-progress::-webkit-progress-value{{background:var(--warn);border-radius:99px}}
.odometer .roller.searching{{color:transparent;overflow:hidden;background:linear-gradient(#3a2c06,#6d5410 48%,#3a2c06)}}
.odometer .roller.searching::before{{content:"0 1 2 3 4 5 6 7 8 9 0";position:absolute;left:0;right:0;top:0;color:#ffcf53;opacity:.85;
white-space:pre-line;line-height:1.24em;text-align:center;animation:roll 2.2s linear infinite}}
@keyframes roll{{from{{transform:translateY(0)}}to{{transform:translateY(-10.6em)}}}}
@media(prefers-reduced-motion:reduce){{.odometer .roller.searching::before,.meter-hero-note[data-state="searching"]::before{{animation:none}}}}
.meter-hero-meta{{display:flex;gap:.4rem 1.2rem;flex-wrap:wrap;margin:0;color:var(--muted);font-size:.86rem}}
.meter-hero-meta strong{{color:var(--ink);font-weight:650;font-variant-numeric:tabular-nums}}
/* ---------- Status, facts and actions ---------- */
.check-card-heading{{display:none}}
.automatic-banner{{border-radius:var(--radius-sm);border-width:1px;padding:.75rem .9rem}}
.automatic-banner[data-tone="ok"]{{background:var(--ok-soft);border-color:transparent;color:var(--ok)}}
.automatic-banner[data-tone="warning"]{{background:var(--warn-soft);border-color:transparent;color:var(--warn)}}
.automatic-banner[data-tone="problem"]{{background:var(--bad-soft);border-color:transparent;color:var(--bad)}}
.automatic-banner[data-tone="notice"]{{background:transparent;border-color:var(--line, currentColor);color:var(--muted);padding:.55rem .85rem;font-size:.9rem}}
.automatic-banner[data-tone="notice"] strong{{font-weight:650}}
.automatic-actions{{display:flex;flex-wrap:wrap;gap:.55rem;align-items:center;margin:0 0 1rem}}
.automatic-actions form{{margin:0;display:block}}
#start-automatic-form{{margin:0}}
.fact-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,10.5rem),1fr));gap:.6rem;margin:.4rem 0 0}}
.fact-grid > div{{padding:.7rem .85rem;border-radius:var(--radius-sm);background:var(--surface-2);border:1px solid var(--edge);min-width:0}}
.fact-grid dt{{font-size:.76rem;font-weight:650;letter-spacing:.02em;color:var(--muted)}}
.fact-grid dd{{margin:.2rem 0 0;font-size:1.02rem;font-weight:650}}
.connection-status{{display:inline-flex;align-items:center;gap:.4rem;margin:.2rem 0 .6rem;font-size:.85rem}}
.connection-status::before{{content:"";width:.5rem;height:.5rem;border-radius:50%;background:currentColor;opacity:.8}}
.failure-recovery,.paused-notice{{border-radius:var(--radius-sm)}}
/* ---------- Consumption ---------- */
.consumption-panel{{display:block;margin:1.25rem 0 0;padding:1.1rem 1.15rem;border-radius:var(--radius);background:var(--surface-2);border:1px solid var(--edge)}}
.consumption-panel h2{{margin:0 0 .6rem}}
.consumption-summary{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,9rem),1fr));gap:.6rem;margin:0}}
.consumption-summary > div{{padding:.75rem .9rem;border-radius:var(--radius-sm);background:var(--surface);border:1px solid var(--edge)}}
.consumption-summary dt{{font-size:.76rem;font-weight:650}}
.consumption-summary dd{{font-size:clamp(1.05rem,4.2vw,1.45rem);letter-spacing:-.02em;margin-top:.15rem}}
.consumption-chart{{display:flex;align-items:end;gap:3px;height:5.5rem;margin:.9rem 0 .2rem;padding-bottom:1px;border-bottom:1px solid var(--edge)}}
.consumption-chart span{{flex:1;min-width:0;border-radius:4px 4px 1px 1px;background:linear-gradient(var(--accent),color-mix(in srgb,var(--accent) 55%,transparent));min-height:2px}}
.consumption-chart span[data-empty="true"]{{background:var(--edge);min-height:2px;height:2px!important}}
.consumption-chart span[data-estimated="true"]{{opacity:.55}}
.consumption-chart-axis{{display:flex;justify-content:space-between;margin:0;color:var(--muted);font-size:.75rem}}
#consumption-details summary,.dashboard-help summary,.automatic-images > summary,#recognition-tools > summary,.ocr-details summary{{cursor:pointer;font-weight:650;color:var(--muted)}}
/* ---------- Images and tools ---------- */
.automatic-images{{margin:0 0 1rem;padding:1rem 1.15rem;border-radius:var(--radius);border:1px solid var(--edge)}}
.automatic-images[open] > summary{{margin-bottom:.4rem}}
.preview{{border-top:0;padding-top:0}}
.preview h2{{display:none}}
.preview img{{border-radius:var(--radius-sm);border:0;background:#0d141a;box-shadow:inset 0 0 0 1px var(--edge)}}
#recognition-tools{{margin-top:1rem;padding:1rem 1.15rem;border:1px dashed var(--edge);border-radius:var(--radius)}}
.dashboard-help{{margin:1rem 0 0}}
.test-box{{border-radius:var(--radius-sm);background:var(--surface-2)}}
/* ---------- Tools tab ---------- */
#tools-panel #recognition-tools{{margin:0 0 1rem;padding:0;border:0}}
#tools-panel #recognition-tools > summary{{font-size:1.02rem;color:var(--ink);margin-bottom:.4rem}}
.manual-crop-override{{grid-column:1/-1;padding:.2rem .9rem;border:1px solid var(--edge);border-radius:var(--radius-sm)}}
.manual-crop-override > summary{{min-height:2.6rem;display:flex;align-items:center;cursor:pointer;font-weight:650;color:var(--muted)}}
.manual-crop-override[open]{{padding-bottom:.9rem}}
.manual-crop-override > label,.manual-crop-override > .crop-draw,.manual-crop-override > .crop-fields{{margin-top:.6rem}}
/* ---------- Settings ---------- */
.settings-item{{border-top:0;margin:0 0 .6rem;padding:0 1.15rem;border:1px solid var(--edge);border-radius:var(--radius);background:var(--surface)}}
.settings-item > summary{{min-height:3.4rem;font-weight:700}}
.manual-panel[open]{{box-shadow:var(--shadow)}}
.manual-panel > summary::after{{content:"";width:.55rem;height:.55rem;border-right:2px solid var(--muted);border-bottom:2px solid var(--muted);transform:rotate(45deg);transition:transform .2s;margin-right:.2rem}}
.manual-panel[open] > summary::after{{content:"";transform:rotate(-135deg)}}
.setup-dialog{{border-radius:calc(var(--radius) + .2rem);box-shadow:0 1.5rem 4rem #0006}}
.page-footer{{margin-top:2rem}}
.advanced-actions{{margin-top:.6rem;font-size:.9rem}}
.advanced-actions > summary{{color:var(--muted);cursor:pointer}}
.advanced-actions button{{font-size:.85rem;min-height:2.2rem;padding:.3rem .8rem;background:transparent}}
.debug-log-text{{max-height:22rem;overflow:auto;white-space:pre-wrap;word-break:break-all;font-size:.75rem;background:var(--surface-2);border:1px solid var(--edge);border-radius:var(--radius-sm);padding:.6rem}}
#debug-log{{margin-top:1rem}}
.button-link{{display:inline-flex;align-items:center;min-height:2.4rem;padding:.4rem 1rem;border-radius:99px;border:1px solid var(--edge);background:var(--surface-2);color:var(--ink);text-decoration:none;font-weight:650}}
/* ---------- Setup wizard in the new design ---------- */
.setup-dialog{{height:min(90dvh,44rem);scrollbar-gutter:stable;padding:1.1rem 1.3rem 1rem}}
.setup-dialog .manual-content{{border-top:0;padding-top:0;margin-top:.25rem}}
.setup-dialog form#setup-form{{display:grid;grid-template-columns:minmax(0,1fr);gap:.4rem}}
#setup-skip{{background:var(--surface-2);color:var(--ink);border-color:var(--edge)}}
#open-demo-setup{{justify-self:start}}
.setup-stepper{{list-style:none;display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.4rem;margin:.1rem 0 .9rem;padding:0;counter-reset:setupstep}}
.setup-stepper li{{counter-increment:setupstep;display:flex;align-items:center;gap:.4rem;min-width:0;padding:.4rem .55rem;border-radius:99px;background:var(--surface-2);border:1px solid var(--edge);color:var(--muted);font-size:.8rem;font-weight:650;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.setup-stepper li::before{{content:counter(setupstep);display:inline-grid;place-items:center;flex:none;width:1.35rem;height:1.35rem;border-radius:50%;background:var(--surface);border:1px solid var(--edge);font-size:.75rem}}
.setup-stepper li[data-state="current"]{{color:var(--ink);border-color:var(--accent);background:var(--accent-soft)}}
.setup-stepper li[data-state="current"]::before{{background:var(--accent);color:var(--accent-ink);border-color:transparent}}
.setup-stepper li[data-state="done"]::before{{content:"✓";color:var(--accent);border-color:var(--accent)}}
@media(max-width:480px){{.setup-stepper li{{justify-content:center;font-size:0;gap:0;padding:.35rem}}.setup-stepper li::before{{font-size:.75rem}}}}
.setup-step{{border-top:0;padding:0}}
.setup-step.active{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.9rem 1rem;align-items:start;align-content:start}}
@media(max-width:560px){{.setup-step.active{{grid-template-columns:minmax(0,1fr)}}}}
.setup-step > legend{{font-size:1.15rem;font-weight:750;color:var(--ink);margin-bottom:.5rem;padding:0}}
.setup-step .setup-help,.setup-step .source-mode-guide,.setup-step > .check-option,.setup-step > p,.setup-step > fieldset{{grid-column:1/-1}}
.setup-step div.setup-help,.setup-step .source-mode-guide{{background:var(--surface-2);border:1px solid var(--edge);border-radius:var(--radius-sm);padding:.8rem .9rem;display:grid;gap:.6rem}}
.setup-step div.setup-help > *,.setup-step .source-mode-guide > *{{margin:0}}
.setup-step .source-mode-guide ul{{padding-left:1.1rem;display:grid;gap:.3rem}}
.setup-step details.setup-help{{background:var(--surface-2);border-radius:var(--radius-sm);padding:0 .9rem}}
.setup-step details.setup-help > summary{{list-style:none;display:flex;align-items:center;justify-content:space-between;gap:.6rem}}
.setup-step details.setup-help > summary::-webkit-details-marker{{display:none}}
.setup-step details.setup-help > summary::after{{content:"";flex:none;width:.5rem;height:.5rem;border-right:2px solid var(--muted);border-bottom:2px solid var(--muted);transform:rotate(45deg);transition:transform .2s}}
.setup-step details.setup-help[open] > summary::after{{transform:rotate(-135deg)}}
.setup-step details.setup-help[open]{{padding-bottom:.8rem}}
.setup-step input,.setup-step select{{width:100%;box-sizing:border-box}}
.setup-step input[type="checkbox"],.setup-step input[type="radio"]{{width:auto}}
.setup-controls{{position:sticky;bottom:-1rem;z-index:2;margin:.4rem -1.3rem -1rem;padding:.75rem 1.3rem;background:var(--surface);border-top:1px solid var(--edge)}}
.setup-controls .setup-next,.setup-controls button[type="submit"]{{background:var(--accent);color:var(--accent-ink);border-color:transparent;margin-left:auto}}
.setup-count{{color:var(--muted);font-size:.85rem;white-space:nowrap}}
@media(max-width:480px){{.setup-count{{display:none}}}}
#setup-title{{font-size:1.3rem;font-weight:750}}
#open-demo-setup{{min-height:2.2rem;padding:.35rem .9rem;font-size:.85rem}}
/* ---------- De-duplication: the hero already shows reading, status and timing ---------- */
.automatic-banner[data-tone="ok"]{{padding:.55rem .85rem;font-size:.92rem}}
.fact-grid > div:has(#automatic-ocr),.fact-grid > div:has(#countdown),.fact-grid > div:has(#automatic-last-check){{display:none}}
#pause-auto-form button,#resume-auto-form button{{background:var(--surface-2);color:var(--ink);border-color:var(--edge)}}
#pause-auto-form button:not(:disabled):hover{{background:light-dark(#e8edf1,#22303c)}}
#start-automatic:disabled{{background:var(--surface-2);color:var(--muted);border-color:var(--edge)}}
#save-manual-crop{{background:var(--surface-2);color:var(--ink);border-color:var(--edge)}}
.main-tabs button{{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.dialog-heading{{flex-wrap:wrap}}
.dialog-heading h2{{flex:1 1 10rem;min-width:0}}
@media(max-width:420px){{.main-menu{{flex-wrap:wrap;border-radius:1.2rem;gap:.15rem}}.main-tabs{{flex-basis:100%;gap:.15rem}}
.main-tabs button{{padding-inline:.35rem;font-size:.84rem;min-height:2.6rem}}}}
@media(max-width:640px){{.main-menu{{flex-wrap:nowrap}}.main-tabs{{flex:1 1 auto;min-width:0;flex-basis:auto}}
nav.main-menu a.main-guide{{flex:none;width:2.6rem;min-height:2.6rem;padding:0;font-size:0;line-height:0;display:inline-grid;place-items:center;overflow:hidden}}
nav.main-menu a.main-guide::before{{content:"?";font-size:1.05rem;line-height:1;font-weight:750}}
header{{grid-template-columns:minmax(0,1fr) minmax(0,1fr)}}header .brand{{grid-column:1/-1}}
header #open-setup,header .language-bar,header .language-bar select{{width:100%;min-width:0}}}}
header{{display:grid;grid-template-columns:minmax(0,1fr) auto auto;gap:.6rem}}
.main-tabs button[aria-selected="true"]:not(:disabled):hover{{background:var(--ink);color:var(--surface)}}
.calibration-card form > :is(p,div,details){{grid-column:1/-1}}
.settings-item:not(.manual-panel) > summary,#experimental > summary{{display:flex;align-items:center;justify-content:space-between;list-style:none;cursor:pointer}}
.settings-item:not(.manual-panel) > summary::-webkit-details-marker,#experimental > summary::-webkit-details-marker{{display:none}}
.settings-item:not(.manual-panel) > summary::after,#experimental > summary::after{{content:"";width:.55rem;height:.55rem;border-right:2px solid var(--muted);border-bottom:2px solid var(--muted);transform:rotate(45deg);transition:transform .2s;margin-right:.2rem}}
.settings-item:not(.manual-panel)[open] > summary::after,#experimental[open] > summary::after{{transform:rotate(-135deg)}}
.reset-section > summary{{color:var(--bad)}}
@media(max-width:560px){{header{{grid-template-columns:1fr 1fr}}.brand{{grid-column:1/-1}}header > button,.language-bar,.language-bar select{{width:100%}}
.meter-hero{{margin:-.9rem -.9rem 1rem;padding:1.1rem .9rem 1rem}}.brand-subtitle{{display:none}}.automatic-actions > *,.automatic-actions button{{width:100%}}
.main-tabs button,.main-guide{{font-size:.86rem}}}}
</style>
<header>
<div class="brand"><span class="brand-mark" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4.5 16.5a8 8 0 1 1 15 0"/><path d="M12 13l3.5-4"/><circle cx="12" cy="13.5" r="1.4" fill="currentColor"/><path d="M7 20h10"/></svg></span>
<div><h1>{app_name}</h1><p class="brand-subtitle">Zählerstand lokal aus dem Kamerabild</p></div></div>
<button type="button" id="open-setup">Einrichtung</button>
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
<button type="button" role="tab" id="tab-tools" aria-controls="view-tools" aria-selected="false" tabindex="-1">Werkzeuge</button>
</div>
<a id="open-user-guide" class="main-guide" href="https://github.com/Eifellayer/meter-ocr/blob/main/rf1_ocr_test/DOCS.md" target="_blank" rel="noopener noreferrer" title="Anleitung auf GitHub">Anleitung</a>
</nav>
<main>
<div class="tab-content" id="view-overview" role="tabpanel" aria-labelledby="tab-overview" {overview_hidden}>
<div class="panel" id="check-overview">
<div class="meter-hero" id="meter-hero">
<div class="meter-hero-top">
<p class="meter-hero-label">Zählerstand</p>
<span class="status-chip" id="hero-status" data-tone="{automatic_tone}"></span>
</div>
<div class="odometer" id="meter-odometer" role="img" aria-label="Zählerstand {ocr}" data-reading="{ocr}"></div>
<p class="meter-hero-note" id="hero-digit-note" hidden></p>
<progress class="hero-search-progress" id="hero-search-progress" aria-label="Fortschritt der Hintergrundsuche" hidden></progress>
<p class="meter-hero-meta"><span>Letzte Prüfung <strong id="hero-last-check">–</strong></span>
<span>Nächste Prüfung <strong id="hero-countdown">–</strong></span></p>
<p class="meter-hero-stale" id="hero-stale" role="status" hidden><span id="hero-stale-text"></span><button type="button" class="secondary" id="reload-view">Neu laden</button></p>
</div>
<div class="check-card-heading"><h2>Automatische Kontrolle</h2></div>
<div id="setup-success" class="setup-success" role="status" {setup_success_hidden}>
<span class="setup-success-icon" aria-hidden="true">✓</span>
<div><strong>Zähler erfolgreich eingerichtet</strong>
<p id="setup-duration" {setup_duration_hidden}>{setup_duration}</p>
<p>Die Automatik prüft als Nächstes den gespeicherten Rahmen. In den ersten 20 Minuten prüft sie häufiger.</p></div>
</div>
<div class="activity-status" data-state="{automatic_activity_state}" data-routine-ok="{automatic_routine_ok}">
<p role="status" aria-live="polite"><strong>Automatik:</strong> <span id="automatic-activity">{automatic_activity}</span></p>
<progress id="automatic-progress" class="setup-progress" aria-label="Fortschritt der automatischen Prüfung" {automatic_progress_hidden}></progress>
<details id="automatic-activity-details" class="activity-details" {automatic_progress_hidden}>
<summary>Prüfdetails</summary>
<p id="automatic-attempt-info"></p>
<p id="automatic-live-reading"></p><ol id="live-ocr-candidates" hidden></ol>
</details>
</div>
<div class="crop-actions" id="setup-start-actions" {resume_setup_hidden}>
<button type="button" id="resume-setup">Einrichtung fortsetzen</button>
</div>
<p id="calibration-complete-notice" class="settings-note" role="status" hidden></p>
{digit_correction_notice}
<dialog class="setup-dialog digit-correction" id="digit-correction" aria-labelledby="digit-correction-title">
<div class="dialog-heading">
<h2 id="digit-correction-title">Ziffernrahmen korrigieren</h2>
<button type="button" id="close-digit-correction">Schließen</button>
</div>
<figure class="crop-live-preview" id="digit-correction-preview" hidden>
<figcaption>Wähle eine Ziffer. Ziehe ihren Rahmen oder passe ihn mit den Tasten darunter an.</figcaption>
<div class="digit-editor">
<canvas role="img" aria-label="Zählerbild mit Ziffernrahmen"></canvas>
<div class="digit-layer"></div>
</div>
<div class="digit-adjustments">
<label>Position auf der Anzeige<select id="digit-correction-position"></select></label>
<div class="crop-actions" role="group" aria-label="Rahmen verschieben">
<button type="button" data-box-move="-1,0" aria-label="Nach links">←</button>
<button type="button" data-box-move="0,-1" aria-label="Nach oben">↑</button>
<button type="button" data-box-move="0,1" aria-label="Nach unten">↓</button>
<button type="button" data-box-move="1,0" aria-label="Nach rechts">→</button>
<button type="button" data-box-scale="-1">Kleiner</button>
<button type="button" data-box-scale="1">Größer</button>
</div>
<div class="crop-actions">
<button type="button" id="search-one-digit">Diese Ziffer suchen</button>
<button type="button" id="undo-one-digit">Diesen Rahmen zurücksetzen</button>
</div>
</div>
</figure>
<p class="settings-note" id="digit-correction-status" role="status"></p>
<div class="crop-actions">
<button type="button" id="save-digit-correction" disabled>Ziffernrahmen speichern</button>
</div>
</dialog>
<div id="calibration-overview" class="calibration-live" hidden>
<p id="calibration-overview-state" role="status"></p>
<p class="calibration-last-digit-note settings-note" hidden></p>
<dl class="setup-phase" hidden><div><dt>Aktueller Schritt</dt><dd class="setup-current-step"></dd></div>
<div><dt>Nächster Schritt</dt><dd class="setup-next-step"></dd></div></dl>
<details class="setup-help calibration-candidate-panel" hidden><summary>Kandidaten</summary><ol class="calibration-candidates"></ol></details>
{calibration_skip_html}
<p class="calibration-image-hint settings-note" hidden></p>
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
<form method="post" action="vergleichsgenauigkeit" class="automatic-interval-hint" id="comparison-suggestion" {comparison_suggestion_hidden}>
<input type="hidden" name="csrf" value="{csrf}"><input type="hidden" name="lang" value="{language}">
<input type="hidden" name="mode" value="{language_mode}">
<input type="hidden" name="decimals" value="{suggested_decimals}">
<span>Eine Nachkommastelle blieb wiederholt unklar. Du kannst den Vergleich auf weniger Stellen begrenzen.</span>
<button type="submit">{comparison_suggestion_label}</button>
</form>
<div class="automatic-actions">
<form method="post" action="automatik-jetzt" id="start-automatic-form" {start_automatic_hidden}>
<input type="hidden" name="csrf" value="{csrf}"><input type="hidden" name="lang" value="{language}">
<input type="hidden" name="mode" value="{language_mode}">
<button type="submit" id="start-automatic" {start_automatic_disabled}>Automatische Prüfung jetzt starten</button>
</form>
<form method="post" action="automatik-pause" id="pause-auto-form" {pause_button_hidden}><input type="hidden" name="lang" value="{language}"><input type="hidden" name="mode" value="{language_mode}"><input type="hidden" name="csrf" value="{csrf}"><input type="hidden" name="paused" value="1"><button type="submit">Automatik pausieren</button></form>
</div>
<div class="automatic-interval-hint" id="automatic-interval-hint" hidden><span>Wiederholte Fehlablesung? Ein kürzeres Prüfintervall kann helfen, wenn sich der Zähler nach einer Weile wieder klarer ablesen lässt.</span><button type="button" id="open-interval-settings">Prüfintervall ändern</button></div>
<span id="preview-home" hidden></span><details class="automatic-images" id="automatic-images" open><summary>Letztes Testbild</summary>
<p id="preview-empty" class="legend" {preview_empty_hidden}>Noch kein Testbild verfügbar.</p>
<div class="preview" id="test-preview" {automatic_preview_hidden}>
<h2 id="preview-heading">Letztes Testbild</h2>
<img id="test-preview-image"{automatic_preview_src} alt="Letztes Testbild">
<p id="ocr-method" class="settings-note" hidden></p>
<details id="ocr-candidate-details" hidden>
<summary>Beste Kandidaten der Rahmen-Nachprüfung</summary>
<ol id="ocr-candidates"></ol>
</details>
<p class="legend" id="preview-legend" {preview_legend_hidden}><span class="green-key">Grün:</span> Ziffer gelesen · <span class="yellow-key">Gelb:</span> Ziffer schwankte zwischen OCR-Versuchen oder wurde aus mehreren Versuchen zusammengesetzt · <span class="red-key">Rot:</span> Ziffer weiterhin unklar. Die Farben zeigen OCR-Sicherheit, nicht die Übereinstimmung mit dem Referenzstand. Ohne automatisch erkannte Ziffernrahmen sind die Bereiche nur näherungsweise aufgeteilt.</p>
</div>
</details>
<p class="connection-status" id="source-connection" data-state="{source_connection_state}">Quelle: {source_connection}</p>
<dl class="fact-grid"><div><dt>Erkannter Stand</dt><dd id="automatic-ocr">{ocr}</dd></div>
<div><dt title="Stand aus der ersten Aufnahme oder aus einer externen Quelle">Vergleichswert</dt><dd><span id="automatic-reference">{reference}</span>
<small id="automatic-reference-note" class="reference-note" data-epoch="{reference_time}"
 data-fallback="{reference_is_fallback}" hidden></small></dd></div>
<div><dt>Bildzeit</dt><dd id="automatic-image-time" class="stamp" data-epoch="{image_time}">–</dd></div>
<div><dt>Letzte Prüfung</dt><dd id="automatic-last-check" class="stamp" data-epoch="{last_check}">–</dd></div>
<div><dt>Letzter bestätigter Abgleich</dt><dd id="automatic-last-match" class="stamp" data-epoch="{last_match}">–</dd></div>
<div><dt>Nächste Prüfung</dt><dd id="countdown">–</dd></div></dl>
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
<section class="consumption-panel" aria-labelledby="consumption-title">
<h2 id="consumption-title">Verbrauch</h2>
<dl class="consumption-summary">
<div><dt>Diese Stunde</dt><dd id="consumption-hour">–</dd></div>
<div><dt>Heute</dt><dd id="consumption-day">–</dd></div>
</dl>
<div class="consumption-chart" id="consumption-chart" role="img" aria-label="Verbrauch je Stunde, letzte 24 Stunden" hidden></div>
<p class="consumption-chart-axis" id="consumption-chart-axis" hidden><span>vor 24 h</span><span>jetzt</span></p>
<p id="consumption-empty" class="settings-note">Die Statistik füllt sich mit bestätigten Ablesungen.</p>
<details id="consumption-details" hidden>
<summary>Verlauf nach Stunde und Tag</summary>
<p class="settings-note">An Zeitgrenzen wird der Verbrauch zwischen zwei Ablesungen geschätzt. Lücken bleiben offen.</p>
<div class="consumption-history">
<div><strong>Letzte 24 Stunden</strong><ol id="consumption-hours"></ol></div>
<div><strong>Letzte 7 Tage</strong><ol id="consumption-days"></ol></div>
</div>
</details>
</section>
<details class="dashboard-help">
<summary>Stand im Home-Assistant-Dashboard anzeigen</summary>
<p>Wenn AI Meter Reader selbst aus einer ESPHome- oder Home-Assistant-Kamera liest, kannst du den Sensor „Zählerstand“ zum Dashboard hinzufügen. Seine Entitäts-ID lautet <code>sensor.rf1_ocr_zaehlerstand</code>.</p>
<p>Oder füge diese kurze YAML-Konfiguration in eine manuelle Karte ein:</p>
<pre><code>type: entity
entity: sensor.rf1_ocr_zaehlerstand
name: Zählerstand (OCR)</code></pre>
</details>
</div>
</div>
<div class="tab-content" id="view-tools" role="tabpanel" aria-labelledby="tab-tools" {tools_hidden}>
<div class="panel" id="tools-panel">
<details id="recognition-tools" open>
<summary>Werkzeuge zur Erkennung</summary>
<div class="check-actions">
<button type="button" id="open-demo-tools">Demo ohne Kamera ausprobieren</button>
<button type="button" id="open-digit-correction" {digit_correction_hidden}>Ziffernrahmen korrigieren</button>
<button type="button" id="open-manual-settings">Manueller Test</button>
</div>
</details>
<details id="debug-log">
<summary>Debug-Protokoll</summary>
<p class="settings-note">Die letzten Prüfungen mit allen OCR-Durchläufen, Entscheidung und Verbrauchsstand. Ohne Bilder und Zugangsdaten. Hilfreich für Fehlermeldungen.</p>
<p><a class="button-link" id="debug-log-download" href="debug-protokoll" download="ai-meter-reader-debug.jsonl">Protokoll herunterladen</a></p>
<pre id="debug-log-text" class="debug-log-text">–</pre>
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
<details class="manual-crop-override" id="manual-crop-override">
<summary>Abweichenden Bildausschnitt ausprobieren</summary>
<p class="settings-note">Der Test verwendet den gespeicherten Ausschnitt der Automatik. Dauerhaft änderst du ihn unter Einstellungen → Automatische Prüfung. Hier kannst du eine Variante testen und danach übernehmen.</p>
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
<div class="crop-actions">
<button id="save-manual-crop" type="submit" name="save_settings" value="1" hidden>Ausschnitt und Drehung speichern</button>
<button type="button" id="reset-manual-crop" class="crop-reset" data-default-crop="{default_crop_value}"
        data-default-width="{default_crop_width}" hidden>Ausschnitt zurücksetzen</button>
</div>
</details>
<label>Eigenes Testbild (optional, JPG oder PNG)
<input type="file" name="image" accept="image/jpeg,image/png"></label>
<p class="settings-note">Ein ausgewähltes Bild wird nur für diesen manuellen Test verwendet (max. 3 MB).</p>
<div class="crop-actions">
<button id="start-check-with-options" type="submit">Jetzt prüfen</button>
</div>
</form>
<details class="help"><summary title="Informationen zum manuellen Bildtest">ⓘ Was passiert bei „Jetzt prüfen“?</summary>
<p>Die App verwendet das letzte vorhandene Zählerbild oder ein ausgewähltes eigenes JPG-/PNG-Testbild (bis 3 MB). Sie liest die Zahlen aus dem Bild und vergleicht sie mit dem Referenzwert. Sobald die Werte übereinstimmen, stoppt die Prüfung. Andernfalls werden höchstens so viele OCR-Versuche durchgeführt wie eingestellt (1–10). Der Test verändert die automatische Trefferzahl nicht.</p></details>
</div></details>
</div>
<span id="preview-tools-slot" hidden></span>
</div>
</div>
<div class="tab-content" id="view-settings" role="tabpanel" aria-labelledby="tab-settings" {settings_hidden}>
{reset_notice}
<section class="panel calibration-card" id="calibration-settings" aria-labelledby="calibration-title" {calibration_hidden}>
<h2 id="calibration-title" tabindex="-1">Selbsteinrichtung für Ausschnitt und Drehung</h2>
<p>Die App sucht einen passenden Rahmen und Winkel. Nach drei bestätigten Aufnahmen übernimmt die Automatik die Gegenprüfung. Ziel sind fünf Minuten. Die Suche endet spätestens nach 20 Minuten.</p>
<p>Ohne externen Vergleichswert hilft ein von Hand abgelesener Startwert. Ohne Startwert wartet die App zusätzlich auf einen plausiblen Zähleranstieg.</p>
{calibration_saved_notice}
<dl class="setup-phase" hidden><div><dt>Aktueller Schritt</dt><dd class="setup-current-step"></dd></div>
<div><dt>Nächster Schritt</dt><dd class="setup-next-step"></dd></div></dl>
<details id="calibration-diagnostics" open hidden>
<summary>Diagnose der Selbsteinrichtung</summary>
<p id="calibration-state" role="status" hidden></p>
<p class="calibration-last-digit-note settings-note" hidden></p>
<ol class="calibration-candidates"></ol>
{calibration_preview_html}
</details>
{calibration_skip_html}
<p class="calibration-image-hint settings-note" hidden></p>
<button type="button" id="calibration-proposal" hidden>Gefundenen Rahmen im Test prüfen</button>
<progress id="calibration-progress" aria-label="Verstrichene Zeit der Selbsteinrichtung" hidden></progress>
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
<p id="calibration-precision-notice">{calibration_precision_notice}</p>
<div class="crop-actions">
<button id="calibration-start" type="submit" name="action" value="start">Selbsteinrichtung starten</button>
<button id="calibration-restore" type="submit" name="action" value="restore" formnovalidate {calibration_restore_hidden}>Gesicherten Ausschnitt wiederherstellen</button>
<button id="calibration-cancel" type="submit" name="action" value="cancel" formnovalidate hidden>Selbsteinrichtung stoppen</button>
</div>
<details class="advanced-actions" id="calibration-advanced" {calibration_intensive_hidden}>
<summary>Erweitert</summary>
<p class="settings-note">Die App sucht die letzte Stelle selbst im Hintergrund. Nur nötig, wenn das dauerhaft nicht klappt.</p>
<div class="crop-actions">
<button id="calibration-intensive" type="submit" name="action" value="intensive">Dritte Nachkommastelle intensiv suchen</button>
<button id="calibration-manual-digit" type="button">Dritte Nachkommastelle manuell markieren</button>
</div>
</details>
</form>
</section>
<div class="panel" id="settings"><h2>Einstellungen</h2>
<dialog class="setup-dialog" id="setup-dialog" aria-labelledby="setup-title" data-first-run="{setup_first_run}">
<div class="dialog-heading"><h2 id="setup-title">Einrichtungsassistent</h2>
<form method="post" action="einrichtung-ueberspringen" id="setup-skip-form">
<input type="hidden" name="lang" value="{language}"><input type="hidden" name="mode" value="{language_mode}">
<input type="hidden" name="csrf" value="{csrf}">
<button type="submit" id="setup-skip">Später einrichten</button></form></div>
<button type="button" id="open-demo-setup">Demo ohne Kamera ausprobieren</button>
<div class="manual-content">
<form method="post" action="einrichtung" id="setup-form">
<input type="hidden" name="lang" value="{language}"><input type="hidden" name="mode" value="{language_mode}">
<input type="hidden" name="csrf" value="{csrf}">
<ol class="setup-stepper" id="setup-stepper" aria-label="Schritte"><li data-step="0" data-state="current">Bildquelle</li><li data-step="1">Anzeige</li><li data-step="2">Ausschnitt</li><li data-step="3">Hinweise</li></ol>
<fieldset class="setup-step active" data-step="0"><legend>1. Bildquelle</legend>
<div class="source-mode-guide">
<label>Woher kommt das Zählerbild?<select name="source_mode" id="wizard-source-mode" required>{wizard_source_options}</select></label>
<ul class="settings-note" aria-label="Erklärung der Bildquellen">
<li><strong>ESPHome / Kamera:</strong> Empfohlen für den Einstieg mit einer Kamera. Die App liest den Stand selbst.</li>
<li><strong>Home-Assistant-Kamera mit Vergleichswert:</strong> Die App holt pro Prüfung ein Standbild und kann den Wert mit einem vorhandenen Sensor abgleichen.</li>
<li><strong>AI on the Edge / SLFork:</strong> Die App prüft den ESP-Messwert. Du kannst den ESP auch nur als Kamera verwenden.</li>
</ul>
</div>
<div id="wizard-discovered-sources" class="setup-help">
<label>Geräte suchen<input type="search" id="wizard-camera-search" placeholder="z. B. Gaszähler"></label>
<label>In Home Assistant gefunden<select id="wizard-discovered-source" disabled><option value="">Es wurden keine Geräte gefunden</option></select></label>
</div>
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
<div class="setup-controls"><span class="setup-count"></span><button type="button" class="setup-next">Weiter</button></div>
</fieldset>
<fieldset class="setup-step" data-step="1"><legend>2. Zähleranzeige</legend>
<label>Anzeigeart<select name="meter_display">{meter_display_options}</select></label>
<label>Ziffern vor dem Komma<select name="integer_digits">{integer_digit_options}</select></label>
<label>Nachkommastellen auf dem Zähler<select name="fraction_digits">{fraction_digit_options}</select></label>
<label>Verglichen wird bis<select name="decimals">{wizard_decimal_options}</select></label>
<div class="settings-note setup-help" data-precision-options {precision_hidden}>
<p>Der Präzisionsmodus ist experimentell. Der Wert selbst ist genau, aber die schnell laufende letzte Rolle wird oft nicht sicher erkannt. Dann prüft die App vorübergehend mit zwei Nachkommastellen.</p>
<p {wizard_initial_hidden}>Die dritte Nachkommastelle ist bei Rollen oft schwer zu erkennen. „Automatische Selbsteinrichtung“ bestätigt bei der Ersteinrichtung die ersten zwei Stellen. Die dritte bleibt unbestätigt und kann später intensiv gesucht oder im Kamerabild manuell markiert werden.</p>
<label class="check-option"><input type="checkbox" name="precision_mode" value="1" {precision_checked}> Präzisionsmodus: auch die dritte Nachkommastelle vergleichen</label>
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
<p class="settings-note">Startet nach dem Speichern. Nach drei bestätigten Aufnahmen übernimmt die Automatik die Gegenprüfung.</p>
</div>
<div class="setup-help">
<input type="hidden" name="fine_alignment_option_present" value="1">
<label class="check-option"><input type="checkbox" name="fine_alignment_enabled" value="1" {wizard_fine_alignment_checked}> Ziffernrahmen langfristig feinjustieren</label>
<label class="check-option"><input type="checkbox" name="self_repair_enabled" value="1" {wizard_self_repair_checked}> Selbstreparatur bei wiederholten Fehlmessungen</label>
<p class="settings-note">Die App sucht frühestens nach zwei Stunden anhaltender Erkennungsprobleme einen besseren Rahmen. Probleme nur an der letzten Rolle zählen dabei nicht mit. Der bisherige Rahmen gilt bis zur erfolgreichen Gegenprobe.</p>
</div>
<div class="setup-help">
<input type="hidden" name="reflection_option_present" value="1">
<label class="check-option"><input type="checkbox" name="reflection_estimate_enabled" value="1" {reflection_enabled_checked}> Verdeckte Ziffern ergänzen</label>
<p class="settings-note">Bei Spiegelungen hilfreich. Die App schätzt verdeckte Stellen nur, wenn Zählerstände und Durchfluss genau eine Ergänzung zulassen. Geschätzte Ziffern bleiben gelb.</p>
<div id="wizard-reflection-options" hidden>
<button type="button" id="wizard-reflection-load">Ziffernrahmen für Spiegelungen suchen</button>
<figure class="crop-live-preview" id="wizard-reflection-preview" hidden>
<figcaption>Gelbe Rahmen sind möglicherweise gespiegelt. Du kannst bis zu zwei Stellen markieren und die Rahmen ziehen.</figcaption>
<div class="digit-editor"><canvas role="img" aria-label="Ziffernfeld mit markierten Spiegelungen"></canvas><div class="digit-layer"></div></div>
<div class="crop-actions" id="wizard-reflection-choices"></div>
</figure>
<p id="wizard-reflection-status" class="settings-note" role="status"></p>
<input type="hidden" name="reflection_geometry">
</div>
</div>
<label>OCR-Versuche pro Bild<select name="attempts">{auto_attempt_options}</select></label>
<label>Ziffernfarbe<select name="polarity">{auto_polarity_options}</select></label>
<label>Prüfintervall (Minuten)<input type="number" name="interval_minutes" min="5" max="1440" value="{interval_minutes}" required></label>
<details class="setup-help"><summary>ⓘ Warum das Prüfintervall ändern?</summary><p>Nach einem fehlgeschlagenen automatischen Test folgen bis zu zwei weitere Prüfungen im Abstand von fünf Minuten. Sind alle drei erfolglos, wartet die App eine Stunde und prüft dann erneut. Nach Erfolg gilt wieder dein eingestelltes Intervall. Ein kürzeres Intervall kann helfen, wenn sich der Zähler beim Weiterdrehen vorübergehend schlecht lesen lässt.</p></details>
<label>Maximaler Durchfluss (m³/h)<input name="max_flow" type="text" inputmode="decimal" maxlength="10" value="{max_flow}" required></label>
<div class="setup-help" id="wizard-manual-draw" hidden>
<p>1. Lade ein Bild deiner Kamera oder wähle ein Testbild derselben Kamera.</p>
<div class="crop-actions">
<button type="button" id="wizard-crop-load">Kamerabild für Rahmen laden</button>
<label>Eigenes Bild für den Rahmen<input id="wizard-crop-file" type="file" accept="image/jpeg,image/png"></label>
</div>
<p>2. Ziehe einen Rahmen um die gesamte Ziffernreihe. Lass etwas Rand und spare die Seriennummer aus.</p>
<div class="crop-draw-image" hidden><img alt="Kamerabild zum Zeichnen des Ziffernrahmens" draggable="false"><span class="crop-draw-outline" hidden></span></div>
<p class="settings-note" role="status"></p>
<div class="crop-fields" id="wizard-crop-fields">
<label>3. Bilddrehung bei Bedarf (°)<input name="rotation" type="number" min="-180" max="180" step="1" value="{auto_rotation_value}"></label>
<input type="hidden" name="digit_boxes" value="{wizard_digit_boxes}">
<details class="setup-help"><summary>Koordinaten und Breite bearbeiten</summary>
<label>Bildbereich (links, oben, rechts, unten)<input name="crop" value="{auto_crop_value}" maxlength="30" placeholder="52,56,564,132"></label>
<label>Breite des Vorkomma-Bereichs in Pixeln<input name="width" type="number" min="1" max="9999" value="{auto_width_value}"></label>
</details>
</div>
<figure class="crop-live-preview" hidden>
<figcaption>Vorschau mit Bilddrehung</figcaption>
<div class="digit-editor"><canvas role="img" aria-label="Vorschau mit Bilddrehung"></canvas><div class="digit-layer"></div></div>
<button type="button" class="clear-digit-boxes">Einzelrahmen zurücksetzen</button>
</figure>
<p id="wizard-crop-confirmation">4. Prüfe die Vorschau und bestätige den Rahmen.</p>
<label class="check-option"><input name="confirm_manual_crop" type="checkbox" value="1" required disabled> Dieser Rahmen umfasst die Ziffernreihe</label>
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
<p>Der Präzisionsmodus ist experimentell. Der Wert selbst ist genau, aber die schnell laufende letzte Rolle wird oft nicht sicher erkannt. Dann prüft die App vorübergehend mit zwei Nachkommastellen.</p>
<label class="check-option"><input type="checkbox" name="precision_mode" value="1" {precision_checked}> Präzisionsmodus: auch die dritte Nachkommastelle vergleichen</label>
</div>
<label title="Nach einer unklaren Ablesung folgt ein zusätzlicher Versuch nach fünf Minuten. Schlägt auch der fehl, gilt wieder dieses Intervall.">Prüfintervall (Minuten)
<input name="interval_minutes" type="number" min="1" max="{max_interval_minutes}" value="{interval_minutes}" required>
<small {slfork_interval_hidden}>Bei AI on the Edge / SLFork liegen reguläre Prüfungen mindestens fünf Minuten auseinander.</small></label>
<label>Max. OCR-Versuche
<select name="attempts">{auto_attempt_options}</select></label>
<label>Übereinstimmung für die Intensivprüfung (%)
<input name="intensive_agreement" type="number" min="1" max="100" step="1" value="{intensive_agreement}" required>
<small>Ab diesem Wert wechselt die Selbsteinrichtung in die Intensivprüfung. Eine einzelne vermutete Ziffernposition kann sie auch früher gezielt prüfen.</small></label>
<label title="Qmax steht auf deinem Zähler. Die Vorgabe für einen G4 beträgt 6 m³/h.">Maximaler Durchfluss (m³/h)
<input name="max_flow" type="text" inputmode="decimal" maxlength="10" value="{max_flow}" required></label>
<label>Ziffernfarbe
<select name="polarity">{auto_polarity_options}</select></label>
<details class="help setup-help">
<summary>ⓘ Automatik im Hintergrund verbessern</summary>
<label class="check-option"><input type="checkbox" name="fine_alignment_enabled" value="1" {fine_alignment_checked}> Ziffernrahmen langfristig feinjustieren</label>
<label class="check-option"><input type="checkbox" name="self_repair_enabled" value="1" {self_repair_checked}> Selbstreparatur bei wiederholten Fehlmessungen</label>
<p>Die App sucht frühestens nach zwei Stunden anhaltender Erkennungsprobleme einen besseren Rahmen. Probleme nur an der letzten Rolle zählen dabei nicht mit. Der bisherige Rahmen gilt bis zur erfolgreichen Gegenprobe.</p>
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
<p class="settings-note">Du kannst die Einrichtung vollständig zurücksetzen oder die bestätigten Zählerstands- und Verbrauchsstatistiken behalten. Home-Assistant-App-Konfiguration und Entitäten bleiben in beiden Fällen bestehen.</p>
<button type="button" id="open-reset-keep">Factory Reset – Statistik behalten</button>
<button type="button" id="open-reset">Auf Werkseinstellungen zurücksetzen</button>
</div></details>
</div>
<details class="panel" id="experimental" {extra_meter_open}><summary>Experimentell · Mehrere Zähler</summary>
<p>Zusätzliche Home-Assistant-Sensoren beobachten. Diese Funktion ist experimentell. Praxistests stehen noch aus.</p>
<p class="settings-note">Unterstützt fortlaufend steigende Zähler in m³ oder kWh. Pro Zeile eine Entität und optional das Prüfintervall in Minuten, z. B. <code>sensor.wasserzaehler, 15</code>.</p>
<form id="experimental-form" method="post" action="experimentelle-zaehler">
<input type="hidden" name="csrf" value="{csrf}"><input type="hidden" name="lang" value="{language}">
<input type="hidden" name="mode" value="{language_mode}">
<label>Zusätzliche Zähler<textarea rows="3" name="meters" maxlength="640">{extra_meter_config}</textarea></label>
<button type="submit">Zähler speichern</button>
<p role="status" id="experimental-status"></p>
</form>
<div id="experimental-meter-list"></div>
</details>
<dialog class="setup-dialog" id="demo-dialog" aria-labelledby="demo-title">
<div class="dialog-heading"><h2 id="demo-title">Zähler-Demo</h2><button type="button" id="close-demo">Schließen</button></div>
<p>Probiere die Erkennung mit einem künstlichen Gaszählerbild. Deine echte Einrichtung und Verbrauchsdaten bleiben getrennt.</p>
<div class="crop-actions">
<button type="button" id="run-demo-clear">Schräges Bild prüfen</button>
<button type="button" id="run-demo-glare">Spiegelung ausprobieren</button>
</div>
<p id="demo-status" role="status"></p>
<div id="demo-results" hidden>
<p id="demo-reading"></p><p id="demo-estimate"></p>
<div class="demo-grid">
<figure><img id="demo-original" alt="Schräges künstliches Zählerbild"><figcaption>Originalbild</figcaption></figure>
<figure><img id="demo-aligned" alt="Gerader Ausschnitt mit Ziffernrahmen"><figcaption>Ausgerichteter Ausschnitt</figcaption></figure>
</div>
</div>
</dialog>
<dialog class="setup-dialog" id="reset-dialog" aria-labelledby="reset-title">
<h2 id="reset-title">Werkseinstellungen wiederherstellen?</h2>
<p id="reset-full-info">Gespeicherte Bildquelle, OCR- und Benachrichtigungseinstellungen, Prüfhistorie, Verbrauchsstatistik und Testbilder werden zurückgesetzt. Home-Assistant-App-Konfiguration und Entitätsnamen bleiben erhalten.</p>
<p id="reset-keep-info" hidden>Bildquelle, OCR- und Benachrichtigungseinstellungen, Prüfhistorie und Testbilder werden zurückgesetzt. Bestätigte Zählerstands- und Verbrauchsstatistiken sowie der kumulierte Verbrauch bleiben erhalten. Anschließend ist eine neue Einrichtung erforderlich.</p>
<form method="post" action="werkreset" id="reset-form">
<input type="hidden" name="lang" value="{language}"><input type="hidden" name="mode" value="{language_mode}">
<input type="hidden" name="csrf" value="{csrf}">
<input type="hidden" name="keep_statistics" id="reset-keep-statistics" value="0">
<button type="button" id="cancel-reset">Abbrechen</button>
<button type="submit">Jetzt zurücksetzen</button>
</form>
<p id="reset-progress" class="settings-note" role="status" hidden>Werkreset angefordert. Eine laufende Prüfung kann den Reset verzögern. Bitte warte, bis sich die Einrichtung öffnet.</p>
</dialog>
</div>
</main>

<footer class="page-footer">Kostenloses Hobbyprojekt · <a href="https://www.paypal.com/donate/?hosted_button_id=FG4Q7VKQJ9BW8" target="_blank" rel="noopener noreferrer">Freiwillig mit PayPal unterstützen</a>
<details class="about-project"><summary>Über AI Meter Reader</summary><p><a href="https://github.com/Eifellayer" target="_blank" rel="noopener noreferrer">Projekt von EifelLayer auf GitHub</a></p><p>KI-unterstützt entwickelt. Keine geeichte Messung oder Gewähr für OCR-Ergebnisse. Bitte Zählerstände bei Bedarf direkt am Gerät prüfen.</p><p><a id="roadmap-link" href="https://github.com/Eifellayer/meter-ocr/blob/main/RELEASE-PLAN.md" target="_blank" rel="noopener noreferrer">Roadmap auf GitHub</a></p></details>
</footer>
<script>
let next = {next_check};
const lang = '{language}';
let automaticStatusFailures = 0;
const pageInstance = '{instance_id}';
let staleView = '';
let reportedRenderError = '';
const searchPrefs = new URLSearchParams(location.search);
const tabs = [...document.querySelectorAll('[role="tab"]')];
const views = [...document.querySelectorAll('.tab-content')];
function activateTab(name, updateUrl = true) {{
  const selected = ['settings', 'tools'].includes(name) ? name : 'overview';
  tabs.forEach(tab => {{
    const active = tab.id === `tab-${{selected}}`;
    tab.setAttribute('aria-selected', String(active));
    tab.tabIndex = active ? 0 : -1;
  }});
  views.forEach(view => view.hidden = view.id !== `view-${{selected}}`);
  // One shared test image: show it in the tab where the user is working.
  const previewCard = document.querySelector('#automatic-images');
  const slot = document.querySelector(selected === 'tools' ? '#preview-tools-slot' : '#preview-home');
  if (previewCard && slot && slot.nextElementSibling !== previewCard) slot.after(previewCard);
  if (updateUrl) {{
    const url = new URL(location.href);
    if (selected !== 'overview') url.searchParams.set('ui', selected);
    else url.searchParams.delete('ui');
    history.replaceState(null, '', url.pathname + (url.searchParams.size ? '?' + url.searchParams : ''));
  }}
}}
tabs.forEach((tab, index) => {{
  tab.addEventListener('click', () => activateTab(tab.id.replace('tab-', '')));
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
const toolsOpen = !settingsOpen && (selectedTab === 'tools' || !document.querySelector('#view-tools').hidden);
activateTab(settingsOpen ? 'settings' : toolsOpen ? 'tools' : 'overview', false);
const setupDialog = document.querySelector('#setup-dialog');
// Keep the first-run modal outside the tab panel so its hidden ancestor cannot hide it.
document.body.appendChild(setupDialog);
// Dialogs must not inherit a hidden tab panel; they can be opened from any tab.
for (const dialog of document.querySelectorAll('.tab-content dialog')) document.body.appendChild(dialog);
const setupDismissKey = 'meter-ocr-setup-dismissed';
function dismissSetup() {{
  if (setupDialog.open) setupDialog.close();
  localStorage.setItem(setupDismissKey, '1');
}}
setupDialog.addEventListener('close', () => localStorage.setItem(setupDismissKey, '1'));
document.querySelector('#setup-skip-form').addEventListener('submit', () => localStorage.setItem(setupDismissKey, '1'));
function openSetup() {{
  activateTab('settings');
  showSetupStep(0);
  if (!setupDialog.open) setupDialog.showModal();
  loadSourceSuggestions();
}}
document.querySelector('#open-setup').addEventListener('click', openSetup);
document.querySelector('#resume-setup').addEventListener('click', openSetup);
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
const demoDialog = document.querySelector('#demo-dialog');
document.body.appendChild(demoDialog);
const demoStatus = document.querySelector('#demo-status');
const demoResults = document.querySelector('#demo-results');
let closeDemoToSetup = false;
function openDemo(fromSetup) {{
  closeDemoToSetup = fromSetup;
  demoDialog.showModal();
  if (demoResults.hidden) checkDemo(false);
}}
document.querySelector('#open-demo-setup').addEventListener('click', () => openDemo(true));
document.querySelector('#open-demo-tools').addEventListener('click', () => openDemo(false));
document.querySelector('#close-demo').addEventListener('click', () => demoDialog.close());
demoDialog.addEventListener('close', () => {{
  if (closeDemoToSetup) document.querySelector('#open-demo-setup').focus();
}});
async function checkDemo(reflection) {{
  const buttons = demoDialog.querySelectorAll('.crop-actions button');
  buttons.forEach(button => button.disabled = true);
  demoResults.hidden = true;
  demoStatus.textContent = 'Demo-Bild wird geprüft …';
  try {{
    const fields = new URLSearchParams({{csrf: '{csrf}', lang, reflection: reflection ? '1' : '0'}});
    const reply = await fetch('zaehler-demo', {{method: 'POST', body: fields}});
    if (!reply.ok) throw Error();
    const result = await reply.json();
    document.querySelector('#demo-original').src = 'data:image/jpeg;base64,' + result.image;
    document.querySelector('#demo-aligned').src = 'data:image/jpeg;base64,' + result.aligned;
    document.querySelector('#demo-reading').textContent =
      'Abgelesen ' + result.reading + ' m³ · Drehung ' + result.angle + '° · ' +
      (result.reading === result.expected ? 'Alle Ziffern erkannt.' :
       'Mindestens eine Ziffer blieb offen.');
    document.querySelector('#demo-estimate').textContent = result.estimate ?
      'Aus einem Beispiel-Referenzwert geschätzt: ' + result.estimate + ' m³.' : '';
    demoStatus.textContent = '';
    demoResults.hidden = false;
  }} catch (_) {{
    demoStatus.textContent = 'Die Demo konnte nicht geladen werden. Bitte erneut versuchen.';
  }} finally {{
    buttons.forEach(button => button.disabled = false);
  }}
}}
document.querySelector('#run-demo-clear').addEventListener('click', () => checkDemo(false));
document.querySelector('#run-demo-glare').addEventListener('click', () => checkDemo(true));
const resetDialog = document.querySelector('#reset-dialog');
const resetForm = document.querySelector('#reset-form');
const resetProgress = document.querySelector('#reset-progress');
function openFactoryReset(keepStatistics) {{
  document.querySelector('#reset-keep-statistics').value = keepStatistics ? '1' : '0';
  document.querySelector('#reset-keep-info').hidden = !keepStatistics;
  document.querySelector('#reset-full-info').hidden = keepStatistics;
  resetDialog.showModal();
}}
document.querySelector('#open-reset').addEventListener('click', () => openFactoryReset(false));
document.querySelector('#open-reset-keep').addEventListener('click', () => openFactoryReset(true));
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
const reflectionOption = setupForm.elements.reflection_estimate_enabled;
const reflectionOptions = document.querySelector('#wizard-reflection-options');
const reflectionPreview = document.querySelector('#wizard-reflection-preview');
const reflectionButton = document.querySelector('#wizard-reflection-load');
const reflectionStatus = document.querySelector('#wizard-reflection-status');
const reflectionChoices = document.querySelector('#wizard-reflection-choices');
let reflectionRevision = 0;
function clearReflectionPreview() {{
  reflectionRevision++;
  reflectionOptions.hidden = !reflectionOption.checked;
  reflectionPreview.hidden = true;
  reflectionStatus.textContent = '';
  setupForm.elements.reflection_geometry.value = '';
}}
for (const name of [...wizardSourceFields, 'integer_digits', 'fraction_digits', 'reflection_estimate_enabled']) {{
  setupForm.elements[name].addEventListener('input', clearReflectionPreview);
}}
document.querySelector('#wizard-discovered-source').addEventListener('change', clearReflectionPreview);
clearReflectionPreview();
reflectionButton.addEventListener('click', async () => {{
  clearReflectionPreview();
  const revision = reflectionRevision;
  const body = new URLSearchParams({{preview: 'reflection'}});
  for (const name of [...wizardSourceFields, 'integer_digits', 'fraction_digits', 'polarity', 'csrf', 'lang', 'mode']) {{
    const field = setupForm.elements[name];
    if (field.type !== 'checkbox' || field.checked) body.set(name, field.value);
  }}
  reflectionButton.disabled = true;
  reflectionStatus.textContent = 'Ziffernrahmen werden gesucht …';
  try {{
    const response = await fetch('einrichtungsbild', {{method: 'POST', body, cache: 'no-store'}});
    if (!response.ok) throw new Error();
    const result = await response.json();
    const image = new Image();
    image.src = 'data:image/jpeg;base64,' + result.image;
    await image.decode();
    if (revision !== reflectionRevision) return;
    const whole = Number(setupForm.elements.integer_digits.value);
    const count = whole + Number(setupForm.elements.fraction_digits.value);
    const marked = new Set(result.suspected);
    const field = {{value: JSON.stringify(result.layout.digit_boxes)}};
    const canvas = reflectionPreview.querySelector('canvas');
    drawRegister(canvas, image, [0, 0, image.naturalWidth, image.naturalHeight], 0);
    const layer = reflectionPreview.querySelector('.digit-layer');
    layer.replaceChildren();
    const editor = digitFrameEditor(reflectionPreview, field, {{value: result.layout.width}}, null, count, whole);
    editor.paint(editor.current());
    function saveMarkings() {{
      setupForm.elements.reflection_geometry.value = JSON.stringify({{
        ...result.layout, digit_boxes: editor.current(), positions: [...marked],
      }});
      Array.from(reflectionChoices.children).forEach((button, index) => {{
        const selected = marked.has(index);
        button.setAttribute('aria-pressed', String(selected));
        button.disabled = !selected && marked.size >= 2;
        layer.children[index].dataset.reflection = String(selected);
      }});
    }}
    reflectionPreview.addEventListener('digit-edit', () => {{
      if (revision === reflectionRevision) saveMarkings();
    }});
    reflectionChoices.replaceChildren();
    for (let index = 0; index < count; index++) {{
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = 'Stelle ' + (index + 1);
      button.addEventListener('click', () => {{
        if (marked.has(index)) marked.delete(index);
        else if (marked.size < 2) marked.add(index);
        saveMarkings();
      }});
      reflectionChoices.append(button);
    }}
    saveMarkings();
    reflectionStatus.textContent = '';
    reflectionPreview.hidden = false;
  }} catch (_) {{
    if (revision === reflectionRevision)
      reflectionStatus.textContent = 'Kein Ziffernfeld gefunden. Du kannst die Einrichtung direkt fortsetzen.';
  }} finally {{
    reflectionButton.disabled = false;
  }}
}});
let wizardTimeEdited = false;
wizardReadingTime.addEventListener('input', () => {{ wizardTimeEdited = true; }});
wizardReading.addEventListener('input', () => {{
  if (wizardTimeEdited) return;
  const now = new Date(Date.now() - new Date().getTimezoneOffset() * 60000);
  wizardReadingTime.value = wizardReading.value.trim() ? now.toISOString().slice(0, 16) : '';
}});
setupForm.addEventListener('invalid', event => {{
  const step = event.target.closest('.setup-step');
  if (step) showSetupStep(Number(step.dataset.step));
}}, true);
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
  document.querySelectorAll('#setup-stepper li').forEach((item, i) => {{
    item.dataset.state = i === setupStep ? 'current' : i < setupStep ? 'done' : '';
    if (i === setupStep) item.setAttribute('aria-current', 'step'); else item.removeAttribute('aria-current');
  }});
  document.querySelector('#setup-dialog').scrollTop = 0;
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
const cameraSearch = document.querySelector('#wizard-camera-search');
let sourceSuggestions = [];
let loadingSourceSuggestions = false;
async function loadSourceSuggestions() {{
  if (loadingSourceSuggestions || sourceSuggestions.length) return;
  loadingSourceSuggestions = true;
  try {{
    const response = await fetch('bildquellen', {{cache: 'no-store'}});
    if (!response.ok) throw Error('Device discovery failed');
    const suggestions = await response.json();
    if (!Array.isArray(suggestions)) throw Error('Invalid device list');
    sourceSuggestions = suggestions;
    filterWizardSources();
  }} catch (_) {{
    // Keep the selector visible and disabled when Home Assistant is not ready.
    filterWizardSources();
  }} finally {{
    loadingSourceSuggestions = false;
  }}
}}
function filterWizardSources() {{
  const selected = discoveredSource.value;
  const term = cameraSearch.value.trim().toLowerCase();
  discoveredSource.options.length = 1;
  sourceSuggestions.forEach((source, index) => {{
    if (![source.label, source.camera, source.url].join(' ').toLowerCase().includes(term)) return;
    const type = source.mode === 'slfork' ? 'AI on the Edge' : (lang === 'en' ? 'Camera' : 'Kamera');
    discoveredSource.add(new Option(type + ' · ' + source.label, String(index)));
  }});
  const available = discoveredSource.options.length > 1;
  discoveredSource.options[0].textContent = available ?
    (lang === 'en' ? 'Choose a device …' : 'Gerät auswählen …') :
    (lang === 'en' ? 'No devices found' : 'Es wurden keine Geräte gefunden');
  if ([...discoveredSource.options].some(option => option.value === selected)) discoveredSource.value = selected;
  discoveredSource.disabled = !available;
}}
cameraSearch.addEventListener('input', filterWizardSources);
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
  const fields = document.querySelector('#wizard-manual-draw');
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
  const fraction = options.closest('form').querySelector('[name="fraction_digits"]');
  if (!fraction) return;
  const showPrecisionOptions = () => {{ options.hidden = fraction.value !== '3'; }};
  fraction.addEventListener('change', showPrecisionOptions);
  showPrecisionOptions();
}});
document.querySelector('#close-manual-test').addEventListener('click', () => {{
  manualTestArea.hidden = true;
}});
document.querySelector('#language-select').addEventListener('change', () => {{
  const url = new URL(document.querySelector('#language-form').action);
  if (document.querySelector('#manual-panel').open) url.searchParams.set('test', 'open');
  if (document.querySelector('#view-settings').hidden === false) url.searchParams.set('ui', 'settings');
  else if (document.querySelector('#view-tools').hidden === false) url.searchParams.set('ui', 'tools');
  document.querySelector('#language-form').action = url;
  document.querySelector('#language-form').submit();
}});

let sendingCheck = false;
let statusPending = false;
const manualPanel = document.querySelector('#manual-panel');
const manualForm = document.querySelector('#manual-form');
const testBox = document.querySelector('#test-box');
const testButtons = [document.querySelector('#start-check-with-options')];
function setTestActive(active) {{
  for (const [index, button] of testButtons.entries()) {{
    button.disabled = active;
    button.textContent = active ? 'Prüfung läuft …' : 'Jetzt prüfen';
  }}
}}
let lastManualCropResetTime = 0;

function drawRegister(canvas, image, [left, top, right, bottom], rotation) {{
    const angle = rotation * Math.PI / 180;
    const width = right - left;
    const height = bottom - top;
    const turnedWidth = Math.ceil(width * Math.abs(Math.cos(angle)) + height * Math.abs(Math.sin(angle)));
    const turnedHeight = Math.ceil(width * Math.abs(Math.sin(angle)) + height * Math.abs(Math.cos(angle)));
    const scale = Math.min(1, 700 / turnedWidth, 420 / turnedHeight);
    canvas.width = Math.max(1, Math.round(scale * turnedWidth));
    canvas.height = Math.max(1, Math.round(scale * turnedHeight));
    canvas.dataset.rotation = rotation;
    canvas.dataset.cropWidth = turnedWidth;
    const context = canvas.getContext('2d');
    context.translate(canvas.width / 2, canvas.height / 2);
    context.rotate(angle);
    context.drawImage(image, left, top, width, height,
      -width * scale / 2, -height * scale / 2, width * scale, height * scale);
}}
function digitFrameEditor(preview, boxField, widthField, position = null,
                          digitCount = {crop_digit_count}, wholeCount = {crop_integer_digits}) {{
  const canvas = preview.querySelector('canvas');
  const frameLayer = preview.querySelector('.digit-layer');
  let frameDrag = null;
  function select(index) {{
    if (!position) return;
    position.value = index;
    frames.forEach((frame, i) => {{
      frame.dataset.active = String(i === index);
      frame.setAttribute('aria-pressed', String(i === index));
    }});
  }}
  function setBoxes(boxes) {{
    boxField.value = JSON.stringify(boxes);
    paintDigitBoxes(boxes);
    preview.dispatchEvent(new Event('digit-edit'));
  }}
  function currentDigitBoxes() {{
    const boxes = JSON.parse(boxField.value || '[]');
    if (boxes.length === digitCount) return boxes;
    const width = Number(widthField.value);
    const total = Number(canvas.dataset.cropWidth);
    const edge = wholeCount;
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
      select(index);
      if (!position) frame.dataset.active = 'true';
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
      if (!position) frame.dataset.active = 'false';
    }});
    frame.addEventListener('click', () => select(index));
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
    setBoxes(boxes);
  }}
  function replace(index, box) {{
    const boxes = currentDigitBoxes();
    const midpoint = box[0] + box[2];
    if ((index && midpoint <= boxes[index - 1][0] + boxes[index - 1][2]) ||
        (index + 1 < digitCount && midpoint >= boxes[index + 1][0] + boxes[index + 1][2])) return false;
    boxes[index] = box;
    setBoxes(boxes);
    return true;
  }}
  return {{paint: paintDigitBoxes, current: currentDigitBoxes, select, setBoxes, replace, edit: editDigitBox}};
}}
function cropEditor(form, panel, fields, reset, save, emptyText, wizard = false) {{
  const mode = form.elements.crop_mode;
  const crop = form.elements.crop;
  const rotation = form.elements.rotation;
  const area = panel.querySelector('.crop-draw-image');
  const image = area.querySelector('img');
  const outline = area.querySelector('span');
  const preview = panel.querySelector('.crop-live-preview');
  const canvas = preview.querySelector('canvas');
  const boxField = form.elements.digit_boxes;
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
    form.elements.width.value = Math.min(9999, Math.max(1, Math.round(turned * (wizard ? Number(form.elements.integer_digits.value) /
      (Number(form.elements.integer_digits.value) + Number(form.elements.fraction_digits.value)) : {crop_whole_ratio}))));
  }}
  let digitEditor;
  let digitFormat;
  function paintDigitBoxes() {{
    const whole = wizard ? Number(form.elements.integer_digits.value) : {crop_integer_digits};
    const count = wizard ? whole + Number(form.elements.fraction_digits.value) : {crop_digit_count};
    const format = whole + '/' + count;
    if (format !== digitFormat) {{
      preview.querySelector('.digit-layer').replaceChildren();
      digitEditor = digitFrameEditor(preview, boxField, form.elements.width, null, count, whole);
      digitFormat = format;
    }}
    digitEditor.paint(digitEditor.current());
  }}
  function markCropChanged() {{
    if (wizard) {{
      form.elements.confirm_manual_crop.checked = false;
      boxField.value = '[]';
    }}
  }}
  preview.querySelector('.clear-digit-boxes').addEventListener('click', () => {{
    boxField.value = '[]';
    markCropChanged();
    paintDigitBoxes();
  }});
  function drawRotationPreview(left, top, right, bottom) {{
    drawRegister(canvas, image, [left, top, right, bottom], Number(rotation.value));
    paintDigitBoxes();
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
  function loadImage(previewUrl) {{
    if (displayedUrl.startsWith('blob:')) URL.revokeObjectURL(displayedUrl);
    const file = upload?.files[0];
    displayedUrl = previewUrl || (file ? URL.createObjectURL(file) : 'aktuell.jpg?v=' + encodeURIComponent(currentVersion || Date.now()));
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
      markCropChanged();
      updateWidth(box);
    }}
    paintSaved();
  }});
  area.addEventListener('pointercancel', () => {{ drag = null; paintSaved(); }});
  rotation.addEventListener('input', () => {{
    markCropChanged();
    if (drawnCrop && crop.value === drawnCrop.join(',')) updateWidth(drawnCrop);
    paintSaved();
  }});
  crop.addEventListener('input', () => {{ markCropChanged(); paintSaved(); }});
  form.elements.width.addEventListener('input', () => {{ markCropChanged(); paintSaved(); }});
  upload?.addEventListener('change', () => {{ if (!panel.hidden) loadImage(); }});
  if (wizard) {{
    preview.addEventListener('digit-edit', () => {{ form.elements.confirm_manual_crop.checked = false; }});
    return loadImage;
  }}
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
const wizardManualPanel = document.querySelector('#wizard-manual-draw');
const wizardCropFile = document.querySelector('#wizard-crop-file');
const wizardCropLoad = document.querySelector('#wizard-crop-load');
const wizardCropStatus = wizardManualPanel.querySelector('[role="status"]');
const setWizardCropImage = cropEditor(setupForm, wizardManualPanel, document.querySelector('#wizard-crop-fields'),
  null, null, 'Kein Bild verfügbar. Prüfe die Bildquelle oder wähle ein Testbild.', true);
let wizardCropRevision = 0;
function clearWizardCrop() {{
  wizardCropRevision++;
  setupForm.elements.confirm_manual_crop.checked = false;
  setupForm.elements.digit_boxes.value = '[]';
  const area = wizardManualPanel.querySelector('.crop-draw-image');
  area.hidden = true;
  area.querySelector('img').removeAttribute('src');
  wizardManualPanel.querySelector('.crop-live-preview').hidden = true;
  wizardCropStatus.hidden = true;
}}
for (const name of [...wizardSourceFields, 'integer_digits', 'fraction_digits']) {{
  setupForm.elements[name].addEventListener('input', clearWizardCrop);
}}
discoveredSource.addEventListener('change', clearWizardCrop);
wizardCropFile.addEventListener('change', () => {{
  if (!wizardCropFile.files[0]) return;
  clearWizardCrop();
  setWizardCropImage(URL.createObjectURL(wizardCropFile.files[0]));
}});
wizardCropLoad.addEventListener('click', async () => {{
  clearWizardCrop();
  const revision = wizardCropRevision;
  const body = new URLSearchParams({{preview: 'crop'}});
  for (const name of [...wizardSourceFields, 'csrf', 'lang', 'mode']) {{
    const field = setupForm.elements[name];
    if (field.type !== 'checkbox' || field.checked) body.set(name, field.value);
  }}
  wizardCropLoad.disabled = true;
  wizardCropStatus.hidden = false;
  wizardCropStatus.textContent = 'Kamerabild wird geladen …';
  try {{
    const response = await fetch('einrichtungsbild', {{method: 'POST', body, cache: 'no-store'}});
    if (!response.ok) throw new Error();
    const picture = await response.blob();
    if (revision === wizardCropRevision) setWizardCropImage(URL.createObjectURL(picture));
  }} catch (_) {{
    if (revision === wizardCropRevision)
      wizardCropStatus.textContent = 'Kein Bild verfügbar. Prüfe die Bildquelle oder wähle ein Testbild.';
  }} finally {{
    wizardCropLoad.disabled = false;
  }}
}});
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
  document.querySelector('#manual-crop-override').open = true;
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
    penultimate_unclear: 'Die letzte Rolle war lesbar. Die vorletzte blieb trotz gezielter Prüfung offen.',
    soft_image: 'Der Ausschnitt ist deutlich weniger scharf oder kontrastreich als zuvor. Warte auf ein besseres Bild.',
    collecting: 'Grobsuche läuft. Die besten Zwischenkandidaten werden gespeichert.',
    disagree: 'Die OCR-Versuche lieferten unterschiedliche Ziffern.',
    reference_unavailable: 'Kein gültiger Vergleichswert zu diesem Bild.',
    reference_mismatch: 'Der gelesene Stand weicht vom Vergleichswert ab.',
    position_error: 'Die Ziffernreihe scheint gegenüber der Referenz um eine Stelle verschoben.',
    implausible: 'Der Stand passt zeitlich nicht zur letzten sicheren Ablesung.',
    await_movement: 'Der Rahmen ist lesbar. Die App wartet auf einen plausiblen Zähleranstieg.',
    accepted: 'Dieser Rahmen wurde auf dem aktuellen Bild bestätigt.',
    roll_transition: 'Letzte Rolle dreht weiter. Warte auf eine eindeutige Ziffer.',
    optional_last_slot: 'Letzte Rolle auf diesem Bild gelesen. Sie ist noch nicht unabhängig bestätigt.',
    reflected_geometry: 'Die sichtbaren Ziffern stützen den markierten Rahmen. Die verdeckten Stellen bleiben offen.',
    accepted_geometry: 'Ziffern bis zur zweiten Nachkommastelle gelesen. Der Rahmen zählt vorläufig. Der Vergleichswert fehlt.',
    accepted_partial: 'Bis zur zweiten Nachkommastelle bestätigt. Die dritte Stelle bleibt offen.',
    verified: 'Die abschließende Gegenprobe war erfolgreich.',
  }};
  for (const section of document.querySelectorAll('.calibration-photo-panel')) {{
    section.hidden = !preview?.frame;
    if (section.hidden) continue;
    const frame = section.querySelector('[data-image="frame"]');
    const crop = section.querySelector('[data-image="crop"]');
    const region = section.querySelector('.calibration-crop-region');
    const hasCrop = Boolean(preview.crop);
    section.querySelector('.calibration-frame-caption').textContent = preview.best_fine_score ?
      'Bester Treffer der Feinprüfung · ' + preview.best_fine_score + ' %' : 'Aktuelles Kamerabild';
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
    section.querySelector('.calibration-preview-reading').textContent = preview.last_digit_only ?
      (preview.reading ? 'Letzte Rolle: ' + preview.reading : 'Letzte Rolle wird gelesen …') :
      preview.reading ? 'OCR gelesen: ' + preview.reading : 'Ziffern werden gelesen …';
    const reason = section.querySelector('.calibration-preview-reason');
    reason.textContent = reasons[preview.reason] || '';
    reason.hidden = !reason.textContent;
    section.querySelector('.calibration-preview-help').textContent = !hasCrop ?
      (reason.hidden ? 'Die App sucht in diesem Bild nach der Ziffernreihe.' : '') : preview.reading ?
      'Grün: gelesen. Gelb: OCR-Versuche weichen ab. Gelb mit ?: Stelle vermutet, Ziffer nicht lesbar. Rot: unklar.' :
      'Die blauen Rahmen zeigen, welche Stellen die App gerade prüft.';
    if (hasCrop && preview.method === 'neighbours') section.querySelector('.calibration-preview-help').append(
      ' Die Rahmen wurden aus sichtbaren Ziffern und ihren Abständen abgeleitet.');
    else if (hasCrop && preview.approximate) section.querySelector('.calibration-preview-help').append(
      ' Die Position der Ziffernrahmen ist angenähert.');
  }}
}}

let calibrationWasActive = false;
let lastDigitSearching = false;
let lastDigitProgress = null;
let comparedDecimals = null;
let configuredDecimals = null;
let lastDigitSearchAt = null;
let partialEighthDigit = false;
let previousCalibrationState = '';
let routineOk = {automatic_routine_ok};
let calibrationNoticeUntil = 0;
function updateCalibrationNotice() {{
  const notice = document.querySelector('#calibration-complete-notice');
  notice.hidden = routineOk || !document.querySelector('#setup-success').hidden ||
    Date.now() >= calibrationNoticeUntil;
}}
function refreshCalibration(status) {{
  refreshCalibrationImages(status?.preview);
  for (const form of document.querySelectorAll('.calibration-skip')) {{
    form.elements.verification_id.value = status?.skip_verification_id || '';
    form.hidden = !form.elements.verification_id.value;
  }}
  if (!status) return;
  const active = status.state === 'waiting' || status.state === 'testing';
  const background = status.background === true;
  lastDigitSearching = background && active;
  lastDigitProgress = lastDigitSearching && status.duration > 0
    ? {{elapsed: Math.max(0, status.duration - status.seconds), duration: status.duration, seconds: status.seconds}} : null;
  const setupReading = String(status.preview?.reading || status.candidates?.[0]?.reading || '');
  const setupFraction = setupReading.replace(',', '.').split('.')[1] || '';
  const setupDigits = setupReading.replace(/[^0-9?]/g, '').length;
  const lastDigitLabel = setupDigits
    ? (lang === 'en' ? `The ${{setupDigits}}th digit` : `Die ${{setupDigits}}. Ziffer`)
    : (lang === 'en' ? 'The last decimal digit' : 'Die letzte Nachkommastelle');
  let lastDigitNote = '';
  if (active && !background && status.simplified) {{
    lastDigitNote = lastDigitLabel + (lang === 'en'
      ? ' does not need to be found for setup. After saving, the app keeps searching for it in the background.'
      : ' muss für die Einrichtung noch nicht gefunden werden. Nach dem Speichern sucht die App sie im Hintergrund weiter.');
  }} else if (active && !background && !status.intensive && comparedDecimals === 2 && setupFraction.length === 3) {{
    lastDigitNote = lastDigitLabel + (lang === 'en'
      ? ' is skipped with 2 decimal places. Choose 3 decimal places to have it searched in the background after setup.'
      : ' wird bei 2 Nachkommastellen übersprungen. Mit 3 Nachkommastellen sucht die App sie nach der Einrichtung im Hintergrund.');
  }}
  for (const element of document.querySelectorAll('.calibration-last-digit-note')) {{
    if (element.textContent !== lastDigitNote) element.textContent = lastDigitNote;
    element.hidden = !lastDigitNote;
  }}
  const overview = document.querySelector('#calibration-overview');
  overview.classList.toggle('background-only', background);
  const label = document.querySelector('#calibration-state');
  const progress = document.querySelector('#calibration-progress');
  label.hidden = false;
  const messages = {{
    waiting: 'Warte auf ein neues Kamerabild …',
    testing: 'Prüfe Ausschnitt und Drehung …',
    saved: status.simplified ?
      'Einrichtung abgeschlossen: Sieben Ziffern bestätigt. Die dritte Nachkommastelle wird zusätzlich intensiv geprüft.' :
      status.intensive ? 'Dritte Nachkommastelle bestätigt. Die Ziffernrahmen sind übernommen.' :
      'Erfolgreich eingerichtet. Ausschnitt und Drehung sind übernommen.',
    saved_reflection: 'Ausschnitt mit markierter Spiegelung vorläufig gespeichert. Die verdeckten Ziffern bleiben offen.',
    saved_stationary: 'Ausschnitt vorläufig gespeichert. Die Automatik prüft die sieben lesbaren Stellen. Die dritte Nachkommastelle bleibt vorerst offen.',
    saved_without_verification: 'Rahmen ohne Gegenprobe übernommen. Spätere Ablesungen können ungenauer sein.',
    failed: 'Selbsteinrichtung fehlgeschlagen. Prüfe Bildausschnitt, Kamerawinkel und Beleuchtung.',
    image_timeout: 'Kein neues Kamerabild erhalten. Prüfe die Bildquelle.',
    timeout: status.automatic ? 'Nachjustierung nach vier Minuten beendet. Der bisherige Rahmen bleibt gültig.' :
      'Selbsteinrichtung nach 20 Minuten beendet. Keine Einstellung sicher bestätigt.',
    cancelled: 'Selbsteinrichtung gestoppt.',
    save_failed: 'Ausschnitt und Drehung konnten nicht gespeichert werden.',
  }};
  const clock = Math.floor(status.seconds / 60) + ':' + String(status.seconds % 60).padStart(2, '0');
  const stages = {{
    queued: status.followup ?
      'Ausschnitt gespeichert. Suche jetzt gezielt nach der dritten Nachkommastelle …' :
      status.known_good_available ? 'Die App prüft zuerst den zuletzt bestätigten Rahmen.' :
      'Selbsteinrichtung wird vorbereitet …',
    capture: 'Kamerabild wird abgerufen …',
    search: 'Grobkalibrierung: Suche nach der Ziffernreihe …',
    shortlist: 'Intensivprüfung für Kandidat ' + status.variant + ' …',
    digit_probe: 'Teste die vermutete Position der letzten Rolle auf diesem Bild …',
    angle: 'Drehung wird geprüft. Der Winkel steht am Vorschaubild.',
    last_digit: 'Prüfe nur die letzte Rolle im gespeicherten Ausschnitt …',
    refine: status.preview?.weak_positions?.length ?
      'Einzelziffernsuche. Offene Stellen von links: ' + status.preview.weak_positions.join(', ') + '.' :
      'Feinkalibrierung: Prüfe Rahmen und Drehung am vorhandenen Bild …',
    verify_wait: status.intensive ? 'Letzte Rolle gefunden. Warte auf ein frisches Bild zur Gegenprobe …' :
      'Rahmen gefunden. Warte auf ein frisches Bild zur Gegenprüfung …',
    verify: 'Gefundenen Rahmen mit der normalen Prüfung gegenprüfen …',
    ocr: status.preview?.crop && status.preview.angle !== status.rotation ?
      'Prüfe den nächsten Rahmen …' :
      'Prüfe Rahmen ' + status.variant + ' mit Drehung ' + status.rotation + '° …',
  }};
  const steps = status.intensive ? ['Kamerabild laden', 'Letzte Rolle prüfen', 'Ergebnis gegenprüfen'] :
    ['Kamerabild laden', 'Ziffernreihe finden', 'Rahmen und Drehung prüfen', 'Rahmen bestätigen'];
  const confirm = Number(status.confirmations || status.reflected_confirmations || 0) > 0;
  const stage = status.stage;
  const current = ['queued', 'capture'].includes(stage) ? 0 :
    status.intensive ? (['verify', 'verify_wait'].includes(stage) ? 2 : 1) :
    ['verify', 'verify_wait'].includes(stage) || stage === 'waiting' && confirm ? 3 :
    ['shortlist', 'refine', 'angle', 'digit_probe'].includes(stage) ? 2 : 1;
  for (const plan of document.querySelectorAll('.setup-phase')) {{
    plan.hidden = !active || status.automatic;
    plan.querySelector('.setup-current-step').textContent = steps[current];
    plan.querySelector('.setup-next-step').textContent = steps[current + 1] ||
      (status.intensive ? 'Ergebnis anzeigen' : 'Rahmen speichern und Automatik starten');
  }}
  const reason = status.preview?.reason;
  for (const list of document.querySelectorAll('.calibration-candidates')) {{
    list.replaceChildren(...(status.candidates || []).map(candidate => {{
      const row = document.createElement('li');
      row.textContent = candidate.percent + ' % · ' + (candidate.reading || '–');
      return row;
    }}));
    const parent = list.closest('.calibration-candidate-panel');
    if (parent) parent.hidden = !list.children.length;
  }}
  let message = active && stages[status.stage] ? stages[status.stage] : messages[status.state] || '';
  if (status.state === 'waiting' && status.stage !== 'queued') {{
    if (reason === 'roll_transition') {{
      message = 'Letzte Rolle dreht weiter. Warte auf eine eindeutige Ziffer.' +
        (status.preview?.wheel_transition ? ' ' + status.preview.wheel_transition.join(' → ') : '');
    }} else if (reason === 'soft_image') {{
      message = 'Gegenprobe wartet auf ein besseres Bild. Der bestätigte Rahmen bleibt ausgewählt.';
    }} else if (reason === 'collecting') {{
      message = 'Grobtests: ' + status.coarse_attempts + '/' + status.coarse_limit + '.';
    }} else if (status.stage === 'verify_wait' && reason === 'accepted') {{
      message = status.coarse_complete ?
        'Drei Treffer mit 100 %: Grobprüfung beendet. Warte auf ein frisches Bild für die Gegenprobe.' :
        'Treffer gesammelt. Warte auf ein frisches Bild für die Gegenprobe.';
    }} else if (reason === 'reference_unavailable') {{
      message = 'Grün bedeutet lesbar. Ein gültiger Vergleichswert für dieses Bild fehlt.';
    }} else if (reason === 'reference_mismatch') {{
      message = 'Grün bedeutet lesbar. Der abgelesene Stand passt noch nicht zum Vergleichswert.';
    }} else if (reason === 'await_clear_roller') {{
      message = 'Eine der ersten sieben Ziffern dreht gerade. Der gefundene Rahmen bleibt erhalten; ein frisches Bild wird geprüft.';
    }} else if (reason === 'await_movement') {{
      message = 'Ziffernfeld ist lesbar.';
    }} else if (reason === 'accepted' && status.candidate_agreement === 100) {{
      message = 'Rahmen mit 100 % Übereinstimmung gefunden. Die Intensivprüfung bleibt bei diesem Rahmen und wartet auf ein neues Bild.';
    }} else if (status.confirmations >= 2) {{
      message = 'Prüfe denselben Rahmen mit dem nächsten neuen Bild weiter.';
    }} else if (status.confirmations > 0) {{
      message = 'Ziffernfeld bestätigt. Die App prüft mit dem nächsten neuen Bild weiter.';
    }} else if (reason === 'no_region') {{
      message = status.tested >= 2 ?
        'Ziffernfeld nicht gefunden. Grenze das Ziffernfeld im Kamerabild ein.' :
        'Noch kein Ziffernbereich gefunden. Warte auf ein neues Bild …';
    }}
  }}
  if (active && ['shortlist', 'refine', 'waiting'].includes(status.stage) && status.row_found) {{
    message = 'Ziffernzeile gefunden · ' + status.row_found + ' % (' +
      'Schwelle ' + status.agreement_threshold + ' %). ' + message;
  }}
  if (active && reason === 'reflected_geometry') {{
    message = 'Markierter Rahmen mit sichtbaren Ziffern geprüft. Verdeckte Stellen bleiben offen.' +
      ' ' + status.reflected_confirmations + '/' + status.required;
  }}
  if (status.state === 'failed' && ['reference_mismatch', 'position_error'].includes(reason)) {{
    message = 'Der gelesene Bereich passt nicht zum Vergleichswert. Prüfe den Vergleichswert und markiere das Ziffernfeld.';
  }}
  if (background && active) {{
    message = 'Optimierung läuft: Die Automatik arbeitet bereits; die App stimmt die dritte Nachkommastelle im Hintergrund noch fein ab.';
  }}
  if (background && ['failed', 'timeout', 'image_timeout'].includes(status.state)) {{
    message = 'Dritte Nachkommastelle noch offen. Die Automatik läuft weiterhin mit sieben bestätigten Ziffern.';
  }} else if (status.intensive && ['failed', 'timeout', 'image_timeout'].includes(status.state)) {{
    message = status.confirmations >= status.required ?
      'Feinprüfung erfolgreich, Gegenprobe offen. Der beste Rahmen steht für den manuellen Test bereit.' :
      'Dritte Nachkommastelle bleibt unbestätigt. Du kannst später erneut suchen oder sie manuell markieren.';
  }}
  if (active && status.preview?.last_digit_hint) {{
    message += ' Vorschlag für die letzte Rolle gefunden. Warte auf Bestätigung mit einem neuen Bild.';
  }}
  if (active && !status.intensive && !status.simplified && (status.awaiting_start_value || reason === 'await_movement')) {{
    message += ' Ohne Vergleichswert braucht die App einen plausiblen Anstieg oder einen Startwert.';
  }}
  if (active && status.simplified) {{
    message += ' Für den Rahmen zählen die ersten zwei Nachkommastellen.';
  }}
  const confirmationLabel = status.followup ? ' · Feinprüfung der dritten Stelle: ' : ' · Bestätigungen: ';
  const detail = 'Bilder geprüft: ' + status.tested +
    ' · Rahmen getestet: ' + status.attempts +
    confirmationLabel + status.confirmations + '/' + status.required +
    (active ? (status.intensive && ['verify', 'verify_wait'].includes(status.stage) ?
      ' · Zeit für Gegenprobe: ' : (status.intensive || status.automatic ?
      ' · Rechenzeit übrig: ' : ' · Zeit für die Einrichtung: ')) + clock + ' min' : '');
  const weakSlots = status.stress_weak_slots || [];
  const stabilityNote = weakSlots.length ?
    ' · Schwankende Stellen im Intensivtest (von links): ' + weakSlots.join(', ') : '';
  const tone = status.state === 'saved' ? 'ok' : ['saved_without_verification', 'saved_stationary', 'saved_reflection'].includes(status.state) ? 'warning' :
    ['failed', 'timeout', 'image_timeout', 'save_failed'].includes(status.state) ? 'error' : '';
  label.textContent = (status.automatic ? 'Automatische Nachjustierung · ' : '') + message + ' ' + detail + stabilityNote;
  label.dataset.tone = tone;
  document.querySelector('#calibration-overview').dataset.tone = tone;
  document.querySelector('#calibration-overview-state').dataset.tone = tone;
  const completed = ['saved', 'saved_without_verification', 'saved_stationary', 'saved_reflection'].includes(status.state);
  document.querySelector('#calibration-overview').hidden = completed;
  const notice = document.querySelector('#calibration-complete-notice');
  notice.textContent = completed ? message : '';
  const diagnostics = document.querySelector('#calibration-diagnostics');
  diagnostics.hidden = false;
  if (previousCalibrationState !== status.state) {{
    calibrationNoticeUntil = 0;
    if (completed) {{
      diagnostics.open = false;
      const justSkipped = status.state === 'saved_without_verification' && searchPrefs.get('saved') === 'calibration';
      if (calibrationWasActive || justSkipped) calibrationNoticeUntil = Date.now() + 60 * 1000;
    }} else if (active && !calibrationWasActive) diagnostics.open = true;
  }}
  previousCalibrationState = status.state;
  updateCalibrationNotice();
  if (completed && calibrationWasActive) activateTab('overview');
  calibrationWasActive = active;
  const imageHints = {{
    dark: 'Das Ziffernfeld wirkt dunkel.',
    bright: 'Das Ziffernfeld wirkt sehr hell.',
    low_contrast: 'Das Ziffernfeld hat wenig Kontrast.',
    soft: 'Das Ziffernfeld wirkt unscharf.',
  }};
  const imageNote = (status.image_hints || []).map(hint => imageHints[hint]).filter(Boolean).join(' ');
  for (const hint of document.querySelectorAll('.calibration-image-hint')) {{
    hint.hidden = completed || !imageNote;
    hint.textContent = imageNote ? 'Hinweis zum Kamerabild. ' + imageNote : '';
  }}
  document.querySelector('#calibration-overview-state').textContent =
    message + (!background && active && status.confirmations ? ' · ' + status.confirmations + '/' + status.required : '');
  // Full calibration steps stay visible on Overview only until the first seven
  // digits have been saved. The optional eighth digit must not hide normal activity.
  document.querySelector('.activity-status').hidden = active && !background;
  document.querySelector('#setup-start-actions').hidden = active ||
    document.querySelector('.activity-status').dataset.state !== 'setup_wait';
  for (const bar of [progress, document.querySelector('#calibration-overview-progress')]) {{
    bar.hidden = !active || (background && bar.id === 'calibration-overview-progress');
    bar.max = status.duration;
    const elapsed = status.duration - status.seconds;
    if (elapsed > 0) bar.value = elapsed;
    else bar.removeAttribute('value');
  }}
  if (status.settings?.crop_revision &&
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
  document.querySelector('#calibration-intensive').disabled = active;
  document.querySelector('#calibration-manual-digit').disabled = active;
  document.querySelector('#calibration-cancel').hidden = !active;
}}
const correctionDialog = document.querySelector('#digit-correction');
const correctionPreview = document.querySelector('#digit-correction-preview');
const correctionPosition = document.querySelector('#digit-correction-position');
const correctionStatus = document.querySelector('#digit-correction-status');
const correctionOpen = document.querySelector('#open-digit-correction');
const correctionSearch = document.querySelector('#search-one-digit');
const correctionSave = document.querySelector('#save-digit-correction');
const correctionUndo = document.querySelector('#undo-one-digit');
const correctionBoxes = {{value: '[]'}};
const correctionWidth = {{value: ''}};
const correctionEditor = digitFrameEditor(correctionPreview, correctionBoxes, correctionWidth, correctionPosition);
const correctionImage = new Image();
let correctionLayout = null;
let correctionSource = null;
let originalCorrection = [];
let correctionBusy = false;

function updateCorrectionControls() {{
  const index = Number(correctionPosition.value);
  const changed = correctionBoxes.value !== JSON.stringify(originalCorrection);
  correctionSave.disabled = correctionBusy || !changed || correctionPreview.hidden;
  correctionSearch.disabled = correctionBusy || correctionPreview.hidden;
  correctionUndo.disabled = correctionPreview.hidden || JSON.stringify(correctionEditor.current()[index]) ===
    JSON.stringify(originalCorrection[index]);
}}
async function openDigitCorrection(last = false) {{
  if (correctionDialog.open) return;
  correctionSource = null;
  correctionDialog.showModal();
  correctionPreview.hidden = true;
  correctionSave.disabled = true;
  correctionStatus.textContent = 'Kamerabild wird geladen …';
  correctionBusy = true;
  try {{
    const response = await fetch('status?lang=' + lang, {{cache: 'no-store'}});
    if (!response.ok) throw new Error();
    const job = await response.json();
    const layout = job.digit_correction;
    if (!layout || layout.integer_digits + layout.fraction_digits !== {crop_digit_count} ||
        ['waiting', 'testing'].includes(job.calibration?.state)) throw new Error();
    const images = [];
    if (job.digit_correction_image) images.push({{kind: 'current', version: job.digit_correction_image}});
    if (job.calibration?.preview?.frame) images.push({{kind: 'calibration', version: job.calibration.preview.frame}});
    if (!images.length) throw new Error();
    for (const source of images) {{
      const url = (source.kind === 'current' ? 'aktuell.jpg?v=' : 'lernvorschau.jpg?bild=frame&v=') +
        encodeURIComponent(source.version);
      correctionImage.src = url;
      try {{
        await correctionImage.decode();
        correctionSource = source;
        break;
      }} catch {{ correctionSource = null; }}
    }}
    if (!correctionDialog.open || !correctionSource) throw new Error();
    const crop = layout.crop.split(',').map(Number);
    if (crop[0] < 0 || crop[1] < 0 || crop[2] > correctionImage.naturalWidth ||
        crop[3] > correctionImage.naturalHeight) throw new Error();
    correctionLayout = layout;
    correctionWidth.value = layout.width;
    correctionPosition.replaceChildren();
    for (let i = 0; i < layout.integer_digits + layout.fraction_digits; i++) {{
      const label = i < layout.integer_digits ? 'Vor dem Komma: ' + (i + 1) :
        'Nach dem Komma: ' + (i - layout.integer_digits + 1);
      correctionPosition.add(new Option(label, i));
    }}
    drawRegister(correctionPreview.querySelector('canvas'), correctionImage, crop, layout.rotation);
    correctionBoxes.value = JSON.stringify(layout.digit_boxes || []);
    originalCorrection = correctionEditor.current();
    correctionEditor.setBoxes(originalCorrection);
    correctionEditor.select(last ? correctionPosition.options.length - 1 : 0);
    correctionPreview.hidden = false;
    correctionStatus.textContent = '';
    correctionPosition.focus();
  }} catch {{
    correctionStatus.textContent = 'Kein passendes Kamerabild verfügbar. Warte auf eine reguläre Prüfung.';
  }} finally {{
    correctionBusy = false;
    updateCorrectionControls();
  }}
}}
correctionOpen.addEventListener('click', () => openDigitCorrection());
document.querySelector('#close-digit-correction').addEventListener('click', () => {{ if (!correctionBusy) correctionDialog.close(); }});
correctionDialog.addEventListener('cancel', event => {{ if (correctionBusy) event.preventDefault(); }});
correctionPosition.addEventListener('change', () => {{
  correctionEditor.select(Number(correctionPosition.value));
  correctionStatus.textContent = '';
  updateCorrectionControls();
}});
correctionPreview.addEventListener('digit-edit', updateCorrectionControls);
for (const button of correctionPreview.querySelectorAll('[data-box-move], [data-box-scale]')) {{
  button.addEventListener('click', () => {{
    const step = Number(button.dataset.boxScale || 0) * 10;
    const [x, y] = (button.dataset.boxMove || '0,0').split(',').map(Number);
    const index = Number(correctionPosition.value);
    const boxes = correctionEditor.current();
    const [left, top, right, bottom] = boxes[index];
    if (step) {{
      const resized = [Math.max(0, left - step), Math.max(0, top - step),
        Math.min(1000, right + step), Math.min(1000, bottom + step)];
      if (resized[2] - resized[0] >= 10 && resized[3] - resized[1] >= 25) correctionEditor.replace(index, resized);
    }} else {{
      correctionEditor.edit(boxes, index, x * 10, y * 10, false);
    }}
  }});
}}
correctionUndo.addEventListener('click', () => {{
  const index = Number(correctionPosition.value);
  correctionEditor.replace(index, originalCorrection[index]);
  correctionStatus.textContent = '';
}});
async function submitDigitCorrection(action) {{
  const index = Number(correctionPosition.value);
  const sent = correctionBoxes.value;
  correctionBusy = true;
  correctionPreview.inert = action === 'save';
  updateCorrectionControls();
  correctionStatus.textContent = action === 'search' ? 'Die ausgewählte Ziffer wird gesucht …' : '';
  const fields = new URLSearchParams({{
    action, index, digit_boxes: sent, token: correctionLayout.token,
    image_kind: correctionSource.kind, image_version: correctionSource.version,
    csrf: document.querySelector('#auto-form input[name="csrf"]').value, lang,
    mode: document.querySelector('#auto-form input[name="mode"]').value,
  }});
  try {{
    const response = await fetch('ziffernrahmen', {{method: 'POST', body: fields}});
    if (response.redirected && action === 'save') {{
      location.assign(response.url);
      return;
    }}
    if (response.status === 409) {{
      correctionStatus.textContent = 'Bild oder Ausschnitt hat sich geändert. Öffne den Editor erneut.';
      return;
    }}
    if (!response.ok) throw new Error();
    const result = await response.json();
    if (!correctionDialog.open || correctionBoxes.value !== sent || Number(correctionPosition.value) !== index) return;
    if (result && correctionEditor.replace(index, result.box)) {{
      correctionStatus.textContent = 'Vorgeschlagener Rahmen. Gelesene Ziffer: ' + result.digit;
    }} else {{
      correctionStatus.textContent = 'Kein sicherer Vorschlag. Du kannst den Rahmen von Hand verschieben.';
    }}
  }} catch {{
    correctionStatus.textContent = 'Die Änderung konnte nicht verarbeitet werden.';
  }} finally {{
    correctionPreview.inert = false;
    correctionBusy = false;
    updateCorrectionControls();
  }}
}}
correctionSearch.addEventListener('click', () => submitDigitCorrection('search'));
correctionSave.addEventListener('click', () => submitDigitCorrection('save'));
function renderOcrCandidates(list, candidates) {{
  const evidence = {{
    accepted: 'Zwei Profile stimmen überein, Prüfung akzeptiert den Kandidaten',
    agreement: 'Zwei Profile stimmen überein, Vergleich offen',
    disagreement: 'Profile lesen unterschiedlich',
    unclear: 'Ziffer blieb offen',
  }};
  const key = JSON.stringify(candidates || []);
  if (list.dataset.candidates === key) return;
  list.dataset.candidates = key;
  list.replaceChildren(...(candidates || []).slice(0, 3).map(candidate => {{
    const item = document.createElement('li');
    const [left, top, right, bottom] = candidate.box;
    item.textContent = 'Ziffernposition ' + candidate.position + ' · ' + candidate.angle + '° · ' +
      'Rahmen im Ausschnitt (px) ' + left + ', ' + top + ' · ' + (right - left) + ' × ' +
      (bottom - top) + ' · ' + evidence[candidate.evidence];
    return item;
  }}));
  list.hidden = !list.children.length;
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
    const success = document.querySelector('#setup-success');
    success.hidden = !job.setup_success;
    const duration = document.querySelector('#setup-duration');
    duration.textContent = job.setup_success?.duration || '';
    duration.hidden = !duration.textContent;
    refreshCalibration(job.calibration);
    if (!success.hidden) calibrationNoticeUntil = 0;
    updateCalibrationNotice();
    const calibrating = ['waiting', 'testing'].includes(job.calibration?.state);
    correctionOpen.hidden = !job.digit_correction;
    correctionOpen.disabled = calibrating;
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
      'Versuche abgeschlossen: ' + done :
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
    const method = document.querySelector('#ocr-method');
    method.textContent = showManual || !job.automatic_preview ? '' : ({{
      shifted: 'Die fehlende Ziffer wurde im verschobenen Rahmen direkt gelesen.',
      composed: 'Ziffern aus übereinstimmenden OCR-Versuchen zusammengesetzt.',
      anchored: 'Unveränderliche führende Stellen aus dem zuletzt bestätigten Stand ergänzt.',
    }}[job.ocr_method] || '');
    method.hidden = !method.textContent;
    const candidateList = document.querySelector('#ocr-candidates');
    renderOcrCandidates(candidateList, showManual || !job.automatic_preview ? [] : job.ocr_candidates);
    document.querySelector('#ocr-candidate-details').hidden = candidateList.hidden;
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
  activateTab('tools');
  manualTestArea.hidden = false;
  manualPanel.open = true;
  manualPanel.scrollIntoView({{block: 'nearest'}});
}});
document.querySelector('#calibration-manual-digit').addEventListener('click', () => openDigitCorrection(true));
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
  activateTab('tools');
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
function renderOdometer(reading) {{
  const box = document.querySelector('#meter-odometer');
  const text = String(reading || '').trim();
  if (box.dataset.rendered === text) return;
  box.dataset.rendered = text;
  box.setAttribute('aria-label', (lang === 'en' ? 'Meter reading ' : 'Zählerstand ') + (text || '–'));
  if (!/[0-9?]/.test(text)) {{
    const empty = document.createElement('span');
    empty.className = 'odometer-empty';
    empty.textContent = lang === 'en' ? 'No reading yet' : 'Noch kein Zählerstand';
    box.replaceChildren(empty);
    return;
  }}
  const [whole, fraction = ''] = text.replace(',', '.').split('.');
  const roller = (char, isFraction) => {{
    const cell = document.createElement('span');
    cell.className = 'roller' + (isFraction ? ' fraction' : '') + (/[0-9]/.test(char) ? '' : ' unclear');
    cell.textContent = char;
    return cell;
  }};
  const cells = Array.from(whole, char => roller(char, false));
  if (fraction) {{
    const separator = document.createElement('span');
    separator.className = 'separator';
    separator.textContent = lang === 'en' ? '.' : ',';
    cells.push(separator, ...Array.from(fraction, char => roller(char, true)));
  }}
  const unit = document.createElement('span');
  unit.className = 'unit';
  unit.textContent = 'm³';
  box.replaceChildren(...cells, unit);
}}
function syncHero() {{
  renderOdometer(document.querySelector('#automatic-ocr').textContent);
  const chip = document.querySelector('#hero-status');
  const tone = document.querySelector('#paused-notice').hidden ? (automaticBanner.dataset.tone || '') : 'warning';
  const labels = lang === 'en'
    ? {{ok: 'Running', notice: 'Running', warning: 'Needs attention', problem: 'Problem'}}
    : {{ok: 'Läuft', notice: 'Läuft', warning: 'Bitte prüfen', problem: 'Problem'}};
  const busy = document.querySelector('.activity-status')?.dataset.state === 'working';
  let label = !document.querySelector('#paused-notice').hidden ? (lang === 'en' ? 'Paused' : 'Pausiert')
    : (labels[tone] || (busy ? (lang === 'en' ? 'Checking …' : 'Prüft …') : '–'));
  if (staleView) label = lang === 'en' ? 'Not current' : 'Nicht aktuell';
  if (chip.textContent !== label) chip.textContent = label;
  chip.dataset.tone = staleView ? 'stale' : tone;
  document.querySelector('#meter-hero').classList.toggle('is-stale', Boolean(staleView));
  const note = document.querySelector('#hero-digit-note');
  const reading = (document.querySelector('#automatic-ocr').textContent || '').trim().replace(',', '.');
  const [wholeDigits, fractionDigits = ''] = reading.split('.');
  const position = wholeDigits.length + fractionDigits.length;
  let noteText = '', noteState = '';
  if (/[0-9?]/.test(reading) && lastDigitSearching) {{
    const minutesLeft = lastDigitProgress ? Math.max(1, Math.ceil(lastDigitProgress.seconds / 60)) : 0;
    const maxMinutes = lastDigitProgress ? Math.round(lastDigitProgress.duration / 60) : 0;
    if (/[0-9]$/.test(fractionDigits)) {{
      noteText = lang === 'en' ? 'Optimisation running: all digits are read, the app is fine-tuning the frames.'
        : 'Optimierung läuft: Alle Ziffern sind gelesen, die App stimmt die Rahmen noch fein ab.';
      noteState = 'optimizing';
    }} else {{
      noteText = lang === 'en' ? `The ${{position}}th digit is being searched in the background.`
        : `Die ${{position}}. Ziffer wird im Hintergrund gesucht.`;
      noteState = 'searching';
    }}
    if (minutesLeft) noteText += lang === 'en'
      ? ` At most ${{minutesLeft}} of ${{maxMinutes}} min left.`
      : ` Noch höchstens ${{minutesLeft}} von ${{maxMinutes}} min.`;
  }} else if (comparedDecimals !== null && configuredDecimals !== null && comparedDecimals < configuredDecimals) {{
    const at = lastDigitSearchAt && lastDigitSearchAt * 1000 > Date.now()
      ? new Date(lastDigitSearchAt * 1000).toLocaleTimeString(lang === 'en' ? 'en-GB' : 'de-DE', {{hour: '2-digit', minute: '2-digit'}})
      : '';
    noteText = lang === 'en'
      ? `Temporarily only ${{comparedDecimals}} decimal places are compared (setting: ${{configuredDecimals}}). `
        + (at ? `The search for the ${{position}}th digit starts at about ${{at}}.` : `The background search for the ${{position}}th digit is retried automatically.`)
      : `Vorübergehend werden nur ${{comparedDecimals}} Nachkommastellen verglichen (eingestellt: ${{configuredDecimals}}). `
        + (at ? `Die Suche nach der ${{position}}. Ziffer beginnt gegen ${{at}} Uhr.` : `Die Suche nach der ${{position}}. Ziffer wird automatisch wiederholt.`);
    noteState = 'skipped';
  }} else if (fractionDigits.endsWith('?') && comparedDecimals !== null && comparedDecimals < fractionDigits.length) {{
    noteText = lang === 'en'
      ? `The ${{position}}th digit is not compared (setting: ${{comparedDecimals}} decimal places).`
      : `Die ${{position}}. Ziffer wird nicht verglichen (eingestellt: ${{comparedDecimals}} Nachkommastellen).`;
    noteState = 'skipped';
  }}
  if (partialEighthDigit && configuredDecimals === 3 && lastDigitSearching) {{
    noteText = (lang === 'en' ? 'Configured: 3 decimal places, currently 2 verified. '
      : 'Eingestellt: 3 Nachkommastellen, aktuell 2 geprüft. ') + noteText;
  }}
  if (note.textContent !== noteText) note.textContent = noteText;
  note.dataset.state = noteState;
  note.hidden = !noteText;
  const searchProgress = document.querySelector('#hero-search-progress');
  searchProgress.hidden = !(['searching', 'optimizing'].includes(noteState) && lastDigitProgress);
  if (!searchProgress.hidden) {{
    searchProgress.max = lastDigitProgress.duration;
    searchProgress.value = lastDigitProgress.elapsed;
  }}
  const fractionRollers = document.querySelectorAll('#meter-odometer .roller.fraction');
  fractionRollers.forEach((roller, index) => roller.classList.toggle(
    'searching', noteState === 'searching' && index === fractionRollers.length - 1));
  for (const [from, to] of [['#countdown', '#hero-countdown'], ['#automatic-last-check', '#hero-last-check']]) {{
    const value = document.querySelector(from).textContent;
    const target = document.querySelector(to);
    if (target.textContent !== value) target.textContent = value;
  }}
}}
syncHero(); setInterval(syncHero, 1000);
const ignoreWarning = document.querySelector('#ignore-automatic-warning');
const preferenceKey = automaticBanner.dataset.preferenceKey;
const anonymousPreferenceKey = '{anonymous_banner_key}';
let ignoredIncident = '';
try {{
  ignoredIncident = (preferenceKey ? localStorage : sessionStorage).getItem(preferenceKey || anonymousPreferenceKey) || '';
}} catch (_) {{ /* Storage is optional. */ }}
function updateBannerVisibility() {{
  const ignored = Boolean(automaticBanner.dataset.incident) && automaticBanner.dataset.incident === ignoredIncident;
  automaticBanner.hidden = ignored || (automaticStatusFailures > 0 && routineOk);
}}
ignoreWarning.addEventListener('click', () => {{
  ignoredIncident = automaticBanner.dataset.incident;
  try {{
    (preferenceKey ? localStorage : sessionStorage).setItem(preferenceKey || anonymousPreferenceKey, ignoredIncident);
  }} catch (_) {{ /* Keep the choice for the current view. */ }}
  updateBannerVisibility();
}});
updateBannerVisibility();

const consumptionFormat = new Intl.NumberFormat(lang, {{maximumFractionDigits: 3}});
function renderConsumption(data) {{
  if (!data) return;
  function volume(bucket) {{
    if (bucket?.litres == null) return '–';
    const amount = consumptionFormat.format(bucket.litres / 1000) + ' m³';
    return (bucket.estimated ? '≈ ' : '') + amount + (bucket.partial ? ' · teilweise' : '');
  }}
  document.querySelector('#consumption-hour').textContent = volume(data.hours[0]);
  document.querySelector('#consumption-day').textContent = volume(data.days[0]);
  const available = [...data.hours, ...data.days].some(bucket => bucket.litres != null);
  const chart = document.querySelector('#consumption-chart');
  const chartKey = JSON.stringify(data.hours);
  chart.hidden = document.querySelector('#consumption-chart-axis').hidden = !data.hours.some(bucket => bucket.litres != null);
  if (!chart.hidden && chart.dataset.values !== chartKey) {{
    const hours = data.hours.slice().reverse();
    const peak = Math.max(1, ...hours.map(bucket => bucket.litres || 0));
    chart.replaceChildren(...hours.map(bucket => {{
      const bar = document.createElement('span');
      bar.title = bucket.label + ' · ' + volume(bucket);
      bar.dataset.empty = String(bucket.litres == null);
      bar.dataset.estimated = String(Boolean(bucket.estimated));
      bar.style.height = bucket.litres == null ? '' : Math.max(3, 100 * bucket.litres / peak) + '%';
      return bar;
    }}));
    chart.dataset.values = chartKey;
  }}
  document.querySelector('#consumption-empty').hidden = available;
  document.querySelector('#consumption-details').hidden = !available;
  for (const [id, buckets] of [['hours', data.hours], ['days', data.days]]) {{
    const list = document.querySelector('#consumption-' + id);
    const key = JSON.stringify(buckets);
    if (list.dataset.values === key) continue;
    list.replaceChildren(...buckets.map(bucket => {{
      const row = document.createElement('li');
      const label = document.createElement('span');
      const value = document.createElement('span');
      label.textContent = bucket.label;
      value.textContent = volume(bucket);
      row.append(label, value);
      return row;
    }}));
    list.dataset.values = key;
  }}
}}

const experimental = document.querySelector('#experimental');
const extraForm = document.querySelector('#experimental-form');
const extraStatus = document.querySelector('#experimental-status');
async function refreshExperimental() {{
  if (!experimental.open) return;
  const reply = await fetch('experimentelle-zaehler', {{cache:'no-store'}});
  if (!reply.ok) return;
  const rows = await reply.json();
  const grid = document.querySelector('#experimental-meter-list');
  const snapshot = JSON.stringify(rows);
  if (grid.dataset.snapshot === snapshot) return;
  grid.dataset.snapshot = snapshot;
  const states = {{
    waiting: 'Wartet auf Daten', ok: 'Aktuell', stale: 'Wartet auf neuen Sensorwert',
    reset: 'Neuer Ausgangswert gespeichert', reset_pending: 'Möglicher Zählerrücksprung',
    unavailable: 'Kein gültiger Sensorwert',
  }};
  grid.replaceChildren(...rows.map(meter => {{
    const card = document.createElement('article');
    card.className = 'experimental-meter-card';
    const heading = document.createElement('strong');
    heading.textContent = meter.label;
    const status = document.createElement('p');
    status.textContent = states[meter.status] + ' · ' + meter.id;
    const last = document.createElement('p');
    const value = amount => amount == null ? '–' : consumptionFormat.format(amount / 1000) + ' ' + meter.unit;
    last.textContent = 'Letzte Ablesung ' + value(meter.reading) +
      (meter.timestamp ? ' · ' + formatStamp(meter.timestamp) : '');
    const usage = document.createElement('p');
    const format = bucket => (bucket.estimated ? '≈ ' : '') + value(bucket.litres) +
      (bucket.partial ? ' · teilweise' : '');
    usage.textContent = 'Diese Stunde ' + format(meter.usage.hours[0]) + ' · Heute ' + format(meter.usage.days[0]);
    const chart = document.createElement('div');
    chart.className = 'experimental-hour-chart';
    chart.setAttribute('role', 'img');
    chart.setAttribute('aria-label', 'Verbrauch je Stunde');
    const hours = meter.usage.hours.slice().reverse();
    const max = Math.max(1, ...hours.map(entry => entry.litres || 0));
    for (const entry of hours) {{
      const bar = document.createElement('span');
      bar.title = entry.label + ' · ' + format(entry);
      bar.style.height = entry.litres === null ? '0%' : Math.max(3, 100 * entry.litres / max) + '%';
      chart.append(bar);
    }}
    const days = document.createElement('details');
    const daysLabel = document.createElement('summary');
    daysLabel.textContent = 'Verlauf nach Tag';
    days.append(daysLabel);
    for (const entry of meter.usage.days) {{
      const day = document.createElement('p');
      day.textContent = entry.label + ' · ' + format(entry);
      days.append(day);
    }}
    card.append(heading, status, last, usage, chart, days);
    return card;
  }}));
}}
experimental.addEventListener('toggle', () => refreshExperimental().catch(() => {{}}));
extraForm.addEventListener('submit', async event => {{
  event.preventDefault();
  try {{
    const response = await fetch('experimentelle-zaehler', {{
      method: 'POST', body: new URLSearchParams(new FormData(extraForm)),
    }});
    if (!response.ok) throw Error();
    extraStatus.textContent = 'Zähler gespeichert.';
    await refreshExperimental();
  }} catch (_) {{
    extraStatus.textContent = 'Bitte Sensor-IDs und Prüfintervalle überprüfen.';
  }}
}});
function showStale(kind) {{
  staleView = kind;
  const box = document.querySelector('#hero-stale');
  box.hidden = !kind;
  const text = {{
    offline: lang === 'en' ? 'No connection to the app – this view is not current. It reloads as soon as the app answers again.'
      : 'Keine Verbindung zur App – die Anzeige ist nicht aktuell. Sie lädt neu, sobald die App wieder antwortet.',
    render: lang === 'en' ? 'This view could not be updated completely. The error was written to the app log.'
      : 'Die Anzeige konnte nicht vollständig aktualisiert werden. Der Fehler steht im App-Protokoll.',
    restarted: lang === 'en' ? 'The app was restarted. Reloading …' : 'Die App wurde neu gestartet. Seite wird neu geladen …',
  }}[kind] || '';
  const target = document.querySelector('#hero-stale-text');
  if (target.textContent !== text) target.textContent = text;
  syncHero();
}}
document.querySelector('#reload-view').addEventListener('click', () => location.reload());
// A save confirmation is a one-time message: fade it out and drop it from the URL,
// so it does not linger or come back after the automatic reload.
setTimeout(() => {{
  document.querySelectorAll('.save-notice').forEach(notice => {{ notice.hidden = true; }});
  const url = new URL(location.href);
  if (url.searchParams.has('saved')) {{
    url.searchParams.delete('saved');
    history.replaceState(null, '', url.pathname + (url.searchParams.size ? '?' + url.searchParams : ''));
  }}
}}, 10000);
document.querySelector('#debug-log').addEventListener('toggle', async (event) => {{
  if (!event.target.open) return;
  const target = document.querySelector('#debug-log-text');
  try {{
    const response = await fetch('debug-protokoll?limit=40', {{cache: 'no-store'}});
    const text = response.ok ? await response.text() : '';
    target.textContent = text.trim().split(String.fromCharCode(10)).reverse().join(String.fromCharCode(10))
      || (lang === 'en' ? 'No entries yet.' : 'Noch keine Einträge.');
  }} catch (_) {{
    target.textContent = lang === 'en' ? 'Log could not be loaded.' : 'Protokoll konnte nicht geladen werden.';
  }}
}});
async function refreshAutomatic() {{
  let refreshDelay = 15000;
  let sample;
  try {{
    const response = await fetch('automatic?lang=' + lang, {{cache: 'no-store'}});
    if (!response.ok) throw new Error();
    sample = await response.json();
  }} catch (_) {{
    automaticStatusFailures += 1;
    updateBannerVisibility();
    const status = document.querySelector('.activity-status');
    document.querySelector('#automatic-progress').hidden = true;
    document.querySelector('#automatic-activity-details').hidden = true;
    status.dataset.state = 'unknown';
    const unavailable = automaticStatusFailures >= 3;
    status.dataset.offline = unavailable ? 'true' : 'pending';
    if (unavailable) showStale('offline');
    document.querySelector('#automatic-activity').textContent = lang === 'en'
      ? unavailable
        ? 'No connection to the app for about 45 seconds. Retrying…'
        : 'Connection to the app briefly interrupted. Retrying…'
      : unavailable
        ? 'Seit etwa 45 Sekunden keine Verbindung zur App. Neuer Versuch läuft …'
        : 'Verbindung zur App kurz unterbrochen. Neuer Versuch läuft …';
    setTimeout(refreshAutomatic, 5000);
    return;
  }}
  if (sample.instance && sample.instance !== pageInstance) {{
    showStale('restarted');
    setTimeout(() => location.reload(), 1500);
    return;
  }}
  try {{
    automaticStatusFailures = 0;
    routineOk = sample.routine_ok;
    if (routineOk) calibrationNoticeUntil = 0;
    updateCalibrationNotice();
    next = sample.next_check;
    renderConsumption(sample.consumption);
    comparedDecimals = Number.isInteger(sample.decimals) ? sample.decimals : null;
    configuredDecimals = Number.isInteger(sample.configured_decimals) ? sample.configured_decimals : comparedDecimals;
    lastDigitSearchAt = typeof sample.last_digit_search_at === 'number' ? sample.last_digit_search_at : null;
    partialEighthDigit = sample.partial_eighth_digit === true;
    if (experimental.open) refreshExperimental().catch(() => {{}});
    document.querySelector('#paused-notice').hidden = !sample.paused;
    document.querySelector('#pause-auto-form').hidden = sample.paused;
    document.querySelector('#start-automatic').disabled = !sample.can_start_automatic;
    const comparison = document.querySelector('#comparison-suggestion');
    comparison.hidden = sample.precision_suggestion == null;
    comparison.elements.decimals.value = sample.precision_suggestion ?? '';
    comparison.querySelector('button').textContent = sample.precision_suggestion_label;
    automaticBanner.dataset.tone = sample.tone;
    automaticBanner.dataset.incident = sample.incident;
    document.querySelector('#automatic-interval-hint').hidden = !(sample.interval_hint && sample.tone !== 'ok');
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
    document.querySelector('#setup-start-actions').hidden = sample.activity_state !== 'setup_wait' || activityStatus.hidden;
    activityStatus.dataset.routineOk = String(routineOk);
    const activityText = document.querySelector('#automatic-activity');
    if (activityText.textContent !== sample.activity) activityText.textContent = sample.activity;
    const progress = document.querySelector('#automatic-progress');
    progress.hidden = !['queued', 'working'].includes(sample.activity_state);
    renderOcrCandidates(document.querySelector('#live-ocr-candidates'), sample.activity_candidates);
    const checkDetails = document.querySelector('#automatic-activity-details');
    checkDetails.hidden = progress.hidden;
    if (checkDetails.hidden) checkDetails.open = false;
    document.querySelector('#automatic-attempt-info').textContent = sample.activity_total > 0
      ? 'Versuche abgeschlossen: ' + (sample.activity_completed || 0) + ' von ' + sample.activity_total
      : 'Die Ziffernerkennung beginnt, sobald das Bild bereitsteht.';
    document.querySelector('#automatic-live-reading').textContent = /[0-9]/.test(sample.activity_reading || '')
      ? 'Zuletzt gelesen (noch unbestätigt): ' + sample.activity_reading
      : 'Bisher keine Ziffer gelesen.';
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
    if (staleView) showStale('');
  }} catch (error) {{
    const message = String(error?.stack || error).split(String.fromCharCode(10)).slice(0, 2).join(' ');
    console.error(error);
    showStale('render');
    if (message !== reportedRenderError) {{
      reportedRenderError = message;
      fetch('anzeigefehler?m=' + encodeURIComponent(message), {{cache: 'no-store'}}).catch(() => {{}});
    }}
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


def reflection_setup_preview(content, whole, fraction, polarity):
    if not 1 <= whole <= 9 or not 0 <= fraction <= 3 or polarity not in POLARITIES:
        raise ValueError("Invalid meter format")
    with Image.open(BytesIO(content)) as image:
        image.load()
        layout = next(layouts(image, None, {"integer_digits": whole, "fraction_digits": fraction}, 0), None)
        if layout is None:
            raise ValueError("No digit row found")
        register = turn_crop(crop_register(image, layout.box), layout.rotation)
    boxes = layout.digit_boxes
    count = whole + fraction
    if len(boxes) != count:
        split = max(whole * 10, min(1000 - fraction * 10, round(1000 * layout.width / register.width)))
        edges = [round(i * split / whole) for i in range(whole + 1)]
        edges.extend(split + round((1000 - split) * i / fraction) for i in range(1, fraction + 1))
        boxes = [(left, 0, right, 1000) for left, right in zip(edges, edges[1:])]
    boxes = digit_box_settings(boxes, count)
    deadline = time.monotonic() + 4
    observed = []
    for box in scale_digit_boxes(boxes, register.size):
        if time.monotonic() >= deadline:
            observed.append(None)
            continue
        digit = register.crop(box)
        try:
            votes = [read_register(digit, polarity != "dark", 1, force_polarity=polarity != "auto",
                                   profile=profile, deadline=deadline) for profile in OCR_PROFILES[:2]]
        except (OSError, ValueError, subprocess.SubprocessError):
            observed.append(None)
            continue
        observed.append(bool(votes[0] and votes[0] == votes[1]))
    readable = [index for index, result in enumerate(observed) if result is True]
    suspected = ([index for index in range(readable[0] + 1, readable[-1]) if observed[index] is False][:2]
                 if len(readable) >= 2 else [])
    with BytesIO() as encoded:
        register.convert("RGB").save(encoded, "JPEG")
        jpeg = base64.b64encode(encoded.getvalue()).decode("ascii")
    return {"image": jpeg, "layout": {**layout.settings(), "digit_boxes": boxes}, "suspected": suspected}


def start_panel(
    history_path, current_image, good_image, requested, default_decimals, default_attempts,
    get_auto_rules, save_auto_rules, default_crop, default_width, test_image,
    load_language_modes, save_language_modes, get_delivery, save_delivery, get_source, save_source,
    wake_worker=None, *, address=("0.0.0.0", 8099), test_source_image=None, automatic_preview=None,
    request_factory_reset=None, get_reset_status=None, skip_setup=None, get_activity=None,
    get_auto_paused=None, save_auto_paused=None, discover_sources=None,
    settings_lock=None, get_calibration=None, control_calibration=None, get_calibration_image=None,
    has_calibration_backup=None, get_wizard_image=None, statistics_zone=timezone.utc, experimental_meters=None,
    can_start_automatic=None, start_automatic_check=None,
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
    digit_search_lock = Lock()
    demo_lock = Lock()
    def read_auto_rules():
        return {"integer_digits": 5, "fraction_digits": 3, "meter_display": "rollers",
                "fallback_value": "", "fallback_time": "", "digit_boxes": [], **get_auto_rules()}

    def digit_correction_settings(rules, source):
        if rules["crop_mode"] != "manual":
            return None
        layout = {key: rules.get(key) for key in ("crop", "width", "rotation", "digit_boxes",
                                                   "integer_digits", "fraction_digits", "polarity")}
        layout["rotation"] = layout["rotation"] or 0
        layout["token"] = setup_source_id([source, layout, rules.get("crop_revision")])
        return layout

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
        confirmed = auto_rules.get("reflection_confirmed_id") == estimate_id
        anchor_time = (history.get("reflection_anchor") or {}).get("time")
        # An unconfirmed suggestion is outdated once verified readings have moved on for an hour.
        if (not confirmed and type(anchor_time) in (int, float) and type(estimate.get("time")) in (int, float)
                and anchor_time - estimate["time"] > REFLECTION_OFFER_SECONDS):
            return None
        return {**estimate, "id": estimate_id, "confirmed": confirmed}

    def geometry_warning(history, auto_rules, language):
        recovery = history.get("geometry_recovery", {})
        if recovery.get("scheduled_at") and recovery.get("first_failure_at"):
            message = "Die Ziffernerkennung ist seit mindestens zwei Stunden gestört. Bitte Bildausschnitt prüfen."
            return EN_UI[message] if language == "en" else message
        failures = recovery.get("failures", 0)
        if not failures:
            return ""
        if not auto_rules.get("self_repair_enabled"):
            message = "Automatische Neukalibrierung ist ausgeschaltet."
            return EN_UI[message] if language == "en" else message
        message = "Die App beobachtet, ob die Erkennungsprobleme anhalten."
        return EN_UI[message] if language == "en" else message

    def setup_success(history, rules, source, language):
        if not setup_deadlines(rules, source)[0]:
            return None
        completed = rules.get("setup_success") or rules["setup_completed"]
        if completed.get("source") != setup_source_id(source):
            completed = rules["setup_completed"]
        if "duration_seconds" not in completed:
            return None
        finished_check = history.get("automatic_completed_at")
        if (type(finished_check) in (int, float) and finished_check > completed["time"]
                and time.time() - completed["time"] >= 5):
            return None
        elapsed = completed["duration_seconds"]
        details = []
        if type(elapsed) is int and elapsed >= 0:
            minutes, seconds = divmod(elapsed, 60)
            duration = f"{minutes} min {seconds:02d} s" if minutes else f"{seconds} s"
            label = "Setup duration" if language == "en" else "Einrichtungsdauer"
            details.append(f"{label} · {duration}")
        counts = (("frames_tested", "Frame attempts", "Rahmenversuche"),
                  ("images_checked", "Images checked", "Geprüfte Bilder"))
        for key, english, german in counts:
            value = completed.get(key)
            if type(value) is int and value >= 0:
                details.append(f"{english if language == 'en' else german} {value}")
        return {"duration": " · ".join(details)}

    def automatic_summary(history, language, auto_rules):
        source, setup_pending = get_source()
        stabilizing_until, optimization_until = setup_deadlines(auto_rules, source)
        partial_eighth_digit = stationary_partial_active(auto_rules, source)
        decimals = 2 if partial_eighth_digit else auto_rules["decimals"]
        now = time.time()
        interval = stabilization_interval(auto_rules.get("interval_minutes", DEFAULT_INTERVAL_MINUTES),
                                          stabilizing_until, now)
        reschedule_next_check(history, interval)
        paused = bool(get_auto_paused()) if get_auto_paused else False
        detail = history.get("check_detail")
        precision_pending = any(history.get(key, value) != value for key, value in (
            ("comparison_decimals", decimals),
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
            tone, heading, icon = "notice", "Prüfung bestanden mit Hinweis", ""
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
            if not prolonged and history.get("failure_attempts", 0) < QUIET_FAILURES:
                # A single failed check usually resolves itself with the next roller position.
                # Show it quietly; only repeated failures get the prominent warning.
                tone, icon = "notice", ""
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
            elif history.get("check_detail") == MOVING_DIGIT_NOTICE:
                heading = "Rolle drehte sich gerade"
                detail = history["check_detail"] if language == "de" else english_result(history["check_detail"], status)
            elif history.get("check_detail") in (LOWER_PENDING, LOWER_READING, EXCESSIVE_INCREASE):
                heading = "Ablesung passt nicht zum letzten Stand"
                detail = history["check_detail"] if language == "de" else english_result(history["check_detail"], status)
            elif history.get("check_detail") == LAST_DIGIT_NOTICE:
                heading = "Letzte Nachkommastelle unsicher"
                detail = LAST_DIGIT_NOTICE if language == "de" else EN_UI[LAST_DIGIT_NOTICE]
            elif status == "difference":
                heading = "Ablesung und Vergleichswert weichen ab" if not prolonged else heading
                instructions = ("Vergleiche beide Werte mit dem Stand direkt am Zähler."
                                if prolonged or paused else
                                "Die App prüft automatisch erneut. Bleibt der Unterschied, vergleiche beide Werte mit dem Stand direkt am Zähler.")
                detail = instructions if language == "de" else EN_UI[instructions]
        if not precision_pending and history.get("check_detail") in (FRAME_OFF_NOTICE, FRAME_OFF_WAIT_NOTICE):
            heading = "Rahmen der letzten Stelle sitzt daneben"
            detail = (history["check_detail"] if language == "de"
                      else english_result(history["check_detail"], status))
            if tone == "ok":
                tone = "neutral"
        if language == "en":
            heading = EN_UI[heading]
        adjustment = history.get("ocr_rotation_adjustment", 0)
        if not precision_pending and status in ("match", "ocr_only") and type(adjustment) is int and adjustment:
            rotation_note = (f"Read with an image rotation of {adjustment:+d}°."
                             if language == "en" else f"Mit Bilddrehung von {adjustment:+d}° gelesen.")
            detail = " ".join(part for part in (detail, rotation_note) if part)
        grace = (not precision_pending and history.get("setup_first_check_unclear")
                 and history.get("failure_attempts") == 1 and tone in ("warning", "notice"))
        if grace:
            tone, icon, incident = "neutral", "", ""
            heading = ("First automatic check still unclear" if language == "en" else
                       "Erste automatische Prüfung noch unklar")
            detail = ("The app will try again with a fresh image." if language == "en" else
                      "Die App prüft mit einem frischen Bild erneut.")
        routine_ok = (tone == "ok" and not paused and not setup_pending
                      and history.get("source_connection_status") != "error")
        if routine_ok and partial_eighth_digit:
            # Normal operation in the seven-digit mode: no warning. The hero note
            # above the reading already explains the eighth digit.
            heading = ("All good. The 8th digit is still being confirmed." if language == "en"
                       else "Alles OK. Die 8. Ziffer wird noch abgesichert.")
            detail = ""
        elif routine_ok:
            heading = "All good. Automatic checks running." if language == "en" else "Alles OK. Automatik läuft."
            detail = ""
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
            next_at = history.get("next_check_at")
            clock = (datetime.fromtimestamp(next_at, statistics_zone).strftime("%H:%M")
                     if type(next_at) in (int, float) and next_at > 0 else "")
            recovery_notice = (
                f"{failure_attempts} automatic checks failed. Waiting for a higher meter reading or a new image."
                + (f" Next attempt at about {clock}." if clock else "")
                if language == "en" else
                f"{failure_attempts} automatische Prüfungen fehlgeschlagen. Es wird auf einen höheren Zählerstand "
                "oder ein neues Bild gewartet." + (f" Nächster Versuch gegen {clock} Uhr." if clock else "")
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
        if activity.get("state") == "setup_wait":
            tone, icon, incident, routine_ok = "neutral", "", "", False
            heading = "Automatik wartet auf Einrichtung" if language == "de" else "Automatic checks are waiting for setup"
            detail, show_attempts, failure_attempts, recovery_notice = "", False, 0, ""
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
        source_key = source_check_key(source)
        precision_suggestion = (
            recommended_comparison_decimals(history, decimals, auto_rules["integer_digits"])
            if not precision_pending and not setup_pending and source.get("selected")
            and history.get("check_source", source_key) == source_key and activity.get("state") != "setup_wait" else None
        )
        if precision_suggestion:
            if language == "en":
                precision_label = f"Compare {precision_suggestion} decimal " + ("place" if precision_suggestion == 1 else "places")
            else:
                precision_label = f"Mit {precision_suggestion} " + ("Nachkommastelle" if precision_suggestion == 1 else "Nachkommastellen") + " vergleichen"
        else:
            precision_label = ""
        return {
            "detail": (detail if detail is not None else
                       "No automatic result yet." if language == "en" else "Noch kein automatisches Prüfergebnis."),
            "tone": tone, "heading": heading, "icon": icon, "routine_ok": routine_ok,
            "incident": incident,
            "ocr": str(history["ocr_value"]) if history.get("ocr_value") is not None else "–",
            "reference": str(history["last_reference"]) if history.get("last_reference") is not None else "–",
            "reference_time": history.get("last_reference_time"),
            "reference_is_fallback": history.get("last_reference_is_fallback", False),
            "image_time": history.get("last_epoch") or 0,
            "next_check": None if activity.get("state") == "setup_wait" else history.get("next_check_at"),
            "last_check": last_check_at(history),
            "last_match": history.get("last_match_at"),
            "readings": history.get("ocr_readings", []) if show_attempts else [],
            "failure_attempts": failure_attempts,
            "retry_suppressed": retry_suppressed,
            "recovery_notice": recovery_notice,
            "geometry_warning": geometry_warning(history, auto_rules, language) if now >= optimization_until else "",
            "stabilizing_until": stabilizing_until,
            "configured_decimals": auto_rules["decimals"],
            "interval_hint": bool(failure_attempts) and history.get("check_detail") in (RAW_ROW_UNCLEAR, MANUAL_ROW_UNCLEAR),
            "last_digit_search_at": (max(optimization_until, history.get("eighth_digit_retry_at") or 0)
                                     if decimals < auto_rules["decimals"] else None),
            "reflection_estimate": reflection_estimate,
            "reflection_live_estimate": (history.get("reflection_live_estimate")
                                        if auto_rules.get("reflection_estimate_enabled") else None),
            "reflection_suggestion": reflection_suggestion,
            "activity": activity.get("detail", "Wartet auf die nächste automatische Prüfung."),
            "activity_state": activity.get("state", "waiting"),
            "can_start_automatic": bool(can_start_automatic and can_start_automatic()),
            "precision_suggestion": precision_suggestion, "precision_suggestion_label": precision_label,
            "activity_completed": activity.get("completed"),
            "activity_total": activity.get("total"),
            "activity_reading": activity.get("reading"),
            "activity_candidates": activity.get("candidates"),
            "paused": paused,
            "source_connection": source_connection,
            "source_connection_state": history.get("source_connection_status", "unknown"),
            "decimals": history.get("comparison_decimals", default_decimals),
            "partial_eighth_digit": partial_eighth_digit,
            "eighth_digit_retry_at": history.get("eighth_digit_retry_at"),
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
            if path == "/debug-protokoll":
                try:
                    limit = max(1, min(600, int(query.get("limit", ["600"])[0])))
                except ValueError:
                    limit = 600
                self.reply(debug_log.read_text(limit).encode("utf-8"), "text/plain; charset=utf-8")
                return
            if path == "/anzeigefehler":
                message = re.sub(r"[^\w .,:;()'/<>=-]", "?", query.get("m", [""])[0])[:300]
                print(f"Anzeigefehler im Browser: {message}")
                self.reply(b"", "text/plain", 204)
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
                with rules_lock:
                    rules, source = read_auto_rules(), get_source()[0]
                    snapshot["digit_correction"] = digit_correction_settings(rules, source)
                history = read_history()
                snapshot["setup_success"] = setup_success(history, rules, source, language)
                snapshot["ocr_candidates"] = history.get("ocr_candidates", [])
                snapshot["ocr_method"] = history.get("ocr_method")
                snapshot["digit_correction_image"] = str(snapshot["current_image"] or "")
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
            if path == "/experimentelle-zaehler" and experimental_meters is not None:
                self.reply(json.dumps(experimental_meters.snapshot()).encode("utf-8"), "application/json")
                return
            if path not in ("/", "/automatic"):
                self.send_error(404)
                return
            history = read_history()
            auto_rules = read_auto_rules()
            if path == "/automatic":
                summary = automatic_summary(history, language, auto_rules)
                series = history.get("consumption_statistics", {})
                source_scope = setup_source_id(get_source()[0])
                if history.get("statistics_preserved_after_reset") and series.get("source"):
                    source_scope = series["source"] if source_scope != series["source"] else source_scope
                summary["consumption"] = consumption_statistics(
                    series, source_scope, time.time(), statistics_zone,
                )
                summary["instance"] = INSTANCE_ID
                payload = json.dumps(summary)
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
            extra_meters = experimental_meters.snapshot() if experimental_meters is not None else []
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
            values["automatic_routine_ok"] = json.dumps(summary["routine_ok"])
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
            success = setup_success(history, auto_rules, source, language)
            duration = success["duration"] if success else ""
            reset_state = query.get("reset", [""])[0]
            keep_reset_statistics = query.get("keep_statistics") == ["1"]
            if reset_state == "pending" and get_reset_status is not None:
                reset_state = get_reset_status()
                if reset_state not in ("pending", "done", "failed"):
                    reset_state = "failed"
            if reset_state not in ("pending", "done", "failed"):
                reset_state = ""
            reset_message = {
                "done": ("Werkseinstellungen wiederhergestellt. Verbrauchsstatistik und Gesamtverbrauch sind erhalten. Die Einrichtung öffnet sich erneut."
                         if keep_reset_statistics else "Werkseinstellungen wiederhergestellt. Die Einrichtung öffnet sich erneut."),
                "pending": "Werkreset läuft noch. Die Einrichtung öffnet sich, sobald er fertig ist.",
                "failed": "Werkreset konnte nicht vollständig ausgeführt werden.",
            }.get(reset_state, "")
            if language == "en" and reset_message:
                reset_message = EN_UI[reset_message]
            selected_tab = query.get("ui", [""])[0]
            settings_tab_active = (selected_tab == "settings" if selected_tab in ("settings", "overview", "tools") else
                                   saved in ("1", "crop", "notifications", "source", "setup-calibration") or setup_pending)
            tools_tab_active = not settings_tab_active and (
                selected_tab == "tools" or saved == "manual-crop"
                or query.get("test", [""])[0] in ("queued", "open", "busy"))
            saved_message = (
                "Ziffernrahmen gespeichert." if saved == "digit-frames" else
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
                start_automatic_hidden="" if start_automatic_check else "hidden",
                start_automatic_disabled="" if summary["can_start_automatic"] else "disabled",
                comparison_suggestion_hidden="" if summary["precision_suggestion"] else "hidden",
                suggested_decimals=summary["precision_suggestion"] or "",
                comparison_suggestion_label=html.escape(summary["precision_suggestion_label"]),
                automatic_progress_hidden="" if summary["activity_state"] in ("queued", "working") else "hidden",
                resume_setup_hidden="" if summary["activity_state"] == "setup_wait" else "hidden",
                automatic_tone=summary["tone"], automatic_heading=summary["heading"],
                automatic_icon=summary["icon"], automatic_incident=html.escape(summary["incident"]),
                banner_preference_key=f"{NAMESPACE}-ignored-warning-{user}" if user else "",
                anonymous_banner_key=f"{NAMESPACE}-ignored-warning",
                instance_id=INSTANCE_ID,
                ignore_hidden="" if summary["incident"] else "hidden",
                profile_script=scripts,
                extra_meter_config=html.escape("\n".join(
                    f"{meter['id']}, {meter['minutes']}" for meter in extra_meters
                )),
                extra_meter_open="open" if extra_meters else "",
                overview_hidden="hidden" if settings_tab_active or tools_tab_active else "",
                settings_hidden="" if settings_tab_active else "hidden",
                tools_hidden="" if tools_tab_active else "hidden",
                language_options=select_options({"auto": automatic, "de": "Deutsch", "en": "English"}, mode),
                settings_open="open" if saved in ("1", "crop", "crop-reset", "fallback") else "",
                fallback_saved_notice=auto_saved_notice if saved == "fallback" else "",
                calibration_preview_html=(translate_page(CALIBRATION_PREVIEW_HTML) if language == "en"
                                          else CALIBRATION_PREVIEW_HTML),
                calibration_skip_html=(translate_page(CALIBRATION_SKIP_HTML) if language == "en"
                                       else CALIBRATION_SKIP_HTML).format(language=language, mode=mode, csrf=csrf_token),
                setup_success_hidden="" if success else "hidden",
                setup_duration_hidden="" if duration else "hidden",
                setup_duration=html.escape(duration),
                calibration_saved_notice=auto_saved_notice if saved == "crop-restored" else "",
                calibration_hidden="" if control_calibration else "hidden",
                calibration_intensive_hidden="" if auto_rules["fraction_digits"] == 3 and auto_rules["decimals"] == 3 else "hidden",
                calibration_precision_notice=(
                    ("Setup confirms seven digits first. The third decimal can then be checked separately."
                     if language == "en" else
                     "Die Einrichtung bestätigt zuerst sieben Ziffern. Die dritte Nachkommastelle kann anschließend separat geprüft werden.")
                    if auto_rules["decimals"] == 3 else
                    ("Fewer than three decimal places selected. The last roller is skipped because it is not needed for the reading."
                     if language == "en" else
                     "Weniger als drei Nachkommastellen ausgewählt. Die letzte Rolle wird übersprungen, weil sie für die Ablesung nicht benötigt wird.")),
                wizard_initial_hidden="" if setup_pending else "hidden",
                wizard_precision_hidden="hidden" if setup_pending else "",
                wizard_precision_disabled="disabled" if setup_pending else "",
                geometry_warning_hidden="" if summary["geometry_warning"] else "hidden",
                geometry_warning_text=html.escape(summary["geometry_warning"]),
                calibration_restore_hidden="" if has_calibration_backup and has_calibration_backup() else "hidden",
                self_repair_checked="checked" if auto_rules.get("self_repair_enabled") else "",
                wizard_fine_alignment_checked="checked" if setup_pending or auto_rules.get("fine_alignment_enabled") else "",
                wizard_self_repair_checked="checked" if setup_pending or auto_rules.get("self_repair_enabled") else "",
                calibration_min=MIN_IMAGE_LIMIT, calibration_max=MAX_IMAGES,
                calibration_limit=calibration["limit"] if calibration else DEFAULT_LIMIT,
                setup_first_run=str(bool(setup_pending or reset_state == "done")).lower(),
                precision_hidden="" if auto_rules["fraction_digits"] == 3 else "hidden",
                precision_checked="checked" if auto_rules["decimals"] == 3 else "",
                intensive_agreement=auto_rules.get("intensive_agreement", DEFAULT_INTENSIVE_AGREEMENT),
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
                     if int(key) <= min(2, auto_rules["fraction_digits"])}, str(min(2, auto_rules["decimals"]))),
                wizard_crop_options=radio_options("crop_mode", {
                    **({"learn": "Automatic setup (recommended)" if language == "en"
                        else "Automatische Selbsteinrichtung (empfohlen)"} if control_calibration else {}),
                    "auto": CROP_MODES_EN["auto"] if language == "en" else CROP_MODES["auto"],
                    "manual": "Set up manually" if language == "en" else "Manuell einrichten",
                }, "learn" if control_calibration and (setup_pending or summary["activity_state"] == "setup_wait")
                   else auto_rules["crop_mode"]),
                wizard_digit_boxes=html.escape(json.dumps(auto_rules["digit_boxes"]), quote=True),
                fallback_value=html.escape(auto_rules["fallback_value"], quote=True),
                fallback_time=html.escape(auto_rules["fallback_time"], quote=True),
                wizard_saved_notice=(
                    auto_saved_notice + (
                        '<button type="button" id="setup-image-test">' +
                        ("Test your own image" if language == "en" else "Eigenes Bild testen") +
                        '</button>' if saved == "setup" else ""
                    ) if saved in ("setup", "setup-calibration") else ""
                ),
                manual_open="open" if test == "open" else "",
                digit_correction_hidden="" if auto_rules["crop_mode"] == "manual" else "hidden",
                digit_correction_notice=auto_saved_notice if saved == "digit-frames" else "",
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
                    {key: label for key, label in comparable_decimals.items() if int(key) <= 2},
                    str(min(2, auto_rules["decimals"])),
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
                            "/benachrichtigungen", "/bildquelle", "/einrichtung", "/einrichtungsbild",
                            "/einrichtung-ueberspringen", "/werkreset", "/automatik-pause",
                            "/spiegelungs-hinweis-ausblenden", "/ergaenzte-ziffer-bestaetigen", "/selbsteinrichtung", "/fallback", "/ziffernrahmen", "/zaehler-demo", "/experimentelle-zaehler", "/automatik-jetzt", "/vergleichsgenauigkeit"):
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
                values = form.get("keep_statistics", ["0"])
                if len(values) != 1 or values[0] not in ("0", "1"):
                    problem(400)
                    return
                keep_statistics = values[0] == "1"
                result = (request_factory_reset(keep_statistics=keep_statistics)
                          if request_factory_reset is not None else "failed")
                if result not in ("done", "pending", "failed"):
                    result = "failed"
                self.redirect("?reset=" + result + "&ui=settings"
                              + ("&keep_statistics=1" if keep_statistics else "") + keep_mode)
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
                return_query = parse_qs(urlsplit(self.path).query)
                test_open = return_query.get("test") == ["open"]
                return_tab = return_query.get("ui", [""])[0]
                params = (["test=open"] if test_open else []) + (
                    ["ui=" + return_tab] if return_tab in ("settings", "tools") else []) + (
                    ["mode=" + mode] if keep_mode else [])
                self.redirect("?" + "&".join(params) if params else "")
                return
            def field(name, default=""):
                value, = form.get(name, [default])
                return value

            def selected_source_mode(default=""):
                selected = field("source_mode", default)
                return "slfork_camera" if selected == "slfork" and field("esp_camera_only") == "1" else selected

            if path == "/automatik-jetzt":
                if not start_automatic_check or not start_automatic_check():
                    problem(409, "Die automatische Prüfung kann gerade nicht gestartet werden.",
                            "An automatic check cannot be started right now.")
                    return
                self.redirect("?ui=overview" + keep_mode)
                return
            if path == "/vergleichsgenauigkeit":
                try:
                    with rules_lock:
                        rules = read_auto_rules()
                        suggested = automatic_summary(read_history(), language, rules)["precision_suggestion"]
                        if suggested is None or field("decimals") != str(suggested):
                            problem(409, "Bitte die aktuelle Empfehlung neu laden.",
                                    "Reload the current precision suggestion.")
                            return
                        save_auto_rules({**rules, "decimals": suggested, "precision_mode": False})
                except (OSError, ValueError):
                    problem(503)
                    return
                self.redirect("?ui=overview" + keep_mode)
                return
            if path == "/zaehler-demo":
                if not demo_lock.acquire(blocking=False):
                    problem(503)
                    return
                try:
                    result = run_demo(field("reflection") == "1")
                    self.reply(json.dumps(result).encode("utf-8"), "application/json")
                except (OSError, ValueError, subprocess.SubprocessError):
                    problem(503)
                finally:
                    demo_lock.release()
                return
            if path == "/experimentelle-zaehler":
                if experimental_meters is None:
                    self.send_error(404)
                    return
                try:
                    experimental_meters.configure(field("meters"))
                except ValueError:
                    problem(400)
                    return
                except OSError:
                    problem(503)
                    return
                self.reply(b'{}', "application/json")
                return
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
                    content = (get_wizard_image(source, full_size=True) if field("preview") == "crop"
                               else get_wizard_image(source))
                    if field("preview") == "reflection":
                        preview = reflection_setup_preview(content, int(field("integer_digits")),
                                                           int(field("fraction_digits")), field("polarity"))
                except (OSError, ValueError):
                    problem(503, "Das Kamerabild konnte nicht geladen werden.", "Could not load the camera image.")
                else:
                    if field("preview") == "reflection":
                        self.reply(json.dumps(preview).encode("utf-8"), "application/json; charset=utf-8")
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
                    if not learn_crop and crop_mode == "manual" and field("confirm_manual_crop") != "1":
                        raise ValueError("Confirm the manually selected crop")
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
                    precise = field("precision_mode") == "1" and fraction_digits == 3
                    decimals = 3 if precise else min(2, decimals)
                    rules_values = {
                        **old_rules, "decimals": decimals, "attempts": attempts,
                        "polarity": polarity, "crop_mode": crop_mode, "crop": crop,
                        "width": width, "rotation": rotation,
                        "digit_boxes": old_rules["digit_boxes"] if (
                            crop_mode == old_rules["crop_mode"] and crop == old_rules["crop"]
                            and rotation == old_rules.get("rotation", 0) and width == old_rules["width"]
                            and integer_digits == old_rules["integer_digits"] and fraction_digits == old_rules["fraction_digits"]
                        ) else [], "max_flow_lph": max_flow,
                        "precision_mode": precise,
                        "self_repair_enabled": field("self_repair_enabled") == "1",
                        "fine_alignment_enabled": (field("fine_alignment_enabled") == "1"
                                                  if field("fine_alignment_option_present") == "1"
                                                  else old_rules.get("fine_alignment_enabled", False)),
                        "reflection_estimate_enabled": (field("reflection_estimate_enabled") == "1"
                                                        if field("reflection_option_present") == "1"
                                                        else old_rules.get("reflection_estimate_enabled", False)),
                        "interval_minutes": interval_minutes, "integer_digits": integer_digits,
                        "fraction_digits": fraction_digits, "meter_display": meter_display,
                        "fallback_value": fallback_value, "fallback_time": fallback_time,
                    }
                    if not learn_crop and crop_mode == "manual" and field("digit_boxes"):
                        rules_values["digit_boxes"] = digit_box_settings(
                            json.loads(field("digit_boxes")), integer_digits + fraction_digits,
                        )
                    marked_text = field("reflection_geometry")
                    rules_values["setup_reflection"] = None
                    if learn_crop and rules_values["reflection_estimate_enabled"] and marked_text:
                        marked = json.loads(marked_text)
                        if not isinstance(marked, dict):
                            raise ValueError("Invalid reflection geometry")
                        positions = marked.get("positions")
                        count = integer_digits + fraction_digits
                        if (not isinstance(positions, list) or len(positions) > 2
                                or any(type(value) is not int or not 0 <= value < count for value in positions)
                                or len(set(positions)) != len(positions)):
                            raise ValueError("Invalid reflected positions")
                        if positions:
                            boxes = digit_box_settings(marked.get("digit_boxes"), count)
                            if not boxes:
                                raise ValueError("Missing digit boxes")
                            crop_coordinates(marked["crop"], marked["width"], marked["rotation"])
                            rules_values["setup_reflection"] = {
                                "source": setup_source_id({**source_values, "selected": True}),
                                "positions": positions, "crop": marked["crop"], "width": marked["width"],
                                "rotation": marked["rotation"], "digit_boxes": boxes,
                            }
                    with source_lock, rules_lock:
                        if learn_crop and get_auto_paused and get_auto_paused():
                            problem(409, "Setze die Automatik fort und starte dann die Selbsteinrichtung.",
                                    "Resume automatic checks before starting automatic setup.")
                            return
                        previous_source, initial_setup = get_source()
                        save_source(source_values)
                        if not learn_crop or fallback_value and (
                                fallback_value != old_rules.get("fallback_value") or previous_source != get_source()[0]):
                            rules_values["setup_input_source"] = setup_source_id(get_source()[0])
                        else:
                            rules_values.pop("setup_input_source", None)
                        if initial_setup and not learn_crop and (crop_mode == "manual" or fallback_value):
                            rules_values["setup_pending_source"] = setup_source_id(get_source()[0])
                            rules_values["setup_pending_started"] = None
                            rules_values["setup_pending_metrics"] = None
                        with delivery_lock:
                            save_delivery(delivery_values)
                        save_auto_rules(rules_values)
                        if learn_crop:
                            control_calibration("setup" if initial_setup else "start", image_limit)
                except (ValueError, TypeError, KeyError):
                    problem(400, "Bitte prüfe Bildquelle, Ziffernaufteilung und Fallback-Wert.",
                            "Check the image source, digit layout and fallback reading.")
                    return
                except OSError:
                    problem(503)
                    return
                if learn_crop:
                    self.redirect("?saved=setup-calibration&ui=overview" + keep_mode)
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
                        current["setup_input_source"] = setup_source_id(get_source()[0])
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
                        save_auto_rules({**rules, "fallback_value": value, "fallback_time": stamp,
                                         "setup_input_source": setup_source_id(get_source()[0])})
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
                action = field("action")
                try:
                    if action not in ("start", "intensive", "cancel", "restore", "skip-verification"):
                        raise ValueError("Invalid calibration action")
                    starting = action in ("start", "intensive")
                    limit = int(field("image_limit", str(DEFAULT_LIMIT))) if starting else 0
                    if starting and not MIN_IMAGE_LIMIT <= limit <= MAX_IMAGES:
                        raise ValueError("Invalid calibration image limit")
                    region = search_region(field("region")) if action == "start" else None
                    if action == "skip-verification":
                        verification_id = field("verification_id")
                        if not verification_id:
                            raise ValueError("Missing verification ID")
                        control_calibration(action, limit, verification_id=verification_id)
                    elif region:
                        control_calibration(action, limit, region=region)
                    else:
                        control_calibration(action, limit)
                except ValueError:
                    if action == "skip-verification":
                        problem(409, "Die Gegenprobe für diesen Rahmen ist nicht mehr offen.",
                                "Verification for this crop is no longer pending.")
                        return
                    if action == "intensive":
                        problem(400, "Für die Feinprüfung muss ein Ziffernrahmen gespeichert und die Automatik aktiv sein.",
                                "The fine check needs a saved digit crop and enabled automatic checks.")
                        return
                    problem(400, "Bitte Bildquelle einrichten, die Automatik fortsetzen und das Bildlimit prüfen.",
                            "Set up an image source, resume automatic checks and check the image limit.")
                    return
                except OSError:
                    problem(503)
                    return
                saved = "crop-restored" if action == "restore" else "calibration"
                view = "overview" if action in ("start", "intensive", "skip-verification") else "settings"
                self.redirect(f"?saved={saved}&ui={view}" + keep_mode)
                return
            if path == "/ziffernrahmen":
                action = field("action")
                try:
                    if action not in ("save", "search"):
                        raise ValueError("Invalid digit action")
                    with rules_lock:
                        rules = read_auto_rules()
                        source, _ = get_source()
                        layout = digit_correction_settings(rules, source)
                        active = get_calibration() if get_calibration else None
                        if (not layout or field("token") != layout["token"]
                                or active and active["state"] in ("waiting", "testing")):
                            problem(409, "Der gespeicherte Ausschnitt hat sich geändert. Öffne den Editor erneut.",
                                    "The saved crop has changed. Reopen the editor.")
                            return
                        count = layout["integer_digits"] + layout["fraction_digits"]
                        boxes = digit_box_settings(json.loads(field("digit_boxes")), count)
                        if not boxes:
                            raise ValueError("Missing digit boxes")
                        if action == "save":
                            revision = str(time.time_ns())
                            values = {**rules, "digit_boxes": boxes, "crop_revision": revision,
                                      "setup_input_source": setup_source_id(source)}
                            old_revision = rules.get("crop_revision")
                            if old_revision and rules.get("stationary_partial_scope") == setup_source_id([source, old_revision]):
                                values["stationary_partial_scope"] = setup_source_id([source, revision])
                            if boxes != rules["digit_boxes"]:
                                save_auto_rules(values)
                    if action == "save":
                        self.redirect("?saved=digit-frames&ui=overview" + keep_mode)
                        return
                    index = int(field("index"))
                    if not 0 <= index < count:
                        raise ValueError("Invalid digit index")
                    version = field("image_version")
                    if field("image_kind") == "calibration":
                        content = get_calibration_image("frame", version) if get_calibration_image else None
                    else:
                        with current_image.open("rb") as stream:
                            content = stream.read() if str(os.fstat(stream.fileno()).st_mtime_ns) == version else None
                    if not content:
                        problem(409, "Ein neueres Kamerabild liegt vor. Öffne den Editor erneut.",
                                "A newer camera image is available. Reopen the editor.")
                        return
                    if not digit_search_lock.acquire(blocking=False):
                        problem(409, "Eine Ziffernsuche läuft bereits.", "A digit search is already running.")
                        return
                    try:
                        crop = crop_coordinates(layout["crop"], layout["width"], layout["rotation"])
                        with Image.open(BytesIO(content)) as frame:
                            register = turn_crop(crop_register(frame, crop), layout["rotation"])
                        proposal = suggest_single_digit_box(register, boxes, index, layout["polarity"])
                    finally:
                        digit_search_lock.release()
                    self.reply(json.dumps(proposal).encode("utf-8"), "application/json; charset=utf-8")
                except (TypeError, ValueError, Image.DecompressionBombError):
                    problem(400)
                except OSError:
                    problem(503)
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
                        try:
                            intensive_agreement = int(field("intensive_agreement", str(old_rules.get(
                                "intensive_agreement", DEFAULT_INTENSIVE_AGREEMENT))))
                        except ValueError:
                            intensive_agreement = 0
                        if not valid_intensive_agreement(intensive_agreement):
                            problem(400, "Die Übereinstimmung für die Intensivprüfung muss zwischen 1 und 100 Prozent liegen.",
                                    "Enter an intensive-check agreement threshold between 1 and 100 percent.")
                            return
                        precise = field("precision_mode") == "1" and old_rules["fraction_digits"] == 3
                        save_auto_rules({"decimals": 3 if precise else min(2, int(decimals[0])),
                                         "attempts": int(attempts[0]),
                                         "intensive_agreement": intensive_agreement,
                                         "precision_mode": precise,
                                         "reflection_estimate_enabled": field("reflection_estimate_enabled") == "1",
                                         "fine_alignment_enabled": field("fine_alignment_enabled") == "1",
                                         "self_repair_enabled": field("self_repair_enabled") == "1",
                                         "adaptive_interval_enabled": field("adaptive_interval_enabled") == "1",
                                         "reflection_suggestion_hidden": field("reflection_suggestion_hidden") == "1",
                                         "polarity": polarity[0], "crop_mode": crop_mode[0],
                                         "crop": crop, "width": width, "rotation": rotation, "digit_boxes": boxes,
                                         "max_flow_lph": max_flow, "interval_minutes": interval_minutes,
                                         "setup_input_source": (setup_source_id(get_source()[0]) if crop_mode[0] == "manual"
                                                                else old_rules.get("setup_input_source"))})
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
