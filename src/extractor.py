"""
URL Analysis and Metadata Extractor Service for OmniStream.
Extracts media titles, thumbnails, available resolutions, playlists, and subtitles using yt-dlp.
"""

import re
from urllib.parse import urlparse
import yt_dlp
from typing import Dict, Any, List, Optional
from .validators import is_valid_url, detect_platform, is_instagram_collection_url, classify_instagram_url, InstagramURLType
from .formats import filter_available_resolutions
from .media import MediaMetadata, PlaylistItem
from .errors import InvalidURLError, ExtractorError
from .system import resolve_js_runtime
from .cookies import apply_cookie_opts, COOKIES_TXT_HELP
from .instagram_scraper import InstagramReelsScraper, extract_instagram_reels_from_profile


# Player client fallback chains for YouTube. None = let yt-dlp choose its own
# clients, which is the most reliable option when YouTube throttles the others.
YOUTUBE_CLIENT_CHAINS = [
    ['visionos', 'web_embedded'],
    ['android_vr', 'tv', 'web_safari'],
    ['web', 'android', 'mweb'],
    None,
]

YOUTUBE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")

# YouTube URL shapes that point at a collection rather than a single video.
# Note "/watch" is deliberately absent: a plain watch?v=... link is one video.
CHANNEL_URL_MARKERS = (
    "/channel/", "/c/", "/user/", "/@", "/shorts", "/playlist",
)

# Instagram URL patterns that point at a collection (profile or reels listing)
INSTAGRAM_COLLECTION_MARKERS = (
    "/reels/",
)

# Dailymotion collection markers
DAILYMOTION_COLLECTION_MARKERS = (
    "/user/", "/playlist/", "/channel/",
)

# Twitch collection markers
TWITCH_COLLECTION_MARKERS = (
    "/videos", "/clips", "/collections",
)

# LinkedIn collection markers
LINKEDIN_COLLECTION_MARKERS = (
    "/posts/", "/video/",
)

# Snapchat collection markers
SNAPCHAT_COLLECTION_MARKERS = (
    "/spotlight/", "/discover/",
)

# Facebook collection markers
FACEBOOK_COLLECTION_MARKERS = (
    "/videos/", "/reels/", "/watch/", "sk=reels_tab", "sk=reels", "sk=videos_tab", "sk=videos", "/videos", "/reels",
)

# SoundCloud collection markers
SOUNDCLOUD_COLLECTION_MARKERS = (
    "/sets/", "/tracks/", "/playlists/",
)

# Vimeo collection markers
VIMEO_COLLECTION_MARKERS = (
    "/channels/", "/groups/", "/albums/", "/showcases/",
)

# Desktop User Agent - exported for use by other modules
DESKTOP_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


def is_youtube_id(value: Any) -> bool:
    return bool(value) and isinstance(value, str) and bool(YOUTUBE_ID_RE.match(value))


def normalize_entry_url(entry: Dict[str, Any], parent_url: str) -> str:
    """
    Resolves a playlist entry to a real, re-extractable media URL.

    Flat ("extract_flat") extraction returns a bare video id in `entry['url']`,
    which yt-dlp cannot download. Left unfixed, batch downloads of a channel
    silently fail on every item.
    """
    for key in ("webpage_url", "original_url"):
        candidate = entry.get(key)
        if candidate and str(candidate).startswith(("http://", "https://")):
            return str(candidate)

    if is_youtube_id(entry.get("id")):
        return f"https://www.youtube.com/watch?v={entry['id']}"

    candidate = entry.get("url")
    if candidate and str(candidate).startswith(("http://", "https://")):
        return str(candidate)

    return parent_url


def _youtube_handle(url: str) -> Optional[str]:
    """Extracts an @handle or channel id from a YouTube URL, when present."""
    path = urlparse(url).path or ""

    match = re.search(r"/@([^/?#]+)", path)
    if match:
        return match.group(1)

    match = re.search(r"/(?:channel|c|user)/([^/?#]+)", path)
    if match:
        return match.group(1)

    return None


