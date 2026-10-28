package com.alexvulcu.videospeedcontrol.core

import java.math.BigInteger

/** Exact fraction, like Python's `fractions.Fraction` (stored as "240000/1001" in .cst files). */
class Rational private constructor(val num: BigInteger, val den: BigInteger) : Comparable<Rational> {

    operator fun plus(o: Rational) = of(num * o.den + o.num * den, den * o.den)
    operator fun minus(o: Rational) = of(num * o.den - o.num * den, den * o.den)
    operator fun times(o: Rational) = of(num * o.num, den * o.den)
    operator fun div(o: Rational) = of(num * o.den, den * o.num)
    operator fun plus(o: Long) = this + of(o)
    operator fun minus(o: Long) = this - of(o)
    operator fun times(o: Long) = this * of(o)
    operator fun div(o: Long) = this / of(o)
    operator fun unaryMinus() = of(-num, den)

    override fun compareTo(other: Rational) = (num * other.den).compareTo(other.num * den)
    override fun equals(other: Any?) = other is Rational && num == other.num && den == other.den
    override fun hashCode() = 31 * num.hashCode() + den.hashCode()

    fun toDouble(): Double = num.toDouble() / den.toDouble()
    /** Rounded towards minus infinity, like Python's `//`. */
    fun floor(): Long = num.divide(den).let { if (num.signum() < 0 && it * den != num) it - BigInteger.ONE else it }.toLong()

    /** Same text as Python's `str(Fraction)`: "30" or "30000/1001". */
    override fun toString() = if (den == BigInteger.ONE) "$num" else "$num/$den"

    /** Closest fraction with denominator ≤ maxDen (Python's `limit_denominator`). */
    fun limitDenominator(maxDen: Long): Rational {
        val max = BigInteger.valueOf(maxDen)
        if (den <= max) return this
        var p0 = BigInteger.ZERO; var q0 = BigInteger.ONE
        var p1 = BigInteger.ONE; var q1 = BigInteger.ZERO
        var n = num; var d = den
        while (true) {
            val a = n.divide(d)
            val q2 = q0 + a * q1
            if (q2 > max) break
            val p2 = p0 + a * p1
            p0 = p1; q0 = q1; p1 = p2; q1 = q2
            val r = n - a * d
            n = d; d = r
            if (d.signum() == 0) break
        }
        val k = (max - q0).divide(q1)
        val b1 = of(p0 + k * p1, q0 + k * q1)
        val b2 = of(p1, q1)
        return if ((b2 - this).abs() <= (b1 - this).abs()) b2 else b1
    }

    fun abs() = if (num.signum() < 0) -this else this

    /** Nearest integer, ties to even – Python's round(Fraction) (used by the desktop's plans). */
    fun roundHalfEven(): Long {
        val f = floor()
        val diff = this - f
        val half = of(1, 2)
        return when {
            diff < half -> f
            diff > half -> f + 1
            else -> if (f % 2 == 0L) f else f + 1
        }
    }

    companion object {
        val ZERO = of(0)
        val ONE = of(1)

        fun of(n: Long, d: Long = 1) = of(BigInteger.valueOf(n), BigInteger.valueOf(d))

        fun of(n: BigInteger, d: BigInteger): Rational {
            require(d.signum() != 0) { "denominator is zero" }
            val g = n.gcd(d).let { if (it.signum() == 0) BigInteger.ONE else it }
            val s = if (d.signum() < 0) BigInteger.ONE.negate() else BigInteger.ONE
            return Rational(n / g * s, d / g * s)
        }

        /** "30000/1001", "29.97", "30" → Rational (decimals exactly, like Fraction("29.97")). */
        fun parse(text: String): Rational {
            val t = text.trim()
            if ('/' in t) {
                val (a, b) = t.split('/', limit = 2)
                return parse(a) / parse(b)
            }
            val bd = t.toBigDecimal()
            return if (bd.scale() <= 0) of(bd.toBigIntegerExact(), BigInteger.ONE)
            else of(bd.unscaledValue(), BigInteger.TEN.pow(bd.scale()))
        }

        fun fromDouble(v: Double, maxDen: Long = 1001) = parse(v.toBigDecimal().toPlainString()).limitDenominator(maxDen)
    }
}
