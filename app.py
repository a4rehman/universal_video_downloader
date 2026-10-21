import os
import time
import requests
import streamlit as st
from PIL import Image
from io import BytesIO

from src.system import get_system_status, is_network_online
from src.validators import is_valid_url, detect_platform, sanitize_filename, is_instagram_collection_url
from src.filesystem import format_bytes, get_default_download_directory, ensure_directory_exists
from src.formats import parse_raw_formats, AUDIO_CODECS, AUDIO_QUALITIES
from src.media import AdvancedOptions, JobStatus
from src.extractor import extract_media_info
from src.downloader import download_media
from src.queue import QueueManager
from src.history import search_history, clear_history, delete_history_item, add_history_record
from src.favorites import load_favorites, add_favorite, remove_favorite, clear_favorites
from src.settings import load_settings, save_settings
from src.errors import map_exception_to_user_message
from src.ui import inject_custom_css, render_hero, render_legal_notice
from src.database import get_database_status, apply_migrations, sync_local_to_cloud, is_db_configured

# --- Page Config ---
st.set_page_config(
    page_title="OmniStream | One downloader. Almost every platform.",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Inject custom glassmorphism dark SaaS CSS
inject_custom_css()

# --- Global State Initialization ---
if "settings" not in st.session_state:
    st.session_state.settings = load_settings()

if "queue_mgr" not in st.session_state:
    st.session_state.queue_mgr = QueueManager(
        max_concurrency=int(st.session_state.settings.get("max_concurrency", 3)),
        cookies_browser=st.session_state.settings.get("cookies_browser"),
        cookies_file=st.session_state.settings.get("cookies_file"),
    )

if "analyzed_meta" not in st.session_state:
    st.session_state.analyzed_meta = None

if "last_analyzed_url" not in st.session_state:
    st.session_state.last_analyzed_url = ""

if "batch_urls_text" not in st.session_state:
    st.session_state.batch_urls_text = ""

if "is_downloading_now" not in st.session_state:
    st.session_state.is_downloading_now = False

# --- Sidebar Navigation ---
with st.sidebar:
    st.markdown("## ⚡ **OMNISTREAM**")
    st.markdown("<p style='color:#94a3b8; font-size:0.85rem;'>One downloader. Almost every platform.</p>", unsafe_allow_html=True)
    st.divider()

    nav_option = st.radio(
        "Navigation",
        ["Home", "Downloads Queue", "Batch Downloader", "History", "Favorites", "Settings", "Help"],
        index=0,
        label_visibility="collapsed"
    )

    st.divider()
    
    # System Status Mini Widget
    sys_status = get_system_status()
    st.markdown("##### System Status")
    col_s1, col_s2 = st.columns(2)
    with col_s1:
        st.markdown(f"yt-dlp: {'✅' if sys_status['yt_dlp']['status'] else '❌'}")
        st.markdown(f"FFmpeg: {'✅' if sys_status['ffmpeg']['status'] else '❌'}")
    with col_s2:
        st.markdown(f"FFprobe: {'✅' if sys_status['ffprobe']['status'] else '❌'}")
        st.markdown(f"Network: {'⚡' if sys_status['network']['status'] else '⚠️'}")

    db_info = sys_status.get("database", {})
    db_state = db_info.get("status", "Not configured")
    if db_state == "Connected":
        st.markdown(f"DB: 🟢 **TiDB Cloud** (`{db_info.get('version', 1)}`)")
    elif db_state == "Migration required":
        st.markdown(f"DB: 🟡 **Migration Needed**")
    elif db_state == "Connection failed":
        st.markdown(f"DB: 🔴 **Local Fallback**")
    else:
        st.markdown(f"DB: ⚪ **Local Storage**")

    if not sys_status['ffmpeg']['status']:
        st.error(
            "FFmpeg is missing, so separate video-only and audio-only streams cannot be "
            "merged into one playable file. Run `pip install imageio-ffmpeg` and restart the app."
        )
    else:
        st.caption(f"FFmpeg: `{sys_status['ffmpeg']['path']}`")


# ==========================================
# PAGE 1: HOME (SINGLE URL ANALYZER & DOWNLOAD)
# ==========================================
if nav_option == "Home":
    render_hero()

    st.markdown('<div class="omni-glass-card">', unsafe_allow_html=True)
    
    c_url, c_btn = st.columns([5, 1.2])
    with c_url:
        input_url = st.text_input(
            "Paste Media URL",
            placeholder="e.g. https://www.youtube.com/watch?v=dQw4w9WgXcQ or TikTok / Instagram link",
            label_visibility="collapsed"
        )
    with c_btn:
        analyze_clicked = st.button("🔍 Analyze URL", use_container_width=True)

    # Optional channel/collection filter selectors
    shorts_only = False
    reels_only = False
    if input_url and is_valid_url(input_url):
        platform_hint = detect_platform(input_url)
        if platform_hint == "YouTube":
            shorts_only = st.checkbox("📱 Shorts Only", value=False, help="Only discover YouTube Shorts from channel")
        elif platform_hint.startswith("Instagram"):
            reels_only = st.checkbox("🎞️ Reels Only", value=False, help="Only discover Instagram Reels from profile")

    render_legal_notice()
    st.markdown('</div>', unsafe_allow_html=True)

    # Analyze trigger logic
    if analyze_clicked and input_url:
        if not is_valid_url(input_url):
            st.error("❌ Invalid URL provided. Please paste a valid web link starting with http:// or https://")
        else:
            with st.spinner("Analyzing media metadata..."):
                try:
                    meta = extract_media_info(
                        input_url,
                        playlist_limit=int(st.session_state.settings.get("playlist_limit", 0) or 0) or None,
                        shorts_only=shorts_only,
                        reels_only=reels_only,
                        cookies_browser=st.session_state.settings.get("cookies_browser"),
                        cookies_file=st.session_state.settings.get("cookies_file"),
                    )
                    st.session_state.analyzed_meta = meta
                    st.session_state.last_analyzed_url = input_url
                    st.success("✅ Media analyzed successfully!")
                except Exception as e:
                    err_info = map_exception_to_user_message(e)
                    st.error(f"❌ {err_info['title']}: {err_info['user_message']}")
                    st.info(f"💡 Tip: {err_info['tip']}")
                    with st.expander("Technical details"):
                        st.code(err_info['technical_details'])

    # Media Preview & Format Selector Card
    meta = st.session_state.analyzed_meta
    if meta and st.session_state.last_analyzed_url == input_url:
        st.markdown('<div class="omni-glass-card">', unsafe_allow_html=True)
        st.markdown("### 🎬 Media Preview")
        
        m_col1, m_col2 = st.columns([2, 3])
        with m_col1:
            if meta.thumbnail:
                try:
                    st.image(meta.thumbnail, use_container_width=True)
                except Exception:
                    st.markdown("🖼️ *(Thumbnail preview unavailable)*")
            else:
                st.markdown("🖼️ *(No thumbnail available)*")
        
        with m_col2:
            st.markdown(f"#### **{meta.title}**")
            st.markdown(f"**Platform:** `{meta.platform}` | **Uploader:** `{meta.uploader or 'N/A'}`")
            if meta.duration:
                mins, secs = divmod(meta.duration, 60)
                hrs, mins = divmod(mins, 60)
                dur_str = f"{hrs}h {mins}m {secs}s" if hrs else f"{mins}m {secs}s"
                st.markdown(f"**Duration:** `{dur_str}`")
            if meta.view_count:
                st.markdown(f"**Views:** `{meta.view_count:,}`")
            
            # Quick Save to Favorites
            if st.button("⭐ Save to Favorites", key="btn_save_fav"):
                add_favorite(meta.url, meta.title, meta.platform)
                st.toast("Saved to Favorites!", icon="⭐")

        st.divider()

        # Playlist / Channel / Reels Selection Notice
        selected_playlist_urls = []
        if meta.is_playlist:
            if meta.playlist_items:
                # Determine appropriate label based on platform
                if meta.platform.startswith("Instagram"):
                    label = "Reels Listing"
                    item_label = "Reels"
                elif meta.playlist_count > 1:
                    label = "Channel / Playlist"
                    item_label = "videos"
                else:
                    label = "Playlist"
                    item_label = "videos"
                
                st.warning(f"📦 {label} detected! Found **{meta.playlist_count}** accessible {item_label}. "
                           "Each will be downloaded as an individual merged file.")
                p_col1, p_col2 = st.columns(2)
                with p_col1:
                    if st.button(f"Select All {item_label}", key="p_select_all"):
                        for item in meta.playlist_items:
                            item.selected = True
                with p_col2:
                    if st.button(f"Deselect All", key="p_clear_all"):
                        for item in meta.playlist_items:
                            item.selected = False

                with st.expander(f"Inspect {item_label}", expanded=True):
                    for p_item in meta.playlist_items[:50]:  # Show first 50
                        if meta.platform.startswith("Instagram") and p_item.thumbnail:
                            t_col1, t_col2 = st.columns([1, 6])
                            with t_col1:
                                try:
                                    st.image(p_item.thumbnail, width=80)
                                except Exception:
                                    st.markdown("🖼️")
                            with t_col2:
                                p_item.selected = st.checkbox(
                                    f"#{p_item.index} {p_item.title}",
                                    value=p_item.selected,
                                    key=f"pl_chk_{p_item.index}"
                                )
                        else:
                            p_item.selected = st.checkbox(
                                f"#{p_item.index} {p_item.title}",
                                value=p_item.selected,
                                key=f"pl_chk_{p_item.index}"
                            )
                selected_playlist_urls = [p.url for p in meta.playlist_items if p.selected]
                st.info(f"**{len(selected_playlist_urls)}** {item_label} selected for download.")
            else:
                # Empty collection state
                st.warning("⚠️ **No accessible items discovered for this collection.**")
                if meta.platform.startswith("Instagram"):
                    st.info(
                        "🔒 **Instagram Access Notice:** Instagram frequently blocks anonymous access to profiles and reels collections, "
                        "requires login, or restricts access for rate-limiting. OmniStream does not bypass Instagram access controls.\n\n"
                        "💡 **Recommendation:** Try pasting the direct link to an individual Reel (e.g. `https://www.instagram.com/reel/...`) "
                        "or Post (`https://www.instagram.com/p/...`) into the URL box above."
                    )
                else:
                    st.info("💡 **Recommendation:** Check if the collection is public, or try pasting direct individual video URLs.")

        # Download Configuration
        st.markdown("### ⚙️ Download Options")
        f_col1, f_col2, f_col3 = st.columns(3)
        with f_col1:
            media_type = st.selectbox("Media Format", ["Video", "Audio", "Image"], index=0)
        with f_col2:
            if media_type == "Video":
                avail_res = meta.available_resolutions if meta.available_resolutions else ["Best Available", "1080p", "720p", "480p"]
                quality_key = st.selectbox("Resolution / Quality", avail_res, index=0)
                audio_codec = "MP3"
                audio_quality = "192 kbps"
            elif media_type == "Audio":
                quality_key = "Best Available"
                audio_codec = st.selectbox("Audio Format", AUDIO_CODECS, index=0)
                audio_quality = st.selectbox("Audio Bitrate", AUDIO_QUALITIES, index=2)
            else:
                quality_key = "Original Quality"
                audio_codec = "MP3"
                audio_quality = "192 kbps"

        with f_col3:
            default_dir = st.session_state.settings.get("download_path", get_default_download_directory())
            target_dir = st.text_input("Server Download Directory", value=default_dir)

        # Expandable Advanced Options Panel
        with st.expander("🛠️ Advanced Options (Subtitles, Metadata, Custom Filename, Raw Formats)"):
            adv_c1, adv_c2 = st.columns(2)
            with adv_c1:
                custom_filename = st.text_input("Custom Filename (optional)", placeholder="my_custom_video")
                embed_thumb = st.checkbox("Embed Thumbnail into file", value=True)
                embed_meta = st.checkbox("Embed Metadata tags", value=True)
            with adv_c2:
                enable_subs = st.checkbox("Download Subtitles", value=False)
                sub_lang = st.text_input("Subtitle Language Code", value="en")
                auto_subs = st.checkbox("Include Auto-generated Subtitles", value=False)
                embed_subs = st.checkbox("Embed Subtitles into Video", value=False)

            raw_fmt_id = None
            if meta.available_formats and media_type == "Video":
                raw_fmts_parsed = parse_raw_formats(meta.available_formats)
                fmt_labels = ["Auto Selection"] + [f["display_label"] for f in raw_fmts_parsed]
                raw_choice = st.selectbox("Raw yt-dlp Format ID (Advanced Override)", fmt_labels, index=0)
                if raw_choice != "Auto Selection":
                    raw_fmt_id = raw_choice.split("]")[0].replace("[", "").strip()
                    picked = next(
                        (f for f in meta.available_formats if str(f.get("format_id")) == raw_fmt_id),
                        None,
                    )
                    if picked and picked.get("vcodec") not in (None, "none") \
                            and picked.get("acodec") in (None, "none"):
                        raw_fmt_id = f"{raw_fmt_id}+bestaudio/best"
                        st.caption(f"Format `{picked.get('format_id')}` has no audio, "
                                   "so the best audio track is attached automatically.")

        adv_opts = AdvancedOptions(
            custom_filename=custom_filename if custom_filename else None,
            embed_thumbnail=embed_thumb,
            embed_metadata=embed_meta,
            subtitles_enabled=enable_subs,
            subtitle_language=sub_lang,
            auto_subtitles=auto_subs,
            embed_subtitles=embed_subs,
            raw_format_id=raw_fmt_id,
        )

        st.write("")

        # Action Buttons
        if meta.is_playlist:
            if meta.playlist_items:
                btn_label = f"📥 Queue {len(selected_playlist_urls)} Selected Items" if selected_playlist_urls else "📥 Queue Selected Items"
                if st.button(btn_label, use_container_width=True, type="primary"):
                    if not selected_playlist_urls:
                        st.warning("⚠️ Please select at least one item from the playlist checklist above.")
                    else:
                        target_dir = ensure_directory_exists(target_dir)
                        jobs = st.session_state.queue_mgr.enqueue_metadata(
                            meta=meta,
                            media_type=media_type,
                            quality_key=quality_key,
                            audio_codec=audio_codec,
                            audio_quality=audio_quality,
                            output_dir=target_dir,
                            options=adv_opts,
                        )
                        st.success(f"✅ Successfully enqueued **{len(jobs)}** items into the background Downloads Queue!")
                        st.info("Switch to 'Downloads Queue' in the sidebar to monitor download progress.")
            else:
                st.button("📥 No Items to Queue", disabled=True, use_container_width=True)
        else:
            # Single media actions: direct download or background queue
            b_col1, b_col2 = st.columns(2)
            with b_col1:
                start_now = st.button("🚀 Download Now", use_container_width=True, type="primary", disabled=st.session_state.is_downloading_now)
            with b_col2:
                queue_single = st.button("📥 Add to Queue", use_container_width=True, disabled=st.session_state.is_downloading_now)

            if queue_single:
                target_dir = ensure_directory_exists(target_dir)
                try:
                    job = st.session_state.queue_mgr.add_job(
                        url=meta.url,
                        title=meta.title,
                        media_type=media_type,
                        quality_key=quality_key,
                        audio_codec=audio_codec,
                        audio_quality=audio_quality,
                        output_dir=target_dir,
                        options=adv_opts,
                        thumbnail=meta.thumbnail,
                        platform=meta.platform,
                    )
                    st.success(f"✅ Added **{job.title}** to the background Downloads Queue!")
                    st.info("Switch to 'Downloads Queue' in the sidebar to view progress.")
                except Exception as ex:
                    st.error(f"❌ Failed to enqueue: {ex}")

            if start_now:
                target_dir = ensure_directory_exists(target_dir)
                if media_type in ("Video", "Audio") and not sys_status["ffmpeg"]["status"]:
                    st.error("❌ FFmpeg is required to merge streams / convert audio. "
                             "Install it (`pip install imageio-ffmpeg`) and try again.")
                else:
                    progress_bar = st.progress(0.0, text="Initializing download engine...")
                    status_text = st.empty()

                    def home_progress_hook(d):
                        if d.get('status') == 'downloading':
                            p_str = d.get('_percent_str', '0%').strip()
                            try:
                                val = float(p_str.replace('%', '')) / 100.0
                                progress_bar.progress(val, text=f"Downloading: {p_str}")
                                status_text.markdown(f"🚀 **Speed:** `{d.get('_speed_str', 'N/A')}` | **ETA:** `{d.get('_eta_str', 'N/A')}`")
                            except Exception:
                                pass
                        elif d.get('status') == 'finished':
                            progress_bar.progress(1.0, text="Download complete! Merging/Post-processing...")

                    st.session_state.is_downloading_now = True
                    try:
                        with st.spinner("Downloading media..."):
                            success, result = download_media(
                                url=meta.url,
                                media_type=media_type,
                                quality_key=quality_key,
                                output_dir=target_dir,
                                audio_codec=audio_codec,
                                audio_quality=audio_quality,
                                options=adv_opts,
                                cookies_browser=st.session_state.settings.get("cookies_browser"),
                                cookies_file=st.session_state.settings.get("cookies_file"),
                                progress_callback=home_progress_hook,
                            )
                    finally:
                        st.session_state.is_downloading_now = False

                    # Verify positive file size and real file creation on disk
                    if success and os.path.isfile(result) and os.path.getsize(result) > 0:
                        st.success("🎉 **Download Completed Successfully!**")
                        
                        res_size = format_bytes(os.path.getsize(result))
                        st.markdown(f"📁 **Server File Saved:** `{os.path.basename(result)}` (`{res_size}`)")
                        st.caption(f"Full server path: `{result}`")

                        # Auto record history
                        add_history_record(
                            url=meta.url,
                            title=meta.title,
                            platform=meta.platform,
                            format_type=media_type,
                            resolution=quality_key,
                            size_str=res_size,
                            file_path=result,
                            thumbnail=meta.thumbnail,
                            status="Completed"
                        )

                        mime_type = "video/mp4" if media_type == "Video" else ("audio/mpeg" if media_type == "Audio" else "application/octet-stream")
                        with open(result, "rb") as f_data:
                            st.download_button(
                                label="💾 SAVE FILE TO YOUR COMPUTER / DEVICE",
                                data=f_data,
                                file_name=os.path.basename(result),
                                mime=mime_type,
                                use_container_width=True
                            )
                        st.caption("ℹ️ *Click above to save directly to your browser's download folder.*")
                        st.balloons()
                    else:
                        err_mapped = map_exception_to_user_message(Exception(result if not success else "File was not created on disk."))
                        st.error(f"❌ {err_mapped['title']}: {err_mapped['user_message']}")
                        st.info(f"💡 Tip: {err_mapped['tip']}")
                        with st.expander("Technical details"):
                            st.code(err_mapped['technical_details'])

        st.markdown('</div>', unsafe_allow_html=True)


# ==========================================
# PAGE 2: DOWNLOADS QUEUE
# ==========================================
elif nav_option == "Downloads Queue":
    st.markdown("## 📥 Downloads Queue")
    st.markdown("Monitor background download jobs, active progress, speed, and status.")

    queue_mgr = st.session_state.queue_mgr
    all_jobs = queue_mgr.get_all_jobs()

    col_h1, col_h2, col_h3 = st.columns([2, 1, 1])
    with col_h2:
        if st.button("🔄 Refresh Status", use_container_width=True):
            st.rerun()
    with col_h3:
        if st.button("🧹 Clear Completed", use_container_width=True):
            queue_mgr.clear_completed()
            st.rerun()

    active_jobs_count = sum(1 for j in all_jobs if j.status in (JobStatus.QUEUED, JobStatus.DOWNLOADING, JobStatus.PROCESSING))
    if active_jobs_count > 0:
        st.info(f"⚡ **{active_jobs_count}** job(s) actively downloading or queued.")

    if not all_jobs:
        st.info("No active or queued downloads. Paste a URL on the Home page or Batch page to start!")
    else:
        for job in reversed(all_jobs):
            st.markdown('<div class="omni-glass-card">', unsafe_allow_html=True)
            col_j1, col_j2, col_j3 = st.columns([3, 2, 1.5])
            with col_j1:
                st.markdown(f"**{job.title}**")
                st.caption(f"URL: {job.url[:60]}... | Format: {job.media_type} ({job.quality_key})")
            with col_j2:
                badge_class = f"badge-{job.status.value.lower()}"
                st.markdown(f'<span class="{badge_class}">{job.status.value}</span>', unsafe_allow_html=True)
                if job.status == JobStatus.DOWNLOADING:
                    st.caption(f"⚡ {job.speed_str} | ⏳ {job.eta_str}")
                elif job.status == JobStatus.COMPLETED and job.result_file:
                    st.caption(f"Saved: {os.path.basename(job.result_file)}")
                elif job.status == JobStatus.FAILED and job.error_info:
                    st.caption(f"Error: {job.error_info.get('title', 'Download Failed')}")
            with col_j3:
                if job.status == JobStatus.FAILED:
                    if st.button("🔄 Retry", key=f"retry_{job.job_id}"):
                        queue_mgr.retry_job(job.job_id)
                        st.rerun()
                elif job.status in (JobStatus.QUEUED, JobStatus.DOWNLOADING, JobStatus.PROCESSING):
                    if st.button("⏹️ Cancel", key=f"cancel_{job.job_id}"):
                        queue_mgr.cancel_job(job.job_id)
                        st.rerun()

                if st.button("🗑️ Remove", key=f"remove_{job.job_id}"):
                    queue_mgr.remove_job(job.job_id)
                    st.rerun()

            if job.status == JobStatus.DOWNLOADING:
                st.progress(job.progress, text=f"{job.percent_str}")

            if job.status == JobStatus.COMPLETED and job.result_file and os.path.isfile(job.result_file) and os.path.getsize(job.result_file) > 0:
                with open(job.result_file, "rb") as f_file:
                    st.download_button(
                        label="💾 Download to Device",
                        data=f_file,
                        file_name=os.path.basename(job.result_file),
                        key=f"dl_queue_{job.job_id}",
                        use_container_width=True,
                    )

            if job.status == JobStatus.FAILED and job.error_info:
                st.error(f"❌ {job.error_info.get('title', 'Error')}: {job.error_info.get('user_message', 'Download failed')}")
                if job.error_info.get('tip'):
                    st.info(f"💡 Tip: {job.error_info.get('tip')}")
                if job.error_info.get('technical_details'):
                    with st.expander("Technical details"):
                        st.code(job.error_info.get('technical_details'))

            st.markdown('</div>', unsafe_allow_html=True)


# ==========================================
# PAGE 3: BATCH DOWNLOADER
# ==========================================
elif nav_option == "Batch Downloader":
    st.markdown("## 📦 Batch Downloader")
    st.markdown("Paste multiple video, audio, or media links (one per line) to queue batch downloads.")

    st.markdown('<div class="omni-glass-card">', unsafe_allow_html=True)
    batch_input = st.text_area(
        "Paste Links (One URL per line)",
        value=st.session_state.batch_urls_text,
        height=180,
        placeholder="https://www.youtube.com/watch?v=...\nhttps://www.tiktok.com/@user/video/...\nhttps://www.instagram.com/reel/..."
    )

    bc1, bc2, bc3 = st.columns(3)
    with bc1:
        b_media_type = st.selectbox("Batch Media Type", ["Video", "Audio"], key="b_type")
    with bc2:
        b_quality = st.selectbox("Batch Quality", ["Best Available", "1080p", "720p", "480p"], key="b_qual")
    with bc3:
        b_target_dir = st.text_input("Batch Target Directory", value=st.session_state.settings.get("download_path", get_default_download_directory()), key="b_dir")

    st.write("")
    if st.button("🚀 Queue All Batch Items", use_container_width=True, type="primary"):
        urls = [line.strip() for line in batch_input.splitlines() if line.strip() and is_valid_url(line.strip())]
        if not urls:
            st.error("No valid URLs found in the batch text area!")
        else:
            b_target_dir = ensure_directory_exists(b_target_dir)
            queued_count = 0
            skipped_collections = 0
            for u in urls:
                if is_instagram_collection_url(u):
                    skipped_collections += 1
                    continue
                try:
                    st.session_state.queue_mgr.add_job(
                        url=u,
                        title=f"Batch Item: {u[:40]}...",
                        media_type=b_media_type,
                        quality_key=b_quality,
                        output_dir=b_target_dir,
                        platform=detect_platform(u),
                    )
                    queued_count += 1
                except Exception:
                    pass

            if queued_count > 0:
                st.success(f"✅ Successfully queued **{queued_count}** items into the background Downloads Queue!")
                st.info("Switch to 'Downloads Queue' in the sidebar to view progress.")
            if skipped_collections > 0:
                st.warning(f"⚠️ Skipped {skipped_collections} Instagram collection/profile URL(s). "
                           "Please analyze profiles on the Home page to discover and select individual Reels.")

    st.markdown('</div>', unsafe_allow_html=True)


# ==========================================
# PAGE 4: HISTORY
# ==========================================
elif nav_option == "History":
    st.markdown("## 📜 Download History")
    st.markdown("Inspect past completed downloads.")

    hc1, hc2, hc3, hc4 = st.columns([3, 2, 2, 2])
    with hc1:
        search_q = st.text_input("🔍 Search History", placeholder="Search title or platform...")
    with hc2:
        platform_f = st.selectbox("Filter Platform", ["All", "YouTube", "TikTok", "Instagram", "Twitter / X", "Facebook", "Direct Image", "Web Platform"])
    with hc3:
        type_f = st.selectbox("Filter Media Type", ["All", "Video", "Audio", "Image"])
    with hc4:
        sort_f = st.selectbox("Sort By", ["Newest", "Oldest", "Title (A-Z)"])

    st.write("")
    records = search_history(query=search_q, platform_filter=platform_f, type_filter=type_f, sort_by=sort_f)

    c_hbtn, _ = st.columns([2, 5])
    with c_hbtn:
        if st.button("🗑️ Clear Entire History"):
            clear_history()
            st.rerun()

    st.write("")
    if not records:
        st.info("No matching history records found.")
    else:
        for r in records:
            st.markdown('<div class="omni-glass-card">', unsafe_allow_html=True)
            rc1, rc2, rc3 = st.columns([4, 2, 1])
            with rc1:
                st.markdown(f"**{r.get('title')}**")
                st.caption(f"Platform: {r.get('platform')} | Format: {r.get('format')} ({r.get('resolution')}) | Size: {r.get('size')}")
                st.caption(f"Date: {r.get('date')} | Path: {r.get('file_path')}")
            with rc2:
                st.markdown(f"**URL:** `{r.get('url')[:45]}...`")
                # Provide device download button if file still exists on server
                fp = r.get('file_path')
                if fp and os.path.isfile(fp) and os.path.getsize(fp) > 0:
                    try:
                        with open(fp, "rb") as hf:
                            st.download_button(
                                label="💾 Save to Device",
                                data=hf,
                                file_name=os.path.basename(fp),
                                key=f"dl_hist_{r.get('id')}",
                                use_container_width=True,
                            )
                    except Exception:
                        pass
            with rc3:
                if st.button("❌ Delete", key=f"del_h_{r.get('id')}"):
                    delete_history_item(r.get('id'))
                    st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)


