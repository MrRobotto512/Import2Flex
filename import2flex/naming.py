"""Turn disc labels like ``THE_MATRIX_WS`` into Plex-friendly names."""
from __future__ import annotations

import re
from pathlib import Path

# Labels that tell us nothing about the movie.
GENERIC_LABELS = {
    "", "DVD", "DVDVIDEO", "DVD_VIDEO", "DVDVOLUME", "DVD_VOLUME", "VIDEO_TS",
    "BDMV", "BLURAY", "BLU_RAY", "BD_ROM", "BDROM", "DISC", "DISC1", "VOLUME",
    "NEW", "MOVIE", "LOGICAL_VOLUME_ID", "CDROM", "UNTITLED", "NO_LABEL",
}

# Trailing tokens studios tack onto volume labels.
NOISE_TOKENS = {
    "WS", "FS", "WIDESCREEN", "FULLSCREEN", "FULL", "SCREEN", "NTSC", "PAL",
    "R1", "R2", "R3", "R4", "16X9", "4X3", "169", "43", "DVD", "BD", "BLURAY",
    "BLU", "RAY", "UHD", "4K", "HD", "SE", "CE", "DE", "LE", "UE", "AE",
    "DISC", "DISK", "D1", "D2", "D3", "D4", "DISC1", "DISC2", "DISC3",
    "SIDE", "A", "B", "US", "UK", "EU", "CAN", "MAIN", "FEATURE", "TITLE",
    "SPECIAL", "EDITION", "COLLECTORS", "ANNIV", "ANNIVERSARY", "RETAIL",
}

SMALL_WORDS = {
    "a", "an", "and", "as", "at", "but", "by", "for", "from", "in", "into",
    "nor", "of", "on", "or", "the", "to", "vs", "with",
}

ROMAN = re.compile(r"^(?=[MDCLXVI])M*(C[MD]|D?C{0,3})(X[CL]|L?X{0,3})(I[XV]|V?I{0,3})$")


def is_generic_label(label: str) -> bool:
    return re.sub(r"[^A-Z0-9_]", "", (label or "").upper()) in GENERIC_LABELS


def clean_label(label: str) -> str:
    """``THE_LORD_OF_THE_RINGS_WS_D1`` -> ``The Lord of the Rings``."""
    text = (label or "").strip()
    if not text:
        return ""
    # Split CamelCase only when the label is mixed case (e.g. "TheMatrix").
    if not text.isupper() and not text.islower():
        text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)
    tokens = [t for t in re.split(r"[\s_.\-]+", text) if t]

    # Drop noise tokens from the end (keep at least one word).
    while len(tokens) > 1 and tokens[-1].upper() in NOISE_TOKENS:
        tokens.pop()
    # A trailing year-ish token gets dropped too; TMDb lookup can restore it.
    if len(tokens) > 1 and re.fullmatch(r"(19|20)\d\d", tokens[-1]):
        tokens.pop()

    words = []
    for i, tok in enumerate(tokens):
        upper = tok.upper()
        if ROMAN.match(upper) and len(upper) <= 4 and i > 0:
            words.append(upper)            # Rocky II, Part III
        elif i > 0 and tok.lower() in SMALL_WORDS:
            words.append(tok.lower())
        elif tok.isdigit():
            words.append(tok)
        else:
            words.append(tok[:1].upper() + tok[1:].lower())
    return " ".join(words)


_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
             *(f"LPT{i}" for i in range(1, 10))}


def safe_filename(name: str) -> str:
    """Make ``name`` legal as a Windows file/folder name."""
    name = name.replace(":", " -")
    name = _ILLEGAL.sub("", name)
    name = re.sub(r"\s+", " ", name).strip().rstrip(". ")
    if name.upper() in _RESERVED:
        name = f"_{name}"
    return name[:150] or "Untitled"


def plex_name(title: str, year: str | int | None = None) -> str:
    """``Plex`` naming: ``Movie Title (Year)``."""
    title = safe_filename(title)
    year = str(year or "").strip()
    return f"{title} ({year})" if re.fullmatch(r"\d{4}", year) else title


def library_destination(movies_dir: str | Path, name: str, suffix: str = "",
                        ext: str = ".mkv") -> Path:
    """Return ``movies_dir/Name/Name<suffix>.mkv``, avoiding overwrites."""
    return unique_path(Path(movies_dir) / name / f"{name}{suffix}{ext}")


def unique_path(path: Path) -> Path:
    """``path`` if free, else ``name - copy 2.ext``, ``name - copy 3.ext``, …"""
    dest, n = path, 2
    while dest.exists():
        dest = path.with_name(f"{path.stem} - copy {n}{path.suffix}")
        n += 1
    return dest
