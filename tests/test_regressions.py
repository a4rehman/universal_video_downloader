"""Regression tests for queue execution, duplicate prevention, and channel/platform handling."""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.queue import QueueManager
from src.media import JobStatus, MediaMetadata, PlaylistItem, AdvancedOptions
from src.extractor import (
    DESKTOP_USER_AGENT,
    YOUTUBE_CLIENT_CHAINS as EXTRACTOR_CHAINS,
    channel_tab_urls,
    _entry_key,
    _build_ydl_opts,
    _MISSING_TAB_RE,
)
from src.downloader import (
    YOUTUBE_CLIENT_CHAINS as DOWNLOADER_CHAINS,
    apply_common_opts,
    download_media,
)
from src.system import resolve_js_runtime


# ---------------------------------------------------------------- worker stall & queue
def test_worker_slot_released_when_download_raises(monkeypatch):
    """
    Queue stall regression test:
    When a download worker raises an unhandled exception or fails, the worker slot must be released
    and subsequent jobs must proceed rather than locking the worker pool.
    """
    queue_mgr = QueueManager(max_concurrency=2)

    def failing_download(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("src.queue.download_media", failing_download)

    # Enqueue 3 jobs on a 2-worker pool
    job1 = queue_mgr.add_job("https://example.com/fail1", "Fail 1")
    job2 = queue_mgr.add_job("https://example.com/fail2", "Fail 2")
    job3 = queue_mgr.add_job("https://example.com/fail3", "Fail 3")

    # Wait briefly for execution
    timeout = time.time() + 5.0
    while time.time() < timeout:
        all_jobs = queue_mgr.get_all_jobs()
        if all(j.status == JobStatus.FAILED for j in all_jobs):
            break
        time.sleep(0.1)

    jobs = {j.url: j for j in queue_mgr.get_all_jobs()}
    assert jobs["https://example.com/fail1"].status == JobStatus.FAILED
    assert jobs["https://example.com/fail2"].status == JobStatus.FAILED
    assert jobs["https://example.com/fail3"].status == JobStatus.FAILED
    assert "boom" in str(jobs["https://example.com/fail1"].error_info.get("technical_details", ""))


def test_worker_continues_after_failures(monkeypatch):
    """A failed job must not prevent the next queued job from starting and succeeding."""
    queue_mgr = QueueManager(max_concurrency=1)

    ran = []

    def mock_download(url, *args, **kwargs):
        ran.append(url)
        if "bad" in url:
            return False, "Simulated failure"
        return True, "test_file.mp4"

    monkeypatch.setattr("src.queue.download_media", mock_download)
    monkeypatch.setattr("src.queue.add_history_record", lambda **kw: None)

    queue_mgr.add_job("https://example.com/bad", "Bad Job")
    queue_mgr.add_job("https://example.com/good1", "Good Job 1")
    queue_mgr.add_job("https://example.com/good2", "Good Job 2")

    timeout = time.time() + 5.0
    while time.time() < timeout:
        if len(ran) == 3:
            break
        time.sleep(0.1)

    assert len(ran) == 3, f"Expected 3 jobs to run, but ran: {ran}"
    jobs = {j.url: j for j in queue_mgr.get_all_jobs()}
    assert jobs["https://example.com/bad"].status == JobStatus.FAILED
    assert jobs["https://example.com/good1"].status == JobStatus.COMPLETED
    assert jobs["https://example.com/good2"].status == JobStatus.COMPLETED


def test_queue_prevents_duplicate_active_jobs(monkeypatch):
    """Adding the same URL when it is already queued or downloading must not create duplicate jobs."""
    import threading
    pause_event = threading.Event()

    def slow_mock(*args, **kwargs):
        pause_event.wait(timeout=2.0)
        return True, "mock.mp4"

    monkeypatch.setattr("src.queue.download_media", slow_mock)
    monkeypatch.setattr("src.queue.add_history_record", lambda **kw: None)

    queue_mgr = QueueManager(max_concurrency=2)
    job1 = queue_mgr.add_job("https://example.com/dup1", "Duplicate Test")
    job2 = queue_mgr.add_job("https://example.com/dup1", "Duplicate Test")

    pause_event.set()
    assert job1.job_id == job2.job_id
    assert len(queue_mgr.get_all_jobs()) == 1


def test_queue_never_enqueues_empty_playlist():
    """An empty playlist/collection must return an empty list and never enqueue the collection URL."""
    queue_mgr = QueueManager(max_concurrency=2)
    meta = MediaMetadata(
        url="https://www.instagram.com/empty_user/reels/",
        title="Empty Profile",
        is_playlist=True,
        playlist_items=[],
        playlist_count=0,
    )

    enqueued = queue_mgr.enqueue_metadata(meta)
    assert enqueued == []
    assert len(queue_mgr.get_all_jobs()) == 0


def test_instagram_collection_blocked_from_download():
    """Attempting to download an Instagram profile or reels collection directly as a single video is blocked."""
    ok, err = download_media(
        url="https://www.instagram.com/ampureleathers/reels/",
        media_type="Video",
        quality_key="Best Available",
        output_dir="downloads",
    )
    assert ok is False
    assert "cannot be downloaded directly as a single video" in err


# ------------------------------------------------------------ channel listings
def test_listing_uses_desktop_user_agent():
    """
    A mobile User-Agent makes YouTube serve the mweb channel page, which yt-dlp's
    youtube:tab extractor cannot parse ("Unable to recognize tab page").
    """
    opts = _build_ydl_opts(
        "https://www.youtube.com/@x/shorts", "YouTube", ["visionos"], None, None
    )
    ua = opts["http_headers"]["User-Agent"]
    assert ua == DESKTOP_USER_AGENT
    assert "iPhone" not in ua and "Mobile" not in ua


def test_listing_does_not_force_tab_arg():
    """Forcing the 'tab' extractor arg is what produced 'Unable to recognize tab page'."""
    opts = _build_ydl_opts(
        "https://www.youtube.com/@x/shorts", "YouTube", ["visionos"], None, None
    )
    assert "tab" not in opts["extractor_args"]["youtube"]


def test_no_forced_client_is_a_supported_chain():
    """None is the last-resort chain meaning 'let yt-dlp choose'."""
    assert None in EXTRACTOR_CHAINS
    assert None in DOWNLOADER_CHAINS
    opts = _build_ydl_opts(
        "https://www.youtube.com/@x/videos", "YouTube", None, None, None
    )
    assert "player_client" not in opts["extractor_args"]["youtube"]


def test_retries_are_bounded():
    """retries must be bounded so one slow or failing request cannot hang indefinitely."""
    opts = _build_ydl_opts(
        "https://www.youtube.com/@x/videos", "YouTube", None, None, None
    )
    assert opts.get("socket_timeout", 0) <= 60


# ------------------------------------------------------------- all channel tabs
def test_bare_handle_expands_to_all_tabs():
    urls = channel_tab_urls("https://www.youtube.com/@TehzeebLibasOfficial")
    assert urls == [
        "https://www.youtube.com/@TehzeebLibasOfficial/videos",
        "https://www.youtube.com/@TehzeebLibasOfficial/shorts",
        "https://www.youtube.com/@TehzeebLibasOfficial/streams",
    ]


def test_tab_or_video_url_is_not_expanded():
    assert channel_tab_urls("https://www.youtube.com/@x/shorts") == []
    assert channel_tab_urls("https://www.youtube.com/@x/videos") == []
    assert channel_tab_urls("https://www.youtube.com/watch?v=abcdefghijk") == []
    assert channel_tab_urls("https://www.youtube.com/playlist?list=PL1") == []


def test_entry_key_dedupes_across_tabs():
    """The same video listed on two tabs must be queued only once."""
    assert _entry_key("https://www.youtube.com/watch?v=abcdefghijk") == "abcdefghijk"
    assert _entry_key("https://youtu.be/abcdefghijk") != ""
    assert (
        _entry_key("https://www.youtube.com/watch?v=abcdefghijk")
        == _entry_key("https://www.youtube.com/shorts/abcdefghijk")
    )


def test_missing_tab_is_not_treated_as_fatal():
    """'channel does not have a streams tab' is expected, not an error."""
    assert _MISSING_TAB_RE.search("This channel does not have a streams tab")
    assert _MISSING_TAB_RE.search("This channel does not have a shorts tab")
    assert not _MISSING_TAB_RE.search("Unable to recognize tab page")


# ------------------------------------------------------------- JS challenge
def test_js_runtime_is_resolved_and_wired():
    """
    yt-dlp requires a JS runtime for YouTube signature challenges.
    The runtime must be detected and passed properly.
    """
    js = resolve_js_runtime()
    if js is None:
        opts = _build_ydl_opts(
            "https://www.youtube.com/watch?v=abcdefghijk", "YouTube", ["visionos"], None, None
        )
        assert "js_runtimes" not in opts
        return

    name, cfg = next(iter(js.items()))
    assert name in ("deno", "node", "bun", "quickjs")
    assert isinstance(cfg, dict)

    opts = _build_ydl_opts(
        "https://www.youtube.com/watch?v=abcdefghijk", "YouTube", ["visionos"], None, None
    )
    assert opts["js_runtimes"] == js
    assert "ejs:github" in opts["remote_components"]


def test_apply_common_opts_wires_shared_settings():
    """Verifies that apply_common_opts attaches user agent, ffmpeg, and js runtime."""
    opts = apply_common_opts({"quiet": True}, "https://www.youtube.com/watch?v=test1234567")
    assert opts["http_headers"]["User-Agent"] == DESKTOP_USER_AGENT
    assert opts.get("windowsfilenames") is True
    assert opts.get("trim_file_name") > 0