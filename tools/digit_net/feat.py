from PIL import Image, ImageChops, ImageFilter, ImageOps
FW, FH = 16, 24

def glyph_channel(picture, light=True):
    if picture.mode != "L":
        r, g, b = picture.convert("RGB").split()
        gray = ImageChops.darker(ImageChops.darker(r, g), b) if light else ImageOps.invert(ImageChops.lighter(ImageChops.lighter(r, g), b))
    else:
        gray = picture if light else ImageOps.invert(picture)
    return gray

def glyph_image(picture, light=True):
    gray = glyph_channel(picture, light)
    if gray.height != 48:
        gray = gray.resize((max(8, round(gray.width * 48 / gray.height)), 48), Image.Resampling.BILINEAR)
    gray = ImageOps.autocontrast(gray, cutoff=1)
    k = 15
    opened = gray.filter(ImageFilter.MinFilter(k)).filter(ImageFilter.MaxFilter(k))
    top = ImageOps.autocontrast(ImageChops.subtract(gray, opened), cutoff=1)
    width = top.width
    if top.width > width:
        cols = [sum(top.crop((x, 0, x + 1, top.height)).tobytes()) for x in range(top.width)]
        sums = [sum(cols[x:x + width]) for x in range(top.width - width + 1)]
        x = max(range(len(sums)), key=sums.__getitem__)
        top = top.crop((x, 0, x + width, top.height))
    return top

def features(picture, light=True):
    small = glyph_image(picture, light).resize((FW, FH), Image.Resampling.BOX)
    values = list(small.tobytes())
    n = len(values)
    mean = sum(values) / n
    std = (sum((v - mean) ** 2 for v in values) / n) ** .5 or 1.0
    return [(v - mean) / std for v in values]
