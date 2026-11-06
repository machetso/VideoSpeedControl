# Copyright (c) 2026 Alex Vulcu
#
# Concept, architecture, direction, and curation by Alex Vulcu.
# Implementation assisted by generative AI tools.
#
# Licensed under the MIT License.
# See the LICENSE file in the repository root for details.
"""Convert videos (user request 2026-11-03): re-encode many files with the same codec and
quality, nothing else changed – every frame once at the file's own frame rate, source size,
sound kept – into MP4. Meant for old collections (AVI / DivX / Xvid …) as well as phone clips.

Pro mode (user request 2026-11-04): `ConvertSettings` – frame rate, container (MP4 / MOV /
MKV), codec, quality level / own quality value / kbit/s, sound (copy, AAC, Opus, MP3, FLAC,
channels, kbit/s) – as general settings for every file, with own settings per file. "Smart"
(both modes, `core/suggest.py`): measured per file, the smallest file that keeps the picture
(VMAF) and the sound.

No Qt here: the GUI (`gui/convert_dialog.py`) probes the files, builds the jobs with
`make_job` / `make_pro_job` and runs them with `batch.Batch`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from fractions import Fraction
from pathlib import Path

from . import audio, batch, formats
from .job import Job, OutputSettings
from .probe import FrameMap, MediaInfo
from ..i18n import tr

# codecs offered (best default first); the GUI greys out the ones FFmpeg lacks
CODECS = ("svtav1", "aom", "x265", "x264")
DEFAULT_CODEC = "svtav1"            # user choice 2026-11-03: AV1 in MP4
DEFAULT_LEVEL = 1                   # index in formats.QUALITY_LEVELS: "High"
CONTAINER = "mp4"
CONTAINERS = ("mp4", "mov", "mkv")    # pro mode
FOLDER_NAME = "Converted"           # default: a sub-folder next to the originals

VIDEO_EXTENSIONS = frozenset({
    ".mp4", ".m4v", ".mov", ".mkv", ".webm", ".avi", ".divx", ".xvid", ".wmv", ".asf", ".flv",
    ".mpg", ".mpeg", ".mpe", ".m2v", ".vob", ".ts", ".mts", ".m2ts", ".mxf", ".3gp", ".3g2",
    ".ogv", ".dv", ".360", ".lrv",
})


def is_video(path: Path) -> bool:
    return path.suffix.lower() in VIDEO_EXTENSIONS


def _natural(path: Path):
    """Sort key: '2 - x' before '10 - x', case-insensitive."""
    return [int(t) if t.isdigit() else t.casefold() for t in re.split(r"(\d+)", str(path))]


def find_videos(paths, recursive: bool = True) -> list[Path]:
    """Video files among `paths`; folders are searched (with sub-folders if `recursive`).

    Files given directly are kept even with an unknown extension (the user chose them);
    files found in folders need a video extension. Hidden files / folders are skipped.
    Order: as given, each folder's content in natural order. No duplicates.
    """
    found: list[Path] = []
    seen: set[Path] = set()

    def add(p: Path) -> None:
        key = p.resolve()
        if key not in seen:
            seen.add(key)
            found.append(p)

    for p in map(Path, paths):
        if p.is_dir():
            pattern = p.rglob("*") if recursive else p.glob("*")
            inside = [f for f in pattern if f.is_file() and is_video(f)
                      and not any(part.startswith(".") for part in f.relative_to(p).parts)]
            for f in sorted(inside, key=_natural):
                add(f)
        elif p.is_file():
            add(p)
    return found


def clean_stem(path: Path) -> str:
    """File name without its video extensions: 'Clip.avi.MP4.AVI' → 'Clip' (renamed copies of
    old files often carry several). Never empty."""
    name = path.name
    while True:
        stem, dot, ext = name.rpartition(".")
        if not dot or not stem or f".{ext.lower()}" not in VIDEO_EXTENSIONS:
            break
        name = stem
    name = name.strip(" .")
    return name or path.stem


def quality_value(codec_key: str, level: int) -> int | None:
    """The codec's own quality number for level `level` (0 = best) – None = codec default."""
    codec = formats.CODECS_BY_KEY.get(codec_key)
    levels = formats.quality_levels(codec) if codec else []
    return levels[level][2] if 0 <= level < len(levels) else None


