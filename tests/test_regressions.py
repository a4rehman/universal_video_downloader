"""Regression tests for the queue-stall and channel-listing bugs."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app_gui import DownloadApp, DownloadItem, DESKTOP_USER_AGENT
import app_gui
import src.extractor as extractor


class DummyConfig:
    def __init__(self, **kw):
        self._cfg = {
            "download_path": os.path.expanduser("~/Downloads"),
            "playlist": True,
            "max_retries": 8,
            "socket_timeout": 30,
            "job_timeout": 600,
        }
        self._cfg.update(kw)

    def get(self, key, default=None):
        return self._cfg.get(key, default)


class DummyApp:
    def __init__(self, **kw):
        self.config = DummyConfig(**kw)
        self.cookie_locked = type("L", (), {"is_set": lambda self: False})()
        self.logs = []

    def log(self, msg):
        self.logs.append(msg)


class FakeLabel:
    def __init__(self):
        self.text = ""

    def configure(self, **kw):
        if "text" in kw:
            self.text = kw["text"]


def make_host():
    """A minimal stand-in for DownloadApp that records worker bookkeeping."""
    host = DummyApp()
    host.downloads = {}
    host.history = []
    host.workers = 0
    host.max_workers = 3
    host.item_lock = __import__("threading").Lock()
    host.spawned = 0
    host.stat_workers_lbl = FakeLabel()
    host.stat_total_lbl = FakeLabel()
    host.stat_queued_lbl = FakeLabel()
    return host


def bind(host, name):
    """Binds a real DownloadApp method onto the stub host."""
    return lambda *a, **kw: getattr(DownloadApp, name)(host, *a, **kw)


# ---------------------------------------------------------------- worker stall
def test_worker_slot_released_when_play_raises():
    """
    The original bug: _run_worker called item.play() with no try/finally, so any
    exception leaked the slot. After max_workers failures the pool was dead and
    the batch silently stopped at exactly 3 items.
    """
    host = make_host()
    host.after = lambda ms, fn=None, *a: fn and fn()
    host._refresh_stats = bind(host, "_refresh_stats")
    host.render_active = lambda: None
    host._set_item_status = lambda url, status: None
    host.add_history = lambda *a, **kw: None

    calls = {"spawn": 0, "workers": 0}

    def spawn():
        calls["spawn"] += 1
        calls["workers"] = host.workers

    host._spawn_workers = spawn

    class Exploding(DownloadItem):
        def play(self, app):
            raise RuntimeError("boom")

    for _ in range(3):
        item = Exploding(host, "http://x", "Video", None)
        host.workers += 1
        DownloadApp._run_worker(host, item)
        assert item.status == "Error", item.status
        assert "boom" in (item.error or "")

    # Slot must be free again and the pool must be asked for more work.
    assert host.workers == 0, f"leaked {host.workers} worker slots"
    assert calls["spawn"] == 3
    assert calls["workers"] == 0

    # And the pool is still able to take on new work.
    host._spawn_workers()
    assert calls["spawn"] == 4


def test_worker_continues_after_failures():
    """A failed job must not prevent the next queued job from starting."""
    host = make_host()
    host.after = lambda ms, fn=None, *a: fn and fn()
    host._refresh_stats = bind(host, "_refresh_stats")
    host.render_active = lambda: None
    host._set_item_status = lambda url, status: None
    host.add_history = lambda *a, **kw: None
    host._spawn_workers = lambda: None

    ran = []

    class Flaky(DownloadItem):
        def play(self, app):
            ran.append(self.url)
            if self.url.endswith("bad"):
                raise ValueError("nope")
            return True, self.url + ".mp4"

    for name in ("http://bad", "http://good1", "http://good2"):
        item = Flaky(host, name, "Video", None)
        host.workers += 1
        DownloadApp._run_worker(host, item)

    assert len(ran) == 3, "later jobs were blocked by an earlier failure"
    assert host.workers == 0


def test_progress_counter_reports_x_of_n():
    """The batch view must show real progress so a long run does not look frozen."""
    host = make_host()

    class It:
        def __init__(self, status):
            self.status = status

    host.downloads = {str(i): It(s) for i, s in enumerate(
        ["Done", "Done", "Error", "Queued", "Downloading"])}
    host.history = ["a", "b"]

    DownloadApp._refresh_stats(host)
    text = host.stat_queued_lbl.text
    assert "2/5" in text, text
    assert "1 failed" in text, text


# ------------------------------------------------------------ channel listings
def test_listing_uses_desktop_user_agent():
    """
    A mobile User-Agent makes YouTube serve the mweb channel page, which yt-dlp's
    youtube:tab extractor cannot parse ("Unable to recognize tab page"). That
    made every channel/Shorts listing fail.
    """
    opts = extractor._build_ydl_opts(
        "https://www.youtube.com/@x/shorts", "YouTube", ["visionos"], None, None)
    ua = opts["http_headers"]["User-Agent"]
    assert ua == DESKTOP_USER_AGENT
    assert "iPhone" not in ua and "Mobile" not in ua


def test_listing_does_not_force_tab_arg():
    """Forcing the 'tab' extractor arg is what produced "Unable to recognize tab page"."""
    opts = extractor._build_ydl_opts(
        "https://www.youtube.com/@x/shorts", "YouTube", ["visionos"], None, None)
    assert "tab" not in opts["extractor_args"]["youtube"]


def test_no_forced_client_is_a_supported_chain():
    """None is the last-resort chain meaning 'let yt-dlp choose'."""
    assert None in extractor.YOUTUBE_CLIENT_CHAINS
    assert None in app_gui.YOUTUBE_CLIENT_CHAINS
    opts = extractor._build_ydl_opts(
        "https://www.youtube.com/@x/videos", "YouTube", None, None, None)
    assert "player_client" not in opts["extractor_args"]["youtube"]


def test_retries_are_bounded():
    """retries=100 held a worker slot for many minutes and looked like a freeze."""
    item = DownloadItem(DummyApp(), "http://x", "Video", None)
    opts = item.build_opts(["visionos"])
    assert opts["retries"] <= 10
    assert opts["fragment_retries"] <= 10
    assert opts["socket_timeout"] <= 60


# ------------------------------------------------------------- all channel tabs
def test_bare_handle_expands_to_all_tabs():
    urls = extractor.channel_tab_urls("https://www.youtube.com/@TehzeebLibasOfficial")
    assert urls == [
        "https://www.youtube.com/@TehzeebLibasOfficial/videos",
        "https://www.youtube.com/@TehzeebLibasOfficial/shorts",
        "https://www.youtube.com/@TehzeebLibasOfficial/streams",
    ]


def test_tab_or_video_url_is_not_expanded():
    # An explicit tab must not be re-expanded, or videos would be fetched twice.
    assert extractor.channel_tab_urls("https://www.youtube.com/@x/shorts") == []
    assert extractor.channel_tab_urls("https://www.youtube.com/@x/videos") == []
    assert extractor.channel_tab_urls("https://www.youtube.com/watch?v=abcdefghijk") == []
    assert extractor.channel_tab_urls("https://www.youtube.com/playlist?list=PL1") == []


def test_gui_channel_tab_targets():
    assert DownloadApp._channel_tab_targets(
        "https://www.youtube.com/@x") == [
        "https://www.youtube.com/@x/videos",
        "https://www.youtube.com/@x/shorts",
        "https://www.youtube.com/@x/streams",
    ]
    assert DownloadApp._channel_tab_targets("https://www.youtube.com/@x/shorts") == []


def test_entry_key_dedupes_across_tabs():
    """The same video listed on two tabs must be queued only once."""
    assert extractor._entry_key("https://www.youtube.com/watch?v=abcdefghijk") == "abcdefghijk"
    assert extractor._entry_key("https://youtu.be/abcdefghijk") != ""
    assert (extractor._entry_key("https://www.youtube.com/watch?v=abcdefghijk")
            == extractor._entry_key("https://www.youtube.com/shorts/abcdefghijk"))


def test_missing_tab_is_not_treated_as_fatal():
    """'channel does not have a streams tab' is expected, not an error."""
    from src.extractor import _MISSING_TAB_RE
    assert _MISSING_TAB_RE.search("This channel does not have a streams tab")
    assert _MISSING_TAB_RE.search("This channel does not have a shorts tab")
    assert not _MISSING_TAB_RE.search("Unable to recognize tab page")


# ------------------------------------------------------------- JS challenge
def test_js_runtime_is_resolved_and_wired():
    """
    yt-dlp only enables Deno by default, so with only Node installed every
    YouTube video failed with "This video is not available". The runtime must be
    detected and passed explicitly.
    """
    from src.system import resolve_js_runtime
    js = resolve_js_runtime()
    if js is None:
        # No runtime installed at all: nothing to wire, but the option must
        # still be absent rather than malformed.
        opts = extractor._build_ydl_opts(
            "https://www.youtube.com/watch?v=abcdefghijk", "YouTube", ["visionos"], None, None)
        assert "js_runtimes" not in opts
        return

    name, cfg = next(iter(js.items()))
    assert name in ("deno", "node", "bun", "quickjs")
    assert isinstance(cfg, dict)

    opts = extractor._build_ydl_opts(
        "https://www.youtube.com/watch?v=abcdefghijk", "YouTube", ["visionos"], None, None)
    assert opts["js_runtimes"] == js
    assert "ejs:github" in opts["remote_components"]

    item = DownloadItem(DummyApp(), "https://www.youtube.com/watch?v=abcdefghijk", "Video", None)
    gopts = item.build_opts(["visionos"])
    assert gopts["js_runtimes"] == js
    assert "ejs:github" in gopts["remote_components"]


def test_gui_apply_js_runtime_shape():
    opts = app_gui.apply_js_runtime({"quiet": True})
    if "js_runtimes" in opts:
        runtime = next(iter(opts["js_runtimes"]))
        assert runtime in ("deno", "node", "bun", "quickjs")
        assert "ejs:github" in opts["remote_components"]
    # The key must never be present with an empty/malformed value.
    assert opts.get("js_runtimes") not in ({}, None)


def run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception as e:
            print(f"FAIL {fn.__name__}: {type(e).__name__}: {e}")
            return 1
    print("ALL REGRESSION TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(run_all())