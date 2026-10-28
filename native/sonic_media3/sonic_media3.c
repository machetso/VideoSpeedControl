/*
 * Sonic time stretching – C port of Media3's androidx.media3.common.audio.Sonic (16-bit path),
 * so the desktop app stretches sound exactly like the Android app (verified bit-exact against the
 * Java original by tests/test_sonic.py with tools/sonic_reference/).
 *
 * Original: Copyright (C) 2017 The Android Open Source Project, based on
 * https://github.com/waywardgeek/sonic (Bill Cox). Licensed under the Apache License 2.0:
 * http://www.apache.org/licenses/LICENSE-2.0 – see LICENSE in this directory.
 * Port: Copyright (c) 2026 Alex Vulcu, same licence. Changes: C instead of Java, 16-bit samples
 * only, byte buffers replaced by frame arrays.
 *
 * Java semantics kept on purpose: Math.round = floor(x + 0.5); int products wrap like Java's
 * (two's complement, via uint32); float vs double evaluation as in the original.
 */
#include <math.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#if defined(_WIN32)
#define EXPORT __declspec(dllexport)
#else
#define EXPORT __attribute__((visibility("default")))
#endif

#define MINIMUM_PITCH 65
#define MAXIMUM_PITCH 400
#define AMDF_FREQUENCY 4000
#define MINIMUM_SPEEDUP_RATE 1.00001f
#define MINIMUM_SLOWDOWN_RATE 0.99999f

typedef struct {
    int inputSampleRateHz, channelCount;
    float speed, pitch, rate;
    int minPeriod, maxPeriod, maxRequiredFrameCount;

    int inputFrameCount, outputFrameCount, pitchFrameCount;
    int oldRatePosition, newRatePosition;
    int remainingInputToCopyFrameCount;
    int prevPeriod;
    double accumulatedSpeedAdjustmentError;

    /* SonicShortImpl */
    short *downSampleBuffer;
    short *inputBuffer, *outputBuffer, *pitchBuffer;
    int inputCap, outputCap, pitchCap; /* capacities in frames */
    int minDiff, maxDiff, prevMinDiff;
} Sonic;

static int32_t mul32(int32_t a, int32_t b) { return (int32_t)((uint32_t)a * (uint32_t)b); }
static long java_round(double x) { return (long)floor(x + 0.5); }

/* ensureSpaceForAdditionalFrames: grow like Arrays.copyOf (zero-filled) */
static short *ensure(Sonic *s, short *buf, int *cap, int frameCount, int additional) {
    if (frameCount + additional <= *cap) return buf;
    int newCap = 3 * *cap / 2 + additional;
    short *n = (short *)realloc(buf, (size_t)newCap * s->channelCount * sizeof(short));
    if (!n) abort();
    memset(n + (size_t)*cap * s->channelCount, 0, (size_t)(newCap - *cap) * s->channelCount * sizeof(short));
    *cap = newCap;
    return n;
}
#define ENSURE_INPUT(s, k) ((s)->inputBuffer = ensure((s), (s)->inputBuffer, &(s)->inputCap, (s)->inputFrameCount, (k)))
#define ENSURE_OUTPUT(s, k) ((s)->outputBuffer = ensure((s), (s)->outputBuffer, &(s)->outputCap, (s)->outputFrameCount, (k)))
#define ENSURE_PITCH(s, k) ((s)->pitchBuffer = ensure((s), (s)->pitchBuffer, &(s)->pitchCap, (s)->pitchFrameCount, (k)))

static short interpolate(Sonic *s, const short *in, int inPos, long long oldSampleRate, long long newSampleRate) {
    short left = in[inPos];
    short right = in[inPos + s->channelCount];
    long long position = (long long)s->newRatePosition * oldSampleRate;
    long long leftPosition = (long long)s->oldRatePosition * newSampleRate;
    long long rightPosition = ((long long)s->oldRatePosition + 1) * newSampleRate;
    long long ratio = rightPosition - position;
    long long width = rightPosition - leftPosition;
    return (short)((ratio * left + (width - ratio) * right) / width);
}

