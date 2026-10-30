package com.alexvulcu.videospeedcontrol.core

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/** The treatments folder: saving replaces a file of the same name; fingerprints are found. */
@RunWith(AndroidJUnit4::class)
class CstStoreDeviceTest {
    private val ctx = InstrumentationRegistry.getInstrumentation().targetContext

    @Test fun saveFindReplace() {
        val store = CstStore(ctx)
        val text = { fp: String -> """{"format": "x", "source": {"fingerprint": "$fp"}}""" }
        val a = store.save("vsc_probe.cst", text("fp-one"))
        val b = store.save("vsc_probe.cst", text("fp-two"))           // same name: replaced
        try {
            assertEquals(a, b)
            val fps = store.fingerprints()
            assertTrue("fp-two" in fps)
            assertTrue("fp-one" !in fps)
        } finally {
            ctx.contentResolver.delete(a, null, null)
        }
    }
}
