# Copyright (c) 2026 Alex Vulcu
#
# Concept, architecture, direction, and curation by Alex Vulcu.
# Implementation assisted by generative AI tools.
#
# Licensed under the MIT License.
# See the LICENSE file in the repository root for details.
"""Catalogue of everything the user can choose: frame rates, resolutions, chroma,
scalers, interpolation methods and codecs, each with UI texts."""
from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction

# --------------------------------------------------------------------------- frame rates

FRAME_RATES: list[tuple[str, Fraction]] = [
    ("23.976", Fraction(24000, 1001)),
    ("24", Fraction(24)),
    ("25 (PAL)", Fraction(25)),
    ("29.97", Fraction(30000, 1001)),
    ("30", Fraction(30)),
    ("50 (PAL)", Fraction(50)),
    ("59.94", Fraction(60000, 1001)),
    ("60", Fraction(60)),
    ("120", Fraction(120)),
]
DEFAULT_FPS = Fraction(25)

# --------------------------------------------------------------------------- resolutions


@dataclass(frozen=True)
class Resolution:
    key: str
    label: str
    width: int
    height: int
    tooltip: str = ""


RESOLUTIONS: list[Resolution] = [
    Resolution("sd480", "480p SD (854×480)", 854, 480, "Standard definition, 16:9"),
    Resolution("hd720", "720p HD (1280×720)", 1280, 720, "HD ready, 16:9"),
    Resolution("hd1080", "1080p Full HD (1920×1080)", 1920, 1080, "Full HD, most common delivery format"),
    Resolution("qhd1440", "1440p QHD (2560×1440)", 2560, 1440, "Quad HD, 16:9"),
    Resolution("gopro27", "2.7K (2704×1520)", 2704, 1520, "GoPro 2.7K 16:9"),
    Resolution("uhd4k", "4K UHD (3840×2160)", 3840, 2160, "Ultra HD (TV / YouTube 4K)"),
    Resolution("dci2k", "DCI 2K (2048×1080)", 2048, 1080, "Digital cinema 2K, ~1.9:1"),
    Resolution("dci4k", "DCI 4K (4096×2160)", 4096, 2160, "Digital cinema 4K, ~1.9:1"),
    Resolution("v1080", "Vertical 9:16 (1080×1920)", 1080, 1920, "Reels, Shorts, TikTok"),
    Resolution("sq1080", "Square 1:1 (1080×1080)", 1080, 1080, "Square social media format"),
]

ASPECT_PRESETS: list[tuple[str, Fraction]] = [
    ("16:9", Fraction(16, 9)),
    ("4:3", Fraction(4, 3)),
    ("21:9 (2.33:1)", Fraction(21, 9)),
    ("2.39:1 Cinemascope", Fraction(239, 100)),
    ("1.85:1 Flat", Fraction(185, 100)),
    ("1:1", Fraction(1)),
    ("4:5", Fraction(4, 5)),
    ("9:16", Fraction(9, 16)),
]

FIT_MODES = {
    "pad": ("Fit (black bars)", "Whole picture visible; free space is filled with black bars."),
    "crop": ("Fill (crop)", "Frame is completely filled; edges of the picture are cut off."),
    "stretch": ("Stretch", "Picture is distorted to the new aspect ratio. Rarely wanted."),
}

# --------------------------------------------------------------------------- chroma / depth

CHROMA = {
    "444": ("4:4:4", "Full colour resolution for every pixel.\n"
                     "High-end VFX, compositing, green screen, screen recordings.\n"
                     "Largest files."),
    "422": ("4:2:2", "Colour at half horizontal resolution.\n"
                     "Broadcast TV, professional editing and intermediates (ProRes, DNxHR)."),
    "420": ("4:2:0", "Colour at quarter resolution (half width, half height).\n"
                     "Streaming and delivery (Netflix, YouTube), Blu-ray, most cameras.\n"
                     "Smallest files, plays everywhere."),
}
CHROMA_UPSAMPLE_NOTE = ("The source has less colour information – choosing a higher\n"
                        "subsampling does not restore detail, it only makes files bigger.")

DEPTHS = {
    8: ("8-bit", "256 shades per channel. Standard for delivery and maximum compatibility."),
    10: ("10-bit", "1024 shades per channel. Less banding in gradients, needed for HDR / Log\n"
                   "footage and colour grading."),
}

