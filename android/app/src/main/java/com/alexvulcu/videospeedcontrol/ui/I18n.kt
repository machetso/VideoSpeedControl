package com.alexvulcu.videospeedcontrol.ui

import android.content.Context
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import java.util.Locale

/**
 * User interface language (user, 0.93): English or German; default = the phone's language,
 * changeable in the menu behind the logo and kept across restarts (pref "lang").
 * Texts stay English in the code and are looked up in [GERMAN] – `tr("Save video")`. Templates use
 * String.format placeholders (%s, %d, %.1f …); numbers follow the language (9.6 / 9,6).
 * [choice] is Compose state: changing it redraws every text at once.
 */
object I18n {
    enum class Lang(val label: String) { SYSTEM("Phone language"), EN("English"), DE("Deutsch") }

    var choice by mutableStateOf(Lang.SYSTEM)
        private set

    val german: Boolean
        get() = when (choice) {
            Lang.SYSTEM -> Locale.getDefault().language == "de"
            Lang.DE -> true
            Lang.EN -> false
        }

    /** Locale for numbers in texts. */
    val locale: Locale get() = if (german) Locale.GERMANY else Locale.US

    /** Without storing it (tests). */
    fun use(lang: Lang) { choice = lang }

    fun load(context: Context) {
        val v = context.getSharedPreferences("vsc", Context.MODE_PRIVATE).getString("lang", Lang.SYSTEM.name)
        choice = runCatching { Lang.valueOf(v!!) }.getOrDefault(Lang.SYSTEM)
    }

    fun choose(context: Context, lang: Lang) {
        choice = lang
        context.getSharedPreferences("vsc", Context.MODE_PRIVATE).edit().putString("lang", lang.name).apply()
    }
}

/** [en] in the current language; with [args] it is a String.format template. */
fun tr(en: String, vararg args: Any?): String {
    val text = if (I18n.german) GERMAN[en] ?: en else en
    return if (args.isEmpty()) text else String.format(I18n.locale, text, *args)
}
