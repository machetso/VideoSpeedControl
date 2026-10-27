package com.alexvulcu.videospeedcontrol.core

import android.os.ParcelFileDescriptor
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assume.assumeTrue
import java.io.File

/**
 * Test clips pushed by tools/device_test.sh to /data/local/tmp/vsc/. The app may not read that
 * folder itself, so the clip is copied into the app cache through the instrumentation's shell.
 */
object TestClips {
    private const val DEVICE_DIR = "/data/local/tmp/vsc"

    fun get(name: String): File {
        val inst = InstrumentationRegistry.getInstrumentation()
        val target = File(inst.targetContext.cacheDir, "testclips/$name")
        // cached copy only if it still has the size of the pushed clip (clips get regenerated)
        val size = shell("stat -c %s $DEVICE_DIR/$name").trim().toLongOrNull()
        if (target.isFile && target.length() > 0 && target.length() == size) return target
        target.parentFile!!.mkdirs()
        val pfd = inst.uiAutomation.executeShellCommand("cat $DEVICE_DIR/$name")
        target.delete()
        ParcelFileDescriptor.AutoCloseInputStream(pfd).use { input ->
            target.outputStream().use { input.copyTo(it) }
        }
        if (target.length() == 0L) target.delete()
        assumeTrue("test clip $name not pushed (tools/device_test.sh CLIP)", target.isFile)
        return target
    }

    private fun shell(cmd: String): String {
        val pfd = InstrumentationRegistry.getInstrumentation().uiAutomation.executeShellCommand(cmd)
        return ParcelFileDescriptor.AutoCloseInputStream(pfd).use { it.readBytes().decodeToString() }
    }
}