static void interpolateFrame(Sonic *s, int positionFrames, long long oldSampleRate, long long newSampleRate) {
    for (int i = 0; i < s->channelCount; i++) {
        s->outputBuffer[s->outputFrameCount * s->channelCount + i] =
            interpolate(s, s->pitchBuffer, positionFrames * s->channelCount + i, oldSampleRate, newSampleRate);
    }
}

static int isPreviousPeriodBetter(Sonic *s) {
    if (s->minDiff == 0 || s->prevPeriod == 0) return 0;
    if (s->maxDiff > mul32(s->minDiff, 3)) return 0;
    if (mul32(s->minDiff, 2) <= mul32(s->prevMinDiff, 3)) return 0;
    return 1;
}

static void downSampleInput(Sonic *s, int positionFrames, int skip) {
    int frameCount = s->maxRequiredFrameCount / skip;
    int samplesPerValue = s->channelCount * skip;
    positionFrames *= s->channelCount;
    for (int i = 0; i < frameCount; i++) {
        int value = 0;
        for (int j = 0; j < samplesPerValue; j++) value += s->inputBuffer[positionFrames + i * samplesPerValue + j];
        value /= samplesPerValue;
        s->downSampleBuffer[i] = (short)value;
    }
}

static int findPitchPeriodInRange(Sonic *s, const short *samples, int positionFrames, int minPeriod, int maxPeriod) {
    int bestPeriod = 0, worstPeriod = 255;
    int minDiff = 1, maxDiff = 0;
    positionFrames *= s->channelCount;
    for (int period = minPeriod; period <= maxPeriod; period++) {
        int diff = 0;
        for (int i = 0; i < period; i++) {
            short sVal = samples[positionFrames + i];
            short pVal = samples[positionFrames + period + i];
            diff += abs(sVal - pVal);
        }
        if (mul32(diff, bestPeriod) < mul32(minDiff, period)) {
            minDiff = diff;
            bestPeriod = period;
        }
        if (mul32(diff, worstPeriod) > mul32(maxDiff, period)) {
            maxDiff = diff;
            worstPeriod = period;
        }
    }
    s->minDiff = minDiff / bestPeriod;
    s->maxDiff = maxDiff / worstPeriod;
    return bestPeriod;
}

static void overlapAdd(Sonic *s, int frameCount, int channelCount, int outPosition, int rampDownPosition, int rampUpPosition) {
    short *out = s->outputBuffer, *rampDown = s->inputBuffer, *rampUp = s->inputBuffer;
    for (int i = 0; i < channelCount; i++) {
        int o = outPosition * channelCount + i;
        int u = rampUpPosition * channelCount + i;
        int d = rampDownPosition * channelCount + i;
        for (int t = 0; t < frameCount; t++) {
            out[o] = (short)((rampDown[d] * (frameCount - t) + rampUp[u] * t) / frameCount);
            o += channelCount;
            d += channelCount;
            u += channelCount;
        }
    }
}

static void copyToOutput(Sonic *s, int positionFrames, int frameCount) {
    ENSURE_OUTPUT(s, frameCount);
    memmove(s->outputBuffer + (size_t)s->outputFrameCount * s->channelCount,
            s->inputBuffer + (size_t)positionFrames * s->channelCount,
            (size_t)frameCount * s->channelCount * sizeof(short));
    s->outputFrameCount += frameCount;
}

static int copyInputToOutput(Sonic *s, int positionFrames) {
    int frameCount = s->maxRequiredFrameCount < s->remainingInputToCopyFrameCount
                         ? s->maxRequiredFrameCount : s->remainingInputToCopyFrameCount;
    copyToOutput(s, positionFrames, frameCount);
    s->remainingInputToCopyFrameCount -= frameCount;
    return frameCount;
}

