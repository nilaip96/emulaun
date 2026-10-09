<p align="center"><img src="docs/icon.png" width="128" alt="DS Launcher icon"></p>

<h1 align="center">DS Launcher</h1>

<p align="center">A small, offline game library for <a href="https://melonds.kuribo64.net/">melonDS</a> on macOS: your Nintendo DS games in one grid, one-click play, and a checkbox list of cheats for every game.</p>

<p align="center"><img src="docs/screenshot-grid.png" alt="DS Launcher grid view" width="900"></p>
<p align="center"><img src="docs/screenshot-list.png" alt="DS Launcher list view with game details" width="900"></p>
<p align="center"><sub>Screenshots use a made-up demo library (<code>docs/make_demo.py</code>), not real games.</sub></p>

---

## Features

- **Native Mac app**: its own window and Dock icon, about 1 MB. When you quit it, nothing keeps running in the background.
- **Grid or list view.** The list view shows your games on the left and the selected game's details on the right (<kbd>↑</kbd> <kbd>↓</kbd> to browse, <kbd>Return</kbd> to play).
- **Library** with each game's real DS icon (read from the game file). Sort by **Recent**, **A–Z** or **Color**, and search.
- **Per-game colors** taken from each icon and used for the card glow, the pop-up and the Play button.
- **Game pop-up** with:
  - **Play**, which starts melonDS with the game
  - your in-game save and save states with their times (F1–F8 loads a state)
  - every cheat as a checkbox, with a Favorites folder at the top, search, and "pick one" folders
- **Cheat importer** (`tools/add_games.py`). It takes games from `~/Downloads` (`.nds`, `.zip` or `.7z`), files them into `~/Games`, matches each one to the right cheat set by game ID and header checksum, and writes:
  - a melonDS cheat file (`.mch`): an automatic Favorites list plus every code, all off by default
  - a plain-text cheat guide
- **Fully offline** once installed.

> **No games are included.** Use backups of games you own. This repo contains only the launcher code.

## Install

Requires macOS 12+ (Intel or Apple Silicon).

```bash
git clone https://github.com/nilaip96/ds-launcher.git
cd ds-launcher
./install.sh --dock
```

The installer:

1. Installs Apple's Command Line Tools if they're missing. A system dialog appears; finish it and re-run the script.
2. Downloads **melonDS** from its official GitHub releases, if it isn't already in `/Applications`.
3. Creates `~/Games/Pokemon`, `~/Games/DS` and `~/Games/cheat-tools`, and downloads the cheat database once (about 100 MB).
4. Builds **DS Launcher.app** from source and puts it in `/Applications`.
5. With `--dock`, adds it to your Dock.

The script is safe to re-run, and it never touches your games or saves.

## Add games

Put your game backups in `~/Downloads`, then run:

```bash
python3 tools/add_games.py            # import + install cheats
python3 tools/add_games.py --dry-run  # just show what it would do
```

- Games already in your library are skipped.
- Pokémon games go to `~/Games/Pokemon`, everything else to `~/Games/DS`.
- Your Downloads folder is never modified.
- New games appear in DS Launcher on their own.

## Using cheats

1. Open a game's pop-up and tick the cheats you want. They apply the next time you start that game.
2. Flip the **Cheats** switch in the pop-up to ON. melonDS has one cheat switch shared by every game.
3. "Always on" cheats just work. Others need the button combo shown, like `L+R`; press the buttons together.

Tips:

- Make a save state (`Shift+F1`) before trying a new cheat. `F1` jumps back.
- Cheats that patch game code keep running until the game restarts.
- Each game's `… - Cheat Guide.txt` (also under **Cheat guide** in the pop-up) lists every code with notes.

### Suggested melonDS keys

In melonDS, go to **Config → Input and hotkeys**. Mapping **Start → Return** and **Select → Shift** stops cheat combos like `L+R+Start` from pressing `⌘Q` by accident. Set a **fast-forward** hotkey (e.g. hold `Tab`) too.

## Run in a browser instead

```bash
python3 launcher/launcher.py   # opens http://127.0.0.1:8765, stops when you close the tab
```

## How it works

| Path | What it is |
| --- | --- |
| `launcher/launcher.py` | Tiny local server (Python standard library only, bound to `127.0.0.1`). Lists games, reads icons from DS ROM banners, launches melonDS, and reads/writes `.mch` cheat files. |
| `launcher/index.html` | The whole UI, with no external libraries. |
| `app/main.swift` | Native window (WKWebView). Starts the server on launch and stops it on quit. |
| `app/make_icon.swift` | Draws the app icon in code. |
| `app/build.sh` | Builds `DS Launcher.app`. |
| `tools/add_games.py` | Game importer and cheat installer. |
| `install.sh` | One-shot setup. |

Your files live in `~/Games/<folder>/` and the repo never stores them:
- `Game.nds`: the game
- `Game.sav`: in-game save
- `Game.ml1`–`ml8`: save states
- `Game.mch`: cheat file
- `Game - Cheat Guide.txt`: cheat guide

## Credits

- [melonDS](https://github.com/melonDS-emu/melonDS), the emulator
- [DeadSkullzJr's NDS(i) Cheat Databases](https://github.com/szTheory/NDS-Cheat-Databases) (mirror), the cheat codes. Downloaded at install time; not included in this repo.

## License

MIT, for the launcher code only. See [LICENSE](LICENSE).
