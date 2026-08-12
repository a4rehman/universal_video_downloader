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
from datetime import datetime
from urllib.parse import urlparse
from PIL import Image, ImageTk

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

ILLEGAL = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def sanitize(name):
    return ILLEGAL.sub("_", name or "video")


class DownloadItem:
    def __init__(self, app, url, media_type, quality_key):
        self.app = app
        self.url = url
        self.media_type = media_type
        self.quality_key = quality_key
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

    def build_opts(self):
        opts = {
            'outtmpl': os.path.join(self.app.config.get("download_path", os.path.expanduser("~/Downloads")), '%(title)s.%(ext)s'),
            'noplaylist': not self.app.config.get("playlist", True),
            'ignoreerrors': True,
            'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
        }
        browser = self.app.config.get("cookies_browser")
        if browser and not self.app.cookie_locked.is_set():
            opts['cookiesfrombrowser'] = (browser,)
            self.app.log(f"Using cookies from browser: {browser}")

        if self.media_type == "Video":
            opts['format'] = self.quality_key or 'bestvideo+bestaudio/best'
            opts['merge_output_format'] = 'mp4'
        else:
            q = (self.quality_key or '192').replace('k', '').strip()
            opts['format'] = 'bestaudio/best'
            opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': q,
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

        ydl_opts = self.build_opts()

        def progress_hook(d):
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

        ydl_opts['progress_hooks'] = [progress_hook]
        self.stat_display = "Preparing..."
        self._sync_row()

        cookie_tried = False
        while True:
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(self.url, download=True)
                    if 'entries' in info:
                        first = next((e for e in info['entries'] if e), None)
                        filename = ydl.prepare_filename(first) if first else None
                    else:
                        filename = ydl.prepare_filename(info)

                    if filename and not os.path.exists(filename):
                        base = os.path.splitext(filename)[0]
                        for f in os.listdir(download_path):
                            if f.startswith(os.path.basename(base)):
                                filename = os.path.join(download_path, f)
                                break
                    if not filename:
                        return False, "Could not determine output filename."
                    return True, filename
            except Exception as e:
                msg = str(e)
                if cookie_tried:
                    return False, msg
                if "cookie" in msg.lower() or "could not copy" in msg.lower():
                    app.cookie_locked.set()
                    app.log("Chrome cookie DB is locked (Chrome running). Retrying without cookies...")
                    ydl_opts.pop('cookiesfrombrowser', None)
                    cookie_tried = True
                    continue
                if "ffmpeg" in msg.lower():
                    ydl_opts['format'] = 'best'
                    ydl_opts.pop('postprocessors', None)
                    try:
                        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                            info = ydl.extract_info(self.url, download=True)
                            filename = ydl.prepare_filename(info)
                            return True, filename
                    except Exception as e2:
                        return False, f"FFmpeg missing and fallback failed: {str(e2)}"
                if "sign in" in msg.lower():
                    return False, ("YouTube blocked this download because cookies couldn't be read.\n"
                                   "Close Chrome completely and try again, or set cookies in Settings.")
                return False, msg

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
            opts = {'quiet': True, 'no_warnings': True, 'skip_download': True}
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                self.after(1, lambda: self._render_meta(info, mt, url))
                return
        except Exception as e:
            self.after(1, lambda: self._render_meta_fail(str(e)[:300]))
        finally:
            self.after(1, lambda: self.set_analyzing(False))

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
        if entries:
            duration = sum(e.get("duration") or 0 for e in entries if e)
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

        item = DownloadItem(self, url, mt, qk)
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
        item.status = "Downloading"
        self.after(1, lambda: self._set_item_status(item.url, "Downloading"))
        self.log(f"⏳ Downloading {item.url} as {item.media_type}...")
        ok, result = item.play(self)
        with self.item_lock:
            self.workers -= 1
        if ok:
            item.result = result
            item.status = "Done"
            try:
                self.add_history(item.url, result, item.media_type)
            except Exception:
                pass
            self.log(f"✅ Saved: {result}")
        else:
            item.error = result
            item.status = "Error"
            self.log(f"❌ {result}" if result else "❌ Unknown error")
            self.log("   Tip: for YouTube block, close Chrome fully and set cookies in Settings.")
        self._refresh_stats()
        self._spawn_workers()
        self.after(1, self.render_active)

    def _refresh_stats(self):
        try:
            done = sum(1 for it in self.downloads.values() if it.status == "Done")
            queued = sum(1 for it in self.downloads.values()
                         if it.status in ("Queued", "Preparing"))
            self.stat_workers_lbl.configure(text=f"Concurrency: {self.max_workers}")
            self.stat_total_lbl.configure(text=f"Completed: {len(self.history)}")
            self.stat_queued_lbl.configure(text=f"Queued: {queued}")
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