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

# --- Custom CSS for Premium & Professional Looks ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700;800&display=swap');
    
    /* Global Styles */
    html, body, [class*="css"], .stApp {
        font-family: 'Outfit', sans-serif !important;
    }

    /* Background Shifting Gradient */
    @keyframes gradient-bg {
        0% { background-position: 0% 50%; }
        50% { background-position: 100% 50%; }
        100% { background-position: 0% 50%; }
    }
    
    .stApp {
        background: linear-gradient(-45deg, #090d16, #0f172a, #1e1b4b, #090d16);
        background-size: 400% 400%;
        animation: gradient-bg 18s ease infinite;
        color: #f8fafc;
    }
    
    /* Header Styles */
    @keyframes title-shimmer {
        0% { background-position: 0% 50%; }
        50% { background-position: 100% 50%; }
        100% { background-position: 0% 50%; }
    }
    
    .title-text {
        font-size: 4rem;
        font-weight: 800;
        background: linear-gradient(90deg, #38bdf8, #818cf8, #c084fc, #f472b6, #38bdf8);
        background-size: 200% auto;
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        animation: title-shimmer 6s linear infinite;
        margin-bottom: 0.2rem;
        text-align: center;
        letter-spacing: -0.05em;
    }
    
    .subtitle-text {
        color: #94a3b8;
        font-size: 1.3rem;
        text-align: center;
        margin-bottom: 2.5rem;
        font-weight: 300;
    }

    /* Card Layout (Glassmorphism) */
    @keyframes fadeInUp {
        from {
            opacity: 0;
            transform: translateY(30px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }

    .download-card {
        background: rgba(15, 23, 42, 0.6);
        border: 1px solid rgba(129, 140, 248, 0.25);
        padding: 40px;
        border-radius: 24px;
        backdrop-filter: blur(20px);
        -webkit-backdrop-filter: blur(20px);
        box-shadow: 0 20px 50px rgba(0, 0, 0, 0.4);
        animation: fadeInUp 0.8s cubic-bezier(0.16, 1, 0.3, 1) forwards;
        transition: all 0.4s ease;
    }
    
    .download-card:hover {
        border-color: rgba(129, 140, 248, 0.45);
        box-shadow: 0 25px 60px rgba(99, 102, 241, 0.2);
    }
    
    /* Inputs Styling */
    .stTextInput>div>div>input {
        background-color: rgba(15, 23, 42, 0.85) !important;
        color: #ffffff !important;
        border: 1px solid rgba(71, 85, 105, 0.8) !important;
        border-radius: 14px !important;
        padding: 12px 16px !important;
        font-size: 1rem !important;
        transition: all 0.3s ease !important;
    }
    
    .stTextInput>div>div>input:focus {
        border-color: #818cf8 !important;
        box-shadow: 0 0 0 4px rgba(129, 140, 248, 0.25) !important;
    }

    /* Selectboxes Styling */
    .stSelectbox>div>div>div {
        background-color: rgba(15, 23, 42, 0.85) !important;
        color: #ffffff !important;
        border: 1px solid rgba(71, 85, 105, 0.8) !important;
        border-radius: 14px !important;
    }

    /* Buttons with Pulsing Glow */
    .stButton>button {
        background: linear-gradient(135deg, #6366f1, #4f46e5) !important;
        color: white !important;
        font-weight: 700 !important;
        font-size: 1.1rem !important;
        border: none !important;
        border-radius: 14px !important;
        padding: 14px 28px !important;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
        box-shadow: 0 4px 15px rgba(99, 102, 241, 0.35) !important;
        width: 100%;
    }
    
    .stButton>button:hover {
        background: linear-gradient(135deg, #4f46e5, #3730a3) !important;
        transform: translateY(-2px) !important;
        box-shadow: 0 10px 25px rgba(99, 102, 241, 0.65) !important;
    }
    
    .stButton>button:active {
        transform: translateY(1px) !important;
    }

    /* Download button specific styles */
    .stDownloadButton>button {
        background: linear-gradient(135deg, #10b981, #059669) !important;
        box-shadow: 0 4px 15px rgba(16, 185, 129, 0.35) !important;
    }
    .stDownloadButton>button:hover {
        background: linear-gradient(135deg, #059669, #047857) !important;
        box-shadow: 0 10px 25px rgba(16, 185, 129, 0.65) !important;
    }

    /* Info boxes styling */
    .stAlert {
        border-radius: 16px !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
    }

    /* Divider */
    hr {
        border-color: rgba(255, 255, 255, 0.1) !important;
    }
</style>
""", unsafe_allow_html=True)

# --- Authentication ---
def check_password():
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

    st.markdown('<div class="title-text" style="font-size: 2.5rem; margin-top: 5rem;">🔒 Access Restricted</div>', unsafe_allow_html=True)
    st.markdown('<div class="subtitle-text">Please enter the password to access OmniStream</div>', unsafe_allow_html=True)
    
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
    if not os.path.exists(download_path):
        os.makedirs(download_path)

    # Track directory state to robustly capture the correct output file
    try:
        files_before = set(os.listdir(download_path))
    except Exception:
        files_before = set()

    # Base options
    ydl_opts: dict = {
        'outtmpl': os.path.join(download_path, '%(title)s.%(ext)s'),
        'noplaylist': False,
        'ignoreerrors': False,
        'no_warnings': False,
        'nocheckcertificate': True,
        'quiet': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'web']
            }
        },
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="121", "Google Chrome";v="121"',
        },
        'js_runtimes': {'node': {}, 'deno': {}},
        'remote_components': ['ejs:github'],
    }

    if format_type == 'Video':
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
            progress_bar.progress(1.0, text="Download Complete! Post-processing...")

    ydl_opts['progress_hooks'] = [progress_hook]

    filename = None
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if 'entries' in info:
                filename = ydl.prepare_filename(info['entries'][0])
            else:
                filename = ydl.prepare_filename(info)
    except Exception as e:
        error_msg = str(e)
        if "ffmpeg" in error_msg.lower():
            st.warning("⚠️ FFmpeg issue. Falling back to best compatible resolution...")
            ydl_opts['format'] = 'best'
            if 'postprocessors' in ydl_opts: 
                ydl_opts.pop('postprocessors', None)
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    filename = ydl.prepare_filename(info)
            except Exception as e2:
                return False, f"Fallback failed: {str(e2)}"
        else:
            return False, error_msg

    # Robust detection of the downloaded file
    if filename and os.path.exists(filename):
        return True, filename

    # Look for newly added files in directory
    try:
        files_after = set(os.listdir(download_path))
        new_files = files_after - files_before
        if new_files:
            new_files_list = [os.path.join(download_path, f) for f in new_files]
            newest_file = max(new_files_list, key=os.path.getmtime)
            if os.path.exists(newest_file):
                return True, newest_file
    except Exception:
        pass

    # Look for files matching the base title
    if filename:
        base = os.path.splitext(filename)[0]
        try:
            for f in os.listdir(download_path):
                if f.startswith(os.path.basename(base)):
                    full_p = os.path.join(download_path, f)
                    if os.path.exists(full_p):
                        return True, full_p
        except Exception:
            pass

    return False, "File downloaded successfully but could not be located on disk."

def download_image(url, download_path):
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
            return False, f"HTTP Error Status: {response.status_code}"
    except Exception as e:
        return False, str(e)

# --- Sidebar ---
with st.sidebar:
    st.image("https://img.icons8.com/nolan/128/download.png", width=70)
    st.markdown("### Settings")
    
    # Safe default path for Streamlit Cloud deployments
    default_dir = os.path.join(os.getcwd(), "downloads")
    download_folder = st.text_input("Download Target Directory", value=default_dir)
    
    st.divider()
    st.info("💡 Supports: YouTube, Instagram, Facebook, TikTok, Twitter, Pinterest, & more.")

# --- Header ---
st.markdown('<div class="title-text">OmniStream</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle-text">The Premium Universal Video & Image Downloader</div>', unsafe_allow_html=True)

# --- Main UI ---
col1, col2, col3 = st.columns([1, 6, 1])

with col2:
    with st.container():
        st.markdown('<div class="download-card">', unsafe_allow_html=True)
        
        target_url = st.text_input("🔗 Paste Media Link (Video, Playlist, or Image):", placeholder="e.g., https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        
        c1, c2 = st.columns(2)
        with c1:
            media_type = st.selectbox("Type", ["Video", "Audio", "Image"])
        with c2:
            quality = st.selectbox("Preferred Quality", ["Best Available", "1080p", "720p", "480p"])
            
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
                        if success and os.path.exists(result):
                            st.success("✅ Processed successfully!")
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
                            if "not available" in str(result).lower():
                                st.info("💡 Tip: This video might be private, region-restricted, or requires authentication.")
                else:
                    with st.spinner("Fetching Image..."):
                        success, result = download_image(target_url, download_folder)
                        if success and os.path.exists(result):
                            st.success("✅ Image processed!")
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
st.markdown("<p style='text-align: center; color: #64748b;'>Powered by yt-dlp & Streamlit | Professional Download Suite</p>", unsafe_allow_html=True)
