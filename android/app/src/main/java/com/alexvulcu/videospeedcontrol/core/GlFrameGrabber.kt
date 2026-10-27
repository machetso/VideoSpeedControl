package com.alexvulcu.videospeedcontrol.core

import android.graphics.Bitmap
import android.graphics.SurfaceTexture
import android.opengl.EGL14
import android.opengl.EGLConfig
import android.opengl.EGLContext
import android.opengl.EGLDisplay
import android.opengl.EGLExt
import android.opengl.EGLSurface
import android.opengl.GLES11Ext
import android.opengl.GLES20
import android.os.Handler
import android.os.HandlerThread
import android.view.Surface
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.FloatBuffer

/**
 * Decoder output → GPU → either a small RGB bitmap ([grab], proxy frames) or an encoder's input
 * surface ([present], re-encode). The decoder renders into [surface] (a SurfaceTexture); each
 * frame is drawn scaled into a [width] × [height] target – a pbuffer, or the window surface of
 * [target] (MediaCodec.createInputSurface). YUV → RGB, scaling and 10-bit handling are done by
 * the GPU's external-texture sampler. Must be created, used and released on one thread (the EGL
 * context is bound to it). Pattern of AOSP's ExtractMpegFramesTest / DecodeEditEncodeTest.
 */
class GlFrameGrabber(val width: Int, val height: Int, private val target: Surface? = null) {
    private val display: EGLDisplay
    private val context: EGLContext
    private val eglSurface: EGLSurface
    private val texture: Int
    private val program: Int
    private val surfaceTexture: SurfaceTexture
    private val callbackThread = HandlerThread("vsc-frames").apply { start() }
    private val lock = Object()
    private var frameAvailable = false
    private val pixels = ByteBuffer.allocateDirect(width * height * 4).order(ByteOrder.nativeOrder())
    private val bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
    private val stMatrix = FloatArray(16)
    private val quad: FloatBuffer

    /** Give this to MediaCodec.configure as the output surface. */
    val surface: Surface

    init {
        display = EGL14.eglGetDisplay(EGL14.EGL_DEFAULT_DISPLAY)
        val version = IntArray(2)
        check(EGL14.eglInitialize(display, version, 0, version, 1)) { "eglInitialize failed" }
        val attribs = intArrayOf(
            EGL14.EGL_RED_SIZE, 8, EGL14.EGL_GREEN_SIZE, 8, EGL14.EGL_BLUE_SIZE, 8, EGL14.EGL_ALPHA_SIZE, 8,
            EGL14.EGL_RENDERABLE_TYPE, EGL14.EGL_OPENGL_ES2_BIT,
            EGL14.EGL_SURFACE_TYPE, if (target == null) EGL14.EGL_PBUFFER_BIT else EGL14.EGL_WINDOW_BIT,
            *(if (target != null) intArrayOf(EGL_RECORDABLE_ANDROID, 1) else intArrayOf()),
            EGL14.EGL_NONE,
        )
        val configs = arrayOfNulls<EGLConfig>(1)
        val n = IntArray(1)
        check(EGL14.eglChooseConfig(display, attribs, 0, configs, 0, 1, n, 0) && n[0] > 0) { "no EGL config" }
        context = EGL14.eglCreateContext(display, configs[0], EGL14.EGL_NO_CONTEXT,
            intArrayOf(EGL14.EGL_CONTEXT_CLIENT_VERSION, 2, EGL14.EGL_NONE), 0)
        eglSurface = if (target == null) EGL14.eglCreatePbufferSurface(display, configs[0],
            intArrayOf(EGL14.EGL_WIDTH, width, EGL14.EGL_HEIGHT, height, EGL14.EGL_NONE), 0)
        else EGL14.eglCreateWindowSurface(display, configs[0], target, intArrayOf(EGL14.EGL_NONE), 0)
        check(EGL14.eglMakeCurrent(display, eglSurface, eglSurface, context)) { "eglMakeCurrent failed" }

        val tex = IntArray(1)
        GLES20.glGenTextures(1, tex, 0)
        texture = tex[0]
        GLES20.glBindTexture(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, texture)
        GLES20.glTexParameteri(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, GLES20.GL_TEXTURE_MIN_FILTER, GLES20.GL_LINEAR)
        GLES20.glTexParameteri(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, GLES20.GL_TEXTURE_MAG_FILTER, GLES20.GL_LINEAR)
        GLES20.glTexParameteri(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, GLES20.GL_TEXTURE_WRAP_S, GLES20.GL_CLAMP_TO_EDGE)
        GLES20.glTexParameteri(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, GLES20.GL_TEXTURE_WRAP_T, GLES20.GL_CLAMP_TO_EDGE)

        program = link(VERTEX, FRAGMENT)
        surfaceTexture = SurfaceTexture(texture)
        surfaceTexture.setOnFrameAvailableListener({
            synchronized(lock) { frameAvailable = true; lock.notifyAll() }
        }, Handler(callbackThread.looper))
        surface = Surface(surfaceTexture)

        // full-screen quad: x, y, u, v. The rotation is already in the SurfaceTexture transform
        // (MediaCodec applies the track's rotation to its output surface), so only [width] ×
        // [height] must be the rotated size. glReadPixels returns rows bottom-up; for read-back
        // the shader flips v (uFlip), for the encoder surface it doesn't.
        val uv = floatArrayOf(0f, 0f, 1f, 0f, 0f, 1f, 1f, 1f)
        val pos = floatArrayOf(-1f, -1f, 1f, -1f, -1f, 1f, 1f, 1f)
        val data = FloatArray(16) { i -> if (i % 4 < 2) pos[i / 4 * 2 + i % 4] else uv[i / 4 * 2 + i % 4 - 2] }
        quad = ByteBuffer.allocateDirect(data.size * 4).order(ByteOrder.nativeOrder()).asFloatBuffer().put(data)
    }

