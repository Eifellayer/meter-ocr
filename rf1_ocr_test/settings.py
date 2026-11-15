"""Migrate Home Assistant app options to the current RF1 schema."""

SCHEMA_VERSION = 1

DEFAULTS = {
    "esp_url": "http://esp-gaszaehler.local",
    "ausschnitt": "52,56,564,132",
    "vorkomma_breite": 305,
    "helle_ziffern": False,
    "zeitzone": "Europe/Berlin",
    "push_dienst": "",
    "vergleich_nachkommastellen": 0,
    "ocr_versuche": 5,
    "kamera_entitaet": "",
    "referenz_entitaet": "",
}


def migrate_to_v1(options):
    # Version 0.6.0 switched to scheduled checks with fixed intervals.
    options.pop("intervall_sekunden", None)


MIGRATIONS = {1: migrate_to_v1}


def migrate_options(saved, source_version):
    if type(source_version) is not int or not 0 <= source_version <= SCHEMA_VERSION:
        raise ValueError("Unbekannte RF1-Konfigurationsversion")
    options = dict(saved)
    for version in range(source_version + 1, SCHEMA_VERSION + 1):
        MIGRATIONS[version](options)
    return options


def load_options(supervisor_options, snapshot):
    previous = migrate_options(snapshot.get("options", {}), snapshot.get("schema_version", 0))
    current = migrate_options(supervisor_options, 0)
    return {**DEFAULTS, **previous, **current}
