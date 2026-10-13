import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox, filedialog
import yt_dlp
import os
import re
import io
import requests
import threading
import time
import sys
from datetime import datetime
from urllib.parse import urlparse
from PIL import Image, ImageTk

# Add src to path for shared extractor
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
from src.extractor import extract_media_info
from src.validators import detect_platform, is_instagram_collection_url

APP_VERSION = "3.0 PREMIUM"
ACCENTS = {
    "Violet": "#7c3aed",
    "Sky": "#0ea5e9",
    "Emerald": "#10b981",
    "Rose": "#f43f5e",
    "Amber": "#f59e0b",
}
HISTORY_PATH = os.path.join(os.path.expanduser("~"), ".omnistream_history.json")
CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".omnistream_config.json")

def is_network_online():
    for test_url in ["https://1.1.1.1", "https://8.8.8.8", "https://www.google.com"]:
        try:
            res = requests.get(test_url, timeout=3)
            if res.status_code == 200:
                return True
        except Exception:
            pass
    return False

def wait_for_network(app_log=None):
    if not is_network_online():
        if app_log:
            app_log("⚠️ Connection lost. Waiting for Wi-Fi reconnection...")
        while not is_network_online():
            time.sleep(3)
        if app_log:
            app_log("⚡ Internet re-connected! Resuming downloads...")

# YouTube player client fallback chains, tried in order.
# YouTube now enforces proof-of-origin (PO) tokens for many clients on datacenter IPs,
# which turns downloads into HTTP 403. 'visionos' and 'web_embedded' currently expose
# playable formats without any token.
YOUTUBE_CLIENT_CHAINS = [
    ["visionos", "web_embedded"],
    ["android_vr", "tv", "web_safari"],
    ["web", "android", "mweb"],
    # None = let yt-dlp choose its own clients. Last-resort fallback because
    # YouTube intermittently rejects the forced chains.
    None,
]

# Must be a DESKTOP UA: a mobile UA makes YouTube serve the mweb channel page,
# which yt-dlp's youtube:tab extractor cannot parse ("Unable to recognize tab
# page"), so every channel/Shorts listing fails.
DESKTOP_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

# Content tabs that can hold uploads on a YouTube channel.
CHANNEL_TABS = ("videos", "shorts", "streams")


class _Cancelled(Exception):
    """Raised inside a progress hook when a job exceeds its watchdog."""


def resolve_js_runtime():
    """
    Finds a JS runtime yt-dlp can use for YouTube's signature challenge.

    yt-dlp only enables Deno by default. Without any runtime every YouTube
    video fails with "This video is not available", so Node/Bun must be
    registered explicitly.
    """
    global _JS_RUNTIME_CACHE
    if "result" in _JS_RUNTIME_CACHE:
        return _JS_RUNTIME_CACHE["result"]

    import shutil as _shutil

    extra = {
        "node": [r"C:\Program Files\nodejs\node.exe",
                 r"C:\Program Files (x86)\nodejs\node.exe"],
        "bun": [os.path.expandvars(r"%USERPROFILE%\.bun\bin\bun.exe")],
    }
    for name in ("deno", "node", "bun", "quickjs"):
        exe = _shutil.which(name)
        if not exe and name == "node":
            exe = _shutil.which("nodejs")
        if not exe:
            for candidate in extra.get(name, []):
                if os.path.isfile(candidate):
                    exe = candidate
                    break
        if exe:
            _JS_RUNTIME_CACHE["result"] = {name: {"path": exe}}
            return _JS_RUNTIME_CACHE["result"]

    _JS_RUNTIME_CACHE["result"] = None
    return None


def apply_js_runtime(opts):
    """Adds js_runtimes/remote_components to a yt-dlp opts dict when available."""
    js = resolve_js_runtime()
    if js:
        opts['js_runtimes'] = js
        opts['remote_components'] = {'ejs:github'}
    return opts


_JS_RUNTIME_CACHE = {}


def should_retry_client(msg):
    low = str(msg).lower()
    fatal = ("video unavailable", "has been removed", "removed by the uploader",
             "private video", "members-only", "this account has been terminated",
             "does not exist", "no video formats found")
    if any(m in low for m in fatal):
        return False
    return any(k in low for k in (
        "sign in to confirm", "not a bot", "login_required",
        "po_token", "po token",
        "confirm your age", "unplayable result", "playback on other websites",
        "requested format is not available", "http error 403", "403 forbidden",
    ))


_FFMPEG_CACHE = {}


def resolve_ffmpeg_location():
    """
    Finds an ffmpeg executable, falling back to the build bundled with
    `imageio-ffmpeg`. yt-dlp cannot merge separate video-only and audio-only
    streams without it, so a missing ffmpeg is what leaves ".f251.webm" and
    ".f399.mp4" files behind instead of one playable video.
    """
    if "loc" in _FFMPEG_CACHE:
        return _FFMPEG_CACHE["loc"]

    import shutil
    path = shutil.which("ffmpeg")
    if not path:
        try:
            import imageio_ffmpeg
            candidate = imageio_ffmpeg.get_ffmpeg_exe()
            if candidate and os.path.exists(candidate):
                path = candidate
        except Exception:
            path = None

    location = None
    if path:
        # yt-dlp's ffmpeg_location must be a string (binary path or its
        # directory). Passing a dict raises TypeError inside FFmpegMergerPP and
        # leaves video-only/audio-only files unmerged.
        location = os.path.abspath(path)

    _FFMPEG_CACHE["loc"] = location
    return location


FFMPEG_MISSING_MESSAGE = (
    "FFmpeg not found. Separate audio and video streams cannot be merged into "
    "one playable file. Run 'pip install imageio-ffmpeg' or 'winget install ffmpeg', "
    "then restart OmniStream."
)

# Matches yt-dlp per-stream intermediates such as "Title.f251.webm".
STREAM_ARTIFACT_RE = re.compile(r"\.(?:f\d+|temp|part-frag\d*|ytdl)\.[A-Za-z0-9]{1,5}$")


def is_stream_artifact(path):
    return bool(STREAM_ARTIFACT_RE.search(os.path.basename(path)))


def cleanup_stream_artifacts(directory, keep=None):
    """Removes leftover per-stream intermediates so they are not mistaken for output."""
    keep = {os.path.abspath(p) for p in (keep or ())}
    removed = []
    try:
        names = os.listdir(directory)
    except Exception:
        return removed
    for name in names:
        if not is_stream_artifact(name):
            continue
        full = os.path.join(directory, name)
        if not os.path.isfile(full) or os.path.abspath(full) in keep:
            continue
        try:
            os.remove(full)
            removed.append(full)
        except Exception:
            pass
    return removed


DEFAULT_OUTTMPL = "%(title).120s [%(id)s].%(ext)s"

YOUTUBE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def _youtube_handle(url):
    """Extracts an @handle or channel id from a YouTube URL, when present."""
    path = urlparse(url).path or ""
    m = re.search(r"/@([^/?#]+)", path)
    if m:
        return m.group(1)
    m = re.search(r"/(?:channel|c|user)/([^/?#]+)", path)
    if m:
        return m.group(1)
    return None


CHANNEL_URL_MARKERS = ("/channel/", "/c/", "/user/", "/@", "/shorts", "/playlist")

INSTAGRAM_COLLECTION_MARKERS = ("/reels/",)


def is_collection_url(url):
    """
    True when a URL points at many videos (channel, playlist or Shorts tab).
    A plain "/watch?v=..." link is a single video.
    Also detects Instagram profile and reels listing URLs.
    """
    low = (url or "").lower()
    if "list=" in low:
        return True
    if any(m in low for m in CHANNEL_URL_MARKERS):
        return True
    # Instagram: bare profile URLs (instagram.com/username/) and /reels/ listings are collections
    if "instagram.com" in low:
        # Check for /reels/ listing
        if any(m in low for m in INSTAGRAM_COLLECTION_MARKERS):
            return True
        # Check for bare profile URL (instagram.com/username/ with no path after)
        import re
        if re.match(r"https?://(?:www\.)?instagram\.com/[^/?#]+/?$", low):
            return True
    return False


