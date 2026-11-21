#!/usr/bin/env python3
"""news-image-20261121 — Saturday 21 November 2026 world news, one image.

A deterministic Python 3.13 stdlib-only renderer. It draws a newspaper
front page ("THE WORLD TODAY") summing up the day's world news and writes
a 1024x1024 PNG to /output/entry.png (or $MAKEFUN_OUTPUT_DIR/entry.png).
No network, no randomness, no time: two runs write identical bytes.

Run:  MAKEFUN_OUTPUT_DIR=out python3 main.py
"""

import math
import os
import struct
import zlib

W = 1024
H = 1024

# ---------------------------------------------------------------- palette
PAPER = (247, 242, 231)   # warm newsprint
INK = (24, 24, 24)        # body ink
NAVY = (20, 38, 61)       # masthead band
RED = (169, 34, 41)       # kickers / accents
TEAL = (13, 92, 86)       # secondary accent
GOLD = (198, 141, 26)     # pictogram highlights
RULE = (198, 189, 168)    # hairlines
SOFT = (96, 91, 78)       # captions
WHITE = (255, 255, 255)
CREAM = (235, 228, 210)   # cell tint


# ---------------------------------------------------------------- canvas
class Page:
    def __init__(self, w, h, bg):
        self.w = w
        self.h = h
        self.pix = bytearray(w * h * 3)
        for i in range(0, len(self.pix), 3):
            self.pix[i:i + 3] = bytes(bg)

    def px(self, x, y, c):
        if 0 <= x < self.w and 0 <= y < self.h:
            o = (y * self.w + x) * 3
            self.pix[o:o + 3] = bytes(c)

    def rect(self, x, y, w, h, c):
        x0 = max(0, x)
        y0 = max(0, y)
        x1 = min(self.w, x + w)
        y1 = min(self.h, y + h)
        for yy in range(y0, y1):
            o = (yy * self.w + x0) * 3
            self.pix[o:(o + (x1 - x0) * 3)] = bytes(c) * (x1 - x0)

    def hline(self, x, y, w, c, t=1):
        self.rect(x, y, w, t, c)

    def vline(self, x, y, h, c, t=1):
        self.rect(x, y, t, h, c)

    def disc(self, cx, cy, r, c):
        # filled circle, scanline
        for dy in range(-r, r + 1):
            dx = int((r * r - dy * dy) ** 0.5)
            self.rect(cx - dx, cy + dy, 2 * dx + 1, 1, c)

    def dotline(self, x0, y0, x1, y1, c, t=2):
        # thick line as a chain of discs (Bresenham walk)
        dx = x1 - x0
        dy = y1 - y0
        n = max(abs(dx), abs(dy), 1)
        for i in range(n + 1):
            x = x0 + dx * i // n
            y = y0 + dy * i // n
            self.disc(x, y, t, c)

    def tri(self, ax, ay, bx, by, cx, cy, c):
        # filled triangle, scanline over its bounding box
        minx = max(0, min(ax, bx, cx))
        maxx = min(self.w - 1, max(ax, bx, cx))
        miny = max(0, min(ay, by, cy))
        maxy = min(self.h - 1, max(ay, by, cy))
        den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if den == 0:
            return
        for yy in range(miny, maxy + 1):
            for xx in range(minx, maxx + 1):
                a = ((by - cy) * (xx - cx) + (cx - bx) * (yy - cy)) / den
                b = ((cy - ay) * (xx - cx) + (ax - cx) * (yy - cy)) / den
                d = 1.0 - a - b
                if a >= 0 and b >= 0 and d >= 0:
                    self.px(xx, yy, c)


