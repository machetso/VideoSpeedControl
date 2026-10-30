package com.alexvulcu.videospeedcontrol.core

import com.alexvulcu.videospeedcontrol.ui.easyRates
import com.alexvulcu.videospeedcontrol.ui.easySpeedLabel
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/** Easy speed list: every label once, whole frame rates, the original 25 fps (9.6×) kept. */
class EasyRatesTest {
    @Test fun noDoublesAndRoundRates() {
        com.alexvulcu.videospeedcontrol.ui.I18n.use(com.alexvulcu.videospeedcontrol.ui.I18n.Lang.EN)
        val real = Rational.of(240)
        val out = Rational.of(25)
        val rates = easyRates(real, out)
        val labels = rates.map { easySpeedLabel(real, out, it) }
        assertEquals(labels.distinct(), labels)
        assertTrue(rates.none { it == Rational.parse("30000/1001") || it == Rational.parse("24000/1001") })
        assertTrue(Rational.of(30) in rates && Rational.of(60) in rates && real in rates)
        assertTrue("9.6× slower (original)" in labels)
    }
}
