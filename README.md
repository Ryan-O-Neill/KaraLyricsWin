[README.md](https://github.com/user-attachments/files/33224780/README.md)
# Lyric Visualizer for Spotify (Windows)

A small Python app that shows animated, karaoke-style lyrics in sync with whatever is playing in the Spotify desktop app on Windows.

* No Spotify API keys, developer app, or Premium subscription needed
* Works with any song that has time-synced lyrics, not just one track
* Animated background, line-by-line highlight fill, and a progress bar
* Pause/resume and fine-tune the sync from the keyboard

> Windows only. The app reads from the Windows media session (the same info that appears in the volume flyout), so it won't run on macOS or Linux.

\---

## How it works

1. Spotify tells Windows what's playing and how far into the song you are.
2. The app reads that through the Windows media session.
3. It looks up time-stamped lyrics for the song on [LRCLIB](https://lrclib.net), a free community lyrics database.
4. It draws the current line and highlights it as the song progresses.

The lyrics are not bundled with this project. They are fetched from LRCLIB at runtime, so you need an internet connection.

\---

## Requirements

* Windows 10 or 11
* Python 3.9 or newer, with `py` launcher (included in the standard python.org installer)
* The **Spotify desktop app** (not the web player). A free account is fine.

\---

## Install

Open PowerShell and run:

```powershell
# 1. Check Python is installed
py --list

# 2. Update pip (replace 3.9 with the version you want to use)
py -3.9 -m pip install --upgrade pip

# 3. Install dependencies (one long line)
py -3.9 -m pip install pygame requests winrt-runtime winrt-Windows.Media.Control winrt-Windows.Foundation winrt-Windows.Foundation.Collections
```

Then download `lyricvisualizerwindows.py` from this repository.

\---

## Run

1. Open the **Spotify desktop app** and start playing a song.
2. In PowerShell, go to the folder containing the script and run it:

```powershell
cd $HOME\\Downloads
py -3.9 lyricvisualizerwindows.py
```

A window opens, shows "Fetching lyrics..." for a moment, and then the lyrics start following the music.

### Controls

|Key|Action|
|-|-|
|`Space`|Pause / resume Spotify|
|`Left arrow`|Shift lyrics 100 ms earlier|
|`Right arrow`|Shift lyrics 100 ms later|
|`Esc`|Quit|

The current sync trim is shown at the bottom of the window. If the lyrics feel slightly early or late (common with Bluetooth headphones), nudge them with the arrow keys.

\---

## Troubleshooting

**`pip install pygame` fails with a long build error mentioning `distutils` or `msvccompiler`**
You're probably using a very new Python (for example 3.14) that pygame doesn't have prebuilt packages for yet. Install and use Python 3.9 to 3.13 instead, and run everything with `py -3.x` so the right version is used.

**`python --version` and `pip --version` show different Pythons**
Several Python installs can coexist. Avoid bare `pip`. Use `py -3.9 -m pip ...` and `py -3.9 script.py` so both use the same install. `py --list` shows what you have.

**`No matching distribution found for winrt-Windows.Foundation.Collection`**
Typo. The package name ends in an *s*: `winrt-Windows.Foundation.Collections`.

**The window says "Open the Spotify desktop app and press play..."**
The app can't see a Spotify media session. Make sure you're using the desktop app (not a browser tab), that a song is actually playing, and that Spotify's Windows media controls appear when you change the volume.

**"No synced lyrics found for this track."**
LRCLIB doesn't have time-synced lyrics for that recording. Try another song or a different version of the track.

**Lyrics are consistently early or late**
Use the left/right arrow keys. Each press shifts the timing by 100 ms.

**Lyrics drift or jump after skipping around in the song**
The position is re-read about 2.5 times per second, so it should correct itself within a moment. If it doesn't, pause and resume once.

\---

## FAQ

**Why not use the Spotify Web API?**
Spotify tightened its developer-mode rules in early 2026, and as of that change, creating and keeping a developer app requires a Premium subscription. Playback control also requires Premium. Reading the Windows media session avoids all of that. Spotify's API also doesn't provide lyrics or lyric timings, so a separate lyrics source would be needed either way.

**Does this play the music itself?**
No. Spotify plays the audio. This app only displays lyrics in sync with it.

**Can I use it with other music apps?**
The script looks specifically for Spotify's media session. You could adapt it by changing the `"spotify"` check in `poll\_media\_session`.

\---

## Notes

* Lyrics are copyrighted by their owners. This project doesn't store or distribute them. They are retrieved on demand from LRCLIB for personal use.
* This project is not affiliated with or endorsed by Spotify or LRCLIB.
* Please be considerate of LRCLIB, which is a free community service. The app only requests lyrics when the track changes.

## Credits

* Lyrics data: [LRCLIB](https://lrclib.net)
* Rendering: [pygame](https://www.pygame.org)
* Windows media session access: [winrt Python projection](https://pypi.org/project/winrt-runtime/)

## License

Add a license of your choice before sharing (for example MIT) by placing a `LICENSE` file next to this README.

