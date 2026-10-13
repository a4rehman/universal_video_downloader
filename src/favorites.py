"""
Saved Favorite URLs Persistence for OmniStream.
Stores favorite URLs in ~/.omnistream_favorites.json.
"""

import json
import os
import time
from typing import List, Dict, Any

FAVORITES_FILE = os.path.join(os.path.expanduser("~"), ".omnistream_favorites.json")


def load_favorites() -> List[Dict[str, Any]]:
    """Loads favorites list from JSON file."""
    if not os.path.exists(FAVORITES_FILE):
        return []
    try:
        with open(FAVORITES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []


def save_favorites(items: List[Dict[str, Any]]) -> bool:
    """Saves favorites list to JSON file."""
    try:
        with open(FAVORITES_FILE, "w", encoding="utf-8") as f:
            json.dump(items, f, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False


def add_favorite(url: str, title: str, platform: str = "Web", name: str = "") -> bool:
    """Adds a new URL to favorites."""
    if not url:
        return False

    favs = load_favorites()
    # Prevent duplicate URL entries
    favs = [f for f in favs if f.get("url") != url]

    new_item = {
        "id": f"fav_{int(time.time()*1000)}",
        "url": url,
        "title": title or url,
        "name": name or title or url,
        "platform": platform or "Web",
        "added_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "timestamp": time.time(),
    }

    favs.insert(0, new_item)
    return save_favorites(favs)


def remove_favorite(fav_id_or_url: str) -> bool:
    """Removes a favorite entry by ID or URL."""
    favs = load_favorites()
    updated = [f for f in favs if f.get("id") != fav_id_or_url and f.get("url") != fav_id_or_url]
    return save_favorites(updated)


def clear_favorites() -> bool:
    """Clears all saved favorites."""
    return save_favorites([])
