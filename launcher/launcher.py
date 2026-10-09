#!/usr/bin/env python3
"""DS Launcher - a small offline game library for melonDS.

Run:  python3 launcher.py      (opens http://127.0.0.1:8765 in your browser)
Everything is local: it reads ~/Games, launches melonDS, and edits .mch cheat files.
"""
import json, os, re, shutil, socket, struct, subprocess, sys, threading, time, webbrowser, zlib
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

PORT = int(os.environ.get("DS_PORT", "8765"))
HOME = os.path.expanduser("~")
GAMES = os.environ.get("DS_GAMES_DIR", os.path.join(HOME, "Games"))
MELON = "/Applications/melonDS.app/Contents/MacOS/melonDS"
CONFIG = os.environ.get("DS_MELON_CONFIG", os.path.join(HOME, "Library/Preferences/melonDS/melonDS.toml"))
HERE = os.path.dirname(os.path.abspath(__file__))
SKIP_DIRS = {"Launcher", "cheat-tools", "backups"}
IDLE_EXIT = 120      # quit if the page hasn't checked in for this many seconds
BYE_GRACE = 5        # after the tab closes, wait this long (in case it was just a reload)
last_seen = time.time()
bye_at = None


# ---------- games ----------

def scan_games():
    out = []
    for folder in sorted(os.listdir(GAMES)):
        d = os.path.join(GAMES, folder)
        if folder in SKIP_DIRS or not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if f.lower().endswith(".nds"):
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
    title, _ = read_banner(path)
    mtime = lambda name: os.path.getmtime(os.path.join(folder, name))
    states = [{"slot": n, "time": fmt_time(mtime(f"{base}.ml{n}")), "ts": mtime(f"{base}.ml{n}")}
              for n in range(1, 9) if f"{base}.ml{n}" in files]
    sav = mtime(base + ".sav") if base + ".sav" in files else 0
    cheats = parse_mch_file(os.path.join(folder, base + ".mch")) if base + ".mch" in files else None
    return {
        "id": gid, "name": base, "title": title or base, "folder": os.path.basename(folder),
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
    for gid in scan_games():
        folder = os.path.dirname(gid)
        if folder not in listing:
            listing[folder] = set(os.listdir(os.path.join(GAMES, folder)))
        out.append(game_info(gid, listing[folder]))
    return out



# ---------- cheats (.mch, melonDS format) ----------

def mch_path(gid):
    return os.path.splitext(rom_path(gid))[0] + ".mch"


_mch_cache = {}  # path -> ((mtime, size), parsed); files are only re-read when they change


def parse_mch(gid):
    return parse_mch_file(mch_path(gid))


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


def write_cheats(gid, on_set):
    p = mch_path(gid)
    data = parse_mch(gid)
    lines = open(p, encoding="utf-8", errors="replace").read().split("\n")
    shutil.copy2(p, p + ".bak")
    for c in data["codes"]:
        lines[c["line"]] = f"CODE {1 if c['i'] in on_set else 0} {c['name']}"
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    os.replace(tmp, p)


# ---------- melonDS ----------

# Find melonDS via macOS libproc/sysctl instead of spawning `ps` (~1 ms vs ~60 ms per check).
import ctypes, ctypes.util
_libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
_libproc = ctypes.CDLL("/usr/lib/libproc.dylib")
_melon_pid = None  # last known melonDS pid: checked first, so a running game costs one syscall


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
    """Return (pid, rom path or '') if melonDS is running, else None."""
    global _melon_pid
    try:
        pid = None
        if _melon_pid and _exe_path(_melon_pid).endswith("/MacOS/melonDS"):
            pid = _melon_pid
        else:
            n = _libproc.proc_listallpids(None, 0)
            pids = (ctypes.c_int * (n + 64))()
            n = _libproc.proc_listallpids(pids, ctypes.sizeof(pids))
            pid = next((q for q in pids[:n] if q > 0 and _exe_path(q).endswith("melonDS.app/Contents/MacOS/melonDS")), None)
        _melon_pid = pid
        if not pid:
            return None
        args = _proc_args(pid)
        return pid, (args[1] if len(args) > 1 else "")
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


def quit_melon():
    subprocess.run(["osascript", "-e", 'tell application "melonDS" to quit'], capture_output=True)
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
    subprocess.Popen([MELON, path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     stdin=subprocess.DEVNULL, start_new_session=True)
    subprocess.Popen(["osascript", "-e", 'delay 1.5', "-e", 'tell application "melonDS" to activate'],
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
                    running = {"id": rel}
                games = all_games()
                return self.send(200, {"games": games, "running": running, "cheats_global": global_cheats()})
            if u.path == "/api/icon":
                _, png = read_banner(rom_path(q["id"]))
                return self.send(200, png or b"", "image/png", "max-age=86400")
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
                        return self.send(500, {"error": "Couldn't close melonDS - close it yourself (Cmd+Q) and try again."})
                launch(gid)
                return self.send(200, {"ok": True})
            if p == "/api/quit":
                return self.send(200, {"ok": quit_melon()})
            if p == "/api/cheats":
                gid = body["id"]
                r = running_game()
                if r and os.path.realpath(r[1]) == os.path.realpath(rom_path(gid)):
                    return self.send(409, {"error": "This game is running. Close it first, or change cheats inside melonDS (System > Setup cheat codes)."})
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
    print("DS Launcher running at", url)

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
