"""
Download History Persistence and Querying for OmniStream.
Stores completed download metadata in ~/.omnistream_history.json.
"""

import json
import os
import time
from typing import List, Dict, Any, Optional

HISTORY_FILE = os.path.join(os.path.expanduser("~"), ".omnistream_history.json")


def load_history() -> List[Dict[str, Any]]:
    """Loads download history list from local JSON storage."""
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []


def save_history(records: List[Dict[str, Any]]) -> bool:
    """Saves download history list to local JSON storage."""
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False


def add_history_record(
    url: str,
    title: str,
    platform: str,
    format_type: str,
    resolution: str,
    size_str: str,
    file_path: Optional[str] = None,
    thumbnail: Optional[str] = None,
    status: str = "Completed"
) -> bool:
    """Adds a new record to download history."""
    records = load_history()
    
    # Remove older duplicate record if url matches
    records = [r for r in records if r.get("url") != url]

    new_entry = {
        "id": f"hist_{int(time.time()*1000)}",
        "url": url,
        "title": title or "Downloaded Media",
        "platform": platform or "Web",
        "format": format_type or "Video",
        "resolution": resolution or "Best",
        "size": size_str or "?",
        "file_path": file_path or "",
        "thumbnail": thumbnail or "",
        "date": time.strftime("%Y-%m-%d %H:%M:%S"),
        "timestamp": time.time(),
        "status": status,
    }

    records.insert(0, new_entry)
    # Cap history at 500 entries
    return save_history(records[:500])


def search_history(
    query: str = "",
    platform_filter: str = "All",
    type_filter: str = "All",
    sort_by: str = "Newest"
) -> List[Dict[str, Any]]:
    """
    Searches and filters history entries.
    """
    records = load_history()

    if query:
        q = query.lower()
        records = [r for r in records if q in r.get("title", "").lower() or q in r.get("url", "").lower() or q in r.get("platform", "").lower()]

    if platform_filter and platform_filter != "All":
        records = [r for r in records if r.get("platform", "").lower() == platform_filter.lower()]

    if type_filter and type_filter != "All":
        records = [r for r in records if r.get("format", "").lower() == type_filter.lower()]

    if sort_by == "Newest":
        records.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
    elif sort_by == "Oldest":
        records.sort(key=lambda x: x.get("timestamp", 0))
    elif sort_by == "Title (A-Z)":
        records.sort(key=lambda x: x.get("title", "").lower())

    return records


def delete_history_item(record_id: str) -> bool:
    """Deletes a specific record by ID."""
    records = load_history()
    updated = [r for r in records if r.get("id") != record_id and r.get("url") != record_id]
    return save_history(updated)


def clear_history() -> bool:
    """Clears all download history."""
    return save_history([])
