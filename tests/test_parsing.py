from pathlib import Path

from import2flex import handbrake, makemkv, naming
from import2flex.config import Config

INFO_OUTPUT = """\
MSG:1005,0,1,"MakeMKV v1.17.7 win(x64-release) started","%1 started","MakeMKV v1.17.7 win(x64-release)"
DRV:0,2,999,1,"HL-DT-ST DVDRAM GH24NSD1","THE_MATRIX","D:"
DRV:1,256,999,0,"","",""
TCOUNT:3
CINFO:1,6209,"DVD disc"
CINFO:2,0,"The Matrix"
TINFO:0,2,0,"The Matrix"
TINFO:0,8,0,"39"
TINFO:0,9,0,"2:16:17"
TINFO:0,11,0,"7314231296"
TINFO:0,27,0,"The_Matrix_t00.mkv"
TINFO:1,9,0,"0:24:10"
TINFO:1,11,0,"1200000000"
TINFO:2,9,0,"2:16:17"
TINFO:2,11,0,"7000000000"
"""


def test_parse_info_and_main_title():
    info = makemkv.parse_info(INFO_OUTPUT.splitlines())
    assert info.name == "The Matrix"
    assert [t.index for t in info.titles] == [0, 1, 2]
    main = info.main_title()
    assert main.index == 0
    assert main.duration == 2 * 3600 + 16 * 60 + 17
    assert main.chapters == 39
    assert main.output_file == "The_Matrix_t00.mkv"


def test_parse_drives():
    drives = makemkv.parse_drives(INFO_OUTPUT.splitlines())
    assert len(drives) == 1
    d = drives[0]
    assert (d.index, d.has_disc, d.disc_name, d.device) == (0, True, "THE_MATRIX", "D:")


def test_progress_and_messages():
    assert makemkv.parse_progress("PRGV:100,32768,65536") == 0.5
    assert makemkv.parse_progress("MSG:1,2,3") is None
    assert makemkv.parse_message('MSG:5011,0,0,"Operation successfully completed","x"') == \
        "Operation successfully completed"


def test_handbrake_progress():
    line = "Encoding: task 1 of 1, 42.50 % (95.12 fps, avg 97.00 fps, ETA 00h05m01s)"
    assert abs(handbrake.parse_progress(line) - 0.425) < 1e-9
    assert abs(handbrake.parse_progress("Encoding: task 2 of 2, 50.00 %") - 0.75) < 1e-9
    assert handbrake.parse_progress("x264 [info]: profile High") is None


def test_clean_label():
    assert naming.clean_label("THE_MATRIX") == "The Matrix"
    assert naming.clean_label("THE_LORD_OF_THE_RINGS_WS_D1") == "The Lord of the Rings"
    assert naming.clean_label("ROCKY_II") == "Rocky II"
    assert naming.clean_label("SHREK_2_FS") == "Shrek 2"
    assert naming.clean_label("FindingNemo") == "Finding Nemo"
    assert naming.clean_label("ALIEN_1979") == "Alien"


def test_generic_labels():
    assert naming.is_generic_label("DVD_VIDEO")
    assert naming.is_generic_label("")
    assert not naming.is_generic_label("JAWS")


def test_safe_names_and_destination(tmp_path: Path):
    assert naming.safe_filename('Star Wars: Episode IV? "A New Hope"') == \
        "Star Wars - Episode IV A New Hope"
    assert naming.safe_filename("CON") == "_CON"
    assert naming.plex_name("Jaws", "1975") == "Jaws (1975)"
    assert naming.plex_name("Jaws", "") == "Jaws"
    first = naming.library_destination(tmp_path, "Jaws (1975)")
    assert first == tmp_path / "Jaws (1975)" / "Jaws (1975).mkv"
    first.parent.mkdir()
    first.write_bytes(b"x")
    assert naming.library_destination(tmp_path, "Jaws (1975)").name == "Jaws (1975) - copy 2.mkv"


def test_config_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "path", classmethod(lambda cls: tmp_path / "config.json"))
    cfg = Config(movies_dir="M:/Movies", transcode=True, min_title_seconds=900)
    cfg.save()
    loaded = Config.load()
    assert loaded.movies_dir == "M:/Movies" and loaded.transcode and loaded.min_title_seconds == 900
