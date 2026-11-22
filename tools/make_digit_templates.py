"""Render the digit templates used by rf1_ocr_test/glyph_match.py.

Run once when the template fonts change:
    python3 tools/make_digit_templates.py
Needs the Debian packages fonts-dejavu-extra and fonts-liberation. The PNG holds one row per
font with the digits 0-9 as white glyphs on black, each in a 72x96 cell.
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONTS = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSansNarrow-Regular.ttf",
)
CELL = (72, 96)
HEIGHT = 84


def glyph(path, digit):
    font = ImageFont.truetype(path, 160)
    canvas = Image.new("L", (240, 240), 0)
    ImageDraw.Draw(canvas).text((40, 10), digit, fill=255, font=font)
    shape = canvas.crop(canvas.getbbox())
    width = max(1, round(shape.width * HEIGHT / shape.height))
    return shape.resize((min(width, CELL[0] - 4), HEIGHT), Image.Resampling.LANCZOS)


def main():
    sheet = Image.new("L", (CELL[0] * 10, CELL[1] * len(FONTS)), 0)
    for row, path in enumerate(FONTS):
        for digit in range(10):
            shape = glyph(path, str(digit))
            x = digit * CELL[0] + (CELL[0] - shape.width) // 2
            y = row * CELL[1] + (CELL[1] - shape.height) // 2
            sheet.paste(shape, (x, y))
    target = Path(__file__).resolve().parents[1] / "rf1_ocr_test" / "digit_templates.png"
    sheet.save(target, optimize=True)
    print(target, target.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
