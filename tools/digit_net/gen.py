import random, io, glob
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from feat import features
F = ['/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf','/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
 '/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf','/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed.ttf',
 '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf','/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf',
 '/usr/share/fonts/truetype/liberation/LiberationSansNarrow-Regular.ttf','/usr/share/fonts/truetype/liberation/LiberationSansNarrow-Bold.ttf',
 '/usr/share/fonts/truetype/freefont/FreeSans.ttf','/usr/share/fonts/truetype/freefont/FreeSansBold.ttf',
 '/usr/share/fonts/truetype/google-fonts/ofl/anton/Anton-Regular.ttf',
 '/usr/share/fonts/truetype/google-fonts/ofl/firasans/FiraSans-Regular.ttf','/usr/share/fonts/truetype/google-fonts/ofl/firasans/FiraSans-SemiBold.ttf',
 '/usr/share/fonts/truetype/google-fonts/ofl/firasans/FiraSans-Bold.ttf','/usr/share/fonts/truetype/google-fonts/ofl/firasans/FiraSans-Medium.ttf',
 '/usr/share/fonts/truetype/crosextra/Carlito-Regular.ttf','/usr/share/fonts/truetype/crosextra/Carlito-Bold.ttf',
 '/usr/share/fonts/truetype/adf/GilliusADF-Cond.otf','/usr/share/fonts/truetype/adf/GilliusADF-BoldCond.otf',
 '/usr/share/fonts/truetype/google-fonts/ofl/roboto/Roboto[wdth,wght].ttf' if glob.glob('/usr/share/fonts/truetype/google-fonts/ofl/roboto/Roboto[[]wdth,wght].ttf') else '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
]
G='/usr/share/fonts/truetype/google-fonts/ofl/'
BOLD = ['/usr/share/fonts/truetype/google-fonts/ofl/anton/Anton-Regular.ttf',
 '/usr/share/fonts/truetype/liberation/LiberationSansNarrow-Bold.ttf', G+'firasans/FiraSans-Black.ttf', G+'firasans/FiraSans-ExtraBold.ttf',
 G+'firasans/FiraSans-Bold.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
 G+'archivoblack/ArchivoBlack-Regular.ttf', '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf', '/usr/share/fonts/truetype/crosextra/Carlito-Bold.ttf',
 ('var', G+'opensans/OpenSans[wdth,wght].ttf'), ('var', G+'roboto/Roboto[wdth,wght].ttf')]
CACHE = {}
def pick_font():
    f = random.choice(BOLD) if random.random() < .75 else random.choice(F)
    if isinstance(f, tuple):
        f = (f[1], random.choice((75, 80, 87)), random.choice((600, 700, 800)))
    return f
def glyph(font, d, h):
    key = (font, d)
    if key not in CACHE:
        if isinstance(font, tuple):
            fo = ImageFont.truetype(font[0], 160)
            try:
                axes = fo.get_variation_axes()
                vals = [font[1] if a.get('name', b'') in (b'Width', 'Width') else font[2] for a in axes]
                fo.set_variation_by_axes(vals)
            except Exception:
                pass
        else:
            fo = ImageFont.truetype(font, 160)
        img = Image.new('L', (260, 260), 0)
        ImageDraw.Draw(img).text((40, 20), d, fill=255, font=fo)
        CACHE[key] = img.crop(img.getbbox())
    g = CACHE[key]
    w = max(1, round(g.width * h / g.height * random.uniform(.8, 1.15)))
    return g.resize((w, max(1, round(h))), Image.Resampling.LANCZOS)