# ------------------------------------------------------------------- font
# Hand-drawn 5x7 bitmap font, one 7-row block per glyph.
# '#' = ink, '.' = empty. Uppercase + digits + punctuation only:
# the page is set entirely in capitals, like a newspaper headline font.
FONT = {
    'A': ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    'B': ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    'C': ("01111", "10000", "10000", "10000", "10000", "10000", "01111"),
    'D': ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    'E': ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    'F': ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    'G': ("01111", "10000", "10000", "10111", "10001", "10001", "01110"),
    'H': ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    'I': ("01110", "00100", "00100", "00100", "00100", "00100", "01110"),
    'J': ("00111", "00010", "00010", "00010", "00010", "10010", "01100"),
    'K': ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    'L': ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    'M': ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    'N': ("10001", "11001", "11001", "10101", "10011", "10011", "10001"),
    'O': ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    'P': ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    'Q': ("01110", "10001", "10001", "10001", "10101", "10010", "01101"),
    'R': ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    'S': ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    'T': ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    'U': ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    'V': ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
    'W': ("10001", "10001", "10001", "10001", "10001", "10101", "01010"),
    'X': ("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
    'Y': ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
    'Z': ("11111", "00001", "00010", "00100", "01000", "10000", "11111"),
    '0': ("01110", "10011", "10101", "10101", "11001", "10001", "01110"),
    '1': ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    '2': ("01110", "10001", "00001", "00010", "00100", "01000", "11111"),
    '3': ("11110", "00001", "00001", "01110", "00001", "00001", "11110"),
    '4': ("00010", "00110", "01010", "10010", "11111", "00010", "00010"),
    '5': ("11111", "10000", "11110", "00001", "00001", "10001", "01110"),
    '6': ("01110", "10000", "10000", "11110", "10001", "10001", "01110"),
    '7': ("11111", "00001", "00010", "00010", "00100", "00100", "00100"),
    '8': ("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
    '9': ("01110", "10001", "10001", "01111", "00001", "00001", "01110"),
    ' ': ("00000", "00000", "00000", "00000", "00000", "00000", "00000"),
    '.': ("00000", "00000", "00000", "00000", "00000", "01100", "01100"),
    ',': ("00000", "00000", "00000", "00000", "01100", "01100", "01000"),
    ':': ("00000", "01100", "01100", "00000", "01100", "01100", "00000"),
    ';': ("00000", "01100", "01100", "00000", "01100", "01100", "01000"),
    "'": ("00100", "00100", "00100", "00000", "00000", "00000", "00000"),
    '!': ("00100", "00100", "00100", "00100", "00100", "00000", "00100"),
    '?': ("01110", "10001", "00001", "00010", "00100", "00000", "00100"),
    '-': ("00000", "00000", "00000", "11111", "00000", "00000", "00000"),
    '(': ("00010", "00100", "01000", "01000", "01000", "00100", "00010"),
    ')': ("01000", "00100", "00010", "00010", "00010", "00100", "01000"),
    '/': ("00001", "00010", "00010", "00100", "01000", "01000", "10000"),
    '%': ("10001", "10010", "00010", "00100", "01000", "01001", "10001"),
    '$': ("00100", "01111", "10100", "01110", "00101", "11110", "00100"),
    '&': ("01100", "10010", "10010", "01000", "10101", "10010", "01101"),
    '+': ("00000", "00100", "00100", "11111", "00100", "00100", "00000"),
    '=': ("00000", "00000", "11111", "00000", "11111", "00000", "00000"),
    '"': ("01010", "01010", "00000", "00000", "00000", "00000", "00000"),
    '_': ("00000", "00000", "00000", "00000", "00000", "00000", "11111"),
    '>': ("10000", "01000", "00100", "00010", "00100", "01000", "10000"),
    '<': ("00001", "00010", "00100", "01000", "00100", "00010", "00001"),
}


def text_w(s, scale):
    return len(s) * 6 * scale - scale


def draw_text(p, x, y, s, scale, c):
    cx = x
    for ch in s:
        g = FONT.get(ch, FONT[' '])
        for r in range(7):
            row = g[r]
            for col in range(5):
                if row[col] == '1':
                    p.rect(cx + col * scale, y + r * scale, scale, scale, c)
        cx += 6 * scale
    return cx


def wrap(text, max_w, scale):
    """Greedy word wrap; returns a list of lines that fit max_w."""
    words = text.split(' ')
    lines = []
    cur = ''
    for word in words:
        trial = word if not cur else cur + ' ' + word
        if text_w(trial, scale) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def center_text(p, y, s, scale, c, x0=0, x1=W):
    w = text_w(s, scale)
    draw_text(p, x0 + (x1 - x0 - w) // 2, y, s, scale, c)


# -------------------------------------------------------------- pictograms
# Small vector icons, one per story, drawn with discs/triangles/lines.
def icon_missile(p, x, y, s, c1, c2):
    # explosion burst behind a missile flying up and to the right
    cx, cy = x + s // 2, y + s // 2
    for k in range(8):
        ang = k * math.pi / 4
        reach = (s // 2 - 2) * (1 if k % 2 == 0 else 0.55)
        ex = int(cx + reach * math.cos(ang))
        ey = int(cy + reach * math.sin(ang))
        p.dotline(cx, cy, ex, ey, c2, 2)
    p.disc(cx, cy, s // 8, GOLD)
    # missile body, nose at top-right, fins at bottom-left
    tipx, tipy = cx + s // 2 - 4, cy - s // 2 + 4
    tailx, taily = cx - s // 4, cy + s // 4
    p.dotline(tailx, taily, tipx, tipy, c1, 5)
    p.tri(tipx, tipy, tipx - 12, tipy + 2, tipx - 2, tipy + 12, c1)
    p.tri(tailx, taily, tailx - 12, taily + 2, tailx - 2, taily - 10, c1)
    p.tri(tailx, taily, tailx + 2, taily + 12, tailx - 10, taily + 2, c1)


def icon_chart(p, x, y, s, c1, c2):
    # axes + falling line + arrowhead
    p.vline(x + 4, y + 4, s - 8, c1, 2)
    p.hline(x + 4, y + s - 5, s - 8, c1, 2)
    pts = [(x + 6, y + 8), (x + s // 3, y + s // 3),
           (x + s // 2, y + s // 4), (x + 2 * s // 3, y + s // 2),
           (x + s - 6, y + s - 8)]
    for a, b in zip(pts, pts[1:]):
        p.dotline(a[0], a[1], b[0], b[1], c2, 2)
    ex, ey = pts[-1]
    p.tri(ex, ey, ex - 8, ey - 1, ex - 1, ey - 8, c2)


def icon_link(p, x, y, s, c1, c2):
    # two interlocked rings (UK + EU)
    r = s // 4
    cx1, cy1 = x + s // 2 - r // 2, y + s // 2
    cx2, cy2 = x + s // 2 + r // 2, y + s // 2
    for cx, cy, c in ((cx1, cy1, c1), (cx2, cy2, c2)):
        p.disc(cx, cy, r, c)
        p.disc(cx, cy, r - 4, PAPER)
    p.disc(cx1, cy1, 3, c1)
    p.disc(cx2, cy2, 3, c2)


def icon_quake(p, x, y, s, c1, c2):
    # seismograph zigzag over a cracked ground line
    pts = [(x + 4, y + s // 2), (x + s // 4, y + s // 2),
           (x + s // 3, y + 6), (x + 2 * s // 5, y + s - 8),
           (x + s // 2, y + s // 3), (x + 3 * s // 5, y + s - 6),
           (x + 2 * s // 3, y + s // 2), (x + s - 5, y + s // 2)]
    for a, b in zip(pts, pts[1:]):
        p.dotline(a[0], a[1], b[0], b[1], c1, 2)
    p.dotline(x + 4, y + s - 5, x + s // 3, y + s - 9, c2, 2)
    p.dotline(x + s // 3, y + s - 9, x + s // 2, y + s - 5, c2, 2)
    p.dotline(x + s // 2, y + s - 5, x + s - 5, y + s - 8, c2, 2)


def icon_tanker(p, x, y, s, c1, c2):
    # ship hull + containers + flame
    p.tri(x + 4, y + 2 * s // 3, x + s - 5, y + 2 * s // 3,
          x + s - 12, y + s - 6, c1)
    p.tri(x + 4, y + 2 * s // 3, x + s - 12, y + s - 6,
          x + 10, y + s - 6, c1)
    p.rect(x + s // 4, y + s // 2 - 6, s // 5, 10, c2)
    p.rect(x + s // 2, y + s // 2 - 6, s // 5, 10, c1)
    # flame above the bow
    fx = x + 3 * s // 4
    p.tri(fx - 6, y + s // 2 - 4, fx + 6, y + s // 2 - 4, fx, y + 6, GOLD)
    p.tri(fx - 3, y + s // 2 - 4, fx + 3, y + s // 2 - 4, fx, y + 16, RED)
    # waves
    p.dotline(x + 4, y + s - 4, x + s // 3, y + s - 7, TEAL, 2)
    p.dotline(x + s // 3, y + s - 7, x + 2 * s // 3, y + s - 4, TEAL, 2)
    p.dotline(x + 2 * s // 3, y + s - 4, x + s - 5, y + s - 7, TEAL, 2)


def icon_parliament(p, x, y, s, c1, c2):
    # pediment + columns + base
    p.tri(x + 4, y + s // 3, x + s - 5, y + s // 3, x + s // 2, y + 4, c1)
    for k in range(3):
        cx = x + s // 4 + k * s // 4
        p.rect(cx - 3, y + s // 3 + 3, 6, s // 3, c1)
    p.rect(x + 6, y + 2 * s // 3 + 2, s - 12, 4, c1)
    p.rect(x + 4, y + 2 * s // 3 + 8, s - 8, 4, c2)
    p.disc(x + s // 2, y + s // 4 + 2, 4, PAPER)


def icon_aid(p, x, y, s, c1, c2):
    # water droplet + cross (aid reaching flooded Gaza)
    cx = x + s // 2
    p.tri(cx - s // 4, y + s // 2, cx + s // 4, y + s // 2, cx, y + 4, c1)
    p.disc(cx, y + s // 2 + 2, s // 4, c1)
    p.rect(cx - 3, y + s // 2 - 2, 6, s // 3, WHITE)
    p.rect(cx - s // 6, y + s // 2 + s // 12 - 3, s // 3, 6, WHITE)
    p.dotline(x + 4, y + s - 5, x + s - 5, y + s - 5, c2, 2)


def icon_chip(p, x, y, s, c1, c2):
    # microchip with pins
    m = 8
    p.rect(x + m, y + m, s - 2 * m, s - 2 * m, c1)
    p.rect(x + m + 6, y + m + 6, s - 2 * m - 12, s - 2 * m - 12, PAPER)
    p.rect(x + m + 11, y + m + 11, s - 2 * m - 22, s - 2 * m - 22, c2)
    for k in range(3):
        off = m + 8 + k * (s - 2 * m - 16) // 2
        p.rect(x + off, y + 1, 3, m - 1, c1)
        p.rect(x + off, y + s - m, 3, m - 1, c1)
        p.rect(x + 1, y + off, m - 1, 3, c1)
        p.rect(x + s - m, y + off, m - 1, 3, c1)


ICONS = {
    'missile': icon_missile,
    'chart': icon_chart,
    'link': icon_link,
    'quake': icon_quake,
    'tanker': icon_tanker,
    'parliament': icon_parliament,
    'aid': icon_aid,
    'chip': icon_chip,
}


# ------------------------------------------------------------------- story
# Verified from live sources on 21 Nov 2026 (see README for sources).
# Nothing here is reused from the 19 or 20 Nov entries.
LEAD = (
    "LEAD - EUROPE",
    "RUSSIAN MISSILES LAND IN POLAND",
    "TWO MISSILES AND A DRONE CAME DOWN IN THE SOUTH-EAST AS NATO ALLIES "
    "DRILLED NEARBY. WARSAW CALLS IT A DELIBERATE PROVOCATION; NATO CALLS "
    "IT A GRAVE VIOLATION AND ITS CHIEF FLIES TO WARSAW TODAY.",
    'missile',
)

GRID = [
    ("MARKETS",
     "S&P 500 SLIPS INTO CORRECTION",
     "US STOCKS FELL 3.7% AS AI SHARES SOLD OFF, PUSHING THE S&P 500 AND "
     "DOW INTO CORRECTION.",
     'chart'),
    ("EUROPE",
     "UK AND EU SEAL FOOD AND YOUTH DEALS",
     "BRITAIN AND THE EU SEALED DEALS IN BRUSSELS ON FOOD TRADE, CARBON "
     "MARKETS AND YOUTH MOBILITY.",
     'link'),
    ("SOUTH AMERICA",
     "6.8 QUAKE SHAKES CENTRAL PERU",
     "A MAGNITUDE 6.8 EARTHQUAKE STRUCK THE ANDEAN REGION OF JUNIN, WITH "
     "TREMORS FELT IN LIMA, 320 KM AWAY.",
     'quake'),
    ("THE GULF",
     "ANOTHER TANKER HIT IN THE STRAIT",
     "A TANKER WAS HIT BY AN UNKNOWN PROJECTILE OFF OMAN AND CAUGHT FIRE, "
     "THE FOURTH NEAR KHASAB IN THREE DAYS.",
     'tanker'),
    ("ISRAEL",
     "EISENKOT VOWS SWIFT NEW GOVERNMENT",
     "EISENKOT, FORMING THE NEXT GOVERNMENT, SAYS TALKS WILL NOT DRAG ON "
     "AND WARNS OF AN EMERGENCY CABINET.",
     'parliament'),
    ("GAZA",
     "FOUR NATIONS URGE AID INTO FLOODED GAZA",
     "AUSTRALIA, CANADA, ITALY AND BRITAIN URGED ISRAEL TO OPEN AID ACCESS "
     "AS FLOODING ADDS TO GAZA'S SUFFERING.",
     'aid'),
]

STRIP = (
    "TECHNOLOGY",
    "US CLEARED 900,000 AI CHIPS FOR CHINA",
    "WASHINGTON APPROVED THE EXPORT OF ALMOST 900,000 ADVANCED AI CHIPS TO "
    "CHINESE FIRMS IN SIX MONTHS, A HOUSE COMMITTEE DISCLOSED.",
    'chip',
)

BRIEFS = [
    "RUSSIAN MILITARY PLANE CRASHES IN SIBERIA; 19 DEAD",
    "FRENCH POLICE CONVICTED OVER 2020 ZECLER BEATING",
    "MAMDANI SETS 2032 TO CLOSE RIKERS ISLAND",
    "RECORD FOREIGN CASH POURS INTO INDIAN SHARES",
]


# ------------------------------------------------------------------ layout
def draw_masthead(p):
    p.rect(0, 0, W, 118, NAVY)
    p.hline(0, 118, W, GOLD, 4)
    center_text(p, 14, "THE WORLD TODAY", 7, WHITE)
    center_text(p, 78, "SATURDAY  -  21 NOVEMBER 2026", 3, GOLD)
    # thin rules flanking the date line
    dw = text_w("SATURDAY  -  21 NOVEMBER 2026", 3)
    x0 = (W - dw) // 2
    p.hline(24, 88, x0 - 40, RULE, 1)
    p.hline(W - 24 - (x0 - 40), 88, x0 - 40, RULE, 1)


def draw_lead(p, x, y, w, h):
    p.rect(x, y, w, h, CREAM)
    p.hline(x, y, w, RED, 4)
    kicker, headline, deck, icon = LEAD
    draw_text(p, x + 18, y + 16, kicker, 2, RED)
    # headline, two lines, scale 4
    lines = wrap(headline, w - 320, 4)
    hy = y + 44
    for ln in lines:
        draw_text(p, x + 18, hy, ln, 4, INK)
        hy += 32
    # deck, scale 2
    dy = hy + 8
    for ln in wrap(deck, w - 320, 2):
        draw_text(p, x + 18, dy, ln, 2, INK)
        dy += 17
    # pictogram on the right
    ix = x + w - 300
    iy = y + 18
    p.rect(ix, iy, 282, h - 36, PAPER)
    p.rect(ix, iy, 282, 3, GOLD)
    ICONS[icon](p, ix + 66, iy + 18, 150, NAVY, RED)


def draw_cell(p, x, y, w, h, story):
    kicker, headline, deck, icon = story
    p.rect(x, y, w, h, PAPER)
    p.hline(x, y, w, NAVY, 3)
    draw_text(p, x + 14, y + 12, kicker, 2, RED)
    # icon top-right; keep the headline clear of it
    ICONS[icon](p, x + w - 62, y + 10, 48, NAVY, TEAL)
    # headline, scale 3, two lines (width leaves room for the icon)
    hy = y + 40
    for ln in wrap(headline, w - 28 - 64, 3):
        draw_text(p, x + 14, hy, ln, 3, INK)
        hy += 24
    # deck, scale 2, three lines
    dy = hy + 6
    for ln in wrap(deck, w - 28, 2):
        draw_text(p, x + 14, dy, ln, 2, INK)
        dy += 17


def draw_strip(p, x, y, w, h):
    p.rect(x, y, w, h, NAVY)
    kicker, headline, deck, icon = STRIP
    # left: the 8th story
    draw_text(p, x + 16, y + 14, kicker, 2, GOLD)
    hy = y + 40
    for ln in wrap(headline, w - 540, 3):
        draw_text(p, x + 16, hy, ln, 3, WHITE)
        hy += 24
    dy = hy + 6
    for ln in wrap(deck, w - 540, 2):
        draw_text(p, x + 16, dy, ln, 2, (220, 220, 210))
        dy += 17
    ICONS[icon](p, x + w - 470, y + 34, 72, GOLD, RED)
    # divider + IN BRIEF on the right
    bx = x + w - 380
    p.vline(bx, y + 14, h - 28, RULE, 1)
    draw_text(p, bx + 16, y + 14, "IN BRIEF", 2, GOLD)
    by = y + 42
    for b in BRIEFS:
        for ln in wrap(b, 348, 2):
            draw_text(p, bx + 16, by, ln, 2, WHITE)
            by += 15
        by += 4


def draw_footer(p, y):
    center_text(p, y, "SOURCES: AP / REUTERS / UKMTO / PERU GEOPHYSICAL "
                       "INSTITUTE / AL JAZEERA", 1, SOFT)
    center_text(p, y + 12, "DRAWN BY A DETERMINISTIC PROGRAM - NO "
                           "PHOTOGRAPHS - THE WORLD TODAY, 21 NOVEMBER 2026",
                1, SOFT)


def build():
    p = Page(W, H, PAPER)
    draw_masthead(p)
    # lead: full width, y 132..352
    draw_lead(p, 24, 132, W - 48, 216)
    # grid: 2 cols x 3 rows, y 362..800
    gx, gy = 24, 362
    cw = (W - 48 - 16) // 2
    ch = 142
    for i, story in enumerate(GRID):
        cx = gx + (i % 2) * (cw + 16)
        cy = gy + (i // 2) * (ch + 6)
        draw_cell(p, cx, cy, cw, ch, story)
    # strip: y 808..984, footer below
    draw_strip(p, 24, 808, W - 48, 176)
    draw_footer(p, 996)
    return p


# --------------------------------------------------------------------- png
def chunk(typ, data):
    out = struct.pack(">I", len(data)) + typ + data
    out += struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)
    return out


def encode_png(p):
    raw = bytearray()
    for yy in range(p.h):
        raw.append(0)  # filter: none
        raw += p.pix[yy * p.w * 3:(yy + 1) * p.w * 3]
    ihdr = struct.pack(">IIBBBBB", p.w, p.h, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) +
            chunk(b"IDAT", zlib.compress(bytes(raw), 9)) +
            chunk(b"IEND", b""))


def main():
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR") or "/output"
    try:
        os.makedirs(out_dir, exist_ok=True)
    except OSError:
        out_dir = "out"
        os.makedirs(out_dir, exist_ok=True)
    data = encode_png(build())
    with open(os.path.join(out_dir, "entry.png"), "wb") as f:
        f.write(data)


if __name__ == "__main__":
    main()