# pixel format candidates per (chroma, depth), in order of preference
_PIX_CANDIDATES = {
    ("420", 8): ["yuv420p", "nv12", "yuvj420p"],
    ("420", 10): ["yuv420p10le", "p010le"],
    ("422", 8): ["yuv422p", "nv16", "yuvj422p", "yuyv422"],
    ("422", 10): ["yuv422p10le", "p210le", "y210le"],
    ("444", 8): ["yuv444p", "yuvj444p", "gbrp"],
    ("444", 10): ["yuv444p10le", "gbrp10le", "yuv444p10msble", "yuv444p16le"],
}
_RGB_CANDIDATES = {
    8: ["rgb24", "gbrp"],
    10: ["gbrp10le", "rgb48le", "rgb48be"],
}

# --------------------------------------------------------------------------- scalers


@dataclass(frozen=True)
class Scaler:
    key: str      # swscale flag
    label: str
    quality: int  # 1..5
    speed: int    # 1..5
    tooltip: str


SCALERS: list[Scaler] = [
    Scaler("neighbor", "Nearest neighbour", 1, 5,
           "Copies the nearest pixel. Blocky, but exact for integer factors (2×, 3×).\n"
           "Use for pixel art or technical footage."),
    Scaler("bilinear", "Bilinear", 2, 5,
           "Averages 2×2 pixels. Fast but soft; fine for previews."),
    Scaler("bicubic", "Bicubic", 3, 4,
           "Uses 4×4 pixels. Good all-round quality, slightly sharper than bilinear."),
    Scaler("area", "Area (box average)", 4, 4,
           "Averages all source pixels under each target pixel.\n"
           "Very clean for strong downscaling (e.g. 4K → 1080p); poor for upscaling."),
    Scaler("spline", "Spline", 4, 3,
           "Smooth spline curve. Sharp with few artefacts."),
    Scaler("lanczos", "Lanczos", 5, 3,
           "Sharpest result for up- and downscaling. Can show slight halos (ringing)\n"
           "at hard edges. Recommended default."),
]
DEFAULT_SCALER = "lanczos"

# --------------------------------------------------------------------------- interpolation


@dataclass(frozen=True)
class Interpolation:
    key: str
    label: str
    quality: int        # 1..5
    cost: float         # relative processing cost per output frame (1 = plain encode)
    needs_gpu: bool
    tooltip: str


INTERPOLATIONS: list[Interpolation] = [
    Interpolation("dup", "Frame duplication", 1, 1.0, False,
                  "Repeats existing frames. No new images, motion stutters.\n"
                  "Fastest – practically no extra processing time."),
    Interpolation("blend", "Frame blending", 2, 1.2, False,
                  "Cross-fades neighbouring frames. Smooth but with ghosting\n"
                  "(double images) on motion. Very fast."),
    Interpolation("mci", "Motion interpolation (FFmpeg minterpolate)", 3, 12.0, False,
                  "Estimates motion vectors and builds real in-between frames on the CPU.\n"
                  "Good for slow, even motion; artefacts on fast motion and occlusions.\n"
                  "Very slow: about 1–10 frames/s at 1080p depending on the CPU\n"
                  "(measured: 1.2 fps on a laptop with Core i7-8565U)."),
    Interpolation("rife", "AI interpolation (RIFE)", 4, 4.0, True,
                  "Neural network on the GPU (Vulkan, also integrated Intel/AMD graphics).\n"
                  "Clearly better motion and edges than minterpolate.\n"
                  "Fast on dedicated GPUs, slow on integrated graphics\n"
                  "(measured on Intel UHD 620: 2 fps at 720p, 0.9 fps at 1080p).\n"
                  "Works on 8-bit RGB – 10-bit / HDR precision is lost."),
    Interpolation("rife_hq", "AI interpolation (RIFE, high quality)", 5, 8.0, True,
                  "RIFE run in both time directions and merged (temporal test-time\n"
                  "augmentation): fewer artefacts on fast motion and occlusions.\n"
                  "About 2× slower than RIFE (measured on Intel UHD 620: 1 fps at 720p)."),
]
DEFAULT_INTERPOLATION = "blend"

# --------------------------------------------------------------------------- codecs


@dataclass(frozen=True)
class Quality:
    label: str
    args: tuple[str, ...]  # '{q}' is replaced by the value
    minimum: int
    maximum: int
    default: int
    lower_is_better: bool = True
    tooltip: str = ""


