# 📥 OmniStream | Universal Downloader

OmniStream is a professional, universal downloader for videos, audio, and images. It features a modern, animated Streamlit web dashboard and a native desktop GUI built with CustomTkinter. Powered by `yt-dlp` and `requests`, it supports downloading media from over 1000+ popular platforms including YouTube, Instagram, Facebook, TikTok, Twitter, Pinterest, and direct image links.

---

## ✨ Features

### 🌐 Web Dashboard (Streamlit)
*   **Premium Visuals & Animations:** Animated fluid gradient backgrounds, glowing hover-sensitive cards, shimmer title text, and micro-interactions.
*   **Secure Access:** Lock your downloader page with password authentication (configurable via environment variables, default: `admin`).
*   **Flexible Media Types:** Support for Video downloads (mp4 format), Audio extraction (mp3 format), and Image downloads.
*   **Automatic Quality Fallbacks:** Intelligently checks for FFmpeg to download highest resolutions (e.g., 1080p+), with automatic fallbacks to best compatible 720p if FFmpeg is missing.
*   **Real-time Progress:** Displays download speed, percentage completion, and estimated time of arrival (ETA).

### 🖥️ Native Desktop Client (CustomTkinter)
*   **Sleek Dark Theme:** Clean modern window aesthetics configured with CustomTkinter.
*   **Automatic Clipboard Watching:** Runs a background thread that automatically detects valid URLs copied to your clipboard and populates the text field, removing manual paste steps.
*   **Download History Manager:** A local search/review interface showing your download history (saved locally in `~/.omnistream_history.json`).
*   **Folder Selector:** Interactive file dialog to set your custom download folder.
*   **Desktop Integration:** Setup a Windows Desktop shortcut launcher in one click via a PowerShell utility script.

---

## 🛠️ System Requirements

*   **Python:** Version `3.9` or higher.
*   **FFmpeg (Highly Recommended):** Required for merging high-quality video/audio streams (e.g. 1080p resolution) and extracting MP3 audio. Without FFmpeg, OmniStream will download the best pre-merged compatible streams (typically 720p).
    *   *Windows installation:* `winget install Gyan.FFmpeg` or download from [ffmpeg.org](https://ffmpeg.org).
    *   *macOS installation:* `brew install ffmpeg`
    *   *Linux installation:* `sudo apt install ffmpeg`

---

## 🚀 Quick Start & Installation

### 1. Clone the Repository
```bash
git clone https://github.com/your-username/universal_video_downloader.git
cd universal_video_downloader
```

### 2. Set Up a Virtual Environment (Recommended)
```powershell
python -m venv venv
# On Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# On macOS/Linux:
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

---

## 🖥️ Running the Application

### Option A: Launch the Web App (Streamlit)
Start the Streamlit development server:
```bash
streamlit run app.py
```
This will open the web interface in your default browser at `http://localhost:8501`.
*   **Default Password:** `admin` (To customize, set the environment variable `APP_PASSWORD` or add `APP_PASSWORD` to Streamlit secrets).

### Option B: Run the Desktop GUI
Launch the CustomTkinter desktop interface:
```bash
python app_gui.py
```

---

## 📦 Docker Container Deployment

OmniStream is ready for Docker. To build and run the Streamlit web dashboard in a sandboxed container:

1.  **Build the Docker Image:**
    ```bash
    docker build -t omnistream .
    ```
2.  **Run the Container:**
    ```bash
    docker run -d -p 8501:8501 --name omnistream_app -e APP_PASSWORD=your_secure_password omnistream
    ```
3.  Navigate to `http://localhost:8501` to use the downloader.

---

## 📌 Creating a Windows Desktop Shortcut

You can easily generate a native Windows Desktop shortcut for the GUI application:

1.  Open PowerShell as Administrator (or standard user if ExecutionPolicy permits).
2.  Navigate to the repository folder.
3.  Run the helper script:
    ```powershell
    powershell -ExecutionPolicy Bypass -File .\create_shortcut.ps1
    ```
This creates an **OmniStream** shortcut on your Desktop, configured with the correct Python interpreter, directory, and icon automatically.

---

## 📂 File Architecture

*   `app.py` - Core Streamlit web app with custom CSS animations, download handlers, and password protection.
*   `app_gui.py` - CustomTkinter desktop application containing the clipboard watcher, history viewer, and download threads.
*   `create_shortcut.ps1` - PowerShell automation script to build the Windows desktop shortcut.
*   `requirements.txt` - Python project dependencies.
*   `Dockerfile` - Container definition for Dockerized deployment.
*   `packages.txt` - System package listing for deployment hosting platforms.
