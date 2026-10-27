package com.alexvulcu.videospeedcontrol.core

import org.junit.Assert.assertEquals
import org.junit.Test

/** Expected strings are what the desktop's batch._num / render_name produce. */
class JobTest {
    @Test fun numbersLikePython() {
        val cases = mapOf(
            25.0 / 120 to "0_208", 4.8 to "4_8", 10.0 to "10", 1.0 / 3 to "0_333",
            0.05 to "0_05", 123.456 to "123", 1.0 to "1", 1234.5 to "1_23e+03",
        )
        for ((v, want) in cases) assertEquals("$v", want, LosslessJob.num3(v))
    }

    @Test fun fpsTokenLikePython() {
        val cases = mapOf("30000/1001" to "29_97", "24000/1001" to "23_976", "25" to "25",
            "120" to "120", "60000/1001" to "59_94")
        for ((r, want) in cases) assertEquals(want, LosslessJob.fpsToken(Rational.parse(r)))
    }
}