def make_job(info: MediaInfo, frames: FrameMap | None, codec_key: str, level: int = DEFAULT_LEVEL,
             sound: bool = True) -> Job:
    """Every frame once at the file's frame rate, source size, MP4 (speed None = lossless speed,
    so a phone slow-mo file keeps playing exactly as the file does)."""
    settings = OutputSettings(fps=info.fps, speed=None, codec=codec_key, container=CONTAINER,
                              quality=quality_value(codec_key, level), audio=sound)
    return Job(info, settings, frames=frames)


def output_folder(source: Path, folder: Path | None) -> Path:
    """`folder`, or the 'Converted' folder next to the source."""
    return folder if folder is not None else source.parent / FOLDER_NAME


def plan(jobs: list[tuple[Job, list[str] | None]], folder: Path | None,
         policy: str = batch.RENAME) -> list[batch.Item]:
    """Output file for every job: '<clean name>.mp4' in `folder` / the 'Converted' folder."""
    return batch.plan(jobs, None, "{name}", policy,
                      folders=[output_folder(j.info.path, folder) for j, _ in jobs],
                      names=[clean_stem(j.info.path) for j, _ in jobs])


# --------------------------------------------------------------------------- pro mode

RATE_MODES = ("level", "crf", "kbps", "smart")
AUDIO_MODES = ("default", "smart", "copy", "aac", "opus", "mp3", "flac", "none")
GOALS = ("identical", "smaller")


@dataclass
class ConvertSettings:
    """What a conversion does. Easy mode uses codec, level, `rate` "level" / "smart", `goal` and
    `audio` "default" / "smart" / "none"; pro mode everything. None = like the source."""
    codec: str = DEFAULT_CODEC
    container: str = CONTAINER
    fps: Fraction | None = None          # None = the file's own rate
    rate: str = "level"                  # "level" | "crf" (own value) | "kbps" | "smart"
    level: int = DEFAULT_LEVEL           # index in formats.QUALITY_LEVELS
    crf: int | None = None               # rate "crf": the codec's own quality value
    kbps: int | None = None              # rate "kbps": video data rate
    goal: str = "identical"              # rate / audio "smart": "identical" | "smaller"
    audio: str = "default"               # see AUDIO_MODES; "default" = AAC 192k stereo 48 kHz
    channels: int | None = None          # None = like the source
    audio_kbps: int | None = None        # None = the codec's default / the suggestion

    def copy(self, **changes) -> "ConvertSettings":
        return replace(self, **changes)

    @property
    def measures(self) -> bool:
        """Needs a measurement per file (`suggest.suggest`) before it can be converted."""
        return self.rate == "smart" or self.audio == "smart"


def containers_for(codec_key: str) -> list[str]:
    """Pro containers this codec can be written into (AV1 not in MOV – FFmpeg refuses it)."""
    codec = formats.CODECS_BY_KEY.get(codec_key)
    return [c for c in CONTAINERS if codec and c in codec.containers]


def audio_problem(info: MediaInfo, cs: ConvertSettings) -> str | None:
    """Why the chosen sound setting does not work for this file / container (None = it does).
    A frame-rate change keeps the length, so copying still works then."""
    if cs.audio in ("none", "default", "smart") or not info.has_audio:
        return None
    if cs.audio == "copy":
        if not audio.container_holds(cs.container, info.audio_codec):
            return tr("%s cannot be copied into %s – choose MKV or another sound codec.",
                      (info.audio_codec or tr("this sound")).upper(), cs.container.upper())
        return None
    return audio.encode_reason(cs.container, cs.audio)


