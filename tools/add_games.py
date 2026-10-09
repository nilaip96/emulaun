#!/usr/bin/env python3
"""Import new games from ~/Downloads into the repo's games/ folder and install their cheats.

Systems: Nintendo DS (.nds -> games/DS, played in melonDS) and Game Boy / Color /
Advance (.gb .gbc .gba -> games/GB, GBC, GBA, played in mGBA).

usage:  python3 add_games.py            (do it)
        python3 add_games.py --dry-run  (just show what would happen)

For each game file in Downloads, or .zip / .7z containing one:
  * skip it if that exact game is already in games/
  * copy it into its system's folder
  * DS: match the offline cheat database (cheats.xml) by game ID + header checksum and
    write <game>.mch (melonDS cheat file: auto-picked Favorites + every code, all off)
  * GB/GBC/GBA: identify it by CRC32 (No-Intro list), write <game>.cheats from libretro's
    cheat files (mGBA format, all off, favorites marked with a star) and save box art
  * write "<game> - Cheat Guide.txt"
The original files in Downloads are left untouched.
"""
import os, re, shutil, subprocess, sys, tempfile, zipfile, zlib
import xml.etree.ElementTree as ET
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gameboy

HOME = os.path.expanduser("~")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAMES = os.path.join(REPO, "games")
DOWNLOADS = os.path.join(HOME, "Downloads")
HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.environ.get("DS_CHEAT_DB", os.path.join(REPO, "data", "cheats.xml"))
DRY = "--dry-run" in sys.argv

SHOW_GAMES = GAMES.replace(HOME, "~", 1)
GAME_EXTS = (".nds", ".gba", ".gbc", ".gb")
KEYS = "D-Pad = arrow keys    A = D    B = A    X = W    Y = S\n  L = Q    R = E    Start = Return    Select = Shift"


# ---------- helpers ----------

def header_key(head):
    gid = head[12:16].decode("ascii", "replace")
    c = zlib.crc32(head[:512]) & 0xffffffff
    return gid, {f"{c:08X}", f"{c ^ 0xffffffff:08X}"}


def existing_games():
    keys = set()
    for folder in ("DS", "GBA", "GBC", "GB"):
        d = os.path.join(GAMES, folder)
        for f in os.listdir(d) if os.path.isdir(d) else []:
            fp = os.path.join(d, f)
            if f.lower().endswith(".nds"):
                with open(fp, "rb") as fh:
                    gid, crcs = header_key(fh.read(512))
                keys.add((gid, min(crcs)))
            elif gameboy.system_for(f):
                keys.add(("CRC", gameboy.rom_crc(open(fp, "rb").read())))
    return keys


def clean_name(fname):
    n = os.path.splitext(os.path.basename(fname))[0]
    n = re.sub(r"^\d{3,5}\s*-\s*", "", n)          # "4840 - Pokemon ..." release numbers
    n = re.sub(r"\s*[\(\[][^\)\]]*[\)\]]", "", n)   # (USA) (En,Fr) (Rev 1) [!] ...
    n = re.sub(r"^(.*?), The\b", r"The \1", n)      # "Legend of Zelda, The - X" -> "The Legend of Zelda - X"
    n = n.replace("_", " ").replace(":", " -")
    n = re.sub(r"[/\\]", "-", n)
    return re.sub(r"\s+", " ", n).strip(" .-")


def archive_members(path):
    if path.lower().endswith(GAME_EXTS):
        return [os.path.basename(path)]
    if path.lower().endswith(".zip"):
        try:
            with zipfile.ZipFile(path) as z:
                names = z.namelist()
        except (zipfile.BadZipFile, OSError):
            return []
    else:
        names = subprocess.run(["tar", "-tf", path], capture_output=True, text=True).stdout.splitlines()
    return [m for m in names if m.lower().endswith(GAME_EXTS)]


