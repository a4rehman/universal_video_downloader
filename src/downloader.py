"""
Core Downloader Service for OmniStream using yt-dlp & FFmpeg.
"""

import os
import time
import requests
import yt_dlp
from typing import Callable, Optional, Tuple, Dict, Any
from .validators import sanitize_filename
from .formats import build_ytdlp_format_string
from .media import AdvancedOptions, JobStatus
from .errors import FFmpegError  # noqa: F401  (re-exported for callers/tests)
from .extractor import DESKTOP_USER_AGENT
from .system import get_ffmpeg_location, has_ffmpeg, resolve_js_runtime
from .filesystem import cleanup_stream_artifacts, is_stream_artifact

YOUTUBE_CLIENT_CHAINS = [
    ['visionos', 'web_embedded'],
    ['android_vr', 'tv', 'web_safari'],
    ['web', 'android', 'mweb'],
]

FFMPEG_MISSING_MESSAGE = (
    "FFmpeg was not found, so separate audio-only and video-only streams cannot be "
    "merged into one playable video file. Install FFmpeg (winget install ffmpeg) "
    "or install the bundled build (pip install imageio-ffmpeg), then try again."
)


def should_retry_client(msg: str) -> bool:
    """
    Decides whether a failure looks like a YouTube client/PO-token rejection,
    where trying a different player client chain is worthwhile.

    Hard failures such as "video unavailable" or "removed by the uploader" are
    deliberately excluded so they surface immediately instead of being masked
    by three pointless retries.
    """
    low = str(msg).lower()
    fatal_markers = (
        "video unavailable",
        "has been removed",
        "removed by the uploader",
        "private video",
        "members-only",
        "this account has been terminated",
        "does not exist",
        "no video formats found",
    )
    if any(m in low for m in fatal_markers):
        return False

    return any(k in low for k in (
        "sign in to confirm", "not a bot", "login_required",
        "po_token", "po token",
        "confirm your age", "unplayable result",
        "playback on other websites", "requested format is not available",
        "http error 403", "403 forbidden",
    ))


def locate_output_file(output_dir: str, filename_hint: Optional[str] = None, files_before: Optional[set] = None) -> Optional[str]:
    """
    Robustly identifies the actual final output file generated on disk.

    Per-stream intermediates ("title.f251.webm") are never accepted as the
    result, otherwise a failed merge would be reported as a successful download.
    """
    if filename_hint and os.path.exists(filename_hint) and not is_stream_artifact(filename_hint):
        return filename_hint

    # Check newly created files in directory
    try:
        if files_before is not None:
            files_after = set(os.listdir(output_dir))
            new_files = files_after - files_before
            candidates = [
                os.path.join(output_dir, f) for f in new_files
                if not f.endswith(('.part', '.ytdl', '.tmp')) and not is_stream_artifact(f)
            ]
            if candidates:
                return max(candidates, key=os.path.getmtime)
    except Exception:
        pass

    # Look for matching base title filename
    if filename_hint:
        base = os.path.splitext(filename_hint)[0]
        base_name = os.path.basename(base)
        try:
            for f in os.listdir(output_dir):
                if f.startswith(base_name) and not f.endswith(('.part', '.ytdl', '.tmp')) \
                        and not is_stream_artifact(f):
                    full_p = os.path.join(output_dir, f)
                    if os.path.exists(full_p):
                        return full_p
        except Exception:
            pass

    return None


DEFAULT_OUTPUT_TEMPLATE = "%(title).120s [%(id)s].%(ext)s"


def format_selector_needs_merge(format_selector: str) -> bool:
    """
    True when the selector combines multiple streams ("bestvideo+bestaudio"),
    which yt-dlp can only satisfy by downloading parts and merging them.
    """
    return "+" in (format_selector or "")


