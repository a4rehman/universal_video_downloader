import os
import pytest
from src.history import add_history_record, load_history, search_history, clear_history, delete_history_item


def test_history_crud():
    clear_history()
    assert len(load_history()) == 0

    add_history_record(
        url="https://example.com/video1",
        title="Test Video 1",
        platform="YouTube",
        format_type="Video",
        resolution="1080p",
        size_str="15 MB",
    )

    history = load_history()
    assert len(history) == 1
    assert history[0]["title"] == "Test Video 1"

    # Search
    results = search_history(query="Test Video")
    assert len(results) == 1

    # Delete
    delete_history_item(history[0]["id"])
    assert len(load_history()) == 0
