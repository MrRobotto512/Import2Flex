"""End-to-end pipeline test with fake makemkvcon / HandBrakeCLI programs."""
import stat
import sys
import threading
import time
from pathlib import Path

import pytest

from import2flex.config import Config
from import2flex.pipeline import Engine, Status

FAKE_MAKEMKV = r'''
import sys, pathlib
args = sys.argv[1:]
if "info" in args:
    print('DRV:0,2,999,1,"Fake drive","MOVIE","D:"')
    print('CINFO:2,0,"Big Movie"')
    print('TINFO:0,9,0,"1:50:00"')
    print('TINFO:0,11,0,"1000"')
    print('TINFO:1,9,0,"0:25:00"')
    print('TINFO:1,11,0,"100"')
    sys.exit(0)
i = args.index("mkv")
title, out = args[i + 2], pathlib.Path(args[i + 3])
for p in range(0, 65537, 16384):
    print(f"PRGV:{p},{p},65536", flush=True)
names = ["title_t00.mkv", "title_t01.mkv"] if title == "all" else [f"title_t0{title}.mkv"]
for n, name in enumerate(names):
    (out / name).write_bytes(b"x" * (2000 - n * 1000))
print('MSG:5005,0,1,"1 titles saved"')
'''

FAKE_HANDBRAKE = r'''
import sys, shutil
args = sys.argv[1:]
src, dst = args[args.index("-i") + 1], args[args.index("-o") + 1]
for pct in (10, 50, 99.9):
    sys.stdout.write(f"Encoding: task 1 of 1, {pct:.2f} %\r"); sys.stdout.flush()
shutil.copy(src, dst)
'''


def _script(path: Path, body: str) -> str:
    path.write_text(f"#!{sys.executable}\n{body}")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return str(path)


class Events:
    def __init__(self):
        self.notes = []
        self.done = threading.Event()

    def job_changed(self, job):
        if job.finished:
            self.done.set()

    def notify(self, title, message, error=False):
        self.notes.append((title, message, error))

    def ask_name(self, job, guess, timeout):
        return "Custom Name (2001)"

    def drives_changed(self, state):
        pass


@pytest.mark.skipif(sys.platform == "win32", reason="fake tools are shebang scripts")
@pytest.mark.parametrize("transcode,rip_mode,confirm", [
    (False, "main", False), (True, "main", False), (True, "all", True)])
def test_iso_import(tmp_path, transcode, rip_mode, confirm):
    iso_dir = tmp_path / "isos"
    iso_dir.mkdir()
    iso = iso_dir / "BIG_MOVIE_WS.iso"
    iso.write_bytes(b"iso")
    cfg = Config(
        movies_dir=str(tmp_path / "Movies"), work_dir=str(tmp_path / "work"),
        makemkv_path=_script(tmp_path / "makemkvcon", FAKE_MAKEMKV),
        handbrake_path=_script(tmp_path / "HandBrakeCLI", FAKE_HANDBRAKE),
        transcode=transcode, rip_mode=rip_mode, confirm_name=confirm,
        tmdb_api_key="", plex_token="",
    )
    events = Events()
    engine = Engine(cfg, events)
    engine.start()
    try:
        engine.queue_iso(iso)
        assert events.done.wait(20)
        time.sleep(0.1)
    finally:
        engine.stop()

    job = engine.jobs[0]
    assert job.status == Status.DONE, job.error
    name = "Custom Name (2001)" if confirm else "Big Movie"
    movie = tmp_path / "Movies" / name / f"{name}.mkv"
    assert movie.exists() and movie.stat().st_size == 2000
    if rip_mode == "all":
        assert (movie.parent / "Other" / "title_t01.mkv").exists()
    assert not iso.exists(), "ISO should be deleted after import"
    assert list((tmp_path / "work").iterdir()) == [], "temp files should be cleaned up"
    assert events.notes and events.notes[-1][0] == "Movie imported"


def test_failed_rip_keeps_iso(tmp_path):
    iso = tmp_path / "MOVIE.iso"
    iso.write_bytes(b"iso")
    cfg = Config(movies_dir=str(tmp_path / "Movies"), work_dir=str(tmp_path / "work"),
                 makemkv_path=str(tmp_path / "does-not-exist"))
    events = Events()
    engine = Engine(cfg, events)
    engine.start()
    try:
        engine.queue_iso(iso)
        assert events.done.wait(10)
    finally:
        engine.stop()
    assert engine.jobs[0].status == Status.FAILED
    assert "MakeMKV not found" in engine.jobs[0].error
    assert iso.exists()