static int findPitchPeriod(Sonic *s, int positionFrames) {
    int period, retPeriod;
    int skip = s->inputSampleRateHz > AMDF_FREQUENCY ? s->inputSampleRateHz / AMDF_FREQUENCY : 1;
    if (s->channelCount == 1 && skip == 1) {
        period = findPitchPeriodInRange(s, s->inputBuffer, positionFrames, s->minPeriod, s->maxPeriod);
    } else {
        downSampleInput(s, positionFrames, skip);
        period = findPitchPeriodInRange(s, s->downSampleBuffer, 0, s->minPeriod / skip, s->maxPeriod / skip);
        if (skip != 1) {
            period *= skip;
            int minP = period - (skip * 4);
            int maxP = period + (skip * 4);
            if (minP < s->minPeriod) minP = s->minPeriod;
            if (maxP > s->maxPeriod) maxP = s->maxPeriod;
            if (s->channelCount == 1) {
                period = findPitchPeriodInRange(s, s->inputBuffer, positionFrames, minP, maxP);
            } else {
                downSampleInput(s, positionFrames, 1);
                period = findPitchPeriodInRange(s, s->downSampleBuffer, 0, minP, maxP);
            }
        }
    }
    retPeriod = isPreviousPeriodBetter(s) ? s->prevPeriod : period;
    s->prevMinDiff = s->minDiff;
    s->prevPeriod = period;
    return retPeriod;
}

static void moveNewSamplesToPitchBuffer(Sonic *s, int originalOutputFrameCount) {
    int frameCount = s->outputFrameCount - originalOutputFrameCount;
    ENSURE_PITCH(s, frameCount);
    memmove(s->pitchBuffer + (size_t)s->pitchFrameCount * s->channelCount,
            s->outputBuffer + (size_t)originalOutputFrameCount * s->channelCount,
            (size_t)frameCount * s->channelCount * sizeof(short));
    s->outputFrameCount = originalOutputFrameCount;
    s->pitchFrameCount += frameCount;
}

static void removePitchFrames(Sonic *s, int frameCount) {
    if (frameCount == 0) return;
    memmove(s->pitchBuffer, s->pitchBuffer + (size_t)frameCount * s->channelCount,
            (size_t)(s->pitchFrameCount - frameCount) * s->channelCount * sizeof(short));
    s->pitchFrameCount -= frameCount;
}

static void adjustRate(Sonic *s, float rate, int originalOutputFrameCount) {
    if (s->outputFrameCount == originalOutputFrameCount) return;
    long long newSampleRate = (long long)(s->inputSampleRateHz / rate);
    long long oldSampleRate = s->inputSampleRateHz;
    while (newSampleRate != 0 && oldSampleRate != 0 && newSampleRate % 2 == 0 && oldSampleRate % 2 == 0) {
        newSampleRate /= 2;
        oldSampleRate /= 2;
    }
    moveNewSamplesToPitchBuffer(s, originalOutputFrameCount);
    for (int position = 0; position < s->pitchFrameCount - 1; position++) {
        while (((long long)s->oldRatePosition + 1) * newSampleRate > (long long)s->newRatePosition * oldSampleRate) {
            ENSURE_OUTPUT(s, 1);
            interpolateFrame(s, position, oldSampleRate, newSampleRate);
            s->newRatePosition++;
            s->outputFrameCount++;
        }
        s->oldRatePosition++;
        if (s->oldRatePosition == oldSampleRate) {
            s->oldRatePosition = 0;
            s->newRatePosition = 0;
        }
    }
    removePitchFrames(s, s->pitchFrameCount - 1);
}

static int skipPitchPeriod(Sonic *s, int position, double speed, int period) {
    int newFrameCount;
    if (speed >= 2.0f) {
        double expectedFrameCount = period / (speed - 1.0) + s->accumulatedSpeedAdjustmentError;
        newFrameCount = (int)java_round(expectedFrameCount);
        s->accumulatedSpeedAdjustmentError = expectedFrameCount - newFrameCount;
    } else {
        newFrameCount = period;
        double expectedInputToCopy = period * (2.0f - speed) / (speed - 1.0f) + s->accumulatedSpeedAdjustmentError;
        s->remainingInputToCopyFrameCount = (int)java_round(expectedInputToCopy);
        s->accumulatedSpeedAdjustmentError = expectedInputToCopy - s->remainingInputToCopyFrameCount;
    }
    ENSURE_OUTPUT(s, newFrameCount);
    overlapAdd(s, newFrameCount, s->channelCount, s->outputFrameCount, position, position + period);
    s->outputFrameCount += newFrameCount;
    return newFrameCount;
}