def looks_like_collection(url: str, platform: str) -> bool:
    """Heuristic: does this URL likely resolve to many videos (channel/playlist/shorts)?"""
    if platform == "YouTube":
        low = url.lower()
        if "list=" in low:
            return True
        return any(m in low for m in CHANNEL_URL_MARKERS)
    
    if platform.startswith("Instagram"):
        return is_instagram_collection_url(url)
    
    low = url.lower()
    
    if platform == "Dailymotion":
        return any(m in low for m in DAILYMOTION_COLLECTION_MARKERS)
    
    if platform == "Twitch":
        return any(m in low for m in TWITCH_COLLECTION_MARKERS)
    
    if platform == "LinkedIn":
        return any(m in low for m in LINKEDIN_COLLECTION_MARKERS)
    
    if platform == "Snapchat":
        return any(m in low for m in SNAPCHAT_COLLECTION_MARKERS)
    
    if platform == "Facebook":
        return any(m in low for m in FACEBOOK_COLLECTION_MARKERS)
    
    if platform == "SoundCloud":
        return any(m in low for m in SOUNDCLOUD_COLLECTION_MARKERS)
    
    if platform == "Vimeo":
        return any(m in low for m in VIMEO_COLLECTION_MARKERS)
    
    if platform == "Pinterest":
        # Pinterest boards and user profiles
        return "/pin/" in low or "/board/" in low or "/user/" in low
    
    if platform == "TikTok":
        # TikTok user profiles and hashtag pages
        return "/@" in low and "/video/" not in low
    
    if platform == "Twitter / X":
        # Twitter user timelines and lists
        return "/status/" not in low and ("/lists/" in low or "/i/lists/" in low or re.match(r"https?://(?:www\.)?(?:twitter\.com|x\.com)/[^/?#]+/?$", low))
    
    return False


# Tabs that can hold downloadable uploads on a YouTube channel.
CHANNEL_TABS = ("videos", "shorts", "streams")


def channel_tab_urls(url: str) -> List[str]:
    """
    Expands a YouTube channel URL into one URL per content tab.

    A bare handle ("/@name") only returns the default tab, which silently hides
    Shorts. To satisfy "download everything on this channel", every tab is
    enumerated so videos + shorts are all picked up.
    """
    path = urlparse(url).path or ""

    if not re.search(r"/@[^/?#]+$", path):
        # Already points at a specific tab, playlist or single video.
        return []

    base = url.rstrip("/")
    return [f"{base}/{tab}" for tab in CHANNEL_TABS]


def _build_ydl_opts(
    url: str,
    platform: str,
    client_chain: Optional[List[str]],
    playlist_limit: Optional[int],
    cookies_browser: Optional[str],
    playlist_start: Optional[int] = None,
    cookies_file: Optional[str] = None,
) -> Dict[str, Any]:
    """Builds yt-dlp options for a flat metadata probe."""
    ydl_opts: Dict[str, Any] = {
        'extract_flat': 'in_playlist',
        'skip_download': True,
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        # Kept False so the real extractor error (rather than a generic
        # "empty metadata") is surfaced to the user.
        'ignoreerrors': False,
        # Must be a DESKTOP user agent. A mobile UA makes YouTube serve the
        # mweb channel page, which yt-dlp's youtube:tab extractor cannot parse,
        # so every channel/tab listing dies with "Unable to recognize tab page".
        'http_headers': {
            'User-Agent': DESKTOP_USER_AGENT,
        },
        # Listing a tab is a light request; cap it so one slow tab cannot hang
        # the UI analysis thread.
        'socket_timeout': 30,
    }

    # YouTube requires a JS runtime to solve its signature challenge. Without
    # one, listing *and* extraction fail with "This video is not available".
    if platform == "YouTube":
        js_runtime = resolve_js_runtime()
        if js_runtime:
            ydl_opts['js_runtimes'] = js_runtime
            ydl_opts['remote_components'] = {'ejs:github'}

        youtube_args = ydl_opts.setdefault('extractor_args', {}).setdefault('youtube', {})

        # None means "let yt-dlp pick its own clients". YouTube intermittently
        # rejects the forced chains, so this is the last-resort fallback.
        if client_chain:
            youtube_args['player_client'] = client_chain

        # NOTE: the "tab" extractor arg is deliberately NOT set. Forcing it makes
        # yt-dlp ask for a tab page that YouTube then refuses to render, which
        # fails with "Unable to recognize tab page". URLs that already end in
        # /videos, /shorts or /streams need no hint, and a bare handle already
        # defaults to the Videos tab.

    if playlist_limit and playlist_limit > 0:
        ydl_opts['playlistend'] = playlist_limit

    if playlist_start and playlist_start > 1:
        ydl_opts['playliststart'] = playlist_start

    apply_cookie_opts(ydl_opts, cookies_browser, cookies_file)

    return ydl_opts


