---
title: VideoUtil Bot
emoji: 🎬
colorFrom: red
colorTo: purple
sdk: docker
app_file: Dockerfile
app_port: 7860
pinned: false
---

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-blue?style=for-the-badge&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/WZGram-Pyrogram-0088cc?style=for-the-badge&logo=telegram&logoColor=white" alt="WZGram">
  <img src="https://img.shields.io/badge/FFmpeg-Required-orange?style=for-the-badge&logo=ffmpeg&logoColor=white" alt="FFmpeg">
  <img src="https://img.shields.io/badge/MongoDB-Motor-green?style=for-the-badge&logo=mongodb&logoColor=white" alt="MongoDB">
  <img src="https://img.shields.io/badge/MediaInfo-Reports-blueviolet?style=for-the-badge&logo=readme&logoColor=white" alt="MediaInfo">
</p>

<h1 align="center">VideoUtil - Video Compressor Bot</h1>

<p align="center">
  A Telegram bot that compresses videos, downloads links, and does many
  small editing jobs (crop, cut, merge, subtitles, audio, watermark, and more).
  It also has a settings page you can open in your browser.
</p>

<p align="center">
  <a href="https://youtube.com/@NexonBots">
    <img src="https://img.shields.io/badge/YouTube-Subscribe-FF0000?style=for-the-badge&logo=youtube&logoColor=white" alt="YouTube">
  </a>
  <a href="https://t.me/NexonBots">
    <img src="https://img.shields.io/badge/Telegram-Channel-26A5E4?style=for-the-badge&logo=telegram&logoColor=white" alt="Telegram">
  </a>
</p>

---

## What the bot can do

| Feature | What it does |
|---------|--------------|
| **Compress video** | Makes video files smaller. You choose quality, preset and sound size with `/encsettings` |
| **One-tap sizes** | `/144p` `/240p` `/360p` `/480p` `/720p` `/1080p` `/4k` — one command, done |
| **Download links** | `/leech` downloads magnets, torrents, direct links and MEGA links, then uploads the result |
| **Split big files** | Files bigger than Telegram's limit are cut into parts and uploaded one by one |
| **Crop** | `/crop` — cut out one part of a video |
| **Cut** | `/cut` — break one video into smaller time parts |
| **Merge** | `/merge` — join many video parts into one file |
| **Subtitles** | `/extract_sub` `/sub` `/hsub` `/rsub` — take out, add, or burn subtitles |
| **Audio tools** | `/extract_audio` `/remaudio` `/addaudio` — take out, replace, or add a sound track |
| **Watermark** | `/setwatermark` `/addwatermark` — put your mark on a video |
| **Thumbnail** | `/setthumb` `/addthumb` — set the cover picture for uploads |
| **Screenshots** | `/ss` — make a picture sheet from a video |
| **MediaInfo report** | `/mediainfo` — full report of a file |
| **Metadata editor** | `/settitle` `/setauthor` `/setallmeta` — change title/artist tags on outputs |
| **Force subscribe** | People must join your channel before using the bot (with Join Request support) |
| **Premium plans** | `/addpaid` `/rempaid` `/myplan` — paid user plans with expiry |
| **Settings page** | `/settings` opens a browser page: delivery place, spoiler, thumbnail, upload channel |
| **Live status** | One status card per chat, refreshed every 8 seconds, shows all running tasks |
| **Git updater** | `/update` pulls the newest code from this repository |
| **Admin tools** | `/exec` `/eval` `/log` `/stats` `/speedtest` `/restart` with audit log |
| **Dump channel** | Every finished upload is also copied to your private dump channel (optional) |

---

## Requirements

