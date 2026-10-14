"""
Data structures and models for OmniStream metadata, jobs, playlists, and formats.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Any, Optional
import time
import uuid


class JobStatus(str, Enum):
    QUEUED = "QUEUED"
    ANALYZING = "ANALYZING"
    DOWNLOADING = "DOWNLOADING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass
class PlaylistItem:
    url: str
    title: str
    index: int
    duration: Optional[int] = None
    thumbnail: Optional[str] = None
    selected: bool = True


@dataclass
class MediaMetadata:
    url: str
    title: str
    thumbnail: Optional[str] = None
    uploader: Optional[str] = None
    duration: Optional[int] = None
    platform: str = "Unknown"
    upload_date: Optional[str] = None
    view_count: Optional[int] = None
    available_formats: List[Dict[str, Any]] = field(default_factory=list)
    available_resolutions: List[str] = field(default_factory=list)
    available_subtitles: Dict[str, Any] = field(default_factory=dict)
    is_playlist: bool = False
    playlist_title: Optional[str] = None
    playlist_count: int = 0
    playlist_items: List[PlaylistItem] = field(default_factory=list)
    raw_info: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AdvancedOptions:
    custom_filename: Optional[str] = None
    filename_template: Optional[str] = None
    embed_thumbnail: bool = True
    embed_metadata: bool = True
    subtitles_enabled: bool = False
    subtitle_language: str = "en"
    auto_subtitles: bool = False
    subtitle_format: str = "srt"
    embed_subtitles: bool = False
    overwrite_behavior: str = "no_overwrite"  # no_overwrite, overwrite
    raw_format_id: Optional[str] = None
    # Shorts/Reels filter modes
    shorts_only: bool = False
    reels_only: bool = False


@dataclass
class DownloadJob:
    url: str
    title: str = "Initializing..."
    media_type: str = "Video"  # Video, Audio, Image
    quality_key: str = "Best Available"
    audio_codec: str = "MP3"
    audio_quality: str = "192 kbps"
    output_dir: str = ""
    status: JobStatus = JobStatus.QUEUED
    progress: float = 0.0
    percent_str: str = "0%"
    speed_str: str = "N/A"
    eta_str: str = "N/A"
    downloaded_bytes: int = 0
    total_bytes: Optional[int] = None
    result_file: Optional[str] = None
    error_info: Optional[Dict[str, Any]] = None
    job_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    created_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    thumbnail: Optional[str] = None
    platform: str = "Web"
    options: AdvancedOptions = field(default_factory=AdvancedOptions)
