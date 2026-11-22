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
import bug_report
import status_view
import system_monitor
import background_view
from auto_rules import frames_locked, user_frames
import debug_log

INSTANCE_ID = token_urlsafe(8)
from calibration import (
    DEFAULT_INTENSIVE_AGREEMENT, DEFAULT_LIMIT, MIN_IMAGE_LIMIT, MAX_IMAGES,
    layouts, search_region, valid_intensive_agreement,
)
from checks import (DEFAULT_INTERVAL_MINUTES, MAX_INTERVAL_MINUTES, WARNING_DETAIL_AFTER, meter_prefix,
                    OCR_PROFILES, crop_register, read_register, LAST_DIGIT_NOTICE, LAST_DIGIT_PASS, REFLECTION_SUGGEST_AFTER, STANDALONE_PENDING, STANDALONE_REJECTED_NOTICE,
                    STANDALONE_VERIFIED_NOTICE, last_check_at, recommended_comparison_decimals, reschedule_next_check,
                    setup_deadlines, setup_source_id, stabilization_interval, stationary_partial_active, valid_interval_minutes,
                    eighth_digit_given_up, wait_reason_text)
QUIET_FAILURES = status_view.QUIET_FAILURES
from checks import (DEFAULT_FAILURE_PAUSE_MINUTES, MAX_FAILURE_PAUSE_MINUTES, MIN_FAILURE_PAUSE_MINUTES,
                    FRAME_OFF_NOTICE, FRAME_OFF_WAIT_NOTICE, MOVING_DIGIT_NOTICE, MOVING_NOTICES)
from consumption import (DEFAULT_FLOW_LPH, EXCESSIVE_INCREASE, LOWER_PENDING, LOWER_READING,
                         CALORIFIC_RANGE, CONVERSION_RANGE, STATE_FACTOR_RANGE, consumption_statistics, format_cubic_metres,
                         parse_energy_factor, parse_flow_limit)
from demo import run_demo
from i18n import EN_UI, english_progress, english_result, translate_page
from language import MODES, SUPPORTED, USER_ID, browser_locale, profile_script
from layout import MANUAL_ROW_UNCLEAR, PARTLY_UNCLEAR, RAW_ROW_UNCLEAR, crop_coordinates, fine_rotation, split_rotation, digit_box_settings, scale_digit_boxes, turn_crop
from meter_learning import suggest_single_digit_box
from notification_settings import notification_rules
from source_settings import CAMERA, CameraOffline, source_check_key, source_rules
from kit_camera import EXTRAS as KIT_EXTRAS

SUPERVISOR_ADDRESS = "172.30.32.2"
# Installer page for the ready-made meter camera firmware (esphome/ in the repository).
KIT_INSTALLER_URL = "https://eifellayer.github.io/meter-ocr/"
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
<form method="post" action="selbsteinrichtung" class="calibration-orientation" hidden>
<input type="hidden" name="lang" value="{language}">
<input type="hidden" name="mode" value="{mode}">
<input type="hidden" name="csrf" value="{csrf}">
<button type="submit" name="action" value="flip">Steht auf dem Kopf? Um 180° drehen</button>
<button type="submit" name="action" value="mirror">Spiegelverkehrt? Bild spiegeln</button>
</form>
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
/* 0.5.15: options to tick are soft tiles with a slide switch, like
   the settings of a current smartphone. The real checkbox stays: keyboard and screen readers work. */