def build_output_template(options: AdvancedOptions) -> str:
    """
    Resolves the yt-dlp output template for a job.

    Path separators and parent-directory references are stripped so a custom
    template cannot escape the chosen output directory.
    """
    if options.custom_filename:
        return f"{sanitize_filename(options.custom_filename, fallback='download')}.%(ext)s"

    template = (options.filename_template or "").strip()
    if not template:
        return DEFAULT_OUTPUT_TEMPLATE

    # Legacy default used "/" as the fallback when channel/playlist was unknown,
    # which silently created stray subdirectories. Fall back to "_" instead.
    template = template.replace("&{}/", "&{}_").replace("&{}/|", "&{}_|")

    # Reject directory traversal while allowing intentional subfolders.
    normalized = template.replace("\\", "/")
    if ".." in normalized:
        normalized = normalized.replace("..", "")
    # A template must not start with a separator, otherwise it escapes the
    # chosen output directory (os.path.join would drop the base path).
    normalized = normalized.lstrip("/")
    template = normalized

    if not template.endswith(".%(ext)s"):
        template = f"{template}.%(ext)s"

    return template


def download_media(
    url: str,
    media_type: str,  # "Video", "Audio", "Image"
    quality_key: str,  # "Best Available", "1080p", etc.
    output_dir: str,
    audio_codec: str = "MP3",
    audio_quality: str = "192 kbps",
    options: Optional[AdvancedOptions] = None,
    cookies_browser: Optional[str] = None,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    cancel_event: Optional[Any] = None,
) -> Tuple[bool, str]:
    """
    Executes a media download task and returns (success: bool, file_path_or_error: str).

    Video downloads always resolve to a single, fully merged, playable file.
    """
    options = options or AdvancedOptions()
    os.makedirs(output_dir, exist_ok=True)

    if media_type == "Image":
        return download_direct_image(url, output_dir, options, progress_callback, cancel_event)

    try:
        files_before = set(os.listdir(output_dir))
    except Exception:
        files_before = set()

    def internal_progress_hook(d):
        if cancel_event and getattr(cancel_event, "is_set", lambda: False)():
            raise Exception("Download cancelled by user.")
        if progress_callback:
            try:
                progress_callback(d)
            except Exception:
                pass

    format_selector = build_ytdlp_format_string(media_type, quality_key, options.raw_format_id)

    ffmpeg_location = get_ffmpeg_location()

    # Video merging and audio conversion are impossible without ffmpeg. Fail fast
    # with an actionable message instead of leaving orphan stream files behind.
    if media_type == "Video" and format_selector_needs_merge(format_selector) and not ffmpeg_location:
        return False, FFMPEG_MISSING_MESSAGE
    if media_type == "Audio" and audio_codec.lower() not in ("m4a", "copy") and not ffmpeg_location:
        return False, FFMPEG_MISSING_MESSAGE

    outtmpl_pattern = build_output_template(options)

    def build_opts(client_chain):
        ydl_opts: dict = {
            'outtmpl': os.path.join(output_dir, outtmpl_pattern),
            'nooverwrites': (options.overwrite_behavior == "no_overwrite"),
            'continuedl': True,
            'retries': 10,
            'fragment_retries': 10,
            'skip_unavailable_fragments': True,
            'noplaylist': True,
            'ignoreerrors': False,
            'no_warnings': False,
            'nocheckcertificate': True,
            'quiet': True,
            'format': format_selector,
            # Let yt-dlp sanitize illegal characters and cap path length itself,
            # otherwise Windows turns characters such as "|" into "?" .
            'windowsfilenames': True,
            'trim_file_name': 180,
            'extractor_args': {
                'youtube': {
                    'player_client': client_chain,
                }
            },
            'http_headers': {
                # Desktop UA: a mobile UA breaks YouTube channel/tab listings.
                'User-Agent': DESKTOP_USER_AGENT,
            },
            'progress_hooks': [internal_progress_hook],
        }

        if ffmpeg_location:
            ydl_opts['ffmpeg_location'] = ffmpeg_location

        # Without a JS runtime YouTube's signature challenge is never solved and
        # every download fails with "This video is not available".
        js_runtime = resolve_js_runtime()
        if js_runtime:
            ydl_opts['js_runtimes'] = js_runtime
            ydl_opts['remote_components'] = {'ejs:github'}

        if cookies_browser:
            ydl_opts['cookiesfrombrowser'] = (cookies_browser,)

        postprocessors = []

        if media_type == "Video":
            ydl_opts['merge_output_format'] = 'mp4'
            if options.embed_metadata:
                postprocessors.append({'key': 'FFmpegMetadata'})
                postprocessors.append({'key': 'FFmpegVideoRemuxerPP'})
            if options.embed_thumbnail:
                postprocessors.append({'key': 'EmbedThumbnail'})
                ydl_opts['writethumbnail'] = True
        elif media_type == "Audio":
            q_clean = "".join(filter(str.isdigit, audio_quality)) or "192"
            postprocessors.append({
                'key': 'FFmpegExtractAudio',
                'preferredcodec': audio_codec.lower(),
                'preferredquality': q_clean,
            })
            if options.embed_thumbnail:
                postprocessors.append({'key': 'EmbedThumbnail'})
                ydl_opts['writethumbnail'] = True
            if options.embed_metadata:
                postprocessors.append({'key': 'FFmpegMetadata'})

        # Subtitles handling
        if options.subtitles_enabled:
            ydl_opts['writesubtitles'] = True
            ydl_opts['subtitleslangs'] = [options.subtitle_language or 'en']
            if options.auto_subtitles:
                ydl_opts['writeautomaticsub'] = True
            if options.embed_subtitles and media_type == "Video":
                postprocessors.append({'key': 'FFmpegEmbedSubtitle'})

        if postprocessors:
            ydl_opts['postprocessors'] = postprocessors

        return ydl_opts

    last_error_msg = None

    for chain in YOUTUBE_CLIENT_CHAINS:
        filename_hint = None
        opts = build_opts(chain)
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if info:
                    entries = info.get('entries')
                    if entries:
                        first = next((e for e in entries if e), None)
                        filename_hint = ydl.prepare_filename(first) if first else None
                    else:
                        filename_hint = ydl.prepare_filename(info)
        except Exception as e:
            last_error_msg = str(e)
            # Remove per-stream intermediates left behind by the aborted attempt.
            cleanup_stream_artifacts(output_dir, keep={filename_hint} if filename_hint else None)

            if "ffmpeg" in last_error_msg.lower():
                return False, FFMPEG_MISSING_MESSAGE
            if should_retry_client(last_error_msg) and chain is not YOUTUBE_CLIENT_CHAINS[-1]:
                continue
            return False, last_error_msg

        located = locate_output_file(output_dir, filename_hint, files_before)
        if located and os.path.exists(located):
            # Best-effort sweep of any leftovers from partial merges.
            cleanup_stream_artifacts(output_dir, keep={located})
            return True, located

        # No final file: the streams were downloaded but never merged.
        cleanup_stream_artifacts(output_dir)
        last_error_msg = (
            "Downloaded streams were not merged into a single file. "
            + (FFMPEG_MISSING_MESSAGE if not has_ffmpeg() else "Please try 'Best Available' quality.")
        )
        break

    return False, last_error_msg or "File download completed but target output file could not be verified on disk."


