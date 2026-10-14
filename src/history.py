"""
Download History Persistence and Querying for OmniStream.
Stores completed download metadata in ~/.omnistream_history.json.
"""

import json
import os
import time
from typing import List, Dict, Any, Optional

from .database import CloudHistoryRepository, is_db_configured

HISTORY_FILE = os.path.join(os.path.expanduser("~"), ".omnistream_history.json")


def load_history() -> List[Dict[str, Any]]:
    """Loads download history list from TiDB Cloud or local JSON fallback."""
    if is_db_configured():
        records = CloudHistoryRepository.search_records(limit=500)
        if records:
            return records
    # Local fallback
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
    """Adds a new record to download history (TiDB Cloud + local fallback cache)."""
    return CloudHistoryRepository.add_record(
        url=url,
        title=title,
        platform=platform,
        format_type=format_type,
        resolution=resolution,
        size_str=size_str,
        file_path=file_path,
        thumbnail=thumbnail,
        status=status,
    )


def search_history(
    query: str = "",
    platform_filter: str = "All",
    type_filter: str = "All",
    sort_by: str = "Newest"
) -> List[Dict[str, Any]]:
    """
    Searches and filters history entries from TiDB Cloud with local fallback.
    """
    return CloudHistoryRepository.search_records(
        query=query,
        platform_filter=platform_filter,
        type_filter=type_filter,
        sort_by=sort_by,
    )


def delete_history_item(record_id: str) -> bool:
    """Deletes a specific record by ID from TiDB Cloud and local cache."""
    return CloudHistoryRepository.delete_record(record_id)


def clear_history() -> bool:
    """Clears all download history from TiDB Cloud and local cache."""
    return CloudHistoryRepository.clear_all()