def read_head(path, member, size=512):
    if path.lower().endswith(GAME_EXTS):
        with open(path, "rb") as f:
            return f.read(size) if size else f.read()
    if path.lower().endswith(".zip"):
        with zipfile.ZipFile(path) as z, z.open(member) as f:
            return f.read(size) if size else f.read()
    p = subprocess.Popen(["tar", "-xOf", path, member], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    head = p.stdout.read(size) if size else p.stdout.read()
    p.kill(); p.wait()
    return head


def extract(path, member, dest_dir):
    if path.lower().endswith(GAME_EXTS):  # loose file: copy, never move the original
        out = os.path.join(dest_dir, os.path.basename(path))
        shutil.copy2(path, out)
        return out
    if path.lower().endswith(".zip"):
        out = os.path.join(dest_dir, os.path.basename(member))
        with zipfile.ZipFile(path) as z, z.open(member) as src, open(out, "wb") as dst:
            shutil.copyfileobj(src, dst, 1 << 20)
        return out
    else:
        subprocess.run(["tar", "-xf", path, "-C", dest_dir, member], check=True)
    out = os.path.join(dest_dir, os.path.basename(member))
    if not os.path.exists(out):  # tar keeps sub-paths
        out = os.path.join(dest_dir, member)
    return out


# ---------- cheat database ----------

def load_db():
    root = ET.parse(DB).getroot()
    db = {}
    for g in root.findall("game"):
        gid = (g.findtext("gameid") or "").split()
        if len(gid) == 2:
            db.setdefault(gid[0], []).append((gid[1], g))
    return db


def cheat(c):
    return {"name": (c.findtext("name") or "").strip(), "note": (c.findtext("note") or "").strip(),
            "codes": (c.findtext("codes") or "").split()}


def game_cats(g):
    cats = []
    top = [cheat(c) for c in g.findall("cheat")]
    if top:
        cats.append({"name": "General", "onlyone": False, "note": "", "cheats": top})
    for f in g.findall("folder"):
        cats.append({"name": (f.findtext("name") or "").strip() or "Misc",
                     "onlyone": (f.findtext("allowedon") or "0").strip() == "1",
                     "note": (f.findtext("note") or "").strip(),
                     "cheats": [cheat(c) for c in f.findall("cheat")]})
    for c in cats:
        c["cheats"] = [ch for ch in c["cheats"] if ch["codes"] and len(ch["codes"]) % 2 == 0]
    return [c for c in cats if c["cheats"]]


# ---------- auto favorites ----------

GOOD = [  # (regex, score) - matched against "category / cheat name / note"
    (r"walk(ing)? through walls", 9), (r"moon ?jump", 8),
    (r"invincib|invulnerab|god ?mode|never die|disable death|can'?t die", 9),
    (r"(infinite|max|unlimited).{0,25}(health|hp\b|life|lives|hearts|energy)", 10),
    (r"(infinite|max|unlimited).{0,25}(money|coins?|cash|gold|rupees|gil|zenny|bells|rings|points|gems)", 9),
    (r"(infinite|max|unlimited).{0,25}(ammo|bullets|grenades|arrows|bombs|items|magic|mp\b|pp\b|time|stars|tickets)", 7),
    (r"unlock (all|every)|all (levels|stages|worlds|characters|chapters|cups|tracks|courses|songs|cards|weapons|items|missions|minigames|mini-games)", 8),
    (r"(have|get) all", 6),
    (r"\bx(4|8)\b.*", 5), (r"(exp|experience)", 4), (r"level 99|level 100|max level", 6),
    (r"one hit kill|1 hit kill|instant kill", 5), (r"fast|speed", 2),
    (r"never decrease|never (run|go) (out|down)|doesn'?t decrease|don'?t decrease|never lose", 7),
    (r"\bunlock", 6), (r"all medals|all (gold )?trophies|all stars", 5),
    (r"(max|infinite).{0,20}(munny|bells|nook points|cash|zenny|sp\b|score)", 7), (r"max stats|perfect stats", 3),
    (r"free|cost(s)? 1 |only cost", 5), (r"save anywhere|never get resetti|restock|drop rate|cool ?down", 5),
    (r"quick level up|level up", 5), (r"never reload|rarely shoots", 5), (r"refill (hp|health)", 6),
]
BAD = r"wi-?fi|wfc|online|backlight|debug|crash|anti-?piracy|no\$gba|must be on|master code|enable code|toolkit|camera|widescreen|" \
      r"language|test|beta|unused|glitch|corrupt|mess up|overwrite|freeze|joker|e3 |region|swap|disable sound|music|enemy|enemies|cpu|opponent|" \
      r"\b(1/2|half) speed|slow|0 (hp|health)|zero"


def is_multiplier(c):
    return c["onlyone"] and re.search(r"exp|experience", c["name"], re.I)


def fav_label(c, ch):
    """Short names like 'x4' or '8' only make sense next to their folder name."""
    if len(ch["name"]) <= 6 or re.fullmatch(r"[x×]?[\d,.]+", ch["name"].strip(), re.I):
        return f"{c['name']}: {ch['name']}"
    return ch["name"]


def pick_favorites(cats, limit=12):
    scored, seen = [], set()
    for ci, c in enumerate(cats):
        for chi, ch in enumerate(c["cheats"]):
            text = f"{c['name']} / {ch['name']} / {ch['note']}".lower()
            if re.search(BAD, text) or "warning" in (ch["note"] + c["note"]).lower():
                continue
            s = sum(w for rx, w in GOOD if re.search(rx, text))
            if is_multiplier(c):
                s = 7 if re.fullmatch(r"x?8|x?4", ch["name"].strip(), re.I) else 0
            elif c["onlyone"]:
                s -= 1
            if s >= 5:
                scored.append((s, ci, chi))
    scored.sort(key=lambda t: (-t[0], t[1], t[2]))
    out, used_onlyone, per_cat = [], set(), {}
    for s, ci, chi in scored:
        c, ch = cats[ci], cats[ci]["cheats"][chi]
        key = re.sub(r"\b(v\d+(\.\d+)?|\(.*?\))", "", ch["name"].lower()).strip()
        # "kind" groups look-alike codes: "All Medals: Mario/Luigi/...", "AK-47/M4/... Max/Perfect Stats"
        name = re.sub(r"\s*[\(\[][^)\]]*[\)\]]", "", ch["name"].lower())  # "Gold (Cute)" ~ "Gold (Cool)"
        kind = (ci, name.split(":", 1)[0] if ":" in name else name if len(name.split()) > 3 else re.sub(r"^\S+\s*", "", name))
        if key in seen or (c["onlyone"] and ci in used_onlyone) or per_cat.get(ci, 0) >= 6 or per_cat.get(kind, 0) >= 2:
            continue
        per_cat[ci] = per_cat.get(ci, 0) + 1
        per_cat[kind] = per_cat.get(kind, 0) + 1
        seen.add(key)
        if c["onlyone"]:
            used_onlyone.add(ci)
        out.append((ci, chi))
        if len(out) >= limit:
            break
    return sorted(out)


def how_to(ch):
    m = re.search(r"\((?:press|hold)[^)]*\)", ch["name"] + " " + ch["note"], re.I)
    if m:
        return ch["note"] or m.group(0).strip("()")
    if re.search(r"\bpress|\bhold", ch["note"], re.I):
        return ch["note"]
    return ("Always on while ticked. " + ch["note"]).strip()


# ---------- writers ----------

def clean(s, n):
    return re.sub(r"\s+", " ", s).strip()[:n]


def lines(codes):
    return [f"{codes[i].upper()} {codes[i+1].upper()}" for i in range(0, len(codes), 2)]


def write_mch(path, cats, favs):
    m = ["CAT 0 *** FAVORITES - start here (all off; tick what you want) ***",
         "DESC Auto-picked from the cheat database. Button combos use DS buttons - see the cheat guide for your keys.", ""]
    for ci, chi in favs:
        ch = cats[ci]["cheats"][chi]
        m += [f"CODE 0 {clean(fav_label(cats[ci], ch), 127)}", f"DESC {clean(how_to(ch) + ' [folder: ' + cats[ci]['name'] + ']', 255)}"] + lines(ch["codes"]) + [""]
    for c in cats:
        m.append(f"CAT {1 if c['onlyone'] else 0} {clean(c['name'], 127)}")
        if c["note"]:
            m.append(f"DESC {clean(c['note'], 255)}")
        m.append("")
        for ch in c["cheats"]:
            m.append(f"CODE 0 {clean(ch['name'] or 'Unnamed', 127)}")
            if ch["note"]:
                m.append(f"DESC {clean(ch['note'], 255)}")
            m += lines(ch["codes"]) + [""]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(m) + "\n")


