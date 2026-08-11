import customtkinter as ctk
from tkinter import messagebox, filedialog
import yt_dlp
import os
import requests
import threading
import time
import json
from datetime import datetime
from urllib.parse import urlparse

class DownloaderApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("OmniStream | Universal Downloader")
        self.geometry("900x600")
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # Premium background
        try:
            self.configure(fg_color="#071022")
        except Exception:
            pass

        # --- Variables ---
        self.download_path = os.path.join(os.path.expanduser("~"), "Downloads")

        # --- UI Setup ---
        self.grid_columnconfigure(0, weight=1)
        
        # Header
        self.header_label = ctk.CTkLabel(self, text="📥 OMNISTREAM", font=("Inter", 36, "bold"), text_color="#7c3aed")
        self.header_label.pack(pady=(28, 4))

        # Premium badge
        self.premium_badge = ctk.CTkLabel(self, text="PREMIUM", font=("Inter", 10, "bold"), text_color="#fbbf24")
        self.premium_badge.pack(pady=(0, 6))

        self.sub_label = ctk.CTkLabel(self, text="The Universal Video & Image Downloader", font=("Inter", 13), text_color="#94a3b8")
        self.sub_label.pack(pady=(0, 22))

        # Main Input Frame
        self.input_frame = ctk.CTkFrame(self, fg_color="#07142a", corner_radius=12)
        self.input_frame.pack(pady=10, padx=40, fill="x")

        self.url_entry = ctk.CTkEntry(self.input_frame, placeholder_text="Paste your link here (YouTube, Instagram, Image URL, etc.)", height=48, fg_color="#0f1724")
        self.url_entry.pack(fill="x", pady=10)

        # Settings Frame
        self.settings_frame = ctk.CTkFrame(self, fg_color="#07142a", corner_radius=12)
        self.settings_frame.pack(pady=10, padx=40, fill="x")

        self.media_type = ctk.CTkSegmentedButton(self.settings_frame, values=["Video", "Audio", "Image"])
        self.media_type.set("Video")
        self.media_type.pack(side="left", padx=5)

        self.folder_btn = ctk.CTkButton(self.settings_frame, text="📁 Select Folder", fg_color="#0b1220", text_color="#f8fafc", command=self.select_folder)
        self.folder_btn.pack(side="right", padx=5)

        # Progress Section
        self.progress_frame = ctk.CTkFrame(self, fg_color="#07142a", corner_radius=12)
        self.progress_frame.pack(pady=20, padx=40, fill="x")

        self.progress_bar = ctk.CTkProgressBar(self.progress_frame)
        self.progress_bar.set(0)
        self.progress_bar.pack(fill="x", pady=10)

        self.status_label = ctk.CTkLabel(self.progress_frame, text="Ready", font=("Inter", 12))
        self.status_label.pack()

        # Download Button
        self.download_btn = ctk.CTkButton(self, text="🚀 START DOWNLOAD", font=("Inter", 16, "bold"), height=54, fg_color="#7c3aed", hover_color="#5b21b6", command=self.start_download_thread)
        self.download_btn.pack(pady=30, padx=40, fill="x")

        # Footer
        self.footer = ctk.CTkLabel(self, text="Supports 1000+ sites via yt-dlp | Professional Download Suite", font=("Inter", 10), text_color="#6b7280")
        self.footer.pack(side="bottom", pady=10)

        # History storage
        self.history_path = os.path.join(os.path.expanduser("~"), ".omnistream_history.json")
        self.history = self.load_history()

        # Start clipboard watcher
        self.clipboard_last = None
        self.start_clipboard_watcher()

        # History button
        self.history_btn = ctk.CTkButton(self.settings_frame, text="📜 History", fg_color="#0b1220", command=self.open_history_window)
        self.history_btn.pack(side="right", padx=5)

    def select_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.download_path = folder
            messagebox.showinfo("Folder Updated", f"Downloads will be saved to:\n{folder}")

    def load_history(self):
        try:
            if os.path.exists(self.history_path):
                with open(self.history_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception:
            pass
        return []

    def save_history(self):
        try:
            with open(self.history_path, 'w', encoding='utf-8') as f:
                json.dump(self.history, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def add_history(self, url, filename, media_type):
        entry = {
            'time': datetime.utcnow().isoformat() + 'Z',
            'url': url,
            'file': filename,
            'type': media_type
        }
        self.history.insert(0, entry)
        # keep max 100 entries
        self.history = self.history[:100]
        self.save_history()

    def open_history_window(self):
        win = ctk.CTkToplevel(self)
        win.title('Download History')
        win.geometry('700x400')

        listbox = ctk.CTkTextbox(win, width=640, height=300)
        listbox.pack(pady=12, padx=12)

        if not self.history:
            listbox.insert('0.0', 'No history yet.')
        else:
            lines = []
            for i, h in enumerate(self.history, 1):
                ts = h.get('time', '')
                lines.append(f"{i}. [{h.get('type','?')}] {h.get('file','(unknown)')}\n    {h.get('url')}\n    {ts}\n")
            listbox.insert('0.0', '\n'.join(lines))

        btn_frame = ctk.CTkFrame(win)
        btn_frame.pack(fill='x', pady=8, padx=12)

        def clear_history():
            if messagebox.askyesno('Clear History', 'Clear all download history?'):
                self.history = []
                self.save_history()
                listbox.delete('0.0', 'end')
                listbox.insert('0.0', 'No history yet.')

        clear_btn = ctk.CTkButton(btn_frame, text='🗑 Clear', fg_color='#111827', command=clear_history)
        clear_btn.pack(side='right', padx=6)

        close_btn = ctk.CTkButton(btn_frame, text='Close', fg_color='#0b1220', command=win.destroy)
        close_btn.pack(side='right', padx=6)

    def start_clipboard_watcher(self):
        t = threading.Thread(target=self.clipboard_watcher, daemon=True)
        t.start()

    def clipboard_watcher(self):
        while True:
            try:
                clip = None
                try:
                    clip = self.clipboard_get()
                except Exception:
                    clip = None
                if clip and clip != self.clipboard_last:
                    self.clipboard_last = clip
                    # basic URL check
                    if self.is_likely_url(clip):
                        # update entry in UI thread
                        self.after(0, lambda c=clip: self.url_entry.delete(0, 'end') or self.url_entry.insert(0, c))
                        self.after(0, lambda: self.status_label.configure(text='URL detected in clipboard'))
                time.sleep(1.2)
            except Exception:
                time.sleep(2)

    def is_likely_url(self, text):
        if not text or len(text) < 8:
            return False
        text = text.strip()
        if text.startswith('http://') or text.startswith('https://'):
            return True
        # fallback: contains a dot and no spaces
        if ' ' not in text and '.' in text:
            return True
        return False

    def progress_hook(self, d):
        if d['status'] == 'downloading':
            p = d.get('_percent_str', '0%').replace('%', '').strip()
            try:
                percent = float(p) / 100
                self.progress_bar.set(percent)
                self.status_label.configure(text=f"Downloading... {p}% | Speed: {d.get('_speed_str', 'N/A')}")
            except:
                pass
        if d['status'] == 'finished':
            self.progress_bar.set(1.0)
            self.status_label.configure(text="Download Complete! Finalizing...")

    def start_download_thread(self):
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning("Warning", "Please paste a URL first!")
            return
        
        self.download_btn.configure(state="disabled", text="PROCESSING...")
        self.progress_bar.set(0)
        
        thread = threading.Thread(target=self.run_download, args=(url,), daemon=True)
        thread.start()

    def run_download(self, url):
        m_type = self.media_type.get()
        start_time = time.time()
        import shutil
        ffmpeg_exists = shutil.which("ffmpeg") is not None

        try:
            if m_type in ["Video", "Audio"]:
                class MyLogger:
                    def __init__(self, app):
                        self.app = app
                    def debug(self, msg):
                        if "Extracting URL" in msg or "Downloading webpage" in msg:
                            self.app.after(0, lambda: self.app.status_label.configure(text=f"🔍 Analyzing: {msg[:50]}..."))
                    def info(self, msg):
                        self.app.after(0, lambda: self.app.status_label.configure(text=msg[:60]))
                    def warning(self, msg):
                        pass
                    def error(self, msg):
                        pass

                ydl_opts = {
                    'outtmpl': os.path.join(self.download_path, '%(title)s.%(ext)s'),
                    'progress_hooks': [self.progress_hook],
                    'logger': MyLogger(self),
                    'socket_timeout': 30,
                    'retries': 20,
                    'fragment_retries': 20,
                    'ignoreerrors': 'only_download',
                    'noplaylist': False,
                    'lazy_playlist': True, # Start downloading first video immediately
                    'concurrent_fragment_downloads': 10, 
                    'n_threads': 10,
                    'js_runtimes': {'node': {}, 'deno': {}},
                }

                if m_type == "Audio":
                    if ffmpeg_exists:
                        ydl_opts['format'] = 'bestaudio/best'
                        ydl_opts['postprocessors'] = [{
                            'key': 'FFmpegExtractAudio',
                            'preferredcodec': 'mp3',
                            'preferredquality': '192',
                        }]
                    else:
                        ydl_opts['format'] = 'bestaudio/best'
                else: # Video
                    if ffmpeg_exists:
                        ydl_opts['format'] = 'bestvideo+bestaudio/best'
                    else:
                        ydl_opts['format'] = 'best[ext=mp4]/best'

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    self.status_label.configure(text="Connecting to server...")
                    ydl.download([url])
                    # try to find the most recent file saved in the download folder
                    saved_filename = None
                    try:
                        candidates = []
                        for f in os.listdir(self.download_path):
                            full = os.path.join(self.download_path, f)
                            try:
                                mtime = os.path.getmtime(full)
                                if mtime >= start_time - 5:
                                    candidates.append((mtime, full))
                            except Exception:
                                continue
                        if candidates:
                            candidates.sort(reverse=True)
                            saved_filename = candidates[0][1]
                    except Exception:
                        saved_filename = None
                    if saved_filename:
                        self.add_history(url, saved_filename, m_type)
                
            else: # Image Logic
                self.status_label.configure(text="Fetching image...")
                response = requests.get(url, stream=True, timeout=30)
                if response.status_code == 200:
                    ext = response.headers.get('content-type', '').split('/')[-1]
                    filename = f"image_{int(time.time())}.{ext if ext else 'jpg'}"
                    with open(os.path.join(self.download_path, filename), 'wb') as f:
                        f.write(response.content)
                    saved_filename = os.path.join(self.download_path, filename)
                    self.add_history(url, saved_filename, m_type)
                else:
                    raise Exception(f"HTTP Error {response.status_code}")

            self.after(0, lambda: messagebox.showinfo("Success", "Download Task Finished!"))
            self.after(0, lambda: self.status_label.configure(text="Ready"))
            
        except Exception as e:
            err_msg = str(e)
            self.after(0, lambda error=err_msg: messagebox.showerror("Error", f"Failed: {error}"))
        
        finally:
            self.after(0, lambda: self.download_btn.configure(state="normal", text="🚀 START DOWNLOAD"))

if __name__ == "__main__":
    app = DownloaderApp()
    app.mainloop()
