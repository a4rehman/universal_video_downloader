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

# --- Authentication ---
def check_password():
    # Get password from Streamlit Secrets or Environment Variables
    try:
        APP_PASSWORD = st.secrets["APP_PASSWORD"]
    except Exception:
        APP_PASSWORD = os.environ.get("APP_PASSWORD", "admin")

    def password_entered():
        if st.session_state["password"] == APP_PASSWORD:
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if st.session_state.get("password_correct", False):
        return True

    # Show input if not correct or not entered yet
    st.markdown('<div class="title-text" style="font-size: 2.5rem; margin-top: 5rem;">🔒 Access Restricted</div>', unsafe_allow_html=True)
    st.markdown('<div class="subtitle-text">Please enter the password to use OmniStream</div>', unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.text_input("Password", type="password", on_change=password_entered, key="password", label_visibility="collapsed", placeholder="Enter Password")
        if "password_correct" in st.session_state and not st.session_state["password_correct"]:
            st.error("😕 Incorrect password")
            
    return False

if not check_password():
    st.stop()

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
            info = ydl.extract_info(url, download=True)
            # Find the actual filename
            if 'entries' in info: # It's a playlist
                filename = ydl.prepare_filename(info['entries'][0])
            else:
                filename = ydl.prepare_filename(info)
            
            # Ensure extension is correct (sometimes prepare_filename is slightly off for merged files)
            if not os.path.exists(filename):
                # Look for files with the same base name
                base = os.path.splitext(filename)[0]
                for f in os.listdir(download_path):
                    if f.startswith(os.path.basename(base)):
                        filename = os.path.join(download_path, f)
                        break

            return True, filename
    except Exception as e:
        error_msg = str(e)
        if "ffmpeg" in error_msg.lower():
            st.warning("⚠️ FFmpeg not found. Downloading best compatible version (usually 720p)...")
            ydl_opts['format'] = 'best'
            if 'postprocessors' in ydl_opts: ydl_opts.pop('postprocessors', None)
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    filename = ydl.prepare_filename(info)
                    return True, filename
            except Exception as e2:
                return False, f"FFmpeg is missing and fallback failed: {str(e2)}"
        return False, error_msg

    try:
        response = requests.get(url, stream=True, timeout=30)
        if response.status_code == 200:
            content_type = response.headers.get('content-type', '')
            if 'image' in content_type:
                ext = content_type.split('/')[-1].split(';')[0]
                filename = f"image_{int(time.time())}.{ext}"
                full_path = os.path.join(download_path, filename)
                
                with open(full_path, 'wb') as f:
                    f.write(response.content)
                return True, full_path
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
                    with st.spinner("Processing Media... This may take a moment."):
                        success, result = download_video(target_url, media_type, download_folder)
                        if success:
                            st.success("✅ Download complete on server!")
                            with open(result, "rb") as file:
                                st.download_button(
                                    label="💾 SAVE TO COMPUTER",
                                    data=file,
                                    file_name=os.path.basename(result),
                                    mime="application/octet-stream",
                                    use_container_width=True
                                )
                            st.balloons()
                        else:
                            st.error(f"❌ Failed: {result}")
                            if "not available" in result.lower():
                                st.info("💡 Tip: This video might be restricted, private, or blocked in the server's region.")
                else:
                    with st.spinner("Fetching Image..."):
                        success, result = download_image(target_url, download_folder)
                        if success:
                            st.success("✅ Image ready!")
                            with open(result, "rb") as file:
                                st.download_button(
                                    label="💾 SAVE IMAGE TO COMPUTER",
                                    data=file,
                                    file_name=os.path.basename(result),
                                    mime="image/jpeg",
                                    use_container_width=True
                                )
                            st.balloons()
                        else:
                            st.error(f"❌ Failed: {result}")
        
        st.markdown('</div>', unsafe_allow_html=True)

# Footer
st.divider()
st.markdown("<p style='text-align: center; color: #475569;'>Powered by yt-dlp & Streamlit | Professional Download Suite</p>", unsafe_allow_html=True)
