# OmniStream 3.0 Premium - Implementation Plan

## Current State Analysis (as of commit a9c46cb)

### ✅ Already Implemented
- **Core Architecture**: Shared services in `src/` used by both Streamlit (`app.py`) and CustomTkinter (`app_gui.py`)
- **Platform Detection**: YouTube, TikTok, Instagram (Profile/Reels/Reel/Post/TV), Twitter/X, Facebook, Pinterest, Vimeo, Twitch, SoundCloud, Reddit, Direct Image
- **Instagram Reels Discovery**: Profile and `/reels/` listing URLs convert to profile URL for yt-dlp compatibility
- **YouTube Channel/Playlist/Shorts Discovery**: Multi-tab enumeration (videos, shorts, streams)
- **Batch Download Queue**: Thread-safe queue with per-item progress, retry, cancel
- **FFmpeg Detection**: Via `imageio-ffmpeg` bundle + system PATH fallback
- **Cookie Authentication**: Browser cookie integration for YouTube/Instagram
- **Error Handling**: Platform-specific friendly error messages
- **Desktop UI**: CustomTkinter with dark theme, navigation, queue, history, settings
- **Streamlit UI**: Web interface with similar features
- **Tests**: 123 passing tests (102 core + 21 GUI logic)

### 🔴 Critical Gaps (Per Master Prompt)

| Feature | Status | Priority |
|---------|--------|----------|
| Shorts/Reels-only filter modes | ❌ Not implemented | HIGH |
| Additional platform detection (Dailymotion, Twitch VODs, LinkedIn, Snapchat, etc.) | ⚠️ Basic detection only | HIGH |
| Platform capability registry | ❌ Not implemented | HIGH |
| Diagnostics screen | ⚠️ Partial (Streamlit sidebar only) | HIGH |
| Incremental loading/pagination | ❌ Not implemented | MEDIUM |
| Search/filter in discovered items (Desktop) | ❌ Not implemented | MEDIUM |
| Queue persistence across restarts | ❌ Not implemented | MEDIUM |
| Settings sync between desktop/Streamlit | ❌ Different config files | MEDIUM |
| Desktop shortcut verification | ❌ Not tested | HIGH |
| Download history file verification | ⚠️ Partial | MEDIUM |

---

## Phase 1: Shorts/Reels-Only Modes (HIGH)

### YouTube Shorts-Only
- Add `ShortsOnly` filter option in UI
- When analyzing YouTube channel URL with Shorts-only mode:
  - Only query `/shorts` tab (skip `/videos`, `/streams`)
  - Filter results by duration (< 60s) as fallback

### Instagram Reels-Only
- Already works for `/reels/` URLs
- Add explicit Reels-only toggle for profile URLs

### Implementation:
1. Add filter option to `AdvancedOptions` / download configuration
2. Modify `_analyze_worker_inner` (desktop) and `extract_media_info` (shared) to respect filter
3. Update both UIs with filter controls

---

## Phase 2: Additional Platform Support (HIGH)

### Platforms to Add Explicit Detection For:
| Platform | Extractor Names | URL Patterns |
|----------|----------------|--------------|
| Dailymotion | `dailymotion`, `dailymotion:playlist`, `dailymotion:user` | dailymotion.com/video/, /playlist/, /user/ |
| Twitch VODs/Clips | `twitch:videos`, `twitch:clips`, `twitch:collection` | twitch.tv/videos/, /clip/, /collections/ |
| LinkedIn | `linkedin`, `linkedin:learning` | linkedin.com/posts/, /video/, /learning/ |
| Snapchat | `snapchat:spotlight`, `snapchat:user` | snapchat.com/spotlight/, /add/ |
| SoundCloud | `soundcloud`, `soundcloud:playlist`, `soundcloud:user` | soundcloud.com/, /sets/, /user/ |
| Generic Web | `generic` | Any URL with direct media |

### Implementation:
1. Extend `validators.py` with new platform detection patterns
2. Add platform-specific collection detection in `extractor.py`
3. Update `looks_like_collection()` for each platform
4. Add platform-specific extraction logic where needed

---

## Phase 3: Platform Capability Registry & Diagnostics (HIGH)

### Capability Registry:
Create `src/platforms.py` with:
```python
PLATFORM_CAPABILITIES = {
    "YouTube": {
        "single_video": True,
        "channel": True,
        "playlist": True,
        "shorts": True,
        "livestreams": True,
        "auth_required": "optional",
        "quality_options": ["4K", "1440p", "1080p", "720p", "480p", "360p"],
        "audio_only": True,
    },
    "Instagram": {
        "single_reel": True,
        "profile": True,
        "reels_listing": True,
        "auth_required": "required_for_private",
        "quality_options": ["Best Available"],
        "audio_only": False,
    },
    # ... etc
}
```

### Diagnostics Screen:
- Add "Platform Support" page to both UIs
- Show capability matrix
- Test extraction for each platform
- Report yt-dlp version and extractor status

---

## Phase 4: Incremental Loading & Search/Filter (MEDIUM)

### Incremental Loading:
- Add `playlist_limit` config (already exists)
- Add "Load More" button in discovery UI
- Support pagination via yt-dlp `playliststart`/`playlistend`

### Search/Filter in Desktop App:
- Add search box above discovered items list
- Filter by title, duration, date
- Sort by title, date, duration, platform

---

## Phase 5: Queue Persistence & Settings Sync (MEDIUM)

### Queue Persistence:
- Save queue to JSON on disk
- Restore on startup
- Track completed/failed items separately

### Settings Sync:
- Use shared config location for both apps
- Or add config import/export

---

## Phase 6: Desktop Shortcut Verification (HIGH)

### Verification Steps:
1. Run `create_streamlit_shortcut.ps1`
2. Check shortcut target exists
3. Verify working directory
4. Test launch from shortcut
5. Fix any issues

---

## Phase 7: Tests & Verification (HIGH)

### Test Coverage Gaps:
- Shorts/Reels filter modes
- New platform detection
- Incremental loading
- Queue persistence
- Settings sync
- Desktop shortcut launch

---

## Implementation Order

1. **Phase 1**: Shorts/Reels-only modes (immediate user value)
2. **Phase 2**: Additional platform detection (broader support)
3. **Phase 3**: Capability registry & diagnostics (architectural)
3. **Phase 4**: Incremental loading & search/filter (UX)
4. **Phase 5**: Queue persistence & settings sync (reliability)
5. **Phase 6**: Shortcut verification (deployment)
6. **Phase 7**: Comprehensive tests & verification (quality)

---

## Technical Notes

### Shared Services Pattern (Keep):
- `src/extractor.py` - URL analysis, metadata extraction
- `src/downloader.py` - Core download logic
- `src/queue.py` - Queue management
- `src/system.py` - System detection (FFmpeg, JS runtime)
- `src/validators.py` - URL validation, platform detection
- `src/formats.py` - Format selection
- `src/media.py` - Data models
- `src/filesystem.py` - File operations
- `src/history.py` - History persistence
- `src/settings.py` - Settings persistence
- `src/errors.py` - Error handling

### Files to Modify:
- `src/validators.py` - Add platform detection
- `src/extractor.py` - Add platform extraction logic
- `src/platforms.py` - NEW: Capability registry
- `src/downloader.py` - Add filter support
- `app_gui.py` - Desktop UI enhancements
- `app.py` - Streamlit UI enhancements
- `create_shortcut.ps1` - Fix if needed
- Tests - Add new test cases