# Tabs that legitimately do not exist on a channel. Not an error.
_MISSING_TAB_RE = re.compile(
    r"does not have a (videos|shorts|streams|live|playlists) tab|tab does not exist",
    re.IGNORECASE,
)


def _entry_key(url: str) -> str:
    """Stable dedupe key for a playlist entry URL."""
    query = urlparse(url).query or ""
    match = re.search(r"(?:^|&)v=([A-Za-z0-9_-]{11})", query)
    if match:
        return match.group(1)

    # /shorts/<id> and /live/<id> carry the id in the path instead, and must
    # still collide with the /watch?v=<id> form of the same video.
    path = urlparse(url).path or ""
    match = re.search(r"/(?:shorts|live|v|embed)/([A-Za-z0-9_-]{11})(?:$|[/?#])", path)
    if match:
        return match.group(1)

    return url


def _extract_channel_tabs(
    url: str,
    tab_urls: List[str],
    playlist_limit: Optional[int],
    cookies_browser: Optional[str],
    shorts_only: bool = False,
    cookies_file: Optional[str] = None,
) -> Optional[MediaMetadata]:
    """
    Extracts every content tab of a channel and merges them into one result.

    Tabs that the channel does not have (e.g. no streams) are skipped. Returns
    None only when no tab at all could be listed, so the caller can fall back to
    a single-URL extraction.
    """
    # Filter tabs based on shorts_only flag
    if shorts_only:
        tab_urls = [u for u in tab_urls if u.endswith("/shorts")]
        if not tab_urls:
            return None
    
    last_err = None

    for client_chain in YOUTUBE_CLIENT_CHAINS:
        collected: Dict[str, PlaylistItem] = {}
        base: Optional[MediaMetadata] = None
        tab_errors: List[str] = []

        for tab_url in tab_urls:
            ydl_opts = _build_ydl_opts(
                tab_url, "YouTube", client_chain, playlist_limit, cookies_browser,
                playlist_start=None, cookies_file=cookies_file,
            )
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(tab_url, download=False)
                if not info:
                    tab_errors.append(f"{tab_url}: empty metadata")
                    continue
            except Exception as e:
                last_err = e
                if _MISSING_TAB_RE.search(str(e)):
                    continue
                tab_errors.append(f"{tab_url}: {e}")
                continue

            if base is None:
                base = MediaMetadata(
                    url=url,
                    title=info.get("title") or _youtube_handle(url) or "Channel",
                    thumbnail=info.get("thumbnail"),
                    uploader=info.get("uploader") or info.get("channel"),
                    platform="YouTube",
                    is_playlist=True,
                    playlist_title=info.get("title"),
                )

            for idx, entry in enumerate(info.get("entries") or [], 1):
                if not isinstance(entry, dict):
                    continue
                item_url = normalize_entry_url(entry, tab_url)
                key = _entry_key(item_url)
                if key in collected:
                    continue
                collected[key] = PlaylistItem(
                    url=item_url,
                    title=entry.get("title") or f"Item {idx}",
                    index=len(collected) + 1,
                    duration=entry.get("duration"),
                    thumbnail=entry.get("thumbnail"),
                    selected=True,
                )

        if base is None:
            continue

        items = list(collected.values())
        if not items:
            # Every tab listed successfully but held nothing usable.
            base.playlist_items = []
            base.playlist_count = 0
            return base

        base.playlist_items = items
        base.playlist_count = len(items)
        base.playlist_title = f"{base.playlist_title or base.title} (all uploads)"
        return base

    if last_err is not None:
        # Every chain failed for a real reason; let the single-URL path retry.
        return None
    return None


