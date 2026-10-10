#!/usr/bin/env python3
"""EmuLaun - a small offline game library for melonDS (DS) and mGBA (GB/GBC/GBA).

Run:  python3 launcher.py      (opens http://127.0.0.1:8765 in your browser)
Everything is local: it reads the repo's games/ folder, launches the emulator, and edits cheat files
(.mch for melonDS, .cheats for mGBA).
"""
import json, os, re, shutil, socket, struct, subprocess, sys, threading, time, webbrowser, zlib
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

PORT = int(os.environ.get("DS_PORT", "8765"))
HOME = os.path.expanduser("~")
# games/ in the repo; the app passes the absolute path (it runs a bundled copy of this file)
GAMES = os.environ.get("DS_GAMES_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "games"))
MELON = "/Applications/melonDS.app/Contents/MacOS/melonDS"
MGBA = "/Applications/mGBA.app/Contents/MacOS/mGBA"
SYSTEM_BY_EXT = {".nds": "DS", ".gba": "GBA", ".gbc": "GBC", ".gb": "GB"}
EMULATOR = {"DS": ("melonDS", MELON), "GBA": ("mGBA", MGBA), "GBC": ("mGBA", MGBA), "GB": ("mGBA", MGBA)}
CONFIG = os.environ.get("DS_MELON_CONFIG", os.path.join(HOME, "Library/Preferences/melonDS/melonDS.toml"))
HERE = os.path.dirname(os.path.abspath(__file__))
SKIP_DIRS = {"backups"}
IDLE_EXIT = 120      # quit if the page hasn't checked in for this many seconds
BYE_GRACE = 5        # after the tab closes, wait this long (in case it was just a reload)
last_seen = time.time()
bye_at = None


# ---------- games ----------

def scan_games():
    out = []
    for folder in sorted(os.listdir(GAMES)):
        d = os.path.join(GAMES, folder)
        if folder in SKIP_DIRS or folder.startswith(".") or not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if os.path.splitext(f)[1].lower() in SYSTEM_BY_EXT:
                out.append(os.path.join(folder, f))
    return out


def rom_path(gid):
    """Validate a game id ('Folder/Name.nds') and return its absolute path."""
    if gid not in scan_games():
        raise ValueError("unknown game")
    return os.path.join(GAMES, gid)


_banner_cache = {}

def read_banner(path):
    key = (path, os.path.getmtime(path))
    if key in _banner_cache:
        return _banner_cache[key]
    title, icon = None, None
    with open(path, "rb") as f:
        f.seek(0x68)
        off = struct.unpack("<I", f.read(4))[0]
        if off:
            f.seek(off)
            b = f.read(0x840)
            if len(b) >= 0x440:
                raw = b[0x340:0x440].decode("utf-16-le", "ignore").split("\x00")[0]
                lines = [l.strip() for l in raw.split("\n") if l.strip()]
                if len(lines) > 1:
                    lines = lines[:-1]  # last line is the publisher
                title = " ".join(lines) or None
                icon = icon_png(b[0x20:0x220], b[0x220:0x240])
    _banner_cache[key] = (title, icon)
    return title, icon


def icon_png(bitmap, palette):
    pal = []
    for i in range(16):
        c = palette[i * 2] | palette[i * 2 + 1] << 8
        r, g, b = c & 31, (c >> 5) & 31, (c >> 10) & 31
        pal.append((r << 3 | r >> 2, g << 3 | g >> 2, b << 3 | b >> 2, 0 if i == 0 else 255))
    px = [[(0, 0, 0, 0)] * 32 for _ in range(32)]
    for ty in range(4):
        for tx in range(4):
            tile = bitmap[(ty * 4 + tx) * 32:(ty * 4 + tx + 1) * 32]
            for y in range(8):
                for x in range(8):
                    byte = tile[y * 4 + x // 2]
                    idx = byte & 15 if x % 2 == 0 else byte >> 4
                    px[ty * 8 + y][tx * 8 + x] = pal[idx]
    raw = b"".join(b"\x00" + bytes(v for p in row for v in p) for row in px)

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 32, 32, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def fmt_time(ts):
    return datetime.fromtimestamp(ts).strftime("%b %d, %I:%M %p").replace(" 0", " ")


def game_info(gid, files=None):
    """files: names in the game's folder (pass it in to avoid re-listing the folder per game)."""
    path = os.path.join(GAMES, gid)
    folder, base = os.path.dirname(path), os.path.splitext(os.path.basename(path))[0]
    if files is None:
        files = set(os.listdir(folder))
    system = SYSTEM_BY_EXT[os.path.splitext(path)[1].lower()]
    title = read_banner(path)[0] if system == "DS" else None
    mtime = lambda name: os.path.getmtime(os.path.join(folder, name))
    st_ext = "ml" if system == "DS" else "ss"  # melonDS: Game.ml1-8, mGBA: Game.ss1-9
    states = [{"slot": n, "time": fmt_time(mtime(f"{base}.{st_ext}{n}")), "ts": mtime(f"{base}.{st_ext}{n}")}
              for n in range(0 if st_ext == "ss" else 1, 10) if f"{base}.{st_ext}{n}" in files]  # mGBA autosave = .ss0
    sav = mtime(base + ".sav") if base + ".sav" in files else 0
    cfile = base + (".mch" if system == "DS" else ".cheats")
    cheats = parse_cheat_file(os.path.join(folder, cfile)) if cfile in files else None
    return {
        "id": gid, "name": base, "title": title or base, "folder": os.path.basename(folder), "system": system,
        "art": system == "DS" or base + ".png" in files,
        "save": fmt_time(sav) if sav else None,
        "last": max([sav] + [st["ts"] for st in states]),
        "states": states,
        "cheats_total": len(cheats["codes"]) if cheats else 0,
        "cheats_on": sum(c["on"] for c in cheats["codes"]) if cheats else 0,
        "has_guide": f"{base} - Cheat Guide.txt" in files,
    }


def all_games():
    listing = {}
    out = []
    prefs, play, sess = load_prefs(), playtime(), current_session()
    for gid in scan_games():
        folder = os.path.dirname(gid)
        if folder not in listing:
            listing[folder] = set(os.listdir(os.path.join(GAMES, folder)))
        g = game_info(gid, listing[folder])
        pt = play.get(gid, {"secs": 0, "last": 0})
        live = sess and sess.get("id") == gid and running_game()
        g["played"] = pt["secs"] + (int(time.time()) - sess["start"] if live else 0)
        g["last"] = max(g["last"], pt["last"], sess["start"] if live else 0)
        g["pinned"] = gid in prefs["pinned"]
        g["hidden"] = gid in prefs["hidden"]
        out.append(g)
    return out



# ---------- library state: prefs, playtime, save backups ----------
# Kept next to the games (games/.emulaun/) so it travels with the library.
STATE_DIR = os.path.join(GAMES, ".emulaun")
PREFS = os.path.join(STATE_DIR, "prefs.json")
PLAYLOG = os.path.join(STATE_DIR, "playtime.tsv")      # id <tab> start <tab> end, one line per session
SESSION = os.path.join(STATE_DIR, "session.json")      # the game currently being played
SAVE_BACKUPS = os.path.join(os.path.dirname(GAMES), "backups", "saves")
KEEP_BACKUPS = 5


def load_prefs():
    try:
        p = json.load(open(PREFS))
    except (OSError, ValueError):
        p = {}
    p.setdefault("pinned", []); p.setdefault("hidden", []); p.setdefault("fullscreen", True)
    return p


def save_prefs(p):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(PREFS + ".tmp", "w") as f:
        json.dump(p, f, indent=1)
    os.replace(PREFS + ".tmp", PREFS)


_play_cache = (None, {})

def playtime():
    """id -> {"secs": total seconds, "last": last end time}, from the play log (cached by mtime)."""
    global _play_cache
    try:
        key = os.stat(PLAYLOG).st_mtime_ns
    except OSError:
        return {}
    if _play_cache[0] == key:
        return _play_cache[1]
    out = {}
    for line in open(PLAYLOG, encoding="utf-8", errors="replace"):
        parts = line.rstrip("\n").split("\t")
        if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
            d = out.setdefault(parts[0], {"secs": 0, "last": 0})
            d["secs"] += max(0, int(parts[2]) - int(parts[1]))
            d["last"] = max(d["last"], int(parts[2]))
    _play_cache = (key, out)
    return out


def current_session():
    try:
        return json.load(open(SESSION))
    except (OSError, ValueError):
        return None


def backup_save(gid):
    """Copy the game's .sav into backups/saves/ before launching, if it changed; keep the newest few."""
    sav = os.path.splitext(rom_path(gid))[0] + ".sav"
    if not os.path.exists(sav):
        return
    d = os.path.join(SAVE_BACKUPS, os.path.splitext(gid)[0])
    os.makedirs(d, exist_ok=True)
    olds = sorted(f for f in os.listdir(d) if f.endswith(".sav"))
    data = open(sav, "rb").read()
    if olds and open(os.path.join(d, olds[-1]), "rb").read() == data:
        return  # unchanged since the last backup
    shutil.copy2(sav, os.path.join(d, datetime.now().strftime("%Y-%m-%d %H%M%S") + ".sav"))
    for f in sorted(f for f in os.listdir(d) if f.endswith(".sav"))[:-KEEP_BACKUPS]:
        os.remove(os.path.join(d, f))


# ---------- cheats (.mch, melonDS format) ----------

def cheat_path(gid):
    p = rom_path(gid)
    return os.path.splitext(p)[0] + (".mch" if p.lower().endswith(".nds") else ".cheats")


_mch_cache = {}  # path -> ((mtime, size), parsed); files are only re-read when they change


def parse_mch(gid):
    return parse_cheat_file(cheat_path(gid))


def parse_cheat_file(p):
    return parse_mch_file(p) if p.endswith(".mch") else parse_mgba_file(p)


def parse_mch_file(p):
    try:
        st = os.stat(p)
    except OSError:
        return None
    key = (st.st_mtime_ns, st.st_size)
    hit = _mch_cache.get(p)
    if hit and hit[0] == key:
        return hit[1]
    cats, codes = [], []
    last = None
    for i, line in enumerate(open(p, encoding="utf-8", errors="replace").read().split("\n")):
        if line.startswith("CAT "):
            m = re.match(r"CAT (?:([01]) )?(.*)$", line)
            cats.append({"name": m.group(2).strip(), "one": m.group(1) == "1", "desc": "", "codes": []})
            last = cats[-1]
        elif line.startswith("CODE ") and cats:
            m = re.match(r"CODE ([01]) (.*)$", line)
            if m:
                c = {"i": len(codes), "line": i, "on": m.group(1) == "1", "name": m.group(2).strip(), "desc": ""}
                codes.append(c)
                cats[-1]["codes"].append(c["i"])
                last = c
        elif line.startswith("DESC ") and last is not None:
            last["desc"] = line[5:].strip()
    data = {"cats": cats, "codes": codes}
    _mch_cache[p] = (key, data)
    return data


# ---------- cheats (.cheats, mGBA format) ----------
# "!disabled" before "# Name" turns a cheat off; code lines follow the name.
# Names starting with "★" are this tool's favorites and get their own folder in the UI.

def _mgba_entries(p):
    pre, entries, pending, disabled = [], [], [], False
    for line in open(p, encoding="utf-8", errors="replace").read().split("\n"):
        t = line.strip()
        if t.lower() == "!disabled":
            disabled = True
        elif t.startswith("!"):
            pending.append(line)
        elif t.startswith("#"):
            entries.append({"name": t[1:].strip(), "on": not disabled, "pre": pending, "body": []})
            pending, disabled = [], False
        elif entries:
            if t:
                entries[-1]["body"].append(line)
        elif t:
            pre.append(line)
    return pre, entries


def parse_mgba_file(p):
    try:
        st = os.stat(p)
    except OSError:
        return None
    key = (st.st_mtime_ns, st.st_size)
    hit = _mch_cache.get(p)
    if hit and hit[0] == key:
        return hit[1]
    _, entries = _mgba_entries(p)
    codes = [{"i": i, "on": e["on"], "name": e["name"].lstrip("★ ").strip(), "desc": ""} for i, e in enumerate(entries)]
    favs = [i for i, e in enumerate(entries) if e["name"].startswith("★")]
    cats = ([{"name": "*** FAVORITES ***", "one": False, "desc": "", "codes": favs}] if favs else []) + \
           [{"name": "All cheats", "one": False, "desc": "", "codes": list(range(len(entries)))}]
    data = {"cats": cats, "codes": codes}
    _mch_cache[p] = (key, data)
    return data


def write_mgba(p, on_set):
    pre, entries = _mgba_entries(p)
    out = list(pre)
    for i, e in enumerate(entries):
        out += e["pre"] + ([] if i in on_set else ["!disabled"]) + [f"# {e['name']}"] + e["body"] + [""]
    shutil.copy2(p, p + ".bak")
    with open(p + ".tmp", "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    os.replace(p + ".tmp", p)


def write_cheats(gid, on_set):
    p = cheat_path(gid)
    if p.endswith(".cheats"):
        return write_mgba(p, on_set)
    data = parse_mch(gid)
    lines = open(p, encoding="utf-8", errors="replace").read().split("\n")
    shutil.copy2(p, p + ".bak")
    for c in data["codes"]:
        lines[c["line"]] = f"CODE {1 if c['i'] in on_set else 0} {c['name']}"
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    os.replace(tmp, p)


# ---------- emulators ----------

# Find melonDS via macOS libproc/sysctl instead of spawning `ps` (~1 ms vs ~60 ms per check).
import ctypes, ctypes.util
_libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
_libproc = ctypes.CDLL("/usr/lib/libproc.dylib")
_melon_pid = None  # last known emulator pid: checked first, so a running game costs one syscall
_EMU_EXES = ("melonDS.app/Contents/MacOS/melonDS", "mGBA.app/Contents/MacOS/mGBA")


def _exe_path(pid):
    buf = ctypes.create_string_buffer(4096)
    n = _libproc.proc_pidpath(pid, buf, 4096)
    return buf.value.decode("utf-8", "replace") if n > 0 else ""


def _proc_args(pid):
    """argv of a process via sysctl(KERN_PROCARGS2)."""
    mib = (ctypes.c_int * 3)(1, 49, pid)  # CTL_KERN, KERN_PROCARGS2
    size = ctypes.c_size_t(1 << 16)
    buf = ctypes.create_string_buffer(size.value)
    if _libc.sysctl(mib, 3, buf, ctypes.byref(size), None, 0) != 0:
        return []
    raw = buf.raw[:size.value]
    argc = struct.unpack_from("<i", raw)[0]
    parts = [x for x in raw[4:].split(b"\0") if x][1:]  # skip exec path
    return [x.decode("utf-8", "replace") for x in parts[:argc]]


def running_game():
    if os.environ.get("DS_DEMO"):  # README screenshots: ignore real emulators
        return None
    return _running_game()


def _running_game():
    """Return (pid, rom path or '') if melonDS or mGBA is running, else None."""
    global _melon_pid
    try:
        pid = None
        if _melon_pid and _exe_path(_melon_pid).endswith(_EMU_EXES):
            pid = _melon_pid
        else:
            n = _libproc.proc_listallpids(None, 0)
            pids = (ctypes.c_int * (n + 64))()
            n = _libproc.proc_listallpids(pids, ctypes.sizeof(pids))
            pid = next((q for q in pids[:n] if q > 0 and _exe_path(q).endswith(_EMU_EXES)), None)
        _melon_pid = pid
        if not pid:
            return None
        args = _proc_args(pid)
        return pid, (args[-1] if len(args) > 1 else "")
    except Exception:
        return None


def global_cheats():
    try:
        m = re.search(r"^EnableCheats = (true|false)", open(CONFIG).read(), re.M)
        return m.group(1) == "true" if m else False
    except OSError:
        return False


def set_global_cheats(on):
    txt = open(CONFIG).read()
    txt = re.sub(r"^EnableCheats = (true|false)", f"EnableCheats = {'true' if on else 'false'}", txt, count=1, flags=re.M)
    open(CONFIG, "w").write(txt)


DS_AUTOSAVE_SLOT = 8  # melonDS: Shift+F8 saves slot 8 (Game.ml8), F8 loads it


DS_AUTOSAVE_SECS = int(os.environ.get("DS_AUTOSAVE_SECS", "60"))
_F_KEYS = {1: 122, 2: 120, 3: 99, 4: 118, 5: 96, 6: 97, 7: 98, 8: 100}  # macOS virtual key codes


# JavaScript for osascript: press F<n> with only the Shift *flag* set, so melonDS sees Shift+F<n> (save
# state) while the Shift key itself is never pressed (it may be a game button, e.g. L). The key goes
# through the normal keyboard route, so melonDS must be in front: with activate=1 it's brought forward,
# otherwise nothing is sent unless it already is. Run via osascript because that's the program macOS
# grants Accessibility to here.
_SHIFT_FKEY_JS = """ObjC.import('CoreGraphics'); ObjC.import('AppKit');
function run(argv) {
  const pid = parseInt(argv[0]), key = parseInt(argv[1]), activate = argv[2] === "1";
  const front = () => $.NSWorkspace.sharedWorkspace.frontmostApplication.processIdentifier === pid;
  if (activate && !front()) {
    $.NSRunningApplication.runningApplicationWithProcessIdentifier(pid).activateWithOptions(2);
    delay(0.6);
  }
  if (!front()) return "skipped";
  [true, false].forEach(down => {
    const e = $.CGEventCreateKeyboardEvent(null, key, down);
    $.CGEventSetFlags(e, 131072);
    $.CGEventPost(0, e);
    delay(0.05);
  });
  return "sent";
}"""


def ds_save_state(pid, slot=DS_AUTOSAVE_SLOT, activate=False):
    """Make a melonDS save state (Shift+F<slot>). Returns (sent, error)."""
    r = subprocess.run(["osascript", "-l", "JavaScript", "-e", _SHIFT_FKEY_JS, str(pid), str(_F_KEYS[slot]),
                        "1" if activate else "0"], capture_output=True, text=True)
    return r.returncode == 0 and r.stdout.strip() == "sent", r.stderr.strip()


def ds_autosave():
    r = running_game()
    if not r or not _exe_path(r[0]).endswith("/melonDS"):
        return False, "melonDS isn't running"
    state = os.path.splitext(r[1])[0] + f".ml{DS_AUTOSAVE_SLOT}"
    before = os.path.getmtime(state) if os.path.exists(state) else 0
    ok, err = ds_save_state(r[0], activate=True)
    if not ok:
        return False, err or "couldn't bring melonDS to the front"
    for _ in range(30):  # confirm melonDS really wrote the state before it gets closed
        time.sleep(0.2)
        if os.path.exists(state) and os.path.getmtime(state) > before:
            time.sleep(0.5)
            return True, ""
    return False, "melonDS didn't write a save state (is EmuLaun allowed in Accessibility?)"


def ds_autosave_loop(rom):
    """Runs detached alongside a DS game (survives EmuLaun closing): save a state every minute."""
    pid = None
    for _ in range(60):  # wait for melonDS to start
        r = _running_game()
        if r and _exe_path(r[0]).endswith("/melonDS") and os.path.realpath(r[1]) == os.path.realpath(rom):
            pid = r[0]
            break
        time.sleep(1)
    while pid:
        for _ in range(DS_AUTOSAVE_SECS):
            time.sleep(1)
            if not _exe_path(pid).endswith("/melonDS"):
                return
        ds_save_state(pid)


def quit_melon():
    r = running_game()
    app = "mGBA" if r and _exe_path(r[0]).endswith("/mGBA") else "melonDS"
    subprocess.run(["osascript", "-e", f'tell application "{app}" to quit'], capture_output=True)
    for _ in range(20):
        if not running_game():
            return True
        time.sleep(0.25)
    r = running_game()
    if r:
        os.kill(r[0], 15)
        time.sleep(1)
    return not running_game()


def launch(gid):
    path = rom_path(gid)
    app, exe = EMULATOR[SYSTEM_BY_EXT[os.path.splitext(path)[1].lower()]]
    try:
        backup_save(gid)
    except OSError:
        pass
    args = (["-f"] if load_prefs()["fullscreen"] else []) + [path]
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(SESSION, "w") as f:
        json.dump({"id": gid, "start": int(time.time())}, f)
    # A tiny shell wrapper logs the session when the emulator exits, even if EmuLaun was closed meanwhile.
    wrapper = 'start=$(date +%s); "$0" "$@"; printf "%s\\t%s\\t%s\\n" "$EMULAUN_ID" "$start" "$(date +%s)" >> "$EMULAUN_LOG"; rm -f "$EMULAUN_SESSION"'
    env = dict(os.environ, EMULAUN_ID=gid, EMULAUN_LOG=PLAYLOG, EMULAUN_SESSION=SESSION)
    subprocess.Popen(["/bin/sh", "-c", wrapper, exe] + args, env=env, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, start_new_session=True)
    if app == "melonDS" and not os.environ.get("DS_DEMO"):  # DS: EmuLaun autosaves (mGBA does its own)
        subprocess.Popen([sys.executable, os.path.abspath(__file__), "--ds-autosave", path], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, start_new_session=True)
    subprocess.Popen(["osascript", "-e", 'delay 1.5', "-e", f'tell application "{app}" to activate'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ---------- http ----------

class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, ctype="application/json", cache="no-store"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.end_headers()
        self.wfile.write(body)

    def ok_host(self):
        return self.headers.get("Host", "") in (f"127.0.0.1:{PORT}", f"localhost:{PORT}")

    def do_GET(self):
        global last_seen, bye_at
        if not self.ok_host():
            return self.send(403, {"error": "forbidden"})
        last_seen, bye_at = time.time(), None
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path == "/":
                return self.send(200, open(os.path.join(HERE, "index.html"), "rb").read(), "text/html; charset=utf-8")
            if u.path == "/api/state":
                r = running_game()
                running = None
                if r:
                    rel = os.path.relpath(r[1], GAMES) if r[1].startswith(GAMES) else ""
                    running = {"id": rel, "emulator": "mGBA" if _exe_path(r[0]).endswith("/mGBA") else "melonDS"}
                games = all_games()
                return self.send(200, {"games": games, "running": running, "cheats_global": global_cheats(),
                                       "fullscreen": load_prefs()["fullscreen"]})
            if u.path == "/api/icon":
                rp = rom_path(q["id"])
                if rp.lower().endswith(".nds"):
                    png = read_banner(rp)[1]
                else:  # box art saved by the importer, if any
                    art = os.path.splitext(rp)[0] + ".png"
                    png = open(art, "rb").read() if os.path.exists(art) else None
                if not png:
                    return self.send(404, {"error": "no icon"})
                return self.send(200, png, "image/png", "max-age=86400")
            if u.path == "/api/cheats":
                return self.send(200, parse_mch(q["id"]) or {"cats": [], "codes": []})
            if u.path == "/api/guide":
                p = os.path.splitext(rom_path(q["id"]))[0] + " - Cheat Guide.txt"
                return self.send(200, open(p, encoding="utf-8").read(), "text/plain; charset=utf-8")
        except (ValueError, KeyError, OSError) as e:
            return self.send(400, {"error": str(e)})
        self.send(404, {"error": "not found"})

    def do_POST(self):
        global last_seen, bye_at
        if self.ok_host() and urlparse(self.path).path == "/api/bye":
            bye_at = time.time()  # tab closed (sent by the page, no custom header possible)
            return self.send(200, {"ok": True})
        if not self.ok_host() or self.headers.get("X-Launcher") != "1":
            return self.send(403, {"error": "forbidden"})
        last_seen, bye_at = time.time(), None
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
            p = urlparse(self.path).path
            if p == "/api/play":
                gid = body["id"]
                rom_path(gid)
                if running_game():
                    if not body.get("force"):
                        return self.send(409, {"error": "running"})
                    if not quit_melon():
                        return self.send(500, {"error": "Couldn't close the emulator - close it yourself (Cmd+Q) and try again."})
                launch(gid)
                return self.send(200, {"ok": True})
            if p == "/api/quit":
                r = running_game()
                saved = None
                if r and _exe_path(r[0]).endswith("/melonDS") and not body.get("nosave"):
                    ok, err = ds_autosave()
                    if not ok:
                        return self.send(409, {"error": "autosave", "detail": err})
                    saved = DS_AUTOSAVE_SLOT
                return self.send(200, {"ok": quit_melon(), "saved_slot": saved})
            if p == "/api/prefs":
                prefs = load_prefs()
                if "fullscreen" in body:
                    prefs["fullscreen"] = bool(body["fullscreen"])
                if "id" in body:
                    gid = body["id"]; rom_path(gid)
                    for key in ("pinned", "hidden"):
                        if key in body:
                            lst = [x for x in prefs[key] if x != gid]
                            prefs[key] = lst + ([gid] if body[key] else [])
                save_prefs(prefs)
                return self.send(200, {"ok": True})
            if p == "/api/cheats":
                gid = body["id"]
                r = running_game()
                if r and os.path.realpath(r[1]) == os.path.realpath(rom_path(gid)):
                    return self.send(409, {"error": "This game is running. Close it first, or change cheats inside the emulator (melonDS: System > Setup cheat codes, mGBA: Tools > Cheats)."})
                write_cheats(gid, set(int(i) for i in body["on"]))
                return self.send(200, {"ok": True})
            if p == "/api/global_cheats":
                if running_game():
                    return self.send(409, {"error": "Close melonDS first (it would overwrite this setting when it closes)."})
                set_global_cheats(bool(body["on"]))
                return self.send(200, {"ok": True})
            if p == "/api/reveal":
                subprocess.run(["open", "-R", rom_path(body["id"])])
                return self.send(200, {"ok": True})
        except (ValueError, KeyError, OSError, json.JSONDecodeError) as e:
            return self.send(400, {"error": str(e)})
        self.send(404, {"error": "not found"})


def main():
    if len(sys.argv) > 2 and sys.argv[1] == "--ds-autosave":
        return ds_autosave_loop(sys.argv[2])
    url = f"http://127.0.0.1:{PORT}/"
    try:  # is a launcher already answering on this port?
        socket.create_connection(("127.0.0.1", PORT), timeout=0.5).close()
        if "--no-browser" not in sys.argv:
            webbrowser.open(url)
        return
    except OSError:
        pass
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    if "--no-browser" not in sys.argv:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    print("EmuLaun running at", url)

    def watchdog():
        while True:
            time.sleep(1)
            now = time.time()
            if (bye_at and now - bye_at > BYE_GRACE) or now - last_seen > IDLE_EXIT:
                srv.shutdown()
                return
    threading.Thread(target=watchdog, daemon=True).start()
    srv.serve_forever()


if __name__ == "__main__":
    main()
