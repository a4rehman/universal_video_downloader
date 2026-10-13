# OmniStream

> **One downloader. Almost every platform.**

OmniStream is a modern, SaaS-grade media downloading suite designed to extract videos, audio, images, playlists, and subtitles from virtually any web platform (YouTube, TikTok, Instagram, Twitter/X, Facebook, Pinterest, Vimeo, SoundCloud, Reddit, direct URLs, and more).

Powered by `yt-dlp`, `FFmpeg`, `Streamlit`, and `CustomTkinter`.

---

## ✨ Key Features

- 🎬 **Multi-Resolution Video Downloads**: Support for 4K (2160p), 1440p, 1080p, 720p, 480p, 360p, and raw yt-dlp format strings.
- 🎵 **High-Fidelity Audio Extraction**: Convert videos into MP3, M4A, WAV, or Opus at 320, 256, 192, or 128 kbps.
- 🖼️ **Direct Image & Thumbnail Extraction**: Download high-resolution images or embed thumbnails directly into media files.
- 💬 **Subtitle & Caption Engine**: Download manual or auto-generated SRT/VTT subtitles, or embed them into MP4 files.
- 📦 **Playlist & Channel Batch Downloader**: A channel, Shorts-tab or playlist link expands into every video, each queued as its own job with independent progress, retry and cancel. Interactive playlist checklist selector and multi-threaded batch queue.
- 🔗 **True Universal Platform Support**: One engine for every site yt-dlp supports — not a hardcoded domain list.
- 🧹 **Self-Healing Merges**: Leftover per-stream intermediates are detected and removed; a download is never reported as successful unless a real merged file exists.
- 📜 **Persistent Download History & Favorites**: Search, filter by platform or media type, sort, and re-download past items.
- ⚙️ **System Diagnostics & Auto Fallbacks**: Dynamic dependency detection for `yt-dlp`, `FFmpeg`, `FFprobe`, and `Node.js` with YouTube bot-check fallback client chains.
- 🎨 **Dual UI Options**: Modern SaaS dark glassmorphism Web UI (Streamlit) and Desktop GUI (`CustomTkinter`).

---

## 🏗️ Clean Architecture

```text
OmniStream/
├── app.py                  # Main Streamlit SaaS Web Application
├── app_gui.py              # Desktop GUI Application (CustomTkinter)
├── src/                    # Shared Downloader Engine & Business Logic
│   ├── __init__.py
│   ├── downloader.py       # Core yt-dlp downloading service & progress hooks
│   ├── extractor.py        # URL metadata analysis & playlist parser
│   ├── formats.py          # Resolution mappings & format string builder
│   ├── media.py            # Dataclasses (MediaMetadata, DownloadJob, etc.)
│   ├── queue.py            # Thread-safe download queue & worker pool
│   ├── history.py          # Download history JSON store (~/.omnistream_history.json)
│   ├── favorites.py        # Saved favorites JSON store (~/.omnistream_favorites.json)
│   ├── settings.py         # App configuration JSON store (~/.omnistream_config.json)
│   ├── validators.py       # URL syntax, platform detection, filename sanitization
│   ├── filesystem.py       # Directory management & temp file cleanup
│   ├── errors.py           # Structured error taxonomy & diagnostic mapper
│   ├── system.py           # Dependency checks (FFmpeg, Node.js, network status)
│   └── ui.py               # Glassmorphism styling & Streamlit UI helpers
├── tests/                  # Automated pytest test suite
│   ├── conftest.py
│   ├── test_errors.py
│   ├── test_formats.py
│   ├── test_history.py
│   ├── test_system.py
│   └── test_validators.py
├── test_gui_logic.py       # Desktop GUI regression tests
├── requirements.txt        # Python package requirements
├── packages.txt            # System dependencies (FFmpeg, Node.js)
├── Dockerfile              # Production Docker image configuration
└── README.md
```

---

## 🚀 Installation & Getting Started

### Prerequisites

- **Python**: 3.9 or higher
- **FFmpeg**: **Required.** YouTube and most platforms serve video and audio as two
  separate streams. FFmpeg is what merges them into one playable file. Without it a
  download lands as a video-only file (`.f399.mp4`) plus an audio-only file
  (`.f251.webm`) instead of one video.
  - `pip install imageio-ffmpeg` — ships a static build that OmniStream auto-detects. Simplest option.
  - Or install system FFmpeg: **Windows** `winget install ffmpeg`, **macOS** `brew install ffmpeg`, **Linux** `sudo apt install ffmpeg`.
  - OmniStream checks for system FFmpeg first, then falls back to the bundled build.
    The resolved path is shown in the app's System Status panel.
