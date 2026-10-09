"""Game Boy / Game Boy Color / Game Boy Advance support for add_games.py.

Games are identified by CRC32 against libretro's No-Intro checksum lists, cheats come
from libretro's .cht files, and are written as mGBA .cheats files (which mGBA loads
automatically from next to the game). Box art comes from libretro-thumbnails.
"""
import os, re, urllib.parse, urllib.request, zlib

SYSTEMS = {  # extension -> (folder, libretro system name)
    ".gba": ("GBA", "Nintendo - Game Boy Advance"),
    ".gbc": ("GBC", "Nintendo - Game Boy Color"),
    ".gb": ("GB", "Nintendo - Game Boy"),
}
LIBRETRO_DB = os.path.join(os.path.expanduser("~"), "Games", "cheat-tools", "libretro-database")


def system_for(path):
    return SYSTEMS.get(os.path.splitext(path)[1].lower())


def rom_crc(data):
    return f"{zlib.crc32(data) & 0xffffffff:08X}"


_dat_cache = {}

def nointro_names(system):
    """crc -> official No-Intro name, from libretro's checksum list."""
    if system not in _dat_cache:
        names, cur = {}, None
        path = os.path.join(LIBRETRO_DB, "metadat", "no-intro", system + ".dat")
        if os.path.exists(path):
            for line in open(path, encoding="utf-8", errors="replace"):
                m = re.match(r'\s*name "(.*)"\s*$', line)
                if m:
                    cur = m.group(1)
                m = re.search(r"\bcrc ([0-9A-Fa-f]{8})\b", line)
                if m and cur:
                    names[m.group(1).upper()] = cur
        _dat_cache[system] = names
    return _dat_cache[system]


def norm_title(name):
    """'Mario & Luigi - Superstar Saga (USA)' and 'Mario _ Luigi - Superstar Saga (USA, Europe) (Code Breaker)'
    both become 'marioluigisuperstarsaga' (libretro names vary in punctuation and spacing)."""
    t = re.sub(r"\s*\([^)]*\)", "", name)
    t = re.sub(r"^(.*?), The\b", r"The \1", t)
    return re.sub(r"[^a-z0-9]", "", t.lower())


def find_cheat_files(system, nointro, fallback_name):
    d = os.path.join(LIBRETRO_DB, "cht", system)
    if not os.path.isdir(d):
        return []
    want = norm_title(nointro or fallback_name)
    cands = [f for f in sorted(os.listdir(d)) if f.endswith(".cht") and norm_title(f[:-4]) == want]
    region = re.search(r"\(([^)]*)\)", nointro or "")
    same = [f for f in cands if region and f"({region.group(1)})" in f]
    return [os.path.join(d, f) for f in (same or cands)]


def parse_cht(path):
    """libretro .cht -> list of (description, [code tokens])."""
    txt = open(path, encoding="utf-8", errors="replace").read()
    desc = dict(re.findall(r'^cheat(\d+)_desc\s*=\s*"(.*)"\s*$', txt, re.M))
    code = dict(re.findall(r'^cheat(\d+)_code\s*=\s*"(.*)"\s*$', txt, re.M))
    out = []
    for i in sorted(code, key=int):
        toks = [t for t in re.split(r"[+\s]+", code[i].strip()) if t]
        if toks:
            out.append((desc.get(i, f"Cheat {i}").strip() or f"Cheat {i}", toks))
    return out


def code_lines(toks):
    """Group tokens into mGBA lines: 8+8 / 8+4 hex pairs, otherwise one per line."""
    lines, i = [], 0
    while i < len(toks):
        a = toks[i]
        b = toks[i + 1] if i + 1 < len(toks) else None
        if re.fullmatch(r"[0-9A-Fa-f]{8}", a) and b and re.fullmatch(r"[0-9A-Fa-f]{4}|[0-9A-Fa-f]{8}", b):
            lines.append(f"{a.upper()} {b.upper()}")
            i += 2
        else:
            lines.append(a.upper())
            i += 1
    return lines


def device_of(path):
    m = re.search(r"\((Code Breaker|GameShark|Action Replay|Game Genie|Xploder)[^)]*\)\.cht$", path, re.I)
    return m.group(1) if m else ""


def write_mgba_cheats(path, cheats, fav_idx):
    """cheats: list of (name, device, lines). Favorites get a ★ prefix (the launcher groups them)."""
    out = []
    for i, (name, device, lines) in enumerate(cheats):
        label = name + (f" [{device}]" if device and len({c[1] for c in cheats}) > 1 else "")
        if i in fav_idx:
            label = "★ " + label
        out += ["!disabled", f"# {label}"] + lines + [""]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out))


def boxart(system, nointro, dest_png):
    """Download box art once (needs internet at import time); quietly skip if unavailable."""
    if not nointro:
        return False
    repo = system.replace(" ", "_")
    fname = re.sub(r"[&*/:`<>?\\|]", "_", nointro) + ".png"
    url = f"https://raw.githubusercontent.com/libretro-thumbnails/{repo}/master/Named_Boxarts/{urllib.parse.quote(fname)}"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            data = r.read()
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            open(dest_png, "wb").write(data)
            return True
    except Exception:
        pass
    return False