def _build_instagram_ydl_opts(
    url: str,
    playlist_limit: Optional[int],
    cookies_browser: Optional[str],
    cookies_file: Optional[str] = None,
) -> Dict[str, Any]:
    """Builds yt-dlp options for Instagram metadata extraction."""
    ydl_opts: Dict[str, Any] = {
        'extract_flat': 'in_playlist',
        'skip_download': True,
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'ignoreerrors': False,
        'http_headers': {
            'User-Agent': DESKTOP_USER_AGENT,
        },
        'socket_timeout': 30,
    }

    if playlist_limit and playlist_limit > 0:
        ydl_opts['playlistend'] = playlist_limit

    apply_cookie_opts(ydl_opts, cookies_browser, cookies_file)

    return ydl_opts


def _extract_instagram_reels(
    url: str,
    playlist_limit: Optional[int],
    cookies_browser: Optional[str],
    reels_only: bool = False,
    cookies_file: Optional[str] = None,
) -> Optional[MediaMetadata]:
    """
    Extracts Reels from an Instagram profile or Reels listing URL.
    
    Uses yt-dlp's instagram extractor which supports profile URLs.
    Converts /reels/ listing URLs to profile URLs for compatibility.
    Returns MediaMetadata with playlist_items populated for each Reel.
    
    Note: Instagram often requires authentication. Provide cookies_browser
    (e.g., "chrome", "firefox", "edge") for private or restricted profiles.
    """
    # If reels_only is True but URL is not a reels listing, convert it
    if reels_only and "/reels/" not in url:
        # Convert profile URL to reels listing URL
        import re
        match = re.search(r"instagram\.com/([^/?#]+)/?$", url)
        if match:
            username = match.group(1)
            url = f"https://www.instagram.com/{username}/reels/"
    
    # Convert /reels/ listing URL to profile URL for yt-dlp compatibility
    # yt-dlp's instagram extractor supports profile URLs but not /reels/ listings
    extraction_url = url
    if "/reels/" in url:
        # Extract username from /username/reels/ and convert to profile URL
        import re
        match = re.search(r"instagram\.com/([^/?#]+)/reels/?", url)
        if match:
            username = match.group(1)
            extraction_url = f"https://www.instagram.com/{username}/"
    
    ydl_opts = _build_instagram_ydl_opts(
        extraction_url, playlist_limit, cookies_browser, cookies_file
    )
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(extraction_url, download=False)
    except Exception as e:
        # Provide actionable error message for common Instagram issues
        err_str = str(e).lower()
        if "unable to extract data" in err_str or "unsupported url" in err_str:
            if not cookies_browser and not cookies_file:
                raise ExtractorError(
                    "Instagram requires authentication to access this profile. "
                    "Set a cookies.txt file in Settings → Cookies File (export it with a "
                    "browser extension while logged in), or set browser cookies and retry.",
                    details=str(e)
                )
            else:
                raise ExtractorError(
                    "Instagram blocked this request even with cookies. The profile may be private, "
                    "rate-limited, or require login. Try using individual Reel URLs instead.",
                    details=str(e)
                )
        elif "login required" in err_str or "please log in" in err_str or "empty media response" in err_str:
            raise ExtractorError(
                "This Instagram content requires login. Set browser cookies in Settings "
                "(close browser completely first) and retry.",
                details=str(e)
            )
        elif "rate limit" in err_str or "too many requests" in err_str or "429" in err_str:
            raise ExtractorError(
                "Instagram rate limit reached. Wait a few minutes and try again.",
                details=str(e)
            )
        elif "private" in err_str:
            raise ExtractorError(
                "This Instagram account is private. You need to follow the account "
                "and use browser cookies to access its content.",
                details=str(e)
            )
        else:
            raise ExtractorError(f"Failed to extract Instagram Reels: {e}", details=str(e))
    
    if not info:
        return None
    
    # Instagram profile returns entries with individual reel info
    entries = info.get("entries") or []
    if not entries:
        # Might be a single reel URL passed as collection - treat as single item
        return None
    
    title = info.get("title") or info.get("id") or "Instagram Reels"
    thumbnail = info.get("thumbnail")
    uploader = info.get("uploader") or info.get("channel") or info.get("uploader_id")
    
    base = MediaMetadata(
        url=url,  # Keep original URL for reference
        title=title,
        thumbnail=thumbnail,
        uploader=uploader,
        platform="Instagram",
        is_playlist=True,
        playlist_title=title,
    )
    
    playlist_items = []
    seen_urls = set()
    
    for idx, entry in enumerate(entries, 1):
        if not entry or not isinstance(entry, dict):
            continue
        
        # Get the reel URL - Instagram entries should have webpage_url or url
        item_url = entry.get("webpage_url") or entry.get("url") or entry.get("original_url")
        if not item_url:
            # Try to construct from id
            reel_id = entry.get("id")
            if reel_id:
                item_url = f"https://www.instagram.com/reel/{reel_id}/"
        
        if not item_url or not isinstance(item_url, str) or not item_url.startswith("http"):
            continue
        
        # Deduplicate by URL
        if item_url in seen_urls:
            continue
        seen_urls.add(item_url)
        
        item_title = entry.get("title") or f"Reel {idx}"
        duration = entry.get("duration")
        item_thumb = entry.get("thumbnail")
        
        playlist_items.append(PlaylistItem(
            url=item_url,
            title=item_title,
            index=len(playlist_items) + 1,
            duration=duration,
            thumbnail=item_thumb,
            selected=True,
        ))
    
    if not playlist_items:
        return None
    
    base.playlist_items = playlist_items
    base.playlist_count = len(playlist_items)
    base.playlist_title = f"{base.playlist_title} ({len(playlist_items)} Reels)"
    
    return base


