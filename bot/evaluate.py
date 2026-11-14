"""Chấm đúng/sai các gợi ý đã gửi, bằng nến ĐÃ ĐÓNG sau nến tín hiệu.

MUA/BÁN: win nếu chạm chốt lời 1 trước cắt lỗ, loss nếu chạm cắt lỗ trước (nến chạm cả hai tính loss),
expired nếu sau HORIZON nến chưa chạm mức nào. CANH MUA/BÁN: right/wrong theo giá đóng sau WATCH_BARS nến.
skip: không chấm được (thiếu mức giá, hoặc nến tín hiệu đã trôi khỏi dữ liệu).
"""
from .advisor import direction

HORIZON = 24
WATCH_BARS = 12


def _pct(price, entry, sign):
    return round((price - entry) / entry * sign * 100, 2)


def _judge(s, after):
    """Trả về (outcome, giá thoát, số nến) hoặc None nếu chưa đủ nến."""
    entry, rating = s["price"], s["rating"]
    if rating.startswith("watch"):
        if len(after) < WATCH_BARS:
            return None
        c = after[WATCH_BARS - 1]["c"]
        sign = 1 if rating == "watch_buy" else -1
        return ("right" if (c - entry) * sign > 0 else "wrong"), c, WATCH_BARS, sign
    sign = direction(rating)
    if not sign or "sl" not in s or "tp1" not in s:
        return "skip", None, 0, sign
    for i, c in enumerate(after[:HORIZON], 1):
        hit_sl = c["l"] <= s["sl"] if sign > 0 else c["h"] >= s["sl"]
        hit_tp = c["h"] >= s["tp1"] if sign > 0 else c["l"] <= s["tp1"]
        if hit_sl:
            return "loss", s["sl"], i, sign
        if hit_tp:
            return "win", s["tp1"], i, sign
    if len(after) < HORIZON:
        return None
    return "expired", after[HORIZON - 1]["c"], HORIZON, sign


def evaluate(signals, candles_by):
    """Chấm tại chỗ các gợi ý chưa có `outcome`. candles_by[(symbol, tf)] = nến, phần tử cuối là nến đang chạy.
    Trả về số tín hiệu vừa có kết quả."""
    done = 0
    for s in signals:
        if s.get("type") != "advice" or s.get("outcome"):
            continue
        rows = candles_by.get((s["symbol"], s["tf"]))
        if not rows:
            continue
        closed = rows[:-1]
        idx = next((i for i, c in enumerate(closed) if c["t"] == s["candle"]), None)
        if idx is None:
            if closed and closed[0]["t"] > s["candle"]:
                s.update(outcome="skip", pnl_pct=None, bars=0)
                done += 1
            continue
        res = _judge(s, closed[idx + 1:])
        if res is None:
            continue
        outcome, exit_price, bars, sign = res
        s.update(outcome=outcome, bars=bars,
                 pnl_pct=None if exit_price is None else _pct(exit_price, s["price"], sign))
        done += 1
    return done