# ==========================================
# PAGE 5: FAVORITES
# ==========================================
elif nav_option == "Favorites":
    st.markdown("## ⭐ Saved Favorites")
    st.markdown("Quick access to your saved URLs.")

    favs = load_favorites()

    fc1, fc2 = st.columns([4, 1])
    with fc2:
        if st.button("🗑️ Clear Favorites"):
            clear_favorites()
            st.rerun()

    if not favs:
        st.info("No saved favorites yet. Click '⭐ Save to Favorites' during URL analysis to bookmark links!")
    else:
        for f in favs:
            st.markdown('<div class="omni-glass-card">', unsafe_allow_html=True)
            col_f1, col_f2, col_f3 = st.columns([4, 2, 1])
            with col_f1:
                st.markdown(f"**{f.get('name') or f.get('title')}**")
                st.caption(f"URL: {f.get('url')} | Added: {f.get('added_at')}")
            with col_f2:
                if st.button("⚡ Download Again", key=f"dl_fav_{f.get('id')}"):
                    fav_url = f.get('url')
                    if is_instagram_collection_url(fav_url):
                        st.warning("Instagram collection URLs should be analyzed on the Home page.")
                    else:
                        st.session_state.queue_mgr.add_job(url=fav_url, title=f.get('title') or "Favorite Download")
                        st.toast("Queued favorite for download!", icon="🚀")
            with col_f3:
                if st.button("🗑️ Remove", key=f"del_fav_{f.get('id')}"):
                    remove_favorite(f.get('id'))
                    st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)


