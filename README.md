# OmniStream

> **One downloader. Almost every platform.**

OmniStream is a modern, SaaS-grade media downloading suite designed to extract videos, audio, images, playlists, and subtitles from virtually any web platform (YouTube, TikTok, Instagram, Twitter/X, Facebook, Pinterest, Vimeo, SoundCloud, Reddit, direct URLs, and more).

Powered by `yt-dlp`, `FFmpeg`, and `Streamlit`.

---

## ✨ Key Features

- 🎬 **Multi-Resolution Video Downloads**: Support for 4K (2160p), 1440p, 1080p, 720p, 480p, 360p, and raw yt-dlp format strings.
- 🎵 **High-Fidelity Audio Extraction**: Convert videos into MP3, M4A, WAV, or Opus at 320, 256, 192, or 128 kbps.
- 🖼️ **Direct Image & Thumbnail Extraction**: Download high-resolution images or embed thumbnails directly into media files.
- 💬 **Subtitle & Caption Engine**: Download manual or auto-generated SRT/VTT subtitles, or embed them into MP4 files.
- 📦 **Playlist & Channel Batch Downloader**: Channel, Shorts-tab, or playlist links expand into every video, each queued as its own background job with independent progress, retry, and cancel. Interactive playlist checklist selector and multi-threaded batch queue.
- 🎞️ **Robust Instagram Support**: Distinguishes collections (profiles and reels listings) from individual Reels/Posts. Discovers accessible Reels and prevents attempting to download profile URLs directly.
- 💾 **Browser & Cloud Friendly**: Download files directly to your device via browser download actions (`Save to Device`), clearly distinguishing server-side files from browser-downloaded files.
- 🧹 **Self-Healing Merges**: Leftover per-stream intermediates are detected and removed; a download is never reported as successful unless a real merged file exists.
- 📜 **Persistent Download History & Favorites**: Search, filter by platform or media type, sort, and re-download past items.
- ⚙️ **System Diagnostics & Auto Fallbacks**: Dynamic dependency detection for `yt-dlp`, `FFmpeg`, `FFprobe`, and `Node.js` with YouTube bot-check fallback client chains.
- 🎨 **Pure Browser Web UI**: Modern SaaS dark glassmorphism interface running entirely in your browser using Streamlit.

---

## 🏗️ Clean Architecture

```text
OmniStream/
├── app.py                  # Main Streamlit Web Application (Single Entry Point)
├── src/                    # Shared Downloader Engine & Business Logic
│   ├── __init__.py
│   ├── database.py         # TiDB Cloud Serverless persistence, migrations & offline fallback
│   ├── downloader.py       # Core yt-dlp downloading service & progress hooks
│   ├── extractor.py        # URL metadata analysis & playlist parser
│   ├── formats.py          # Resolution mappings & format string builder
│   ├── media.py            # Dataclasses (MediaMetadata, DownloadJob, etc.)
│   ├── platforms.py        # Platform capability registry & diagnostics
│   ├── queue.py            # Thread-safe download queue & worker pool
│   ├── history.py          # Download history persistence (TiDB Cloud / local JSON fallback)
│   ├── favorites.py        # Saved favorites persistence (TiDB Cloud / local JSON fallback)
│   ├── settings.py         # App configuration persistence (TiDB Cloud / local JSON fallback)
│   ├── validators.py       # URL syntax, platform detection, filename sanitization
│   ├── filesystem.py       # Directory management & temp file cleanup
│   ├── errors.py           # Structured error taxonomy & diagnostic mapper
│   ├── system.py           # Dependency checks (FFmpeg, Node.js, network status, TiDB health)
│   ├── instagram_scraper.py# Cookie-free & session Instagram Reel extractor
│   └── ui.py               # Glassmorphism styling & Streamlit UI helpers
├── tests/                  # Automated pytest test suite
│   ├── conftest.py
│   ├── test_audit_enhancements.py # File verification & FFmpeg checks
│   ├── test_browser_web_suite.py  # Comprehensive browser UI & Instagram tests
│   ├── test_database.py    # TiDB Cloud CRUD, parameterization & offline fallback tests
│   ├── test_downloader.py
│   ├── test_errors.py
│   ├── test_extractor.py
│   ├── test_formats.py
│   ├── test_history.py
│   ├── test_regressions.py # Queue execution, duplicate prevention & platform regressions
│   ├── test_system.py
│   └── test_validators.py
├── .env.example            # Safe template for TiDB Cloud credentials
├── requirements.txt        # Python package requirements (pure web/backend)
├── packages.txt            # System dependencies for Streamlit Cloud (FFmpeg, Node.js)
├── Dockerfile              # Production Docker image configuration
└── README.md
```

