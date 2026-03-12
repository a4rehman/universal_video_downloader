import customtkinter as ctk
from tkinter import messagebox, filedialog
import yt_dlp
import os
import requests
import threading
import time

class DownloaderApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("OmniStream | Universal Downloader")
        self.geometry("800x550")
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # --- Variables ---
        self.download_path = os.path.join(os.path.expanduser("~"), "Downloads")

        # --- UI Setup ---
        self.grid_columnconfigure(0, weight=1)
        
        # Header
        self.header_label = ctk.CTkLabel(self, text="📥 OMNISTREAM", font=("Inter", 32, "bold"), text_color="#60a5fa")
        self.header_label.pack(pady=(30, 5))
        
        self.sub_label = ctk.CTkLabel(self, text="The Universal Video & Image Downloader", font=("Inter", 14), text_color="#94a3b8")
        self.sub_label.pack(pady=(0, 30))

        # Main Input Frame
        self.input_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.input_frame.pack(pady=10, padx=40, fill="x")

        self.url_entry = ctk.CTkEntry(self.input_frame, placeholder_text="Paste your link here (YouTube, Instagram, Image URL, etc.)", height=45)
        self.url_entry.pack(fill="x", pady=10)

        # Settings Frame
        self.settings_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.settings_frame.pack(pady=10, padx=40, fill="x")

        self.media_type = ctk.CTkSegmentedButton(self.settings_frame, values=["Video", "Audio", "Image"])
        self.media_type.set("Video")
        self.media_type.pack(side="left", padx=5)

        self.folder_btn = ctk.CTkButton(self.settings_frame, text="📁 Select Folder", fg_color="#334155", command=self.select_folder)
        self.folder_btn.pack(side="right", padx=5)

        # Progress Section
        self.progress_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.progress_frame.pack(pady=20, padx=40, fill="x")

        self.progress_bar = ctk.CTkProgressBar(self.progress_frame)
        self.progress_bar.set(0)
        self.progress_bar.pack(fill="x", pady=10)

        self.status_label = ctk.CTkLabel(self.progress_frame, text="Ready", font=("Inter", 12))
        self.status_label.pack()

        # Download Button
        self.download_btn = ctk.CTkButton(self, text="🚀 START DOWNLOAD", font=("Inter", 16, "bold"), height=50, command=self.start_download_thread)
        self.download_btn.pack(pady=30, padx=40, fill="x")

        # Footer
        self.footer = ctk.CTkLabel(self, text="Supports 1000+ sites via yt-dlp", font=("Inter", 10), text_color="#475569")
        self.footer.pack(side="bottom", pady=10)

    def select_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.download_path = folder
            messagebox.showinfo("Folder Updated", f"Downloads will be saved to:\n{folder}")

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
                
            else: # Image Logic
                self.status_label.configure(text="Fetching image...")
                response = requests.get(url, stream=True, timeout=30)
                if response.status_code == 200:
                    ext = response.headers.get('content-type', '').split('/')[-1]
                    filename = f"image_{int(time.time())}.{ext if ext else 'jpg'}"
                    with open(os.path.join(self.download_path, filename), 'wb') as f:
                        f.write(response.content)
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
