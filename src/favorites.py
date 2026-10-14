"""
Saved Favorite URLs Persistence for OmniStream.
Stores favorite URLs in ~/.omnistream_favorites.json.
"""

import json
import os
import time
from typing import List, Dict, Any

from .database import CloudFavoritesRepository, is_db_configured

FAVORITES_FILE = os.path.join(os.path.expanduser("~"), ".omnistream_favorites.json")


def load_favorites() -> List[Dict[str, Any]]:
    """Loads favorites list from TiDB Cloud or local JSON fallback."""
    if is_db_configured():
        favs = CloudFavoritesRepository.load_favorites()
        if favs:
            return favs
    if not os.path.exists(FAVORITES_FILE):
        return []
    try:
        with open(FAVORITES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []


def save_favorites(items: List[Dict[str, Any]]) -> bool:
    """Saves favorites list to local JSON file."""
    try:
        with open(FAVORITES_FILE, "w", encoding="utf-8") as f:
            json.dump(items, f, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False


def add_favorite(url: str, title: str, platform: str = "Web", name: str = "") -> bool:
    """Adds a new URL to favorites (TiDB Cloud + local fallback cache)."""
    if not url:
        return False
    return CloudFavoritesRepository.add_favorite(url, title, platform, name)


def remove_favorite(fav_id_or_url: str) -> bool:
    """Removes a favorite entry by ID or URL from TiDB Cloud and local cache."""
    return CloudFavoritesRepository.remove_favorite(fav_id_or_url)


def clear_favorites() -> bool:
    """Clears all saved favorites from TiDB Cloud and local cache."""
    return CloudFavoritesRepository.clear_all()