.check-option{{display:flex;align-items:center;justify-content:space-between;gap:.9rem;grid-column:1/-1;min-height:2.9rem;padding:.6rem .9rem;border:1px solid var(--edge);border-radius:.95rem;background:light-dark(#f6f9fb,#1f2b35);color:inherit;font-size:.95rem;font-weight:550;cursor:pointer;transition:background .2s ease,border-color .2s ease,box-shadow .2s ease}}
.check-option:hover{{border-color:light-dark(#b9c9d4,#4d6170)}}
.check-option:has(input:checked){{background:light-dark(#e6f6f1,#17352f);border-color:light-dark(#8fd0bf,#2f7868)}}
.check-option:has(input:disabled){{opacity:.6;cursor:not-allowed}}
label.check-option input[type="checkbox"]{{appearance:none;-webkit-appearance:none;order:2;flex:0 0 auto;position:relative;width:2.9rem;min-width:2.9rem;height:1.7rem;min-height:1.7rem;margin:0;padding:0;border:0;border-radius:99px;background:light-dark(#c3cfd8,#4a5a66);cursor:pointer;transition:background .2s ease}}
label.check-option input[type="checkbox"]::before{{content:"";position:absolute;top:.15rem;left:.15rem;width:1.4rem;height:1.4rem;border-radius:50%;background:#fff;box-shadow:0 1px 3px #0005;transition:transform .2s ease}}
label.check-option input[type="checkbox"]:checked{{background:light-dark(#12a38b,#2ec4a6)}}
label.check-option input[type="checkbox"]:checked::before{{transform:translateX(1.2rem)}}
label.check-option input[type="checkbox"]:disabled{{cursor:not-allowed}}
@media(prefers-reduced-motion:reduce){{.check-option,label.check-option input[type="checkbox"],label.check-option input[type="checkbox"]::before{{transition:none}}}}
.notification-form input{{width:100%}}
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
.setting-link{{cursor:pointer}}
.setting-link::after{{content:" ›";opacity:.7}}
.setting-highlight{{outline:3px solid var(--accent, #2ec4a6);outline-offset:2px}}
.reflection-suggestion{{margin:.65rem 0;color:var(--muted);font-size:.92rem}}
/* 0.5.11: an input the app is waiting for sits at the top of the overview and stands out. */
.hidden-digit-figure{{flex-basis:100%;margin:.2rem 0 .5rem}}
.hidden-digit-figure img{{display:block;width:100%;max-width:34rem;height:auto;border-radius:.4rem;image-rendering:auto}}
.hidden-digit-figure figcaption{{font-size:.85rem;color:var(--muted);margin-top:.25rem}}
#test-preview-image.preview-outdated{{opacity:.5;filter:grayscale(.6)}}
.reflection-suggestion.action-needed{{padding:.75rem .9rem;border:2px solid light-dark(#b26a00,#ffb74d);border-radius:.7rem;background:var(--surface-2);color:inherit;font-size:1rem}}
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
.setup-success{{position:relative}}
.setup-success-close{{position:absolute;top:.5rem;right:.5rem;min-height:2.4rem;width:2.4rem;padding:0;border-radius:50%;background:transparent;border-color:transparent;color:inherit;font-size:1rem;line-height:1}}
.setup-success-close:hover{{background:light-dark(#d6efdf,#24503a)}}
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
/* 0.5.10: display:block above overrode the hidden attribute, so the previous picture stayed
   visible under the frame of the new one until the new picture had loaded. */
.calibration-photo-grid img[hidden]{{display:none}}
.calibration-photo-frame{{position:relative;width:fit-content;max-width:100%}}
.calibration-crop-region{{position:absolute;border:2px solid #ffcd60;border-radius:.1rem;box-shadow:0 0 0 1px #151c23;pointer-events:none}}
.calibration-crop-region[data-state="testing"]{{border-style:dashed}}
.calibration-orientation{{display:flex;flex-wrap:wrap;gap:.4rem;margin:.5rem 0 0}}
.calibration-orientation button{{font-size:.85rem;padding:.35rem .75rem}}
.calibration-candidates{{font-variant-numeric:tabular-nums;padding-inline-start:1.8rem;margin:.45rem 0}}
.calibration-candidates li{{margin:.2rem 0}}
/* Setup progress: vertical timeline of the work steps (0.3.0). */
.setup-timeline-box{{display:block;margin:.75rem 0}}
.setup-timeline-box h3{{margin:0 0 .5rem;font-size:1rem}}
.setup-timeline{{list-style:none;margin:0;padding:0}}
/* 0.5.11: the free space on the right holds the checklist of the pictures evaluated so far. */
.setup-timeline-grid{{display:grid;gap:.8rem 1.6rem}}
@media(min-width:900px){{.setup-timeline-grid{{grid-template-columns:minmax(0,1.1fr) minmax(0,1fr);align-items:start}}}}
/* 0.5.28: steps left, the tested picture and the pictures so far right; one column on small screens
   and whenever one side has nothing to show. */
.calibration-layout{{display:grid;gap:.9rem 1.6rem;margin:.75rem 0;align-items:start}}
.calibration-main:not(:has(> :not([hidden]))),.calibration-side:not(:has(> :not([hidden]))){{display:none}}
@media(min-width:900px){{.calibration-layout:has(> .calibration-main > :not([hidden])):has(> .calibration-side > :not([hidden])){{grid-template-columns:minmax(0,1fr) minmax(0,1.05fr)}}}}
.calibration-main .setup-timeline-box{{margin:0}}
.calibration-side{{display:grid;gap:.75rem;min-width:0}}
.calibration-side .calibration-photo-panel{{margin:0;padding:.65rem .75rem;border:1px solid var(--edge);border-radius:.6rem;background:var(--surface-2)}}
.calibration-side .calibration-photo-panel > summary{{cursor:pointer;font-weight:650}}
.calibration-side .calibration-photo-grid{{grid-template-columns:minmax(0,1fr);margin:.55rem 0 0}}
.calibration-side .calibration-photo-frame{{width:auto}}
.calibration-side .calibration-photo-grid img{{width:100%}}
.calibration-side .setup-rounds-box{{padding:.65rem .75rem;border:1px solid var(--edge);border-radius:.6rem}}
.calibration-actions{{display:flex;flex-wrap:wrap;align-items:flex-start;gap:.6rem;margin:.2rem 0 .4rem}}
.calibration-live .quality-hint{{grid-template-columns:minmax(0,1fr);gap:.5rem;margin:0 0 .6rem}}
.calibration-live .quality-hint p{{margin:0}}
.calibration-actions .calibration-skip{{flex:1 1 18rem}}
.setup-rounds-box h4{{margin:0 0 .4rem;font-size:.92rem}}
.setup-rounds{{list-style:none;margin:0;padding:0;display:grid;gap:.3rem;font-size:.86rem;font-variant-numeric:tabular-nums}}
.setup-rounds li{{display:grid;grid-template-columns:1.3rem minmax(0,1fr);gap:.45rem;padding:.35rem .55rem;border-radius:.5rem;background:var(--surface-2);border:1px solid var(--edge)}}
.setup-rounds .setup-round-mark{{font-weight:800;text-align:center}}
.setup-rounds li[data-result="ok"] .setup-round-mark{{color:light-dark(#1e7a43,#5fd18c)}}
.setup-rounds li[data-result="fail"] .setup-round-mark{{color:light-dark(#b3261e,#ff8a80)}}
.setup-rounds li[data-result="wait"] .setup-round-mark{{color:var(--muted)}}
.setup-rounds small{{display:block;color:var(--muted);overflow-wrap:anywhere}}
.setup-timeline li{{position:relative;display:grid;grid-template-columns:1.6rem 1fr;column-gap:.6rem;padding:0 0 .75rem}}
.setup-timeline li::before{{content:"";position:absolute;left:.75rem;top:1.1rem;bottom:-.1rem;border-left:2px solid var(--edge)}}
.setup-timeline li:last-child::before{{display:none}}
.setup-timeline li[data-state="done"]::before{{border-left-color:light-dark(#8fa9b8,#c9d6df)}}
.setup-timeline li[data-state="current"]::before,.setup-timeline li[data-state="todo"]::before{{border-left-style:dashed}}
.setup-dot{{grid-row:1/span 2;justify-self:center;display:grid;place-items:center;width:.95rem;height:.95rem;margin-top:.2rem;border-radius:50%;box-sizing:border-box;font-size:.62rem;line-height:1;z-index:1}}
.setup-timeline li[data-state="done"] .setup-dot{{background:light-dark(#ffffff,#f4f7fa);color:light-dark(#185d35,#185d35);border:1px solid light-dark(#7aa58a,#ffffff);animation:setup-tick .35s ease-out}}
.setup-timeline li[data-state="current"] .setup-dot{{width:1.35rem;height:1.35rem;margin-top:0;background:light-dark(#ffffff,#f4f7fa);border:3px solid var(--accent);animation:setup-pulse 1.6s ease-in-out infinite}}
.setup-timeline li[data-state="todo"] .setup-dot,.setup-timeline li[data-state="optional"] .setup-dot{{background:transparent;border:2px solid light-dark(#a3b1bb,#6c7a85)}}
.setup-step-label{{font-weight:500}}
.setup-timeline li[data-state="current"] .setup-step-label{{font-weight:750}}
.setup-timeline li[data-state="todo"] .setup-step-label,.setup-timeline li[data-state="optional"] .setup-step-label{{color:var(--muted);font-size:.92rem}}
.setup-step-result{{color:var(--muted);font-size:.85rem;font-variant-numeric:tabular-nums}}
.setup-step-detail{{grid-column:2;font-size:.88rem;font-variant-numeric:tabular-nums;color:light-dark(#243b4b,#e5edf5)}}
.setup-step-head{{display:flex;flex-wrap:wrap;gap:.2rem .6rem;align-items:baseline;justify-content:space-between;min-width:0}}
.setup-substeps{{grid-column:2;margin:.2rem 0 0;font-size:.86rem}}
.setup-substeps summary{{cursor:pointer;color:var(--muted)}}
.setup-substeps ul{{list-style:none;margin:.2rem 0 0;padding:0}}
.setup-substeps li{{margin:.1rem 0;font-variant-numeric:tabular-nums}}
/* 0.5.8: the timeline rules (.setup-timeline li: two-column grid, connector line) also hit the
   sub-step items and squeezed them into the 1.6rem marker column. Reset them here. */
.setup-timeline .setup-substeps li{{display:block;position:static;padding:0;grid-template-columns:none}}
.setup-timeline .setup-substeps li::before{{content:none;display:none}}
.setup-substeps li[data-sub="todo"]{{color:var(--muted)}}
.setup-substeps li[data-sub="current"]{{font-weight:700}}
.setup-substeps li[data-sub="warn"]{{color:light-dark(#8a5a00,#ffd27a)}}
.setup-timeline-stats{{margin:.1rem 0 0;color:var(--muted);font-size:.85rem;font-variant-numeric:tabular-nums}}
@keyframes setup-pulse{{0%,100%{{box-shadow:0 0 0 0 light-dark(#0b8f7c55,#38c9b055)}}50%{{box-shadow:0 0 0 .4rem light-dark(#0b8f7c00,#38c9b000)}}}}
@keyframes setup-tick{{from{{transform:scale(.4);opacity:0}}to{{transform:scale(1);opacity:1}}}}
@media(prefers-reduced-motion:reduce){{.setup-timeline .setup-dot{{animation:none!important}}}}
.calibration-candidate-panel{{margin:.6rem 0;padding:.55rem .75rem;border:1px solid var(--edge);border-radius:.6rem}}
.calibration-candidate-panel summary{{cursor:pointer;font-weight:650}}
.calibration-candidates li[data-selected="true"]{{font-weight:700}}
.calibration-candidates li[data-selected="true"]::marker{{color:var(--accent)}}
.digit-grid-wrap{{overflow-x:auto;margin:.4rem 0}}
.digit-grid{{border-collapse:collapse;font-variant-numeric:tabular-nums;font-size:.88rem}}
.digit-grid th,.digit-grid td{{padding:.15rem .35rem;text-align:center;border-bottom:1px solid var(--edge)}}
.digit-grid th[scope="row"]{{text-align:start;font-weight:600;white-space:nowrap}}
.digit-grid .digit-sep{{border-left:2px solid light-dark(#c0392b,#ff8a80)}}
.digit-grid td[data-uncompared="true"],.digit-grid th[data-uncompared="true"]{{opacity:.45}}
.digit-grid tr.digit-result td[data-tone="ok"]{{color:light-dark(#185d35,#9ce5b5);font-weight:750}}
.digit-grid tr.digit-result td[data-tone="warn"]{{color:light-dark(#8a5a00,#ffd27a);font-weight:750}}
.digit-grid tr.digit-result td[data-tone="bad"]{{color:light-dark(#a1262d,#ffb6bb);font-weight:750}}
.calibration-photo-grid figcaption{{margin-top:.35rem;color:var(--muted)}}
.calibration-photo-panel .calibration-preview-help{{font-size:.83rem;color:var(--muted);margin:.35rem 0 0}}
.calibration-photo-panel .calibration-preview-reading{{overflow-wrap:anywhere;font-weight:650;font-variant-numeric:tabular-nums;margin:.25rem 0 0}}
.source-mode-guide{{grid-column:1/-1;display:grid;gap:.75rem;grid-template-columns:repeat(auto-fit,minmax(min(100%,14rem),1fr))}}
.source-mode-guide ul{{padding-inline-start:1.25rem;margin:0}}
.source-mode-guide li + li{{margin-top:.35rem}}
.crop-draw{{grid-column:1/-1;padding:.85rem;border:1px solid var(--edge);border-radius:.65rem}}
.crop-draw > p{{margin:.3rem 0 .7rem}}
.crop-actions{{grid-column:1/-1;display:flex;flex-wrap:wrap;gap:.55rem}}
.discovered-row{{display:flex;gap:.5rem;align-items:flex-end}}.discovered-row label{{flex:1 1 auto;min-width:0}}.discovered-row select{{width:100%}}.icon-refresh,form:not(.language-bar) button.icon-refresh{{flex:0 0 44px;width:44px;min-width:44px;max-width:44px;height:44px;min-height:44px;padding:0;font-size:1.2rem}}
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
.grey-key{{color:light-dark(#6b7782,#a3afb9);font-weight:700}}
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
.meter-hero-wait{{margin:.35rem 0 0;font-size:.88rem;color:var(--muted)}}
.meter-hero-action{{margin:.5rem 0 0}}
.meter-hero-action a{{display:inline-block;padding:.4rem .8rem;border-radius:.6rem;border:2px solid light-dark(#b26a00,#ffb74d);font-weight:700;color:inherit;text-decoration:none}}
.background-work-box{{margin:1rem 0 .5rem}}
/* Decent: a small, quiet row at the end of the card. */
.check-option.background-work-toggle{{min-height:2.4rem;padding:.35rem .75rem;font-size:.86rem;font-weight:500;color:var(--muted);background:transparent}}
.background-live{{margin-top:.5rem}}
.background-job{{margin:0 0 .6rem;padding:.6rem .85rem;border:1px solid var(--edge);border-radius:.75rem}}
.background-job[data-state="running"]{{border-color:var(--accent)}}
.background-job p{{margin:.15rem 0 0;font-size:.9rem;overflow-wrap:anywhere}}
.background-job .background-job-head{{margin:0;font-size:1rem}}
.background-job .background-job-state{{color:var(--muted);font-weight:500}}
.background-job[data-state="running"] .background-job-state{{color:var(--accent);font-weight:700}}
.background-job progress{{width:100%;margin-top:.35rem}}
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
#start-automatic,#start-check-with-options,#start-check-top,#save-digit-correction,form button[type="submit"]:not(.crop-reset){{background:var(--accent);border-color:transparent;color:var(--accent-ink)}}
#start-automatic:not(:disabled):hover,#start-check-with-options:not(:disabled):hover,#start-check-top:not(:disabled):hover,form button[type="submit"]:not(.crop-reset):not(:disabled):hover{{background:light-dark(#097a6a,#5fd8c3)}}
select,input{{border-radius:var(--radius-sm);background:var(--surface);border:1px solid var(--edge)}}
/* Compact form fields (0.1.7): smaller selects and inputs, less visual weight in settings, tools and setup. */
form select,form input:not([type="checkbox"]):not([type="radio"]):not([type="file"]){{min-height:2.25rem;padding:.4rem .65rem;font-size:.92rem}}
.setup-step select,#wizard-camera-search{{min-height:2.35rem}}
.setup-step details.setup-help > summary{{min-height:2.3rem;padding:.45rem .2rem}}
form label{{gap:.2rem}}
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
/* ---------- 0.5.24: source cards and the one-click meter camera ---------- */
.source-cards-ready .source-mode-select{{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap}}
.setup-step .source-mode-guide:has(.source-cards:not([hidden])){{background:transparent;border:0;padding:0}}
.source-cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,15rem),1fr));gap:.6rem}}
.source-card{{position:relative;display:grid;grid-template-columns:auto 1fr;gap:.15rem .7rem;align-items:start;text-align:left;font:inherit;color:inherit;cursor:pointer;
min-height:0;padding:.8rem .85rem;border-radius:var(--radius-sm);border:1.5px solid var(--edge);background:var(--surface-2);transition:border-color .15s,transform .15s}}
.source-card:hover{{transform:translateY(-1px);border-color:light-dark(#b9c7d2,#3c4c59)}}
.source-card[aria-checked="true"]{{border-color:var(--accent);background:var(--accent-soft)}}
.source-card[aria-checked="true"]::after{{content:"✓";position:absolute;top:.5rem;right:.6rem;width:1.3rem;height:1.3rem;border-radius:50%;display:grid;place-items:center;background:var(--accent);color:var(--accent-ink);font-size:.75rem;font-weight:800}}
.source-card-icon{{grid-row:span 2;display:grid;place-items:center;width:2.3rem;height:2.3rem;border-radius:.7rem;background:var(--surface);border:1px solid var(--edge);color:var(--accent)}}
.source-card-icon svg{{width:1.35rem;height:1.35rem}}
.source-card strong{{font-size:.95rem;line-height:1.3;padding-right:1.2rem}}
.source-card small{{color:var(--muted);font-size:.82rem;line-height:1.4}}
.source-cards.needs-choice .source-card{{border-color:var(--warn)}}
.source-cards-hint{{color:var(--warn)}}
.setup-step div.kit-panel{{border-color:var(--accent);background:linear-gradient(160deg,var(--accent-soft),var(--surface-2) 70%)}}
.kit-boards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,13.5rem),1fr));gap:.45rem}}
.kit-board{{display:flex;align-items:flex-start;gap:.5rem;padding:.55rem .65rem;border:1px solid var(--edge);border-radius:.55rem;background:var(--surface);cursor:pointer}}
.kit-board:has(:checked){{border-color:var(--accent)}}
.kit-board input{{margin:.2rem 0 0;flex:none}}
.kit-board span{{display:grid;gap:.05rem;min-width:0}}
.kit-board strong{{font-size:.88rem}}
.kit-board small{{color:var(--muted);font-size:.78rem}}
.kit-steps{{margin:0;padding-left:1.3rem;display:grid;gap:.45rem}}
.kit-steps li::marker{{color:var(--accent);font-weight:750}}
.kit-install{{background:var(--accent);color:var(--accent-ink);border-color:transparent;margin-right:.4rem}}
.kit-status[data-state="found"]{{color:var(--ok);font-weight:650}}
.kit-pending{{display:flex;flex-wrap:wrap;align-items:center;gap:.5rem .8rem;padding:.65rem .8rem;border-radius:.6rem;background:var(--surface);border:1px solid var(--accent)}}
.kit-pending p{{margin:0;flex:1 1 14rem}}
#wizard-kit-add{{background:var(--accent);color:var(--accent-ink);border-color:transparent}}
.kit-extras{{margin:0;padding:.65rem .8rem;border:1px solid var(--edge);border-radius:.6rem;background:var(--surface);display:grid;gap:.45rem}}
.kit-extras legend{{padding:0 .3rem;font-size:.88rem;font-weight:650}}
.kit-extras label{{display:flex;align-items:flex-start;gap:.5rem}}
.kit-extras small{{color:var(--muted)}}
.setup-step details.setup-help{{background:var(--surface-2);border-radius:var(--radius-sm);padding:0 .9rem}}
.setup-step details.setup-help > summary{{list-style:none;display:flex;align-items:center;justify-content:space-between;gap:.6rem}}
.setup-step details.setup-help > summary::-webkit-details-marker{{display:none}}
.setup-step details.setup-help > summary::after{{content:"";flex:none;width:.5rem;height:.5rem;border-right:2px solid var(--muted);border-bottom:2px solid var(--muted);transform:rotate(45deg);transition:transform .2s}}
.setup-step details.setup-help[open] > summary::after{{transform:rotate(-135deg)}}
.setup-step details.setup-help[open]{{padding-bottom:.8rem}}
.setup-step input,.setup-step select{{width:100%;box-sizing:border-box}}
.setup-step input[type="checkbox"],.setup-step input[type="radio"]{{width:auto}}
.energy-factors{{display:grid;grid-template-columns:repeat(auto-fit,minmax(9rem,1fr));gap:.5rem;margin:.5rem 0}}
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
.settings-item:not(.manual-panel) > summary{{display:flex;align-items:center;justify-content:space-between;list-style:none;cursor:pointer}}
.settings-item:not(.manual-panel) > summary::-webkit-details-marker{{display:none}}
.settings-item:not(.manual-panel) > summary::after{{content:"";width:.55rem;height:.55rem;border-right:2px solid var(--muted);border-bottom:2px solid var(--muted);transform:rotate(45deg);transition:transform .2s;margin-right:.2rem}}
.settings-item:not(.manual-panel)[open] > summary::after{{transform:rotate(-135deg)}}
.reset-section > summary{{color:var(--bad)}}
@media(max-width:560px){{header{{grid-template-columns:1fr 1fr}}.brand{{grid-column:1/-1}}header > button,.language-bar,.language-bar select{{width:100%}}
.meter-hero{{margin:-.9rem -.9rem 1rem;padding:1.1rem .9rem 1rem}}.brand-subtitle{{display:none}}.automatic-actions > *,.automatic-actions button{{width:100%}}
.main-tabs button,.main-guide{{font-size:.86rem}}}}
/* ---------- 0.4.0: navigation, recognisable collapsible sections, settings grid ---------- */
.main-tabs button[aria-selected="false"]:not(:disabled):hover{{background:var(--surface-2);color:var(--ink)}}
.main-tabs button:focus-visible{{outline-offset:-3px}}
.main-tabs button[aria-selected="true"]{{box-shadow:0 1px 4px light-dark(#0f1f2b33,#0008)}}
#open-setup:not(:disabled):hover{{border-color:var(--accent);background:var(--accent-soft)}}
details:not(.manual-panel):not(.settings-item) > summary{{list-style:none;display:flex;align-items:center;gap:.5rem;min-height:2.5rem;width:auto;max-width:100%;padding:.3rem .5rem .3rem .2rem;border-radius:.55rem;cursor:pointer;transition:background .15s,color .15s}}
details:not(.manual-panel):not(.settings-item) > summary::-webkit-details-marker{{display:none}}
details:not(.manual-panel):not(.settings-item) > summary::before{{content:"";flex:none;width:.45rem;height:.45rem;margin:0 .2rem 0 .3rem;border-right:2px solid currentColor;border-bottom:2px solid currentColor;transform:rotate(-45deg);transition:transform .2s;opacity:.8}}
details[open]:not(.manual-panel):not(.settings-item) > summary::before{{transform:rotate(45deg)}}
details:not(.manual-panel):not(.settings-item) > summary:hover{{background:var(--surface-2);color:var(--ink);text-decoration:none}}
details.about-project > summary{{width:fit-content!important;margin-inline:auto}}
details > summary:focus-visible{{outline:3px solid light-dark(#0b8f7c66,#38c9b088);outline-offset:1px}}
.setup-dialog .setup-step details.setup-help > summary{{padding:.45rem .2rem;min-height:2.6rem}}
.setup-dialog .setup-step details.setup-help > summary::before{{content:none}}
.setup-dialog .setup-step details.setup-help > summary:hover{{background:transparent}}
.setup-dialog .setup-step details.setup-help:hover{{border-color:light-dark(#b9c6cf,#3b4a57)}}
@media(prefers-reduced-motion:reduce){{details > summary::before,details > summary::after{{transition:none!important}}}}
.experiments-box{{border:1px solid var(--accent)!important;border-radius:var(--radius-sm);background:var(--accent-soft)!important;padding:0 .9rem}}
.experiments-box > summary{{font-weight:650;color:var(--ink)!important}}
.experiments-box[open]{{padding-bottom:.8rem}}
.experiments-box > .check-option{{margin:.45rem 0 0;color:var(--ink)}}
.experiments-box > .experiment-option{{display:block;margin:.55rem 0 0 1.65rem;color:var(--ink)}}
.experiments-box > .experiment-option select{{display:block;margin-top:.25rem;max-width:100%}}
.experiments-box > p{{margin:.5rem 0 0;color:var(--muted);font-size:.86rem}}
#auto-form{{grid-template-columns:minmax(0,1fr);align-items:start;gap:1rem}}
#auto-form > .crop-actions,#auto-form > .crop-draw,#auto-form > .crop-fields{{margin:0}}
.settings-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,19rem),1fr));gap:1.1rem 1.4rem;align-items:start}}
.settings-field{{display:grid;grid-row:span 3;grid-template-rows:auto auto 1fr;grid-template-rows:subgrid;row-gap:.3rem;align-content:start;min-width:0}}
.settings-field > .field-label{{align-self:end;color:var(--ink);font-weight:650}}
.settings-field select,.settings-field input:not([type="checkbox"]){{width:100%}}
.settings-field .field-help{{display:block;margin:0;font-size:.8rem;font-weight:400;line-height:1.45;color:var(--muted)}}
.settings-wide{{grid-column:1/-1}}
.settings-wide > .check-option{{color:var(--ink);font-weight:650}}
.settings-wide > .field-help{{padding-left:1.65rem;max-width:46rem}}
.settings-more{{display:grid;gap:.6rem}}
.settings-more > details.help,.settings-more > .reflection-settings{{margin:0;padding:.1rem .8rem;border:1px solid var(--edge);border-radius:var(--radius-sm);background:var(--surface-2)}}
.settings-more > details.help[open]{{padding-bottom:.8rem}}
.settings-more > details.help > summary{{color:var(--ink);font-weight:650;font-size:.9rem}}
.settings-more > details.help > :not(summary){{margin-top:.5rem}}
.settings-more > .reflection-settings{{padding:.6rem .8rem}}
.settings-more .reflection-settings .help{{margin:.2rem 0 0 1.4rem}}
.last-readings{{margin-top:.5rem}}
.last-readings > summary{{font-weight:650;color:var(--ink)}}
.last-readings > .settings-note{{margin:.2rem 0 .4rem}}
.calibration-candidates li[data-role="hint"]{{color:var(--muted)}}
.candidate-hint{{display:inline-block;margin-left:.25rem;padding:0 .45rem;border:1px solid var(--edge);border-radius:99px;background:var(--surface-2);font-size:.78rem;font-weight:600;color:var(--muted)}}
.calibration-rejected{{margin:.3rem 0 .5rem;font-size:.88rem;color:var(--muted)}}
.calibration-rejected > summary{{font-weight:600}}
.calibration-rejected ul{{margin:.3rem 0 0;padding-left:1.4rem;font-variant-numeric:tabular-nums}}
</style>
<header>
<div class="brand"><span class="brand-mark" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4.5 16.5a8 8 0 1 1 15 0"/><path d="M12 13l3.5-4"/><circle cx="12" cy="13.5" r="1.4" fill="currentColor"/><path d="M7 20h10"/></svg></span>
<div><h1>{app_name}</h1><p class="brand-subtitle">Zählerstand lokal aus dem Kamerabild</p></div></div>
<button type="button" title="Einrichtungsassistent öffnen" id="open-setup">Einrichtung</button>
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
{overview_saved_notice}
{marked_reflection_note}
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
<p class="meter-hero-wait" id="hero-wait-reason" role="status" hidden></p>
<p class="meter-hero-action" id="hero-action" role="status" hidden><a href="#hidden-digit-prompt">Eingabe nötig: Zählerstand einmal eintragen</a></p>
<p class="meter-hero-stale" id="hero-stale" role="status" hidden><span id="hero-stale-text"></span><button type="button" class="secondary" id="reload-view">Neu laden</button></p>
</div>
<div class="check-card-heading"><h2>Automatische Kontrolle</h2></div>
<div id="setup-success" class="setup-success" role="status" {setup_success_hidden}>
<span class="setup-success-icon" aria-hidden="true">✓</span>
<div><strong>Zähler erfolgreich eingerichtet</strong>
<p id="setup-duration" {setup_duration_hidden}>{setup_duration}</p>
<p>Die Automatik läuft. Rahmen und Winkel verbessert die App automatisch im Hintergrund mit den normalen Prüfbildern weiter.</p></div>
<button type="button" class="setup-success-close" id="setup-success-close" aria-label="Hinweis ausblenden" title="Ausblenden">✕</button>
</div>
<div class="reflection-suggestion action-needed" id="hidden-digit-prompt" hidden>
<p><strong>Ziffer verdeckt.</strong> <span id="hidden-digit-text">Eine Stelle ist durch eine Spiegelung verdeckt.</span> Trag einmal den aktuellen Zählerstand ein. Danach ergänzt die App die verdeckte Stelle selbst, solange nur ein Wert zum Verbrauch passt.</p>
<form method="post" action="fallback" class="reflection-actions" id="hidden-digit-form">
<input type="hidden" name="lang" value="{language}"><input type="hidden" name="mode" value="{language_mode}">
<input type="hidden" name="csrf" value="{csrf}"><input type="hidden" name="return_to" value="overview">
<input type="hidden" name="fallback_time" id="hidden-digit-time" value="">
<figure class="hidden-digit-figure" id="hidden-digit-figure" hidden><img id="hidden-digit-image" alt="Ausschnitt des Zählwerks aus der letzten Aufnahme"><figcaption>Zählwerk in der letzten Aufnahme<span id="hidden-digit-image-time"></span>. Lies den Stand hier ab; die verdeckte Stelle bitte am Zähler nachsehen.</figcaption></figure>
<label>Aktueller Zählerstand<input name="fallback_value" inputmode="decimal" maxlength="16" placeholder="z. B. 10486,16" required></label>
<label class="check-option"><input type="checkbox" name="hide_prompt" value="1"> Zählerstand speichern und diese Frage dauerhaft ausblenden</label>
<button type="submit">Zählerstand übernehmen</button>
</form></div>
<div class="activity-status" data-state="{automatic_activity_state}" data-routine-ok="{automatic_routine_ok}">
<p role="status" aria-live="polite"><strong>Automatik:</strong> <span id="automatic-activity">{automatic_activity}</span></p>
<progress id="automatic-progress" class="setup-progress" aria-label="Fortschritt der automatischen Prüfung" {automatic_progress_hidden}></progress>
<details id="automatic-activity-details" class="activity-details" open {automatic_progress_hidden}>
<summary>Prüfdetails</summary>
<p id="automatic-attempt-info"></p>
<p id="automatic-live-reading"></p><ol id="live-ocr-candidates" hidden></ol>
<div class="digit-grid-wrap" id="automatic-digit-grid" hidden><table class="digit-grid" aria-label="Gelesene Ziffern je Versuch und Stelle"><thead></thead><tbody></tbody></table></div>
</details>
<details id="automatic-last-readings" class="activity-details last-readings" open hidden>
<summary>Die letzten Leseversuche</summary>
<p class="settings-note">Ziffern je Versuch und Stelle aus der zuletzt beendeten Prüfung. Die Liste bleibt bis zur nächsten Prüfung stehen.</p>
<div class="digit-grid-wrap" id="automatic-last-digit-grid" hidden><table class="digit-grid" aria-label="Gelesene Ziffern je Versuch und Stelle"><thead></thead><tbody></tbody></table></div>
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
<button type="button" id="save-digit-correction" disabled>Für Automatik speichern</button>
<button type="button" id="save-digit-correction-manual" disabled>Für manuellen Test speichern</button>
</div>
<p class="settings-note">„Für Automatik“ gilt ab der nächsten automatischen Prüfung. „Für manuellen Test“ ändert nur den Test unter Werkzeuge; die Automatik behält ihre Rahmen und startet keine Prüfung.</p>
</dialog>
<div id="calibration-overview" class="calibration-live" hidden>
<form method="post" action="bildqualitaet-hinweis-ausblenden" class="quality-hint settings-note" {quality_hint_hidden}>
<input type="hidden" name="lang" value="{language}"><input type="hidden" name="mode" value="{language_mode}">
<input type="hidden" name="csrf" value="{csrf}">
<p>Je schlechter das Kamerabild (Unschärfe, Spiegelungen, schwaches Licht, schräger Blickwinkel), desto länger dauern Einrichtung und Optimierung. Ein scharfes, gerades Bild ohne Lichtfleck auf den Ziffern spart am meisten Zeit.</p>
<label class="check-option"><input type="checkbox" name="hide" value="1" onchange="this.form.submit()"> Diesen Hinweis dauerhaft ausblenden</label>
<noscript><button type="submit">Speichern</button></noscript>
</form>
<p id="calibration-overview-state" role="status"></p>
<progress id="calibration-overview-progress" aria-label="Verstrichene Zeit der Selbsteinrichtung"></progress>
<p class="calibration-last-digit-note settings-note" hidden></p>
<div class="reflection-suggestion action-needed glare-confirm" hidden>
<p><strong>Spiegelung erkannt.</strong> <span class="glare-confirm-text"></span> Bitte bestätige das und trag den aktuellen Zählerstand ein. Die App übernimmt dann den Rahmen und nutzt den Stand in den weiteren Prüfungen, um die verdeckte Stelle zu ergänzen.</p>
<form method="post" action="selbsteinrichtung" class="reflection-actions">
<input type="hidden" name="lang" value="{language}"><input type="hidden" name="mode" value="{language_mode}">
<input type="hidden" name="csrf" value="{csrf}"><input type="hidden" name="glare_id" value="">
<label>Aktueller Zählerstand<input name="fallback_value" inputmode="decimal" maxlength="16" placeholder="z. B. 10512,345" required></label>
<button type="submit" name="action" value="confirm-reflection">Bestätigen und übernehmen</button>
</form></div>
<!-- 0.5.28: steps on the left, the picture being tested on the right; the frame list folded away below. -->
<div class="calibration-layout">
<div class="calibration-main">
<div class="setup-timeline-box" role="group" aria-labelledby="setup-timeline-title" hidden>
<h3 id="setup-timeline-title">So weit ist die Einrichtung</h3>
<ol class="setup-timeline" aria-live="polite"></ol>
<p class="setup-timeline-stats"></p>
</div>
</div>
<div class="calibration-side">
{calibration_preview_html}
<div class="setup-rounds-box" hidden>
<h4>Bilder bisher</h4>
<ol class="setup-rounds"></ol>
</div>
</div>
</div>
<p class="calibration-image-hint settings-note" hidden></p>
<div class="calibration-actions">
<button type="button" id="calibration-open-region">Ziffernfeld manuell markieren</button>
{calibration_skip_html}
</div>
<details class="setup-help calibration-candidate-panel" hidden><summary>Gefundene Rahmen (Kandidaten)</summary><ol class="calibration-candidates"></ol></details>
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
<p id="preview-time" class="settings-note" hidden></p>
<p id="ocr-method" class="settings-note" hidden></p>
<details id="ocr-candidate-details" hidden>
<summary>Beste Kandidaten der Rahmen-Nachprüfung</summary>
<ol id="ocr-candidates"></ol>
</details>
<p class="legend" id="preview-legend" {preview_legend_hidden}><span class="green-key">Grün:</span> Ziffer gelesen · <span class="yellow-key">Gelb:</span> Ziffer schwankte zwischen OCR-Versuchen oder wurde aus mehreren Versuchen zusammengesetzt · <span class="red-key">Rot:</span> Ziffer weiterhin unklar · <span class="grey-key">Grau:</span> Stelle wurde nicht verglichen (z. B. drehende letzte Rolle). Die Farben zeigen OCR-Sicherheit, nicht die Übereinstimmung mit dem Referenzstand. Ohne automatisch erkannte Ziffernrahmen sind die Bereiche nur näherungsweise aufgeteilt.</p>
</div>
</details>
<div class="background-work-box">
<label class="check-option background-work-toggle"><input type="checkbox" id="show-background-work"> Hintergrundaufgaben anzeigen</label>
<section id="background-live" class="background-live" aria-label="Hintergrundaufgaben" hidden>
<p class="settings-note">Hier siehst du, was die App zwischen den regulären Prüfungen selbstständig erledigt: die letzte Nachkommastelle genauer bestimmen, unklare Ergebnisse nachprüfen und neue Leseverfahren testen. Nur zur Information – du musst nichts tun.</p>
<div id="background-live-list"></div>
<p class="settings-note background-load" id="background-load" role="status"></p>
</section>
</div>
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
<p class="failure-recovery setting-link" id="automatic-recovery" data-state="retrying" data-setting="failure_pause_minutes" role="link" tabindex="0" title="Zur Einstellung" {recovery_hidden}>{recovery_notice}</p>
<p class="settings-note" id="report-bug-hint" {recovery_hidden}>Klappt es dauerhaft nicht? <a href="fehler-melden" target="_blank" rel="noopener noreferrer">Fehler melden</a> (öffnet ein vorausgefülltes Formular auf GitHub, ohne private Daten).</p>
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
<p class="settings-note frames-note" id="frames-note-overview">{frames_note}</p>
<section class="consumption-panel" aria-labelledby="consumption-title">
<h2 id="consumption-title">Verbrauch</h2>
<dl class="consumption-summary">
<div><dt>Diese Stunde</dt><dd id="consumption-hour">–</dd></div>
<div><dt>Heute</dt><dd id="consumption-day">–</dd></div>
</dl>
<div class="consumption-chart" id="consumption-chart" role="img" aria-label="Verbrauch je Stunde, letzte 24 Stunden" hidden></div>
<p class="consumption-chart-axis" id="consumption-chart-axis" hidden><span>vor 24 h</span><span id="consumption-chart-peak"></span><span>jetzt</span></p>
<p id="consumption-resolution" class="settings-note" hidden></p>
<p id="consumption-empty" class="settings-note">Die Statistik füllt sich mit bestätigten Ablesungen.</p>
<details id="consumption-details" hidden>
<summary>Verlauf nach Stunde und Tag</summary>
<p class="settings-note">Liegt eine Stunden- oder Tagesgrenze zwischen zwei Ablesungen, verteilt die App den Verbrauch anteilig. Zeiträume ohne Ablesung bleiben leer.</p>
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
<p><a class="button-link" id="debug-log-download" href="debug-protokoll" download="ai-meter-reader-debug.jsonl">Protokoll herunterladen</a>
<a class="button-link" id="report-bug" href="fehler-melden" target="_blank" rel="noopener noreferrer">Fehler melden</a></p>
<p class="settings-note" id="report-bug-note">Öffnet auf GitHub ein vorausgefülltes Fehlerformular mit App-Version, Art der Bildquelle und Fehlquote. Es wird nichts automatisch gesendet; hänge das heruntergeladene Protokoll selbst an.</p>
<pre id="debug-log-text" class="debug-log-text">–</pre>
</details>
<details id="system-monitor">
<summary>Systemauslastung</summary>
<p class="settings-note">Auslastung des Geräts und Anteil dieser App. Die Texterkennung zählt zur App. Die Werte gelten für die letzten Sekunden.</p>
<dl class="consumption-summary" id="system-monitor-values">
<div><dt>Prozessor gesamt</dt><dd id="system-cpu">–</dd></div>
<div><dt>Prozessor durch die App</dt><dd id="system-app-cpu">–</dd></div>
<div><dt>Arbeitsspeicher belegt</dt><dd id="system-memory">–</dd></div>
<div><dt>Arbeitsspeicher der App</dt><dd id="system-app-memory">–</dd></div>
<div><dt>Temperatur</dt><dd id="system-temperature">–</dd></div>
</dl>
</details>
<details id="background-work">
<summary>Schattenmodus und Arbeit im Hintergrund</summary>
<p class="settings-note">Was Experimente im Schattenmodus und die Arbeit in der Wartezeit geliefert haben. Beides ändert nie den Zählerstand. Gezählt wird aus dem Debug-Protokoll.</p>
<ul class="background-work" id="background-work-list"><li>–</li></ul>
</details>
<div class="manual-test-area" id="manual-test-area" {manual_area_hidden}>
<div class="manual-test-heading"><h2>Manueller Test</h2>
<button type="submit" form="manual-form" id="start-check-top">Jetzt prüfen</button>
<button type="button" id="close-manual-test">Schließen</button></div>
<div class="test-box" id="test-box" data-phase="idle" data-result="neutral" tabindex="-1" {test_hidden} role="status" aria-live="polite">
<strong id="test-head">Aktueller Schritt: Bereit</strong>
<p id="test-status">{request_status}</p>
<progress id="test-progress" max="{default_attempts}" value="0" aria-label="OCR-Versuche" hidden></progress>
<small id="test-meta">Bereit für den manuellen Test.</small>
<p id="test-live" class="test-live" hidden></p>
<div class="test-result" id="test-result" hidden>
<p id="test-result-detail"></p>
<dl id="manual-readings" hidden><dt>Erkannter Stand</dt><dd id="manual-ocr"></dd>
<dt>Referenz</dt><dd><span id="manual-reference"></span><small id="manual-reference-note" class="reference-note" hidden></small></dd>
<dt>Bildzeit</dt><dd id="manual-image-time">–</dd></dl>
<small id="test-result-stamp"></small>
<p><button type="button" id="correct-after-test" hidden>Ziffernrahmen an diesem Bild korrigieren</button></p>
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
<input name="rotation" type="number" min="-180" max="180" step="0.1" value="{rotation_value}"></label>
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
<p>Die App sucht einen passenden Rahmen und Winkel. Nach drei bestätigten Aufnahmen übernimmt die Automatik die Gegenprüfung. Das dauert meist rund fünf Minuten, höchstens 20 Minuten.</p>
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
<div class="reflection-suggestion action-needed glare-confirm" hidden>
<p><strong>Spiegelung erkannt.</strong> <span class="glare-confirm-text"></span> Bitte bestätige das und trag den aktuellen Zählerstand ein. Die App übernimmt dann den Rahmen und nutzt den Stand in den weiteren Prüfungen, um die verdeckte Stelle zu ergänzen.</p>
<form method="post" action="selbsteinrichtung" class="reflection-actions">
<input type="hidden" name="lang" value="{language}"><input type="hidden" name="mode" value="{language_mode}">
<input type="hidden" name="csrf" value="{csrf}"><input type="hidden" name="glare_id" value="">
<label>Aktueller Zählerstand<input name="fallback_value" inputmode="decimal" maxlength="16" placeholder="z. B. 10512,345" required></label>
<button type="submit" name="action" value="confirm-reflection">Bestätigen und übernehmen</button>
</form></div>
<p class="calibration-image-hint settings-note" hidden></p>
<button type="button" id="calibration-proposal" hidden>Gefundenen Rahmen im Test prüfen</button>
<progress id="calibration-progress" aria-label="Verstrichene Zeit der Selbsteinrichtung" hidden></progress>
<form method="post" action="selbsteinrichtung">
<input type="hidden" name="lang" value="{language}">
<input type="hidden" name="mode" value="{language_mode}">
<input type="hidden" name="csrf" value="{csrf}">
<input id="calibration-limit" name="image_limit" type="hidden" value="{calibration_limit}">
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
<p class="settings-note quality-hint" {quality_hint_hidden}>Je schlechter das Kamerabild (Unschärfe, Spiegelungen, schwaches Licht, schräger Blickwinkel), desto länger dauern Einrichtung und Optimierung. Ein scharfes, gerades Bild ohne Lichtfleck auf den Ziffern spart am meisten Zeit.</p>
<div class="source-mode-guide">
<label class="source-mode-select">Woher kommt das Zählerbild?<select name="source_mode" id="wizard-source-mode" required>{wizard_source_options}</select></label>
<div class="source-cards" id="wizard-source-cards" role="radiogroup" aria-label="Woher kommt das Zählerbild?" hidden>
<button type="button" class="source-card" role="radio" aria-checked="false" data-mode="esphome" data-kit="1"><span class="source-card-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="3" width="14" height="18" rx="2"/><circle cx="12" cy="10" r="3.5"/><path d="M9 17h6"/><path d="M19.5 3.5l1.5-1.5M21 6h1.5"/></svg></span><strong>Zählerkamera bauen</strong><small>ESP32 mit Kamera: Firmware mit einem Klick installieren, Blitz inklusive.</small></button>
<button type="button" class="source-card" role="radio" aria-checked="false" data-mode="esphome"><span class="source-card-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 8a2 2 0 0 1 2-2h2l1.5-2h7L17 6h2a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><circle cx="12" cy="12.5" r="3.5"/></svg></span><strong>Kamera aus Home Assistant</strong><small>ESPHome, Überwachungskamera oder Handy. Die App liest den Stand selbst.</small></button>
<button type="button" class="source-card" role="radio" aria-checked="false" data-mode="camera"><span class="source-card-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 8a2 2 0 0 1 2-2h2l1.5-2h7L17 6h2a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M9 12.5l2 2 4-4"/></svg></span><strong>Kamera mit Vergleichswert</strong><small>Standbild pro Prüfung, abgeglichen mit einem vorhandenen Zählersensor.</small></button>
<button type="button" class="source-card" role="radio" aria-checked="false" data-mode="slfork"><span class="source-card-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="7" y="7" width="10" height="10" rx="1.5"/><path d="M10 3v4M14 3v4M10 17v4M14 17v4M3 10h4M3 14h4M17 10h4M17 14h4"/></svg></span><strong>AI on the Edge / SLFork</strong><small>Die App prüft den ESP-Messwert oder nutzt den ESP nur als Kamera.</small></button>
</div>
<p class="settings-note source-cards-hint" id="wizard-source-cards-hint" role="alert" hidden>Bitte wähle zuerst aus, woher das Zählerbild kommt.</p>
</div>
<div id="wizard-kit" class="setup-help kit-panel" hidden>
<p><strong>Zählerkamera mit einem Klick</strong> – ein ESP32 mit Kamera wird zur fertigen Zählerkamera, ohne ESPHome-Kenntnisse. Welches Board hast du?</p>
<div class="kit-boards" role="radiogroup" aria-label="Board">
<label class="kit-board"><input type="radio" form="wizard-kit-choice" name="kit_board" value="auto" checked><span><strong>Automatisch erkennen</strong><small>ESP32-CAM oder ESP32-S3-CAM</small></span></label>
<label class="kit-board"><input type="radio" form="wizard-kit-choice" name="kit_board" value="esp32-cam"><span><strong>AI-Thinker ESP32-CAM</strong><small>mit Blitz-LED</small></span></label>
<label class="kit-board"><input type="radio" form="wizard-kit-choice" name="kit_board" value="esp32-s3-cam"><span><strong>ESP32-S3-CAM</strong><small>Freenove oder AI-Thinker, mit Blitz</small></span></label>
<label class="kit-board"><input type="radio" form="wizard-kit-choice" name="kit_board" value="xiao-esp32s3-sense"><span><strong>XIAO ESP32S3 Sense</strong><small>sehr klein, ohne Blitz</small></span></label>
<label class="kit-board"><input type="radio" form="wizard-kit-choice" name="kit_board" value="waveshare-esp32s3-eth"><span><strong>Waveshare ESP32-S3-ETH</strong><small>Netzwerkkabel statt WLAN</small></span></label>
</div>
<ol class="kit-steps">
<li><a class="button-link kit-install" id="wizard-kit-install" href="{kit_installer_url}?board=auto&amp;lang={language}" target="_blank" rel="noopener">Firmware installieren</a> <span>Öffnet den Installer in einem neuen Tab. Am Computer Chrome oder Edge benutzen und das Board per USB anstecken.</span></li>
<li><span>Im Installer das WLAN eintragen.</span></li>
<li><span>Sobald Home Assistant die neue Zählerkamera findet, erscheint hier „In Home Assistant hinzufügen“. Alternativ geht es unter <a href="/config/integrations/dashboard" target="_top">Geräte &amp; Dienste</a>.</span></li>
</ol>
<div id="wizard-kit-pending" class="kit-pending" hidden><p id="wizard-kit-pending-text"></p><button type="button" id="wizard-kit-add">In Home Assistant hinzufügen</button></div>
<p id="wizard-kit-status" class="settings-note kit-status" role="status" aria-live="polite">Sobald die Kamera in Home Assistant ist, wählt der Assistent sie hier selbst aus.</p>
<fieldset id="wizard-kit-extras" class="kit-extras" hidden><legend>Zusätze der Zählerkamera (ab Werk aus)</legend>
<label class="check-option" data-extra-row="wlan_kanal"><input type="checkbox" form="wizard-kit-choice" data-extra="wlan_kanal"> <span><strong>WLAN-Kanal</strong> <small>zeigt in der Historie, ob der Router den Kanal wechselt</small></span></label>
<label class="check-option" data-extra-row="wlan_zugangspunkt"><input type="checkbox" form="wizard-kit-choice" data-extra="wlan_zugangspunkt"> <span><strong>WLAN-Zugangspunkt</strong> <small>zeigt bei mehreren Routern oder Repeatern, wo die Kamera hängt</small></span></label>
<p id="wizard-kit-extras-status" class="settings-note" role="status" aria-live="polite"></p>
</fieldset>
</div>
<p id="wizard-stream-hint" class="settings-note" hidden>Überwachungskamera oder Handy mit Bildadresse (Snapshot, MJPEG, RTSP)? <a href="/config/integrations/dashboard/add?domain=generic" target="_top">In Home Assistant als Kamera anlegen</a>, danach erscheint sie hier in der Liste.</p>
<div id="wizard-discovered-sources" class="setup-help">
<label>Geräte suchen<input type="search" id="wizard-camera-search" placeholder="z. B. Gaszähler"></label>
<div class="discovered-row"><label>In Home Assistant gefunden<select id="wizard-discovered-source" disabled><option value="">Es wurden keine Geräte gefunden</option></select></label><button type="button" id="wizard-refresh-sources" class="icon-refresh" aria-label="Neu suchen" title="Neu suchen">↻</button></div>
<p id="wizard-discovery-status" class="settings-note" role="status" aria-live="polite" hidden></p>
</div>
<label id="wizard-source-url">ESP-Adresse<input name="url" value="{source_url}" maxlength="150" placeholder="http://esp-gaszaehler.local"></label>
<div id="wizard-esp-camera-only" class="setup-help" hidden>
<label class="check-option"><input type="checkbox" name="esp_camera_only" value="1" {esp_camera_only_checked}> ESP nur als Kamera verwenden</label>
<p>Wenn der ESP den Zähler nicht zuverlässig liest, kann die App das Bild direkt abrufen und selbst ablesen.</p>
</div>
<label id="wizard-source-camera">Home-Assistant-Kamera<input name="camera" value="{source_camera}" maxlength="80" placeholder="camera.gaszaehler"></label>
<label id="wizard-source-reference">Vergleichssensor (optional)<input name="reference" value="{source_reference}" maxlength="80" placeholder="sensor.gaszaehler"></label>
<input type="hidden" name="camera_light_present" value="1"><label class="check-option" id="wizard-source-camera-light"><input type="checkbox" name="camera_light" value="1" {camera_light_checked}> Blitz der Kamera verwenden</label>
<label id="wizard-source-light" title="Wird für jede Aufnahme kurz eingeschaltet, wie der Blitz bei AI on the Edge.">Externes Licht (optional, hat Vorrang)<input name="light" value="{source_light}" maxlength="80" placeholder="leer = Blitz der Kamera, z. B. light.lampe_keller"></label>
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
<p>Der Präzisionsmodus ist experimentell. Der Wert selbst ist genau, aber die schnell laufende letzte Rolle wird oft nicht sicher erkannt. Dann prüft die App vorübergehend mit zwei Nachkommastellen. Ist die Bildqualität zu schlecht oder lässt sich die letzte Ziffer trotz mehrerer Versuche nicht lesen, gibt die App die Suche nach sechs Stunden auf und prüft dauerhaft mit zwei Nachkommastellen, bis zur nächsten Einrichtung.</p>
<p {wizard_initial_hidden}>Die Selbsteinrichtung bestätigt zuerst die ersten zwei Nachkommastellen. Die dritte sucht die App danach automatisch im Hintergrund und justiert die Rahmen mit der Zeit selbst nach. Du musst dafür nichts tun.</p>
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
<input name="image_limit" type="hidden" value="{calibration_limit}" disabled>
<p class="settings-note">Startet nach dem Speichern. Nach drei bestätigten Aufnahmen übernimmt die Automatik die Gegenprüfung.</p>
</div>
<div class="setup-help">
<input type="hidden" name="fine_alignment_option_present" value="1">
<label class="check-option"><input type="checkbox" name="fine_alignment_enabled" value="1" {wizard_fine_alignment_checked}> Ziffernrahmen langfristig feinjustieren</label>
<label class="check-option"><input type="checkbox" name="self_repair_enabled" value="1" {wizard_self_repair_checked}> Selbstreparatur bei wiederholten Fehlmessungen</label>
<p class="settings-note">Die App sucht nach etwa 40 Minuten anhaltender Erkennungsprobleme einen besseren Rahmen und versucht es danach alle zwei Stunden erneut. Probleme nur an der letzten Rolle zählen dabei nicht mit. Der bisherige Rahmen gilt bis zur erfolgreichen Gegenprobe.</p>
</div>
<div class="setup-help">
<input type="hidden" name="reflection_option_present" value="1">
<label class="check-option"><input type="checkbox" name="reflection_estimate_enabled" value="1" {reflection_enabled_checked}> Verdeckte Ziffern ergänzen</label>
<p class="settings-note">Bei Spiegelungen hilfreich. Die App schätzt verdeckte Stellen nur, wenn Zählerstände und Durchfluss genau eine Ergänzung zulassen. Geschätzte Ziffern bleiben gelb.</p>
<div id="wizard-reflection-options" hidden>
<button type="button" id="wizard-reflection-load">Ziffernrahmen für Spiegelungen suchen</button>
<figure class="crop-live-preview" id="wizard-reflection-preview" hidden>
<figcaption>Gelbe Rahmen sind möglicherweise gespiegelt. Tippe auf einen Rahmen, um die Stelle als verdeckt zu markieren oder die Markierung aufzuheben (höchstens zwei). Zum Verschieben den Rahmen ziehen.</figcaption>
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
<details class="setup-help"><summary>ⓘ Warum das Prüfintervall ändern?</summary><p>Nach einem fehlgeschlagenen automatischen Test folgen bis zu zwei weitere Prüfungen im Abstand von fünf Minuten. Sind alle drei erfolglos, pausiert die App für die eingestellte Zeit (Standard: 30 Minuten) und prüft dann erneut. Nach Erfolg gilt wieder dein eingestelltes Intervall. Ein kürzeres Intervall kann helfen, wenn sich der Zähler beim Weiterdrehen vorübergehend schlecht lesen lässt.</p></details>
<label>Maximaler Durchfluss (m³/h)<input name="max_flow" type="text" inputmode="decimal" maxlength="10" value="{max_flow}" required></label>
<details class="setup-help"><summary>Verbrauch auch in kWh (optional)</summary>
<div class="energy-factors">
<label>Zustandszahl<input name="gas_state_factor" type="text" inputmode="decimal" maxlength="7" placeholder="z. B. 0,9636" value="{gas_state_factor}"></label>
<label>Brennwert (kWh/m³)<input name="calorific_value" type="text" inputmode="decimal" maxlength="7" placeholder="z. B. 11,25" value="{calorific_value}"></label>
<label>oder Umrechnungsfaktor<input name="kwh_conversion_factor" type="text" inputmode="decimal" maxlength="7" placeholder="z. B. 10,84" value="{kwh_conversion_factor}"></label>
</div>
<p>Die Werte stehen auf der Gasabrechnung oder beim Netzbetreiber. Entweder Zustandszahl und Brennwert eintragen oder nur den fertigen Umrechnungsfaktor (er hat Vorrang). Dann gibt es zusätzlich <code>sensor.rf1_verbrauch_gesamt_kwh</code> für das Energie-Dashboard. Leer lassen schaltet es ab.</p>
</details>
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
<label>3. Bilddrehung bei Bedarf (°)<input name="rotation" type="number" min="-180" max="180" step="0.1" value="{auto_rotation_value}"></label>
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
<details class="setup-help"><summary>ⓘ Bild einrichten</summary><p>Die automatische Erkennung versucht, den Ziffernrahmen zu finden. Bei einer unsicheren Ablesung folgen bis zu zehn zusätzliche Bildauswertungen; die App setzt einzelne Ziffern nur bei einer strikten Mehrheit zusammen. Nach drei fehlgeschlagenen automatischen Prüfungen mit unterschiedlichen Bildabrufen pausiert sie für die eingestellte Zeit (Standard: 30 Minuten). Prüfe bei wiederholten Fehlern auch Beleuchtung, Abstand und Fokus. Beim Livebild kann AI Meter Reader bis zu 10 frische Standbilder innerhalb von höchstens 20 Sekunden prüfen.</p></details>
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
<details class="setup-help experiments-box" id="wizard-experiments">
<summary>Experimentelle Funktionen (Schattenbetrieb)</summary>
<input type="hidden" name="experiments_option_present" value="1">
<label class="check-option"><input type="checkbox" name="experiments_enabled" value="1" {experiments_checked}> Experimentelle Funktionen testen</label>
<label class="experiment-option">Perspektivkorrektur (Kippung)
<select name="experiment_perspective">{experiment_perspective_levels}</select></label>
<label class="experiment-option">Digitalanzeige: Segmente direkt lesen
<select name="experiment_seven_segment">{experiment_seven_segment_levels}</select></label>
<p>Schattenmodus: Die App liest jedes Bild zusätzlich mit dem Experiment, aber nur, wenn der Rechner gerade Leistung frei hat. Es zählt weiterhin nur das bewährte Ergebnis. Den Vergleich findest du unter Werkzeuge › Schattenmodus und Arbeit im Hintergrund. Die meisten brauchen das nicht.</p>
<p>Aktiv testen (das Experiment bestimmt das Ergebnis mit, zeitlich begrenzt) ist in dieser Version noch für kein Experiment freigegeben.</p>
<p>Du kannst das jederzeit unter Einstellungen › Automatische Prüfung wieder ändern.</p>
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
<input type="hidden" name="camera_light_present" value="1"><label class="check-option" id="source-camera-light"><input type="checkbox" name="camera_light" value="1" {camera_light_checked}> Blitz der Kamera verwenden</label>
<label id="source-light" title="Wird für jede Aufnahme kurz eingeschaltet, wie der Blitz bei AI on the Edge: Licht an, 1,5 Sekunden warten, Bild holen, Licht aus.">Externes Licht (optional, hat Vorrang)
<input name="light" value="{source_light}" placeholder="leer = Blitz der Kamera, z. B. light.lampe_keller" maxlength="80"></label>
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
<div class="settings-grid" id="auto-settings-grid">
<label class="settings-field"><span class="field-label">Vergleich</span>
<select name="decimals">{auto_decimal_options}</select></label>
<label class="settings-field"><span class="field-label">Max. OCR-Versuche</span>
<select name="attempts">{auto_attempt_options}</select></label>
<div class="settings-field settings-wide" data-precision-options {precision_hidden}>
<label class="check-option"><input type="checkbox" name="precision_mode" value="1" {precision_checked}> Präzisionsmodus: auch die dritte Nachkommastelle vergleichen</label>
<small class="field-help">Der Präzisionsmodus ist experimentell. Der Wert selbst ist genau, aber die schnell laufende letzte Rolle wird oft nicht sicher erkannt. Dann prüft die App vorübergehend mit zwei Nachkommastellen. Ist die Bildqualität zu schlecht oder lässt sich die letzte Ziffer trotz mehrerer Versuche nicht lesen, gibt die App die Suche nach sechs Stunden auf und prüft dauerhaft mit zwei Nachkommastellen, bis zur nächsten Einrichtung.</small>
</div>
<label class="settings-field" title="Nach einer unklaren Ablesung folgt ein zusätzlicher Versuch nach fünf Minuten. Schlägt auch der fehl, gilt wieder dieses Intervall."><span class="field-label">Prüfintervall (Minuten)</span>
<input name="interval_minutes" type="number" min="1" max="{max_interval_minutes}" value="{interval_minutes}" required>
<small class="field-help" {slfork_interval_hidden}>Bei AI on the Edge / SLFork liegen reguläre Prüfungen mindestens fünf Minuten auseinander.</small></label>
<label class="settings-field"><span class="field-label">Pause nach drei Fehlprüfungen (Minuten)</span>
<input name="failure_pause_minutes" type="number" min="5" max="240" value="{failure_pause_minutes}" required>
<small class="field-help">Danach prüft die App wieder normal. Bleibt nur die letzte Rolle unklar, pausiert sie nicht.</small></label>
<label class="settings-field"><span class="field-label">Übereinstimmung für die Intensivprüfung (%)</span>
<input name="intensive_agreement" type="number" min="1" max="100" step="1" value="{intensive_agreement}" required>
<small class="field-help">Ab diesem Wert wechselt die Selbsteinrichtung in die Intensivprüfung. Eine einzelne vermutete Ziffernposition kann sie auch früher gezielt prüfen.</small></label>
<label class="settings-field"><span class="field-label">Maximaler Durchfluss (m³/h)</span>
<input name="max_flow" type="text" inputmode="decimal" maxlength="10" value="{max_flow}" required>
<small class="field-help">Qmax steht auf dem Typenschild deines Zählers. Die App erkennt ihn nicht selbst: Ohne deine Angabe rechnet sie mit 6 m³/h, dem üblichen Wert eines Haushaltszählers (G4).</small></label>
<label class="settings-field"><span class="field-label">Ziffernfarbe</span>
<select name="polarity">{auto_polarity_options}</select></label>
<label class="settings-field"><span class="field-label">Bildbereich</span>
<select name="crop_mode" id="auto-crop-mode">{auto_crop_mode_options}</select></label>
</div>
<p class="settings-note frames-note" id="frames-note-settings">{frames_note}</p>
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
<input name="rotation" type="number" min="-180" max="180" step="0.1" value="{auto_rotation_value}"></label>
<label>Breite der Vorkommastellen
<input name="width" type="number" min="1" max="9999" value="{auto_width_value}"></label>
<p class="settings-note">Wähle den Ausschnitt im Originalbild. Die Vorkommabreite gilt nach der Drehung.</p>
</div>
<div class="settings-more">
<details class="help">
<summary>Verbrauch auch in kWh</summary>
<div class="energy-factors">
<label>Zustandszahl<input name="gas_state_factor" type="text" inputmode="decimal" maxlength="7" placeholder="z. B. 0,9636" value="{gas_state_factor}"></label>
<label>Brennwert (kWh/m³)<input name="calorific_value" type="text" inputmode="decimal" maxlength="7" placeholder="z. B. 11,25" value="{calorific_value}"></label>
<label>oder Umrechnungsfaktor<input name="kwh_conversion_factor" type="text" inputmode="decimal" maxlength="7" placeholder="z. B. 10,84" value="{kwh_conversion_factor}"></label>
</div>
<small>Die Werte stehen auf der Gasabrechnung oder beim Netzbetreiber. Entweder Zustandszahl und Brennwert eintragen oder nur den fertigen Umrechnungsfaktor (er hat Vorrang). Dann gibt es zusätzlich <code>sensor.rf1_verbrauch_gesamt_kwh</code> für das Energie-Dashboard. Leer lassen schaltet es ab.</small>
</details>
<details class="help setup-help">
<summary>ⓘ Automatik im Hintergrund verbessern</summary>
<label class="check-option"><input type="checkbox" name="fine_alignment_enabled" value="1" {fine_alignment_checked}> Ziffernrahmen langfristig feinjustieren</label>
<label class="check-option"><input type="checkbox" name="self_repair_enabled" value="1" {self_repair_checked}> Selbstreparatur bei wiederholten Fehlmessungen</label>
<p>Die App sucht nach etwa 40 Minuten anhaltender Erkennungsprobleme einen besseren Rahmen und versucht es danach alle zwei Stunden erneut. Probleme nur an der letzten Rolle zählen dabei nicht mit. Der bisherige Rahmen gilt bis zur erfolgreichen Gegenprobe.</p>
<label class="check-option"><input type="checkbox" name="adaptive_interval_enabled" value="1" {adaptive_interval_checked}> Prüfintervall an den Verbrauch anpassen (früher prüfen, wenn eine Rolle bald umspringt)</label>
</details>
<details class="help setup-help experiments-box" id="experiments-settings">
<summary>Experimentelle Funktionen (Schattenbetrieb)</summary>
<label class="check-option"><input type="checkbox" name="experiments_enabled" value="1" {experiments_checked}> Experimentelle Funktionen testen</label>
<label class="experiment-option">Perspektivkorrektur (Kippung)
<select name="experiment_perspective">{experiment_perspective_levels}</select></label>
<label class="experiment-option">Digitalanzeige: Segmente direkt lesen
<select name="experiment_seven_segment">{experiment_seven_segment_levels}</select></label>
<p>Schattenmodus: Die App liest jedes Bild zusätzlich mit dem Experiment, aber nur, wenn der Rechner gerade Leistung frei hat. Es zählt weiterhin nur das bewährte Ergebnis. Den Vergleich findest du unter Werkzeuge › Schattenmodus und Arbeit im Hintergrund. Die meisten brauchen das nicht.</p>
<p>Aktiv testen (das Experiment bestimmt das Ergebnis mit, zeitlich begrenzt) ist in dieser Version noch für kein Experiment freigegeben.</p>
</details>
<div class="reflection-settings setup-help" id="reflection-settings">
<label class="check-option"><input type="checkbox" name="reflection_estimate_enabled" value="1" {reflection_enabled_checked}> Verdeckte Ziffern ergänzen</label>
<details class="help" id="reflection-settings-help">
<summary>ⓘ Spiegelungen und verdeckte Ziffern</summary>
<p>Die App kann je eine verdeckte Stelle vor und nach dem Komma ergänzen, wenn nur ein Ergebnis zum bisherigen Stand und zum maximalen Durchfluss passt. Berechnete Ziffern bleiben gelb. Ein datierter Startwert kann als erster Vergleichswert dienen.</p>
<label class="check-option"><input type="checkbox" name="reflection_suggestion_hidden" value="1" {reflection_hide_checked}> Vorschlag bei wiederholt unlesbarer Ziffer ausblenden</label>
<label class="check-option"><input type="checkbox" name="quality_hint_hidden" value="1" {quality_hint_checked}> Hinweis „Bildqualität bestimmt die Dauer“ ausblenden</label>
</details>
</div>
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
<button type="button" id="open-reset-keep">Werkseinstellungen – Statistik behalten</button>
<button type="button" id="open-reset">Auf Werkseinstellungen zurücksetzen</button>
</div></details>
</div>
<dialog class="setup-dialog" id="demo-dialog" aria-labelledby="demo-title">
<div class="dialog-heading"><h2 id="demo-title">Zähler-Demo</h2><button type="button" id="close-demo">Schließen</button></div>
<p>Probiere die Erkennung ohne eigene Kamera. Deine echte Einrichtung und Verbrauchsdaten bleiben getrennt.</p>
<p class="settings-note">Echte Kamerabilder eines Gaszählers, gelesen wie bei der automatischen Prüfung. Zu sehen ist nur das Zählwerk; alles andere ist übermalt.</p>
<div class="crop-actions">
<button type="button" class="run-demo-real" data-picture="1">Echtes Bild 1</button>
<button type="button" class="run-demo-real" data-picture="2">Echtes Bild 2</button>
<button type="button" class="run-demo-real" data-picture="3">Echtes Bild 3</button>
<button type="button" class="run-demo-real" data-picture="4">Echtes Bild 4</button>
</div>
<p class="settings-note">Künstliches Zählerbild:</p>
<div class="crop-actions">
<button type="button" id="run-demo-clear">Schräges Bild prüfen</button>
<button type="button" id="run-demo-glare">Spiegelung ausprobieren</button>
</div>
<p id="demo-status" role="status"></p>
<div id="demo-results" hidden>
<p id="demo-reading"></p><p id="demo-estimate"></p>
<div class="demo-grid">
<figure><img id="demo-original" alt="Zählerbild der Demo"><figcaption>Originalbild</figcaption></figure>
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
<p id="reset-progress" class="settings-note" role="status" hidden>Zurücksetzen angefordert. Eine laufende Prüfung kann das kurz verzögern. Danach öffnet sich die Einrichtung von selbst.</p>
</dialog>
</div>
</main>

<footer class="page-footer"><a class="app-version" href="https://github.com/Eifellayer/meter-ocr/blob/main/rf1_ocr_test/CHANGELOG.md" target="_blank" rel="noopener noreferrer">{app_name} {app_version}</a> · Kostenloses Hobbyprojekt · <a href="https://www.paypal.com/donate/?hosted_button_id=FG4Q7VKQJ9BW8" target="_blank" rel="noopener noreferrer">Freiwillig mit PayPal unterstützen</a> · <a href="mailto:amr@eifel-layer.de">Kontakt: amr@eifel-layer.de</a>
<details class="about-project"><summary>Über AI Meter Reader</summary><p><a href="https://github.com/Eifellayer" target="_blank" rel="noopener noreferrer">Projekt von EifelLayer auf GitHub</a></p><p>KI-unterstützt entwickelt. Keine geeichte Messung oder Gewähr für OCR-Ergebnisse. Bitte Zählerstände bei Bedarf direkt am Gerät prüfen.</p><p><a id="roadmap-link" href="https://github.com/Eifellayer/meter-ocr/blob/main/RELEASE-PLAN.md" target="_blank" rel="noopener noreferrer">Roadmap auf GitHub</a></p></details>
</footer>
<script>
let next = {next_check};
let lastBackgroundWork = [];
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
function openSetting(name) {{
  // Settings mentioned in a notice: one click leads straight to the field.
  activateTab('settings');
  const input = document.querySelector(`#view-settings [name="${{name}}"]`);
  if (!input) return;
  const details = input.closest('details');
  if (details) details.open = true;
  input.scrollIntoView({{block: 'center', behavior: 'smooth'}});
  input.focus({{preventScroll: true}});
  input.classList.add('setting-highlight');
  setTimeout(() => input.classList.remove('setting-highlight'), 2500);
}}
for (const link of document.querySelectorAll('[data-setting]')) {{
  link.addEventListener('click', () => openSetting(link.dataset.setting));
  link.addEventListener('keydown', event => {{
    if (event.key === 'Enter' || event.key === ' ') {{ event.preventDefault(); openSetting(link.dataset.setting); }}
  }});
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
function setupSuccessClosed() {{
  try {{ return localStorage.getItem('setupSuccessClosed'); }} catch (_) {{ return null; }}
}}
document.querySelector('#setup-success-close')?.addEventListener('click', () => {{
  const box = document.querySelector('#setup-success');
  try {{ localStorage.setItem('setupSuccessClosed', document.querySelector('#setup-duration').textContent || ''); }} catch (_) {{}}
  box.hidden = true;
}});
const settingsSections = ['#source-settings', '#automatic-settings', '#notification-settings'];
const readingEnteredAt = searchPrefs.get('saved') === 'reading' ? Date.now() / 1000 : 0;
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
async function checkDemo(reflection, picture = '') {{
  const buttons = demoDialog.querySelectorAll('.crop-actions button');
  buttons.forEach(button => button.disabled = true);
  demoResults.hidden = true;
  demoStatus.textContent = 'Demo-Bild wird geprüft …';
  try {{
    const fields = new URLSearchParams({{csrf: '{csrf}', lang, reflection: reflection ? '1' : '0', picture}});
    let reply = await fetch('zaehler-demo', {{method: 'POST', body: fields}}).catch(() => null);
    if (!reply || !reply.ok) {{
      // The machine may be busy with a check or a setup: one quiet second try.
      demoStatus.textContent = lang === 'en' ? 'The app is busy, trying once more …' : 'Die App ist gerade beschäftigt, zweiter Versuch …';
      await new Promise(resolve => setTimeout(resolve, 3000));
      reply = await fetch('zaehler-demo', {{method: 'POST', body: fields}});
    }}
    if (!reply.ok) throw Error();
    const result = await reply.json();
    document.querySelector('#demo-original').src = 'data:image/jpeg;base64,' + result.image;
    document.querySelector('#demo-aligned').src = 'data:image/jpeg;base64,' + result.aligned;
    document.querySelector('#demo-reading').textContent =
      'Abgelesen ' + result.reading + ' m³ · Drehung ' + result.angle + '° · ' +
      (result.real ? (result.complete ? 'Alle geprüften Ziffern erkannt. ' : 'Mindestens eine Ziffer blieb offen. ') +
         'Die letzte Rolle dreht sich ständig und wird wie im Betrieb nicht gelesen (grauer Rahmen).' :
       result.reading === result.expected ? 'Alle Ziffern erkannt.' :
       'Mindestens eine Ziffer blieb offen.');
    document.querySelector('#demo-estimate').textContent = result.estimate ?
      'Aus einem Beispiel-Referenzwert geschätzt: ' + result.estimate + ' m³.' : '';
    demoStatus.textContent = '';
    demoResults.hidden = false;
  }} catch (_) {{
    demoStatus.textContent = 'Die Demo konnte nicht geladen werden, weil die App gerade ausgelastet ist. Versuche es in einer Minute noch einmal.';
  }} finally {{
    buttons.forEach(button => button.disabled = false);
  }}
}}
document.querySelector('#run-demo-clear').addEventListener('click', () => checkDemo(false));
for (const button of document.querySelectorAll('.run-demo-real'))
  button.addEventListener('click', () => checkDemo(false, button.dataset.picture));
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
    if (!response.ok) {{
      const told = (response.headers.get('Content-Type') || '').startsWith('application/json')
        ? await response.json().catch(() => null) : null;
      throw new Error(told && told.reason || '');
    }}
    const image = await response.blob();
    if (revision !== wizardPreviewRevision) return;
    wizardImageUrl = URL.createObjectURL(image);
    wizardImage.src = wizardImageUrl;
    wizardImage.hidden = false;
    wizardImageStatus.hidden = true;
  }} catch (error) {{
    if (revision === wizardPreviewRevision)
      wizardImageStatus.textContent = error.message || 'Kein Kamerabild verfügbar. Prüfe die Bildquelle oder lies direkt am Zähler ab.';
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
      // B3: say what is marked and that it will be used.
      const names = [...marked].sort((a, b) => a - b).map(index => index + 1);
      reflectionStatus.textContent = names.length
        ? 'Stelle ' + names.join(' und ') + ' als verdeckt markiert. Das wird mit der Einrichtung gespeichert und bei der Selbsteinrichtung und allen Prüfungen berücksichtigt.'
        : 'Keine Stelle markiert. Tippe auf einen Rahmen oder eine Schaltfläche, um eine verdeckte Stelle zu markieren.';
    }}
    reflectionPreview.addEventListener('digit-edit', () => {{
      if (revision === reflectionRevision) saveMarkings();
    }});
    // 0.5.14 (B1): a tap on a digit frame (without dragging it) marks or unmarks that digit.
    Array.from(layer.children).forEach((frameButton, index) => {{
      let start = null;
      frameButton.addEventListener('pointerdown', event => {{ start = [event.clientX, event.clientY]; }});
      frameButton.addEventListener('pointerup', event => {{
        if (!start || revision !== reflectionRevision) return;
        const moved = Math.hypot(event.clientX - start[0], event.clientY - start[1]);
        start = null;
        if (moved > 5) return;
        if (marked.has(index)) marked.delete(index);
        else if (marked.size < 2) marked.add(index);
        saveMarkings();
      }});
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
  if (invalid && invalid.id === 'wizard-source-mode' && !sourceCards.hidden) {{
    // The select is only kept for the form: point at the cards instead of a tiny hidden field.
    sourceCards.classList.add('needs-choice');
    sourceCardsHint.hidden = false;
    sourceCards.querySelector('.source-card').focus();
    return;
  }}
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
  document.querySelector('#wizard-source-light').hidden = mode !== 'esphome' && mode !== 'camera';
  document.querySelector('#wizard-source-camera-light').hidden = mode !== 'esphome' && mode !== 'camera';
  const attemptChoice = setupForm.querySelector('[name="attempts"]');
  if (mode === 'camera' && previousWizardSource !== 'camera' && attemptChoice.value === '5') {{
    attemptChoice.value = '10';
  }}
  previousWizardSource = mode;
  updateSourceCards();
}}
// 0.5.24: cards instead of the plain select, and the one-click meter camera.
const sourceCards = document.querySelector('#wizard-source-cards');
const sourceCardsHint = document.querySelector('#wizard-source-cards-hint');
const kitPanel = document.querySelector('#wizard-kit');
const kitStatus = document.querySelector('#wizard-kit-status');
const kitInstall = document.querySelector('#wizard-kit-install');
let kitOpen = false;
let kitTimer = null;
let kitPolls = 0;
function updateSourceCards() {{
  const mode = wizardSourceMode.value;
  sourceCards.querySelectorAll('.source-card').forEach(card => {{
    const kit = card.dataset.kit === '1';
    card.setAttribute('aria-checked', String(card.dataset.mode === mode && (mode !== 'esphome' || kit === kitOpen)));
  }});
  kitPanel.hidden = !(kitOpen && mode === 'esphome');
  document.querySelector('#wizard-stream-hint').hidden = mode !== 'esphome' || kitOpen;
  if (kitPanel.hidden) stopKitWatch(); else startKitWatch();
}}
function kitCameraFound() {{
  const kits = sourceSuggestions.filter(source => source.kit && source.mode === 'esphome' && source.available !== false);
  if (!kits.length) return false;
  const current = setupForm.elements.camera.value.trim();
  const source = kits.find(item => item.camera === current) || kits[0];
  if (current !== source.camera) {{
    setupForm.elements.camera.value = source.camera;
    clearWizardImage();
  }}
  const index = String(sourceSuggestions.indexOf(source));
  if ([...discoveredSource.options].some(option => option.value === index)) discoveredSource.value = index;
  kitStatus.dataset.state = 'found';
  kitPending.hidden = true;
  loadKitExtras(source.camera);
  kitStatus.textContent = lang === 'en' ?
    'Meter camera found: ' + source.label + '. The app takes over flash and exposure automatically.' :
    'Zählerkamera gefunden: ' + source.label + '. Blitz und Belichtung übernimmt die App automatisch.';
  stopKitWatch();
  return true;
}}
// 0.5.25: a camera Home Assistant has discovered but not added yet is added from here.
const kitPending = document.querySelector('#wizard-kit-pending');
const kitPendingText = document.querySelector('#wizard-kit-pending-text');
const kitAdd = document.querySelector('#wizard-kit-add');
let kitFlow = '';
async function checkPendingKit() {{
  if (kitStatus.dataset.state === 'found') {{ kitPending.hidden = true; return; }}
  try {{
    const response = await fetch('neue-zaehlerkameras', {{cache: 'no-store'}});
    if (!response.ok) return;
    const cameras = await response.json();
    if (!Array.isArray(cameras) || !cameras.length) {{ kitPending.hidden = true; kitFlow = ''; return; }}
    kitFlow = cameras[0].flow_id;
    kitPendingText.textContent = lang === 'en' ?
      'Home Assistant has found the meter camera “' + cameras[0].name + '”.' :
      'Home Assistant hat die Zählerkamera „' + cameras[0].name + '“ gefunden.';
    kitPending.hidden = false;
  }} catch (_) {{
    // Home Assistant not reachable right now: the next round tries again.
  }}
}}
kitAdd.addEventListener('click', async () => {{
  if (!kitFlow) return;
  kitAdd.disabled = true;
  const body = new URLSearchParams({{flow_id: kitFlow, csrf: setupForm.elements.csrf.value,
                                    lang: setupForm.elements.lang.value, mode: setupForm.elements.mode.value}});
  let result = 'failed';
  try {{
    const response = await fetch('zaehlerkamera-hinzufuegen', {{method: 'POST', body}});
    if (response.ok) result = (await response.json()).result;
  }} catch (_) {{
    result = 'failed';
  }}
  kitAdd.disabled = false;
  if (result === 'added' || result === 'gone') {{
    kitPending.hidden = true;
    kitFlow = '';
    kitStatus.textContent = lang === 'en' ? 'Added. The camera shows up here in a few seconds …' :
      'Hinzugefügt. Die Kamera erscheint hier in wenigen Sekunden …';
    setTimeout(async () => {{ await loadSourceSuggestions(true, false); kitCameraFound(); }}, 4000);
  }} else {{
    kitPendingText.textContent = lang === 'en' ?
      'Home Assistant still needs an answer for this camera: open Devices & services and press “Add” there.' :
      'Home Assistant braucht für diese Kamera noch eine Angabe: Öffne Geräte & Dienste und drücke dort „Hinzufügen“.';
  }}
}});
// 0.5.26: optional extras of the meter camera (disabled entities), switched without flashing.
const kitExtras = document.querySelector('#wizard-kit-extras');
const kitExtrasStatus = document.querySelector('#wizard-kit-extras-status');
let kitExtrasCamera = '';
async function loadKitExtras(camera) {{
  kitExtrasCamera = camera;
  try {{
    const response = await fetch('zaehlerkamera-zusaetze?camera=' + encodeURIComponent(camera), {{cache: 'no-store'}});
    const extras = response.ok ? await response.json() : {{}};
    let shown = 0;
    kitExtras.querySelectorAll('[data-extra-row]').forEach(row => {{
      const extra = extras[row.dataset.extraRow];
      row.hidden = !extra;
      if (extra) {{ row.querySelector('input').checked = extra.enabled === true; shown += 1; }}
    }});
    kitExtras.hidden = shown === 0;
  }} catch (_) {{
    kitExtras.hidden = true;
  }}
}}
kitExtras.addEventListener('change', async event => {{
  const box = event.target.closest('input[data-extra]');
  if (!box || !kitExtrasCamera) return;
  box.disabled = true;
  const body = new URLSearchParams({{camera: kitExtrasCamera, extra: box.dataset.extra, on: box.checked ? '1' : '0',
                                    csrf: setupForm.elements.csrf.value, lang: setupForm.elements.lang.value,
                                    mode: setupForm.elements.mode.value}});
  let result = 'failed';
  try {{
    const response = await fetch('zaehlerkamera-zusatz', {{method: 'POST', body}});
    if (response.ok) result = (await response.json()).result;
  }} catch (_) {{
    result = 'failed';
  }}
  box.disabled = false;
  if (result === 'saved') {{
    kitExtrasStatus.textContent = lang === 'en' ? 'Saved. Home Assistant applies it in about 30 seconds.' :
      'Gespeichert. Home Assistant übernimmt es in etwa 30 Sekunden.';
  }} else {{
    box.checked = !box.checked;
    kitExtrasStatus.textContent = lang === 'en' ? 'Could not be changed. Try again or switch it at the device in Home Assistant.' :
      'Ließ sich nicht ändern. Versuche es noch einmal oder schalte es beim Gerät in Home Assistant.';
  }}
}});
function startKitWatch() {{
  if (kitTimer || kitCameraFound()) return;
  checkPendingKit();
  kitPolls = 0;
  // Look every 10 seconds whether Home Assistant knows the new camera yet (at most half an hour).
  kitTimer = setInterval(async () => {{
    kitPolls += 1;
    if (kitPanel.hidden || !setupDialog.open || kitPolls > 180) {{ stopKitWatch(); return; }}
    await loadSourceSuggestions(true, false);
    if (!kitCameraFound()) checkPendingKit();
  }}, 10000);
}}
function stopKitWatch() {{
  if (kitTimer) clearInterval(kitTimer);
  kitTimer = null;
}}
sourceCards.hidden = false;
document.querySelector('.source-mode-guide').classList.add('source-cards-ready');
sourceCards.addEventListener('click', event => {{
  const card = event.target.closest('.source-card');
  if (!card) return;
  kitOpen = card.dataset.kit === '1';
  sourceCards.classList.remove('needs-choice');
  sourceCardsHint.hidden = true;
  if (wizardSourceMode.value !== card.dataset.mode) {{
    wizardSourceMode.value = card.dataset.mode;
    clearWizardImage();
  }}
  showWizardSource();
}});
document.querySelectorAll('input[name="kit_board"]').forEach(input => input.addEventListener('change', () => {{
  const url = new URL(kitInstall.href);
  url.searchParams.set('board', input.value);
  kitInstall.href = url.toString();
}}));
wizardSourceMode.addEventListener('change', showWizardSource); showWizardSource();
const discoveredSource = document.querySelector('#wizard-discovered-source');
const cameraSearch = document.querySelector('#wizard-camera-search');
let sourceSuggestions = [];
let loadingSourceSuggestions = false;
let sourceRetryTimer = null;
const refreshSources = document.querySelector('#wizard-refresh-sources');
const discoveryStatus = document.querySelector('#wizard-discovery-status');
function showDiscoveryStatus(text) {{
  discoveryStatus.textContent = text;
  discoveryStatus.hidden = !text;
}}
async function loadSourceSuggestions(force = false, retry = true) {{
  if (loadingSourceSuggestions || (sourceSuggestions.length && !force)) return;
  loadingSourceSuggestions = true;
  refreshSources.disabled = true;
  if (sourceRetryTimer) {{ clearTimeout(sourceRetryTimer); sourceRetryTimer = null; }}
  showDiscoveryStatus(lang === 'en' ? 'Searching Home Assistant …' : 'Suche in Home Assistant …');
  let failed = false;
  try {{
    const response = await fetch('bildquellen', {{cache: 'no-store'}});
    if (!response.ok) throw Error('Device discovery failed');
    const suggestions = await response.json();
    if (!Array.isArray(suggestions)) throw Error('Invalid device list');
    sourceSuggestions = suggestions;
  }} catch (_) {{
    // Keep the selector visible and disabled when Home Assistant is not ready.
    failed = true;
  }} finally {{
    loadingSourceSuggestions = false;
    refreshSources.disabled = false;
  }}
  filterWizardSources();
  if (failed) {{
    showDiscoveryStatus(lang === 'en' ? 'Home Assistant is not reachable right now. The app tries again shortly; you can also tap ↻.' : 'Home Assistant ist gerade nicht erreichbar. Die App versucht es gleich noch einmal; du kannst auch ↻ antippen.');
  }} else {{
    showDiscoveryStatus('');
  }}
  // Home Assistant often answers empty or with 502 right after a restart: try once more by itself.
  if ((failed || !sourceSuggestions.length) && retry) {{
    sourceRetryTimer = setTimeout(() => loadSourceSuggestions(true, false), 5000);
  }}
}}
refreshSources.addEventListener('click', () => loadSourceSuggestions(true, true));
function filterWizardSources() {{
  const selected = discoveredSource.value;
  const term = cameraSearch.value.trim().toLowerCase();
  discoveredSource.options.length = 1;
  sourceSuggestions.forEach((source, index) => {{
    if (![source.label, source.camera, source.url].join(' ').toLowerCase().includes(term)) return;
    const type = source.mode === 'slfork' ? 'AI on the Edge' :
      source.kit ? (lang === 'en' ? 'Meter camera' : 'Zählerkamera') : (lang === 'en' ? 'Camera' : 'Kamera');
    const offline = source.available === false ? (lang === 'en' ? ' (not available in Home Assistant)' : ' (in Home Assistant nicht verfügbar)') : '';
    discoveredSource.add(new Option(type + ' · ' + source.label + offline, String(index)));
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
// Precision mode needs a second, explicit confirmation.
document.querySelectorAll('input[name="precision_mode"]').forEach(box => {{
  box.addEventListener('change', () => {{
    if (!box.checked) return;
    const question = lang === 'en'
      ? 'Really switch on precision mode? The fast-moving last roller is often not read reliably. '
        + 'If the image quality is too poor or the last digit cannot be read despite several attempts, '
        + 'the app gives up after six hours and checks with two decimal places.'
      : 'Präzisionsmodus wirklich einschalten? Die schnell laufende letzte Rolle wird oft nicht sicher erkannt. '
        + 'Ist die Bildqualität zu schlecht oder lässt sich die letzte Ziffer trotz mehrerer Versuche nicht lesen, '
        + 'gibt die App nach sechs Stunden auf und prüft mit zwei Nachkommastellen.';
    if (!window.confirm(question)) box.checked = false;
  }});
}});
// The setup wizard and the settings show the same experiment switches; keep both in step.
for (const name of ['experiments_enabled', 'experiment_perspective', 'experiment_seven_segment']) {{
  const boxes = [...document.querySelectorAll('.experiments-box [name="' + name + '"]:not([type="hidden"])')];
  for (const box of boxes) box.addEventListener('change', () => {{
    for (const other of boxes) {{
      if (box.type === 'checkbox') other.checked = box.checked;
      else other.value = box.value;
    }}
  }});
}}
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
const testButtons = [document.querySelector('#start-check-with-options'), document.querySelector('#start-check-top')];
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
      ['#source-camera', mode === 'esphome' || mode === 'camera'], ['#source-reference', mode === 'camera'],
      ['#source-light', mode === 'esphome' || mode === 'camera'], ['#source-camera-light', mode === 'esphome' || mode === 'camera']]) {{
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
      regionStartButton.focus();
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
    soft_image: 'Der Ausschnitt ist deutlich weniger scharf oder kontrastreich als zuvor. Die App wartet auf ein besseres Bild.',
    collecting: 'Grobprüfung läuft: Die App testet mehrere feste Rahmen und Winkel. Die besten Kandidaten werden gespeichert, danach folgt die Feinjustierung.',
    disagree: 'Die OCR-Versuche lieferten unterschiedliche Ziffern.',
    reference_unavailable: 'Kein gültiger Vergleichswert zu diesem Bild.',
    reference_mismatch: 'Der gelesene Stand weicht vom Vergleichswert ab.',
    position_error: 'Die gelesene Ziffernreihe ist gegenüber dem Vergleichswert vermutlich um eine Stelle verschoben.',
    implausible: 'Der Stand passt zeitlich nicht zur letzten sicheren Ablesung.',
    await_movement: 'Der Rahmen ist lesbar. Die App wartet auf einen plausiblen Zähleranstieg.',
    accepted: 'Dieser Rahmen wurde auf dem aktuellen Bild bestätigt.',
    roll_transition: 'Die letzte Rolle dreht sich noch. Die App wartet auf eine eindeutige Ziffer.',
    optional_last_slot: 'Letzte Rolle auf diesem Bild gelesen. Sie ist noch nicht unabhängig bestätigt.',
    reflected_geometry: 'Die sichtbaren Ziffern stützen den markierten Rahmen. Die verdeckten Stellen bleiben offen.',
    accepted_geometry: 'Ziffern bis zur zweiten Nachkommastelle gelesen. Der Rahmen gilt vorläufig, weil noch kein Vergleichswert vorliegt.',
    accepted_partial: 'Bis zur zweiten Nachkommastelle bestätigt. Die dritte Nachkommastelle ist noch offen.',
    verified: 'Die abschließende Gegenprobe war erfolgreich.',
  }};
  for (const section of document.querySelectorAll('.calibration-photo-panel')) {{
    section.hidden = !preview?.frame;
    if (section.hidden) continue;
    const frame = section.querySelector('[data-image="frame"]');
    const crop = section.querySelector('[data-image="crop"]');
    const region = section.querySelector('.calibration-crop-region');
    const hasCrop = Boolean(preview.crop);
    // 0.5.29: a frame that is only being tested is drawn dashed and called so; before, every
    // tested frame looked like the found counter, also one lying across it in the wrong direction.
    const settled = ['accepted', 'accepted_partial', 'accepted_geometry', 'verified', 'reflected_geometry',
      'await_movement'].includes(preview.reason);
    region.dataset.state = settled ? 'found' : 'testing';
    section.querySelector('.calibration-frame-caption').textContent = (preview.best_fine_score ?
      'Bester Treffer der Feinprüfung · ' + preview.best_fine_score + ' %' : 'Aktuelles Kamerabild') +
      (hasCrop ? (settled ? ' · Rahmen passt' : ' · Rahmen wird geprüft') : '');
    section.querySelector('.calibration-crop-figure').hidden = !hasCrop;
    for (const [kind, img] of [['frame', frame], ['crop', crop]]) {{
      const revision = preview[kind];
      if (!revision) continue;
      const url = 'lernvorschau.jpg?bild=' + kind + '&v=' + encodeURIComponent(revision);
      if (img.getAttribute('src') !== url) {{
        img.hidden = true;
        delete img.dataset.shown;
        img.onload = () => {{
          img.hidden = false;
          img.dataset.shown = String(revision);
          // The frame belongs to exactly this picture: show it only together with it.
          if (kind === 'frame') region.hidden = region.dataset.frame !== String(revision);
        }};
        img.onerror = () => {{ img.hidden = true; delete img.dataset.shown; img.removeAttribute('src'); }};
        img.src = url;
      }}
    }}
    const regionReady = hasCrop && Array.isArray(preview.region);
    region.dataset.frame = regionReady ? String(preview.frame) : '';
    // 0.5.28: position the frame before it can appear. The picture's onload shows it, and
    // before, a frame not yet positioned briefly sat as a dot below the picture.
    if (regionReady) {{
      ['left', 'top', 'width', 'height'].forEach((part, index) => {{
        region.style[part] = preview.region[index] * 100 + '%';
      }});
    }}
    region.hidden = !regionReady || frame.dataset.shown !== String(preview.frame);
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
let frameRelocating = false;
let frameRelocatedAt = null;
let comparedDecimals = null;
let configuredDecimals = null;
let lastDigitSearchAt = null;
let partialEighthDigit = false;
let lastDigitGivenUp = false;
let previousCalibrationState = '';
let routineOk = {automatic_routine_ok};
let calibrationNoticeUntil = 0;
function updateCalibrationNotice() {{
  const notice = document.querySelector('#calibration-complete-notice');
  notice.hidden = routineOk || !document.querySelector('#setup-success').hidden ||
    Date.now() >= calibrationNoticeUntil;
}}
let setupReached = 0;
let setupReachedTested = -1;
// One progress state for the step plan, the timeline and the candidate list (0.3.0).
function setupProgressModel(status) {{
  const en = lang === 'en';
  const active = status.state === 'waiting' || status.state === 'testing';
  const saved = String(status.state || '').startsWith('saved');
  const stage = status.stage;
  const confirmations = Number(status.confirmations || status.reflected_confirmations || 0);
  const required = Number(status.required || 3);
  const candidates = status.candidates || [];
  const best = candidates.reduce((top, item) => Math.max(top, Number(item.percent) || 0), 0);
  // 0.5.29: "find the counter" is ticked only once a frame has really read it (a confirmation,
  // a partial hit or an accepted picture). Before, any tested frame ticked it, also a frame lying
  // across the meter in the wrong direction.
  const counterFound = confirmations > 0 || Number(status.partial_hits || 0) > 0 ||
    (status.rounds || []).some(round => String(round?.reason || '').startsWith('accepted')) ||
    ['verify', 'verify_wait'].includes(stage);
  let current = ['queued', 'capture'].includes(stage) && !status.tested ? 0 :
    ['verify', 'verify_wait'].includes(stage) || confirmations > 0 ? 3 : counterFound ? 2 : 1;
  const phase = current === 0 ? 0 : current === 3 ? 3 :
    ['shortlist', 'refine', 'angle', 'digit_probe', 'ocr'].includes(stage) || candidates.length || counterFound ? 2 : 1;
  if (saved) current = 5;
  // 0.5.11: the list jumped back to "find the counter" with every new
  // picture. A step reached once in this run stays ticked; the cycle of the single picture
  // is shown below the running step instead.
  const rawCurrent = current;
  const testedNow = Number(status.tested || 0);
  if ((!active && !saved) || testedNow < setupReachedTested) setupReached = 0;
  setupReachedTested = testedNow;
  if (active) {{
    setupReached = Math.max(setupReached, current);
    current = setupReached;
  }}
  const elapsed = Math.max(0, Number(status.duration || 0) - Number(status.seconds || 0));
  const clock = Math.floor(elapsed / 60) + ':' + String(elapsed % 60).padStart(2, '0');
  const selected = candidates.find(item => item.selected);
  const detail = [];
  if (current === 0) detail.push(en ? 'Waiting for a camera image' : 'Wartet auf ein Kamerabild');
  if (current === 1) {{
    const testingFrames = ['shortlist', 'refine', 'angle', 'digit_probe', 'ocr'].includes(stage) || candidates.length > 0;
    detail.push(status.row_found ? (en ? 'Digit row found: ' : 'Ziffernreihe erkannt: ') + status.row_found + ' %' :
      testingFrames ? (en ? 'Testing frames and rotations' : 'Prüft Rahmen und Drehungen') :
      (en ? 'Searching the image for the counter window' : 'Sucht im Bild das Zählwerkfenster'));
    if (status.attempts) detail.push(status.attempts + (en ? ' frames tested' : ' Rahmen getestet'));
    if (status.rotation != null) detail.push((en ? 'rotation ' : 'Drehung ') + String(status.rotation).replace('-', '−') + '°');
  }}
  if (current >= 2 && current <= 3) {{
    if (candidates.length) {{
      const number = selected ? selected.number : Number(status.variant) || 1;
      detail.push((en ? 'Frame ' : 'Rahmen ') + Math.min(number, candidates.length) + (en ? ' of ' : ' von ') + candidates.length);
    }}
    if (status.rotation != null) detail.push((en ? 'Rotation ' : 'Drehung ') + String(status.rotation).replace('-', '−') + '°');
    detail.push(confirmations + (en ? ' of ' : ' von ') + required + (en ? ' confirmations' : ' Bestätigungen'));
    // A reading that fits but leaves the last digit open is shown, not hidden behind "0 of 3".
    if (status.partial_hits) detail.push(status.partial_hits + (en ? ' partial hit(s), last digit unclear' : (status.partial_hits === 1 ? ' Teiltreffer' : ' Teiltreffer') + ' (letzte Stelle unklar)'));
  }}
  const steps = [
    {{key: 'image', label: en ? 'Get camera image' : 'Kamerabild holen',
     result: status.tested ? status.tested + (en ? (status.tested === 1 ? ' image' : ' images') : (status.tested === 1 ? ' Bild' : ' Bilder')) : ''}},
    {{key: 'find', label: en ? 'Find the counter' : 'Zählwerk finden',
     result: en ? 'Counter found' : 'Zählwerk gefunden'}},
    {{key: 'check', label: en ? 'Check frame and rotation' : 'Rahmen und Drehung prüfen',
     result: best ? (en ? 'best match ' : 'beste Übereinstimmung ') + best + ' %' : ''}},
    {{key: 'confirm', label: (en ? 'Confirm frame' : 'Rahmen bestätigen') + ' (' + Math.min(confirmations, required) + '/' + required + ')',
     result: confirmations >= required || saved ? (en ? 'confirmed' : 'bestätigt') : ''}},
    {{key: 'save', label: en ? 'Save setup' : 'Einrichtung speichern', result: saved ? (en ? 'saved' : 'gespeichert') : ''}},
  ];
  if (status.simplified) steps.push({{key: 'background', optional: true,
    label: en ? 'In the background: refine the last digit (optional)' : 'Im Hintergrund: letzte Stelle verfeinern (optional)', result: ''}});
  // Sub-steps: the running step unfolds its small intermediate steps,
  // finished steps can be opened again.
  const tested = Number(status.tested || 0);
  const sub = (label, done, running, extra) => ({{label, state: done ? 'done' : running ? 'current' : 'todo', extra: extra || ''}});
  const hintNames = {{dark: en ? 'dark' : 'dunkel', bright: en ? 'very bright' : 'sehr hell', low_contrast: en ? 'low contrast' : 'wenig Kontrast'}};
  const hints = (status.image_hints || []).map(hint => hintNames[hint] || hint).join(', ');
  const plural = count => count === 1 ? (en ? ' image' : ' Bild') : (en ? ' images' : ' Bilder');
  const substeps = {{
    image: [
      sub(en ? 'Request picture' : 'Bild anfordern', tested > 0 || stage !== 'capture', stage === 'capture'),
      sub(en ? 'Check light and brightness' : 'Licht und Helligkeit prüfen', tested > 0, false,
        tested ? (hints ? (en ? 'Note: ' : 'Hinweis: ') + hints : (en ? 'fine' : 'in Ordnung')) : ''),
      sub(en ? 'Picture received' : 'Bild empfangen', tested > 0, false, tested ? tested + plural(tested) : ''),
    ],
    find: [
      sub(en ? 'Search the counter window' : 'Zählwerkfenster suchen', current > 1 || !!status.row_found, current === 1,
        status.row_found ? (en ? 'digit row ' : 'Ziffernreihe ') + status.row_found + ' %' : ''),
      sub(en ? 'Collect frame candidates' : 'Rahmen-Kandidaten sammeln', current > 1 || candidates.length > 0,
        current === 1 && !!status.row_found && !candidates.length,
        candidates.length ? candidates.length + (en ? ' found' : ' gefunden') : ''),
      sub(en ? 'Read the counter plausibly' : 'Zählwerk plausibel gelesen', current > 1, current === 1 && candidates.length > 0,
        current > 1 && selected?.reading ? selected.reading : ''),
    ],
    check: [
      sub((en ? 'Test frames' : 'Rahmen testen') + (candidates.length ? ' (' + Math.min(selected ? selected.number : Number(status.variant) || 1, candidates.length) + (en ? ' of ' : ' von ') + candidates.length + ')' : ''),
        current > 2, current === 2 && ['ocr', 'shortlist'].includes(stage), (status.attempts || 0) + (en ? ' tested' : ' getestet')),
      sub(en ? 'Check rotation' : 'Drehung prüfen', current > 2, current === 2 && stage === 'angle',
        status.rotation != null ? String(status.rotation).replace('-', '−') + '°' : ''),
      sub(en ? 'Fine-tune frames' : 'Rahmen fein nachjustieren', current > 2, current === 2 && ['refine', 'digit_probe'].includes(stage)),
      sub(en ? 'Read digits' : 'Ziffern lesen', current > 2 || !!selected?.reading, false,
        selected?.reading ? (en ? 'candidate ' : 'Kandidat ') + selected.reading : ''),
    ],
    confirm: [
      ...Array.from({{length: required}}, (_, index) => sub((en ? 'Confirmation ' : 'Bestätigung ') + (index + 1) + (en ? ' of ' : ' von ') + required,
        confirmations > index || saved, current === 3 && confirmations === index && stage !== 'verify_wait')),
      ...(stage === 'verify_wait' ? [sub(en ? 'Waiting for a new picture' : 'Wartet auf ein neues Bild', false, true)] : []),
      ...(status.partial_hits ? [sub(en ? 'Partial hits (last digit unclear)' : 'Teiltreffer (letzte Stelle unklar)', true, false, String(status.partial_hits))] : []),
    ],
    save: [
      sub(en ? 'Take over the starting value' : 'Startwert übernehmen', saved, !!status.awaiting_start_value),
      sub(en ? 'Save setup' : 'Einrichtung speichern', saved, false),
    ],
  }};
  if (status.state === 'image_timeout' || status.state === 'timeout') {{
    const key = ['image', 'find', 'check', 'confirm', 'save'][Math.min(current, 4)];
    substeps[key].push({{label: status.state === 'image_timeout' ? (en ? 'No new camera image, repeating' : 'Kein neues Kamerabild – wird wiederholt')
      : (en ? 'Time limit reached' : 'Zeitlimit erreicht'), state: 'warn', extra: ''}});
  }}
  // The cycle every single picture runs through, shown below the running step.
  const cycleIndex = ['queued', 'capture'].includes(stage) ? 0 : ['shortlist', 'ocr'].includes(stage) ? 2 :
    stage === 'angle' ? 3 : ['refine', 'digit_probe'].includes(stage) ? 4 :
    ['verify', 'verify_wait', 'waiting'].includes(stage) ? 5 : 1;
  const cycleLabels = en ?
    ['Request picture', 'Search the counter in the picture', 'Test frames', 'Check rotation', 'Fine-tune the frame', 'Rate the result'] :
    ['Bild anfordern', 'Zählwerk im Bild suchen', 'Rahmen testen', 'Drehung prüfen', 'Rahmen fein nachjustieren', 'Ergebnis bewerten'];
  const cycleExtra = [
    '', status.row_found ? (en ? 'digit row ' : 'Ziffernreihe ') + status.row_found + ' %' : '',
    (status.attempts || 0) + (en ? ' tested in total' : ' insgesamt getestet'),
    status.rotation != null ? String(status.rotation).replace('-', '−') + '°' : '', '',
    cycleIndex === 5 ? (en ? 'waiting for the next picture' : 'wartet auf das nächste Bild') : ''];
  const cycle = cycleLabels.map((label, index) => sub(label, index < cycleIndex, index === cycleIndex,
    index <= cycleIndex ? cycleExtra[index] : ''));
  const pictureNumber = tested + (cycleIndex === 0 ? 1 : 0);
  steps.forEach((step, index) => {{
    step.state = step.optional ? 'optional' : index < current ? 'done' : index === current ? 'current' : 'todo';
    step.detail = step.state === 'current' ? detail.join(' · ') : '';
    const running = step.state === 'current' && active;
    step.substeps = running ? cycle : step.state === 'done' || step.state === 'current' ? (substeps[step.key] || []) : [];
    step.substepsTitle = running ? (en ? 'Current picture (no. ' : 'Aktuelles Bild (Nr. ') + Math.max(1, pictureNumber) + ')' : '';
    if (step.state !== 'done') step.result = '';
  }});
  const roundText = {{
    accepted: [en ? 'Frame confirmed' : 'Rahmen bestätigt', 'ok'],
    accepted_partial: [en ? 'Frame confirmed (last digit open)' : 'Rahmen bestätigt (letzte Stelle offen)', 'ok'],
    verified: [en ? 'Cross-check passed' : 'Gegenprobe bestanden', 'ok'],
    accepted_geometry: [en ? 'Frame fits' : 'Rahmen passt', 'ok'],
    reflected_geometry: [en ? 'Frame fits, one digit hidden (reflection)' : 'Rahmen passt, eine Stelle verdeckt (Spiegelung)', 'ok'],
    await_clear_roller: [en ? 'A roller was turning – not counted' : 'Rolle drehte sich gerade – zählt nicht', 'wait'],
    await_movement: [en ? 'Waiting for the meter to move' : 'Wartet auf Zählerbewegung', 'wait'],
    unclear: [en ? 'Not read clearly' : 'Nicht eindeutig gelesen', 'fail'],
    no_region: [en ? 'Counter not found' : 'Zählwerk nicht gefunden', 'fail'],
    implausible: [en ? 'Does not fit the last reading' : 'Passt nicht zum letzten Stand', 'fail'],
  }};
  const rounds = (Array.isArray(status.rounds) ? status.rounds : []).map(round => {{
    const [text, result] = roundText[round.reason] || [en ? 'No result' : 'Kein Ergebnis', 'fail'];
    const count = Number(round.confirmations || 0);
    return {{number: round.image, result,
      text: text + (result === 'ok' && count ? ' (' + Math.min(count, required) + '/' + required + ')' : ''),
      reading: round.reading && round.reading !== '?' ? String(round.reading).replace('.', en ? '.' : ',') : '',
      seconds: Math.round(Number(round.seconds) || 0)}};
  }}).reverse();
  const stats = (en ? 'Images: ' : 'Bilder: ') + (status.tested || 0) +
    (en ? ' · Frames tested: ' : ' · Rahmen getestet: ') + (status.attempts || 0) +
    (en ? ' · Time so far: ' : ' · Bisherige Dauer: ') + clock + ' min' +
    (best ? (en ? ' · Best match: ' : ' · Beste Übereinstimmung: ') + best + ' %' : '') +
    ((status.marked_positions || []).length ? (en ? ' · Marked as hidden (reflection): digit ' : ' · Als verdeckt markiert (Spiegelung): Stelle ') +
      status.marked_positions.join(en ? ' and ' : ' und ') : '');
  return {{active, current: Math.min(rawCurrent, 3), phase, steps, stats, candidates, rounds}};
}}
const setupSubstepsOpen = new Map();
function renderSetupTimeline(box, model) {{
  const list = box.querySelector('.setup-timeline');
  const key = JSON.stringify(model.steps);
  if (list.dataset.model !== key) {{
    const previous = JSON.parse(list.dataset.model || '[]');
    list.replaceChildren(...model.steps.map((step, index) => {{
      const row = document.createElement('li');
      row.dataset.state = step.state;
      row.dataset.step = step.key;
      if (step.state === 'current') row.setAttribute('aria-current', 'step');
      const dot = document.createElement('span');
      dot.className = 'setup-dot';
      dot.setAttribute('aria-hidden', 'true');
      dot.textContent = step.state === 'done' ? '✓' : '';
      // Animate only a step that was just completed, not every refresh.
      if (step.state === 'done' && previous[index]?.state === 'done') dot.style.animation = 'none';
      const head = document.createElement('div');
      head.className = 'setup-step-head';
      const label = document.createElement('span');
      label.className = 'setup-step-label';
      label.textContent = step.label;
      head.append(label);
      if (step.result) {{
        const result = document.createElement('span');
        result.className = 'setup-step-result';
        result.textContent = step.result;
        head.append(result);
      }}
      row.append(dot, head);
      if (step.detail) {{
        const detail = document.createElement('div');
        detail.className = 'setup-step-detail';
        detail.textContent = step.detail;
        row.append(detail);
      }}
      if (step.substeps?.length) {{
        const fold = document.createElement('details');
        fold.className = 'setup-substeps';
        const remembered = setupSubstepsOpen.get(step.key);
        fold.open = remembered ?? step.state === 'current';
        const summary = document.createElement('summary');
        summary.textContent = step.substepsTitle || (lang === 'en' ? 'Intermediate steps' : 'Zwischenschritte');
        const items = document.createElement('ul');
        items.append(...step.substeps.map(part => {{
          const item = document.createElement('li');
          item.dataset.sub = part.state;
          item.textContent = (part.state === 'done' ? '✓ ' : part.state === 'current' ? '▸ ' : part.state === 'warn' ? '! ' : '○ ') +
            part.label + (part.extra ? ' – ' + part.extra : '');
          return item;
        }}));
        fold.append(summary, items);
        fold.addEventListener('toggle', () => {{
          // A user's choice wins; a step that just became current opens by itself.
          if (fold.open !== (step.state === 'current')) setupSubstepsOpen.set(step.key, fold.open);
          else setupSubstepsOpen.delete(step.key);
        }});
        row.append(fold);
      }}
      return row;
    }}));
    list.dataset.model = key;
  }}
  const stats = box.querySelector('.setup-timeline-stats');
  if (stats.textContent !== model.stats) stats.textContent = model.stats;
  const roundsBox = (box.closest('.calibration-live') || box).querySelector('.setup-rounds-box');
  if (roundsBox) {{
    const en = lang === 'en';
    roundsBox.hidden = !model.rounds.length;
    const roundList = roundsBox.querySelector('.setup-rounds');
    const roundKey = JSON.stringify(model.rounds);
    if (roundList.dataset.values !== roundKey) {{
      roundList.replaceChildren(...model.rounds.map(round => {{
        const row = document.createElement('li');
        row.dataset.result = round.result;
        const mark = document.createElement('span');
        mark.className = 'setup-round-mark';
        mark.setAttribute('aria-hidden', 'true');
        mark.textContent = round.result === 'ok' ? '✓' : round.result === 'fail' ? '✗' : '○';
        const body = document.createElement('span');
        body.textContent = (en ? 'Picture ' : 'Bild ') + round.number + ': ' + round.text;
        const more = document.createElement('small');
        more.textContent = [round.reading ? (en ? 'read ' : 'gelesen ') + round.reading : '',
          round.seconds ? round.seconds + ' s' : ''].filter(Boolean).join(' · ');
        if (more.textContent) body.append(more);
        row.append(mark, body);
        return row;
      }}));
      roundList.dataset.values = roundKey;
    }}
  }}
}}
function renderGlareConfirm(status, active, background) {{
  const prompt = active && !background && status && status.glare_prompt;
  for (const box of document.querySelectorAll('.glare-confirm')) {{
    box.hidden = !prompt;
    if (!prompt) continue;
    const en = lang === 'en';
    box.querySelector('[name="glare_id"]').value = prompt.id;
    const visible = String(prompt.visible || '');
    const text = (en ? 'Digit ' : 'Stelle ') + prompt.positions.join(en ? ' and ' : ' und ') +
      (en ? ' looks hidden by a reflection' : ' sieht durch eine Spiegelung verdeckt aus') +
      (visible ? (en ? ' (read so far: ' : ' (bisher gelesen: ') + visible + ')' : '') + '.';
    const out = box.querySelector('.glare-confirm-text');
    if (out.textContent !== text) out.textContent = text;
  }}
  // 0.5.19: the frame did not fit the entered reading – say so while the setup keeps looking.
  const mismatch = active && !background && !prompt && status && status.glare_mismatch === true;
  for (const box of document.querySelectorAll('.glare-confirm')) {{
    let note = box.nextElementSibling;
    if (!note || !note.classList.contains('glare-mismatch')) {{
      if (!mismatch) continue;
      note = document.createElement('p');
      note.className = 'glare-mismatch';
      box.after(note);
    }}
    note.hidden = !mismatch;
    const text = lang === 'en' ?
      'The digits read in this frame do not fit the meter reading you entered. The setup keeps looking for a better frame and will ask again.' :
      'Die gelesenen Ziffern passen nicht zum eingetragenen Zählerstand. Die Einrichtung sucht weiter nach einem besseren Rahmen und fragt dann noch einmal.';
    if (note.textContent !== text) note.textContent = text;
  }}
}}
function renderSetupCandidates(list, candidates) {{
  const en = lang === 'en';
  const key = JSON.stringify(candidates);
  if (list.dataset.values === key) return;
  list.replaceChildren(...candidates.map(candidate => {{
    const row = document.createElement('li');
    row.dataset.selected = String(candidate.selected === true);
    const parts = [];
    if (candidate.number) parts.push((en ? 'Frame ' : 'Rahmen ') + candidate.number);
    if (candidate.rotation != null) parts.push(String(candidate.rotation).replace('-', '−') + '°');
    // 0.5.11: two percentages – glyph found in the digit fields / agreement of the readings.
    if (candidate.found != null) parts.push((en ? 'fields with a digit ' : 'Felder mit Ziffer ') + candidate.found + ' %');
    if (candidate.percent != null) parts.push((candidate.found != null ? (en ? 'reading agreement ' : 'Lese-Übereinstimmung ') : '') + candidate.percent + ' %');
    parts.push(candidate.reading || '–');
    // 0.4.0 status fields; older status data has none of them.
    const hits = Number(candidate.hits);
    if (candidate.hits != null && Number.isFinite(hits)) {{
      parts.push(hits + (en ? (hits === 1 ? ' hit' : ' hits') : ' Treffer'));
    }}
    const merged = Number(candidate.merged);
    if (Number.isFinite(merged) && merged > 0) {{
      parts.push(merged + (en ? (merged === 1 ? ' similar frame merged' : ' similar frames merged') :
        (merged === 1 ? ' ähnlicher Rahmen zusammengefasst' : ' ähnliche Rahmen zusammengefasst')));
    }}
    if (Array.isArray(candidate.reflected) && candidate.reflected.length) {{
      parts.push((en ? 'digit ' : 'Stelle ') + candidate.reflected.join(en ? ' and ' : ' und ') +
        (en ? ' hidden (reflection)' : ' verdeckt (Spiegelung)'));
    }}
    if (candidate.selected) parts.push(en ? 'being checked' : 'wird geprüft');
    row.textContent = parts.join(' · ');
    if (candidate.role === 'hint') {{
      row.dataset.role = 'hint';
      const badge = document.createElement('span');
      badge.className = 'candidate-hint';
      badge.textContent = en ? 'search aid only' : 'nur Suchhilfe';
      badge.title = en ? 'Below the confirmation threshold: only used to guide the search.' :
        'Unter der Bestätigungsschwelle: hilft nur bei der Suche.';
      row.append(' ', badge);
    }}
    return row;
  }}));
  list.dataset.values = key;
}}
const rejectedReasons = {{
  small_label: ['zu klein, vermutlich ein Typenschild oder eine Beschriftung', 'too small, probably a type plate or label'],
  quarter_turn: ['um 90° gedreht, passt nicht zur Zählerausrichtung', 'turned by 90°, does not match the meter orientation'],
  aspect: ['Seitenverhältnis passt nicht zu einem Zählwerk', 'aspect ratio does not fit a counter'],
  implausible: ['passt nicht zum letzten bekannten Zählerstand', 'does not fit the last known meter reading'],
  half_turn: ['um 180° verdreht gelesen, der gegenüberliegende Rahmen passt besser zum letzten Stand',
    'read turned by 180°, the opposite frame fits the last reading better'],
}};
// Collapsible "Verworfen (n)" list next to a candidate list; created once, closed by default.
function renderRejectedCandidates(list, rejected) {{
  const en = lang === 'en';
  let box = list.nextElementSibling;
  if (!box?.classList.contains('calibration-rejected')) {{
    box = document.createElement('details');
    box.className = 'calibration-rejected';
    box.append(document.createElement('summary'), document.createElement('ul'));
    list.after(box);
  }}
  const entries = Array.isArray(rejected) ? rejected : [];
  box.hidden = !entries.length;
  const key = JSON.stringify(entries);
  if (box.dataset.values === key) return entries.length;
  box.dataset.values = key;
  box.querySelector('summary').textContent = (en ? 'Rejected (' : 'Verworfen (') + entries.length + ')';
  box.querySelector('ul').replaceChildren(...entries.map(entry => {{
    const row = document.createElement('li');
    const known = rejectedReasons[entry?.reason];
    const parts = [known ? known[en ? 1 : 0] : (en ? 'other reason' : 'sonstiger Grund') +
      (entry?.reason ? ' (' + entry.reason + ')' : '')];
    if (entry?.reading) parts.push((en ? 'read ' : 'las ') + String(entry.reading).replace('.', en ? '.' : ','));
    if (entry?.rotation != null) parts.push((en ? 'rotation ' : 'Drehung ') + String(entry.rotation).replace('-', '−') + '°');
    const frame = Array.isArray(entry?.box) ? entry.box.join(', ') : entry?.box;
    if (frame) parts.push((en ? 'frame ' : 'Rahmen ') + frame);
    row.textContent = parts.join(' · ');
    return row;
  }}));
  return entries.length;
}}
// "Die letzten Leseversuche" (0.4.0): the attempts of the last finished check stay visible
// and open until the next check starts; closing it is remembered like the check details.
const lastReadingsKey = 'rf1-last-readings';
function rememberDetailsState(details, key) {{
  if (details.dataset.toggleBound) return;
  details.dataset.toggleBound = '1';
  let closed = false;
  try {{ closed = localStorage.getItem(key) === '1'; }} catch (error) {{}}
  details.open = !closed;
  details.addEventListener('toggle', () => {{
    try {{ localStorage.setItem(key, details.open ? '0' : '1'); }} catch (error) {{}}
  }});
}}
function updateLastReadings(sample, running) {{
  const details = document.querySelector('#automatic-last-readings');
  const decimals = Number.isInteger(sample.decimals) ? sample.decimals : null;
  let stored = null;
  if (running) {{
    // A new check replaces the previous attempts, even before its first reading arrives.
    stored = {{readings: sample.activity_readings || [], decimals}};
    try {{ localStorage.setItem(lastReadingsKey, JSON.stringify(stored)); }} catch (error) {{}}
  }} else {{
    try {{ stored = JSON.parse(localStorage.getItem(lastReadingsKey) || 'null'); }} catch (error) {{}}
    if (sample.readings?.length) stored = {{readings: sample.readings, decimals}};
  }}
  const rows = !running && Array.isArray(stored?.readings) ? stored.readings : [];
  details.hidden = !rows.length;
  if (details.hidden) return;
  rememberDetailsState(details, 'rf1-last-readings-closed');
  renderDigitGrid(document.querySelector('#automatic-last-digit-grid'), rows,
    Number.isInteger(stored.decimals) ? stored.decimals : decimals);
}}
// Per-digit table of the attempts of a check: rows = attempts, columns = digit positions.
function renderDigitGrid(wrap, readings, decimals) {{
  const en = lang === 'en';
  const rows = (readings || []).map(value => String(value ?? ''));
  wrap.hidden = !rows.length;
  if (!rows.length) return;
  const key = JSON.stringify([rows, decimals]);
  if (wrap.dataset.values === key) return;
  wrap.dataset.values = key;
  const split = rows.map(value => {{
    const [whole, fraction = ''] = value.replace(',', '.').split('.');
    return {{whole: [...whole], fraction: [...fraction]}};
  }});
  const wholeCount = Math.max(...split.map(item => item.whole.length));
  const fractionCount = Math.max(...split.map(item => item.fraction.length));
  const compared = Number.isInteger(decimals) ? decimals : fractionCount;
  const cells = split.map(item => [
    ...Array(wholeCount - item.whole.length).fill('?'), ...item.whole,
    ...item.fraction, ...Array(fractionCount - item.fraction.length).fill('?')]);
  const total = wholeCount + fractionCount;
  const table = wrap.querySelector('table');
  const head = table.tHead;
  head.replaceChildren();
  const headRow = head.insertRow();
  const corner = document.createElement('th');
  corner.textContent = en ? 'Digit' : 'Stelle';
  headRow.append(corner);
  for (let index = 0; index < total; index++) {{
    const cell = document.createElement('th');
    cell.scope = 'col';
    cell.textContent = String(index + 1);
    if (index === wholeCount) cell.className = 'digit-sep';
    if (index >= wholeCount + compared) cell.dataset.uncompared = 'true';
    headRow.append(cell);
  }}
  const body = table.tBodies[0];
  body.replaceChildren();
  cells.forEach((values, attempt) => {{
    const row = body.insertRow();
    const label = document.createElement('th');
    label.scope = 'row';
    label.textContent = (en ? 'Attempt ' : 'Versuch ') + (attempt + 1);
    row.append(label);
    values.forEach((digit, index) => {{
      const cell = row.insertCell();
      cell.textContent = digit;
      if (index === wholeCount) cell.className = 'digit-sep';
      if (index >= wholeCount + compared) cell.dataset.uncompared = 'true';
    }});
  }});
  const result = body.insertRow();
  result.className = 'digit-result';
  const label = document.createElement('th');
  label.scope = 'row';
  label.textContent = en ? 'Result' : 'Ergebnis';
  result.append(label);
  for (let index = 0; index < total; index++) {{
    const counts = {{}};
    for (const values of cells) if (/[0-9]/.test(values[index])) counts[values[index]] = (counts[values[index]] || 0) + 1;
    const ranked = Object.entries(counts).sort((a, b) => b[1] - a[1]);
    const cell = result.insertCell();
    cell.textContent = ranked.length ? ranked[0][0] : '?';
    cell.dataset.tone = !ranked.length ? 'bad' : ranked.length === 1 ? 'ok' : 'warn';
    if (index === wholeCount) cell.className = 'digit-sep';
    if (index >= wholeCount + compared) cell.dataset.uncompared = 'true';
  }}
}}
function refreshCalibration(status) {{
  refreshCalibrationImages(status?.preview);
  for (const form of document.querySelectorAll('.calibration-skip')) {{
    form.elements.verification_id.value = status?.skip_verification_id || '';
    form.hidden = !form.elements.verification_id.value;
  }}
  // 0.5.31: a cut-out seen upside down or mirrored is corrected right in the running setup.
  const orientable = !!status && (status.state === 'waiting' || status.state === 'testing') && !status.background
    && !status.intensive && !status.automatic && !!status.preview?.crop;
  for (const form of document.querySelectorAll('.calibration-orientation')) {{
    form.hidden = !orientable;
    const flip = form.querySelector('button[value="flip"]');
    const pending = !!status?.flip_pending;
    const flipText = pending ? (lang === 'en' ? 'Turning with the next picture …' : 'Wird mit dem nächsten Bild gedreht …')
      : (lang === 'en' ? 'Upside down? Turn by 180°' : 'Steht auf dem Kopf? Um 180° drehen');
    if (flip.textContent !== flipText) flip.textContent = flipText;
    flip.setAttribute('aria-pressed', status?.turned_by_user ? 'true' : 'false');
  }}
  if (!status) return;
  const active = status.state === 'waiting' || status.state === 'testing';
  const background = status.background === true;
  lastDigitSearching = background && active;
  frameRelocating = lastDigitSearching && status.purpose === 'relocate';
  frameRelocatedAt = status.purpose === 'relocate' && String(status.state).startsWith('saved') ? status.relocated_at || null : null;
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
    waiting: 'Nächstes Kamerabild wird angefordert …',
    testing: 'Ausschnitt und Drehung werden geprüft …',
    saved: status.simplified ?
      'Einrichtung abgeschlossen: Sieben Ziffern sind bestätigt. Die dritte Nachkommastelle prüft die App zusätzlich im Hintergrund.' :
      status.intensive ? 'Dritte Nachkommastelle bestätigt. Die Ziffernrahmen sind übernommen.' :
      'Erfolgreich eingerichtet. Ausschnitt und Drehung sind übernommen.',
    saved_reflection: 'Ausschnitt mit markierter Spiegelung vorläufig gespeichert. Die verdeckten Ziffern bleiben offen.',
    saved_stationary: 'Ausschnitt vorläufig gespeichert. Die Automatik prüft die sieben lesbaren Stellen. Die dritte Nachkommastelle bleibt vorerst offen.',
    saved_without_verification: 'Rahmen ohne Gegenprobe übernommen. Spätere Ablesungen können ungenauer sein.',
    failed: 'Selbsteinrichtung fehlgeschlagen. Prüfe Bildausschnitt, Kamerawinkel und Beleuchtung.',
    image_timeout: 'Kein neues Kamerabild erhalten. Prüfe die Bildquelle.',
    timeout: status.automatic ? 'Nachjustierung nach zehn Minuten beendet. Der bisherige Rahmen bleibt gültig.' :
      'Selbsteinrichtung nach 20 Minuten beendet, ohne dass ein Rahmen sicher bestätigt wurde.',
    cancelled: 'Selbsteinrichtung gestoppt.',
    save_failed: 'Ausschnitt und Drehung konnten nicht gespeichert werden.',
  }};
  const clock = Math.floor(status.seconds / 60) + ':' + String(status.seconds % 60).padStart(2, '0');
  const stages = {{
    queued: status.followup ?
      'Ausschnitt gespeichert. Die App sucht jetzt gezielt die dritte Nachkommastelle …' :
      status.known_good_available ? 'Die App prüft zuerst den zuletzt bestätigten Rahmen.' :
      'Selbsteinrichtung wird vorbereitet …',
    capture: 'Kamerabild wird abgerufen …',
    search: 'Grobprüfung: Die App testet mehrere feste Rahmen und Winkel und schaltet danach auf die Feinjustierung um …',
    shortlist: 'Intensivprüfung für Kandidat ' + status.variant + ' …',
    digit_probe: 'Die vermutete Position der letzten Rolle wird auf diesem Bild getestet …',
    angle: 'Drehung wird geprüft. Der Winkel steht am Vorschaubild.',
    last_digit: 'Nur die letzte Rolle im gespeicherten Ausschnitt wird geprüft …',
    refine: status.preview?.weak_positions?.length ?
      'Einzelziffernsuche. Offene Stellen von links: ' + status.preview.weak_positions.join(', ') + '.' :
      'Feinkalibrierung: Rahmen und Drehung werden am vorhandenen Bild geprüft …',
    verify_wait: status.intensive ? 'Letzte Rolle gefunden. Die App wartet auf ein frisches Bild zur Gegenprobe …' :
      'Rahmen gefunden. Die App wartet auf ein frisches Bild zur Gegenprüfung …',
    verify: 'Gefundenen Rahmen mit der normalen Prüfung gegenprüfen …',
    ocr: status.preview?.crop && status.preview.angle !== status.rotation ?
      'Nächster Rahmen wird geprüft …' :
      'Rahmen ' + status.variant + ' wird mit Drehung ' + status.rotation + '° geprüft …',
  }};
  const steps = status.intensive ? ['Kamerabild laden', 'Letzte Rolle prüfen', 'Ergebnis gegenprüfen'] :
    ['Kamerabild laden', 'Ziffernreihe finden', 'Rahmen und Drehung prüfen', 'Rahmen bestätigen'];
  const stage = status.stage;
  const progressModel = setupProgressModel(status);
  // The step plan and the timeline come from the same progress state.
  const current = status.intensive ? (['queued', 'capture'].includes(stage) ? 0 :
    ['verify', 'verify_wait'].includes(stage) ? 2 : 1) : progressModel.phase;
  for (const box of document.querySelectorAll('.setup-timeline-box')) {{
    box.hidden = !active || status.automatic || status.intensive || background;
    if (!box.hidden) renderSetupTimeline(box, progressModel);
    // 0.5.28: the pictures-so-far list stands beside the timeline and follows it.
    const rounds = box.closest('.calibration-live')?.querySelector('.setup-rounds-box');
    if (box.hidden && rounds) rounds.hidden = true;
  }}
  for (const plan of document.querySelectorAll('.setup-phase')) {{
    plan.hidden = !active || status.automatic;
    plan.querySelector('.setup-current-step').textContent = steps[current];
    plan.querySelector('.setup-next-step').textContent = steps[current + 1] ||
      (status.intensive ? 'Ergebnis anzeigen' : 'Rahmen speichern und Automatik starten');
  }}
  const reason = status.preview?.reason;
  renderGlareConfirm(status, active, background);
  for (const list of document.querySelectorAll('.calibration-candidates')) {{
    renderSetupCandidates(list, status.candidates || []);
    const rejectedCount = renderRejectedCandidates(list, status.rejected);
    const parent = list.closest('.calibration-candidate-panel');
    if (parent) parent.hidden = !(list.children.length || rejectedCount) || !active || background;
  }}
  let message = active && stages[status.stage] ? stages[status.stage] : messages[status.state] || '';
  if (status.state === 'waiting' && status.stage !== 'queued') {{
    if (reason === 'roll_transition') {{
      message = 'Die letzte Rolle dreht sich noch. Die App wartet auf eine eindeutige Ziffer.' +
        (status.preview?.wheel_transition ? ' ' + status.preview.wheel_transition.join(' → ') : '');
    }} else if (reason === 'soft_image') {{
      message = 'Gegenprobe wartet auf ein besseres Bild. Der bestätigte Rahmen bleibt ausgewählt.';
    }} else if (reason === 'collecting') {{
      message = 'Grobtests: ' + status.coarse_attempts + '/' + status.coarse_limit + '.';
    }} else if (status.stage === 'verify_wait' && reason === 'accepted') {{
      message = status.coarse_complete ?
        'Drei Treffer mit 100 %: Grobprüfung beendet. Die App wartet auf ein frisches Bild für die Gegenprobe.' :
        'Treffer gesammelt. Die App wartet auf ein frisches Bild für die Gegenprobe.';
    }} else if (reason === 'reference_unavailable') {{
      message = 'Grün bedeutet lesbar. Ein gültiger Vergleichswert für dieses Bild fehlt.';
    }} else if (reason === 'reference_mismatch') {{
      message = 'Grün bedeutet lesbar. Der abgelesene Stand passt noch nicht zum Vergleichswert.';
    }} else if (reason === 'await_clear_roller') {{
      message = 'Eine der ersten sieben Ziffern dreht sich gerade. Der gefundene Rahmen bleibt erhalten; ein frisches Bild wird geprüft.';
    }} else if (reason === 'await_movement') {{
      message = 'Ziffernfeld ist lesbar.';
    }} else if (reason === 'accepted' && status.candidate_agreement === 100) {{
      message = 'Rahmen mit 100 % Übereinstimmung gefunden. Die Intensivprüfung bleibt bei diesem Rahmen und wartet auf ein neues Bild.';
    }} else if (status.confirmations >= 2) {{
      message = 'Derselbe Rahmen wird mit dem nächsten neuen Bild weiter geprüft.';
    }} else if (status.confirmations > 0) {{
      message = 'Ziffernfeld bestätigt. Die App prüft mit dem nächsten neuen Bild weiter.';
    }} else if (reason === 'no_region') {{
      message = status.tested >= 2 ?
        'Ziffernfeld nicht gefunden. Markiere den ungefähren Bereich im Kamerabild.' :
        'Noch kein Ziffernbereich gefunden. Die App prüft gleich das nächste Bild …';
    }}
  }}
  if (active && ['shortlist', 'refine', 'waiting'].includes(status.stage) && status.row_found) {{
    const lowered = status.coarse_threshold && status.row_found < status.agreement_threshold;
    message = 'Ziffernzeile gefunden · gelesen ' + status.row_found + ' % (' +
      'Schwelle ' + (lowered ? status.coarse_threshold + ' %, weil in den Feldern Ziffern erkannt wurden' :
        status.agreement_threshold + ' %') + '). ' + message;
  }}
  if (active && reason === 'reflected_geometry') {{
    message = 'Markierter Rahmen mit sichtbaren Ziffern geprüft. Verdeckte Stellen bleiben offen.' +
      ' ' + status.reflected_confirmations + '/' + status.required;
  }}
  if (status.state === 'failed' && ['reference_mismatch', 'position_error'].includes(reason)) {{
    message = 'Der gelesene Bereich passt nicht zum Vergleichswert. Prüfe den Vergleichswert und markiere das Ziffernfeld.';
  }}
  if (background && active) {{
    message = 'Optimierung läuft: Die Automatik ist aktiv. Im Hintergrund sucht die App noch die dritte Nachkommastelle und verbessert Rahmen und Winkel.';
  }}
  if (status.state === 'gave_up') {{
    message = 'Letzte Rolle nicht gefunden: Die Suche wurde nach mehreren Stunden beendet. Die Automatik läuft weiter mit einer Nachkommastelle weniger.';
  }} else if (background && ['failed', 'timeout', 'image_timeout'].includes(status.state)) {{
    message = 'Dritte Nachkommastelle noch offen. Die Automatik läuft weiterhin mit sieben bestätigten Ziffern.';
  }} else if (status.intensive && ['failed', 'timeout', 'image_timeout'].includes(status.state)) {{
    message = status.confirmations >= status.required ?
      'Feinprüfung erfolgreich, Gegenprobe offen. Der beste Rahmen steht für den manuellen Test bereit.' :
      'Dritte Nachkommastelle bleibt unbestätigt. Du kannst später erneut suchen oder sie manuell markieren.';
  }}
  if (active && status.preview?.last_digit_hint) {{
    message += ' Vorschlag für die letzte Rolle gefunden. Die Bestätigung folgt mit einem neuen Bild.';
  }}
  if (active && !status.intensive && !status.simplified && (status.awaiting_start_value || reason === 'await_movement')) {{
    message += ' Ohne Vergleichswert braucht die App einen plausiblen Anstieg oder einen Startwert.';
  }}
  if (active && status.simplified) {{
    message += ' Für die Rahmenwahl werden die ersten zwei Nachkommastellen verglichen.';
  }}
  const confirmationLabel = status.followup ? ' · Feinprüfung der dritten Stelle: ' : ' · Bestätigungen: ';
  const detail = 'Bilder geprüft: ' + status.tested +
    ' · Rahmen getestet: ' + status.attempts +
    confirmationLabel + status.confirmations + '/' + status.required +
    (status.partial_hits ? ' · Teiltreffer (letzte Stelle unklar): ' + status.partial_hits : '') +
    (active ? (status.intensive && ['verify', 'verify_wait'].includes(status.stage) ?
      ' · Zeit für Gegenprobe: ' : (status.intensive || status.automatic ?
      ' · Rechenzeit übrig: ' : ' · Zeit für die Einrichtung: ')) + clock + ' min' : '');
  const weakSlots = status.stress_weak_slots || [];
  const stabilityNote = weakSlots.length ?
    ' · Schwankende Stellen im Intensivtest (von links): ' + weakSlots.join(', ') : '';
  const tone = status.state === 'saved' ? 'ok' : ['saved_without_verification', 'saved_stationary', 'saved_reflection', 'gave_up'].includes(status.state) ? 'warning' :
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
const correctionSaveManual = document.querySelector('#save-digit-correction-manual');
const correctionUndo = document.querySelector('#undo-one-digit');
const correctionBoxes = {{value: '[]'}};
const correctionWidth = {{value: ''}};
const correctionEditor = digitFrameEditor(correctionPreview, correctionBoxes, correctionWidth, correctionPosition);
const correctionImage = new Image();
let correctionLayout = null;
let correctionSource = null;
let originalCorrection = [];
let correctionBusy = false;
let correctionPreferTest = false;

function updateCorrectionControls() {{
  const index = Number(correctionPosition.value);
  const changed = correctionBoxes.value !== JSON.stringify(originalCorrection);
  correctionSave.disabled = correctionBusy || !changed || correctionPreview.hidden;
  correctionSaveManual.disabled = correctionBusy || correctionPreview.hidden;
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
  correctionSaveManual.disabled = true;
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
    // Opened from a finished manual test: its own picture first (also an uploaded one).
    if (correctionPreferTest && job.phase === 'done' && job.checked_at) images.push({{kind: 'test', version: String(job.checked_at)}});
    correctionPreferTest = false;
    if (job.digit_correction_image) images.push({{kind: 'current', version: job.digit_correction_image}});
    if (job.calibration?.preview?.frame) images.push({{kind: 'calibration', version: job.calibration.preview.frame}});
    if (!images.length) throw new Error();
    for (const source of images) {{
      const url = (source.kind === 'test' ? 'testbild.jpg?v=' : source.kind === 'current' ? 'aktuell.jpg?v=' : 'lernvorschau.jpg?bild=frame&v=') +
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
    correctionStatus.textContent = 'Kein passendes Kamerabild vorhanden. Es kommt mit der nächsten regulären Prüfung.';
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
  correctionPreview.inert = action !== 'search';
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
    if (response.redirected && action !== 'search') {{
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
document.querySelector('#correct-after-test').addEventListener('click', () => {{
  correctionPreferTest = true;
  correctionOpen.click();
}});
correctionSaveManual.addEventListener('click', () => submitDigitCorrection('save_manual'));
function renderOcrCandidates(list, candidates) {{
  const evidence = {{
    accepted: 'Zwei Leseprofile stimmen überein – Kandidat übernommen',
    agreement: 'Zwei Leseprofile stimmen überein, Vergleich steht noch aus',
    disagreement: 'Leseprofile liefern unterschiedliche Ziffern',
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
    // 0.5.17: "for the impatient" the notice can be closed; it stays
    // closed for this setup only.
    success.hidden = !job.setup_success || setupSuccessClosed() === (job.setup_success?.duration || '');
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

    const live = document.querySelector('#test-live');
    const seen = active && job.phase === 'ocr' ? (job.readings || []) : [];
    live.hidden = !seen.length;
    live.textContent = seen.length ? 'Bisher gelesen: ' + seen.join(' · ') : '';
    const correctAfter = document.querySelector('#correct-after-test');
    correctAfter.hidden = job.phase !== 'done' || !job.digit_correction;
    correctAfter.disabled = calibrating;

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
      anchored_hidden: 'Die verdeckte Stelle wurde aus dem Zählerstand und dem Durchfluss ergänzt.',
      estimated_hidden: 'Die verdeckte Nachkommastelle wurde geschätzt.',
    }}[job.ocr_method] || '');
    method.hidden = !method.textContent;
    // 0.5.14 (B4): say which check the picture belongs to. While a new
    // check is running, the picture of the previous one is dimmed and labelled as such.
    const previewTime = document.querySelector('#preview-time');
    const stampNs = Number(showManual ? job.checked_at * 1e9 : automaticVersion);
    const running = ['working', 'queued'].includes(document.querySelector('.activity-status')?.dataset.state);
    let timeText = '';
    if (Number.isFinite(stampNs) && stampNs > 1e17) {{
      const taken = new Date(stampNs / 1e6);
      const clock = [taken.getHours(), taken.getMinutes(), taken.getSeconds()].map(value => String(value).padStart(2, '0')).join(':');
      timeText = running && !showManual
        ? 'Bild der vorigen Prüfung (' + clock + ' Uhr). Die laufende Prüfung ist noch nicht fertig.'
        : 'Bild der letzten Prüfung (' + clock + ' Uhr).';
    }}
    if (previewTime.textContent !== timeText) previewTime.textContent = timeText;
    previewTime.hidden = !timeText;
    document.querySelector('#test-preview-image').classList.toggle('preview-outdated', running && !showManual);
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
// 0.5.14: the load of the machine below the background tasks, to
// estimate when the next one can start.
let backgroundLoadTimer = null;
async function refreshBackgroundLoad() {{
  const out = document.querySelector('#background-load');
  const toggle = document.querySelector('#show-background-work');
  if (!out || !toggle || !toggle.checked) return;
  try {{
    const response = await fetch('systemstatus', {{cache: 'no-store'}});
    if (!response.ok) throw new Error();
    const load = await response.json();
    const en = lang === 'en';
    const parts = [];
    if (load.cpu_percent != null) parts.push((en ? 'Processor ' : 'Prozessor ') + load.cpu_percent + ' %' +
      (load.app_cpu_percent != null ? (en ? ' (app ' : ' (App ') + load.app_cpu_percent + ' %)' : ''));
    if (load.memory_used_percent != null) parts.push((en ? 'Memory ' : 'Arbeitsspeicher ') + load.memory_used_percent + ' %');
    if (load.temperature_c != null) parts.push(Math.round(load.temperature_c) + ' °C');
    const seconds = next ? Math.max(0, Math.ceil(next - Date.now() / 1000)) : null;
    if (seconds != null) parts.push((en ? 'next check in ' : 'nächste Prüfung in ') + Math.floor(seconds / 60) + ':' + String(seconds % 60).padStart(2, '0') + ' min');
    const busy = (load.cpu_percent != null && load.cpu_percent >= 85) || (load.memory_used_percent != null && load.memory_used_percent >= 92);
    out.textContent = (en ? 'Load: ' : 'Auslastung: ') + (parts.join(' · ') || '–') + '. ' + (busy
      ? (en ? 'The machine is busy; background tasks wait.' : 'Der Rechner ist ausgelastet; Hintergrundaufgaben warten.')
      : (en ? 'Background tasks run in the time between the checks.' : 'Hintergrundaufgaben laufen in der Zeit zwischen den Prüfungen.'));
  }} catch (_) {{
    out.textContent = '';
  }}
}}
function renderBackgroundWork(items) {{
  const box = document.querySelector('#background-live');
  const toggle = document.querySelector('#show-background-work');
  if (!box || !toggle) return;
  box.hidden = !toggle.checked;
  if (box.hidden) {{
    if (backgroundLoadTimer) {{ clearInterval(backgroundLoadTimer); backgroundLoadTimer = null; }}
    return;
  }}
  if (!backgroundLoadTimer) {{
    refreshBackgroundLoad();
    backgroundLoadTimer = setInterval(refreshBackgroundLoad, 5000);
  }}
  const list = document.querySelector('#background-live-list');
  const key = JSON.stringify(items);
  if (list.dataset.items === key) return;
  list.dataset.items = key;
  const en = lang === 'en';
  if (!items.length) {{
    const empty = document.createElement('p');
    empty.className = 'settings-note';
    empty.textContent = en ? 'No background tasks since the app started.' : 'Seit dem Start der App gab es noch keine Hintergrundaufgaben.';
    list.replaceChildren(empty);
    return;
  }}
  list.replaceChildren(...items.map(item => {{
    const card = document.createElement('div');
    card.className = 'background-job';
    card.dataset.state = item.state;
    card.dataset.job = item.id;
    const head = document.createElement('p');
    head.className = 'background-job-head';
    head.setAttribute('role', 'status');
    const title = document.createElement('strong');
    title.textContent = item.title + ': ';
    const state = document.createElement('span');
    state.className = 'background-job-state';
    state.textContent = item.state_label;
    head.append(title, state);
    card.append(head);
    const line = (label, value) => {{
      if (value == null || value === '') return;
      const row = document.createElement('p');
      row.textContent = label + value;
      card.append(row);
    }};
    line(en ? 'Step: ' : 'Schritt: ', item.step);
    if (item.image) {{
      const stamp = Date.parse(item.image);
      line(en ? 'Picture: ' : 'Bild: ', Number.isNaN(stamp) ? item.image : formatStamp(stamp / 1000));
    }}
    line(en ? 'Read: ' : 'Gelesen: ', item.reading);
    if (Number.isInteger(item.total) && item.total > 0) {{
      const bar = document.createElement('progress');
      bar.max = item.total;
      bar.value = Math.min(item.total, Number(item.completed) || 0);
      bar.setAttribute('aria-label', item.title);
      card.append(bar);
      line(en ? 'Progress: ' : 'Fortschritt: ', (Number(item.completed) || 0) + (en ? ' of ' : ' von ') + item.total);
    }}
    line(item.state === 'running' || item.state === 'waiting' ? (en ? 'Status: ' : 'Stand: ') : (en ? 'Result: ' : 'Ergebnis: '), item.result);
    if (item.at) line(en ? 'Last activity: ' : 'Zuletzt aktiv: ', formatStamp(item.at));
    return card;
  }}));
}}
{{
  const toggle = document.querySelector('#show-background-work');
  if (toggle) {{
    try {{ toggle.checked = localStorage.getItem('rf1-show-background-work') === '1'; }} catch (error) {{}}
    toggle.addEventListener('change', () => {{
      try {{ localStorage.setItem('rf1-show-background-work', toggle.checked ? '1' : '0'); }} catch (error) {{}}
      document.querySelector('#background-live-list').dataset.items = '';
      renderBackgroundWork(lastBackgroundWork);
    }});
  }}
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
let filledSlots = [];
function renderOdometer(reading) {{
  const box = document.querySelector('#meter-odometer');
  const text = String(reading || '').trim();
  // Rollers beyond the compared decimal places are not needed and not shown (0.5.0).
  const shown = Number.isInteger(configuredDecimals) ? configuredDecimals : 9;
  const key = text + '|' + shown + '|' + filledSlots.join(',');
  if (box.dataset.rendered === key) return;
  box.dataset.rendered = key;
  box.setAttribute('aria-label', (lang === 'en' ? 'Meter reading ' : 'Zählerstand ') + (text || '–'));
  if (!/[0-9?]/.test(text)) {{
    const empty = document.createElement('span');
    empty.className = 'odometer-empty';
    empty.textContent = lang === 'en' ? 'No reading yet' : 'Noch kein Zählerstand';
    box.replaceChildren(empty);
    return;
  }}
  const [whole, allFraction = ''] = text.replace(',', '.').split('.');
  const fraction = allFraction.slice(0, shown);
  let slot = 0;
  const roller = (char, isFraction) => {{
    const cell = document.createElement('span');
    const filled = filledSlots.includes(slot++) && /[0-9]/.test(char);
    cell.className = 'roller' + (isFraction ? ' fraction' : '') + (/[0-9]/.test(char) && !filled ? '' : ' unclear');
    if (filled) cell.title = lang === 'en' ? 'Filled in from the meter reading (hidden by a reflection)' :
      'Aus dem Zählerstand ergänzt (durch Spiegelung verdeckt)';
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
  // The digit searched in the background is the first one that is not compared yet.
  const searchedPosition = reading.includes('.') && comparedDecimals !== null
    ? wholeDigits.length + comparedDecimals + 1 : 0;
  let noteText = '', noteState = '';
  if (/[0-9?]/.test(reading) && frameRelocating) {{
    noteText = lang === 'en'
      ? 'The frame of the last digit sat beside its roller and is being searched again in the background. Until then the app checks with one decimal place less.'
      : 'Der Rahmen der letzten Stelle saß neben der Rolle und wird gerade im Hintergrund neu gesucht. Bis dahin prüft die App mit einer Nachkommastelle weniger.';
    noteText += lang === 'en' ? ' This runs automatically in the background with the normal check pictures.'
      : ' Das läuft automatisch im Hintergrund mit den normalen Prüfbildern mit.';
    noteState = 'searching';
  }} else if (/[0-9?]/.test(reading) && lastDigitSearching) {{
    // No countdown: the search only evaluates the pictures of the normal automatic checks.
    const left = lang === 'en' ? ' (runs along with the normal check pictures)' : ' (läuft nebenbei mit den normalen Prüfbildern mit)';
    if (/[0-9]$/.test(fractionDigits)) {{
      noteText = lang === 'en' ? `Optimising${{left}}: all digits are read, the app is improving frames and angle.`
        : `Optimierung läuft${{left}}: Alle Ziffern sind gelesen, die App verbessert noch Rahmen und Winkel.`;
      noteState = 'optimizing';
    }} else {{
      noteText = lang === 'en' ? `The ${{position}}th digit is being searched in the background${{left}}.`
        : `Die ${{position}}. Ziffer wird im Hintergrund gesucht${{left}}.`;
      noteState = 'searching';
    }}
  }} else if (lastDigitGivenUp && comparedDecimals !== null && configuredDecimals !== null && comparedDecimals < configuredDecimals) {{
    noteText = lang === 'en'
      ? `The last roller could not be found after several hours of searching. The app keeps checking with ${{comparedDecimals}} of ${{configuredDecimals}} decimal places, even in precision mode. `
        + 'Either the image quality is too poor, or the last digit could not be read despite several attempts (for example because of a reflection, or because it keeps turning while gas flows). A new setup starts the search again.'
      : `Die letzte Rolle wurde nach mehreren Stunden Suche nicht gefunden. Die App prüft weiter mit ${{comparedDecimals}} von ${{configuredDecimals}} Nachkommastellen, auch im Präzisionsmodus. `
        + 'Entweder ist die Bildqualität zu schlecht, oder die letzte Ziffer ließ sich trotz mehrerer Versuche nicht lesen (zum Beispiel wegen einer Spiegelung oder weil sie sich bei laufendem Gas ständig dreht). Eine neue Einrichtung startet die Suche erneut.';
    noteState = 'skipped';
  }} else if (comparedDecimals !== null && configuredDecimals !== null && comparedDecimals < configuredDecimals) {{
    const at = lastDigitSearchAt && lastDigitSearchAt * 1000 > Date.now()
      ? new Date(lastDigitSearchAt * 1000).toLocaleTimeString(lang === 'en' ? 'en-GB' : 'de-DE', {{hour: '2-digit', minute: '2-digit'}})
      : '';
    noteText = lang === 'en'
      ? `Temporarily only ${{comparedDecimals}} decimal places are compared (setting: ${{configuredDecimals}}). `
        + (searchedPosition ? (at ? `The search for the ${{searchedPosition}}th digit starts at about ${{at}}.` : `The background search for the ${{searchedPosition}}th digit is retried automatically.`)
          : (at ? `The search for the last digit starts at about ${{at}}.` : `The background search for the last digit is retried automatically.`))
      : `Vorübergehend werden nur ${{comparedDecimals}} Nachkommastellen verglichen (eingestellt: ${{configuredDecimals}}). `
        + (searchedPosition ? (at ? `Die Suche nach der ${{searchedPosition}}. Ziffer beginnt gegen ${{at}} Uhr.` : `Die Suche nach der ${{searchedPosition}}. Ziffer wird automatisch wiederholt.`)
          : (at ? `Die Suche nach der letzten Ziffer beginnt gegen ${{at}} Uhr.` : `Die Suche nach der letzten Ziffer wird automatisch wiederholt.`));
    noteState = 'skipped';
  }} else if (fractionDigits.endsWith('?') && comparedDecimals !== null && comparedDecimals < fractionDigits.length) {{
    noteText = lang === 'en'
      ? `The ${{position}}th digit is not compared (setting: ${{comparedDecimals}} decimal places).`
      : `Die ${{position}}. Ziffer wird nicht verglichen (eingestellt: ${{comparedDecimals}} Nachkommastellen).`;
    noteState = 'skipped';
  }}
  if (!noteText && frameRelocatedAt && Date.now() - frameRelocatedAt * 1000 < 2 * 3600 * 1000) {{
    const at = new Date(frameRelocatedAt * 1000).toLocaleTimeString(lang === 'en' ? 'en-GB' : 'de-DE', {{hour: '2-digit', minute: '2-digit'}});
    noteText = lang === 'en' ? `The frame of the last digit was set again automatically at ${{at}}.`
      : `Der Rahmen der letzten Stelle wurde um ${{at}} Uhr automatisch neu gesetzt.`;
    noteState = 'optimizing';
  }}
  if (partialEighthDigit && configuredDecimals === 3 && lastDigitSearching) {{
    noteText += lang === 'en' ? ' Until then 2 of 3 decimal places are compared.'
      : ' Bis dahin werden 2 von 3 Nachkommastellen verglichen.';
  }}
  if (note.textContent !== noteText) note.textContent = noteText;
  note.dataset.state = noteState;
  note.hidden = !noteText;
  const searchProgress = document.querySelector('#hero-search-progress');
  // Background searches have no time limit to show: they run along with the automatic checks.
  searchProgress.hidden = true;
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
    const top = Math.max(0, ...hours.map(bucket => bucket.litres || 0));
    document.querySelector('#consumption-chart-peak').textContent = top
      ? (lang === 'en' ? 'highest hour: ' : 'höchste Stunde: ') + consumptionFormat.format(top / 1000) + ' m³' : '';
  }}
  const coarse = document.querySelector('#consumption-resolution');
  const step = Number(data.resolution_litres) || 0;
  coarse.hidden = chart.hidden || step < 100;
  if (!coarse.hidden) {{
    const size = consumptionFormat.format(step / 1000) + ' m³';
    coarse.textContent = lang === 'en'
      ? 'The meter is read in steps of ' + size + '. Hourly values are therefore only rough; compare more decimal places for a finer chart.'
      : 'Der Zähler wird in Schritten von ' + size + ' abgelesen. Die Stundenwerte sind deshalb nur grob; mit mehr verglichenen Nachkommastellen wird die Anzeige feiner.';
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
let systemMonitorTimer = null;
async function refreshSystemMonitor() {{
  const set = (id, text) => {{ document.querySelector(id).textContent = text; }};
  const percent = value => value == null ? '–' : value + ' %';
  try {{
    const response = await fetch('systemstatus', {{cache: 'no-store'}});
    if (!response.ok) throw Error();
    const data = await response.json();
    set('#system-cpu', percent(data.cpu_percent) + (data.cores ? ' · ' + data.cores + (lang === 'en' ? ' cores' : ' Kerne') : ''));
    set('#system-app-cpu', percent(data.app_cpu_percent));
    set('#system-memory', data.memory_total_mb == null ? '–'
      : percent(data.memory_used_percent) + ' · ' + (data.memory_total_mb - data.memory_available_mb) + ' / ' + data.memory_total_mb + ' MB');
    set('#system-app-memory', data.app_memory_mb == null ? '–' : data.app_memory_mb + ' MB');
    set('#system-temperature', data.temperature_c == null
      ? (lang === 'en' ? 'not available on this device' : 'auf diesem Gerät nicht verfügbar')
      : String(data.temperature_c).replace('.', lang === 'en' ? '.' : ',') + ' °C');
  }} catch (_) {{
    set('#system-cpu', lang === 'en' ? 'Could not be loaded.' : 'Konnte nicht geladen werden.');
  }}
}}
async function refreshBackgroundWork() {{
  const list = document.querySelector('#background-work-list');
  const en = lang === 'en';
  const rows = [];
  try {{
    const response = await fetch('hintergrund?lang=' + lang, {{cache: 'no-store'}});
    if (!response.ok) throw Error();
    const data = await response.json();
    rows.push((en ? 'Automatic checks in the log: ' : 'Automatische Prüfungen im Protokoll: ') + data.checks);
    for (const tested of Object.values(data.experiments)) {{
      rows.push(tested.label + ': ' + (!tested.runs
        ? (en ? 'no run yet (switch it on under Settings)' : 'noch kein Lauf (unter Einstellungen einschalten)')
        : tested.runs + (en ? ' runs · same as the check: ' : ' Läufe · gleich wie die Prüfung: ') + tested.same +
          (en ? ' · different: ' : ' · anders: ') + tested.different +
          (en ? ' · unclear: ' : ' · unklar: ') + tested.unclear +
          (en ? ' · no result: ' : ' · ohne Ergebnis: ') + tested.no_result +
          (tested.errors ? (en ? ' · errors: ' : ' · Fehler: ') + tested.errors : '') +
          (tested.seconds == null ? '' : (en ? ' · on average ' : ' · im Schnitt ') +
            String(tested.seconds).replace('.', en ? '.' : ',') + ' s')));
    }}
    const hintNames = en ? {{dark: 'too dark', bright: 'too bright', low_contrast: 'low contrast'}}
      : {{dark: 'zu dunkel', bright: 'zu hell', low_contrast: 'wenig Kontrast'}};
    const hints = Object.entries(data.image_hints || {{}}).map(([name, count]) => hintNames[name] + ' ' + count + '×');
    rows.push((en ? 'Picture hints in these checks: ' : 'Bildhinweise in diesen Prüfungen: ') +
      (hints.length ? hints.join(' · ') : (en ? 'none' : 'keine')));
    if (data.skipped_busy) rows.push((en ? 'Skipped because the device was busy: ' : 'Wegen Auslastung übersprungen: ') + data.skipped_busy);
    const idle = data.idle;
    rows.push(!idle.runs
      ? (en ? 'Waiting time: nothing to do so far.' : 'Wartezeit: bisher nichts zu tun.')
      : (en ? 'Waiting time: ' : 'Wartezeit: ') + idle.runs + (en ? ' jobs · unclear digits read again: ' : ' Arbeiten · unklare Ziffern nochmals gelesen: ') +
        idle.reread + (en ? ', readable: ' : ', davon lesbar: ') + idle.resolved +
        (en ? ' · experiments caught up: ' : ' · Experimente nachgeholt: ') + idle.experiments);
  }} catch (_) {{
    rows.push(en ? 'Could not be loaded.' : 'Konnte nicht geladen werden.');
  }}
  list.replaceChildren(...rows.map(text => {{
    const item = document.createElement('li');
    item.textContent = text;
    return item;
  }}));
}}
document.querySelector('#background-work').addEventListener('toggle', event => {{
  if (event.target.open) refreshBackgroundWork();
}});
document.querySelector('#system-monitor').addEventListener('toggle', event => {{
  clearInterval(systemMonitorTimer);
  if (!event.target.open) return;
  refreshSystemMonitor();
  systemMonitorTimer = setInterval(refreshSystemMonitor, 5000);
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
    const waitReason = document.querySelector('#hero-wait-reason');
    if (waitReason.textContent !== (sample.wait_reason || '')) waitReason.textContent = sample.wait_reason || '';
    waitReason.hidden = !sample.wait_reason;
    lastBackgroundWork = sample.background_work || [];
    renderBackgroundWork(lastBackgroundWork);
    renderConsumption(sample.consumption);
    comparedDecimals = Number.isInteger(sample.decimals) ? sample.decimals : null;
    configuredDecimals = Number.isInteger(sample.configured_decimals) ? sample.configured_decimals : comparedDecimals;
    lastDigitSearchAt = typeof sample.last_digit_search_at === 'number' ? sample.last_digit_search_at : null;
    partialEighthDigit = sample.partial_eighth_digit === true;
    lastDigitGivenUp = sample.last_digit_given_up === true;
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
    if (!checkDetails.hidden && !checkDetails.dataset.toggleBound) {{
      checkDetails.dataset.toggleBound = '1';
      checkDetails.addEventListener('toggle', () => {{
        try {{ localStorage.setItem('rf1-check-details-closed', checkDetails.open ? '0' : '1'); }} catch (error) {{}}
      }});
    }}
    if (!checkDetails.hidden && !checkDetails.dataset.restored) {{
      checkDetails.dataset.restored = '1';
      let closed = false;
      try {{ closed = localStorage.getItem('rf1-check-details-closed') === '1'; }} catch (error) {{}}
      checkDetails.open = !closed;
    }}
    renderDigitGrid(document.querySelector('#automatic-digit-grid'), checkDetails.hidden ? [] : sample.activity_readings,
      Number.isInteger(sample.decimals) ? sample.decimals : null);
    updateLastReadings(sample, !progress.hidden);
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
    // Background work is shown live: refresh more often while the box is ticked.
    if (document.querySelector('#show-background-work')?.checked) refreshDelay = Math.min(refreshDelay, 3000);
    const geometryStatus = document.querySelector('#geometry-repair-warning');
    geometryStatus.hidden = !sample.geometry_warning;
    geometryStatus.textContent = sample.geometry_warning;
    const recovery = document.querySelector('#automatic-recovery');
    recovery.hidden = !sample.failure_attempts;
    document.querySelector('#report-bug-hint').hidden = !(sample.failure_attempts >= 3);
    recovery.dataset.state = sample.retry_suppressed ? 'waiting' : 'retrying';
    recovery.textContent = sample.recovery_notice;
    // 0.5.12: once the reading was entered the request disappears; it only comes
    // back when a check after the entry could not fill the digit again.
    filledSlots = Array.isArray(sample.filled_slots) ? sample.filled_slots : [];
    const hiddenPrompt = sample.hidden_digit_prompt && !(readingEnteredAt && Number(sample.hidden_digit_prompt.image_time || sample.hidden_digit_prompt.time) <= readingEnteredAt)
      ? sample.hidden_digit_prompt : null;
    document.querySelector('#hidden-digit-prompt').hidden = !hiddenPrompt;
    document.querySelector('#hero-action').hidden = !hiddenPrompt;
    if (hiddenPrompt) {{
      document.querySelector('#hidden-digit-text').textContent =
        'Stelle ' + hiddenPrompt.positions.join(' und ') + ' ist durch eine Spiegelung verdeckt.';
      // 0.5.12: the cut-out counter of the last picture; the reading entered belongs to its time.
      const figure = document.querySelector('#hidden-digit-figure');
      const picture = document.querySelector('#hidden-digit-image');
      const stamp = Number(hiddenPrompt.image_time);
      if (Number.isFinite(stamp) && stamp > 0 && picture.dataset.stamp !== String(stamp)) {{
        picture.dataset.stamp = String(stamp);
        picture.onload = () => {{ figure.hidden = false; }};
        picture.onerror = () => {{ figure.hidden = true; document.querySelector('#hidden-digit-time').value = ''; }};
        picture.src = 'zaehlwerk.jpg?v=' + stamp;
        const taken = new Date(stamp * 1000);
        const pad = value => String(value).padStart(2, '0');
        document.querySelector('#hidden-digit-time').value = taken.getFullYear() + '-' + pad(taken.getMonth() + 1) + '-' +
          pad(taken.getDate()) + 'T' + pad(taken.getHours()) + ':' + pad(taken.getMinutes());
        document.querySelector('#hidden-digit-image-time').textContent = ' (' + pad(taken.getHours()) + ':' + pad(taken.getMinutes()) + ')';
      }}
    }}
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
    document.querySelector('#automatic-last-match').title = sample.last_match ? '' : (lang === 'en'
      ? 'No confirmed reading since the setup yet' : 'Noch keine bestätigte Lesung seit der Einrichtung');
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


def wizard_energy_factors(field, old_rules):
    """kWh factors from the setup wizard; fields the form did not send keep their saved value."""
    values = {}
    for key, limits in (("gas_state_factor", STATE_FACTOR_RANGE), ("calorific_value", CALORIFIC_RANGE),
                        ("kwh_conversion_factor", CONVERSION_RANGE)):
        text = field(key, None)
        values[key] = old_rules.get(key) if text is None else parse_energy_factor(text, limits)
    return values


EXPERIMENT_LEVELS = (("off", "Aus", "Off"), ("1", "Schattenmodus", "Shadow mode"),
                     ("active", "Aktiv testen (noch nicht freigegeben)", "Active testing (not released yet)"))


def experiment_level_options(shadow, language="de"):
    """The three levels of one experiment; "Aktiv testen" is not released for any experiment yet."""
    chosen = "1" if shadow else "off"
    return "".join(f'<option value="{value}"{" selected" if value == chosen else ""}'
                   f'{" disabled" if value == "active" else ""}>{english if language == "en" else german}</option>'
                   for value, german, english in EXPERIMENT_LEVELS)


def experiment_settings(field):
    """Levels of the experiments; the setup wizard and the settings send the same fields.

    Only "off" and shadow mode ("1") are stored; a forged "active" counts as off.
    """
    return {"experiments_enabled": field("experiments_enabled") == "1",
            "experiments": {"perspective": field("experiment_perspective") == "1",
                            "seven_segment": field("experiment_seven_segment") == "1"}}


def parse_failure_pause(text):
    value = int(str(text).strip())
    if not MIN_FAILURE_PAUSE_MINUTES <= value <= MAX_FAILURE_PAUSE_MINUTES:
        raise ValueError("Ungültige Pause nach Fehlprüfungen")
    return value


def format_factor(value, language="de"):
    if type(value) not in (int, float):
        return ""
    text = f"{value:.4f}".rstrip("0").rstrip(".")
    return text if language == "en" else text.replace(".", ",")


def editable_rotation(values):
    angle = values.get("rotation", 0)
    if type(angle) is not int:
        return 0
    angle = -90 if angle == 270 else angle if -180 <= angle <= 180 else 0
    fine = fine_rotation(values.get("rotation_fine", 0))
    return f"{angle + fine:.1f}".rstrip("0").rstrip(".") if fine else angle
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


def marked_reflection_note(rules, source, language):
    """0.5.14 (B3): say on the overview which digit is treated as hidden by a reflection."""
    marked = rules.get("setup_reflection")
    if (not rules.get("reflection_estimate_enabled") or not isinstance(marked, dict) or source is None
            or marked.get("source") != setup_source_id(source)):
        return ""
    positions = [slot + 1 for slot in marked.get("positions") or [] if type(slot) is int]
    if not positions:
        return ""
    if language == "en":
        text = (f"Digit {' and '.join(map(str, positions))} is hidden by a reflection "
                f"({'found by the setup' if marked.get('automatic') else 'marked by you'}). "
                "The app does not read it, but fills it in from the meter reading and the flow.")
    else:
        text = (f"Stelle {' und '.join(map(str, positions))} ist durch eine Spiegelung verdeckt "
                f"({'von der Einrichtung erkannt' if marked.get('automatic') else 'von dir markiert'}). "
                "Die App liest sie nicht, sondern ergänzt sie aus Zählerstand und Durchfluss.")
    return '<p class="settings-note marked-reflection-note">' + html.escape(text) + "</p>"


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


FRAME_NOTES = {
    "user": "Rahmen: von Hand gesetzt. Die Automatik liest genau diese Rahmen und verändert sie nicht.",
    "setup": "Rahmen: von der Selbsteinrichtung gefunden. Die Automatik darf sie nachjustieren.",
    "manual": "Rahmen: fest gespeichert. Die Automatik darf sie nachjustieren.",
    "auto": "Bildbereich: automatische Erkennung ohne feste Rahmen. Die App sucht die Ziffernreihe in jedem Bild neu.",
}


def frames_note(rules, language):
    """One sentence that says which frames the automatic uses (overview and settings)."""
    kind = ("auto" if rules.get("crop_mode") != "manual" else
            rules.get("frames_origin") if rules.get("frames_origin") in ("user", "setup") else "manual")
    text = FRAME_NOTES[kind]
    return EN_UI[text] if language == "en" else text


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
    request_factory_reset=None, get_reset_status=None, skip_setup=None, get_activity=None, get_background_work=None,
    get_auto_paused=None, save_auto_paused=None, discover_sources=None,
    find_kit_cameras=None, confirm_kit_camera=None, get_kit_extras=None, set_kit_extra=None,
    settings_lock=None, get_calibration=None, control_calibration=None, get_calibration_image=None,
    has_calibration_backup=None, get_wizard_image=None, real_demo=None, statistics_zone=timezone.utc,
    can_start_automatic=None, start_automatic_check=None,
):
    images = {"/aktuell.jpg": current_image, "/treffer.jpg": good_image,
              "/testvorschau.jpg": test_image}
    if automatic_preview is not None:
        images["/automatikvorschau.jpg"] = automatic_preview
    if test_source_image is not None:
        images["/testbild.jpg"] = test_source_image
    images["/zaehlwerk.jpg"] = history_path.with_name("ocr-zaehlwerk.jpg")
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

    worker_save_auto_rules = save_auto_rules

    def save_auto_rules(values, **options):
        # Frames changed in the web interface were placed by the user (auto_rules.user_frames).
        worker_save_auto_rules(user_frames(read_auto_rules(), values), **options)

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
            message = "Die Ziffern werden seit mindestens 40 Minuten nicht sicher erkannt. Prüfe Bildausschnitt, Fokus und Beleuchtung."
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
        # 0.5.17: a setup saved with a reflection (or a still meter) only
        # counts as completed with its first passed automatic check; the notice then stays a
        # minute instead of until the next check.
        if (type(finished_check) in (int, float) and abs(finished_check - completed["time"]) < 5
                and time.time() - completed["time"] >= 60):
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
        last_digit_given_up = partial_eighth_digit and eighth_digit_given_up(history, auto_rules)
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
        view = status_view.verdict(history, language, detail=detail, precision_pending=precision_pending,
                                   paused=paused, setup_pending=setup_pending,
                                   partial_eighth_digit=partial_eighth_digit, now=now,
                                   last_digit_given_up=last_digit_given_up)
        tone, heading, icon, incident = view["tone"], view["heading"], view["icon"], view["incident"]
        show_attempts, detail, routine_ok = view["show_attempts"], view["detail"], view["routine_ok"]
        failure_attempts, retry_suppressed, recovery_notice = status_view.recovery(
            history, language, paused, statistics_zone)
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
            "wait_reason": "" if activity.get("state") == "setup_wait" or paused else wait_reason_text(history, language),
            "background_work": get_background_work(language) if get_background_work else [],
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
                                     if decimals < auto_rules["decimals"] and not last_digit_given_up else None),
            "last_digit_given_up": last_digit_given_up,
            "reflection_estimate": reflection_estimate,
            "filled_slots": [slot for slot in history.get("filled_slots") or [] if type(slot) is int],
            "hidden_digit_prompt": (history.get("hidden_digit_prompt")
                                    if auto_rules.get("reflection_estimate_enabled")
                                    and not auto_rules.get("hidden_digit_prompt_hidden") else None),
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
            "activity_readings": activity.get("readings"),
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
            if path == "/hintergrund":
                overview = background_view.summary(debug_log.read_text())
                if language == "en":
                    for tested in overview["experiments"].values():
                        tested["label"] = EN_UI.get(tested["label"], tested["label"])
                self.reply(json.dumps(overview).encode("utf-8"), "application/json")
                return
            if path == "/systemstatus":
                self.reply(json.dumps(system_monitor.snapshot()).encode("utf-8"), "application/json")
                return
            if path == "/debug-protokoll":
                try:
                    limit = max(1, min(600, int(query.get("limit", ["600"])[0])))
                except ValueError:
                    limit = 600
                self.reply(debug_log.read_text(limit).encode("utf-8"), "text/plain; charset=utf-8")
                return
            if path == "/testbild-streifen":
                # Only the cropped digit window, as Base64 text (the HA proxy mangles binary images).
                strip = history_path.with_name("ocr-ziffernstreifen.png")
                if not read_auto_rules().get("experiments_enabled") or not strip.exists():
                    self.send_error(404)
                    return
                self.reply(base64.b64encode(strip.read_bytes()), "text/plain; charset=ascii")
                return
            if path == "/fehler-melden":
                rules = read_auto_rules()
                source = get_source()[0] if get_source else {}
                experiments = rules.get("experiments", {}) if rules.get("experiments_enabled") else {}
                target = bug_report.issue_url(
                    os.environ.get("BUILD_VERSION", "") or "unbekannt", source.get("mode", ""),
                    rules.get("integer_digits", 5), rules.get("fraction_digits", 3),
                    [name for name, active in experiments.items() if active], debug_log.read_text(),
                    language=language,
                )
                self.send_response(303)
                self.send_header("Location", target)
                self.send_header("Content-Length", "0")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Referrer-Policy", "no-referrer")
                self.end_headers()
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
            if path == "/zaehlerkamera-zusaetze":
                # 0.5.26: the extras of the meter camera (off by default) for the checkboxes.
                camera = parse_qs(urlsplit(self.path).query).get("camera", [""])[0]
                extras = get_kit_extras(camera) if get_kit_extras and CAMERA.fullmatch(camera) else {}
                self.reply(json.dumps(extras).encode("utf-8"), "application/json; charset=utf-8")
                return
            if path == "/neue-zaehlerkameras":
                # 0.5.25: meter cameras Home Assistant has discovered but not added yet.
                cameras = find_kit_cameras() if find_kit_cameras else []
                self.reply(json.dumps(cameras).encode("utf-8"), "application/json; charset=utf-8")
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
                "pending": "Das Zurücksetzen läuft noch. Die Einrichtung öffnet sich, sobald es fertig ist.",
                "failed": "Das Zurücksetzen wurde nicht vollständig ausgeführt.",
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
                "Die Einrichtung prüft mit dem nächsten Bild um 180° gedreht weiter." if saved == "flip" else
                "Das Kamerabild wird jetzt gespiegelt. Die Einrichtung sucht das Zählwerk neu." if saved == "mirror" else
                "Fallback-Wert gespeichert." if saved == "fallback" else
                "Zählerstand übernommen. Die nächste Prüfung startet jetzt." if saved == "reading" else
                ("Gerade läuft schon eine Prüfung oder Einrichtung, oder die Automatik ist pausiert. "
                 "Eine weitere Prüfung startet danach automatisch.") if saved == "check-busy" else
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
                '<p class="legend" id="test-source-empty" hidden>Kein Bild vorhanden. Prüfe Bildquelle und Verbindung und starte den manuellen Test erneut.</p>'
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
                app_version=html.escape(os.environ.get("BUILD_VERSION", "") or ""),
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
                overview_hidden="hidden" if settings_tab_active or tools_tab_active else "",
                settings_hidden="" if settings_tab_active else "hidden",
                tools_hidden="" if tools_tab_active else "hidden",
                language_options=select_options({"auto": automatic, "de": "Deutsch", "en": "English"}, mode),
                settings_open="open" if saved in ("1", "crop-reset", "fallback") else "",
                frames_note=html.escape(frames_note(auto_rules, language)),
                fallback_saved_notice=auto_saved_notice if saved == "fallback" else "",
                calibration_preview_html=(translate_page(CALIBRATION_PREVIEW_HTML) if language == "en"
                                          else CALIBRATION_PREVIEW_HTML).format(
                    language=language, mode=mode, csrf=csrf_token),
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
                experiments_checked="checked" if auto_rules.get("experiments_enabled") else "",
                experiment_seven_segment_levels=experiment_level_options(
                    (auto_rules.get("experiments") or {}).get("seven_segment"), language),
                experiment_perspective_levels=experiment_level_options(
                    (auto_rules.get("experiments") or {}).get("perspective"), language),
                reflection_hide_checked="checked" if auto_rules.get("reflection_suggestion_hidden") else "",
                quality_hint_checked="checked" if auto_rules.get("quality_hint_hidden") else "",
                quality_hint_hidden="hidden" if auto_rules.get("quality_hint_hidden") else "",
                reflection_suggestion_hidden="" if summary["reflection_suggestion"] else "hidden",
                reflection_estimate_hidden="" if estimate.get("confirmed") else "hidden",
                marked_reflection_note=marked_reflection_note(auto_rules, get_source()[0] if get_source else None, language),
                reflection_approval_hidden="" if pending_estimate else "hidden",
                reflection_approval_id=html.escape(str(pending_estimate.get("id", ""))),
                reflection_digits_option=(select_options({pending_estimate["digit"]: pending_estimate["digit"]}, "")
                                          if pending_estimate else ""),
                reflection_left=html.escape(str(estimate.get("left", ""))),
                reflection_digit=html.escape(str(estimate.get("digit", ""))),
                reflection_right=html.escape(str(estimate.get("right", ""))),
                reflection_time=html.escape(str(estimate.get("time", 0))),
                kit_installer_url=KIT_INSTALLER_URL,
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
                source_light=html.escape(source.get("light", "")),
                camera_light_checked="checked" if source.get("camera_light", True) is not False else "",
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
                gas_state_factor=format_factor(auto_rules.get("gas_state_factor"), language),
                calorific_value=format_factor(auto_rules.get("calorific_value"), language),
                kwh_conversion_factor=format_factor(auto_rules.get("kwh_conversion_factor"), language),
                max_interval_minutes=MAX_INTERVAL_MINUTES,
                slfork_interval_hidden="" if source["mode"] == "slfork" else "hidden",
                interval_minutes=auto_rules.get("interval_minutes", DEFAULT_INTERVAL_MINUTES),
                failure_pause_minutes=auto_rules.get("failure_pause_minutes", DEFAULT_FAILURE_PAUSE_MINUTES),
                auto_rotation_value=editable_rotation(auto_rules),
                auto_saved_notice=auto_saved_notice if saved in ("1", "crop-reset") else "",
                overview_saved_notice=auto_saved_notice if saved in ("crop", "reading", "check-busy", "flip", "mirror") else "",
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
                            "/spiegelungs-hinweis-ausblenden", "/bildqualitaet-hinweis-ausblenden", "/ergaenzte-ziffer-bestaetigen", "/selbsteinrichtung", "/fallback", "/ziffernrahmen", "/zaehler-demo", "/automatik-jetzt", "/vergleichsgenauigkeit",
                            "/zaehlerkamera-hinzufuegen", "/zaehlerkamera-zusatz"):
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
                                    max_num_fields=48)  # the wizard sends about 42 fields since the level selects (0.5.0)
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
            if path == "/zaehlerkamera-zusatz":
                camera, extra, state = (form.get(name, []) for name in ("camera", "extra", "on"))
                if (set_kit_extra is None or len(camera) != 1 or not CAMERA.fullmatch(camera[0])
                        or len(extra) != 1 or extra[0] not in KIT_EXTRAS or state not in (["1"], ["0"])):
                    problem(400)
                    return
                outcome = set_kit_extra(camera[0], extra[0], state == ["1"])
                self.reply(json.dumps({"result": outcome}).encode("utf-8"), "application/json; charset=utf-8")
                return
            if path == "/zaehlerkamera-hinzufuegen":
                flow = form.get("flow_id", [])
                if len(flow) != 1 or confirm_kit_camera is None:
                    problem(400)
                    return
                outcome = confirm_kit_camera(flow[0])
                self.reply(json.dumps({"result": outcome}).encode("utf-8"), "application/json; charset=utf-8")
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
                    # 0.5.17: no bare error page – usually a check is already
                    # running or requested. Back to the overview with a short note.
                    self.redirect("?ui=overview&saved=check-busy" + keep_mode)
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
                # A second request waits for the first instead of failing at once.
                if not demo_lock.acquire(timeout=45):
                    problem(503)
                    return
                try:
                    picture = field("picture")
                    if picture and real_demo is None:
                        problem(503)
                        return
                    result = (real_demo(int(picture)) if picture.isdigit()
                              else run_demo(field("reflection") == "1"))
                    self.reply(json.dumps(result).encode("utf-8"), "application/json")
                except (OSError, ValueError, subprocess.SubprocessError):
                    problem(503)
                finally:
                    demo_lock.release()
                return
            if path == "/einrichtungsbild":
                try:
                    source = source_rules({"mode": selected_source_mode(), "url": field("url"),
                                           "camera": field("camera"), "reference": "", "light": field("light"),
                                           "camera_light": field("camera_light") == "1" if field("camera_light_present") == "1" else True})
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
                except CameraOffline as error:
                    reason = EN_UI.get(str(error), str(error)) if language == "en" else str(error)
                    self.reply(json.dumps({"reason": reason}).encode("utf-8"), "application/json; charset=utf-8", 503)
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

            if path == "/bildqualitaet-hinweis-ausblenden":
                try:
                    with rules_lock:
                        save_auto_rules({**read_auto_rules(), "quality_hint_hidden": True}, request_check=False)
                except (OSError, ValueError):
                    problem(503)
                    return
                self.redirect("?ui=overview" + keep_mode)
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
                        "camera": field("camera"), "reference": field("reference"), "light": field("light"),
                        "camera_light": field("camera_light") == "1" if field("camera_light_present") == "1" else True,
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
                    rotation_fine = fine_rotation(old_rules.get("rotation_fine", 0))
                    if not learn_crop:
                        crop = field("crop", crop)
                        width = int(field("width", str(width)))
                        rotation, rotation_fine = split_rotation(field("rotation", str(rotation)))
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
                        "width": width, "rotation": rotation, "rotation_fine": rotation_fine,
                        "digit_boxes": old_rules["digit_boxes"] if (
                            crop_mode == old_rules["crop_mode"] and crop == old_rules["crop"]
                            and rotation == old_rules.get("rotation", 0) and width == old_rules["width"]
                            and integer_digits == old_rules["integer_digits"] and fraction_digits == old_rules["fraction_digits"]
                        ) else [], "max_flow_lph": max_flow,
                        "gas_state_factor": parse_energy_factor(field("gas_state_factor"), STATE_FACTOR_RANGE),
                        "calorific_value": parse_energy_factor(field("calorific_value"), CALORIFIC_RANGE),
                        "kwh_conversion_factor": parse_energy_factor(field("kwh_conversion_factor"), CONVERSION_RANGE),
                        "precision_mode": precise,
                        "self_repair_enabled": field("self_repair_enabled") == "1",
                        "fine_alignment_enabled": (field("fine_alignment_enabled") == "1"
                                                  if field("fine_alignment_option_present") == "1"
                                                  else old_rules.get("fine_alignment_enabled", False)),
                        "reflection_estimate_enabled": (field("reflection_estimate_enabled") == "1"
                                                        if field("reflection_option_present") == "1"
                                                        else old_rules.get("reflection_estimate_enabled", False)),
                        "interval_minutes": interval_minutes, "integer_digits": integer_digits,
                        "failure_pause_minutes": parse_failure_pause(field("failure_pause_minutes",
                                                                           str(old_rules.get("failure_pause_minutes",
                                                                                             DEFAULT_FAILURE_PAUSE_MINUTES)))),
                        "fraction_digits": fraction_digits, "meter_display": meter_display,
                        "fallback_value": fallback_value, "fallback_time": fallback_time,
                    }
                    if field("experiments_option_present") == "1":
                        rules_values.update(experiment_settings(field))
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
                            "light": field("light", current.get("light", "")),
                            "camera_light": (field("camera_light") == "1" if field("camera_light_present") == "1"
                                             else current.get("camera_light", True)),
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
                # The takeover belongs to the overview: that is where the automatic shows its result.
                self.redirect("?saved=crop&ui=overview" + keep_mode)
                return
            if path == "/fallback":
                try:
                    with rules_lock:
                        rules = read_auto_rules()
                        entered_time = field("fallback_time")
                        if not entered_time and field("return_to") == "overview":
                            # Reading entered on the overview: it was read just now.
                            entered_time = datetime.now(statistics_zone).strftime("%Y-%m-%dT%H:%M")
                        value, stamp = fallback_options(
                            field("fallback_value"), entered_time, rules["decimals"],
                            rules["integer_digits"], rules["fraction_digits"],
                        )
                        save_auto_rules({**rules, "fallback_value": value, "fallback_time": stamp,
                                         "setup_input_source": setup_source_id(get_source()[0]),
                                         **({"hidden_digit_prompt_hidden": True} if field("hide_prompt") == "1" else {})})
                except ValueError:
                    problem(400, "Bitte Zählerstand und Ablesezeit prüfen.", "Check the meter reading and its time.")
                    return
                except OSError:
                    problem(503)
                    return
                if field("return_to") == "overview":
                    # Stay on the overview and say that the value was taken over.
                    self.redirect("?saved=reading&ui=overview" + keep_mode)
                    return
                self.redirect("?saved=fallback&ui=settings" + keep_mode + "#fallback-form")
                return
            if path == "/selbsteinrichtung":
                if control_calibration is None:
                    self.send_error(404)
                    return
                action = field("action")
                try:
                    if action not in ("start", "intensive", "cancel", "restore", "skip-verification", "confirm-reflection",
                                      "flip", "mirror"):
                        raise ValueError("Invalid calibration action")
                    starting = action in ("start", "intensive")
                    limit = int(field("image_limit", str(DEFAULT_LIMIT))) if starting else 0
                    if starting and not MIN_IMAGE_LIMIT <= limit <= MAX_IMAGES:
                        raise ValueError("Invalid calibration image limit")
                    region = search_region(field("region")) if action == "start" else None
                    if action == "confirm-reflection":
                        rules = read_auto_rules()
                        reading = fallback_options(field("fallback_value"),
                                                   datetime.now(statistics_zone).strftime("%Y-%m-%dT%H:%M"),
                                                   rules["decimals"], rules["integer_digits"], rules["fraction_digits"])
                        control_calibration(action, 0, verification_id=field("glare_id"), reading=reading)
                    elif action in ("flip", "mirror"):
                        control_calibration(action, 0)
                    elif action == "skip-verification":
                        verification_id = field("verification_id")
                        if not verification_id:
                            raise ValueError("Missing verification ID")
                        control_calibration(action, limit, verification_id=verification_id)
                    elif region:
                        control_calibration(action, limit, region=region)
                    else:
                        control_calibration(action, limit)
                except ValueError:
                    if action == "confirm-reflection":
                        problem(400, "Bitte den Zählerstand prüfen. Die Spiegelung wartet nicht mehr auf eine Bestätigung, wenn die Einrichtung inzwischen weiter ist.",
                                "Check the meter reading. The reflection no longer waits for a confirmation if the setup has moved on.")
                        return
                    if action == "skip-verification":
                        problem(409, "Die Gegenprobe für diesen Rahmen ist nicht mehr offen.",
                                "Verification for this crop is no longer pending.")
                        return
                    if action in ("flip", "mirror"):
                        problem(409, "Die Einrichtung läuft nicht mehr. Starte sie neu, um das Bild zu drehen oder zu spiegeln.",
                                "The setup is no longer running. Start it again to turn or mirror the picture.")
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
                saved = ("crop-restored" if action == "restore" else action if action in ("flip", "mirror")
                         else "calibration")
                view = ("overview" if action in ("start", "intensive", "skip-verification", "confirm-reflection",
                                                 "flip", "mirror") else "settings")
                self.redirect(f"?saved={saved}&ui={view}" + keep_mode)
                return
            if path == "/ziffernrahmen":
                action = field("action")
                try:
                    if action not in ("save", "save_manual", "search"):
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
                        elif action == "save_manual":
                            # Only the manual test gets these frames: the automatic keeps its own
                            # and no automatic check is started (0.5.0).
                            save_manual_settings({
                                **load_manual_settings(), "polarity": rules["polarity"], "decimals": rules["decimals"],
                                "attempts": rules["attempts"], "crop_mode": "manual", "crop": layout["crop"],
                                "width": layout["width"], "rotation": layout["rotation"],
                                "rotation_fine": fine_rotation(rules.get("rotation_fine", 0)),
                                "digit_boxes": boxes, "crop_revision": rules.get("crop_revision", "")})
                    if action == "save":
                        self.redirect("?saved=digit-frames&ui=overview" + keep_mode)
                        return
                    if action == "save_manual":
                        self.redirect("?saved=manual-crop&ui=tools" + keep_mode)
                        return
                    index = int(field("index"))
                    if not 0 <= index < count:
                        raise ValueError("Invalid digit index")
                    version = field("image_version")
                    if field("image_kind") == "calibration":
                        content = get_calibration_image("frame", version) if get_calibration_image else None
                    elif field("image_kind") == "test":
                        # The picture of the last manual test (also an uploaded one); it only
                        # changes with the next manual test.
                        manual_picture = images.get("/testbild.jpg")
                        content = (manual_picture.read_bytes()
                                   if manual_picture is not None and manual_picture.exists() else None)
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
                        rotation_fine = fine_rotation(old_rules.get("rotation_fine", 0))
                        boxes = []
                        if crop_mode[0] == "manual":
                            crop = field("crop", crop)
                            boxes = digit_box_settings(json.loads(field("digit_boxes", "[]")),
                                                      old_rules["integer_digits"] + old_rules["fraction_digits"])
                            width = int(field("width", str(width)))
                            rotation, rotation_fine = split_rotation(field("rotation", str(rotation)))
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
                                         **experiment_settings(field),
                                         "reflection_suggestion_hidden": field("reflection_suggestion_hidden") == "1",
                                         "quality_hint_hidden": field("quality_hint_hidden") == "1",
                                         "polarity": polarity[0], "crop_mode": crop_mode[0],
                                         "crop": crop, "width": width, "rotation": rotation, "rotation_fine": rotation_fine, "digit_boxes": boxes,
                                         "max_flow_lph": max_flow, "interval_minutes": interval_minutes,
                                         **wizard_energy_factors(field, old_rules),
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
            rotation_fine = 0.0
            boxes = []
            crop_revision = auto_rules.get("crop_revision", "")
            if crop_revision and field("crop_revision") != crop_revision:
                crop_mode = [auto_rules["crop_mode"]]
                crop_value, width_value, rotation = auto_rules["crop"], auto_rules["width"], auto_rules["rotation"]
                rotation_fine = fine_rotation(auto_rules.get("rotation_fine", 0))
                boxes = auto_rules["digit_boxes"]
            elif crop_mode[0] == "manual":
                try:
                    crop_value = field("crop", default_crop)
                    width_value = int(field("width", str(default_width)))
                    rotation, rotation_fine = split_rotation(field("rotation", "0"))
                    boxes = digit_box_settings(json.loads(field("digit_boxes", "[]")),
                                              auto_rules["integer_digits"] + auto_rules["fraction_digits"])
                    boundaries = crop_coordinates(crop_value, width_value, rotation)
                    crop_value = ",".join(map(str, boundaries))
                except ValueError:
                    problem(400)
                    return
            settings = {"polarity": polarity[0], "decimals": int(decimals[0]),
                        "attempts": int(attempts[0]), "crop_mode": crop_mode[0],
                        "crop": crop_value, "width": width_value, "rotation": rotation,
                        "rotation_fine": rotation_fine, "digit_boxes": boxes}
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