@dataclass(frozen=True)
class Profile:
    key: str
    label: str
    args: tuple[str, ...]
    chroma: tuple[str, ...] | None = None   # restricts chroma if set
    depths: tuple[int, ...] | None = None   # restricts depth if set
    tooltip: str = ""


@dataclass(frozen=True)
class Codec:
    key: str
    label: str
    encoder: str
    lossless: bool
    containers: tuple[str, ...]   # first one is the default
    description: str
    speed: int = 3                # 1..5 rough encoding speed
    cost: float = 1.0             # relative cost vs. x264 medium (for time estimates)
    quality: Quality | None = None
    preset_flag: str | None = None
    presets: tuple[str, ...] = ()
    default_preset: str | None = None
    profiles: tuple[Profile, ...] = ()
    default_profile: str | None = None
    args: tuple[str, ...] = ()
    hw: str | None = None          # 'nvenc', 'qsv', 'vaapi', 'amf'
    rgb: bool = False              # works in RGB (image sequences, QuickTime Animation)
    image_sequence: bool = False
    container_args: dict = field(default_factory=dict)
    external: str | None = None    # encoded by a separate program, e.g. 'avm' (AV2)


_X26X_PRESETS = ("ultrafast", "superfast", "veryfast", "faster", "fast", "medium",
                 "slow", "slower", "veryslow")
_NVENC_PRESETS = ("p1", "p2", "p3", "p4", "p5", "p6", "p7")
_QSV_PRESETS = ("veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow")
_CRF_TIP = "Constant quality. Lower = better quality and bigger files."
_HVC1 = {"mp4": ("-tag:v", "hvc1"), "mov": ("-tag:v", "hvc1")}


AV2_PRESETS = tuple(str(i) for i in range(10))     # --cpu-used: 9 = fastest
AV2_COST = 2000.0                                   # vs. x264 medium – measured, see CLAUDE.md
AV2_TIP = ("AV2, the successor of AV1 (AOMedia, spec 1.0 from May 2026), encoded with the\n"
           "AVM reference software. About 30 % smaller than AV1 – but the reference\n"
           "encoder is a research tool – measured on a Core i7-8565U (cpu-used 9):\n"
           "about 75 s per 1080p frame, about 20 s per 360p frame. Only for short clips.\n"
           "Hardly any player can play AV2 yet (no FFmpeg support, hardware from ~2027).")


def _crf(default: int, maximum: int = 51) -> Quality:
    return Quality("CRF", ("-crf", "{q}"), 0, maximum, default, tooltip=_CRF_TIP)