static int insertPitchPeriod(Sonic *s, int position, double speed, int period) {
    int newFrameCount;
    if (speed < 0.5f) {
        double expectedFrameCount = period * speed / (1.0f - speed) + s->accumulatedSpeedAdjustmentError;
        newFrameCount = (int)java_round(expectedFrameCount);
        s->accumulatedSpeedAdjustmentError = expectedFrameCount - newFrameCount;
    } else {
        newFrameCount = period;
        double expectedInputToCopy = period * (2.0f * speed - 1.0f) / (1.0f - speed) + s->accumulatedSpeedAdjustmentError;
        s->remainingInputToCopyFrameCount = (int)java_round(expectedInputToCopy);
        s->accumulatedSpeedAdjustmentError = expectedInputToCopy - s->remainingInputToCopyFrameCount;
    }
    ENSURE_OUTPUT(s, period + newFrameCount);
    memmove(s->outputBuffer + (size_t)s->outputFrameCount * s->channelCount,
            s->inputBuffer + (size_t)position * s->channelCount,
            (size_t)period * s->channelCount * sizeof(short));
    overlapAdd(s, newFrameCount, s->channelCount, s->outputFrameCount + period, position + period, position);
    s->outputFrameCount += period + newFrameCount;
    return newFrameCount;
}

static void removeProcessedInputFrames(Sonic *s, int positionFrames) {
    int remainingFrames = s->inputFrameCount - positionFrames;
    memmove(s->inputBuffer, s->inputBuffer + (size_t)positionFrames * s->channelCount,
            (size_t)remainingFrames * s->channelCount * sizeof(short));
    s->inputFrameCount = remainingFrames;
}

static void changeSpeed(Sonic *s, double speed) {
    if (s->inputFrameCount < s->maxRequiredFrameCount) return;
    int frameCount = s->inputFrameCount;
    int positionFrames = 0;
    do {
        if (s->remainingInputToCopyFrameCount > 0) {
            positionFrames += copyInputToOutput(s, positionFrames);
        } else {
            int period = findPitchPeriod(s, positionFrames);
            if (speed > 1.0) {
                positionFrames += period + skipPitchPeriod(s, positionFrames, speed, period);
            } else {
                positionFrames += insertPitchPeriod(s, positionFrames, speed, period);
            }
        }
    } while (positionFrames + s->maxRequiredFrameCount <= frameCount);
    removeProcessedInputFrames(s, positionFrames);
}

static void processStreamInput(Sonic *s) {
    int originalOutputFrameCount = s->outputFrameCount;
    double sp = (double)(s->speed / s->pitch);
    float r = s->rate * s->pitch;
    if (sp > MINIMUM_SPEEDUP_RATE || sp < MINIMUM_SLOWDOWN_RATE) {
        changeSpeed(s, sp);
    } else {
        copyToOutput(s, 0, s->inputFrameCount);
        s->inputFrameCount = 0;
    }
    if (r != 1.0f) adjustRate(s, r, originalOutputFrameCount);
}

/* ------------------------------------------------------------------------------------ API */

