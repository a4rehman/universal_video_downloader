"""
System inspection and dynamic dependency detection for OmniStream.
Detects yt-dlp version, FFmpeg/FFprobe availability, Node.js installation, and network status.
"""

import os
import shutil
import subprocess
import requests
import yt_dlp
from typing import Dict, Any, Optional


def is_network_online(timeout: float = 3.0) -> bool:
    """Checks if the network connection is active."""
    for test_url in ["https://1.1.1.1", "https://8.8.8.8", "https://www.google.com"]:
        try:
            res = requests.get(test_url, timeout=timeout)
            if res.status_code == 200:
                return True
        except Exception:
            pass
    return False


def check_ffmpeg() -> bool:
    """Returns True if ffmpeg command is available in PATH."""
    return shutil.which("ffmpeg") is not None


def check_ffprobe() -> bool:
    """Returns True if ffprobe command is available in PATH."""
    return shutil.which("ffprobe") is not None


_FFMPEG_CACHE: Dict[str, Any] = {}


def _verify_executable(path: str) -> bool:
    """Verifies that an executable exists, is executable, and can execute without crashing."""
    if not path or not os.path.exists(path):
        return False
    try:
        startupinfo = None
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        res = subprocess.run(
            [path, "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
            startupinfo=startupinfo,
        )
        return res.returncode == 0
    except Exception:
        return False


def resolve_ffmpeg_path() -> Optional[str]:
    """
    Resolves a usable ffmpeg executable path.

    Priority order:
      1. System ffmpeg available on PATH (verified by running).
      2. Bundled static build shipped by the `imageio-ffmpeg` wheel (verified by running).

    yt-dlp cannot merge separate video-only/audio-only streams without ffmpeg,
    so this resolution is mandatory for producing single playable files.
    Returns None when no valid ffmpeg build can be found or verified.
    """
    if "path" in _FFMPEG_CACHE:
        return _FFMPEG_CACHE["path"]

    resolved = None
    system_candidate = shutil.which("ffmpeg")
    if system_candidate and _verify_executable(system_candidate):
        resolved = system_candidate

    if not resolved:
        try:
            import imageio_ffmpeg

            bundled_candidate = imageio_ffmpeg.get_ffmpeg_exe()
            if bundled_candidate and _verify_executable(bundled_candidate):
                resolved = bundled_candidate
        except Exception:
            resolved = None

    if resolved:
        resolved = os.path.abspath(resolved)

    _FFMPEG_CACHE["path"] = resolved
    return resolved


def resolve_ffprobe_path() -> Optional[str]:
    """
    Resolves an ffprobe path.
    Checks system PATH, then checks beside the resolved ffmpeg binary, verifying by running.
    """
    if "probe" in _FFMPEG_CACHE:
        return _FFMPEG_CACHE["probe"]

    resolved = None
    system_probe = shutil.which("ffprobe")
    if system_probe and _verify_executable(system_probe):
        resolved = system_probe

    if not resolved:
        ffmpeg_bin = resolve_ffmpeg_path()
        if ffmpeg_bin:
            ffmpeg_dir = os.path.dirname(ffmpeg_bin)
            for name in ("ffprobe.exe", "ffprobe"):
                candidate = os.path.join(ffmpeg_dir, name)
                if _verify_executable(candidate):
                    resolved = candidate
                    break

    if resolved:
        resolved = os.path.abspath(resolved)

    _FFMPEG_CACHE["probe"] = resolved
    return resolved


def get_ffmpeg_location() -> Optional[str]:
    """
    Returns a value accepted by yt-dlp's `ffmpeg_location` parameter.

    yt-dlp (postprocessor/ffmpeg.py) only accepts a string here - either the
    ffmpeg binary itself or the directory containing it. Passing a dict such as
    {"ffmpeg": ..., "ffprobe": ...} raises
    "TypeError: path should be string, bytes, os.PathLike or integer, not dict"
    inside FFmpegMergerPP, which is what previously left separate
    video-only/audio-only files on disk.
    Returns None when no ffmpeg build can be found.
    """
    return resolve_ffmpeg_path()


def has_ffmpeg() -> bool:
    """True when any usable ffmpeg build (system or bundled) is resolvable."""
    return resolve_ffmpeg_path() is not None


def check_nodejs() -> bool:
    """Returns True if node command is available in PATH."""
    return shutil.which("node") is not None or shutil.which("nodejs") is not None


_JS_RUNTIME_CACHE: Dict[str, Any] = {}

# Extra install locations, because Node is frequently installed but absent from
# the PATH of a GUI launched from Explorer.
_JS_EXTRA_PATHS: Dict[str, list] = {
    "node": [
        r"C:\Program Files\nodejs\node.exe",
        r"C:\Program Files (x86)\nodejs\node.exe",
    ],
    "bun": [r"C:\Users\%USERNAME%\.bun\bin\bun.exe"],
}


def resolve_js_runtime() -> Optional[Dict[str, Dict[str, Any]]]:
    """
    Finds a JavaScript runtime yt-dlp can use to solve YouTube's `n`/`sig` challenge.

    yt-dlp only enables Deno out of the box. If Deno is missing but Node (or
    Bun/quickjs) is installed, every YouTube video can fail with
    "This video is not available" because the challenge is never solved. This
    returns yt-dlp's `js_runtimes` mapping, e.g. {'node': {'path': ...}},
    or None when no runtime is installed.
    """
    if "result" in _JS_RUNTIME_CACHE:
        return _JS_RUNTIME_CACHE["result"]

    # Order matters: deno is yt-dlp's preferred/default runtime.
    for name in ("deno", "node", "bun", "quickjs"):
        exe = shutil.which(name)
        if not exe:
            exe = shutil.which("nodejs" if name == "node" else name)
        if not exe:
            for candidate in _JS_EXTRA_PATHS.get(name, []):
                path = os.path.expandvars(candidate)
                if os.path.isfile(path):
                    exe = path
                    break
        if exe:
            _JS_RUNTIME_CACHE["result"] = {name: {"path": exe}}
            return _JS_RUNTIME_CACHE["result"]

    _JS_RUNTIME_CACHE["result"] = None
    return None


def get_ytdlp_version() -> str:
    """Returns current version string of yt-dlp."""
    try:
        import yt_dlp.version
        return getattr(yt_dlp.version, "__version__", "Unknown")
    except Exception:
        try:
            return getattr(yt_dlp, "__version__", "Unknown")
        except Exception:
            return "Unknown"


def get_system_status() -> Dict[str, Any]:
    """
    Returns a comprehensive diagnostic report of dependencies and environment.
    """
    ffmpeg_path = resolve_ffmpeg_path()
    has_ffmpeg = bool(ffmpeg_path)
    bundled = has_ffmpeg and shutil.which("ffmpeg") is None
    has_ffprobe = check_ffprobe()
    has_node = check_nodejs()
    online = is_network_online()
    ytdlp_ver = get_ytdlp_version()

    if has_ffmpeg:
        ffmpeg_label = "Available" if not bundled else "Bundled (imageio-ffmpeg)"
    else:
        ffmpeg_label = "Not Found - stream merging is disabled"

    return {
        "yt_dlp": {
            "status": True,
            "version": ytdlp_ver,
            "label": f"yt-dlp v{ytdlp_ver}",
        },
        "ffmpeg": {
            "status": has_ffmpeg,
            "label": ffmpeg_label,
            "path": ffmpeg_path or "",
        },
        "ffprobe": {
            "status": has_ffprobe,
            "label": "Available" if has_ffprobe else "Not Found (optional)",
        },
        "nodejs": {
            "status": has_node,
            "label": "Available" if has_node else "Not Found (Optional JS challenge runner)",
        },
        "network": {
            "status": online,
            "label": "Online" if online else "Offline / Restricted Connection",
        },
        "database": _get_db_health(),
    }


def _get_db_health() -> Dict[str, Any]:
    try:
        from .database import get_database_status
        return get_database_status()
    except Exception as exc:
        return {
            "status": "Not configured",
            "connected": False,
            "label": "Not configured",
            "message": str(exc),
            "version": 0,
        }
