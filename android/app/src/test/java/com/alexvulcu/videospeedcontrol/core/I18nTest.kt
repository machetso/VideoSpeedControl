package com.alexvulcu.videospeedcontrol.core

import com.alexvulcu.videospeedcontrol.ui.I18n
import com.alexvulcu.videospeedcontrol.ui.easySpeedLabel
import com.alexvulcu.videospeedcontrol.ui.tr
import com.alexvulcu.videospeedcontrol.ui.trp
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import java.io.File

/**
 * Interface languages: every dictionary in i18n/ has every text of the code (tr / trp) with the
 * same placeholders; numbers and plural forms follow the language.
 */
class I18nTest {
    private val dir = File("../../i18n")

    @Before fun load() = I18n.useDictionaries(dir.listFiles { f -> f.extension == "json" }!!.map { it.nameWithoutExtension to it.readText() })
    @After fun english() = I18n.use("en")

    /** The English texts of the code (same rules as android/tools/i18n_keys.py). */
    private fun keysInCode(): List<String> {
        val lit = "\"((?:[^\"\\\\]|\\\\.)*)\""
        fun string(s: String, start: Int): Pair<String?, Int> {
            var i = start
            val parts = mutableListOf<String>()
            while (true) {
                val m = Regex("^\\s*$lit").find(s.substring(i)) ?: break
                parts += m.groupValues[1]; i += m.range.last + 1
                val plus = Regex("^\\s*\\+\\s*(?=\")").find(s.substring(i)) ?: break
                i += plus.range.last + 1
            }
            return (if (parts.isEmpty()) null else parts.joinToString("").replace("\\\"", "\"")) to i
        }
        val keys = mutableListOf<String>()
        File("src/main/java").walk().filter { it.extension == "kt" }.forEach { f ->
            val s = f.readText()
            Regex("\\btr\\(\\s*").findAll(s).forEach { m -> string(s, m.range.last + 1).first?.let(keys::add) }
            Regex("\\btrp\\(\\s*").findAll(s).forEach { m ->
                val (one, i) = string(s, m.range.last + 1)
                val comma = Regex("^\\s*,\\s*").find(s.substring(i))
                if (one != null && comma != null) string(s, i + comma.range.last + 1).first?.let(keys::add)
            }
        }
        return keys.distinct()
    }

    @Test fun everyLanguageHasEveryText() {
        val ph = Regex("%[0-9.]*[sdf%]")
        val keys = keysInCode()
        assertTrue(keys.size > 200)
        assertTrue(I18n.languages.size >= 2)
        for (lang in I18n.languages.filter { it.code != "en" }) {
            val missing = keys.filter { it !in lang.texts }
            assertEquals("${lang.code}: texts without translation: $missing", emptyList<String>(), missing)
            for ((k, v) in lang.texts) {
                val forms = if (v is Map<*, *>) v.values.map { it.toString() } else listOf(v.toString())
                for (f in forms) assertEquals("${lang.code}: placeholders of \"$k\"",
                    ph.findAll(k).map { it.value }.toList(), ph.findAll(f).map { it.value }.toList())
            }
        }
    }

    @Test fun germanTextsNumbersPlurals() {
        I18n.use("de")
        assertEquals("Video speichern", tr("Save video"))
        assertEquals("9,6× langsamer (Original)", easySpeedLabel(Rational.of(240), Rational.of(25), Rational.of(25)))
        assertEquals("Wird noch gespeichert … 42 %", tr("Still saving … %d %%", 42))
        assertEquals("Verlustfrei, 1 Abschnitt", trp("Lossless, %d section", "Lossless, %d sections", 1, 1))
        assertEquals("Verlustfrei, 3 Abschnitte", trp("Lossless, %d section", "Lossless, %d sections", 3, 3))
        I18n.use("en")
        assertEquals("9.6× slower (original)", easySpeedLabel(Rational.of(240), Rational.of(25), Rational.of(25)))
        assertEquals("Lossless, 1 section", trp("Lossless, %d section", "Lossless, %d sections", 1, 1))
    }

    @Test fun pluralRules() {
        assertEquals("one", I18n.pluralCategory("fr", 0))
        assertEquals("two", I18n.pluralCategory("he", 2))
        assertEquals("other", I18n.pluralCategory("de", 0))
        assertEquals("other", I18n.pluralCategory("tlh", 1))
        assertEquals("few", I18n.pluralCategory("ro", 2))
        assertEquals("few", I18n.pluralCategory("ro", 119))
        assertEquals("other", I18n.pluralCategory("ro", 20))
    }
}