CODECS: list[Codec] = [
    # ----------------------------------------------------------------- lossless
    Codec("ffv1", "FFV1 (lossless, archive)", "ffv1", True, ("mkv", "avi"),
          "Open lossless codec of FFmpeg, archive standard (e.g. libraries, archives).\n"
          "Very good compression for lossless, multithreaded.", speed=3, cost=1.0,
          args=("-level", "3", "-coder", "1", "-context", "1", "-g", "1",
                "-slices", "16", "-slicecrc", "1")),
    Codec("utvideo", "Ut Video (lossless, editing)", "utvideo", True, ("mkv", "avi", "mov"),
          "Fast lossless intermediate codec. Premiere / VirtualDub on Windows need the\n"
          "free 'Ut Video Codec Suite' to read it; DaVinci Resolve and FFmpeg-based\n"
          "players read it directly.", speed=5, cost=0.4,
          args=("-pred", "median")),
    Codec("magicyuv", "MagicYUV (lossless, editing)", "magicyuv", True, ("mkv", "avi"),
          "Very fast lossless intermediate codec, comparable to Ut Video.", speed=5, cost=0.4),
    Codec("ffvhuff", "HuffYUV (FFmpeg variant, lossless)", "ffvhuff", True, ("mkv", "avi"),
          "Very fast, very large files. FFmpeg variant of HuffYUV with 10-bit and 4:2:0 support.",
          speed=5, cost=0.3),
    Codec("huffyuv", "HuffYUV (classic, lossless)", "huffyuv", True, ("avi", "mkv"),
          "Original HuffYUV, maximum compatibility with old Windows software.\n"
          "8-bit 4:2:2 only.", speed=5, cost=0.3),
    Codec("x264_lossless", "H.264 lossless (x264)", "libx264", True, ("mkv", "mp4", "mov"),
          "H.264 in mathematically lossless mode. Smaller than FFV1, but not every\n"
          "player supports the required High 4:4:4 Predictive profile.", speed=3, cost=1.2,
          args=("-qp", "0"), preset_flag="-preset", presets=_X26X_PRESETS, default_preset="fast"),
    Codec("x265_lossless", "HEVC lossless (x265)", "libx265", True, ("mkv", "mp4", "mov"),
          "HEVC in lossless mode. Small files, slow encoding.", speed=1, cost=4.0,
          args=("-x265-params", "lossless=1:log-level=error"),
          preset_flag="-preset", presets=_X26X_PRESETS, default_preset="medium",
          container_args=_HVC1),
    Codec("vp9_lossless", "VP9 lossless", "libvpx-vp9", True, ("mkv", "webm"),
          "VP9 in lossless mode. Slow.", speed=1, cost=5.0,
          args=("-lossless", "1", "-row-mt", "1", "-deadline", "good", "-cpu-used", "4")),
    Codec("aom_lossless", "AV1 lossless (libaom)", "libaom-av1", True, ("mkv", "mp4"),
          "AV1 in lossless mode. Very slow.", speed=1, cost=10.0,
          args=("-aom-params", "lossless=1", "-row-mt", "1", "-cpu-used", "6")),
    Codec("av2_lossless", "AV2 lossless (AVM reference, extremely slow)", "avmenc", True,
          ("ivf", "webm"), AV2_TIP + "\n\nLossless mode (--lossless=1).", speed=1,
          cost=AV2_COST, external="avm",
          preset_flag="--cpu-used", presets=AV2_PRESETS, default_preset="9",
          args=("--lossless=1",)),
    Codec("qtrle", "QuickTime Animation (lossless, RGB)", "qtrle", True, ("mov",),
          "Old Apple lossless RGB codec, 8-bit only. Huge files; for legacy workflows.",
          speed=4, cost=0.6, rgb=True),
    Codec("png_seq", "PNG image sequence (lossless)", "png", True, ("png",),
          "One PNG file per frame, 8 or 16-bit RGB. Universal for VFX / compositing.",
          speed=2, cost=2.0, rgb=True, image_sequence=True),
    Codec("tiff_seq", "TIFF image sequence (lossless)", "tiff", True, ("tiff",),
          "One TIFF file per frame, 8 or 16-bit RGB.", speed=3, cost=1.0,
          rgb=True, image_sequence=True, args=("-compression_algo", "deflate")),
    Codec("dpx_seq", "DPX image sequence (lossless)", "dpx", True, ("dpx",),
          "Film/VFX standard, one file per frame, 8 or 10-bit RGB.", speed=4, cost=0.5,
          rgb=True, image_sequence=True),
    Codec("exr_seq", "OpenEXR image sequence (32-bit float)", "exr", True, ("exr",),
          "High-end VFX format with floating-point colour. Very large files.",
          speed=3, cost=1.0, rgb=True, image_sequence=True),

    # ----------------------------------------------------------------- lossy CPU
    Codec("x264", "H.264 / AVC (x264)", "libx264", False, ("mp4", "mkv", "mov"),
          "Most compatible codec – plays on every device. Good quality, fast.",
          speed=4, cost=1.0, quality=_crf(18),
          preset_flag="-preset", presets=_X26X_PRESETS, default_preset="medium"),
    Codec("x265", "HEVC / H.265 (x265)", "libx265", False, ("mp4", "mkv", "mov"),
          "About 30–50 % smaller than H.264 at the same quality, slower to encode.\n"
          "Supports 10-bit and HDR.", speed=2, cost=3.0, quality=_crf(20),
          preset_flag="-preset", presets=_X26X_PRESETS, default_preset="medium",
          args=("-x265-params", "log-level=error"), container_args=_HVC1),
    Codec("svtav1", "AV1 (SVT-AV1, fast)", "libsvtav1", False, ("mp4", "mkv", "webm"),
          "Modern royalty-free codec, smaller than HEVC. SVT-AV1 is the fastest\n"
          "AV1 encoder. 4:2:0 only.", speed=3, cost=2.0, quality=_crf(30, 63),
          preset_flag="-preset", presets=tuple(str(i) for i in range(14)), default_preset="8"),
    Codec("aom", "AV1 (libaom, best quality)", "libaom-av1", False, ("mp4", "mkv", "webm"),
          "Reference AV1 encoder: best compression, very slow. Supports 4:2:2 / 4:4:4.",
          speed=1, cost=8.0, quality=_crf(30, 63), args=("-b:v", "0", "-row-mt", "1"),
          preset_flag="-cpu-used", presets=tuple(str(i) for i in range(9)), default_preset="6"),
    Codec("av2", "AV2 (AVM reference, extremely slow)", "avmenc", False, ("ivf", "webm"),
          AV2_TIP, speed=1, cost=AV2_COST, external="avm",
          quality=Quality("QP", ("--end-usage=q", "--qp={q}"), 0, 255, 140,
                          tooltip="Constant quality on AV2's 0–255 scale.\n"
                                  "Lower = better quality and bigger files."),
          preset_flag="--cpu-used", presets=AV2_PRESETS, default_preset="9"),
    Codec("vp9", "VP9 (libvpx)", "libvpx-vp9", False, ("webm", "mkv", "mp4"),
          "Google's codec (YouTube), between H.264 and AV1 in efficiency. Slow.",
          speed=2, cost=4.0, quality=_crf(31, 63),
          args=("-b:v", "0", "-row-mt", "1", "-deadline", "good"),
          preset_flag="-cpu-used", presets=tuple(str(i) for i in range(6)), default_preset="2"),
    Codec("prores", "Apple ProRes (prores_ks)", "prores_ks", False, ("mov", "mkv"),
          "Edit-friendly intermediate codec, standard in Final Cut, Premiere, Resolve.\n"
          "Every frame is a keyframe – smooth scrubbing, large files. Always 10-bit.",
          speed=4, cost=0.8, args=("-vendor", "apl0"),
          profiles=(
              Profile("proxy", "ProRes 422 Proxy", ("-profile:v", "0"), ("422",), (10,),
                      "≈45 Mbit/s at 1080p30 – offline editing / proxies"),
              Profile("lt", "ProRes 422 LT", ("-profile:v", "1"), ("422",), (10,),
                      "≈100 Mbit/s – lighter editing format"),
              Profile("std", "ProRes 422", ("-profile:v", "2"), ("422",), (10,),
                      "≈145 Mbit/s – standard quality"),
              Profile("hq", "ProRes 422 HQ", ("-profile:v", "3"), ("422",), (10,),
                      "≈220 Mbit/s – high quality, visually lossless"),
              Profile("4444", "ProRes 4444", ("-profile:v", "4"), ("444",), (10,),
                      "≈330 Mbit/s – full colour resolution, VFX"),
              Profile("4444xq", "ProRes 4444 XQ", ("-profile:v", "5"), ("444",), (10,),
                      "≈500 Mbit/s – highest quality"),
          ), default_profile="hq"),
    Codec("dnxhr", "Avid DNxHR", "dnxhd", False, ("mov", "mxf"),
          "Avid's intermediate codec (Media Composer, Resolve, Premiere), all-intra.",
          speed=4, cost=0.8,
          profiles=(
              Profile("lb", "DNxHR LB", ("-profile:v", "dnxhr_lb"), ("422",), (8,),
                      "Low bandwidth – offline / proxies"),
              Profile("sq", "DNxHR SQ", ("-profile:v", "dnxhr_sq"), ("422",), (8,),
                      "Standard quality – broadcast delivery"),
              Profile("hq", "DNxHR HQ", ("-profile:v", "dnxhr_hq"), ("422",), (8,),
                      "High quality 8-bit"),
              Profile("hqx", "DNxHR HQX", ("-profile:v", "dnxhr_hqx"), ("422",), (10,),
                      "High quality 10-bit – grading, HDR"),
              Profile("444", "DNxHR 444", ("-profile:v", "dnxhr_444"), ("444",), (10,),
                      "4:4:4 10-bit – finishing, VFX"),
          ), default_profile="hq"),
    Codec("cineform", "GoPro CineForm", "cfhd", False, ("mov", "avi"),
          "Wavelet intermediate codec, 10-bit 4:2:2, edit-friendly.", speed=4, cost=0.8,
          preset_flag="-quality",
          presets=("film3+", "film3", "film2+", "film2", "film1.5", "film1+", "film1",
                   "high+", "high", "medium+", "medium", "low+", "low"),
          default_preset="film1"),
    Codec("mjpeg", "Motion JPEG", "mjpeg", False, ("mov", "mkv", "avi"),
          "Every frame a JPEG. Simple, compatible with old editing software, large files.",
          speed=5, cost=0.5,
          quality=Quality("Quality", ("-q:v", "{q}"), 1, 31, 3,
                          tooltip="1 = best, 31 = worst")),

    # ----------------------------------------------------------------- lossy GPU
    Codec("h264_nvenc", "H.264 (NVIDIA NVENC)", "h264_nvenc", False, ("mp4", "mkv", "mov"),
          "Hardware encoder of NVIDIA graphics cards. Very fast, slightly bigger files\n"
          "than x264 at equal quality.", speed=5, cost=0.2, hw="nvenc",
          quality=Quality("CQ", ("-rc", "vbr", "-cq", "{q}", "-b:v", "0"), 0, 51, 21,
                          tooltip=_CRF_TIP),
          preset_flag="-preset", presets=_NVENC_PRESETS, default_preset="p5"),
    Codec("hevc_nvenc", "HEVC (NVIDIA NVENC)", "hevc_nvenc", False, ("mp4", "mkv", "mov"),
          "NVIDIA hardware HEVC encoder, 8/10-bit.", speed=5, cost=0.2, hw="nvenc",
          quality=Quality("CQ", ("-rc", "vbr", "-cq", "{q}", "-b:v", "0"), 0, 51, 23,
                          tooltip=_CRF_TIP),
          preset_flag="-preset", presets=_NVENC_PRESETS, default_preset="p5",
          container_args=_HVC1),
    Codec("av1_nvenc", "AV1 (NVIDIA NVENC, RTX 40+)", "av1_nvenc", False, ("mp4", "mkv"),
          "NVIDIA hardware AV1 encoder (RTX 4000 series and newer).", speed=5, cost=0.2,
          hw="nvenc",
          quality=Quality("CQ", ("-rc", "vbr", "-cq", "{q}", "-b:v", "0"), 0, 63, 30,
                          tooltip=_CRF_TIP),
          preset_flag="-preset", presets=_NVENC_PRESETS, default_preset="p5"),
    Codec("h264_qsv", "H.264 (Intel Quick Sync)", "h264_qsv", False, ("mp4", "mkv", "mov"),
          "Hardware encoder of Intel CPUs with integrated graphics. Fast, also on laptops.",
          speed=5, cost=0.3, hw="qsv",
          quality=Quality("Quality", ("-global_quality", "{q}"), 1, 51, 23, tooltip=_CRF_TIP),
          preset_flag="-preset", presets=_QSV_PRESETS, default_preset="medium"),
    Codec("hevc_qsv", "HEVC (Intel Quick Sync)", "hevc_qsv", False, ("mp4", "mkv", "mov"),
          "Intel hardware HEVC encoder, 8/10-bit.", speed=5, cost=0.3, hw="qsv",
          quality=Quality("Quality", ("-global_quality", "{q}"), 1, 51, 25, tooltip=_CRF_TIP),
          preset_flag="-preset", presets=_QSV_PRESETS, default_preset="medium",
          container_args=_HVC1),
    Codec("av1_qsv", "AV1 (Intel Quick Sync, Arc+)", "av1_qsv", False, ("mp4", "mkv"),
          "Intel hardware AV1 encoder (Arc graphics, Core Ultra).", speed=5, cost=0.3, hw="qsv",
          quality=Quality("Quality", ("-global_quality", "{q}"), 1, 51, 30, tooltip=_CRF_TIP),
          preset_flag="-preset", presets=_QSV_PRESETS, default_preset="medium"),
    Codec("h264_vaapi", "H.264 (VAAPI, Linux)", "h264_vaapi", False, ("mp4", "mkv", "mov"),
          "Linux hardware encoding via VAAPI (Intel / AMD graphics).", speed=5, cost=0.3,
          hw="vaapi", quality=Quality("QP", ("-qp", "{q}"), 1, 51, 23, tooltip=_CRF_TIP)),
    Codec("hevc_vaapi", "HEVC (VAAPI, Linux)", "hevc_vaapi", False, ("mp4", "mkv", "mov"),
          "Linux hardware HEVC encoding via VAAPI (Intel / AMD graphics).", speed=5, cost=0.3,
          hw="vaapi", quality=Quality("QP", ("-qp", "{q}"), 1, 51, 25, tooltip=_CRF_TIP),
          container_args=_HVC1),
    Codec("h264_amf", "H.264 (AMD AMF, Windows)", "h264_amf", False, ("mp4", "mkv", "mov"),
          "Hardware encoder of AMD graphics cards (Windows).", speed=5, cost=0.25, hw="amf",
          quality=Quality("QP", ("-rc", "cqp", "-qp_i", "{q}", "-qp_p", "{q}", "-qp_b", "{q}"),
                          1, 51, 22, tooltip=_CRF_TIP)),
    Codec("hevc_amf", "HEVC (AMD AMF, Windows)", "hevc_amf", False, ("mp4", "mkv", "mov"),
          "AMD hardware HEVC encoder (Windows).", speed=5, cost=0.25, hw="amf",
          quality=Quality("QP", ("-rc", "cqp", "-qp_i", "{q}", "-qp_p", "{q}"), 1, 51, 24,
                          tooltip=_CRF_TIP),
          container_args=_HVC1),
    Codec("av1_amf", "AV1 (AMD AMF, RX 7000+)", "av1_amf", False, ("mp4", "mkv"),
          "AMD hardware AV1 encoder (RX 7000 series and newer, Windows).", speed=5, cost=0.25,
          hw="amf", quality=Quality("QP", ("-rc", "cqp", "-qp_i", "{q}", "-qp_p", "{q}"),
                                    1, 255, 120, tooltip=_CRF_TIP)),
]

