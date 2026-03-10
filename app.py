import streamlit as st
import yt_dlp
import os
import requests
from PIL import Image
from io import BytesIO
import time

# --- Page Config ---
st.set_page_config(
    page_title="OmniStream | Universal Downloader",
    page_icon="📥",
    layout="wide"
)

# --- Custom CSS for Premium Look ---
st.markdown("""
<style>
    .main { background-color: #0f172a; }
    .stApp { background: radial-gradient(circle at top left, #1e293b, #0f172a); }
    
    .title-text {
        font-family: 'Inter', sans-serif;
        font-size: 3.5rem;
        font-weight: 800;
        background: -webkit-linear-gradient(#60a5fa, #3b82f6);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.5rem;
        text-align: center;
    }
    
    .subtitle-text {
        color: #94a3b8;
        font-size: 1.2rem;
        text-align: center;
        margin-bottom: 3rem;
    }

    .download-card {
        background: rgba(30, 41, 59, 0.5);
        border: 1px solid #334155;
        padding: 30px;
        border-radius: 20px;
        backdrop-filter: blur(10px);
    }
    
    .stTextInput>div>div>input {
        background-color: #1e293b;
        color: white;
        border: 1px solid #334155;
        border-radius: 10px;
    }
</style>
""", unsafe_allow_html=True)

# --- Logic Functions ---

def download_video(url, format_type, download_path):
    # Base options
    ydl_opts: dict = {
        'outtmpl': os.path.join(download_path, '%(title)s.%(ext)s'),
        'noplaylist': False,
        'ignoreerrors': True,
        'no_warnings': False,
        'js_runtimes': {'node': {}, 'deno': {}},
        'remote_components': ['ejs:github'],
    }

    # Format selection based on availability of ffmpeg
    if format_type == 'Video':
        # 'best' usually gives a pre-merged 720p file which doesn't need ffmpeg
        # 'bestvideo+bestaudio' requires ffmpeg to merge
        ydl_opts['format'] = 'bestvideo+bestaudio/best'
        ydl_opts['merge_output_format'] = 'mp4'
    else:
        ydl_opts['format'] = 'bestaudio/best'
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]

    progress_bar = st.progress(0, text="Initializing...")
    status_text = st.empty()

    def progress_hook(d):
        if d['status'] == 'downloading':
            p = d.get('_percent_str', '0%').replace('%', '')
            try:
                progress_bar.progress(float(p)/100, text=f"Downloading: {d.get('_percent_str', '0%')}")
                status_text.write(f"🚀 Speed: {d.get('_speed_str', 'N/A')} | ETA: {d.get('_eta_str', 'N/A')}")
            except:
                pass
        if d['status'] == 'finished':
            progress_bar.progress(1.0, text="Download Complete! Processing...")

    ydl_opts['progress_hooks'] = [progress_hook]

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        return True, "Download Successful!"
    except Exception as e:
        error_msg = str(e)
        if "ffmpeg" in error_msg.lower():
            # Fallback to 'best' format if ffmpeg is missing
            st.warning("⚠️ FFmpeg not found. Downloading best compatible version (usually 720p)...")
            ydl_opts['format'] = 'best' # This doesn't require merging
            if 'postprocessors' in ydl_opts: ydl_opts.pop('postprocessors', None)
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
                return True, "Download Successful (720p Fallback)!"
            except Exception as e2:
                return False, f"FFmpeg is missing and fallback failed: {str(e2)}"
        return False, error_msg

def download_image(url, download_path):
    try:
        response = requests.get(url, stream=True)
        if response.status_code == 200:
            content_type = response.headers.get('content-type', '')
            if 'image' in content_type:
                ext = content_type.split('/')[-1]
                filename = f"image_{int(time.time())}.{ext}"
                full_path = os.path.join(download_path, filename)
                
                with open(full_path, 'wb') as f:
                    f.write(response.content)
                return True, f"Image saved: {filename}"
            else:
                return False, "URL does not point to a valid image."
        else:
            return False, f"Error: Status code {response.status_code}"
    except Exception as e:
        return False, str(e)

# --- Sidebar ---
with st.sidebar:
    st.image("https://img.icons8.com/nolan/128/download.png", width=80)
    st.markdown("### Settings")
    download_folder = st.text_input("Download Folder", value=os.path.join(os.path.expanduser("~"), "Downloads"))
    st.divider()
    st.info("Supports: YouTube, Instagram, Facebook, TikTok, Twitter, Pinterest & More.")

# --- Header ---
st.markdown('<div class="title-text">OmniStream</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle-text">The Universal Video & Image Downloader</div>', unsafe_allow_html=True)

# --- Main UI ---
col1, col2, col3 = st.columns([1, 6, 1])

with col2:
    with st.container():
        st.markdown('<div class="download-card">', unsafe_allow_html=True)
        
        target_url = st.text_input("🔗 Paste URL here (Video, Playlist, or Image):", placeholder="https://www.youtube.com/watch?v=... or https://site.com/image.jpg")
        
        c1, c2 = st.columns(2)
        with c1:
            media_type = st.selectbox("Media Type", ["Video", "Audio", "Image"])
        with c2:
            quality = st.selectbox("Resolution/Quality", ["Best Available", "1080p", "720p", "480p"])
            
        st.write("")
        if st.button("🚀 Start Download", use_container_width=True):
            if not target_url:
                st.error("Please paste a URL first!")
            else:
                if not os.path.exists(download_folder):
                    os.makedirs(download_folder)
                
                if media_type in ["Video", "Audio"]:
                    with st.spinner("Analyzing URL..."):
                        success, message = download_video(target_url, media_type, download_folder)
                        if success:
                            st.success(message)
                            st.balloons()
                        else:
                            st.error(f"Failed: {message}")
                else:
                    with st.spinner("Fetching Image..."):
                        success, message = download_image(target_url, download_folder)
                        if success:
                            st.success(message)
                            st.balloons()
                        else:
                            st.error(f"Failed: {message}")
        
        st.markdown('</div>', unsafe_allow_html=True)

# Footer
st.divider()
st.markdown("<p style='text-align: center; color: #475569;'>Powered by yt-dlp & Streamlit | Professional Download Suite</p>", unsafe_allow_html=True)