def fps_choices(info: MediaInfo) -> list[tuple[str, Fraction | None]]:
    """(label, rate) for the frame-rate list: the original first, then the app's usual rates."""
    out: list[tuple[str, Fraction | None]] = [
        (tr("%s fps (original)", f"{float(info.fps):.5g}"), None)]
    out += [(tr("%s fps", label), r) for label, r in formats.FRAME_RATES if r != info.fps]
    return out


def make_pro_job(info: MediaInfo, frames: FrameMap | None, cs: ConvertSettings,
                 measured=None) -> Job:
    """The job for one file. `measured` = its `suggest.Suggestion` (needed for "smart").

    A different frame rate keeps the length (speed 1): frames are dropped or repeated, never
    invented. Sound: "default" = the app's AAC 192k stereo; everything else is taken straight
    from the source (`audio.direct`) – copied, or encoded once.
    """
    fps = cs.fps or info.fps
    codec = formats.CODECS_BY_KEY[cs.codec]
    container = cs.container if cs.container in codec.containers else codec.containers[0]
    if cs.measures and measured is None:
        raise ValueError(tr("This file has not been measured yet."))
    quality = bitrate = None
    if cs.rate == "smart":
        quality = measured.crf
    elif cs.rate == "crf" and cs.crf is not None:
        quality = cs.crf
    elif cs.rate == "kbps" and cs.kbps:
        bitrate = cs.kbps
    else:
        quality = quality_value(cs.codec, cs.level)

    mode = measured.audio if cs.audio == "smart" else cs.audio
    keep_sound = mode != "none" and info.has_audio
    a_codec = a_kbps = a_ch = None
    if keep_sound and mode != "default":
        a_codec = mode
        if mode != "copy":
            sug = measured if cs.audio == "smart" else None
            a_kbps = cs.audio_kbps or (sug.audio_kbps if sug else None)
            a_ch = cs.channels or (sug.channels if sug else None) or info.audio_channels or 2
            a_ch = min(a_ch, audio.MAX_CHANNELS[mode])
            if info.audio_channels:         # more channels would only copy the same sound
                a_ch = min(a_ch, info.audio_channels)
    settings = OutputSettings(
        fps=fps, speed=None if fps == info.fps else Fraction(1), codec=cs.codec,
        container=container, quality=quality, bitrate=bitrate, audio=keep_sound,
        interpolation="dup", audio_codec=a_codec, audio_bitrate=a_kbps, audio_channels=a_ch)
    return Job(info, settings, frames=frames)


def describe(cs: ConvertSettings) -> str:
    """Short text for a row with its own settings, e.g. 'HEVC MKV · 25 fps · 800 kbit/s · …'."""
    parts = [f"{formats.CODECS_BY_KEY[cs.codec].label.split(' (')[0]} {cs.container.upper()}"]
    if cs.fps:
        parts.append(tr("%s fps", f"{float(cs.fps):.5g}"))
    if cs.rate == "level":
        parts.append(tr(formats.QUALITY_LEVELS[cs.level][0]))
    elif cs.rate == "crf":
        parts.append(tr("quality %d", cs.crf))
    elif cs.rate == "kbps":
        parts.append(tr("%d kbit/s", cs.kbps))
    else:
        parts.append(tr("smart, looks identical") if cs.goal == "identical"
                     else tr("smart, smaller"))
    a = {"default": "AAC", "smart": tr("sound smart"), "copy": tr("sound copied"),
         "none": tr("no sound")}.get(cs.audio) or tr(audio.LABELS[cs.audio])
    if cs.audio in audio.ENCODERS:
        if cs.channels:
            a += " " + (tr("mono") if cs.channels == 1 else tr("stereo") if cs.channels == 2
                        else tr("%d ch", cs.channels))
        if cs.audio_kbps and cs.audio != "flac":
            a += f" {cs.audio_kbps}k"
    parts.append(a)
    return " · ".join(parts)
