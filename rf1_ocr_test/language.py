"""Resolve the UI locale without sharing browser preferences across HA users."""

import json
import re

SUPPORTED = ("de", "en")
MODES = ("auto", *SUPPORTED)
# Supervisor supplies a Home Assistant user UUID or omits the header.
USER_ID = re.compile(r"[a-f0-9]{32}")


def normalize_locale(value):
    language = re.split("[-_]", value.strip().lower(), maxsplit=1)[0]
    return language if language in SUPPORTED else None


def browser_locale(header):
    candidates = []
    for entry in header.split(","):
        tag, *parameters = entry.split(";")
        language = normalize_locale(tag)
        if language is None:
            continue
        weight = 1.0
        for parameter in parameters:
            name, _, value = parameter.strip().partition("=")
            if name.lower() == "q":
                try:
                    weight = float(value)
                except ValueError:
                    weight = 0
        if 0 < weight <= 1:
            candidates.append((weight, language))
    return max(candidates, key=lambda item: item[0])[1] if candidates else "de"


def load_preferences(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    if not isinstance(data, dict):
        raise ValueError("Ungültige Spracheinstellungen")
    return data


# The current user's connection is already authenticated by the HA frontend.
# Do not read browser auth storage or ask Core for other users' preferences.
PROFILE_SCRIPT = """
(() => {
  if (new URLSearchParams(location.search).has('ui')) return;
  document.documentElement.classList.add('resolving-language');
  const user = %s;
  const reveal = () => document.documentElement.classList.remove('resolving-language');
  async function resolve() {
    try {
      if (window.top === window) return;
      let hass = window.top.document.querySelector('home-assistant')?.hass;
      for (let attempt = 0; !hass?.user && attempt < 20; attempt++) {
        await new Promise(resolve => setTimeout(resolve, 150));
        hass = window.top.document.querySelector('home-assistant')?.hass;
      }
      if (hass?.user?.id !== user || typeof hass.callWS !== 'function') return;
      const response = await Promise.race([
        hass.callWS({type: 'frontend/get_user_data', key: 'language'}),
        new Promise(resolve => setTimeout(resolve, 1000)),
      ]);
      const raw = response?.value?.language;
      const language = typeof raw === 'string' ? raw.toLowerCase().split(/[-_]/, 1)[0] : '';
      if (language !== 'en' && language !== 'de') return;
      const url = new URL(location.href);
      url.searchParams.set('ui', language);
      location.replace(url);
      return true;
    } catch (_) {
      // The parent may be cross-origin or the frontend may be unavailable.
    }
  }
  const deadline = setTimeout(reveal, 4500);
  resolve().then(redirecting => {
    clearTimeout(deadline);
    if (!redirecting) reveal();
  });
})();
"""


def profile_script(user):
    return PROFILE_SCRIPT % json.dumps(user)