# ==========================================
# PAGE 6: SETTINGS
# ==========================================
elif nav_option == "Settings":
    st.markdown("## ⚙️ Application Settings")
    st.markdown("Configure defaults, performance settings, and optional browser cookie profiles.")

    settings = st.session_state.settings

    with st.form("settings_form"):
        st.markdown("#### 📁 Downloads Configuration")
        d_path = st.text_input("Default Download Directory", value=settings.get("download_path", get_default_download_directory()))
        d_media = st.selectbox("Default Media Mode", ["Video", "Audio", "Image"], index=["Video", "Audio", "Image"].index(settings.get("default_media_type", "Video")))
        d_qual = st.selectbox("Default Quality Preset", ["Best Available", "1080p", "720p", "480p"], index=0)

        st.divider()
        st.markdown("#### ⚡ Performance & Engine")
        d_conc = st.slider("Maximum Concurrent Downloads", min_value=1, max_value=5, value=int(settings.get("max_concurrency", 3)))
        
        st.divider()
        st.markdown("#### 🏷️ Metadata & Tagging")
        d_thumb = st.checkbox("Embed Thumbnails by default", value=settings.get("embed_thumbnail", True))
        d_meta = st.checkbox("Embed Metadata tags by default", value=settings.get("embed_metadata", True))

        st.divider()
        st.markdown("#### 🍪 Browser Cookies & Authentication")
        st.caption("Optionally use browser cookies or a cookies.txt file for age-restricted or login-only videos.")
        cookie_options = ["None", "chrome", "firefox", "edge", "brave", "opera", "vivaldi", "chromium", "safari"]
        saved_browser = settings.get("cookies_browser") or "None"
        b_idx = cookie_options.index(saved_browser.lower()) if saved_browser and saved_browser.lower() in cookie_options else 0
        d_browser_choice = st.selectbox("Browser Cookie Profile", cookie_options, index=b_idx)
        d_browser = None if d_browser_choice == "None" else d_browser_choice
        d_cookies_file = st.text_input("Custom cookies.txt File Path (Optional)", value=settings.get("cookies_file", "") or "")

        submitted = st.form_submit_button("💾 Save Settings", use_container_width=True)
        if submitted:
            new_cfg = {
                "download_path": d_path,
                "default_media_type": d_media,
                "default_quality": d_qual,
                "max_concurrency": d_conc,
                "embed_thumbnail": d_thumb,
                "embed_metadata": d_meta,
                "cookies_browser": d_browser,
                "cookies_file": d_cookies_file,
            }
            save_settings(new_cfg)
            st.session_state.settings = load_settings()
            st.session_state.queue_mgr.set_concurrency(d_conc)
            st.session_state.queue_mgr.set_cookies(
                cookies_browser=d_browser,
                cookies_file=d_cookies_file,
            )
            st.success("✅ Settings updated successfully!")

    st.markdown('<div class="omni-glass-card">', unsafe_allow_html=True)
    st.markdown("#### ☁️ TiDB Cloud Serverless Database")
    st.markdown("OmniStream syncs download history, favorites, and user preferences with TiDB Cloud Serverless.")

    db_health = get_database_status()
    st.markdown(f"**Status:** {db_health.get('label')}")
    st.caption(f"{db_health.get('message')}")

    col_db1, col_db2, col_db3 = st.columns(3)
    with col_db1:
        if st.button("🔄 Test Connection", use_container_width=True):
            status = get_database_status()
            if status.get("connected"):
                st.success(f"Connected to TiDB! Schema version: v{status.get('version', 0)}")
            else:
                st.warning(f"Connection status: {status.get('label')} - {status.get('message')}")
    with col_db2:
        if st.button("⚡ Run Migrations", use_container_width=True):
            ok, msg = apply_migrations()
            if ok:
                st.success(f"✅ {msg}")
            else:
                st.error(f"❌ {msg}")
    with col_db3:
        if st.button("📥 Sync Local to Cloud", use_container_width=True):
            h_count, f_count = sync_local_to_cloud()
            st.success(f"Synced {h_count} history records and {f_count} favorites to TiDB Cloud!")

    with st.expander("📖 TiDB Cloud Setup Instructions"):
        st.markdown("""
        To connect OmniStream to your TiDB Cloud Serverless cluster, set the following environment variables (or Streamlit Secrets):
        
        **In `.env` or Environment Variables:**
        ```bash
        TIDB_HOST=gateway01.us-east-1.prod.aws.tidbcloud.com
        TIDB_PORT=4000
        TIDB_USER=your_user_prefix.root
        TIDB_PASSWORD=your_secure_password
        TIDB_DATABASE=omnistream
        TIDB_SSL_MODE=REQUIRED
        ```

        **In Streamlit Community Cloud (`secrets.toml`):**
        ```toml
        [database]
        host = "gateway01.us-east-1.prod.aws.tidbcloud.com"
        port = 4000
        user = "your_user_prefix.root"
        password = "your_secure_password"
        database = "omnistream"
        ssl_mode = "REQUIRED"
        ```
        """)
    st.markdown('</div>', unsafe_allow_html=True)


