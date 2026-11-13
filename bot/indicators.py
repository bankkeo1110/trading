"""Chỉ báo kỹ thuật: Bollinger Bands (giống TradingView) và RSI (Wilder)."""
from math import sqrt


def bollinger(closes, period=20, mult=2.0):
    """Trả về (mid, upper, lower) của nến cuối. Dùng độ lệch chuẩn tổng thể như TradingView."""
    if len(closes) < period:
        raise ValueError(f"Cần ít nhất {period} nến, đang có {len(closes)}")
    w = closes[-period:]
    mid = sum(w) / period
    sd = sqrt(sum((x - mid) ** 2 for x in w) / period)
    return mid, mid + mult * sd, mid - mult * sd


def bandwidths(closes, period=20, mult=2.0, lookback=120):
    """Bề rộng dải tương đối (upper-lower)/mid cho tối đa `lookback` nến gần nhất."""
    out = []
    start = max(period, len(closes) - lookback + 1)
    for end in range(start, len(closes) + 1):
        mid, up, lo = bollinger(closes[:end], period, mult)
        out.append((up - lo) / mid if mid else 0.0)
    return out


def rsi(closes, period=14):
    """RSI làm mượt kiểu Wilder. Trả về None nếu chưa đủ dữ liệu."""
    if len(closes) <= period:
        return None
    gains = losses = 0.0
    for i in range(1, period + 1):
        d = closes[i] - closes[i - 1]
        gains += max(d, 0)
        losses += max(-d, 0)
    ag, al = gains / period, losses / period
    for i in range(period + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        ag = (ag * (period - 1) + max(d, 0)) / period
        al = (al * (period - 1) + max(-d, 0)) / period
    if al == 0:
        return 100.0
    return 100 - 100 / (1 + ag / al)


# ---- Chuỗi chỉ báo dùng cho gợi ý mua/bán (bot/advisor.py) -------------------
# Mỗi hàm trả về danh sách cùng độ dài với đầu vào; phần chưa đủ dữ liệu là None.

def ema_series(values, period):
    """EMA khởi tạo bằng SMA của `period` giá trị đầu (giống TradingView)."""
    out = [None] * len(values)
    if len(values) < period:
        return out
    k = 2 / (period + 1)
    e = sum(values[:period]) / period
    out[period - 1] = e
    for i in range(period, len(values)):
        e = values[i] * k + e * (1 - k)
        out[i] = e
    return out


def rsi_series(closes, period=14):
    out = [None] * len(closes)
    if len(closes) <= period:
        return out
    ag = al = 0.0
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        g, l = max(d, 0), max(-d, 0)
        if i <= period:
            ag += g / period
            al += l / period
        else:
            ag = (ag * (period - 1) + g) / period
            al = (al * (period - 1) + l) / period
        if i >= period:
            out[i] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


def macd(closes, fast=12, slow=26, signal=9):
    """Trả về (macd, signal, histogram) của nến cuối và histogram nến trước; None nếu thiếu dữ liệu."""
    ef, es = ema_series(closes, fast), ema_series(closes, slow)
    line = [f - s for f, s in zip(ef, es) if f is not None and s is not None]
    sig = ema_series(line, signal)
    if len(line) < 2 or sig[-2] is None:
        return None
    return line[-1], sig[-1], line[-1] - sig[-1], line[-2] - sig[-2]


def _sma_tail(values, n, end):
    w = values[end - n:end]
    return sum(w) / n


def stoch_rsi(closes, rsi_period=14, stoch_period=14, k_smooth=3, d_smooth=3):
    """Trả về (K, D, K trước, D trước) trên thang 0-100; None nếu thiếu dữ liệu."""
    r = [x for x in rsi_series(closes, rsi_period) if x is not None]
    raw = []
    for i in range(stoch_period, len(r) + 1):
        w = r[i - stoch_period:i]
        lo, hi = min(w), max(w)
        raw.append(50.0 if hi == lo else (w[-1] - lo) / (hi - lo) * 100)
    if len(raw) < k_smooth + d_smooth:
        return None
    k = [_sma_tail(raw, k_smooth, i) for i in range(k_smooth, len(raw) + 1)]
    d = [_sma_tail(k, d_smooth, i) for i in range(d_smooth, len(k) + 1)]
    return k[-1], d[-1], k[-2], d[-2]


def atr_adx(candles, period=14):
    """Trả về (ATR, ADX, +DI, -DI) làm mượt kiểu Wilder; None nếu thiếu dữ liệu."""
    if len(candles) < 2 * period + 1:
        return None
    trs, pdm, mdm = [], [], []
    for prev, c in zip(candles, candles[1:]):
        up, down = c["h"] - prev["h"], prev["l"] - c["l"]
        pdm.append(up if up > down and up > 0 else 0.0)
        mdm.append(down if down > up and down > 0 else 0.0)
        trs.append(max(c["h"] - c["l"], abs(c["h"] - prev["c"]), abs(c["l"] - prev["c"])))
    atr, sp, sm = sum(trs[:period]), sum(pdm[:period]), sum(mdm[:period])
    dxs = []
    pdi = mdi = 0.0
    for i in range(period - 1, len(trs)):
        if i >= period:
            atr = atr - atr / period + trs[i]
            sp = sp - sp / period + pdm[i]
            sm = sm - sm / period + mdm[i]
        pdi = 100 * sp / atr if atr else 0.0
        mdi = 100 * sm / atr if atr else 0.0
        dxs.append(100 * abs(pdi - mdi) / (pdi + mdi) if pdi + mdi else 0.0)
    adx = sum(dxs[:period]) / period
    for dx in dxs[period:]:
        adx = (adx * (period - 1) + dx) / period
    return atr / period, adx, pdi, mdi