---

## 🚀 Installation & Getting Started

### Prerequisites

- **Python**: 3.9 or higher
- **FFmpeg**: **Required.** YouTube and most platforms serve video and audio as two separate streams. FFmpeg is what merges them into one playable file. Without it a download lands as an unmerged video-only file plus an audio-only file.
  - `pip install imageio-ffmpeg` — bundles a static build that OmniStream auto-detects. Simplest option.
  - Or install system FFmpeg: **Windows** `winget install ffmpeg`, **macOS** `brew install ffmpeg`, **Linux** `sudo apt install ffmpeg`.
  - OmniStream checks for system FFmpeg first, then falls back to the bundled build. The resolved path is displayed in the app's System Status panel.
- **JavaScript runtime**: **Recommended for YouTube.** YouTube protects some streams with a signature challenge.
  - OmniStream auto-detects **Deno, Node, Bun, or quickjs** and registers it with yt-dlp.
  - Install **Node.js** or **Deno**:
    **Windows** `winget install OpenJS.NodeJS`, **macOS** `brew install node`, **Linux** `sudo apt install nodejs`.

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

Launch the browser application using Streamlit:

```bash
python -m streamlit run app.py
```

Then open `http://localhost:8501` in your browser.

---

## 🐳 Docker Deployment

To build and run OmniStream using Docker:

```bash
docker build -t omnistream .
docker run -d -p 8501:8501 --name omnistream_container omnistream
```

Access the application in your browser at `http://localhost:8501`.

---

## 🧪 Running Automated Tests

OmniStream includes automated unit and integration tests covering URL validation, platform classification, Instagram collection and reel discovery, queue management, duplicate prevention, and download verification. All network calls are mocked in the test suite.

Compile check:

```bash
python -m compileall .
```

Run test suite:

```bash
python -m pytest tests/ -q
```

Run headless browser test:

```bash
python -m streamlit run app.py --server.headless true
```

---

## 📸 Instagram Platform Notes

- **Collections vs Individual Reels**: Profile and `/reels/` URLs are treated as collections. OmniStream discovers accessible individual Reel URLs and allows selecting them.
- **Direct Downloads**: Individual Reel URLs (`/reel/...`) and Post URLs (`/p/...`) download directly.
- **Platform Limitations**: Anonymous access to Instagram is subject to platform rate limits and authentication restrictions. If a profile requires login or is private, OmniStream displays a helpful guidance message to copy direct Reel links rather than failing silently or attempting to download the profile URL.

---

## ☁️ TiDB Cloud Serverless Integration

OmniStream integrates with **TiDB Cloud Serverless** (a MySQL-compatible distributed relational database) for durable cloud storage of:
- Download history
- Favorite bookmarked URLs
- User application settings & preferences

### 1. Connection Configuration

You can configure TiDB Cloud via environment variables or a local `.env` file (copied from `.env.example`):

```bash
TIDB_HOST=gateway01.us-east-1.prod.aws.tidbcloud.com
TIDB_PORT=4000
TIDB_USER=your_cluster_prefix.root
TIDB_PASSWORD=your_cluster_password
TIDB_DATABASE=omnistream
TIDB_SSL_MODE=REQUIRED
```

### 2. Streamlit Community Cloud Deployment

Add your database connection to Streamlit Secrets (`.streamlit/secrets.toml` or Streamlit Cloud Dashboard):

```toml
[database]
host = "gateway01.us-east-1.prod.aws.tidbcloud.com"
port = 4000
user = "your_cluster_prefix.root"
password = "your_cluster_password"
database = "omnistream"
ssl_mode = "REQUIRED"
```

### 3. Graceful Offline Fallback & Migration

- **Offline / Local Mode**: If TiDB is not configured or network access fails, OmniStream transparently stores and reads data from local JSON files (`~/.omnistream_history.json`, etc.).
- **Auto Migrations**: Versioned database migrations create tables automatically on first connection.
- **One-Click Sync**: The Settings page provides a "Sync Local to Cloud" button to migrate local history and favorites into TiDB Cloud without duplicate records.

---

## 🔒 Security & Privacy

- All user inputs are sanitized against path traversal (`../`) and illegal filename characters.
- Database passwords and tokens are never printed to terminal logs, screenshots, UI, or serialized artifacts.
- Parameterized SQL queries (`%s`) protect all database operations from SQL injection.
- `.env` and local credentials are strictly ignored in `.gitignore`.
- Downloads are executed strictly within designated target directories.

---

## 📜 Legal Notice

OmniStream is provided for downloading content that you have permission or the explicit right to access. Always respect copyright laws and platform terms of service.