| Thing | Needed? | Note |
|-------|---------|------|
| **Python 3.11+** | Yes | Streamlit and the container image already use 3.11 |
| **FFmpeg** | Yes | Used for all video work |
| **MediaInfo** | Yes | Used for `/mediainfo` |
| **MongoDB** | Yes | Free plan at [mongodb.com](https://www.mongodb.com) |
| **Telegram API** | Yes | Take it from [my.telegram.org](https://my.telegram.org) |
| **Git** | No | Only for `/update` (already inside Docker/Streamlit) |
| **Megatools** | No | Only for MEGA links in `/leech` |
| **7z (p7zip-full)** | No | Faster extract for 7z/rar/iso and password zip. Installed by default in Docker and Streamlit |

---

## Quick setup (Streamlit Cloud)

1. Make a new app from this repository. Entrypoint: `app.py`, Python 3.11.
2. Open `.streamlit/secrets.toml.example`, copy everything, and paste it into
   **Advanced settings → Secrets**. Fill in your own values.
3. Press Deploy. That's it — `packages.txt` installs FFmpeg, MediaInfo,
   Megatools, Git, curl and 7z for you.

### Quick setup: Docker Compose (VPS)

```bash
git clone https://github.com/PrimeSujoy/VideoUtil.git
cd VideoUtil
cp .env.example .env
# open .env and fill your values
docker compose up -d --build
docker compose logs -f
```

Health check: `http://SERVER_IP:7860/health`.

### Run on your own computer

```bash
cp .env.example .env            # fill in your values
python -m pip install -r requirements.txt
python -m bot                   # bot only
```

or with the control panel:

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml  # fill in values
streamlit run app.py
```

Other platforms (Heroku, Northflank, Koyeb, Google Cloud, Colab...) are
explained step by step in **[DEPLOYMENT.md](DEPLOYMENT.md)**.

> Run only **one** bot at a time. Two bots with the same token clash with
> `Conflict: terminated by other getUpdates`.

---

## Configuration (secrets)

Two short lists: things you **must** fill, and things you can **leave empty**.

**Must fill:**

| Name | What it is |
|------|------------|
| `APP_ID` / `API_HASH` | From [my.telegram.org](https://my.telegram.org) |
| `TG_BOT_TOKEN` | From [@BotFather](https://t.me/BotFather) |
| `BOT_USERNAME` | Your bot name, without the `@` |
| `AUTH_USERS` | Your Telegram user ID (and group IDs) who may use commands, separated by space |
| `LOG_CHANNEL` | A log channel `@name` or `-100...` ID. The bot needs to be admin there |
| `DB_URL` / `DB_NAME` | MongoDB address and database name |

**Optional (leave empty if you don't need them):**

| Name | What it is |
|------|------------|
| `DUMP_CHANNEL` | Dump channel ID. See the dump section below. Empty = off |
| `SESSION_NAME` | Session file name (default `AHCompressorBot`) |
| `UPDATES_CHANNEL`, `PICS` | Branding pictures/links |
| `USER_SESSION_STRING`, `STRING_API_ID`, `STRING_API_HASH`, `SESSION_USER_ID` | Premium user session — needed only for `/leech -ut` (upload by user account, up to 4 GB) |
| `UPSTREAM_REPO`, `GIT_TOKEN` | Repository + token used by `/update` (token needed for private repos) |
| `WORK_DIR` | Where downloads live (Docker image uses `/data`) |
| `PORT` | Health port (Docker image uses `7860`) |

Real environment variables always beat `.env`. Never commit real secrets —
`.gitignore` and `.dockerignore` already ignore them.

---

## Dump channel (optional)

The bot can make a **private copy** of everything it uploads — a backup shelf
just for you.

1. Make a Telegram channel (or use any group).
2. Add your bot there as **admin**.
3. Copy the channel ID. It looks like `-1004389836505`.
4. Put it in your secrets:

```toml
# .streamlit/secrets.toml
DUMP_CHANNEL = "-1004389836505"
```

or in `.env`:

```bash
DUMP_CHANNEL=-1004389836505
```

5. Restart the bot.

What goes to the dump:

- every finished **video** upload (leech, compress, cut, merge, everything)
- every **file** upload of any type (zip, mkv, mp3, pdf, ...)
- every split **part**

What does **not** go there:

- screenshots (`/ss` albums)
- photos and thumbnails
- log files, reports and status messages

Leave `DUMP_CHANNEL` empty and the dump is switched off. If the copy fails,
the bot only writes a warning — your real upload never breaks.

---

## Commands

Open `/help` in Telegram for the full list (the bot also pushes every command
into Telegram's command menu on startup). The main ones:

| Command | What it does |
|---------|--------------|
| `/start` `/ping` | Welcome, uptime |
| `/help` | Full command list |
| `/compress` | Compress the video you reply to |
| `/144p` `/240p` `/360p` `/480p` `/720p` `/1080p` `/4k` | One-tap compress |
| `/settings` | Your settings page (delivery, spoiler, thumbnail, channel) |
| `/encsettings` `/resetsettings` | Admin encoding panel / restore defaults |
| `/leech` (`/l`) | Download a link or file and upload the result |
| `/leechhelp` | Full `/leech` flag list with examples |
| `/crop` `/cut` `/merge` | Cut area, cut time, join parts |
| `/extract_audio` `/remaudio` `/addaudio` | Sound track tools |
| `/extract_sub` `/sub` `/hsub` `/rsub` | Subtitle tools |
| `/setwatermark` `/addwatermark` `/getwatermark` `/delwatermark` | Watermark |
| `/extract_thumb` `/setthumb` `/getthumb` `/delthumb` `/addthumb` | Thumbnail |
| `/ss` | Screenshot sheet |
| `/mediainfo` (`/mi`) | File report |
| `/metadata` `/settitle` `/setauthor` `/setallmeta` | Output tags |
| `/addchnl` `/delchnl` `/listchnl` `/fsub_mode` | Force-subscribe setup |
| `/shortner` `/shortlink1` `/tutorial1` | Shortlink gates and tutorials |
| `/addpaid` `/rempaid` `/listpaid` `/myplan` | Premium plans |
| `/status` (`/queue`) `/cancelall` | Task list and mass cancel |
| `/setchannel` `/getchannel` `/delchannel` | Default upload place |
| `/stats` `/setmedia` `/spoiler` `/upload` | Small preference switches |
| `/speedtest` `/update` `/restart` `/log` | Server tools |
| `/exec` `/eval` | Admin shell / Python (audited) |

---

## `/leech` — how it works

`/leech` takes a link (or a file you reply to), downloads it, does whatever
you asked with **flags**, then uploads the result.

```text
/leech LINK -flag1 -flag2 value
```

Simple rule: **write the link first, then the flags.**

```text
/leech https://site.com/file.zip -e -z
/leech magnet:?xt=urn:btih:... -ss -sv
/leech https://site.com/movie.mkv -cv mp4 -n My Movie
```

### All flags (short and simple)

| Flag | What it does |
|------|--------------|
| `-e` | Extract the archive after download |
| `-e password` | Extract a password protected archive |
| `-z` | Zip the result before upload |
| `-z password` | Make a password protected zip |
| `-j` | Join split parts (`.001 .002 ...`) into one file first |
| `-n name` | Rename the download (e.g. `-n My Movie.mkv`) |
| `-m folder` | Put the result inside a folder with this name |
| `-ns pattern:replace:count:FLAG` | Rename files by pattern (regex) |
| `-ss` | Make 10 screenshots (`-ss 6` = six of them) |
| `-sv` | Make a short sample video (`-sv 70:5` = 70s, 5 parts) |
| `-cv mp4` | Convert video to another container (`-cv mkv - webm flv` also works) |
| `-ca mp3` | Convert audio (`-ca mp3 + flac ogg` = only those, `-ca mp3 - flac ogg` = all but those) |
| `-meta title=Name\|artist=Someone` | Set container metadata (supports `{filename}` `{basename}` `{extension}` `{year}`) |
| `-t image-url` | Use a picture from a link as thumbnail |
| `-t https://t.me/chan/12` | Use a Telegram picture as thumbnail |
| `-t none` | Send without thumbnail |
| `-tl 3x3` | Build a grid thumbnail from video frames |
| `-sp 500mb` | Split size (mb/gb or raw bytes) |
| `-doc` | Upload as document file |
| `-med` | Upload as streamable media |
| `-hl` | Hybrid: big parts by user session, small parts by bot |
| `-bt` | Force bot client only |
| `-ut` | Force your user session only (needs `USER_SESSION_STRING`) |
| `-h key: value key2: value2` | Custom download headers |
| `-au user -ap pass` | HTTP basic auth for the link |
| `-b` | Bulk: reply to a text/txt file with one link per line |
| `-b 2:5` | Bulk with a line range (2 to 5) |
| `-i 3` | Only the first 3 links |
| `-f` | Skip all queues (download + upload + processing) |
| `-fd` | Skip the download queue only |
| `-fu` | Skip the upload queue only |
| `-ff ["-i mltb.mkv -c copy mltb.mkv"]` | Custom ffmpeg command — **owner only** |

Flags that are **not working yet** (they will come later, or they are not
possible with the current download engine): `-up -ud -gc -rcf -sync` (rclone
upload/sync), `-s` (file pick), `-d` (seeding), `-ad` (AllDebrid), `-seedr`,
`-yt` (YouTube upload). If you use one, the bot stops the task and tells you.

A few flags also work on the **other** commands (compress, extract_audio,
cut, merge, ...): `-n`, `-doc`, `-med`, `-t`, `-sp`.

Example:

```text
/720p -n Compressed Movie -sp 1.9gb -doc
```

Type `/leechhelp` in the bot to see all of this inside Telegram.

### How big files are split

- **Videos** split by the mode you chose in your settings: *Normal split*
  (keeps playable parts) or *Binary split* (raw bytes).
- **Everything else** (zip, rar, pdf, any other extension) always uses
  **Binary split** — rejoining the parts gives a byte-for-byte identical file.
- A part is cut a little below Telegram's real limit (2 GB for a bot,
  4 GB with a premium user session), so nothing is rejected on upload.
- Binary parts are uploaded as documents.

---

## Telegram library (WZGram)

The bot talks to Telegram through [WZGram](https://pypi.org/project/wzgram/),
pinned to one exact tested version in `requirements.txt`. WZGram provides the
usual `pyrogram` names, so all `from pyrogram import ...` lines simply use
WZGram — only this one Telegram library is installed.

**Update notifier (it only tells, it never changes anything).** 60 seconds
after start, a background task checks PyPI once every 24 hours. If a newer
stable release exists, every ID in `AUTH_USERS` gets one message with the
installed version, the new version and a copy-paste install command. The same
version is never announced twice. The checker never installs packages, never
edits files and never restarts the bot — you update by hand.

**Making a new `USER_SESSION_STRING`** (only if Telegram rejects the stored
value) — build it with WZGram, since that is the only library installed:

```python
import asyncio
from wzgram import Client

async def main():
    app = Client("gen", api_id=APP_ID, api_hash=API_HASH,
                 phone_number="+1234567890", in_memory=True)
    async with app:  # type your phone number and login code
        print(await app.export_session_string())

asyncio.run(main())
```

Old `.session` files keep working as they are (this bot has used its original
session file with WZGram since V-1.2.0). If the stored string is rejected, the
bot logs a warning and quietly falls back to normal 2 GB bot uploads — paste a
fresh string to get the 4 GB route back. Never log, commit or paste
`TG_BOT_TOKEN`, `USER_SESSION_STRING` or `GIT_TOKEN`.

---

## Project folders

```
VideoUtil/
├── app.py                  # Streamlit panel (start/stop bot + live log)
├── database.py             # MongoDB operations
├── bot/
│   ├── __main__.py         # Bot start, health server, command menu
│   ├── config.py           # Reads all settings from environment
│   ├── leech.py            # /leech + /leechhelp + bulk downloads
│   ├── compress.py         # Compression presets
│   ├── audio.py / crop.py / split_videos.py / merge_video.py
│   ├── subtitles.py / watermark.py / thumbnail.py / screenshot.py
│   ├── fsub.py / premium.py / metadata.py / features.py
│   ├── encoding_settings.py / status_commands.py
│   ├── task_manager.py     # Queues: 5 downloads, 1 heavy task, 1 upload
│   ├── group_status.py     # Live status card (8s refresh)
│   ├── helper_funcs/       # ffmpeg, uploads, splits, dump, extract, ...
│   └── plugins/            # message / callback / status plugins
├── requirements.txt        # Python packages
├── packages.txt            # System packages (ffmpeg, git, p7zip-full, ...)
├── .env.example            # Template for local runs
├── .streamlit/secrets.toml.example
├── Dockerfile / docker-compose.yml / Procfile / app.json
├── VideoUtil_Colab.ipynb   # Google Colab runner
└── DEPLOYMENT.md           # Step-by-step for every platform
```

---

## Troubleshooting

**`Conflict: terminated by other getUpdates request`**
: Something else uses the same bot token. Keep exactly one running copy.

**Health check fails**
: The platform must set `PORT` (image default `7860`) and call `/health`.

**Bot closes right away**
: Check `APP_ID`, `API_HASH`, `TG_BOT_TOKEN`, `AUTH_USERS`, `LOG_CHANNEL`
  and `DB_URL`. On MongoDB Atlas, allow your host's IP (`0.0.0.0/0` if the IP
  keeps changing).

**FFmpeg not found**
: Use this repository's Dockerfile, or run `apt install ffmpeg mediainfo git`
  on a VPS.

**Bot sleeps after idle time**
: Streamlit Community Cloud puts apps to sleep after 12 hours without web
  traffic — open the app URL to wake it, or use Docker/VPS for 24/7.

**`/update` fails**
: Set `UPSTREAM_REPO` and `GIT_TOKEN`. The Docker image already has Git.

**Files not landing in your dump channel**
: Make sure the bot is **admin** in `DUMP_CHANNEL`, the ID has the
  `-100...` form, and the bot was restarted after the change.

---

# Don't Remove Credit Tg - @NexonBots
# Subscribe YouTube Channel For Amazing Bot https://youtube.com/@NexonBots
# Ask Doubt on telegram @NexonContactBot

---

## Support

- **Telegram:** [@NexonContactBot](https://t.me/NexonContactBot)
- **Channel:** [@NexonBots](https://t.me/NexonBots)
- **YouTube:** [@NexonBots](https://youtube.com/@NexonBots)

## License

This project is open source. Use responsibly. See [LICENSE](LICENSE).
