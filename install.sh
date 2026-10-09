#!/bin/bash
# DS Launcher installer (macOS).
#   ./install.sh          install / update everything
#   ./install.sh --dock   ...and add DS Launcher to the Dock
# Safe to re-run. Never touches your games or saves.
set -euo pipefail
cd "$(dirname "$0")"
REPO="$PWD"
GAMES="$HOME/Games"
DB_URL="https://raw.githubusercontent.com/szTheory/NDS-Cheat-Databases/HEAD/Cheat%20Databases/cheats.xml"

say()  { printf "\033[1;36m==>\033[0m %s\n" "$*"; }
fail() { printf "\033[1;31merror:\033[0m %s\n" "$*" >&2; exit 1; }

[ "$(uname)" = "Darwin" ] || fail "DS Launcher only runs on macOS."

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
mkdir -p "$GAMES/DS" "$GAMES/GBA" "$GAMES/GBC" "$GAMES/GB" "$GAMES/cheat-tools"
if [ ! -s "$GAMES/cheat-tools/cheats.xml" ]; then
  say "Downloading the NDS cheat database (~100 MB, one time - everything works offline after this)..."
  curl -fL --progress-bar -o "$GAMES/cheat-tools/cheats.xml.part" "$DB_URL"
  mv "$GAMES/cheat-tools/cheats.xml.part" "$GAMES/cheat-tools/cheats.xml"
else
  say "Cheat database already downloaded"
fi

if [ ! -d "$GAMES/cheat-tools/libretro-database" ]; then
  say "Downloading Game Boy / GBA cheats + game checksums from libretro-database (~60 MB, one time)..."
  git clone -q --depth 1 --filter=blob:none --sparse https://github.com/libretro/libretro-database.git "$GAMES/cheat-tools/libretro-database"
  git -C "$GAMES/cheat-tools/libretro-database" sparse-checkout set \
    "cht/Nintendo - Game Boy" "cht/Nintendo - Game Boy Color" "cht/Nintendo - Game Boy Advance" "metadat/no-intro"
else
  say "Game Boy cheat data already downloaded"
fi

# 4. build + install the app
say "Building DS Launcher.app..."
./app/build.sh
osascript -e 'tell application "DS Launcher" to quit' >/dev/null 2>&1 || true
rm -rf "/Applications/DS Launcher.app"
cp -R "app/build/DS Launcher.app" /Applications/
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "/Applications/DS Launcher.app" || true

# 5. optional Dock icon
if [ "${1:-}" = "--dock" ] && ! defaults read com.apple.dock persistent-apps 2>/dev/null | grep -q "Applications/DS%20Launcher.app"; then
  say "Adding DS Launcher to the Dock"
  defaults write com.apple.dock persistent-apps -array-add \
    '<dict><key>tile-data</key><dict><key>file-data</key><dict><key>_CFURLString</key><string>file:///Applications/DS%20Launcher.app/</string><key>_CFURLStringType</key><integer>15</integer></dict></dict></dict>'
  killall Dock
fi

cat <<EOF

$(printf "\033[1;32m✓ DS Launcher is installed.\033[0m")

Next:
  1. Put your own game backups (.nds .gba .gbc .gb, or .zip/.7z containing them) in ~/Downloads, then run:
       python3 "$REPO/tools/add_games.py"
     It copies them into ~/Games and installs cheats + a cheat guide for each.
  2. Open "DS Launcher" from Applications (or Spotlight).
EOF
