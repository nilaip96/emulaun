#!/usr/bin/env python3
"""Build a fake game library for README screenshots (no real games or Nintendo art).

usage: python3 docs/make_demo.py <out-dir>
Writes tiny placeholder .nds files (just a header + banner with a generated
pixel-art icon and a made-up title), plus a few saves and a demo cheat list.
Then:  DS_GAMES_DIR=<out-dir> DS_PORT=8766 DS_MELON_CONFIG=<out-dir>/melonDS-demo.toml python3 launcher/launcher.py
"""
import colorsys, math, os, struct, sys, time

OUT = sys.argv[1] if len(sys.argv) > 1 else "demo-games"

GAMES = [  # (title, hue, shape, folder, played_minutes_ago)
    ("Star Courier", 0.62, "star", "DS", 5),
    ("Lava Kart Grand Prix", 0.02, "ring", "DS", 90),
    ("Mossy Mountain Quest", 0.33, "tri", "DS", 600),
    ("Neon Drift", 0.83, "diamond", "DS", None),
    ("Pixel Pirates", 0.55, "ring", "DS", None),
    ("Sunflower Farm Days", 0.14, "dot", "DS", 2000),
    ("Crystal Caverns", 0.5, "diamond", "DS", None),
    ("Monster Pals: Ember", 0.06, "dot", "Pokemon", None),
    ("Monster Pals: Tide", 0.58, "dot", "Pokemon", 30),
    ("Robo Rumble", 0.0, "square", "DS", None),
    ("Moonlit Detective", 0.72, "star", "DS", None),
    ("Bubble Bounce", 0.9, "ring", "DS", None),
    ("Forest Spirits", 0.38, "star", "DS", None),
    ("Desert Racer DX", 0.1, "tri", "DS", None),
    ("Galaxy Golf", 0.67, "dot", "DS", None),
    ("Ice Castle Tactics", 0.53, "square", "DS", None),
]


def bgr555(r, g, b):
    return (r >> 3) | (g >> 3) << 5 | (b >> 3) << 10


def icon(hue, shape):
    """32x32, 16-color palette: 0 transparent, 1-6 background ramp, 7-11 shape ramp, 12 outline, 13 white."""
    pal = [(0, 0, 0)]
    for i in range(6):
        r, g, b = colorsys.hls_to_rgb(hue, 0.16 + i * 0.05, 0.55)
        pal.append((int(r * 255), int(g * 255), int(b * 255)))
    sh = (hue + 0.5) % 1 if shape in ("ring", "dot") else (hue + 0.08) % 1
    for i in range(5):
        r, g, b = colorsys.hls_to_rgb(sh, 0.5 + i * 0.08, 0.9)
        pal.append((int(r * 255), int(g * 255), int(b * 255)))
    pal += [(20, 20, 28), (255, 255, 255)]
    pal += [(0, 0, 0)] * (16 - len(pal))

    px = [[0] * 32 for _ in range(32)]
    for y in range(32):
        for x in range(32):
            if 2 <= x <= 29 and 2 <= y <= 29 and not ((x in (2, 29)) and (y in (2, 29))):
                px[y][x] = 1 + min(5, (29 - y) // 5)

    def inside(x, y):
        cx, cy = x - 15.5, y - 15.5
        if shape == "dot":
            return cx * cx + cy * cy <= 90
        if shape == "ring":
            d = cx * cx + cy * cy
            return 40 <= d <= 110
        if shape == "diamond":
            return abs(cx) + abs(cy) <= 11
        if shape == "square":
            return abs(cx) <= 8 and abs(cy) <= 8
        if shape == "tri":
            return -9 <= cy <= 9 and abs(cx) <= (cy + 9) * 0.6
        a = math.atan2(cy, cx)  # star
        r = 11 * (0.55 + 0.45 * abs(math.cos(2.5 * a)))
        return cx * cx + cy * cy <= r * r

    mask = [[inside(x, y) for x in range(32)] for y in range(32)]
    for y in range(32):
        for x in range(32):
            if mask[y][x]:
                px[y][x] = 7 + min(4, (y * 5) // 32)
            elif any(0 <= y + dy < 32 and 0 <= x + dx < 32 and mask[y + dy][x + dx]
                     for dy in (-1, 0, 1) for dx in (-1, 0, 1)):
                px[y][x] = 12
    for y, x in ((10, 12), (11, 12), (10, 13)):  # tiny highlight
        if mask[y][x]:
            px[y][x] = 13

    bitmap = bytearray()
    for ty in range(4):
        for tx in range(4):
            for y in range(8):
                for x in range(0, 8, 2):
                    a, b = px[ty * 8 + y][tx * 8 + x], px[ty * 8 + y][tx * 8 + x + 1]
                    bitmap.append(a | b << 4)
    palette = b"".join(struct.pack("<H", bgr555(*c)) for c in pal)
    return bytes(bitmap), palette


def rom(title, code, hue, shape):
    header = bytearray(0x200)
    header[0:12] = title.upper().encode("ascii", "ignore")[:12].ljust(12, b"\0")
    header[12:16] = code.encode()
    struct.pack_into("<I", header, 0x68, 0x200)
    banner = bytearray(0x840)
    struct.pack_into("<H", banner, 0, 1)
    bm, pal = icon(hue, shape)
    banner[0x20:0x220] = bm
    banner[0x220:0x240] = pal
    t = (title + "\nDemo Studio").encode("utf-16-le")[:0x100]
    for off in range(0x240, 0x840, 0x100):
        banner[off:off + len(t)] = t
    return bytes(header) + bytes(banner) + bytes(0x10000)


CHEATS = """CAT 0 *** FAVORITES - start here (all off; tick what you want) ***
DESC Demo cheat list.

CODE 1 Infinite health
DESC Always on while ticked.
02000000 00000000

CODE 1 Max money  [Select = Shift]
DESC Press Select in the overworld.
02000004 00000000

CODE 0 Walk through walls  [R+B = E + A / L+B = Q + A]
DESC Press R+B to turn ON, L+B to turn OFF.
02000008 00000000

CODE 0 Moon jump  [B = A]
DESC Hold B to keep rising.
0200000C 00000000

CODE 0 All items x99  [Select+Up = Shift + Up arrow]
DESC Press Select+Up in the overworld.
02000010 00000000

CAT 1 Experience Multiplier
DESC Pick one.

CODE 0 x2
02000014 00000000

CODE 0 x8
02000018 00000000

CAT 0 Unlock Codes

CODE 0 Unlock all levels
0200001C 00000000

CODE 0 Unlock all characters
02000020 00000000
"""

now = time.time()
for i, (title, hue, shape, folder, ago) in enumerate(GAMES):
    d = os.path.join(OUT, folder)
    os.makedirs(d, exist_ok=True)
    base = os.path.join(d, title.replace(":", " -"))
    with open(base + ".nds", "wb") as f:
        f.write(rom(title, f"D{i:02d}E", hue, shape))
    with open(base + ".mch", "w") as f:
        f.write(CHEATS if i == 0 else CHEATS.replace("CODE 1", "CODE 0"))
    if ago is not None:
        for ext in (".sav", ".ml1") if i == 0 else (".sav",):
            p = base + ext
            open(p, "wb").write(b"\0" * 16)
            t = now - ago * 60 - (0 if ext == ".sav" else 300)
            os.utime(p, (t, t))
with open(os.path.join(OUT, "melonDS-demo.toml"), "w") as f:  # so the demo shows cheats switched on
    f.write("[Instance0]\nEnableCheats = true\n")
print(f"demo library with {len(GAMES)} games in {OUT}")
