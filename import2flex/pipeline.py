"""The import engine: watches drives, rips, (re-encodes), files into Plex, cleans up.

Two worker threads form a pipeline so the drive is free for the next disc
while the previous movie is still being re-encoded:

    disc / ISO --> [rip thread: MakeMKV] --> [finish thread: HandBrake, move, cleanup]
"""
from __future__ import annotations

import itertools
import logging
import queue
import shutil
import threading
import time
from concurrent.futures import Future
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Protocol

from . import drives, handbrake, metadata, naming, plex
from .config import Config
from .makemkv import MakeMKV
from .process import Cancelled

log = logging.getLogger(__name__)

DISC_POLL_SECONDS = 3
ISO_POLL_SECONDS = 15


class Status:
    QUEUED = "Queued"
    READING = "Reading disc"
    RIPPING = "Ripping"
    WAITING = "Waiting to encode"
    ENCODING = "Encoding"
    MOVING = "Moving to library"
    DONE = "Done"
    FAILED = "Failed"
    CANCELLED = "Cancelled"

    FINISHED = {DONE, FAILED, CANCELLED}


@dataclass
class Job:
    id: int
    kind: str                         # "disc" or "iso"
    label: str                        # disc label or ISO file name
    drive: str = ""
    iso_path: Path | None = None
    disc_key: tuple | None = None
    status: str = Status.QUEUED
    detail: str = ""
    progress: float = 0.0
    name: str = ""                    # final "Title (Year)"
    name_doubt: str = ""              # why the guessed name may be wrong
    dest: Path | None = None
    error: str = ""
    started: datetime = field(default_factory=datetime.now)
    cancel: threading.Event = field(default_factory=threading.Event)
    name_future: Future | None = None
    work_dir: Path | None = None
    ripped: list[Path] = field(default_factory=list)

    @property
    def source(self) -> str:
        return f"{self.drive} {self.label}".strip() if self.kind == "disc" else str(self.iso_path)

    @property
    def finished(self) -> bool:
        return self.status in Status.FINISHED


class EngineEvents(Protocol):
    def job_changed(self, job: Job) -> None: ...
    def notify(self, title: str, message: str, error: bool = False) -> None: ...
    # timeout 0: wait for an answer (the guess is in doubt, see job.name_doubt)
    def ask_name(self, job: Job, guess: str, timeout: int) -> str | None: ...
    def drives_changed(self, state: dict[str, drives.Disc | None]) -> None: ...


def guess_name(label: str, disc_name: str, cfg: Config,
               disc_minutes: int = 0) -> tuple[str, str]:
    """Best guess at ``Title (Year)`` from the disc label / MakeMKV disc name,
    and why it may be wrong ("" when there is no reason to think so).

    ``disc_minutes`` is the length of the main title: a TMDb match that runs
    much longer or shorter is another movie (label ``FOREST`` on a Forrest
    Gump disc finds The Forest).
    """
    titles = []
    for c in (label, disc_name):
        if c and not naming.is_generic_label(c):
            title = naming.clean_label(c)
            if title and title not in titles:
                titles.append(title)
    if not titles:
        return f"Unknown Disc {datetime.now():%Y-%m-%d %H%M}", ""
    if not cfg.tmdb_api_key:
        return naming.plex_name(titles[0]), ""
    doubted = None
    for title in titles:
        found = metadata.lookup_movie(title, cfg.tmdb_api_key, disc_minutes)
        if found and not found.doubt:
            return naming.plex_name(found.title, found.year), ""
        doubted = doubted or found
    if doubted:
        return naming.plex_name(doubted.title, doubted.year), doubted.doubt
    return naming.plex_name(titles[0]), ""


