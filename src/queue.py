"""
Download Queue Manager and Concurrent Job Dispatcher for OmniStream.
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Callable, Any

from .media import DownloadJob, JobStatus, AdvancedOptions, MediaMetadata
from .downloader import download_media
from .history import add_history_record
from .errors import map_exception_to_user_message
from .filesystem import format_bytes, get_default_download_directory


class QueueManager:
    """
    Thread-safe Queue Manager governing media download tasks.
    """
    def __init__(self, max_concurrency: int = 3, cookies_browser: Optional[str] = None,
                 cookies_file: Optional[str] = None):
        self.max_concurrency = max_concurrency
        self.cookies_browser = cookies_browser
        self.cookies_file = cookies_file
        self.jobs: Dict[str, DownloadJob] = {}
        self.lock = threading.Lock()
        self.cancel_events: Dict[str, threading.Event] = {}
        self.executor = ThreadPoolExecutor(max_workers=max_concurrency, thread_name_prefix="omnistream_worker")
        self.listeners: List[Callable[[DownloadJob], None]] = []

    def set_concurrency(self, max_concurrency: int):
        with self.lock:
            self.max_concurrency = max_concurrency

    def set_cookies(self, cookies_browser: Optional[str] = None,
                    cookies_file: Optional[str] = None):
        """Updates the cookie sources used by subsequently started jobs."""
        with self.lock:
            self.cookies_browser = cookies_browser
            self.cookies_file = cookies_file

    def add_listener(self, callback: Callable[[DownloadJob], None]):
        self.listeners.append(callback)

    def _notify(self, job: DownloadJob):
        for callback in self.listeners:
            try:
                callback(job)
            except Exception:
                pass

    def add_job(
        self,
        url: str,
        title: str = "Media Download",
        media_type: str = "Video",
        quality_key: str = "Best Available",
        audio_codec: str = "MP3",
        audio_quality: str = "192 kbps",
        output_dir: Optional[str] = None,
        options: Optional[AdvancedOptions] = None,
        thumbnail: Optional[str] = None,
        platform: str = "Web"
    ) -> DownloadJob:
        output_dir = output_dir or get_default_download_directory()

        job = DownloadJob(
            url=url,
            title=title,
            media_type=media_type,
            quality_key=quality_key,
            audio_codec=audio_codec,
            audio_quality=audio_quality,
            output_dir=output_dir,
            status=JobStatus.QUEUED,
            thumbnail=thumbnail,
            platform=platform,
            options=options or AdvancedOptions(),
        )

        with self.lock:
            self.jobs[job.job_id] = job
            self.cancel_events[job.job_id] = threading.Event()

        self._notify(job)
        self.executor.submit(self._run_job, job)
        return job

    def enqueue_metadata(
        self,
        meta: MediaMetadata,
        media_type: str = "Video",
        quality_key: str = "Best Available",
        audio_codec: str = "MP3",
        audio_quality: str = "192 kbps",
        output_dir: Optional[str] = None,
        options: Optional[AdvancedOptions] = None,
        limit: Optional[int] = None,
    ) -> List[DownloadJob]:
        """
        Enqueues one job per video.

        Channel, Shorts-tab and playlist links expand into every selected entry,
        each producing its own single merged file with independent progress,
        retry and cancel handling.
        """
        output_dir = output_dir or get_default_download_directory()

        entries = [p for p in (meta.playlist_items or []) if getattr(p, "selected", True)]

        if not entries:
            return [self.add_job(
                url=meta.url,
                title=meta.title,
                media_type=media_type,
                quality_key=quality_key,
                audio_codec=audio_codec,
                audio_quality=audio_quality,
                output_dir=output_dir,
                options=options,
                thumbnail=meta.thumbnail,
                platform=meta.platform,
            )]

        if limit and limit > 0:
            entries = entries[:limit]

        return [
            self.add_job(
                url=entry.url,
                title=entry.title,
                media_type=media_type,
                quality_key=quality_key,
                audio_codec=audio_codec,
                audio_quality=audio_quality,
                output_dir=output_dir,
                options=options,
                thumbnail=entry.thumbnail or meta.thumbnail,
                platform=meta.platform,
            )
            for entry in entries
        ]

    def _run_job(self, job: DownloadJob):
        with self.lock:
            job.status = JobStatus.DOWNLOADING

        self._notify(job)
        cancel_evt = self.cancel_events.get(job.job_id)

        def progress_hook(d):
            if d.get('status') == 'downloading':
                with self.lock:
                    job.status = JobStatus.DOWNLOADING
                    p_str = d.get('_percent_str', '0%').strip()
                    job.percent_str = p_str
                    try:
                        job.progress = float(p_str.replace('%', '')) / 100.0
                    except Exception:
                        pass
                    job.speed_str = d.get('_speed_str', 'N/A')
                    job.eta_str = d.get('_eta_str', 'N/A')
                    job.downloaded_bytes = d.get('downloaded_bytes', 0) or 0
                    job.total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate')
                self._notify(job)
            elif d.get('status') == 'finished':
                with self.lock:
                    job.status = JobStatus.PROCESSING
                    job.progress = 1.0
                    job.percent_str = "100%"
                self._notify(job)

        try:
            success, result = download_media(
                url=job.url,
                media_type=job.media_type,
                quality_key=job.quality_key,
                output_dir=job.output_dir,
                audio_codec=job.audio_codec,
                audio_quality=job.audio_quality,
                options=job.options,
                cookies_browser=self.cookies_browser,
                cookies_file=self.cookies_file,
                progress_callback=progress_hook,
                cancel_event=cancel_evt,
            )

            with self.lock:
                if cancel_evt and cancel_evt.is_set():
                    job.status = JobStatus.CANCELLED
                elif success:
                    job.status = JobStatus.COMPLETED
                    job.result_file = result
                    job.finished_at = time.time()
                    size_str = format_bytes(job.downloaded_bytes or (job.total_bytes if job.total_bytes else None))
                    add_history_record(
                        url=job.url,
                        title=job.title,
                        platform=job.platform,
                        format_type=job.media_type,
                        resolution=job.quality_key,
                        size_str=size_str,
                        file_path=result,
                        thumbnail=job.thumbnail,
                        status="Completed",
                    )
                else:
                    job.status = JobStatus.FAILED
                    job.error_info = map_exception_to_user_message(Exception(result))
                    job.finished_at = time.time()

        except Exception as e:
            with self.lock:
                job.status = JobStatus.FAILED
                job.error_info = map_exception_to_user_message(e)
                job.finished_at = time.time()

        self._notify(job)

    def cancel_job(self, job_id: str) -> bool:
        with self.lock:
            if job_id in self.cancel_events:
                self.cancel_events[job_id].set()
            job = self.jobs.get(job_id)
            if job and job.status in (JobStatus.QUEUED, JobStatus.DOWNLOADING, JobStatus.PROCESSING):
                job.status = JobStatus.CANCELLED
                self._notify(job)
                return True
        return False

    def retry_job(self, job_id: str) -> bool:
        with self.lock:
            job = self.jobs.get(job_id)
            if not job:
                return False
            job.status = JobStatus.QUEUED
            job.progress = 0.0
            job.percent_str = "0%"
            job.error_info = None
            self.cancel_events[job_id] = threading.Event()

        self._notify(job)
        self.executor.submit(self._run_job, job)
        return True

    def remove_job(self, job_id: str) -> bool:
        with self.lock:
            if job_id in self.jobs:
                self.cancel_job(job_id)
                del self.jobs[job_id]
                if job_id in self.cancel_events:
                    del self.cancel_events[job_id]
                return True
        return False

    def get_all_jobs(self) -> List[DownloadJob]:
        with self.lock:
            return list(self.jobs.values())

    def clear_completed(self):
        with self.lock:
            completed_ids = [jid for jid, j in self.jobs.items() if j.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED)]
            for jid in completed_ids:
                del self.jobs[jid]
                if jid in self.cancel_events:
                    del self.cancel_events[jid]
