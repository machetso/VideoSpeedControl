plugins {
    id("com.android.application") version "9.4.1" apply false
    // AGP 9 has Kotlin built in (2.2.x); declaring the plugin raises it to match the Compose compiler.
    id("org.jetbrains.kotlin.android") version "2.4.21" apply false
    id("org.jetbrains.kotlin.plugin.compose") version "2.4.21" apply false
}