- **JavaScript runtime**: **Required for YouTube.** YouTube protects its streams with a
  JavaScript signature challenge. `yt-dlp` only enables **Deno** by default, so if Deno is
  missing every video fails with `This video is not available`.
  - OmniStream auto-detects **Deno, Node, Bun, or quickjs** and registers it with yt-dlp,
    even when Node is installed but not on the GUI's `PATH`.
  - Install **Node.js** (already on most machines) or Deno:
    **Windows** `winget install OpenJS.NodeJS` / `winget install DenoLand.Deno`,
    **macOS** `brew install node`, **Linux** `sudo apt install nodejs`.
  - The detected runtime is listed in the app's startup log.

### 1. Clone & Install Dependencies

```bash
git clone https://github.com/a4rehman/universal_video_downloader.git
cd universal_video_downloader

python -m venv venv
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt
```

---

## 💻 Running OmniStream

### Web Application (Streamlit)

Launch the modern SaaS web interface:

```bash
streamlit run app.py
```

Then open `http://localhost:8501` in your browser.

### Desktop Application (GUI)

Launch the native CustomTkinter desktop interface:

```bash
python app_gui.py
```

---

## 🐳 Docker Deployment

To build and run OmniStream using Docker:

```bash
docker build -t omnistream .
docker run -d -p 8501:8501 --name omnistream_container omnistream
```

Access the app at `http://localhost:8501`.

---

## 🧪 Running Tests

OmniStream includes automated unit and integration tests.

Run the core test suite:

```bash
python -m pytest tests/
```

Run the desktop GUI regression suite:

```bash
python test_gui_logic.py
```

---

## 🩺 Troubleshooting

### I got two files instead of one video

Symptom: a download produces `Title.f399.mp4` (video only) and `Title.f251.webm`
(audio only) — neither plays with sound.

Cause: FFmpeg was missing, so yt-dlp could not merge the streams. OmniStream now
fails fast with an explicit message and deletes the leftovers instead of reporting
a false success.

Fix: `pip install imageio-ffmpeg` (or install system FFmpeg), then restart the app.
Confirm the FFmpeg row in **System Status** shows a path.

### Orphan `.f###` files in my download folder

These are leftovers from an older failed merge. Safe to delete. To sweep them:

```python
from src.filesystem import cleanup_stream_artifacts
cleanup_stream_artifacts(r"A:\zareya")
```

### Channel / Shorts / playlist link says YouTube refused to list it

YouTube's browse API rejects some networks and datacenter IPs. Individual video
links (`/watch?v=...`, `youtu.be/...`) still download normally. To fix listing:

- Set browser cookies in **Settings** (close the browser first so the cookie DB is not locked).
- The GUI's activity log prints the detected FFmpeg path and any YouTube block on startup.

### "This video is not available" on every YouTube link

YouTube's signature challenge was never solved. This is a missing **JavaScript runtime**,
not a YouTube block: `yt-dlp` enables only Deno by default, so an installed Node is ignored.
Install Node.js or Deno (see [Prerequisites](#-prerequisites)); OmniStream detects it
automatically and the startup log confirms which runtime is in use.

### A batch stops after exactly `max_workers` videos

Older builds leaked a worker slot whenever a download raised, so after three failures the
pool was exhausted and the queue silently stopped. The worker loop now releases its slot in
a `finally` block, each job has a timeout (`job_timeout`), retries are bounded, and the
Active view shows `Progress: done/total` so a long run is visibly moving.

### Channel link returns fewer videos than the channel page shows

A bare `@handle` only exposes YouTube's default tab. OmniStream expands it to the
`videos`, `shorts` and `streams` tabs and merges them, so both regular uploads and Shorts are
downloaded. Tabs a channel does not have are skipped, and duplicates are removed.
Only **publicly listed** videos can be discovered — private, deleted and members-only
uploads are not visible to any downloader.

### Filenames contain `?` or the path is too long

OmniStream now passes `windowsfilenames` and `trim_file_name` to yt-dlp, so illegal
characters are replaced and long names are truncated safely. Older files already on
disk keep their old names.

---

## 🔒 Security & Privacy

- All user inputs are sanitized against path traversal (`../`) and illegal filename characters.
- Environment variables and user preferences are safely isolated.
- Downloads are executed strictly within designated target directories.

---

## 📜 Legal Notice

OmniStream is provided for downloading content that you have permission or the explicit right to access. Always respect copyright laws and platform terms of service.