def download_direct_image(
    url: str,
    output_dir: str,
    options: AdvancedOptions,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    cancel_event: Optional[Any] = None,
) -> Tuple[bool, str]:
    """Downloads a direct image file via HTTP GET."""
    try:
        r = requests.get(url, stream=True, timeout=30)
        if r.status_code != 200:
            return False, f"HTTP Error {r.status_code}"
        
        ct = r.headers.get('content-type', '')
        ext = ct.split('/')[-1].split(';')[0] or 'jpg'
        if len(ext) > 5 or not ext.isalnum():
            ext = 'jpg'

        if options.custom_filename:
            filename = f"{sanitize_filename(options.custom_filename)}.{ext}"
        else:
            filename = f"image_{int(time.time())}.{ext}"

        full_path = os.path.join(output_dir, filename)
        total_len = int(r.headers.get('content-length') or 0)
        downloaded = 0

        with open(full_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                if cancel_event and getattr(cancel_event, "is_set", lambda: False)():
                    f.close()
                    if os.path.exists(full_path):
                        os.remove(full_path)
                    return False, "Image download cancelled."

                if not chunk:
                    continue
                f.write(chunk)
                downloaded += len(chunk)

                if progress_callback and total_len:
                    percent_str = f"{(downloaded / float(total_len)) * 100:.1f}%"
                    progress_callback({
                        'status': 'downloading',
                        'downloaded_bytes': downloaded,
                        'total_bytes': total_len,
                        '_percent_str': percent_str,
                    })

        if progress_callback:
            progress_callback({'status': 'finished'})

        return True, full_path
    except Exception as e:
        return False, str(e)
