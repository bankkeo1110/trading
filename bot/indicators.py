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