class Engine:
    def __init__(self, cfg: Config, events: EngineEvents):
        self.cfg = cfg
        self.events = events
        self.jobs: list[Job] = []
        self._ids = itertools.count(1)
        self._lock = threading.Lock()
        self._rip_q: queue.Queue[Job | None] = queue.Queue()
        self._finish_q: queue.Queue[Job | None] = queue.Queue()
        self._stop = threading.Event()
        self.paused = False
        # drive -> key of the disc we already handled (so we don't re-rip it)
        self._handled: dict[str, tuple] = {}
        self._drive_state: dict[str, drives.Disc | None] = {}
        self._iso_sizes: dict[Path, int] = {}
        self._iso_handled: set[Path] = set()
        self._threads: list[threading.Thread] = []

    # ---------------------------------------------------------------- control
    def start(self) -> None:
        for target, name in ((self._monitor_loop, "monitor"), (self._rip_loop, "rip"),
                             (self._finish_loop, "finish")):
            t = threading.Thread(target=target, name=name, daemon=True)
            t.start()
            self._threads.append(t)
        log.info("Engine started")

    def stop(self) -> None:
        self._stop.set()
        with self._lock:
            for job in self.jobs:
                if not job.finished:
                    job.cancel.set()
        self._rip_q.put(None)
        self._finish_q.put(None)

    def set_paused(self, paused: bool) -> None:
        self.paused = paused
        log.info("Auto-import %s", "paused" if paused else "resumed")

    def busy(self) -> bool:
        with self._lock:
            return any(not j.finished for j in self.jobs)

    def cancel_job(self, job_id: int) -> None:
        with self._lock:
            for job in self.jobs:
                if job.id == job_id and not job.finished:
                    job.cancel.set()
                    log.info("Cancel requested for job %d", job_id)

    def clear_finished(self) -> None:
        with self._lock:
            self.jobs = [j for j in self.jobs if not j.finished]

    def rip_drive_now(self, drive: str) -> bool:
        """Manually queue the disc in ``drive`` (ignores the auto/paused setting)."""
        disc = drives.disc_in(drive)
        if disc is None:
            self.events.notify("No disc", f"There is no readable disc in {drive}.", error=True)
            return False
        if self._drive_busy(drive):
            self.events.notify("Busy", f"{drive} is already being imported.", error=True)
            return False
        self._queue_disc(disc)
        return True

    def queue_iso(self, path: Path) -> None:
        path = Path(path)
        self._iso_handled.add(path)
        job = Job(id=next(self._ids), kind="iso", label=path.stem, iso_path=path)
        self._add(job)

    def eject(self, drive: str) -> None:
        if not drives.eject(drive):
            log.warning("Could not eject %s", drive)

    # ---------------------------------------------------------------- helpers
    def _add(self, job: Job) -> None:
        with self._lock:
            self.jobs.append(job)
        log.info("Queued job %d: %s", job.id, job.source)
        self._changed(job)
        self._rip_q.put(job)

    def _changed(self, job: Job) -> None:
        try:
            self.events.job_changed(job)
        except Exception:  # never let a GUI hiccup kill a rip
            log.exception("job_changed handler failed")

    def _set(self, job: Job, status: str | None = None, detail: str | None = None,
             progress: float | None = None) -> None:
        changed = False
        if status is not None and status != job.status:
            job.status, changed = status, True
        if detail is not None and detail != job.detail:
            job.detail, changed = detail, True
        if progress is not None and abs(progress - job.progress) >= 0.002:
            job.progress, changed = progress, True
        if changed:
            self._changed(job)

    def _drive_busy(self, drive: str) -> bool:
        with self._lock:
            return any(j.drive == drive and j.status in (Status.QUEUED, Status.READING, Status.RIPPING)
                       for j in self.jobs)

    def _queue_disc(self, disc: drives.Disc) -> None:
        self._handled[disc.drive] = disc.key
        self._add(Job(id=next(self._ids), kind="disc", label=disc.label,
                      drive=disc.drive, disc_key=disc.key))

    def _check_cancel(self, job: Job) -> None:
        if job.cancel.is_set():
            raise Cancelled()

    # ---------------------------------------------------------------- monitor
    def _monitor_loop(self) -> None:
        last_iso = 0.0
        while not self._stop.is_set():
            try:
                self._poll_drives()
                if time.monotonic() - last_iso >= ISO_POLL_SECONDS:
                    last_iso = time.monotonic()
                    self._poll_iso_folder()
            except Exception:
                log.exception("Monitor error")
            self._stop.wait(DISC_POLL_SECONDS)

    def _poll_drives(self) -> None:
        state = {d: drives.disc_in(d) for d in drives.optical_drives()}
        if state != self._drive_state:
            self._drive_state = state
            self.events.drives_changed(dict(state))
        for drive, disc in state.items():
            if disc is None:
                self._handled.pop(drive, None)   # tray empty -> forget old disc
                continue
            if self._handled.get(drive) == disc.key:
                continue
            if not disc.is_video:
                self._handled[drive] = disc.key
                log.info("Ignoring non-video disc %r in %s", disc.label, drive)
                continue
            if self.paused or not self.cfg.auto_rip or self._drive_busy(drive):
                continue
            log.info("Detected %s %r in %s", disc.kind.upper(), disc.label, drive)
            self._queue_disc(disc)

    def _poll_iso_folder(self) -> None:
        if not (self.cfg.iso_watch_enabled and self.cfg.iso_watch_dir) or self.paused:
            return
        folder = Path(self.cfg.iso_watch_dir)
        if not folder.is_dir():
            return
        for iso in folder.glob("*.iso"):
            if iso in self._iso_handled:
                continue
            try:
                size = iso.stat().st_size
            except OSError:
                continue
            # Only pick it up once the size has stopped changing (copy finished).
            if self._iso_sizes.get(iso) == size and size > 0:
                self._iso_sizes.pop(iso, None)
                log.info("Found ISO %s", iso)
                self.queue_iso(iso)
            else:
                self._iso_sizes[iso] = size

    # ---------------------------------------------------------------- rip stage
    def _rip_loop(self) -> None:
        while True:
            job = self._rip_q.get()
            if job is None:
                return
            if job.cancel.is_set():
                self._set(job, Status.CANCELLED, "")
                continue
            try:
                self._rip(job)
            except Cancelled:
                self._fail(job, cancelled=True)
            except Exception as exc:
                log.exception("Job %d rip failed", job.id)
                self._fail(job, error=str(exc))
            else:
                self._set(job, Status.WAITING if self.cfg.transcode else Status.MOVING, "", 0)
                self._finish_q.put(job)

    def _rip(self, job: Job) -> None:
        cfg = self.cfg
        mk = MakeMKV(cfg.makemkv_path, cfg.min_title_seconds)
        self._set(job, Status.READING, "Scanning titles…", 0)
        if job.kind == "disc":
            source = mk.source_for_drive(job.drive, job.cancel)
        else:
            source = f"iso:{job.iso_path}"
        info = mk.info(source, job.cancel)
        self._check_cancel(job)

        main = info.main_title()
        guess, job.name_doubt = guess_name(job.label, info.name, cfg, main.duration // 60)
        job.name = guess
        self._changed(job)
        if job.name_doubt:
            log.warning("Job %d: not sure about the name %r: %s", job.id, guess, job.name_doubt)
            self.events.notify("Check the movie name",
                               f"{job.source}: is it {guess}? ({job.name_doubt})")
        job.name_future = self._start_name_prompt(job, guess)

        if cfg.rip_mode == "all":
            title_arg: int | str = "all"
            needed = sum(t.size_bytes for t in info.titles)
        else:
            title_arg = main.index
            needed = main.size_bytes
            log.info("Main title #%d (%d min) of %d", main.index, main.duration // 60, len(info.titles))

        work_root = Path(cfg.work_dir)
        work_root.mkdir(parents=True, exist_ok=True)
        free = shutil.disk_usage(work_root).free
        if needed and free < needed * 1.1:
            raise RuntimeError(f"Not enough free space in {work_root}: need "
                               f"{needed / 1e9:.1f} GB, have {free / 1e9:.1f} GB")

        job.work_dir = work_root / f"job{job.id:04d}-{naming.safe_filename(job.label)[:40]}"
        self._set(job, Status.RIPPING, "Starting MakeMKV…", 0)
        job.ripped = mk.rip(
            source, title_arg, job.work_dir,
            on_progress=lambda f: self._set(job, progress=f),
            on_status=lambda s: self._set(job, detail=s),
            cancel=job.cancel,
        )
        log.info("Job %d ripped %d file(s)", job.id, len(job.ripped))
        if job.kind == "disc" and cfg.eject_when_done:
            self.eject(job.drive)

    def _start_name_prompt(self, job: Job, guess: str) -> Future:
        # Asked when the setting says so, and always when the guess is in
        # doubt: then without the countdown that would accept it.
        fut: Future = Future()
        if not self.cfg.confirm_name and not job.name_doubt:
            fut.set_result(guess)
            return fut
        timeout = 0 if job.name_doubt else self.cfg.confirm_timeout_sec

        def ask() -> None:
            try:
                answer = self.events.ask_name(job, guess, timeout)
            except Exception:
                log.exception("Name prompt failed")
                answer = None
            fut.set_result((answer or "").strip() or guess)

        threading.Thread(target=ask, name=f"ask-{job.id}", daemon=True).start()
        return fut

    # ---------------------------------------------------------------- finish stage
    def _finish_loop(self) -> None:
        while True:
            job = self._finish_q.get()
            if job is None:
                return
            try:
                self._check_cancel(job)
                self._finish(job)
            except Cancelled:
                self._fail(job, cancelled=True)
            except Exception as exc:
                log.exception("Job %d finish failed", job.id)
                self._fail(job, error=str(exc))

    def _finish(self, job: Job) -> None:
        cfg = self.cfg
        files = sorted(job.ripped, key=lambda p: p.stat().st_size, reverse=True)

        if cfg.transcode:
            encoded = []
            for i, src in enumerate(files):
                self._set(job, Status.ENCODING, f"File {i + 1} of {len(files)}", 0)
                dst = src.with_name(f"{src.stem}.encoded.mkv")
                handbrake.transcode(
                    cfg.handbrake_path, src, dst, cfg.handbrake_preset, cfg.handbrake_extra_args,
                    on_progress=lambda f, i=i: self._set(job, progress=(i + f) / len(files)),
                    cancel=job.cancel,
                )
                src.unlink(missing_ok=True)       # raw rip no longer needed
                encoded.append(dst)
            files = encoded

        self._set(job, Status.MOVING, "Waiting for movie name…" if cfg.confirm_name or job.name_doubt else "", 1)
        try:
            name = job.name_future.result(timeout=3600) if job.name_future else job.name
        except Exception:
            name = job.name
        name = naming.safe_filename(name)
        job.name = name
        self._set(job, detail="Copying…")

        main_dest = naming.library_destination(cfg.movies_dir, name)
        main_dest.parent.mkdir(parents=True, exist_ok=True)
        _move(files[0], main_dest)
        for extra in files[1:]:
            stem = extra.stem.replace(".encoded", "")
            dest = naming.unique_path(main_dest.parent / "Other" / f"{stem}.mkv")
            dest.parent.mkdir(parents=True, exist_ok=True)
            _move(extra, dest)
        job.dest = main_dest
        log.info("Job %d -> %s", job.id, main_dest)

        self._cleanup(job)
        if job.kind == "iso" and cfg.delete_iso_after and job.iso_path:
            try:
                job.iso_path.unlink()
                log.info("Deleted ISO %s", job.iso_path)
            except OSError as exc:
                log.warning("Could not delete ISO %s: %s", job.iso_path, exc)

        plex.refresh_library(cfg.plex_url, cfg.plex_token, cfg.plex_section_id)
        self._set(job, Status.DONE, str(main_dest), 1)
        self.events.notify("Movie imported", f"{name} was added to your library.")

    def _cleanup(self, job: Job) -> None:
        if job.work_dir and job.work_dir.exists():
            shutil.rmtree(job.work_dir, ignore_errors=True)
            log.info("Removed temporary files in %s", job.work_dir)

    def _fail(self, job: Job, error: str = "", cancelled: bool = False) -> None:
        self._cleanup(job)
        job.error = error
        if cancelled:
            self._set(job, Status.CANCELLED, "")
        else:
            self._set(job, Status.FAILED, error)
            self.events.notify("Import failed", f"{job.name or job.label}: {error}", error=True)
        if job.kind == "disc" and self.cfg.eject_when_done and not cancelled:
            self.eject(job.drive)


def _move(src: Path, dst: Path) -> None:
    """Move a (possibly huge) file, across drives if needed."""
    shutil.move(str(src), str(dst))
