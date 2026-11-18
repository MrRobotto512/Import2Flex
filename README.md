# Import2Flex

Put a DVD (or Blu-ray) in the drive and walk away. Import2Flex:

1. notices the disc,
2. rips the main movie with **MakeMKV** straight to an `.mkv` (no ISO needed),
3. optionally re-encodes it with **HandBrake** to save space,
4. names it the way Plex likes (`Movies\The Matrix (1999)\The Matrix (1999).mkv`),
5. moves it into your Plex Movies folder and asks Plex to rescan,
6. deletes the big temporary rip files and ejects the disc for the next one.

You can also **drop `.iso` files into a watch folder** (or use *Import ISO file…*). Each one is
converted to an MKV, filed into the library, and then the ISO is deleted.

It runs in the **system tray**, can **start with Windows**, and has a simple window for
progress, settings and logs.

## What you need

| Program | Needed? | Get it |
|---|---|---|
| MakeMKV | Yes – does the actual ripping | https://www.makemkv.com/download/ |
| HandBrake **CLI** | Only if you turn on re-encoding | https://handbrake.fr/downloads2.php (the "Command Line Version") |
| Plex Media Server | To watch the movies | https://www.plex.tv |

MakeMKV is free while in beta (enter the current beta key from the MakeMKV forum in MakeMKV's
*Help → Register*), or buy a license. Open the MakeMKV app once to make sure it can read your discs.

## Install

1. Go to the repo's **Releases** page and download the latest **`Import2Flex-Setup-x.y.z.exe`**.
2. Run it. Windows SmartScreen may warn because the installer isn't code-signed; click
   **More info → Run anyway**. No admin rights are needed; you can choose "install for all users" if
   you prefer.
3. The installer adds a Start-menu shortcut, can start Import2Flex at sign-in, and offers a link to
   MakeMKV if it isn't installed. Uninstall from *Settings → Apps* like any other program; your
   settings in `%APPDATA%\Import2Flex` are kept.

**Build it yourself:** install Python 3.11+ (and [Inno Setup 6](https://jrsoftware.org/isdl.php)
for the installer), then double-click `build.bat`. You get `dist\Import2Flex\Import2Flex.exe`
and `dist\Import2Flex-Setup-x.y.z.exe`.

**Run from source:** double-click `run.bat`.

**Making a release:** bump `__version__` in `import2flex/__init__.py`, commit, then push a
matching tag (e.g. `git tag v1.0.1 && git push origin v1.0.1`). GitHub Actions builds the
installer and publishes it as a release.

## First run

The Settings tab opens automatically:

1. **Plex Movies folder** – the folder your Plex "Movies" library points to.
2. **Temporary rip folder** – needs ~8 GB free per DVD (~50 GB per Blu-ray). Putting it on the
   same drive as your Movies folder makes the final move instant.
3. Click **Check setup** to confirm MakeMKV is found, then **Save settings**.
4. Tick **Start Import2Flex when I sign in to Windows** if you want it always running.

Insert a DVD. The tray icon gets a green dot while it's working and you get a notification when
the movie is in your library.

## Settings worth knowing

- **Ask me to confirm the movie name** – a box pops up with the guessed name while ripping
  continues. Edit it or let the countdown accept the guess.
- **TMDb API key** (free at themoviedb.org → Settings → API) – turns a label like `MATRIX_WS`
  into the exact title and year, `The Matrix (1999)`, so Plex matches it reliably. Without it the
  name comes from the disc label, which is usually close but has no year.
- **Plex token** – makes Plex scan the new movie immediately instead of on its own schedule.
  [How to find your token](https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/).
- **What to rip** – *Main movie only* (default) or *All titles*, which puts extras in an
  `Other` subfolder Plex shows as extras.
- **Skip titles shorter than** – ignores menus, trailers and warnings (default 20 min).
- **Re-encode with HandBrake** – a raw DVD rip is 4–8 GB; `H.265 MKV 480p30` usually brings
  that to 1–2 GB with no visible difference, but takes a while. The drive is free for the next
  disc while the previous movie encodes.

## Where things live

- Settings: `%APPDATA%\Import2Flex\config.json`
- Log file: `%APPDATA%\Import2Flex\import2flex.log` (also shown on the *Log* tab)

## Troubleshooting

- **"MakeMKV not found"** – set the path to `makemkvcon64.exe` (normally
  `C:\Program Files (x86)\MakeMKV\`) in Settings.
- **Rip fails right away** – open the MakeMKV app; the beta key may have expired.
- **Disc isn't detected** – only discs with a `VIDEO_TS` (DVD) or `BDMV` (Blu-ray) folder are
  imported automatically. Use *Import disc now* to force it.
- **Wrong movie name** – rename the folder and file in Explorer, then use *Refresh Metadata* in
  Plex, or turn on the confirm-name popup.

Only rip discs you own, and check the laws where you live.

## Development

```bash
pip install -r requirements-dev.txt
```

```bash
python -m pytest -q
```

Code layout: `import2flex/pipeline.py` is the engine (drive watcher → rip thread → encode/move
thread), `makemkv.py` / `handbrake.py` wrap the command-line tools, `drives.py` does Windows drive
detection and eject, `startup.py` handles the Run-at-login registry entry, and `gui/` plus
`app.py` hold the tray icon and window.