CODECS_BY_KEY = {c.key: c for c in CODECS}

# --------------------------------------------------------------------------- quality levels

QUALITY_LEVELS = (
    ("Visually lossless", "No visible difference even in a still frame. Large files."),
    ("High", "Hardly any visible loss – good for further editing and archiving."),
    ("Good", "Streaming quality (YouTube, Netflix): fine for watching."),
    ("Medium", "Losses visible on a close look, e.g. in fine detail or dark areas."),
    ("Small file", "Clearly visible losses – for previews or sending quickly."),
)
# per codec: the codec's own value for each level above (best → smallest). "High" is the
# codec's default, so the levels do not change existing behaviour.
QUALITY_VALUES = {
    "x264": (14, 18, 23, 28, 34), "x265": (16, 20, 25, 30, 35),
    "svtav1": (22, 30, 37, 44, 52), "aom": (22, 30, 36, 43, 50),
    "vp9": (24, 31, 37, 44, 52), "av2": (100, 140, 170, 200, 225),
    "mjpeg": (2, 3, 5, 8, 12),
    "h264_nvenc": (17, 21, 25, 29, 34), "hevc_nvenc": (19, 23, 27, 31, 36),
    "av1_nvenc": (22, 30, 37, 44, 52),
    "h264_qsv": (18, 23, 27, 31, 36), "hevc_qsv": (20, 25, 29, 33, 38),
    "av1_qsv": (22, 30, 36, 42, 48),
    "h264_vaapi": (18, 23, 27, 31, 36), "hevc_vaapi": (20, 25, 29, 33, 38),
    "h264_amf": (17, 22, 26, 30, 35), "hevc_amf": (19, 24, 28, 32, 37),
    "av1_amf": (80, 120, 150, 180, 210),
}


