package com.alexvulcu.videospeedcontrol.core

import android.media.MediaCodecInfo
import android.media.MediaCodecList

/** What one decoder of the phone says about a clip (see [Decoders.classify]). */
data class DecoderFit(
    val profile: Boolean,   // the clip's profile (e.g. HEVC Main 10) is listed, or unknown
    val size: Boolean,      // width × height (either orientation)
    val rate: Boolean,      // size at the file frame rate in real time
    val maxWidth: Int,
    val maxHeight: Int,
)

/** Why this phone may not decode a clip – checked when the clip is opened. */
sealed interface DecodeProblem {
    /** No decoder for the codec at all: the clip can't be shown or re-encoded. */
    data object NoDecoder : DecodeProblem
    /** Decoders exist, but none lists the clip's profile (typically 10-bit / HDR on older phones). */
    data object Profile : DecodeProblem
    /** The clip is larger than any decoder takes; [maxWidth] × [maxHeight] = the largest decoder. */
    data class Size(val maxWidth: Int, val maxHeight: Int) : DecodeProblem
    /** Decodable, but not in real time: preview and exports are slower, playback may stutter. */
    data object Rate : DecodeProblem

    /** Opening or re-encoding will probably fail (not just be slow). */
    val severe: Boolean get() = this != Rate
}

/**
 * Decoder check per clip. Phones differ a lot (an older mid-range phone may lack 10-bit HEVC or
 * 4K 120 fps), so the app says so when the clip is opened instead of failing later. The phone's
 * figures are often conservative, so a problem is a warning – the clip is still opened.
 */
object Decoders {
    /** The best answer over all decoders: null = at least one decoder takes the clip in real time. */
    fun classify(fits: List<DecoderFit>): DecodeProblem? {
        if (fits.isEmpty()) return DecodeProblem.NoDecoder
        if (fits.any { it.profile && it.size && it.rate }) return null
        if (fits.any { it.profile && it.size }) return DecodeProblem.Rate
        val withProfile = fits.filter { it.profile }
        if (withProfile.isEmpty()) return DecodeProblem.Profile
        val largest = withProfile.maxBy { it.maxWidth.toLong() * it.maxHeight }
        return DecodeProblem.Size(largest.maxWidth, largest.maxHeight)
    }

    fun check(info: ClipInfo): DecodeProblem? = classify(fits(info))

    private fun fits(info: ClipInfo): List<DecoderFit> =
        MediaCodecList(MediaCodecList.REGULAR_CODECS).codecInfos
            .filter { codec -> !codec.isEncoder && codec.supportedTypes.any { it.equals(info.videoMime, ignoreCase = true) } }
            .mapNotNull { codec -> runCatching { fit(codec.getCapabilitiesForType(info.videoMime), info) }.getOrNull() }

    private fun fit(caps: MediaCodecInfo.CodecCapabilities, info: ClipInfo): DecoderFit {
        val v = caps.videoCapabilities ?: error("not a video decoder")   // skipped by runCatching
        val (w, h) = info.width to info.height
        val fps = info.fps.toDouble()
        val profile = info.videoProfile == null || caps.profileLevels.isEmpty() ||
            caps.profileLevels.any { it.profile == info.videoProfile }
        val size = v.isSizeSupported(w, h) || v.isSizeSupported(h, w)
        val rate = size && (v.areSizeAndRateSupported(w, h, fps) || v.areSizeAndRateSupported(h, w, fps))
        return DecoderFit(profile, size, rate, v.supportedWidths.upper, v.supportedHeights.upper)
    }
}
