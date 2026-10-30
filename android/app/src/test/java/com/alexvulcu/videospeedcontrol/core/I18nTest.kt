package com.alexvulcu.videospeedcontrol.core

import com.alexvulcu.videospeedcontrol.ui.GERMAN
import com.alexvulcu.videospeedcontrol.ui.I18n
import com.alexvulcu.videospeedcontrol.ui.easySpeedLabel
import com.alexvulcu.videospeedcontrol.ui.tr
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/** German interface: every tr() text of the code has a German entry with the same placeholders. */
class I18nTest {
    @After fun english() = I18n.use(I18n.Lang.EN)

    private fun keysInCode(): List<String> {
        val lit = Regex("\"((?:[^\"\\\\]|\\\\.)*)\"")
        val keys = mutableListOf<String>()
        File("src/main/java").walk().filter { it.extension == "kt" }.forEach { f ->
            val s = f.readText()
            Regex("\\btr\\(\\s*").findAll(s).forEach { m ->
                var i = m.range.last + 1
                val parts = mutableListOf<String>()
                while (true) {
                    val mm = Regex("^\\s*" + lit.pattern).find(s.substring(i)) ?: break
                    parts += mm.groupValues[1]; i += mm.range.last + 1
                    val plus = Regex("^\\s*\\+\\s*(?=\")").find(s.substring(i)) ?: break
                    i += plus.range.last + 1
                }
                if (parts.isNotEmpty()) keys += parts.joinToString("").replace("\\\"", "\"")
            }
        }
        return keys.distinct()
    }

    @Test fun everyTextIsTranslated() {
        val ph = Regex("%[0-9.]*[sdf%]")
        val keys = keysInCode()
        assertTrue(keys.size > 200)
        val missing = keys.filter { it !in GERMAN }
        assertEquals("texts without German: $missing", emptyList<String>(), missing)
        val bad = GERMAN.filter { (k, v) -> ph.findAll(k).map { it.value }.toList() != ph.findAll(v).map { it.value }.toList() }
        assertEquals("placeholders differ: ${bad.keys}", emptyMap<String, String>(), bad)
    }

    @Test fun germanTextsAndNumbers() {
        I18n.use(I18n.Lang.DE)
        assertEquals("Video speichern", tr("Save video"))
        assertEquals("9,6× langsamer (Original)", easySpeedLabel(Rational.of(240), Rational.of(25), Rational.of(25)))
        assertEquals("Wird noch gespeichert … 42 %", tr("Still saving … %d %%", 42))
        I18n.use(I18n.Lang.EN)
        assertEquals("9.6× slower (original)", easySpeedLabel(Rational.of(240), Rational.of(25), Rational.of(25)))
    }
}
