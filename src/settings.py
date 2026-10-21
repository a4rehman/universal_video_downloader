"""
Application Settings & Preferences Management for OmniStream.
Stores user settings in ~/.omnistream_config.json.
"""

import json
import os
from typing import Dict, Any
from .filesystem import get_default_download_directory
from .database import CloudSettingsRepository, is_db_configured

CONFIG_FILE = os.path.join(os.path.expanduser("~"), ".omnistream_config.json")

DEFAULT_SETTINGS: Dict[str, Any] = {
    "download_path": get_default_download_directory(),
    "theme": "Dark",
    "accent": "Violet",
    "default_media_type": "Video",
    "default_quality": "Best Available",
    "default_audio_format": "MP3",
    "default_audio_quality": "192 kbps",
    "max_concurrency": 3,
    "retry_count": 3,
    "timeout_seconds": 30,
    "filename_template": "%(title).120s [%(id)s].%(ext)s",
    "playlist": True,
    "playlist_limit": 0,
    "embed_thumbnail": False,
    "embed_metadata": True,
    "cookies_browser": None,
    "cookies_file": "",
    "history_enabled": True,
    "debug_logging": False,
}


def load_settings() -> Dict[str, Any]:
    """Loads configuration settings from JSON file with defaults fallback and TiDB sync."""
    cfg = DEFAULT_SETTINGS.copy()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                if isinstance(saved, dict):
                    cfg.update(saved)
        except Exception:
            pass
    if "cookies_file" in cfg and isinstance(cfg["cookies_file"], str):
        cfg["cookies_file"] = cfg["cookies_file"].strip().strip("'\"").strip()
    return cfg


def save_settings(settings_dict: Dict[str, Any]) -> bool:
    """Saves updated settings to JSON file and synchronizes to TiDB Cloud where applicable."""
    try:
        current = load_settings()
        cleaned = dict(settings_dict)
        if "cookies_file" in cleaned and isinstance(cleaned["cookies_file"], str):
            cleaned["cookies_file"] = cleaned["cookies_file"].strip().strip("'\"").strip()
        current.update(cleaned)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2, ensure_ascii=False)

        # Synchronize non-machine settings to TiDB Cloud if configured
        if is_db_configured():
            for k, v in settings_dict.items():
                if k not in ("download_path", "download_dir"):
                    CloudSettingsRepository.save_setting(k, v)
        return True
    except Exception:
        return False


def get_setting(key: str, default: Any = None) -> Any:
    """Gets a specific configuration setting."""
    cfg = load_settings()
    return cfg.get(key, default if default is not None else DEFAULT_SETTINGS.get(key))