def quality_levels(codec: Codec) -> list[tuple[str, str, int]]:
    """(name, explanation, codec value) for each named quality level of `codec`."""
    values = QUALITY_VALUES.get(codec.key, ())
    return [(name, tip, v) for (name, tip), v in zip(QUALITY_LEVELS, values)]


# --------------------------------------------------------------------------- preset texts

_NAMED_PRESETS = {
    "ultrafast": "fastest, largest file", "superfast": "very fast, very large file",
    "veryfast": "fast, large file", "faster": "faster, larger file",
    "fast": "a bit faster, a bit larger file", "medium": "balanced",
    "slow": "slower, smaller file", "slower": "much slower, smaller file",
    "veryslow": "slowest, smallest file",
}


def _speed_text(f: float) -> str:
    """0 = slowest / best compression … 1 = fastest."""
    if f <= 0:
        return "slowest, smallest file"
    if f >= 1:
        return "fastest, largest file"
    for limit, text in ((0.25, "very slow, very small file"), (0.45, "slow, small file"),
                        (0.6, "balanced"), (0.8, "fast, larger file")):
        if f < limit:
            return text
    return "very fast, large file"


def preset_label(codec: Codec, preset: str) -> str:
    """Drop-down text for a preset, e.g. 'medium – balanced (default)'."""
    presets = codec.presets
    i, n = presets.index(preset), max(1, len(presets) - 1)
    if codec.key == "cineform":        # its 'preset' is a quality level, best first
        f = i / n
        text = ("highest quality, largest file" if f == 0 else
                "lowest quality, smallest file" if f == 1 else
                "very high quality" if f < 0.3 else "high quality" if f < 0.6 else
                "medium quality, smaller file")
    elif preset in _NAMED_PRESETS:
        text = _NAMED_PRESETS[preset]
    elif codec.preset_flag == "-preset" and preset.startswith("p"):   # NVENC p1 fast … p7
        text = _speed_text(1 - i / n)
    else:                               # numbers: 0 = slowest (SVT-AV1, libaom, VP9, AV2)
        text = _speed_text(i / n)
    if codec.external == "avm" and i == len(presets) - 1:
        text = "fastest – still about a minute per 1080p frame"
    return f"{preset} – {text}" + (" (default)" if preset == codec.default_preset else "")


