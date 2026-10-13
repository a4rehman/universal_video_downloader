import pytest
from src.errors import (
    map_exception_to_user_message,
    ErrorCategory,
    InvalidURLError,
    FFmpegError,
    FormatUnavailableError
)


def test_map_custom_exceptions():
    err1 = InvalidURLError("Bad URL")
    mapped1 = map_exception_to_user_message(err1)
    assert mapped1["category"] == ErrorCategory.INVALID_URL
    assert "Invalid URL" in mapped1["title"]

    err2 = FFmpegError("ffmpeg not found")
    mapped2 = map_exception_to_user_message(err2)
    assert mapped2["category"] == ErrorCategory.FFMPEG_ERROR
    assert "FFmpeg" in mapped2["title"]


def test_map_raw_string_exceptions():
    mapped = map_exception_to_user_message(Exception("Sign in to confirm you’re not a bot"))
    assert mapped["category"] == ErrorCategory.RATE_LIMIT
    assert "Bot Check" in mapped["title"]
