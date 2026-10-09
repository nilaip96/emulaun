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
MGBA_CFG="$HOME/Library/Application Support/mGBA/config.ini"
if [ ! -f "$MGBA_CFG" ]; then  # same keys as the suggested melonDS setup; auto-load cheat files
  mkdir -p "$(dirname "$MGBA_CFG")"
  keys=$'keyA=68\nkeyB=65\nkeyL=81\nkeyR=69\nkeyStart=16777220\nkeySelect=16777248\nkeyUp=16777235\nkeyDown=16777237\nkeyLeft=16777234\nkeyRight=16777236'
  printf '[ports.qt]\ncheatAutoload=1\ncheatAutosave=1\n\n[gba.input.QT_K]\n%s\n\n[gb.input.QT_K]\n%s\n' "$keys" "$keys" > "$MGBA_CFG"
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
