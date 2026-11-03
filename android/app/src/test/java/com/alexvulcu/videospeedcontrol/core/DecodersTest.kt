package com.alexvulcu.videospeedcontrol.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class DecodersTest {
    private fun fit(profile: Boolean = true, size: Boolean = true, rate: Boolean = true, w: Int = 4096, h: Int = 2176) =
        DecoderFit(profile, size, rate, w, h)

    @Test fun noDecoder() = assertEquals(DecodeProblem.NoDecoder, Decoders.classify(emptyList()))

    @Test fun oneGoodDecoderIsEnough() =
        assertNull(Decoders.classify(listOf(fit(profile = false), fit(rate = false), fit())))

    @Test fun onlySlow() = assertEquals(DecodeProblem.Rate, Decoders.classify(listOf(fit(rate = false), fit(profile = false))))

    @Test fun profileMissingEverywhere() =
        assertEquals(DecodeProblem.Profile, Decoders.classify(listOf(fit(profile = false), fit(profile = false, size = false))))

    @Test fun tooLargeNamesTheLargestDecoder() = assertEquals(
        DecodeProblem.Size(3840, 2160),
        Decoders.classify(listOf(fit(size = false, rate = false, w = 1920, h = 1088), fit(size = false, rate = false, w = 3840, h = 2160),
            fit(profile = false, size = false, w = 8192, h = 4320))),
    )

    @Test fun onlyRateIsMild() {
        assertEquals(false, DecodeProblem.Rate.severe)
        assertEquals(true, DecodeProblem.Profile.severe)
    }
}
