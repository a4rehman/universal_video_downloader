"""
Platform Capability Registry for OmniStream.

Defines supported features for each platform so the UI can show
what's available, partially supported, or unavailable.
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from enum import Enum


class PlatformCapability(str, Enum):
    SINGLE_VIDEO = "single_video"
    CHANNEL_PROFILE = "channel_profile"
    PLAYLIST = "playlist"
    SHORTS_REELS = "shorts_reels"
    LIVESTREAMS = "livestreams"
    SEARCH = "search"
    USER_COLLECTION = "user_collection"


class SupportLevel(str, Enum):
    FULL = "full"
    PARTIAL = "partial"
    LIMITED = "limited"
    NONE = "none"


@dataclass
class PlatformCapabilityInfo:
    capability: PlatformCapability
    support_level: SupportLevel
    notes: str = ""
    requires_auth: bool = False
    quality_options: List[str] = field(default_factory=list)
    audio_only: bool = False


PLATFORM_CAPABILITIES: Dict[str, Dict[PlatformCapability, PlatformCapabilityInfo]] = {
    "YouTube": {
        PlatformCapability.SINGLE_VIDEO: PlatformCapabilityInfo(
            capability=PlatformCapability.SINGLE_VIDEO,
            support_level=SupportLevel.FULL,
            quality_options=["4K (2160p)", "1440p", "1080p", "720p", "480p", "360p"],
            audio_only=True,
        ),
        PlatformCapability.CHANNEL_PROFILE: PlatformCapabilityInfo(
            capability=PlatformCapability.CHANNEL_PROFILE,
            support_level=SupportLevel.FULL,
            notes="Supports /videos, /shorts, /streams tabs",
        ),
        PlatformCapability.PLAYLIST: PlatformCapabilityInfo(
            capability=PlatformCapability.PLAYLIST,
            support_level=SupportLevel.FULL,
        ),
        PlatformCapability.SHORTS_REELS: PlatformCapabilityInfo(
            capability=PlatformCapability.SHORTS_REELS,
            support_level=SupportLevel.FULL,
            notes="Via /shorts tab or Shorts-only filter",
        ),
        PlatformCapability.LIVESTREAMS: PlatformCapabilityInfo(
            capability=PlatformCapability.LIVESTREAMS,
            support_level=SupportLevel.PARTIAL,
            notes="Live streams may require auth",
        ),
        PlatformCapability.USER_COLLECTION: PlatformCapabilityInfo(
            capability=PlatformCapability.USER_COLLECTION,
            support_level=SupportLevel.FULL,
            notes="All uploads across tabs",
        ),
    },
    "Instagram": {
        PlatformCapability.SINGLE_VIDEO: PlatformCapabilityInfo(
            capability=PlatformCapability.SINGLE_VIDEO,
            support_level=SupportLevel.FULL,
            notes="Individual Reels, Posts, TV",
            quality_options=["Best Available"],
        ),
        PlatformCapability.CHANNEL_PROFILE: PlatformCapabilityInfo(
            capability=PlatformCapability.CHANNEL_PROFILE,
            support_level=SupportLevel.FULL,
            notes="Profile and /reels/ listing",
            requires_auth=True,
        ),
        PlatformCapability.SHORTS_REELS: PlatformCapabilityInfo(
            capability=PlatformCapability.SHORTS_REELS,
            support_level=SupportLevel.FULL,
            notes="Reels from profile or /reels/ listing",
            requires_auth=True,
        ),
        PlatformCapability.USER_COLLECTION: PlatformCapabilityInfo(
            capability=PlatformCapability.USER_COLLECTION,
            support_level=SupportLevel.FULL,
            notes="All Reels from profile",
            requires_auth=True,
        ),
    },
    "TikTok": {
        PlatformCapability.SINGLE_VIDEO: PlatformCapabilityInfo(
            capability=PlatformCapability.SINGLE_VIDEO,
            support_level=SupportLevel.FULL,
            quality_options=["Best Available"],
            audio_only=True,
        ),
        PlatformCapability.CHANNEL_PROFILE: PlatformCapabilityInfo(
            capability=PlatformCapability.CHANNEL_PROFILE,
            support_level=SupportLevel.PARTIAL,
            notes="User profile videos",
        ),
        PlatformCapability.USER_COLLECTION: PlatformCapabilityInfo(
            capability=PlatformCapability.USER_COLLECTION,
            support_level=SupportLevel.PARTIAL,
        ),
    },
    "Facebook": {
        PlatformCapability.SINGLE_VIDEO: PlatformCapabilityInfo(
            capability=PlatformCapability.SINGLE_VIDEO,
            support_level=SupportLevel.FULL,
            notes="Videos and Reels",
            quality_options=["Best Available"],
        ),
        PlatformCapability.CHANNEL_PROFILE: PlatformCapabilityInfo(
            capability=PlatformCapability.CHANNEL_PROFILE,
            support_level=SupportLevel.PARTIAL,
            notes="Public pages and profiles",
        ),
        PlatformCapability.SHORTS_REELS: PlatformCapabilityInfo(
            capability=PlatformCapability.SHORTS_REELS,
            support_level=SupportLevel.PARTIAL,
            notes="Facebook Reels",
        ),
    },
    "Twitter / X": {
        PlatformCapability.SINGLE_VIDEO: PlatformCapabilityInfo(
            capability=PlatformCapability.SINGLE_VIDEO,
            support_level=SupportLevel.FULL,
            quality_options=["Best Available"],
        ),
        PlatformCapability.USER_COLLECTION: PlatformCapabilityInfo(
            capability=PlatformCapability.USER_COLLECTION,
            support_level=SupportLevel.LIMITED,
            notes="User timeline and lists",
        ),
    },
    "TikTok": {
        PlatformCapability.SINGLE_VIDEO: PlatformCapabilityInfo(
            capability=PlatformCapability.SINGLE_VIDEO,
            support_level=SupportLevel.FULL,
            quality_options=["Best Available"],
            audio_only=True,
        ),
        PlatformCapability.CHANNEL_PROFILE: PlatformCapabilityInfo(
            capability=PlatformCapability.CHANNEL_PROFILE,
            support_level=SupportLevel.PARTIAL,
            notes="User profile videos",
        ),
        PlatformCapability.USER_COLLECTION: PlatformCapabilityInfo(
            capability=PlatformCapability.USER_COLLECTION,
            support_level=SupportLevel.PARTIAL,
        ),
    },
    "Dailymotion": {
        PlatformCapability.SINGLE_VIDEO: PlatformCapabilityInfo(
            capability=PlatformCapability.SINGLE_VIDEO,
            support_level=SupportLevel.FULL,
            quality_options=["Best Available", "1080p", "720p", "480p"],
            audio_only=True,
        ),
        PlatformCapability.CHANNEL_PROFILE: PlatformCapabilityInfo(
            capability=PlatformCapability.CHANNEL_PROFILE,
            support_level=SupportLevel.PARTIAL,
        ),
        PlatformCapability.PLAYLIST: PlatformCapabilityInfo(
            capability=PlatformCapability.PLAYLIST,
            support_level=SupportLevel.FULL,
        ),
        PlatformCapability.USER_COLLECTION: PlatformCapabilityInfo(
            capability=PlatformCapability.USER_COLLECTION,
            support_level=SupportLevel.PARTIAL,
        ),
    },
    "Twitch": {
        PlatformCapability.SINGLE_VIDEO: PlatformCapabilityInfo(
            capability=PlatformCapability.SINGLE_VIDEO,
            support_level=SupportLevel.FULL,
            notes="Clips and VODs",
            quality_options=["Best Available", "1080p", "720p", "480p"],
        ),
        PlatformCapability.CHANNEL_PROFILE: PlatformCapabilityInfo(
            capability=PlatformCapability.CHANNEL_PROFILE,
            support_level=SupportLevel.PARTIAL,
            notes="Videos, Clips, Collections tabs",
        ),
        PlatformCapability.USER_COLLECTION: PlatformCapabilityInfo(
            capability=PlatformCapability.USER_COLLECTION,
            support_level=SupportLevel.PARTIAL,
            notes="Clips and VODs",
        ),
    },
    "LinkedIn": {
        PlatformCapability.SINGLE_VIDEO: PlatformCapabilityInfo(
            capability=PlatformCapability.SINGLE_VIDEO,
            support_level=SupportLevel.FULL,
            quality_options=["Best Available"],
        ),
        PlatformCapability.USER_COLLECTION: PlatformCapabilityInfo(
            capability=PlatformCapability.USER_COLLECTION,
            support_level=SupportLevel.LIMITED,
            notes="Posts and video feed",
        ),
    },
    "Snapchat": {
        PlatformCapability.SINGLE_VIDEO: PlatformCapabilityInfo(
            capability=PlatformCapability.SINGLE_VIDEO,
            support_level=SupportLevel.LIMITED,
            notes="Spotlight and public content only",
        ),
        PlatformCapability.USER_COLLECTION: PlatformCapabilityInfo(
            capability=PlatformCapability.USER_COLLECTION,
            support_level=SupportLevel.LIMITED,
        ),
    },
    "Dailymotion": {
        PlatformCapability.SINGLE_VIDEO: PlatformCapabilityInfo(
            capability=PlatformCapability.SINGLE_VIDEO,
            support_level=SupportLevel.FULL,
            quality_options=["Best Available", "1080p", "720p", "480p"],
            audio_only=True,
        ),
        PlatformCapability.CHANNEL_PROFILE: PlatformCapabilityInfo(
            capability=PlatformCapability.CHANNEL_PROFILE,
            support_level=SupportLevel.PARTIAL,
        ),
        PlatformCapability.PLAYLIST: PlatformCapabilityInfo(
            capability=PlatformCapability.PLAYLIST,
            support_level=SupportLevel.FULL,
        ),
        PlatformCapability.USER_COLLECTION: PlatformCapabilityInfo(
            capability=PlatformCapability.USER_COLLECTION,
            support_level=SupportLevel.PARTIAL,
        ),
    },
    "Vimeo": {
        PlatformCapability.SINGLE_VIDEO: PlatformCapabilityInfo(
            capability=PlatformCapability.SINGLE_VIDEO,
            support_level=SupportLevel.FULL,
            quality_options=["Best Available", "1080p", "720p", "480p"],
            audio_only=True,
        ),
        PlatformCapability.CHANNEL_PROFILE: PlatformCapabilityInfo(
            capability=PlatformCapability.CHANNEL_PROFILE,
            support_level=SupportLevel.PARTIAL,
            notes="Channels, Groups, Albums, Showcases",
        ),
        PlatformCapability.PLAYLIST: PlatformCapabilityInfo(
            capability=PlatformCapability.PLAYLIST,
            support_level=SupportLevel.FULL,
        ),
    },
    "SoundCloud": {
        PlatformCapability.SINGLE_VIDEO: PlatformCapabilityInfo(
            capability=PlatformCapability.SINGLE_VIDEO,
            support_level=SupportLevel.FULL,
            notes="Audio tracks",
            audio_only=True,
        ),
        PlatformCapability.PLAYLIST: PlatformCapabilityInfo(
            capability=PlatformCapability.PLAYLIST,
            support_level=SupportLevel.FULL,
        ),
        PlatformCapability.USER_COLLECTION: PlatformCapabilityInfo(
            capability=PlatformCapability.USER_COLLECTION,
            support_level=SupportLevel.FULL,
            notes="Sets, tracks, playlists",
        ),
    },
    "Reddit": {
        PlatformCapability.SINGLE_VIDEO: PlatformCapabilityInfo(
            capability=PlatformCapability.SINGLE_VIDEO,
            support_level=SupportLevel.FULL,
            quality_options=["Best Available"],
        ),
    },
    "Pinterest": {
        PlatformCapability.SINGLE_VIDEO: PlatformCapabilityInfo(
            capability=PlatformCapability.SINGLE_VIDEO,
            support_level=SupportLevel.LIMITED,
            notes="Video pins only",
        ),
        PlatformCapability.USER_COLLECTION: PlatformCapabilityInfo(
            capability=PlatformCapability.USER_COLLECTION,
            support_level=SupportLevel.LIMITED,
            notes="Boards and user profiles",
        ),
    },
    "SoundCloud": {
        PlatformCapability.SINGLE_VIDEO: PlatformCapabilityInfo(
            capability=PlatformCapability.SINGLE_VIDEO,
            support_level=SupportLevel.FULL,
            notes="Audio tracks",
            audio_only=True,
        ),
        PlatformCapability.PLAYLIST: PlatformCapabilityInfo(
            capability=PlatformCapability.PLAYLIST,
            support_level=SupportLevel.FULL,
        ),
        PlatformCapability.USER_COLLECTION: PlatformCapabilityInfo(
            capability=PlatformCapability.USER_COLLECTION,
            support_level=SupportLevel.FULL,
        ),
    },
    "Vimeo": {
        PlatformCapability.SINGLE_VIDEO: PlatformCapabilityInfo(
            capability=PlatformCapability.SINGLE_VIDEO,
            support_level=SupportLevel.FULL,
            quality_options=["Best Available", "1080p", "720p", "480p"],
            audio_only=True,
        ),
        PlatformCapability.CHANNEL_PROFILE: PlatformCapabilityInfo(
            capability=PlatformCapability.CHANNEL_PROFILE,
            support_level=SupportLevel.PARTIAL,
            notes="Channels, Groups, Albums, Showcases",
        ),
        PlatformCapability.PLAYLIST: PlatformCapabilityInfo(
            capability=PlatformCapability.PLAYLIST,
            support_level=SupportLevel.FULL,
        ),
    },
    "Direct Image": {
        PlatformCapability.SINGLE_VIDEO: PlatformCapabilityInfo(
            capability=PlatformCapability.SINGLE_VIDEO,
            support_level=SupportLevel.FULL,
            notes="Direct image URLs",
        ),
    },
    "Web Platform": {
        PlatformCapability.SINGLE_VIDEO: PlatformCapabilityInfo(
            capability=PlatformCapability.SINGLE_VIDEO,
            support_level=SupportLevel.LIMITED,
            notes="Generic extractor - may not work for all sites",
        ),
    },
}


def get_platform_capabilities(platform: str) -> Dict[PlatformCapability, PlatformCapabilityInfo]:
    """Get capabilities for a platform."""
    return PLATFORM_CAPABILITIES.get(platform, {})


def get_supported_platforms() -> List[str]:
    """Get list of all supported platforms."""
    return list(PLATFORM_CAPABILITIES.keys())


def get_capability_summary(platform: str) -> Dict[str, Any]:
    """Get a summary of platform capabilities for UI display."""
    caps = get_platform_capabilities(platform)
    summary = {
        "platform": platform,
        "capabilities": {},
        "overall_support": SupportLevel.NONE,
    }
    
    max_level = SupportLevel.NONE
    for cap, info in caps.items():
        summary["capabilities"][cap.value] = {
            "support_level": info.support_level.value,
            "notes": info.notes,
            "requires_auth": info.requires_auth,
            "quality_options": info.quality_options,
            "audio_only": info.audio_only,
        }
        # Determine overall support level
        if info.support_level == SupportLevel.FULL:
            max_level = SupportLevel.FULL
        elif info.support_level == SupportLevel.PARTIAL and max_level != SupportLevel.FULL:
            max_level = SupportLevel.PARTIAL
        elif info.support_level == SupportLevel.LIMITED and max_level in (SupportLevel.NONE, SupportLevel.LIMITED):
            max_level = SupportLevel.LIMITED
    
    summary["overall_support"] = max_level.value
    return summary


def test_platform_extraction(platform: str, test_url: str) -> Dict[str, Any]:
    """Test extraction for a platform with a test URL (for diagnostics)."""
    from .extractor import extract_media_info
    from .validators import detect_platform
    
    detected = detect_platform(test_url)
    result = {
        "platform": platform,
        "test_url": test_url,
        "detected_platform": detected,
        "matches": detected == platform or detected.startswith(platform),
        "extraction": None,
        "error": None,
    }
    
    try:
        meta = extract_media_info(test_url, playlist_limit=1)
        result["extraction"] = {
            "title": meta.title,
            "is_playlist": meta.is_playlist,
            "playlist_count": meta.playlist_count,
            "duration": meta.duration,
            "available_resolutions": meta.available_resolutions,
        }
    except Exception as e:
        result["error"] = str(e)
    
    return result