def write_guide(path, title, rom_rel, cats, favs, exact, system="DS"):
    total = sum(len(c["cheats"]) for c in cats)
    required = [ch["name"] for c in cats for ch in c["cheats"]
                if re.search(r"must be on|master code|enable code", ch["name"], re.I)]
    g = [f"{title.upper()} - CHEAT GUIDE", "=" * (len(title) + 14), "",
         "Everything here works fully offline. No internet needed.", "",
         "HOW TO USE"] + ([
         "  1. Open EmuLaun (Dock) and click this game, or in melonDS use",
         f"     File > Open ROM... > {SHOW_GAMES}/{rom_rel}",
         "  2. Make sure the 'Cheats' switch in the game's EmuLaun panel is ON",
         "     (or System > Enable cheats in melonDS).",
         "  3. Tick cheats in EmuLaun (applies next time you start the game), or",
         "     in melonDS: System > Setup cheat codes (applies right away).",
         "  4. 'Always on' cheats just work. Others need the button combo shown -",
         "     press all the buttons at the same time.", ""] if system == "DS" else [
         "  1. Open EmuLaun (Dock) and click this game - it opens in mGBA. Or in mGBA:",
         f"     File > Load ROM... > {SHOW_GAMES}/{rom_rel}",
         "  2. Tick cheats in EmuLaun (applies next time you start the game), or",
         "     in mGBA: Tools > Cheats... (applies right away).",
         "  3. If a 'Master Code' is listed, tick it too - many codes need it.", ""]) + [
         "YOUR CONTROLS (DS button = keyboard key)",
         "  " + KEYS,
         "  Hold Tab = fast-forward   Shift+F1..F8 = save state   F1..F8 = load state", ""]
    if not exact:
        g += ["NOTE: no exact match for this exact game file in the database - these",
              "codes are for the same game ID and should work, but some may not.", ""]
    g += ["-" * 70, "FAVORITES (auto-picked - the first folder in the cheat list)", "-" * 70]
    if favs:
        for i, (ci, chi) in enumerate(favs, 1):
            ch = cats[ci]["cheats"][chi]
            g += [f"{i:2}. {fav_label(cats[ci], ch)}", f"    How: {how_to(ch)}", f"    Folder: {cats[ci]['name']}"]
    else:
        g.append("  (none picked automatically - browse the folders below)")
    g += ["", "-" * 70, "TIPS", "-" * 70,
          "  * Make a save state (Shift+F1) before trying new cheats; F1 jumps back.",
          "  * If the game glitches, untick the last cheat you added and reload.",
          "  * Cheats that change game code keep working until the game restarts -",
          "    untick, save in-game, then System > Reset in melonDS.",
          "  * If a cheat has v1/v2 versions, try v1 first, then v2.",
          "  * Folders marked 'pick one' only allow one code at a time."]
    if required:
        g += [f"  * This game's database has: {', '.join(sorted(set(required)))}.",
              "    It's meant for flashcarts - leave it off unless cheats don't work."]
    g += ["", "-" * 70, f"ALL {total} CHEATS, BY FOLDER", "-" * 70]
    for c in cats:
        g.append(f"\n[{c['name']}]  {len(c['cheats'])} codes" + ("  (pick one)" if c["onlyone"] else ""))
        if c["note"]:
            g.append(f"   note: {clean(c['note'], 300)}")
        if len(c["cheats"]) > 60:
            g.append("   (long list - browse it in EmuLaun)")
            continue
        for ch in c["cheats"]:
            g.append(f"   - {ch['name']}" + (f" - {clean(ch['note'], 200)}" if ch["note"] else ""))
    g += ["", "Codes from DeadSkullzJr's NDS(i) Cheat Database (2021-12-25)."]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(g) + "\n")


