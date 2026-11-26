"""Choosing the TMDb match by the disc's running time."""
from import2flex import metadata, pipeline
from import2flex.config import Config

FOREST = {"id": 1, "title": "The Forest", "release_date": "2016-01-07"}
GUMP = {"id": 2, "title": "Forrest Gump", "release_date": "1994-06-23"}
RUNTIMES = {1: 93, 2: 142}


def runtime_of(result):
    return RUNTIMES.get(result["id"], 0)


def test_first_hit_when_the_length_fits():
    m = metadata.pick([FOREST, GUMP], "Forest", 94, runtime_of)
    assert (m.title, m.year, m.doubt) == ("The Forest", "2016", "")


def test_later_hit_wins_when_it_is_as_long_as_the_disc():
    m = metadata.pick([FOREST, GUMP], "Forest", 142, runtime_of)
    assert (m.title, m.year, m.doubt) == ("Forrest Gump", "1994", "")


def test_wrong_length_is_doubted():
    # What happened: label FOREST on a Forrest Gump disc, TMDb only offers The Forest.
    m = metadata.pick([FOREST], "Forest", 142, runtime_of)
    assert m.title == "The Forest"
    assert "142 min" in m.doubt and "93 min" in m.doubt


def test_small_differences_and_unknown_lengths_are_trusted():
    assert metadata.pick([GUMP], "Forrest Gump", 136, runtime_of).doubt == ""   # PAL
    assert metadata.pick([FOREST], "Forest", 100, runtime_of).doubt == ""       # 8 % off
    assert metadata.pick([FOREST], "Forest", 0, runtime_of).doubt == ""         # disc unknown
    assert metadata.pick([{"id": 9, "title": "X"}], "X", 142, runtime_of).doubt == ""
    assert metadata.pick([], "X", 142, runtime_of) is None


def test_guess_name_tries_the_disc_name_when_the_label_is_doubted(monkeypatch):
    def lookup(query, key, disc_minutes=0, timeout=10):
        if query == "Forest":
            return metadata.pick([FOREST], query, disc_minutes, runtime_of)
        if query == "Forrest Gump":
            return metadata.pick([GUMP], query, disc_minutes, runtime_of)
        return None

    monkeypatch.setattr(metadata, "lookup_movie", lookup)
    cfg = Config(tmdb_api_key="k")
    assert pipeline.guess_name("FOREST", "Forrest Gump", cfg, 142) == ("Forrest Gump (1994)", "")
    name, doubt = pipeline.guess_name("FOREST", "FOREST", cfg, 142)
    assert name == "The Forest (2016)" and doubt
    assert pipeline.guess_name("FOREST", "", cfg, 93) == ("The Forest (2016)", "")
    assert pipeline.guess_name("FOREST", "", Config(tmdb_api_key=""), 142) == ("Forest", "")