PRESET_TIP = ("How long the encoder searches for the best compression.\n"
              "At the same quality setting a slower preset gives a smaller file and takes\n"
              "longer; the visible quality hardly changes.")
CINEFORM_TIP = "CineForm compression level: higher = better picture and larger files."

# Special codec key: keep the source bitstream (lossless retime)
COPY = "copy"

# Which source codecs each container can hold when stream-copying.
COPY_CONTAINERS = {
    "mp4": {"h264", "hevc", "av1", "mpeg4", "mpeg2video", "vp9", "mjpeg"},
    "mov": {"h264", "hevc", "prores", "mjpeg", "dnxhd", "cfhd", "mpeg4", "mpeg2video",
            "qtrle", "av1"},
    "mkv": None,  # Matroska takes (almost) everything
    "avi": {"mjpeg", "huffyuv", "ffvhuff", "utvideo", "magicyuv", "ffv1", "mpeg4", "cfhd",
            "h264", "dnxhd"},
    "mxf": {"dnxhd", "mpeg2video", "h264", "prores"},
    "webm": {"vp8", "vp9", "av1"},
}

CONTAINER_EXT = {"mkv": ".mkv", "mp4": ".mp4", "mov": ".mov", "avi": ".avi",
                 "mxf": ".mxf", "webm": ".webm", "ivf": ".ivf",
                 "png": ".png", "tiff": ".tif", "dpx": ".dpx", "exr": ".exr"}


