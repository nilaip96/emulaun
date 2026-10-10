#!/bin/bash
# EmuLaun installer (macOS).
#   ./install.sh          install / update everything
#   ./install.sh --dock   ...and add EmuLaun to the Dock
# Safe to re-run. Never touches your games or saves.
set -euo pipefail
cd "$(dirname "$0")"
REPO="$PWD"
GAMES="$REPO/games"   # your library (gitignored)
DATA="$REPO/data"     # downloaded cheat databases (gitignored)
DB_URL="https://raw.githubusercontent.com/szTheory/NDS-Cheat-Databases/HEAD/Cheat%20Databases/cheats.xml"

say()  { printf "\033[1;36m==>\033[0m %s\n" "$*"; }
fail() { printf "\033[1;31merror:\033[0m %s\n" "$*" >&2; exit 1; }

[ "$(uname)" = "Darwin" ] || fail "EmuLaun only runs on macOS."

# 1. tools
if ! xcrun --find swiftc >/dev/null 2>&1; then
  say "Installing Apple's Command Line Tools (a system dialog will pop up)..."
  xcode-select --install || true
  fail "Finish the Command Line Tools install, then run ./install.sh again."
fi
command -v python3 >/dev/null || fail "python3 not found (it comes with the Command Line Tools)."

# 2. melonDS emulator
if [ ! -d "/Applications/melonDS.app" ]; then
  say "Downloading melonDS (the DS emulator) from its official GitHub releases..."
  url=$(curl -fsSL https://api.github.com/repos/melonDS-emu/melonDS/releases/latest \
        | python3 -c "import json,sys; print(next(a['browser_download_url'] for a in json.load(sys.stdin)['assets'] if 'macOS' in a['name']))")
  tmp=$(mktemp -d)
  curl -fsSL -o "$tmp/melonDS.zip" "$url"
  unzip -q "$tmp/melonDS.zip" -d "$tmp"
  cp -R "$tmp/melonDS.app" /Applications/
  rm -rf "$tmp"
else
  say "melonDS already installed"
fi

# 2b. mGBA emulator (Game Boy / Color / Advance)
if [ ! -d "/Applications/mGBA.app" ]; then
  say "Downloading mGBA (the Game Boy / GBA emulator) from its official GitHub releases..."
  url=$(curl -fsSL https://api.github.com/repos/mgba-emu/mgba/releases/latest \
        | python3 -c "import json,sys; print(next(a['browser_download_url'] for a in json.load(sys.stdin)['assets'] if a['name'].endswith('-macos.dmg')))")
  tmp=$(mktemp -d)
  curl -fsSL -o "$tmp/mGBA.dmg" "$url"
  hdiutil attach -nobrowse -readonly -mountpoint "$tmp/mnt" "$tmp/mGBA.dmg" >/dev/null
  cp -R "$tmp/mnt/mGBA.app" /Applications/
  hdiutil detach "$tmp/mnt" >/dev/null; rm -rf "$tmp"
else
  say "mGBA already installed"
fi
# mGBA settings live in ~/.config/mgba on macOS. Merge in: same keys as the suggested melonDS
# setup, auto-load cheat files, and autosave (Game.ss0 every ~10 s and on close; EmuLaun's Resume loads it).
if ! pgrep -f "mGBA.app/Contents/MacOS/mGBA" >/dev/null; then
  mkdir -p "$HOME/.config/mgba"
  python3 - "$HOME/.config/mgba/config.ini" <<'PY'
import configparser, os, sys
p = sys.argv[1]
c = configparser.RawConfigParser(); c.optionxform = str
if os.path.exists(p): c.read(p)
keys = {"keyA": 68, "keyB": 65, "keyL": 81, "keyR": 69, "keyStart": 16777220, "keySelect": 16777248,
        "keyUp": 16777235, "keyDown": 16777237, "keyLeft": 16777234, "keyRight": 16777236}
for sec in ("gba.input.QT_K", "gb.input.QT_K"):
    if not c.has_section(sec): c.add_section(sec)
    for k, v in keys.items(): c.set(sec, k, str(v))
if not c.has_section("ports.qt"): c.add_section("ports.qt")
for k in ("autosave", "cheatAutoload", "cheatAutosave"): c.set("ports.qt", k, "1")
c.set("ports.qt", "autoload", "0")  # EmuLaun's Resume loads the autosave; Play starts from the in-game save
for k, v in (("lockIntegerScaling", "1"), ("lockAspectRatio", "1"), ("resampleVideo", "0")): c.set("ports.qt", k, v)  # sharp pixels
with open(p, "w") as f: c.write(f, space_around_delimiters=False)
PY
else
  say "mGBA is open - skipping its settings (re-run ./install.sh after closing it)"
fi

# melonDS: sharper DS graphics (OpenGL renderer at 3x resolution). Its settings file appears after first launch.
MELON_CFG="$HOME/Library/Preferences/melonDS/melonDS.toml"
if [ -f "$MELON_CFG" ] && ! pgrep -f "melonDS.app/Contents/MacOS/melonDS" >/dev/null; then
  python3 - "$MELON_CFG" <<'PY'
