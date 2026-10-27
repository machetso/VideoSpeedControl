package com.alexvulcu.videospeedcontrol.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.gestures.detectHorizontalDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.drawscope.clipRect
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.alexvulcu.videospeedcontrol.core.ClipEdit
import kotlin.math.ceil
import kotlin.math.roundToInt

/** Keyframe thumbnail for the strip: source frame index + picture. */
data class Thumb(val frame: Int, val image: ImageBitmap, val bitmap: android.graphics.Bitmap)

/**
 * Thumbnail strip with speed sections, trim (dimmed outside), keyframe ticks, the pending
 * section start and the playhead. Tap or drag to move the playhead.
 */
@Composable
fun Timeline(
    edit: ClipEdit,
    playhead: Int,
    pendingStart: Int?,
    selected: Int,
    thumbs: List<Thumb>,
    proxyProgress: Float,
    onSeek: (frame: Int, magnetRadius: Int) -> Unit,
    modifier: Modifier = Modifier,
) {
    val count = edit.info.frames.count
    val keyframes = edit.info.frames.keyframes
    val aspect = edit.info.displayWidth.toFloat() / maxOf(1, edit.info.displayHeight)
    val colors = MaterialTheme.colorScheme
    val measurer = rememberTextMeasurer()
    val seek by rememberUpdatedState(onSeek)

    fun frameAt(x: Float, width: Float) = (x / width * count).toInt().coerceIn(0, count - 1)
    val magnetPx = with(androidx.compose.ui.platform.LocalDensity.current) { 12.dp.toPx() }
    /** Magnet radius in frames: 12 dp on screen (a fingertip; the desktop uses 8 px). */
    fun radius(width: Float) = maxOf(1, (magnetPx / width * count).toInt())

    Canvas(
        modifier
            .fillMaxWidth()
            .height(76.dp)
            .pointerInput(count) {
                detectTapGestures { seek(frameAt(it.x, size.width.toFloat()), radius(size.width.toFloat())) }
            }
            .pointerInput(count) {
                detectHorizontalDragGestures(
                    onDragStart = { seek(frameAt(it.x, size.width.toFloat()), radius(size.width.toFloat())) },
                ) { change, _ ->
                    change.consume()
                    seek(frameAt(change.position.x, size.width.toFloat()), radius(size.width.toFloat()))
                }
            },
    ) {
        val w = size.width
        val stripTop = 14.dp.toPx()
        val stripH = 48.dp.toPx()
        fun x(frame: Int) = frame.toFloat() / count * w

        // thumbnails: each slot shows the nearest keyframe at or before its centre
        drawRect(colors.surfaceVariant, Offset(0f, stripTop), Size(w, stripH))
        if (thumbs.isNotEmpty()) {
            val slotW = stripH * aspect
            val slots = ceil(w / slotW).toInt()
            clipRect(0f, stripTop, w, stripTop + stripH) {
                for (i in 0 until slots) {
                    val centre = ((i + 0.5f) * slotW / w * count).toInt()
                    val t = thumbs.lastOrNull { it.frame <= centre } ?: thumbs.first()
                    drawImage(
                        t.image,
                        srcOffset = IntOffset.Zero, srcSize = IntSize(t.image.width, t.image.height),
                        dstOffset = IntOffset((i * slotW).roundToInt(), stripTop.roundToInt()),
                        dstSize = IntSize(slotW.roundToInt() + 1, stripH.roundToInt()),
                    )
                }
            }
        }

        // speed sections: slower = primary, faster = tertiary; label = frame rate
        val real = edit.info.realFps
        edit.segments.forEachIndexed { i, s ->
            val left = x(s.start)
            val right = x(s.end)
            val c = if (s.fps < real) colors.primary else colors.tertiary
            drawRect(c.copy(alpha = if (i == selected) 0.55f else 0.35f), Offset(left, stripTop), Size(right - left, stripH))
            drawRect(c, Offset(left, stripTop + stripH - 4.dp.toPx()), Size(right - left, 4.dp.toPx()))
            val label = measurer.measure(ClipEdit.fpsLabel(s.fps), TextStyle(fontSize = 11.sp, color = c))
            if (label.size.width < right - left) {
                drawText(label, topLeft = Offset(left + (right - left - label.size.width) / 2, 0f))
            }
        }

        // trim: dim what is cut away
        val dim = Color.Black.copy(alpha = 0.6f)
        if (edit.trim.start > 0) drawRect(dim, Offset(0f, stripTop), Size(x(edit.trim.start), stripH))
        if (edit.trimEnd < count) drawRect(dim, Offset(x(edit.trimEnd), stripTop), Size(w - x(edit.trimEnd), stripH))

        // proxy progress: thin bar along the bottom edge while frames are being prepared
        if (proxyProgress < 1f) {
            val barH = 3.dp.toPx()
            drawRect(colors.surface.copy(alpha = 0.7f), Offset(0f, stripTop + stripH - barH), Size(w, barH))
            drawRect(colors.primary, Offset(0f, stripTop + stripH - barH), Size(w * proxyProgress, barH))
        }

        // keyframe ticks under the strip
        val tickTop = stripTop + stripH + 2.dp.toPx()
        for (k in keyframes) {
            drawLine(colors.outline, Offset(x(k), tickTop), Offset(x(k), tickTop + 5.dp.toPx()), 1.dp.toPx())
        }

        // pending section start
        pendingStart?.let {
            val px = x(it)
            drawLine(colors.primary, Offset(px, stripTop - 4.dp.toPx()), Offset(px, stripTop + stripH),
                2.dp.toPx(), pathEffect = PathEffect.dashPathEffect(floatArrayOf(6f, 4f)))
        }

        // playhead with a small handle on top
        val px = x(playhead) + 0.5f * w / count
        drawLine(colors.error, Offset(px, stripTop - 2.dp.toPx()), Offset(px, stripTop + stripH + 8.dp.toPx()), 2.dp.toPx())
        val tri = Path().apply {
            moveTo(px - 6.dp.toPx(), stripTop - 8.dp.toPx())
            lineTo(px + 6.dp.toPx(), stripTop - 8.dp.toPx())
            lineTo(px, stripTop - 1.dp.toPx())
            close()
        }
        drawPath(tri, colors.error)
        drawRoundRect(colors.outline, Offset(0f, stripTop), Size(w, stripH), CornerRadius.Zero,
            style = androidx.compose.ui.graphics.drawscope.Stroke(1.dp.toPx()))
    }
}