def extract_media_info(
    url: str,
    playlist_limit: Optional[int] = None,
    shorts_only: bool = False,
    reels_only: bool = False,
) -> MediaMetadata:
    """
    Analyzes a media URL and returns a structured MediaMetadata object.
    Never crashes on missing or partial metadata fields.

    Channel, Shorts-tab and playlist URLs are returned with every entry
    populated in `playlist_items` so the caller can enqueue a batch download.
    """
    if not is_valid_url(url):
        raise InvalidURLError(f"Invalid URL syntax: '{url}'")

    url = url.strip()
    platform = detect_platform(url)

    # Check for direct image URLs
    if platform == "Direct Image":
        return MediaMetadata(
            url=url,
            title="Direct Image Link",
            thumbnail=url,
            platform="Direct Image",
            available_resolutions=["Original Quality"],
        )

    is_collection = looks_like_collection(url, platform)

    # Handle Instagram profile/reels listing URLs
    if platform.startswith("Instagram") and is_collection:
        # First try the yt-dlp-based extractor (may raise ExtractorError on auth failure)
        merged = None
        try:
            merged = _extract_instagram_reels(
                url, playlist_limit, reels_only
            )
        except Exception:
            # yt-dlp's Instagram extractor often fails (auth required, broken extractor).
            # Fall through to the InstagramReelsScraper fallback below.
            pass

        # If the yt-dlp extractor succeeded, return it immediately.
        if merged is not None:
            return merged

        # Fallback: use InstagramReelsScraper when yt-dlp's extractor returns None
        # or raises an exception. The scraper uses HTML parsing with cookies
        # (cookies.txt preferred, browser best-effort) and can succeed even when
        # yt-dlp's extractor fails (auth issues, broken extractor).
        try:
            from src.instagram_scraper import InstagramReelsScraper
            scraper = InstagramReelsScraper()
            # Use playlist_limit if configured, otherwise discover all accessible Reels
            # (no arbitrary 50-item cap). When a limit is set, mark results accordingly.
            max_reels = playlist_limit
            reel_urls = scraper.extract_reel_urls(url, max_reels=max_reels)
            if reel_urls:
                # Build MediaMetadata from the scraper results
                title = url.split("/")[-2] if "/reels/" in url else "Instagram Profile"
                thumbnail = None
                uploader = None

                base = MediaMetadata(
                    url=url,
                    title=title,
                    thumbnail=thumbnail,
                    uploader=uploader,
                    platform="Instagram",
                    is_playlist=True,
                    playlist_title="Instagram Reels",
                )

                playlist_items = []
                seen_urls = set()
                truncated = False
                for idx, reel_url in enumerate(reel_urls, 1):
                    if reel_url in seen_urls:
                        continue
                    seen_urls.add(reel_url)
                    # Check if we've hit a user-configured limit
                    if max_reels is not None and idx > max_reels:
                        truncated = True
                        continue
                    playlist_items.append(PlaylistItem(
                        url=reel_url,
                        title=reel_url.split("/")[-1] or "Reel " + str(idx),
                        index=idx,
                        selected=True,
                    ))

                if playlist_items:
                    base.playlist_items = playlist_items
                    base.playlist_count = len(playlist_items)
                    # Indicate if results were truncated by a user limit
                    if truncated:
                        base.playlist_title = "Instagram Reels ({} discovered of ~{}+)".format(
                            len(playlist_items), max_reels
                        )
                    else:
                        base.playlist_title = "Instagram Reels ({})".format(
                            len(playlist_items)
                        )
                    return base
        except Exception:
            # If scraper fails for any reason (no cookies, extraction error),
            # fall through to single-item extraction rather than crashing.
            pass

        # If we're dealing with an Instagram collection and haven't found any Reels,
        # return empty playlist metadata instead of falling through to generic
        # extraction (which would treat the profile URL as a single video).
        if platform.startswith("Instagram") and is_collection:
            from .media import MediaMetadata
            return MediaMetadata(
                url=url,
                title=url.split("/")[-2] if "/reels/" in url else "Instagram Profile",
                thumbnail=None,
                uploader=None,
                platform="Instagram",
                is_playlist=True,
                playlist_title="Instagram Reels",
                playlist_items=[],
                playlist_count=0,
            )
    # A bare channel handle only exposes its default tab, which hides Shorts.
    # Enumerate every tab so "download everything on this channel" really does.
    tab_urls = channel_tab_urls(url) if platform == "YouTube" else []
    if tab_urls:
        merged = _extract_channel_tabs(
            url, tab_urls, playlist_limit, cookies_browser, shorts_only, cookies_file
        )
        if merged is not None:
            return merged

    last_err = None
    
    # For non-YouTube platforms, don't iterate client chains - just use default extraction
    if platform == "YouTube":
        client_chains = YOUTUBE_CLIENT_CHAINS
    else:
        client_chains = [None]  # Single attempt with no forced client chain

    for client_chain in client_chains:
        ydl_opts = _build_ydl_opts(
            url, platform, client_chain, playlist_limit, cookies_browser,
            playlist_start=None, cookies_file=cookies_file,
        )

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if not info:
                    raise ExtractorError("yt-dlp returned empty metadata for this link.")

                title = info.get("title") or info.get("id") or "Media Download"
                thumbnail = info.get("thumbnail") or (info.get("thumbnails")[-1].get("url") if info.get("thumbnails") else None)
                uploader = info.get("uploader") or info.get("channel") or info.get("uploader_id")
                duration = info.get("duration")
                upload_date = info.get("upload_date")
                view_count = info.get("view_count")

                # Playlist handling
                is_playlist = "entries" in info or info.get("_type") == "playlist"
                playlist_title = info.get("title") if is_playlist else None
                playlist_items = []
                playlist_count = 0

                if is_playlist:
                    raw_entries = list(info.get("entries") or [])
                    playlist_count = len(raw_entries)
                    for idx, entry in enumerate(raw_entries, 1):
                        if not entry:
                            continue
                        if not isinstance(entry, dict):
                            continue
                        e_url = normalize_entry_url(entry, url)
                        e_title = entry.get("title") or f"Item {idx}"
                        e_dur = entry.get("duration")
                        e_thumb = entry.get("thumbnail")
                        playlist_items.append(PlaylistItem(
                            url=e_url,
                            title=e_title,
                            index=idx,
                            duration=e_dur,
                            thumbnail=e_thumb,
                            selected=True,
                        ))

                # Formats handling
                raw_formats = info.get("formats") or []
                available_resolutions = filter_available_resolutions(raw_formats)

                # Subtitles handling
                subtitles = info.get("subtitles") or {}
                auto_subtitles = info.get("automatic_captions") or {}
                combined_subs = {}
                for k, v in subtitles.items():
                    combined_subs[k] = {"type": "manual", "formats": v}
                for k, v in auto_subtitles.items():
                    if k not in combined_subs:
                        combined_subs[k] = {"type": "auto", "formats": v}

                return MediaMetadata(
                    url=url,
                    title=title,
                    thumbnail=thumbnail,
                    uploader=uploader,
                    duration=duration,
                    platform=platform,
                    upload_date=upload_date,
                    view_count=view_count,
                    available_formats=raw_formats,
                    available_resolutions=available_resolutions,
                    available_subtitles=combined_subs,
                    is_playlist=is_playlist,
                    playlist_title=playlist_title,
                    playlist_count=playlist_count,
                    playlist_items=playlist_items,
                    raw_info=info,
                )
        except Exception as e:
            last_err = e

    raise ExtractorError(_friendly_error(last_err, url), details=str(last_err))