def _entry_url(entry, parent_url):
    """
    Flat extraction returns a bare video id, which yt-dlp cannot download.
    Resolving it to a watch URL is what makes channel/playlist batch downloads work.
    """
    for key in ("webpage_url", "original_url"):
        v = entry.get(key)
        if v and str(v).startswith(("http://", "https://")):
            return str(v)
    eid = entry.get("id")
    if eid and YOUTUBE_ID_RE.match(str(eid)):
        return f"https://www.youtube.com/watch?v={eid}"
    v = entry.get("url")
    if v and str(v).startswith(("http://", "https://")):
        return str(v)
    return parent_url

ILLEGAL = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def sanitize(name):
    return ILLEGAL.sub("_", name or "video")


class DownloadItem:
    def __init__(self, app, url, media_type, quality_key, allow_playlist=False):
        self.app = app
        self.url = url
        self.media_type = media_type
        self.quality_key = quality_key
        # Only True when this single URL is itself a collection (channel/playlist).
        self.allow_playlist = allow_playlist
        self.result = None
        self.error = None
        self.status = "Queued"
        self.progress = 0.0
        self.stat_display = "Waiting..."
        self.percent = "0%"
        self.speed = "N/A"
        self.eta = "N/A"
        self.downloaded = "0 B"
        self.total = "?"
        self.cancelled = False
        self._done = threading.Event()

    def build_opts(self, client_chain=None):
        # Detect platform to apply platform-specific options
        platform = detect_platform(self.url)
        is_youtube = platform == "YouTube"

        opts = {
            'outtmpl': os.path.join(self.app.config.get("download_path", os.path.expanduser("~/Downloads")), DEFAULT_OUTTMPL),
            'nooverwrites': True,
            'continuedl': True,
            # 100 retries with backoff made a single blocked video occupy its
            # worker slot for many minutes, so a large batch looked frozen.
            'retries': int(self.app.config.get("max_retries", 8) or 8),
            'fragment_retries': int(self.app.config.get("max_retries", 8) or 8),
            'file_access_retries': 3,
            'extractor_retries': 3,
            # Never let a dead socket hold a worker slot forever.
            'socket_timeout': int(self.app.config.get("socket_timeout", 30) or 30),
            'skip_unavailable_fragments': True,
            'noplaylist': not (self.allow_playlist and self.app.config.get("playlist", True)),
            'ignoreerrors': True,
            # Let yt-dlp handle illegal characters and long Windows paths so a
            # channel name containing "|" no longer becomes "?" in the filename.
            'windowsfilenames': True,
            'trim_file_name': 180,
        }

        # Only add YouTube-specific extractor args for YouTube URLs
        if is_youtube:
            opts['extractor_args'] = {
                'youtube': {
                    # None means "no forced client": yt-dlp picks its own,
                    # which is the most reliable option when YouTube throttles
                    # the hardcoded chains. Do NOT coerce it back to chains[0].
                    'player_client': client_chain,
                }
            }
            # Required: without a JS runtime YouTube's signature challenge is never
            # solved and every video fails with "This video is not available".
            apply_js_runtime(opts)
            # Desktop UA: a mobile UA makes YouTube serve the mweb channel page,
            # which yt-dlp's youtube:tab extractor cannot parse.
            opts['http_headers'] = {'User-Agent': DESKTOP_USER_AGENT}

        browser = self.app.config.get("cookies_browser")
        if browser and not self.app.cookie_locked.is_set():
            opts['cookiesfrombrowser'] = (browser,)
            self.app.log(f"Using cookies from browser: {browser}")

        ffmpeg = resolve_ffmpeg_location()
        if ffmpeg:
            opts['ffmpeg_location'] = ffmpeg

        if self.media_type == "Video":
            selector = self.quality_key or 'bestvideo+bestaudio/best'
            if '+' in selector and not ffmpeg:
                raise RuntimeError(FFMPEG_MISSING_MESSAGE)
            opts['format'] = selector
            opts['merge_output_format'] = 'mp4'
        else:
            q = re.sub(r"\D", "", ((self.quality_key or "192").split(" ")[0]))
            opts['format'] = 'bestaudio/best'
            # bestaudio is normally Opus/WebM, so conversion runs even at the
            # default bitrate; skipping it would leave an unplayable audio file.
            opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': q or '192',
            }]
        return opts

    def play(self, app):
        download_path = app.config.get("download_path", os.path.expanduser("~/Downloads"))
        try:
            os.makedirs(download_path, exist_ok=True)
        except Exception:
            pass

        if self.media_type == "Image":
            return self._download_image(app, download_path)

        def progress_hook(d):
            if self.cancelled:
                raise _Cancelled()
            if d.get('status') == 'downloading':
                try:
                    p = float(d.get('_percent_str', '0%').replace('%', '').strip())
                    self.percent = d.get('_percent_str', f'{p:.1f}%')
                    self.speed = d.get('_speed_str', 'N/A')
                    self.eta = d.get('_eta_str', 'N/A')
                    down = d.get('downloaded_bytes', 0) or 0
                    tot = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
                    self.downloaded = self._fmt_size(down)
                    self.total = self._fmt_size(tot) if tot else "?"
                    self.progress = min(p / 100.0, 1.0)
                    if tot:
                        self.progress = min(down / float(tot), 1.0)
                    self.stat_display = (f"{self.percent}  |  {self.downloaded} / {self.total}"
                                         f"  |  ⚡ {self.speed}  |  ⏳ {self.eta}")
                    self._sync_row()
                except Exception:
                    pass
            elif d.get('status') == 'finished':
                self.progress = 1.0
                self.stat_display = "Processing/merging..."
                self._sync_row()

        self.stat_display = "Preparing..."
        self._sync_row()

        # Detect platform for platform-specific retry logic
        platform = detect_platform(self.url)
        is_youtube = platform == "YouTube"
        
        cookie_tried = False
        client_index = 0
        # For non-YouTube, we only try once (client_chain=None)
        client_chains = YOUTUBE_CLIENT_CHAINS if is_youtube else [None]
        
        while True:
            try:
                ydl_opts = self.build_opts(client_chains[client_index])
            except RuntimeError as e:
                return False, str(e)
            ydl_opts['progress_hooks'] = [progress_hook]
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(self.url, download=True)
                    
                    # If extraction failed completely (e.g., auth required, unsupported URL)
                    if not info:
                        return False, "Failed to extract media info. The content may require authentication (set browser cookies in Settings), be private, or no longer available."
                    
                    entries = info.get('entries')
                    if entries:
                        saved = []
                        for entry in entries:
                            if not entry:
                                continue
                            resolved = self._resolve_output_file(
                                download_path, ydl.prepare_filename(entry))
                            if resolved:
                                saved.append(resolved)
                        if saved:
                            cleanup_stream_artifacts(download_path, keep=set(saved))
                            return True, saved
                        cleanup_stream_artifacts(download_path)
                        return False, ("Streams were downloaded but never merged into one file. "
                                       + FFMPEG_MISSING_MESSAGE)

                    filename = self._resolve_output_file(
                        download_path, ydl.prepare_filename(info))
                    if not filename:
                        cleanup_stream_artifacts(download_path)
                        return False, ("Streams were downloaded but never merged into one file. "
                                       + FFMPEG_MISSING_MESSAGE)
                    cleanup_stream_artifacts(download_path, keep={filename})
                    return True, filename
            except Exception as e:
                msg = str(e)
                cleanup_stream_artifacts(download_path)
                if isinstance(e, _Cancelled) or self.cancelled:
                    return False, "Timed out and was skipped."
                if cookie_tried:
                    return False, msg
                if "ffmpeg" in msg.lower() or "ffprobe" in msg.lower():
                    return False, FFMPEG_MISSING_MESSAGE
                if "cookie" in msg.lower() or "could not copy" in msg.lower():
                    app.cookie_locked.set()
                    app.log("Chrome cookie DB is locked (Chrome running). Retrying without cookies...")
                    cookie_tried = True
                    continue
                # Only retry with different client chains for YouTube
                if is_youtube and should_retry_client(msg) and client_index < len(YOUTUBE_CLIENT_CHAINS) - 1:
                    client_index += 1
                    app.log(f"YouTube flagged this client. Retrying with {YOUTUBE_CLIENT_CHAINS[client_index]}...")
                    continue
                if "sign in" in msg.lower():
                    return False, ("YouTube blocked this download because cookies couldn't be read.\n"
                                   "Close Chrome completely and try again, or set cookies in Settings.")
                
                # Instagram-specific error handling
                if "instagram" in msg.lower():
                    if "unable to extract" in msg.lower() or "unsupported url" in msg.lower():
                        return False, ("Instagram requires authentication to access this content. "
                                       "Please set browser cookies in Settings (close browser first) and retry.")
                    if "login required" in msg.lower() or "please log in" in msg.lower() or "empty media response" in msg.lower():
                        return False, ("This Instagram content requires login. "
                                       "Set browser cookies in Settings (close browser completely first) and retry.")
                    if "rate limit" in msg.lower() or "too many requests" in msg.lower() or "429" in msg.lower():
                        return False, "Instagram rate limit reached. Wait a few minutes and try again."
                    if "private" in msg.lower():
                        return False, ("This Instagram account is private. "
                                       "You need to follow the account and use browser cookies to access.")
                
                return False, msg

    def _resolve_output_file(self, download_path, filename):
        """
        Finds the real merged output file, ignoring per-stream intermediates such
        as "Title.f399.mp4" which only hold video (or audio) without the other.
        """
        if filename and os.path.exists(filename) and not is_stream_artifact(filename):
            return filename
        if filename:
            base = os.path.basename(os.path.splitext(filename)[0])
            try:
                for f in os.listdir(download_path):
                    if f.startswith(base) and not is_stream_artifact(f) \
                            and not f.endswith(('.part', '.ytdl', '.tmp')):
                        return os.path.join(download_path, f)
            except Exception:
                pass
        return None

    def _sync_row(self):
        try:
            w = self.app.active_widgets.get(self.url)
            if w:
                w["bar"].set(self.progress)
                w["stats"].configure(text=self.stat_display)
        except Exception:
            pass

    def _fmt_size(self, b):
        try:
            b = float(b)
            for unit in ["B", "KB", "MB", "GB"]:
                if b < 1024 or unit == "GB":
                    return f"{b:.1f} {unit}"
                b /= 1024.0
        except Exception:
            pass
        return "0 B"

    def _download_image(self, app, download_path):
        try:
            self.stat_display = "Fetching image..."
            self._sync_row()
            r = requests.get(self.url, stream=True, timeout=30)
            if r.status_code != 200:
                return False, f"HTTP {r.status_code}"
            ct = r.headers.get('content-type', '')
            if 'image' not in ct:
                return False, "URL does not point to an image."
            ext = ct.split('/')[-1].split(';')[0] or 'jpg'
            if len(ext) > 5 or not ext.isalnum():
                ext = 'jpg'
            name = sanitize(f"image_{int(time.time())}") + f".{ext}"
            full = os.path.join(download_path, name)
            total = int(r.headers.get('content-length') or 0)
            done = 0
            with open(full, 'wb') as f:
                for chunk in r.iter_content(8192):
                    if not chunk:
                        continue
                    f.write(chunk)
                    done += len(chunk)
                    if total:
                        self.progress = min(done / float(total), 1.0)
                        self.stat_display = f"{self.progress*100:.0f}%  |  {self._fmt_size(done)} / {self._fmt_size(total)}"
                    else:
                        self.stat_display = f"Downloading... {self._fmt_size(done)}"
                    self._sync_row()
            self.progress = 1.0
            self._sync_row()
            return True, full
        except Exception as e:
            return False, str(e)


class DownloadApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.config = self.load_config()
        self.cookie_locked = threading.Event()
        self.workers = 0
        self.max_workers = int(self.config.get("max_workers", 3))
        self.downloads = {}
        self.item_lock = threading.Lock()
        self.history = self.load_history()
        self.clipboard_last = None
        self.thumb_img = None
        self.fmt_options = []
        self.active_widgets = {}

        ctk.set_appearance_mode("dark")
        self.accent = ACCENTS.get(self.config.get("accent", "Violet"))
        ctk.set_default_color_theme("blue")

        self.title("OmniStream Premium | Universal Downloader")
        self.geometry("1150x760")
        self.minsize(1000, 660)

        # ---------------- Main layout ----------------
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.configure(fg_color="#05070e")

        self.header = ctk.CTkFrame(self, fg_color="transparent", height=88)
        self.header.grid(row=0, column=0, sticky="ew", padx=18, pady=(14, 4))
        self.header.grid_columnconfigure(0, weight=1)

        title_wrap = ctk.CTkFrame(self.header, fg_color="transparent")
        title_wrap.grid(row=0, column=0, sticky="w")
        self.left_panel = ctk.CTkFrame(title_wrap, fg_color="#7c3aed", width=6, corner_radius=3)
        self.left_panel.pack(side="left", fill="y", padx=(0, 12))
        self.brand = ctk.CTkLabel(title_wrap, text="OMNISTREAM", font=("Inter", 34, "bold"), text_color="#f8fafc")
        self.brand.pack(anchor="w")
        self.brand_tag = ctk.CTkLabel(title_wrap, text=f"PREMIUM EDITION  |  Universal Video · Audio · Image Downloader",
                                      font=("Inter", 12), text_color="#94a3b8")
        self.brand_tag.pack(anchor="w")

        # Stats chip row
        self.right_panel = ctk.CTkFrame(self.header, fg_color="transparent")
        self.right_panel.grid(row=0, column=1, sticky="e")
        self.stat_workers_lbl = ctk.CTkLabel(self.right_panel, text=f"Concurrency: {self.max_workers}",
                                              font=("Inter", 11), fg_color="#0b1220", corner_radius=8,
                                              text_color="#cbd5e1", width=140)
        self.stat_workers_lbl.pack(pady=2, fill="x")
        self.stat_total_lbl = ctk.CTkLabel(self.right_panel, text="Completed: 0",
                                           font=("Inter", 11), fg_color="#0b1220", corner_radius=8,
                                           text_color="#cbd5e1", width=140)
        self.stat_total_lbl.pack(pady=2, fill="x")
        self.stat_queued_lbl = ctk.CTkLabel(self.right_panel, text="Queued: 0",
                                            font=("Inter", 11), fg_color="#0b1220", corner_radius=8,
                                            text_color="#cbd5e1", width=140)
        self.stat_queued_lbl.pack(pady=2, fill="x")

        # ---------------- Body: left nav + right app ----------------
        self.body = ctk.CTkFrame(self, fg_color="#05070e")
        self.body.grid(row=1, column=0, sticky="nsew", padx=18, pady=8)
        self.body.grid_columnconfigure(1, weight=1)
        self.body.grid_rowconfigure(0, weight=1)

        self.nav = ctk.CTkFrame(self.body, width=190, fg_color="#0a0f1c", corner_radius=14)
        self.nav.grid(row=0, column=0, sticky="nsw", padx=(0, 14))
        self.nav.grid_propagate(False)

        self.nav_options = [
            ("down", "💾  New Download"),
            ("active", "📊  Active Queue"),
            ("history", "🕘  History"),
            ("settings", "⚙️  Settings"),
        ]
        self.nav_buttons = {}
        for i, (key, label) in enumerate(self.nav_options):
            btn = ctk.CTkButton(self.nav, text=label, anchor="w", font=("Inter", 14),
                                height=46, corner_radius=10, fg_color="transparent",
                                text_color="#94a3b8", hover_color="#16203a",
                                command=lambda k=key: self.switch(k))
            btn.pack(fill="x", padx=10, pady=4)
            self.nav_buttons[key] = btn

        nav_spacer = ctk.CTkFrame(self.nav, height=1, fg_color="#1e293b")
        nav_spacer.pack(fill="x", padx=12, pady=10)

        version = ctk.CTkLabel(self.nav, text=f"OmniStream {APP_VERSION}", font=("Inter", 10),
                               text_color="#475569")
        version.pack(side="bottom", pady=14)

        self.main_frame = ctk.CTkFrame(self.body, fg_color="transparent")
        self.main_frame.grid(row=0, column=1, sticky="nsew")
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_rowconfigure(0, weight=1)

        self.pages = {}
        self.pages["down"] = self.build_download_page()
        self.pages["active"] = self.build_active_page()
        self.pages["history"] = self.build_history_page()
        self.pages["settings"] = self.build_settings_page()

        self.switch("down")

        self.log_console("ready")
        self.start_clipboard_watcher()
        self.fetch_logo()

    # ================= CONFIG / HISTORY =================
    def load_config(self):
        defaults = {
            "download_path": os.path.expanduser("~/Downloads"),
            "accent": "Violet",
            "max_workers": 3,
            "cookies_browser": "",
            "playlist": True,
            "playlist_limit": 0,
            "max_retries": 8,
            "socket_timeout": 30,
            "job_timeout": 600,
            "show_thumb": True,
        }
        try:
            if os.path.exists(CONFIG_PATH):
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    defaults.update(json_safeload(f.read()))
        except Exception:
            pass
        return defaults

    def save_config(self):
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json_dumps(self.config, f)
        except Exception:
            pass

    def load_history(self):
        try:
            if os.path.exists(HISTORY_PATH):
                with open(HISTORY_PATH, "r", encoding="utf-8") as f:
                    return json_safeload(f.read())
        except Exception:
            pass
        return []

    def save_history(self):
        try:
            with open(HISTORY_PATH, "w", encoding="utf-8") as f:
                json_dumps(self.history, f)
        except Exception:
            pass

    def add_history(self, url, filename, media_type):
        self.history.insert(0, {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "url": url, "file": filename, "type": media_type,
        })
        self.history = self.history[:100]
        self.save_history()
        self.render_history()

    def notify(self, title, msg, kind="info"):
        try:
            if kind == "err":
                messagebox.showerror(title, msg)
            else:
                messagebox.showinfo(title, msg)
        except Exception:
            pass

    # ================= PAGE BUILDERS =================
    def make_card(self, parent, title=None, **kw):
        card = ctk.CTkFrame(parent, fg_color="#0a0f1c", corner_radius=14, **kw)
        card.pack(fill="x", pady=(0, 14))
        if title:
            lbl = ctk.CTkLabel(card, text=title, font=("Inter", 13, "bold"),
                               text_color="#e2e8f0", anchor="w")
            lbl.pack(fill="x", padx=18, pady=(14, 0))
        return card

    def build_download_page(self):
        page = ctk.CTkScrollableFrame(self.main_frame, fg_color="transparent")
        page.grid_columnconfigure(0, weight=1)

        # URL input
        card = self.make_card(page)
        url_row = ctk.CTkFrame(card, fg_color="transparent")
        url_row.pack(fill="x", padx=18, pady=(16, 6))
        url_row.grid_columnconfigure(0, weight=1)

        self.url_entry = ctk.CTkEntry(url_row, placeholder_text="Paste link — YouTube, Instagram, Image URL, TikTok, or 1000+ sites...",
                                      height=52, font=("Inter", 14), fg_color="#0b1220",
                                      border_color="#1e293b", corner_radius=10)
        self.url_entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))

        self.fetch_btn = ctk.CTkButton(url_row, text="🔍 Analyze", width=130, height=52,
                                       font=("Inter", 14, "bold"), fg_color=self.accent,
                                       hover_color=self.shade(self.accent), command=self.analyze_url)
        self.fetch_btn.grid(row=0, column=1, padx=(0, 10))

        self.download_btn = ctk.CTkButton(url_row, text="🚀 Start Download", width=190, height=52,
                                          font=("Inter", 14, "bold"), fg_color=self.accent,
                                          hover_color=self.shade(self.accent), command=self.queue_download)
        self.download_btn.grid(row=0, column=2)

        # Metadata card
        self.meta_card = self.make_card(page, "📋 Media Preview")
        self.meta_placeholder = ctk.CTkLabel(self.meta_card,
                                             text="Paste a link above and press Analyze to preview title, thumbnail and available qualities.",
                                             text_color="#475569", font=("Inter", 12), wraplength=700)
        self.meta_placeholder.pack(padx=18, pady=20)

        # Options card
        self.opts_card = self.make_card(page, "⚙️ Download Options")
        row = ctk.CTkFrame(self.opts_card, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(12, 14))

        self.media_type = ctk.CTkSegmentedButton(row, values=["Video", "Audio", "Image"],
                                                 command=self.on_media_change)
        self.media_type.set("Video")
        self.media_type.grid(row=0, column=0, sticky="w")

        self.quality_lbl = ctk.CTkLabel(row, text="Quality:", font=("Inter", 12), text_color="#94a3b8")
        self.quality_lbl.grid(row=0, column=1, sticky="e", padx=(30, 8))
        self.quality_menu = ctk.CTkOptionMenu(row, values=["Auto (Best)"], width=220, height=36,
                                              font=("Inter", 12), fg_color="#0b1220",
                                              button_color=self.accent, button_hover_color=self.shade(self.accent))
        self.quality_menu.grid(row=0, column=2, sticky="e")

        row2 = ctk.CTkFrame(self.opts_card, fg_color="transparent")
        row2.pack(fill="x", padx=18, pady=(0, 14))
        self.folder_btn = ctk.CTkButton(row2, text="📁 Change Folder", fg_color="#0b1220",
                                        hover_color="#16203a", height=38, font=("Inter", 12),
                                        command=self.select_folder)
        self.folder_btn.pack(side="left")
        self.folder_lbl = ctk.CTkLabel(row2, text=f"Save to: {self.config.get('download_path','')}",
                                       font=("Inter", 11), text_color="#64748b")
        self.folder_lbl.pack(side="left", padx=14)

        # Log console
        log_card = self.make_card(page, "📟 Console")
        self.log_box = ctk.CTkTextbox(log_card, height=110, fg_color="#05070e", corner_radius=10,
                                      text_color="#94a3b8", font=("Consolas", 11), wrap="word")
        self.log_box.pack(fill="x", padx=18, pady=(8, 16))
        self.log_box.configure(state="disabled")
        return page

    def build_active_page(self):
        page = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(0, weight=1)

        card = ctk.CTkFrame(page, fg_color="#0a0f1c", corner_radius=14)
        card.grid(row=0, column=0, sticky="nsew")
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(1, weight=1)

        self.active_add = ctk.CTkLabel(card, text="📊 ACTIVE DOWNLOADS", font=("Inter", 15, "bold"),
                                       text_color="#e2e8f0", anchor="w")
        self.active_add.grid(row=0, column=0, sticky="w", padx=20, pady=(16, 6))

        self.active_container = ctk.CTkScrollableFrame(card, fg_color="transparent",
                                                       corner_radius=0)
        self.active_container.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 14))
        self.active_empty = ctk.CTkLabel(self.active_container, text="No active downloads.\nAdd a link in the Download tab.",
                                         text_color="#475569", font=("Inter", 13))
        self.active_empty.pack(pady=80)
        return page

    def build_history_page(self):
        page = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(0, weight=1)

        card = ctk.CTkFrame(page, fg_color="#0a0f1c", corner_radius=14)
        card.grid(row=0, column=0, sticky="nsew")
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(1, weight=1)

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 6))
        ctk.CTkLabel(head, text="🕘 DOWNLOAD HISTORY", font=("Inter", 15, "bold"),
                     text_color="#e2e8f0").pack(side="left")
        ctk.CTkButton(head, text="🗑 Clear", fg_color="#3f1d2e", hover_color="#7f1d1d",
                      font=("Inter", 12), height=32, command=self.clear_history).pack(side="right")

        self.history_box = ctk.CTkTextbox(card, fg_color="#05070e", corner_radius=10,
                                          text_color="#cbd5e1", font=("Consolas", 12), wrap="word")
        self.history_box.grid(row=1, column=0, sticky="nsew", padx=20, pady=(4, 16))
        self.history_box.configure(state="disabled")
        self.render_history()
        return page

    def build_settings_page(self):
        page = ctk.CTkScrollableFrame(self.main_frame, fg_color="transparent")
        page.grid_columnconfigure(0, weight=1)

        # Download folder
        c1 = self.make_card(page, "📂 Download Location")
        row = ctk.CTkFrame(c1, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(10, 16))
        row.grid_columnconfigure(0, weight=1)
        self.set_path_entry = ctk.CTkEntry(row, height=40, font=("Inter", 13), fg_color="#0b1220")
        self.set_path_entry.insert(0, self.config.get("download_path", ""))
        self.set_path_entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        ctk.CTkButton(row, text="Browse", width=110, height=40, fg_color="#0b1220",
                      hover_color="#16203a", command=self.browse_set_path).grid(row=0, column=1)

        # Behavior
        c2 = self.make_card(page, "⚡ Behavior")
        inner = ctk.CTkFrame(c2, fg_color="transparent")
        inner.pack(fill="x", padx=18, pady=(10, 6))
        ctk.CTkLabel(inner, text="Concurrent downloads:", font=("Inter", 12),
                     text_color="#94a3b8").pack(side="left")
        self.max_workers_menu = ctk.CTkOptionMenu(inner, values=["1", "2", "3", "4", "5"],
                                                  width=90, height=34, font=("Inter", 12),
                                                  command=self.on_workers_change)
        self.max_workers_menu.set(str(self.config.get("max_workers", 3)))
        self.max_workers_menu.pack(side="left", padx=12)

        self.playlist_var = tk.BooleanVar(value=self.config.get("playlist", True))
        ctk.CTkCheckBox(inner, text="Allow playlists (download all videos in list)",
                        variable=self.playlist_var, font=("Inter", 12), text_color="#94a3b8",
                        command=self.on_playlist_change).pack(side="left", padx=20)

        # Theme / accent
        c3 = self.make_card(page, "🎨 Appearance")
        inner3 = ctk.CTkFrame(c3, fg_color="transparent")
        inner3.pack(fill="x", padx=18, pady=(10, 6))
        ctk.CTkLabel(inner3, text="Accent color:", font=("Inter", 12),
                     text_color="#94a3b8").pack(side="left")
        self.accent_menu = ctk.CTkOptionMenu(inner3, values=list(ACCENTS.keys()),
                                             width=130, height=34, font=("Inter", 12),
                                             command=self.on_accent_change)
        self.accent_menu.set(self.config.get("accent", "Violet"))
        self.accent_menu.pack(side="left", padx=12)

        # Cookies
        c4 = self.make_card(page, "🍪 Cookies (fixes YouTube bot-block)")
        inner4 = ctk.CTkFrame(c4, fg_color="transparent")
        inner4.pack(fill="x", padx=18, pady=(10, 6))
        ctk.CTkLabel(inner4, text="Use cookies from browser:", font=("Inter", 12),
                     text_color="#94a3b8").pack(side="left")
        self.browser_menu = ctk.CTkOptionMenu(inner4, values=["", "chrome", "edge", "firefox", "brave"],
                                              width=120, height=34, font=("Inter", 12),
                                              command=self.on_browser_change)
        self.browser_menu.set(self.config.get("cookies_browser", ""))
        self.browser_menu.pack(side="left", padx=12)
        ctk.CTkLabel(inner4, text="Note: browser must be closed when downloading for cookies to load.",
                     font=("Inter", 10), text_color="#64748b").pack(side="left", padx=12)

        c5 = self.make_card(page, "❔ Quick Help")
        help_text = (
            "•  Paste any link and press Analyze to preview media.\n"
            "•  Choose Video / Audio / Image and a quality, then Start Download.\n"
            "•  Downloads run in a queue — up to your chosen concurrency.\n"
            "•  History is stored in your profile as .omnistream_history.json.\n"
            "•  If YouTube blocks you, close Chrome fully so cookies can be read."
        )
        ctk.CTkLabel(c5, text=help_text, font=("Inter", 12), text_color="#94a3b8",
                     justify="left", anchor="w").pack(fill="x", padx=18, pady=(4, 16))
        return page

    # ================= NAV & HELPERS =================
    def shade(self, color, factor=0.75):
        try:
            color = color.lstrip("#")
            r, g, b = [int(color[i:i+2], 16) for i in (0, 2, 4)]
            return "#%02x%02x%02x" % (int(r*factor), int(g*factor), int(b*factor))
        except Exception:
            return "#334155"

    def switch(self, key):
        for k, btn in self.nav_buttons.items():
            btn.configure(fg_color=self.accent if k == key else "transparent",
                          text_color="#f8fafc" if k == key else "#94a3b8")
        for k, page in self.pages.items():
            page.grid_forget()
        self.pages[key].grid(row=0, column=0, sticky="nsew")

    def log(self, msg):
        def _do():
            try:
                self.log_box.configure(state="normal")
                self.log_box.insert("end", f"> {msg}\n")
                self.log_box.see("end")
                self.log_box.configure(state="disabled")
            except Exception:
                pass
        try:
            self.after(1, _do)
        except Exception:
            pass

    def log_console(self, msg):
        self.log(f"OmniStream ready — {APP_VERSION}")
        ffmpeg = resolve_ffmpeg_location()
        if ffmpeg:
            self.log(f"FFmpeg detected: {ffmpeg}")
        else:
            self.log("⚠ FFmpeg NOT found — video streams cannot be merged.")
            self.log("  Install it with: pip install imageio-ffmpeg")
        if not is_network_online():
            self.log("⚠ No internet connection detected. Downloads will wait for a connection.")
        js = resolve_js_runtime()
        if js:
            self.log("JS runtime detected: %s" % next(iter(js)))
        else:
            self.log("⚠ No JS runtime found — YouTube videos may fail with "
                     "'This video is not available'.")
            self.log("  Install Node.js or Deno to solve YouTube's signature challenge.")

    def select_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.config["download_path"] = folder
            self.folder_lbl.configure(text=f"Save to: {folder}")
            self.save_config()

    def browse_set_path(self):
        folder = filedialog.askdirectory()
        if folder:
            self.set_path_entry.delete(0, "end")
            self.set_path_entry.insert(0, folder)
            self.config["download_path"] = folder
            self.folder_lbl.configure(text=f"Save to: {folder}")
            self.save_config()

    # ================= CLIPBOARD =================
    def start_clipboard_watcher(self):
        def watch():
            while True:
                try:
                    clip = self.clipboard_get()
                    if clip != self.clipboard_last:
                        self.clipboard_last = clip
                        parsed = urlparse(clip)
                        if parsed.scheme in ("http", "https") and parsed.netloc:
                            if not self.url_entry.get().strip():
                                self.url_entry.delete(0, "end")
                                self.url_entry.insert(0, clip)
                except Exception:
                    pass
                time.sleep(1)
        threading.Thread(target=watch, daemon=True).start()

    # ================= LOGO / THUMB =================
    def fetch_logo(self):
        try:
            data = requests.get("https://i.ytimg.com/vi/null/hqdefault.jpg", timeout=5).content
        except Exception:
            pass

    # ================= ANALYZE =================
    def set_analyzing(self, on):
        self.fetch_btn.configure(state="disabled" if on else "normal",
                                 text="⏳ Analyzing..." if on else "🔍 Analyze")

    def analyze_url(self):
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning("No link", "Paste a link first.", parent=self)
            return
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            messagebox.showwarning("Invalid link", "That doesn't look like a valid URL.", parent=self)
            return

        self.set_analyzing(True)
        mt = self.media_type.get()
        thread = threading.Thread(target=self._analyze_worker, args=(url, mt), daemon=True)
        thread.start()

    def _analyze_worker(self, url, mt):
        try:
            self._analyze_worker_inner(url, mt)
        finally:
            self.after(1, lambda: self.set_analyzing(False))

    def _analysis_opts(self, target, chain, limit):
        """Flat-listing options for one target URL."""
        opts = {'quiet': True, 'no_warnings': True, 'skip_download': True,
                'extract_flat': 'in_playlist', 'ignoreerrors': True,
                'http_headers': {'User-Agent': DESKTOP_USER_AGENT},
                'socket_timeout': 30,
                'extractor_args': {'youtube': {}}}
        if chain:
            opts['extractor_args']['youtube']['player_client'] = chain
        # The 'tab' extractor arg is deliberately not set: forcing it makes
        # YouTube return a tab page yt-dlp cannot parse. URLs ending in
        # /videos, /shorts or /streams are already explicit.
        ffmpeg = resolve_ffmpeg_location()
        if ffmpeg:
            opts['ffmpeg_location'] = ffmpeg
        apply_js_runtime(opts)
        if limit > 0:
            opts['playlistend'] = limit
        return opts

    def _analyze_worker_inner(self, url, mt):
        # Use shared extractor for Instagram URLs
        platform = detect_platform(url)
        if platform.startswith("Instagram") and is_instagram_collection_url(url):
            try:
                cookies_browser = self.config.get("cookies_browser") or None
                limit = int(self.config.get("playlist_limit", 0) or 0)
                meta = extract_media_info(
                    url,
                    cookies_browser=cookies_browser,
                    playlist_limit=limit if limit > 0 else None,
                )
                # Convert MediaMetadata to dict format expected by _render_meta
                info = {
                    "title": meta.title,
                    "thumbnail": meta.thumbnail,
                    "uploader": meta.uploader,
                    "duration": meta.duration,
                    "platform": meta.platform,
                    "entries": [
                        {
                            "url": item.url,
                            "title": item.title,
                            "duration": item.duration,
                            "thumbnail": item.thumbnail,
                        }
                        for item in (meta.playlist_items or [])
                    ],
                    "playlist_count": meta.playlist_count,
                    "formats": meta.available_formats,
                }
                self.after(1, lambda i=info: self._render_meta(i, mt, url))
                return
            except Exception as e:
                self.after(1, lambda: self._render_meta_fail(str(e)[:300]))
                return

        last_err = None
        limit = int(self.config.get("playlist_limit", 0) or 0)

        # A bare channel handle only exposes its default tab and silently hides
        # Shorts, so expand it into every content tab and merge the results.
        targets = self._channel_tab_targets(url) or [url]

        for chain in YOUTUBE_CLIENT_CHAINS:
            merged, seen = [], set()
            base_info = None
            abort = False

            for target in targets:
                opts = self._analysis_opts(target, chain, limit)
                try:
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        info = ydl.extract_info(target, download=False)
                except Exception as e:
                    last_err = e
                    # A tab the channel does not have is expected, not fatal.
                    if "does not have a" in str(e).lower():
                        continue
                    if not should_retry_client(str(e)):
                        abort = True
                    break

                if not info:
                    continue
                if base_info is None:
                    base_info = info
                for idx, entry in enumerate(info.get("entries") or [], 1):
                    if not isinstance(entry, dict):
                        continue
                    item_url = entry.get("webpage_url") or entry.get("original_url")
                    if not item_url and re.match(r"^[A-Za-z0-9_-]{11}$", str(entry.get("id") or "")):
                        item_url = "https://www.youtube.com/watch?v=%s" % entry["id"]
                    if not item_url or item_url in seen:
                        continue
                    seen.add(item_url)
                    merged.append({
                        "url": item_url,
                        "title": entry.get("title") or "Item %d" % idx,
                        "duration": entry.get("duration"),
                        "thumbnail": entry.get("thumbnail"),
                        "selected": True,
                        "_source_tab": target,
                    })

            if abort:
                break

            if base_info is not None:
                if merged:
                    base_info = dict(base_info)
                    base_info["entries"] = merged
                    base_info["playlist_count"] = len(merged)
                    base_info["_app_merged_tabs"] = True
                self.after(1, lambda i=base_info: self._render_meta(i, mt, url))
                return

        self.after(1, lambda: self._render_meta_fail(str(last_err)[:300]))

    @staticmethod
    def _channel_tab_targets(url):
        """Expands a bare @handle into one URL per content tab."""
        path = urlparse(url).path or ""
        if not re.search(r"/@[^/?#]+$", path):
            return []
        base = url.rstrip("/")
        return ["%s/%s" % (base, tab) for tab in CHANNEL_TABS]

    def _format_list(self, info):
        fmts = []
        try:
            heights = set()
            audio = set()
            for f in info.get("formats", []):
                h = f.get("height")
                if h:
                    heights.add(h)
                a = f.get("abbr") or f.get("abr")
                if a:
                    audio.add(str(a))
            heights = {h for h in sorted(heights, reverse=True) if h is not None}
            for h in heights:
                fmts.append((f"{h}p (Video)", f"bestvideo[height<={h}]+bestaudio/best[height<={h}]"))
            if not fmts:
                fmts.append(("Auto (Best)", "bestvideo+bestaudio/best"))
        except Exception:
            fmts.append(("Auto (Best)", "bestvideo+bestaudio/best"))
        return fmts

    def _render_meta(self, info, mt, url):
        self.meta_placeholder.pack_forget()
        for w in getattr(self, "_meta_widgets", []):
            try:
                w.destroy()
            except Exception:
                pass
        self._meta_widgets = []

        card = ctk.CTkFrame(self.meta_card, fg_color="transparent")
        card.pack(fill="x", padx=18, pady=(8, 16))
        card.grid_columnconfigure(0, weight=0)
        card.grid_columnconfigure(1, weight=1)

        self.thumb_lbl = ctk.CTkLabel(card, text="", width=200, height=112)
        self.thumb_lbl.grid(row=0, column=0, rowspan=3, padx=(0, 16))

        title = info.get("title") or url
        duration = None
        entries = info.get("entries")
        platform = info.get("platform", "")
        if entries:
            duration = sum(e.get("duration") or 0 for e in entries if e)
            if platform.startswith("Instagram"):
                extra = f"{len(entries)} Reels in listing"
            else:
                extra = f"{len(entries)} videos in playlist"
        else:
            duration = info.get("duration")
            extra = f"{info.get('uploader') or 'Unknown channel'}"

        txt = f"** {title}"
        if duration:
            mins, secs = divmod(int(duration), 60)
            hrs = 0
            if mins > 60:
                hrs, mins = divmod(mins, 60)
            dur = f"{hrs}h {mins}m {secs}s" if hrs else f"{mins}m {secs}s"
            txt += f"\n⏱ Duration: {dur}  ·  {extra}"
        else:
            txt += f"\n{extra}"
        self._meta_title = ctk.CTkLabel(card, text=txt, font=("Inter", 13), text_color="#e2e8f0",
                                        justify="left", anchor="w", wraplength=650)
        self._meta_title.grid(row=0, column=1, sticky="w", pady=(0, 8))

        self._meta_status = ctk.CTkLabel(card, text="Analysis complete — select quality and download.",
                                         font=("Inter", 11), text_color="#34d399")
        self._meta_status.grid(row=1, column=1, sticky="w")

        mt = self.media_type.get()
        if mt == "Video":
            fmts = self._format_list(info)
            self.fmt_options = fmts
            values = [name for name, _ in fmts]
            self.quality_menu.configure(values=values)
            if values and "Auto (Best)" not in values:
                self.quality_menu.set(values[0])
        else:
            self.fmt_options = [("Auto", None)]
            self.quality_menu.configure(values=["Auto"])

        self._meta_widgets.append(card)

        try:
            thumb = info.get("thumbnail")
            if thumb and self.config.get("show_thumb", True):
                thread = threading.Thread(target=self._load_thumb, args=(thumb,), daemon=True)
                thread.start()
        except Exception:
            pass
        self._meta_info = info

        # Collect real, downloadable URLs for channel / playlist / Shorts tabs / Instagram Reels.
        self._meta_entries = []
        for entry in (entries or []):
            if not isinstance(entry, dict):
                continue
            self._meta_entries.append({
                "url": _entry_url(entry, url),
                "title": entry.get("title") or "Untitled",
                "thumbnail": entry.get("thumbnail"),
                "selected": True,  # Default to selected
            })

    def _render_meta_fail(self, msg):
        self.meta_placeholder.configure(text=f"⚠ Unable to analyze:\n{msg}\n\nYou can still download directly without preview.",
                                        text_color="#f87171")
        self.meta_placeholder.pack(padx=18, pady=20)

    def _load_thumb(self, thumb):
        try:
            data = requests.get(thumb, timeout=8).content
            img = Image.open(io.BytesIO(data)).convert("RGB")
            img.thumbnail((200, 112))
            self.thumb_img = ImageTk.PhotoImage(img)
            self.after(1, lambda: self.thumb_lbl.configure(image=self.thumb_img) if hasattr(self, "thumb_lbl") else None)
        except Exception:
            pass

    def on_media_change(self, _=None):
        mt = self.media_type.get()
        if mt == "Image":
            self.quality_menu.configure(values=["Original"])
            self.quality_menu.set("Original")
        elif mt == "Audio":
            self.quality_menu.configure(values=["192 kbps", "128 kbps", "320 kbps"])
            self.quality_menu.set("192 kbps")
        else:
            if getattr(self, "fmt_options", None):
                self.quality_menu.configure(values=[n for n, _ in self.fmt_options])
            else:
                self.quality_menu.configure(values=["Auto (Best)"])
                self.quality_menu.set("Auto (Best)")
            if self.quality_menu.get() not in [n for n, _ in getattr(self, "fmt_options", [])]:
                self.quality_menu.set("Auto (Best)")

    # ================= DOWNLOAD QUEUE =================
    def _show_playlist_selection_dialog(self, entries, platform):
        """Show a dialog to select/deselect playlist items before downloading."""
        dialog = ctk.CTkToplevel(self)
        dialog.title(f"Select {platform} Items to Download")
        dialog.geometry("700x500")
        dialog.transient(self)
        dialog.grab_set()
        dialog.grid_columnconfigure(0, weight=1)
        dialog.grid_rowconfigure(1, weight=1)

        # Header
        header = ctk.CTkFrame(dialog, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 10))
        header.grid_columnconfigure(0, weight=1)
        
        item_label = "Reels" if platform.startswith("Instagram") else "Videos"
        ctk.CTkLabel(header, text=f"Found {len(entries)} {item_label}. Select which to download:",
                     font=("Inter", 14), text_color="#e2e8f0").grid(row=0, column=0, sticky="w")
        
        btn_frame = ctk.CTkFrame(header, fg_color="transparent")
        btn_frame.grid(row=0, column=1, sticky="e")
        ctk.CTkButton(btn_frame, text="Select All", width=100, height=30,
                      command=lambda: self._select_all_in_dialog(entries, True),
                      fg_color=self.accent, hover_color=self.shade(self.accent)).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="Deselect All", width=100, height=30,
                      command=lambda: self._select_all_in_dialog(entries, False),
                      fg_color="#0b1220", hover_color="#16203a").pack(side="left", padx=5)

        # Scrollable list
        scroll = ctk.CTkScrollableFrame(dialog, fg_color="transparent")
        scroll.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 10))
        scroll.grid_columnconfigure(0, weight=1)

        self._dialog_vars = []
        for idx, entry in enumerate(entries):
            row = ctk.CTkFrame(scroll, fg_color="#0d1526", corner_radius=8)
            row.grid(row=idx, column=0, sticky="ew", pady=2)
            row.grid_columnconfigure(1, weight=1)
            
            var = tk.BooleanVar(value=entry.get("selected", True))
            self._dialog_vars.append((var, entry))
            
            chk = ctk.CTkCheckBox(row, text="", variable=var, width=24, height=24)
            chk.grid(row=0, column=0, padx=10, pady=10)
            
            # Thumbnail if available
            if entry.get("thumbnail"):
                thumb_lbl = ctk.CTkLabel(row, text="", width=60, height=40)
                thumb_lbl.grid(row=0, column=1, padx=(0, 10), pady=5)
                self._load_dialog_thumb(entry["thumbnail"], thumb_lbl)
            
            title_lbl = ctk.CTkLabel(row, text=f"#{idx+1} {entry.get('title', 'Untitled')[:80]}",
                                     font=("Inter", 12), text_color="#e2e8f0", anchor="w")
            title_lbl.grid(row=0, column=2, sticky="w", padx=10, pady=10)

        # Buttons
        btn_row = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_row.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 20))
        btn_row.grid_columnconfigure(0, weight=1)
        
        self._dialog_result = None
        
        def on_confirm():
            self._dialog_result = True
            dialog.destroy()
        
        def on_cancel():
            self._dialog_result = False
            dialog.destroy()
        
        ctk.CTkButton(btn_row, text="Cancel", width=120, height=36,
                      fg_color="#3f1d2e", hover_color="#7f1d1d",
                      command=on_cancel).grid(row=0, column=1, padx=5)
        ctk.CTkButton(btn_row, text=f"Download Selected ({sum(1 for e in entries if e.get('selected', True))})",
                      width=250, height=36, font=("Inter", 13, "bold"),
                      fg_color=self.accent, hover_color=self.shade(self.accent),
                      command=on_confirm).grid(row=0, column=2, padx=5)

        self.wait_window(dialog)
        
        # Update entries with user selection
        if self._dialog_result:
            for var, entry in self._dialog_vars:
                entry["selected"] = var.get()
            return True
        return False

    def _select_all_in_dialog(self, entries, select):
        for var, entry in getattr(self, "_dialog_vars", []):
            var.set(select)
        # Update the entries list too
        for entry in entries:
            entry["selected"] = select

    def _load_dialog_thumb(self, thumb_url, label):
        """Load thumbnail for dialog in background."""
        def worker():
            try:
                data = requests.get(thumb_url, timeout=8).content
                img = Image.open(io.BytesIO(data)).convert("RGB")
                img.thumbnail((60, 40))
                photo = ImageTk.PhotoImage(img)
                self.after(1, lambda: label.configure(image=photo) if label.winfo_exists() else None)
                label.image = photo  # Keep reference
            except Exception:
                pass
        threading.Thread(target=worker, daemon=True).start()

    def queue_download(self):
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning("No link", "Paste a link first.", parent=self)
            return
        mt = self.media_type.get()
        q = self.quality_menu.get()

        if mt == "Image":
            qk = None
        elif mt == "Audio":
            qk = q.replace(" kbps", "")
        else:
            for name, sel in getattr(self, "fmt_options", []) or []:
                if name == q:
                    qk = sel
                    break
            else:
                qk = "bestvideo+bestaudio/best"

        entries = getattr(self, "_meta_entries", None) or []
        if entries and self.playlist_var.get():
            # Show selection dialog for playlist/channel/Reels items
            platform = getattr(self, "_meta_info", {}).get("platform", "YouTube")
            if not self._show_playlist_selection_dialog(entries, platform):
                return  # User cancelled
            
            chosen = [e for e in entries if e.get("selected", True)]
            added, skipped = 0, 0
            for entry in chosen:
                if entry["url"] in self.downloads:
                    skipped += 1
                    continue
                self.downloads[entry["url"]] = DownloadItem(self, entry["url"], mt, qk)
                added += 1
            self.log(f"Queueing {added} new video(s) out of {len(entries)} found"
                     + (f" ({skipped} already in queue/history)." if skipped else "."))
            if not added:
                messagebox.showinfo(
                    "Nothing to queue",
                    f"All {len(entries)} videos are already in your queue or history.",
                    parent=self)
                return
            self.render_active()
            self.switch("active")
            self._spawn_workers()
            return

        item = DownloadItem(self, url, mt, qk, allow_playlist=is_collection_url(url))
        self.downloads[url] = item
        self.render_active()
        self.switch("active")
        self.log(f"Queued: {url} ({mt})")
        self._spawn_workers()

    def _spawn_workers(self):
        with self.item_lock:
            ready = [u for u, it in self.downloads.items()
                     if it.status == "Queued"]
            while ready and self.workers < self.max_workers:
                url = ready.pop(0)
                it = self.downloads[url]
                it.status = "Preparing"
                self.workers += 1
                self._refresh_stats()
                t = threading.Thread(target=self._run_worker, args=(it,), daemon=True)
                t.start()

    def _run_worker(self, item):
        """
        Runs one download.

        The try/finally is essential: without it any unexpected exception leaks
        the worker slot and skips _spawn_workers(). After max_workers such
        failures the pool is permanently exhausted and the queue silently stops,
        which is exactly the "downloaded 3 then nothing forever" symptom.
        """
        item.status = "Downloading"
        self.after(1, lambda: self._set_item_status(item.url, "Downloading"))
        self.log(f"Downloading {item.url} as {item.media_type}...")

        ok, result = False, "Download did not run."
        try:
            watchdog = threading.Timer(
                float(self.config.get("job_timeout", 600)),
                lambda: self._on_job_timeout(item),
            )
            watchdog.daemon = True
            watchdog.start()
            try:
                ok, result = item.play(self)
            finally:
                watchdog.cancel()
        except Exception as e:
            result = f"{type(e).__name__}: {e}"
            self.log(f"Unexpected failure: {result}")
        finally:
            with self.item_lock:
                self.workers -= 1

        if item.status == "TimedOut":
            ok, result = False, (
                "Timed out. This video was skipped so the rest of the queue "
                "keeps going."
            )

        if ok:
            item.result = result
            item.status = "Done"
            saved_files = result if isinstance(result, (list, tuple)) else [result]
            for saved in saved_files:
                try:
                    self.add_history(item.url, saved, item.media_type)
                except Exception:
                    pass
            self.log(f"Saved: {len(saved_files)} file(s) -> {saved_files[0] if saved_files else '?'}")
        else:
            item.error = result
            item.status = "Error"
            self.log(f"Failed: {result}" if result else "Failed: unknown error")

        self._refresh_stats()
        self._spawn_workers()
        self.after(1, self.render_active)

    def _on_job_timeout(self, item):
        """Marks a stuck job as timed out so its worker slot can be reclaimed."""
        if item.status in ("Downloading", "Preparing"):
            item.status = "TimedOut"
            item.error = "Timed out"
            item.cancelled = True
            self.log(f"Timed out (skipping): {item.url}")

    def _refresh_stats(self):
        try:
            done = sum(1 for it in self.downloads.values() if it.status == "Done")
            failed = sum(1 for it in self.downloads.values()
                         if it.status in ("Error", "TimedOut"))
            queued = sum(1 for it in self.downloads.values() if it.status == "Queued")
            # Preparing + Downloading are in flight; they must be part of the
            # total too, otherwise the counter under-reports and looks stuck.
            active = sum(1 for it in self.downloads.values()
                         if it.status in ("Preparing", "Downloading"))
            total = len(self.downloads)
            self.stat_workers_lbl.configure(text=f"Concurrency: {self.max_workers}")
            self.stat_total_lbl.configure(text=f"Completed: {len(self.history)}")
            # Shows X of N so a large batch visibly progresses instead of
            # appearing frozen.
            self.stat_queued_lbl.configure(
                text=f"Progress: {done}/{total} done"
                + (f"  ·  {failed} failed" if failed else "")
                + (f"  ·  {active} downloading" if active else "")
                + (f"  ·  {queued} waiting" if queued else ""))
        except Exception:
            pass

    # ================= ACTIVE VIEW =================
    def _set_item_status(self, url, status):
        try:
            if url in self.downloads and url in self.active_widgets:
                row = self.active_widgets[url]
                row["status"].configure(text=status, text_color="#e2e8f0")
        except Exception:
            pass

    def render_active(self):
        for w in self.active_widgets.values():
            try:
                for child in w.values():
                    child.destroy()
            except Exception:
                pass
        self.active_widgets = {}
        for url, it in self.downloads.items():
            self.active_widgets[url] = self._build_row(url, it)
        if not self.downloads:
            contents = self.active_container.winfo_children()
            if contents:
                contents[0].pack_forget()
            self.active_empty.pack(pady=80)
        else:
            try:
                self.active_empty.pack_forget()
            except Exception:
                pass

    def _build_row(self, url, item):
        row = ctk.CTkFrame(self.active_container, fg_color="#0d1526", corner_radius=10)
        row.pack(fill="x", pady=4, padx=6)
        row.grid_columnconfigure(0, weight=1)

        status = ctk.CTkLabel(row, text=item.status, font=("Inter", 12),
                              text_color="#e2e8f0", anchor="w")
        status.grid(row=0, column=0, sticky="w", padx=14, pady=(10, 2))

        bar = ctk.CTkProgressBar(row, height=12, fg_color="#16203a",
                                 progress_color=self.accent, corner_radius=6)
        bar.set(item.progress if item.media_type and hasattr(item, "progress") else 0)
        bar.grid(row=1, column=0, sticky="ew", padx=14, pady=(4, 4))

        stats = ctk.CTkLabel(row, text=item.stat_display, font=("Consolas", 11),
                             text_color="#64748b", anchor="w")
        stats.grid(row=2, column=0, sticky="w", padx=14, pady=(0, 8))

        btns = ctk.CTkFrame(row, fg_color="transparent")
        btns.grid(row=0, column=1, rowspan=3, padx=12)

        ctk.CTkButton(btns, text="Open Folder", width=100, height=30, font=("Inter", 11),
                      fg_color="#0b1220", hover_color="#16203a",
                      command=lambda p=self.config.get("download_path", ""): self.open_folder(p)).pack(pady=2)
        ctk.CTkButton(btns, text="Remove", width=100, height=30, font=("Inter", 11),
                      fg_color="#3f1d2e", hover_color="#7f1d1d",
                      command=lambda u=url: self.remove_item(u)).pack(pady=2)

        return {"status": status, "bar": bar, "stats": stats}

    def remove_item(self, url):
        with self.item_lock:
            if url in self.downloads:
                del self.downloads[url]
        self.after(1, self.render_active)

    def open_folder(self, path):
        try:
            os.startfile(path)
        except Exception:
            messagebox.showinfo("Folder", f"Download folder:\n{path}", parent=self)

    def clear_history(self):
        if messagebox.askyesno("Clear History", "Clear all download history?", parent=self):
            self.history = []
            self.save_history()
            self.render_history()

    def render_history(self):
        try:
            self.history_box.configure(state="normal")
            self.history_box.delete("1.0", "end")
            if not self.history:
                self.history_box.insert("end", "No downloads yet.")
            else:
                for i, h in enumerate(self.history, 1):
                    self.history_box.insert("end", f"{i}.  [{h.get('type','?')}]  {h.get('file','')}\n"
                                                   f"    {h.get('url','')}\n"
                                                   f"    {h.get('time','')}\n\n")
            self.history_box.configure(state="disabled")
        except Exception:
            pass

    # ================= SETTINGS HANDLERS =================
    def on_workers_change(self, val):
        self.max_workers = int(val)
        self.config["max_workers"] = self.max_workers
        self.save_config()
        self._refresh_stats()
        self._spawn_workers()

    def on_playlist_change(self):
        self.config["playlist"] = bool(self.playlist_var.get())
        self.save_config()

    def on_accent_change(self, val):
        self.accent = ACCENTS[val]
        self.config["accent"] = val
        self.save_config()
        self.fetch_btn.configure(fg_color=self.accent, hover_color=self.shade(self.accent))
        self.download_btn.configure(fg_color=self.accent, hover_color=self.shade(self.accent))
        self.quality_menu.configure(button_color=self.accent,
                                    button_hover_color=self.shade(self.accent))

    def on_browser_change(self, val):
        self.config["cookies_browser"] = val if val else ""
        self.save_config()


def json_safeload(text):
    try:
        import json
        return json.loads(text)
    except Exception:
        return {}


def json_dumps(obj, fh):
    try:
        import json
        json.dump(obj, fh, indent=2)
    except Exception:
        pass


def main():
    app = DownloadApp()
    app.mainloop()


if __name__ == "__main__":
    main()