    /** Wait for the frame just released with render = true; false on timeout. */
    fun awaitFrame(timeoutMs: Long = 2_000): Boolean {
        synchronized(lock) {
            val end = System.currentTimeMillis() + timeoutMs
            while (!frameAvailable) {
                val left = end - System.currentTimeMillis()
                if (left <= 0) return false
                lock.wait(left)
            }
            frameAvailable = false
        }
        surfaceTexture.updateTexImage()
        return true
    }

    /** Draw the current frame and read it back. The bitmap is reused – copy or compress it. */
    fun grab(): Bitmap {
        draw(flipForReadback = true)
        pixels.clear()
        GLES20.glReadPixels(0, 0, width, height, GLES20.GL_RGBA, GLES20.GL_UNSIGNED_BYTE, pixels)
        pixels.rewind()
        bitmap.copyPixelsFromBuffer(pixels)
        return bitmap
    }

    /** Draw the current frame into the encoder surface with presentation time [ptsNs]. */
    fun present(ptsNs: Long) {
        draw(flipForReadback = false)
        EGLExt.eglPresentationTimeANDROID(display, eglSurface, ptsNs)
        EGL14.eglSwapBuffers(display, eglSurface)
    }

    private fun draw(flipForReadback: Boolean) {
        surfaceTexture.getTransformMatrix(stMatrix)
        GLES20.glViewport(0, 0, width, height)
        GLES20.glUseProgram(program)
        GLES20.glActiveTexture(GLES20.GL_TEXTURE0)
        GLES20.glBindTexture(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, texture)
        val aPos = GLES20.glGetAttribLocation(program, "aPos")
        val aUv = GLES20.glGetAttribLocation(program, "aUv")
        quad.position(0)
        GLES20.glVertexAttribPointer(aPos, 2, GLES20.GL_FLOAT, false, 16, quad)
        GLES20.glEnableVertexAttribArray(aPos)
        quad.position(2)
        GLES20.glVertexAttribPointer(aUv, 2, GLES20.GL_FLOAT, false, 16, quad)
        GLES20.glEnableVertexAttribArray(aUv)
        GLES20.glUniformMatrix4fv(GLES20.glGetUniformLocation(program, "uSt"), 1, false, stMatrix, 0)
        GLES20.glUniform1f(GLES20.glGetUniformLocation(program, "uFlip"), if (flipForReadback) 1f else 0f)
        GLES20.glDrawArrays(GLES20.GL_TRIANGLE_STRIP, 0, 4)
    }

    fun release() {
        surface.release()
        surfaceTexture.release()
        GLES20.glDeleteProgram(program)
        GLES20.glDeleteTextures(1, intArrayOf(texture), 0)
        EGL14.eglMakeCurrent(display, EGL14.EGL_NO_SURFACE, EGL14.EGL_NO_SURFACE, EGL14.EGL_NO_CONTEXT)
        EGL14.eglDestroySurface(display, eglSurface)
        EGL14.eglDestroyContext(display, context)
        EGL14.eglTerminate(display)
        callbackThread.quitSafely()
    }

    private fun link(vs: String, fs: String): Int {
        fun shader(type: Int, src: String) = GLES20.glCreateShader(type).also {
            GLES20.glShaderSource(it, src)
            GLES20.glCompileShader(it)
            val ok = IntArray(1)
            GLES20.glGetShaderiv(it, GLES20.GL_COMPILE_STATUS, ok, 0)
            check(ok[0] != 0) { "shader: " + GLES20.glGetShaderInfoLog(it) }
        }
        val p = GLES20.glCreateProgram()
        GLES20.glAttachShader(p, shader(GLES20.GL_VERTEX_SHADER, vs))
        GLES20.glAttachShader(p, shader(GLES20.GL_FRAGMENT_SHADER, fs))
        GLES20.glLinkProgram(p)
        return p
    }

    companion object {
        private const val EGL_RECORDABLE_ANDROID = 0x3142
        private const val VERTEX = """
            attribute vec4 aPos;
            attribute vec2 aUv;
            uniform mat4 uSt;
            uniform float uFlip;
            varying vec2 vUv;
            void main() {
                gl_Position = aPos;
                float v = mix(aUv.y, 1.0 - aUv.y, uFlip);
                vUv = (uSt * vec4(aUv.x, v, 0.0, 1.0)).xy;
            }"""
        private const val FRAGMENT = """
            #extension GL_OES_EGL_image_external : require
            precision mediump float;
            varying vec2 vUv;
            uniform samplerExternalOES uTex;
            void main() { gl_FragColor = texture2D(uTex, vUv); }"""
    }
}