def import_gameboy(ap, archive_name, member, have, report, tmp):
    folder, system = gameboy.system_for(member)
    data = read_head(ap, member, size=0)
    if len(data) < 0x150:
        report.append(("FAILED", archive_name, "could not read"))
        return
    crc = gameboy.rom_crc(data)
    if ("CRC", crc) in have:
        return
    have.add(("CRC", crc))
    nointro = gameboy.nointro_names(system).get(crc)
    name = clean_name(nointro or member)
    ext = os.path.splitext(member)[1].lower()
    dest = os.path.join(GAMES, folder, name + ext)
    if os.path.exists(dest):
        name += f" ({crc})"
        dest = os.path.join(GAMES, folder, name + ext)
    cheats = []
    for f in gameboy.find_cheat_files(system, nointro, name):
        dev = gameboy.device_of(f)
        cheats += [(d, dev, gameboy.code_lines(t)) for d, t in gameboy.parse_cht(f)]
    cats = [{"name": "Cheats", "onlyone": False, "note": "",
             "cheats": [{"name": n + (f" [{d}]" if d else ""), "note": "", "codes": ["x"] * 2} for n, d, _ in cheats]}]
    favs = {chi for _, chi in pick_favorites(cats)} if cheats else set()
    favs |= {i for i, (n, _, _) in enumerate(cheats) if re.search(r"master code|\(m\)|must be on", n, re.I)}
    status = ("matched" if nointro else "unknown dump") + (", no cheats in database" if not cheats else "")
    report.append((name, folder, f"{len(cheats)} cheats, {len(favs)} favorites ({status})"))
    if DRY:
        return
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "wb") as f:
        f.write(data)
    base = os.path.splitext(dest)[0]
    if cheats:
        gameboy.write_mgba_cheats(base + ".cheats", cheats, favs)
        guide_cats = [{"name": "Cheats", "onlyone": False, "note": "",
                       "cheats": [{"name": n + (f" [{d}]" if d else ""), "note": "", "codes": []} for n, d, _ in cheats]}]
        write_guide(base + " - Cheat Guide.txt", re.sub(r"\s*\([^)]*\)", "", nointro or name).strip(),
                    f"{folder}/{name}{ext}", guide_cats, sorted((0, i) for i in favs), bool(nointro), system="GB")
    gameboy.boxart(system, nointro, base + ".png")