def _friendly_error(err: Any, url: str) -> str:
    """Turns known yt-dlp failures into an actionable message instead of a raw dump."""
    raw = str(err or "").lower()

    if "[youtube:tab]" in raw and "404" in raw:
        return (
            "YouTube refused to list this channel/Shorts/playlist. Its browse API is "
            "rejecting this network. Individual video links still download normally - "
            "open the channel, copy a Shorts link, or set browser cookies in Settings "
            "(close the browser first) and try again."
        )

    if "could not copy" in raw and "cookie" in raw:
        return (
            "Could not read browser cookies because your browser is currently running and locking its cookie database. "
            "Please close your browser completely (check Task Manager or system tray to ensure no background processes remain), then try again. "
            + COOKIES_TXT_HELP
        )

    if (
        "facebook.com/login" in raw
        or (
            "facebook" in raw
            and (
                "login" in raw
                or "unsupported url" in raw
                # yt-dlp's Facebook extractor fails to parse most Reels/watch
                # pages without an authenticated session.
                or "cannot parse data" in raw
            )
        )
    ):
        return (
            "Facebook requires an active login session to view this video, profile, or Reels listing. "
            "Either Facebook redirected to its login page, or its page format could not be parsed "
            "without being signed in. Set a cookies.txt file in Settings (export it with a browser "
            "extension while logged into Facebook) and try again. " + COOKIES_TXT_HELP
        )

    # TikTok blocks profile/hashtag listings without a logged-in session.
    if "tiktok" in raw and (
        "secondary user id" in raw or "ip address is blocked" in raw or "login" in raw
    ):
        return (
            "TikTok blocked this profile or video without a logged-in session. "
            "Set a cookies.txt file in Settings (export it with a browser extension while "
            "logged into TikTok) and try again. " + COOKIES_TXT_HELP
        )

    if "not a bot" in raw or "confirm you" in raw and "bot" in raw:
        return (
            "YouTube bot check triggered. Your IP may be flagged by YouTube's anti-automation. "
            "Set browser cookies in Settings (close your browser first) to bypass this, "
            "or try again from a different network."
        )

    if "unsupported url" in raw or "no suitable extractor" in raw:
        return f"No downloader is available for '{url}'."

    if "private video" in raw:
        return "This video is private. Sign-in cookies are required to access it."

    if "video unavailable" in raw:
        return "This video is unavailable or was removed by the uploader."

    # Instagram-specific errors
    if "instagram" in raw:
        if "login required" in raw or "please log in" in raw or "sign in to view" in raw:
            return (
                "This Instagram content requires login. Set a cookies.txt file in Settings "
                "(export it with a browser extension while logged into Instagram) and retry. "
                + COOKIES_TXT_HELP
            )
        if "rate limit" in raw or "too many requests" in raw or "429" in raw:
            return "Instagram rate limit reached. Wait a few minutes and try again."
        if "not found" in raw or "404" in raw:
            return "Instagram content not found. It may have been deleted or the URL is incorrect."

    # Checked outside the "instagram" guard because yt-dlp's private-account
    # message often omits the site name entirely.
    if "this account is private" in raw or "private account" in raw:
        return (
            "This account is private. You need to follow the account, then use a "
            "logged-in cookies.txt file in Settings to access its posts. " + COOKIES_TXT_HELP
        )

    return f"Extraction failed: {str(err) or 'yt-dlp returned empty metadata for this link.'}"