import re, sys
p = sys.argv[1]; s = open(p).read()
def setkey(s, section, key, val):
    pat = rf"(^\[{re.escape(section)}\]\n(?:(?!\[).*\n)*?){re.escape(key)} = .*\n"
    if re.search(pat, s, re.M):
        return re.sub(pat, lambda m: m.group(1) + f"{key} = {val}\n", s, count=1, flags=re.M)
    return re.sub(rf"(^\[{re.escape(section)}\]\n)", lambda m: m.group(1) + f"{key} = {val}\n", s, count=1, flags=re.M)
for sec, k, v in [("3D", "Renderer", "1"), ("3D.GL", "ScaleFactor", "3"), ("3D.GL", "BetterPolygons", "true"), ("Screen", "UseGL", "true")]:
    s = setkey(s, sec, k, v)
open(p, "w").write(s)
PY
fi

# 3. folders + offline cheat databases
mkdir -p "$GAMES/DS" "$GAMES/GBA" "$GAMES/GBC" "$GAMES/GB" "$DATA"
if [ ! -s "$DATA/cheats.xml" ]; then
  say "Downloading the NDS cheat database (~100 MB, one time - everything works offline after this)..."
  curl -fL --progress-bar -o "$DATA/cheats.xml.part" "$DB_URL"
  mv "$DATA/cheats.xml.part" "$DATA/cheats.xml"
else
  say "Cheat database already downloaded"
fi

if [ ! -d "$DATA/libretro-database" ]; then
  say "Downloading Game Boy / GBA cheats + game checksums from libretro-database (~60 MB, one time)..."
  git clone -q --depth 1 --filter=blob:none --sparse https://github.com/libretro/libretro-database.git "$DATA/libretro-database"
  git -C "$DATA/libretro-database" sparse-checkout set \
    "cht/Nintendo - Game Boy" "cht/Nintendo - Game Boy Color" "cht/Nintendo - Game Boy Advance" "metadat/no-intro"
else
  say "Game Boy cheat data already downloaded"
fi

# 4. build + install the app
say "Building EmuLaun.app..."
./app/build.sh
# quit a running copy (by process, not by name: naming an app that no longer exists makes macOS ask "Where is ...?")
OLD_NAMES=("DS Launcher" "Emulaunch")   # this app's previous names
pkill -f "/Applications/(EmuLaun|DS Launcher|Emulaunch).app/Contents/MacOS/" 2>/dev/null || true
pkill -f "\.app/Contents/Resources/launcher/launcher\.py" 2>/dev/null || true   # its server, so the new app doesn't reuse old code
for old in "${OLD_NAMES[@]}"; do rm -rf "/Applications/$old.app"; done
rm -rf "/Applications/EmuLaun.app"
cp -R "app/build/EmuLaun.app" /Applications/
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "/Applications/EmuLaun.app" || true

# 5. Dock: move an icon left by an older name over to EmuLaun; with --dock, add one if there is none
DOCK_CHANGED=$(python3 - "${1:-}" <<'PY'
import plistlib, subprocess, sys
want = "file:///Applications/EmuLaun.app/"
old = ("DS%20Launcher.app", "Emulaunch.app")
d = plistlib.loads(subprocess.run(["defaults", "export", "com.apple.dock", "-"], capture_output=True).stdout)
apps = d.setdefault("persistent-apps", [])
changed, present = False, False
for t in apps:
    fd = t.get("tile-data", {}).get("file-data", {})
    url = fd.get("_CFURLString", "")
    if any(o in url for o in old):
        fd["_CFURLString"], fd["_CFURLStringType"] = want, 15
        t["tile-data"]["file-label"] = "EmuLaun"
        t["tile-data"].pop("book", None)
        changed = True
    if fd.get("_CFURLString") == want:
        present = True
if sys.argv[1] == "--dock" and not present:
    apps.append({"tile-type": "file-tile", "tile-data": {"file-label": "EmuLaun",
                 "file-data": {"_CFURLString": want, "_CFURLStringType": 15}}})
    changed = True
if changed:
    subprocess.run(["defaults", "import", "com.apple.dock", "-"], input=plistlib.dumps(d))
print("yes" if changed else "no")
PY
)
if [ "$DOCK_CHANGED" = "yes" ]; then say "Updated the Dock icon"; killall Dock; fi

cat <<EOF

$(printf "\033[1;32m✓ EmuLaun is installed.\033[0m")

Next:
  1. Put your own game backups (.nds .gba .gbc .gb, or .zip/.7z containing them) in ~/Downloads, then run:
       python3 "$REPO/tools/add_games.py"
     It copies them into the repo's games/ folder and installs cheats + a cheat guide for each.
  2. Open "EmuLaun" from Applications (or Spotlight).
EOF
