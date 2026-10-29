package com.alexvulcu.videospeedcontrol.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.gestures.detectHorizontalDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import kotlin.math.abs
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

/** Space above the thumbnail strip: section labels, playhead handle, the tops of the trim brackets. */
private val STRIP_TOP = 22.dp

/** A speed ramp on the timeline: source frames [start, end), rate going from [from] to [to]. */
data class RampZone(val start: Int, val end: Int, val from: com.alexvulcu.videospeedcontrol.core.Rational,
                    val to: com.alexvulcu.videospeedcontrol.core.Rational)

/** Keyframe thumbnail for the strip: source frame index + picture. */
data class Thumb(val frame: Int, val image: ImageBitmap, val bitmap: android.graphics.Bitmap)

/**
 * Thumbnail strip with speed sections, their borders (with grips), speed ramps, trim (dimmed
 * outside), keyframe ticks, the pending section start and the playhead. Tap: move the playhead
 * and select the section there; drag: scrub – or, starting on a border, move that border.
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
    onTap: (frame: Int, magnetRadius: Int) -> Unit = onSeek,
    ramps: List<RampZone> = emptyList(),
    draggedBorder: Int? = null,
    onBorderDragStart: (border: Int) -> Unit = {},
    onBorderDrag: (frame: Int) -> Unit = {},
    onBorderDragEnd: () -> Unit = {},
    onTrimDrag: (isIn: Boolean, frame: Int) -> Unit = { _, _ -> },
    easy: Boolean = false,
    modifier: Modifier = Modifier,
) {
    val count = edit.info.frames.count
    val keyframes = edit.info.frames.keyframes
    val aspect = edit.info.displayWidth.toFloat() / maxOf(1, edit.info.displayHeight)
    val colors = MaterialTheme.colorScheme
    val measurer = rememberTextMeasurer()
    val seek by rememberUpdatedState(onSeek)
    val tap by rememberUpdatedState(onTap)
    val borders by rememberUpdatedState(edit.borders())
    val dragStart by rememberUpdatedState(onBorderDragStart)
    val dragMove by rememberUpdatedState(onBorderDrag)
    val dragEnd by rememberUpdatedState(onBorderDragEnd)
    val trimDrag by rememberUpdatedState(onTrimDrag)
    val trimIn by rememberUpdatedState(edit.trim.start)
    val trimOut by rememberUpdatedState(edit.trimEnd)
    val stripTopPx = with(androidx.compose.ui.platform.LocalDensity.current) { STRIP_TOP.toPx() }
    val grabPx = with(androidx.compose.ui.platform.LocalDensity.current) { 16.dp.toPx() }

    var downX by remember { mutableFloatStateOf(0f) }
    var downY by remember { mutableFloatStateOf(0f) }
    fun frameAt(x: Float, width: Float) = (x / width * count).toInt().coerceIn(0, count - 1)
    val magnetPx = with(androidx.compose.ui.platform.LocalDensity.current) { 12.dp.toPx() }
    /** Magnet radius in frames: 12 dp on screen (a fingertip; the desktop uses 8 px). */
    fun radius(width: Float) = maxOf(1, (magnetPx / width * count).toInt())

    Canvas(
        modifier
            .fillMaxWidth()
            .height(96.dp)
            .pointerInput(count) {
                detectTapGestures { tap(frameAt(it.x, size.width.toFloat()), radius(size.width.toFloat())) }
            }
            .pointerInput(count) {
                // where the finger went down (onDragStart only reports the point after the touch slop)
                awaitEachGesture {
                    val p = awaitFirstDown(requireUnconsumed = false).position
                    downX = p.x
                    downY = p.y
                }
            }
            .pointerInput(count) {
                var border: Int? = null
                var trim: Boolean? = null          // true = in bracket, false = out bracket
                detectHorizontalDragGestures(
                    onDragStart = {
                        val w = size.width.toFloat()
                        val nearBorder = borders.minByOrNull { b -> abs(b.toFloat() / count * w - downX) }
                        val dBorder = nearBorder?.let { b -> abs(b.toFloat() / count * w - downX) } ?: Float.MAX_VALUE
                        val dIn = abs(trimIn.toFloat() / count * w - downX)
                        val dOut = abs(trimOut.toFloat() / count * w - downX)
                        val dTrim = minOf(dIn, dOut)
                        // the brackets: grabbed above the strip, or when closer than any section border
                        trim = if (dTrim <= grabPx * 1.5f && (downY < stripTopPx || dTrim < dBorder)) dIn <= dOut else null
                        border = if (trim == null) nearBorder?.takeIf { dBorder <= grabPx } else null
                        when {
                            trim != null -> {}
                            border != null -> dragStart(border!!)
                            else -> seek(frameAt(it.x, w), radius(w))
                        }
                    },
                    onDragEnd = { if (border != null) dragEnd(); border = null; trim = null },
                    onDragCancel = { if (border != null) dragEnd(); border = null; trim = null },
                ) { change, _ ->
                    change.consume()
                    val w = size.width.toFloat()
                    val b = (change.position.x / w * count).roundToInt().coerceIn(0, count)
                    when {
                        trim != null -> trimDrag(trim!!, b)
                        border != null -> dragMove(b)
                        else -> seek(frameAt(change.position.x, w), radius(w))
                    }
                }
            },
    ) {
        val w = size.width
        val stripTop = STRIP_TOP.toPx()
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
            // Easy: the speed ("4× slower", short "4×" if it does not fit); Pro: the frame rate
            var label = measurer.measure(if (easy) easySpeedShort(real, s.fps, long = true) else ClipEdit.fpsLabel(s.fps),
                TextStyle(fontSize = 11.sp, color = c))
            if (easy && label.size.width >= right - left) {
                label = measurer.measure(easySpeedShort(real, s.fps, long = false), TextStyle(fontSize = 11.sp, color = c))
            }
            if (label.size.width < right - left) {
                drawText(label, topLeft = Offset(left + (right - left - label.size.width) / 2, 0f))
            }
        }

        // speed ramps: dark field with a slanted line – up = getting faster, down = slower
        for (z in ramps) {
            val top = stripTop + stripH * 0.4f
            val h = stripH * 0.6f - 5.dp.toPx()
            val left = x(z.start)
            val right = maxOf(left + 3f, x(z.end))
            drawRect(Color.Black.copy(alpha = 0.55f), Offset(left, top), Size(right - left, h))
            val faster = z.to > z.from
            val yLow = top + h - 3.dp.toPx()
            val yHigh = top + 3.dp.toPx()
            drawLine(Color.White, Offset(left, if (faster) yLow else yHigh), Offset(right, if (faster) yHigh else yLow),
                2.5f.dp.toPx())
        }

        // section borders: clearly visible lines with a grip below the strip (drag to move)
        for (b in edit.borders()) {
            val bx = x(b)
            val active = b == draggedBorder
            val line = if (active) colors.error else Color.White
            drawLine(Color.Black.copy(alpha = 0.7f), Offset(bx, stripTop), Offset(bx, stripTop + stripH), 4.dp.toPx())
            drawLine(line, Offset(bx, stripTop), Offset(bx, stripTop + stripH), 2.dp.toPx())
            val gy = stripTop + stripH + 5.dp.toPx()
            drawRoundRect(Color.Black.copy(alpha = 0.7f), Offset(bx - 5.dp.toPx(), gy - 5.dp.toPx()),
                Size(10.dp.toPx(), 10.dp.toPx()), CornerRadius(3.dp.toPx()))
            drawRoundRect(line, Offset(bx - 4.dp.toPx(), gy - 4.dp.toPx()), Size(8.dp.toPx(), 8.dp.toPx()),
                CornerRadius(2.dp.toPx()))
        }

        // trim: dim what is cut away
        val dim = Color.Black.copy(alpha = 0.6f)
        if (edit.trim.start > 0) drawRect(dim, Offset(0f, stripTop), Size(x(edit.trim.start), stripH))
        if (edit.trimEnd < count) drawRect(dim, Offset(x(edit.trimEnd), stripTop), Size(w - x(edit.trimEnd), stripH))

        // trim brackets [ ] – reaching above the strip, where they are easy to grab
        val trimColor = Color(0xFFF1C40F)
        val bw = 4.dp.toPx()
        val serif = 10.dp.toPx()
        val bottom = stripTop + stripH + 2.dp.toPx()
        for ((frame, isIn) in listOf(edit.trim.start to true, edit.trimEnd to false)) {
            val bx = x(frame).coerceIn(bw / 2, w - bw / 2)
            val dir = if (isIn) 1f else -1f
            drawLine(trimColor, Offset(bx, 1.dp.toPx()), Offset(bx, bottom), bw)
            drawLine(trimColor, Offset(bx - dir * bw / 2, 1.dp.toPx() + bw / 2), Offset(bx + dir * serif, 1.dp.toPx() + bw / 2), bw)
            drawLine(trimColor, Offset(bx - dir * bw / 2, bottom - bw / 2), Offset(bx + dir * serif, bottom - bw / 2), bw)
        }

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
