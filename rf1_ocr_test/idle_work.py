"""Work between two routine checks, without new camera images (0.5.0, Stefan 21.11.2026).

The app keeps the pictures of the last two checks (the regular picture and the one of the
cross-check). In the waiting time it may look at them again with a small budget; it never
fetches a picture or switches the light for that. The pictures stay in the app's data folder
and are overwritten by every check.
"""

from pathlib import Path

KEPT_IMAGES = 2
MAX_IMAGE_BYTES = 3_000_000


def image_paths(folder):
    """Newest first: where the pictures of the last checks are kept."""
    return [Path(folder) / f"letzte-pruefung-{number}.jpg" for number in range(1, KEPT_IMAGES + 1)]


def remember_check_image(folder, content, write):
    """Keep ``content`` as the newest check picture; the one before moves to second place.

    ``write(path, content, mode)`` stores a file atomically. Returns True when it was kept.
    """
    if not isinstance(content, (bytes, bytearray)) or not 0 < len(content) <= MAX_IMAGE_BYTES:
        return False
    newest, older = image_paths(folder)
    try:
        if newest.exists():
            if newest.read_bytes() == bytes(content):
                return False  # the same picture again (e.g. the source delivered nothing new)
            newest.replace(older)
        write(newest, bytes(content), 0o600)
    except OSError:
        return False
    return True


def kept_images(folder):
    """The stored pictures, newest first, as bytes."""
    pictures = []
    for path in image_paths(folder):
        try:
            pictures.append(path.read_bytes())
        except OSError:
            continue
    return pictures


def forget_images(folder):
    for path in image_paths(folder):
        path.unlink(missing_ok=True)
