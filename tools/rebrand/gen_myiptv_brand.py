#!/usr/bin/env python3
"""Redraw the OwnTV name baked into the TV banners and the splash-screen name images as "MyIPTV".

Core ships one banner (drawable-*/owntv_banner_<colour>.png) and one splash name image
(drawable-*/owntv_splash_name_<colour>.png) per app-icon colour and screen density. The play mark
stays as it is; only the word is replaced, keeping each variant's own colours and the word's box.
Results go to app/src/main/res/drawable-*/ under the same names, which override core's.

Usage (core checked out at the tag the app pins):

    python3 -I tools/rebrand/gen_myiptv_brand.py --core /tmp/core/core/src/main/res \
        --font app/src/main/res/font/poppins_bold.ttf --out app/src/main/res
"""
import argparse
import colorsys
import glob
import os

from PIL import Image, ImageDraw, ImageFont

SS = 4  # supersampling factor for smooth glyph edges
FIRST, SECOND = "My", "IPTV"


def bbox_of_text(im, bg, left_frac):
    """Bounding box of the pixels that are not background, right of left_frac of the width."""
    w, h = im.size
    px = im.load()
    x0, y0, x1, y1 = w, h, 0, 0
    for y in range(h):
        for x in range(int(w * left_frac), w):
            p = px[x, y]
            if p[3] < 40:
                continue
            if sum(abs(p[i] - bg[i]) for i in range(3)) > 90:
                x0, y0, x1, y1 = min(x0, x), min(y0, y), max(x1, x), max(y1, y)
    return (x0, y0, x1 + 1, y1 + 1) if x1 > x0 else None


def sample_colours(im, box, bg):
    """(first-word colour, accent colour) read from the existing text: brightest left, most vivid right."""
    x0, y0, x1, y1 = box
    px = im.load()
    third = (x1 - x0) // 3
    best_l, best_r, score_l, score_r = (255, 255, 255), (80, 200, 190), -1, -1
    for y in range(y0, y1):
        for x in range(x0, x1):
            p = px[x, y]
            if p[3] < 200 or sum(abs(p[i] - bg[i]) for i in range(3)) < 120:
                continue
            h, s, v = colorsys.rgb_to_hsv(p[0] / 255, p[1] / 255, p[2] / 255)
            if x < x0 + third and v - s * 0.2 > score_l:
                score_l, best_l = v - s * 0.2, p[:3]
            if x > x1 - third and s * v > score_r:
                score_r, best_r = s * v, p[:3]
    return best_l, best_r


def draw_word(box_w, box_h, fonts_path, first_col, second_col):
    """The word on a transparent canvas at SS x, fitted to box_w; returns (image, text w, text h) at 1x."""
    size = 10
    while True:
        font = ImageFont.truetype(fonts_path, size * SS)
        wa = font.getlength(FIRST)
        wb = font.getlength(SECOND)
        if (wa + wb) / SS > box_w or size > 400:
            size -= 1
            break
        size += 1
    font = ImageFont.truetype(fonts_path, size * SS)
    wa, wb = font.getlength(FIRST), font.getlength(SECOND)
    asc, desc = font.getmetrics()
    canvas = Image.new("RGBA", (int(wa + wb) + 8 * SS, asc + desc + 8 * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(canvas)
    d.text((4 * SS, 4 * SS), FIRST, font=font, fill=first_col + (255,))
    d.text((4 * SS + wa, 4 * SS), SECOND, font=font, fill=second_col + (255,))
    return canvas


def paste_centered(base, word, cx, cy, left=None):
    w = max(1, word.width // SS)
    h = max(1, word.height // SS)
    small = word.resize((w, h), Image.LANCZOS)
    # vertical centre of the glyphs themselves, not of the font box
    alpha_box = small.getchannel("A").getbbox() or (0, 0, w, h)
    gx = (alpha_box[0] + alpha_box[2]) / 2
    gy = (alpha_box[1] + alpha_box[3]) / 2
    x = int(round((left - alpha_box[0]) if left is not None else cx - gx))
    y = int(round(cy - gy))
    base.alpha_composite(small, (x, y))


def banner(src, font, dst):
    im = Image.open(src).convert("RGBA")
    bg = im.getpixel((im.width - 3, 3))
    box = bbox_of_text(im, bg, 0.42)
    if not box:
        print("no text found in", src)
        return
    first, accent = sample_colours(im, box, bg)
    pad = max(2, im.height // 60)
    ImageDraw.Draw(im).rectangle((box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad), fill=bg)
    word = draw_word(box[2] - box[0], box[3] - box[1], font, first, accent)
    paste_centered(im, word, 0, (box[1] + box[3]) / 2, left=box[0])
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    im.convert("RGB").save(dst, optimize=True)


def splash_name(src, font, dst):
    im = Image.open(src).convert("RGBA")
    box = im.getchannel("A").getbbox()
    if not box:
        print("empty splash name", src)
        return
    first, accent = sample_colours(im, box, (0, 0, 0, 0))
    out = Image.new("RGBA", im.size, (0, 0, 0, 0))
    word = draw_word(box[2] - box[0], box[3] - box[1], font, first, accent)
    paste_centered(out, word, (box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    out.save(dst, optimize=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--core", required=True)
    ap.add_argument("--font", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    n = 0
    for pattern, fn in (("drawable*/owntv_banner_*.png", banner), ("drawable*/owntv_splash_name_*.png", splash_name)):
        for src in sorted(glob.glob(os.path.join(a.core, pattern))):
            rel = os.path.relpath(src, a.core)
            fn(src, a.font, os.path.join(a.out, rel))
            n += 1
    print(n, "images written")


if __name__ == "__main__":
    main()