# ==========================================
# PAGE 7: HELP & ABOUT
# ==========================================
elif nav_option == "Help":
    st.markdown("## ❓ Help & Troubleshooting")
    st.markdown("### OmniStream Documentation")

    st.markdown("""
    #### 🚀 Key Features
    - **Universal Media Extractor**: Supports YouTube, TikTok, Instagram, Twitter/X, Facebook, Pinterest, Vimeo, and direct image links.
    - **Multi-Resolution Video**: Best Available, 4K, 1440p, 1080p, 720p, 480p, 360p.
    - **High Fidelity Audio**: MP3, M4A, WAV, Opus at 320, 256, 192, 128 kbps.
    - **Subtitles Engine**: Download manual or auto-generated SRT/VTT subtitles.
    - **Batch & Playlist Manager**: Select individual playlist items or paste multi-line URL batches.
    
    #### 💡 Frequently Asked Questions
    - **How do I save downloads to my local device?**
      OmniStream downloads and merges the highest quality streams on the host server. Once complete, click **💾 Save to Device** on the Home page, Downloads Queue, or History page to transfer the finished file directly into your browser's local downloads folder.
    - **Why am I getting a YouTube Bot Check / Sign in error?**
      YouTube enforces proof-of-origin tokens on datacenter IPs. OmniStream uses automatic client fallback chains. You can also select your browser under Settings to use browser cookies.
    - **Why is FFmpeg needed?**
      FFmpeg is used to merge separate high-definition video and audio streams into single MP4 files and convert audio formats.
    - **How does Instagram extraction work?**
      Individual Instagram Reel and Post URLs can be downloaded directly. When analyzing a profile or reels collection, OmniStream discovers accessible Reels and allows selecting individual items. Anonymous access to private or restricted profiles is subject to Instagram platform limits.

    #### 🔒 Legal Disclaimer
    OmniStream is intended for downloading content that you have permission or the right to access. Always respect creator rights and platform terms of service.
    """)