# ---------- main ----------

def main():
    have = existing_games()
    db = load_db()
    archives = sorted(f for f in os.listdir(DOWNLOADS) if f.lower().endswith((".zip", ".7z") + GAME_EXTS))
    report = []
    with tempfile.TemporaryDirectory() as tmp:
        for a in archives:
            ap = os.path.join(DOWNLOADS, a)
            for member in archive_members(ap):
                if gameboy.system_for(member):
                    import_gameboy(ap, a, member, have, report, tmp)
                    continue
                head = read_head(ap, member)
                if len(head) < 512:
                    report.append(("FAILED", a, "could not read"))
                    continue
                gid, crcs = header_key(head)
                if (gid, min(crcs)) in have:
                    continue
                name = clean_name(member)
                folder = "DS"
                dest = os.path.join(GAMES, folder, name + ".nds")
                if os.path.exists(dest):
                    name += f" ({gid})"
                    dest = os.path.join(GAMES, folder, name + ".nds")
                entries = db.get(gid, [])
                exact = [g for crc, g in entries if crc in crcs]
                entry = exact[0] if exact else (entries[0][1] if entries else None)
                cats = game_cats(entry) if entry is not None else []
                favs = pick_favorites(cats) if cats else []
                title = (entry.findtext("name") if entry is not None else None) or name
                title = re.sub(r"\s*\([^)]*\)", "", title).strip()
                status = "exact" if exact else ("same game ID" if entries else "NO CHEATS IN DATABASE")
                report.append((name, folder, f"{sum(len(c['cheats']) for c in cats)} cheats, {len(favs)} favorites ({status})"))
                have.add((gid, min(crcs)))
                if DRY:
                    continue
                try:
                    rom = extract(ap, member, tempfile.mkdtemp(dir=tmp))
                except subprocess.CalledProcessError:
                    report[-1] = ("FAILED", a, "could not extract")
                    continue
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                shutil.move(rom, dest)
                base = os.path.splitext(dest)[0]
                if cats:
                    write_mch(base + ".mch", cats, favs)
                    write_guide(base + " - Cheat Guide.txt", title, f"{folder}/{name}.nds", cats, favs, bool(exact))

    if not report:
        print("No new games found in Downloads.")
    for r in report:
        print(" | ".join(r))


if __name__ == "__main__":
    main()