def sample(label=None):
    H = 48
    W = round(H * random.uniform(.5, 1.15))
    big = 3
    Hb, Wb = H * big, W * big
    bg = random.randint(0, 110)
    fg = random.randint(min(255, bg + 40), 255)
    img = Image.new('L', (Wb, Hb), bg)
    dr = ImageDraw.Draw(img)
    # roller body vs. gaps at the sides
    if random.random() < .6:
        gap = random.randint(max(0, bg - 60), min(255, bg + 60))
        edge = round(Wb * random.uniform(0, .18))
        dr.rectangle((0, 0, edge, Hb), fill=gap)
        edge2 = round(Wb * random.uniform(0, .18))
        dr.rectangle((Wb - edge2, 0, Wb, Hb), fill=gap)
    font = pick_font()
    gh = Hb * random.uniform(.65, 1.15)
    cls = label if label is not None else random.randrange(11)
    def paste(d, cx, cy, level=fg):
        g = glyph(font, d, gh)
        mask = g
        layer = Image.new('L', g.size, level)
        img.paste(layer, (round(cx - g.width / 2), round(cy - g.height / 2)), mask)
    cx = Wb / 2 + Wb * random.uniform(-.12, .12)
    cy = Hb / 2 + Hb * random.uniform(-.1, .1)
    pitch = gh * random.uniform(1.25, 1.6)
    if cls < 10:
        d = str(cls)
        paste(d, cx, cy)
        if random.random() < .35:  # neighbouring digits on the roller above/below
            dy = random.choice((-1, 1))
            paste(str((cls - dy) % 10), cx, cy + dy * pitch)
    else:
        kind = random.random()
        if kind < .75:  # roller between two digits
            d = random.randrange(10)
            frac = random.uniform(.3, .7)
            paste(str(d), cx, cy - frac * pitch)
            paste(str((d + 1) % 10), cx, cy + (1 - frac) * pitch)
        elif kind < .9:
            pass  # empty
        else:
            r = Wb * random.uniform(.35, .7)
            dr.ellipse((cx - r, cy - r, cx + r, cy + r), fill=255)
    if random.random() < .5:  # bright frame, label or roller gap at one side
        side = random.choice((0, 1)); part = round(Wb * random.uniform(.08, .45))
        level = random.randint(0, 255)
        box = (0, 0, part, Hb) if side == 0 else (Wb - part, 0, Wb, Hb)
        dr.rectangle(box, fill=level)
    if random.random() < .3:  # bright band above or below
        part = round(Hb * random.uniform(.05, .2)); level = random.randint(bg, 255)
        dr.rectangle((0, 0, Wb, part) if random.random() < .5 else (0, Hb - part, Wb, Hb), fill=level)
    # neighbour glyph fragments at the cell edges
    if random.random() < .4:
        side = random.choice((-1, 1))
        paste(str(random.randrange(10)), cx + side * Wb * random.uniform(.85, 1.3), cy + Hb * random.uniform(-.05, .05))
    if cls < 10 and random.random() < .2:  # small glare
        r = Wb * random.uniform(.08, .2)
        x, y = random.uniform(0, Wb), random.uniform(0, Hb)
        dr.ellipse((x - r, y - r * .6, x + r, y + r * .6), fill=255)
    if random.random() < .3:
        img = img.filter(ImageFilter.MaxFilter(3) if random.random() < .5 else ImageFilter.MinFilter(3))
    img = img.rotate(random.uniform(-4, 4), resample=Image.Resampling.BILINEAR, fillcolor=bg)
    sh = random.uniform(-.12, .12)
    img = img.transform(img.size, Image.Transform.AFFINE, (1, sh, -sh * Hb / 2, 0, 1, 0), resample=Image.Resampling.BILINEAR, fillcolor=bg)
    img = img.filter(ImageFilter.GaussianBlur(random.uniform(.2, 4.5) * big))
    img = img.resize((W, H), Image.Resampling.BOX)
    if random.random() < .6:  # uneven light
        ramp = Image.linear_gradient('L').rotate(random.choice((0, 90, 180, 270))).resize((W, H))
        lo = random.uniform(.4, .9)
        ramp = ramp.point(lambda v: round(255 * (lo + (1 - lo) * v / 255)))
        from PIL import ImageChops
        img = ImageChops.multiply(img, ramp)
    if random.random() < .8:
        noise = Image.effect_noise((W, H), random.uniform(1, 14))
        img = Image.blend(img, noise, random.uniform(0, .15))
    if random.random() < .6:
        b = io.BytesIO(); img.save(b, 'JPEG', quality=random.randint(8, 90)); img = Image.open(io.BytesIO(b.getvalue())).convert('L')
    # random crop jitter / margin
    m = lambda: round(random.uniform(-.06, .1) * H)
    l, t, r_, bt = m(), m(), m(), m()
    img = img.crop((l, t, W - r_, H - bt))
    return img, cls

if __name__ == '__main__':
    import sys
    strip = Image.new('L', (12 * 50, 5 * 54), 128)
    for i in range(60):
        im, c = sample()
        strip.paste(im.resize((48, 48)), ((i % 12) * 50, (i // 12) * 54))
        print(c, end=' ')
    strip.save(sys.argv[1])