def copy_containers(source_codec: str) -> list[str]:
    return [c for c, codecs in COPY_CONTAINERS.items() if codecs is None or source_codec in codecs]


def pixel_format(codec: Codec, chroma: str, depth: int, supported: list[str] | None) -> str | None:
    """Pick the pixel format for codec/chroma/depth, or None if impossible.

    `supported` is the encoder's own list (from `ffmpeg -h encoder=...`); None = unknown.
    """
    if codec.encoder == "exr":
        return "gbrpf32le"
    if codec.rgb:
        candidates = _RGB_CANDIDATES[depth]
    elif codec.encoder == "mjpeg":
        candidates = [f"yuvj{chroma}p"] if depth == 8 else []
    else:
        candidates = _PIX_CANDIDATES.get((chroma, depth), [])
    if supported is None:
        return candidates[0] if candidates else None
    return next((p for p in candidates if p in supported), None)


def allowed_formats(codec: Codec, profile: Profile | None,
                    supported: list[str] | None) -> list[tuple[str, int]]:
    """All (chroma, depth) combinations the codec/profile can produce."""
    out = []
    for chroma in ("420", "422", "444"):
        if codec.rgb and chroma != "444":
            continue
        if profile and profile.chroma and chroma not in profile.chroma:
            continue
        for depth in (8, 10):
            if profile and profile.depths and depth not in profile.depths:
                continue
            if codec.encoder == "exr" and depth != 10:
                continue  # float format – shown once
            if pixel_format(codec, chroma, depth, supported):
                out.append((chroma, depth))
    return out