EXPORT Sonic *m3s_create(int inputSampleRateHz, int channelCount, float speed, float pitch, int outputSampleRateHz) {
    Sonic *s = (Sonic *)calloc(1, sizeof(Sonic));
    if (!s) return NULL;
    s->inputSampleRateHz = inputSampleRateHz;
    s->channelCount = channelCount;
    s->speed = speed;
    s->pitch = pitch;
    s->rate = (float)inputSampleRateHz / outputSampleRateHz;
    s->minPeriod = inputSampleRateHz / MAXIMUM_PITCH;
    s->maxPeriod = inputSampleRateHz / MINIMUM_PITCH;
    s->maxRequiredFrameCount = 2 * s->maxPeriod;
    s->inputCap = s->outputCap = s->pitchCap = s->maxRequiredFrameCount;
    s->downSampleBuffer = (short *)calloc((size_t)s->maxRequiredFrameCount, sizeof(short));
    s->inputBuffer = (short *)calloc((size_t)s->maxRequiredFrameCount * channelCount, sizeof(short));
    s->outputBuffer = (short *)calloc((size_t)s->maxRequiredFrameCount * channelCount, sizeof(short));
    s->pitchBuffer = (short *)calloc((size_t)s->maxRequiredFrameCount * channelCount, sizeof(short));
    return s;
}

EXPORT void m3s_destroy(Sonic *s) {
    if (!s) return;
    free(s->downSampleBuffer);
    free(s->inputBuffer);
    free(s->outputBuffer);
    free(s->pitchBuffer);
    free(s);
}

/* queueInput: interleaved 16-bit frames */
EXPORT void m3s_queue_input(Sonic *s, const short *samples, int frames) {
    ENSURE_INPUT(s, frames);
    memcpy(s->inputBuffer + (size_t)s->inputFrameCount * s->channelCount, samples,
           (size_t)frames * s->channelCount * sizeof(short));
    s->inputFrameCount += frames;
    processStreamInput(s);
}

EXPORT int m3s_output_frames(Sonic *s) { return s->outputFrameCount; }

/* getOutput: copy up to maxFrames frames, returns the number copied */
EXPORT int m3s_read_output(Sonic *s, short *dst, int maxFrames) {
    int framesToRead = maxFrames < s->outputFrameCount ? maxFrames : s->outputFrameCount;
    memcpy(dst, s->outputBuffer, (size_t)framesToRead * s->channelCount * sizeof(short));
    s->outputFrameCount -= framesToRead;
    memmove(s->outputBuffer, s->outputBuffer + (size_t)framesToRead * s->channelCount,
            (size_t)s->outputFrameCount * s->channelCount * sizeof(short));
    return framesToRead;
}

EXPORT void m3s_queue_end_of_stream(Sonic *s) {
    int remainingFrameCount = s->inputFrameCount;
    double sp = (double)(s->speed / s->pitch);
    double r = (double)(s->rate * s->pitch);
    int adjustedRemainingFrames = remainingFrameCount - s->remainingInputToCopyFrameCount;
    int expectedOutputFrames = s->outputFrameCount
        + (int)((adjustedRemainingFrames / sp + s->remainingInputToCopyFrameCount
                 + s->accumulatedSpeedAdjustmentError + s->pitchFrameCount) / r + 0.5);
    s->accumulatedSpeedAdjustmentError = 0;
    ENSURE_INPUT(s, remainingFrameCount + 2 * s->maxRequiredFrameCount);
    memset(s->inputBuffer + (size_t)remainingFrameCount * s->channelCount, 0,
           (size_t)2 * s->maxRequiredFrameCount * s->channelCount * sizeof(short));
    s->inputFrameCount += 2 * s->maxRequiredFrameCount;
    processStreamInput(s);
    if (s->outputFrameCount > expectedOutputFrames) {
        s->outputFrameCount = expectedOutputFrames > 0 ? expectedOutputFrames : 0;
    }
    s->inputFrameCount = 0;
    s->remainingInputToCopyFrameCount = 0;
    s->pitchFrameCount = 0;
}

EXPORT void m3s_flush(Sonic *s) {
    s->inputFrameCount = s->outputFrameCount = s->pitchFrameCount = 0;
    s->oldRatePosition = s->newRatePosition = 0;
    s->remainingInputToCopyFrameCount = 0;
    s->prevPeriod = 0;
    s->accumulatedSpeedAdjustmentError = 0;
    s->prevMinDiff = s->minDiff = s->maxDiff = 0;
}
