"""Gợi ý NÊN MUA / NÊN BÁN: chấm điểm nhiều chỉ báo trên từng coin + khung.

Chỉ dùng nến ĐÃ ĐÓNG để tín hiệu không nhảy qua lại trong lúc nến đang chạy.
Điểm từ -100 (bán mạnh) đến +100 (mua mạnh). Đây là gợi ý tham khảo, không phải lời khuyên đầu tư.
"""
from datetime import datetime, timezone

from .indicators import atr_adx, bollinger, ema_series, macd, rsi_series, stoch_rsi
from .signals import VN, fmt_price, tv_link

MIN_CANDLES = 210                      # đủ cho EMA200
TF_WEIGHT = {"15m": 0.5, "30m": 0.5, "1h": 1, "2h": 1.5, "4h": 2, "1d": 3}
STRONG, WEAK, HOLD = 50, 20, 10        # ngưỡng mạnh / thường / giữ trạng thái (chống nhấp nháy)
LABEL = {"strong_buy": "NÊN MUA (mạnh)", "buy": "NÊN MUA", "neutral": "TRUNG LẬP",
         "sell": "NÊN BÁN", "strong_sell": "NÊN BÁN (mạnh)"}
ICON = {"strong_buy": "🟢🟢", "buy": "🟢", "neutral": "⚪", "sell": "🔴", "strong_sell": "🔴🔴"}


def rating_of(score):
    if score >= STRONG:
        return "strong_buy"
    if score >= WEAK:
        return "buy"
    if score <= -STRONG:
        return "strong_sell"
    if score <= -WEAK:
        return "sell"
    return "neutral"


def direction(rating):
    return 1 if rating.endswith("buy") else -1 if rating.endswith("sell") else 0


def advise(symbol, tf, candles, cfg):
    """Chấm điểm 1 coin trên 1 khung. `candles` gồm cả nến đang chạy ở cuối (sẽ bị bỏ)."""
    closed = candles[:-1]
    if len(closed) < MIN_CANDLES:
        raise ValueError(f"Cần ít nhất {MIN_CANDLES} nến đã đóng, đang có {len(closed)}")
    closes = [c["c"] for c in closed]
    price = closes[-1]
    parts = []

    def add(name, pts, note):
        parts.append({"name": name, "points": round(pts, 1), "note": note})

    # 1. Sức mạnh xu hướng ADX/DI (tối đa ±15)
    atr, adx, pdi, mdi = atr_adx(closed)
    strong_trend = 0                                   # +1 tăng mạnh, -1 giảm mạnh
    ranging = adx < 20                                 # đi ngang: EMA và MACD chỉ tính nửa điểm
    if adx >= 20:
        sign = 1 if pdi > mdi else -1
        pts = sign * (15 if adx >= 30 else 10)
        if adx >= 30:
            strong_trend = sign
        add("ADX/DI", pts, f"ADX {adx:.0f}: xu hướng {'tăng' if sign > 0 else 'giảm'} "
                           f"{'mạnh' if adx >= 30 else 'vừa'}")
    else:
        add("ADX/DI", 0, f"ADX {adx:.0f}: thị trường đi ngang, tín hiệu xu hướng kém tin cậy")

    # 2. Xu hướng theo EMA 20/50/200 (tối đa ±30)
    e20, e50, e200 = (ema_series(closes, n)[-1] for n in (20, 50, 200))
    pts = (10 if price > e200 else -10) + (10 if e20 > e50 else -10) + (10 if e50 > e200 else -10)
    note = {30: "xu hướng tăng rõ (giá > EMA200, EMA20 > EMA50 > EMA200)",
            -30: "xu hướng giảm rõ (giá < EMA200, EMA20 < EMA50 < EMA200)"}.get(
        pts, f"xu hướng lẫn lộn (giá {'trên' if price > e200 else 'dưới'} EMA200, "
             f"EMA20 {'trên' if e20 > e50 else 'dưới'} EMA50)")
    add("EMA 20/50/200", pts / 2 if ranging else pts, note)

    # 3. MACD 12/26/9 (tối đa ±20)
    m, sig, hist, prev_hist = macd(closes)
    pts = (10 if m > sig else -10) + (5 if hist > prev_hist else -5) + (5 if m > 0 else -5)
    cross = (" (vừa cắt lên)" if hist > 0 >= prev_hist else " (vừa cắt xuống)" if hist < 0 <= prev_hist else "")
    add("MACD", pts / 2 if ranging else pts, f"MACD {'trên' if m > sig else 'dưới'} đường tín hiệu{cross}, "
                     f"động lượng {'tăng' if hist > prev_hist else 'giảm'} dần")

    # Tín hiệu đảo chiều (quá mua/quá bán) đi ngược xu hướng mạnh thì chỉ tính 1/3 điểm.
    def reversal(pts):
        return pts / 3 if pts * strong_trend < 0 else pts

    # 4. RSI 14 (tối đa ±15)
    r = rsi_series(closes, cfg.rsi_period)[-1]
    if r <= cfg.rsi_low:
        add("RSI", reversal(15), f"RSI {r:.0f}: quá bán")
    elif r >= cfg.rsi_high:
        add("RSI", reversal(-15), f"RSI {r:.0f}: quá mua")
    else:
        add("RSI", max(-5, min(5, (r - 50) / 4)), f"RSI {r:.0f}: {'nghiêng mua' if r > 50 else 'nghiêng bán'}")

    # 5. Stochastic RSI (tối đa ±10)
    k, d, pk, pd = stoch_rsi(closes, cfg.rsi_period)
    if k > d and pk <= pd and pk < 20:
        add("Stoch RSI", reversal(10), f"K {k:.0f} cắt lên D từ vùng quá bán")
    elif k < d and pk >= pd and pk > 80:
        add("Stoch RSI", reversal(-10), f"K {k:.0f} cắt xuống D từ vùng quá mua")
    elif k < 20:
        add("Stoch RSI", reversal(3), f"K {k:.0f}: vùng quá bán")
    elif k > 80:
        add("Stoch RSI", reversal(-3), f"K {k:.0f}: vùng quá mua")
    else:
        add("Stoch RSI", 0, f"K {k:.0f}: trung tính")

    # 6. Bollinger Bands %B (tối đa ±10)
    mid, upper, lower = bollinger(closes, cfg.bb_period, cfg.bb_mult)
    pctb = (price - lower) / (upper - lower) if upper > lower else 0.5
    if pctb <= 0.05:
        add("Bollinger", reversal(10), "giá ở BB dưới")
    elif pctb <= 0.2:
        add("Bollinger", reversal(5), "giá gần BB dưới")
    elif pctb >= 0.95:
        add("Bollinger", reversal(-10), "giá ở BB trên")
    elif pctb >= 0.8:
        add("Bollinger", reversal(-5), "giá gần BB trên")
    else:
        add("Bollinger", 0, f"giá trong dải (%B {pctb:.2f})")

    # 7. Khối lượng xác nhận (±5)
    vols = [c["v"] for c in closed]
    avg = sum(vols[-21:-1]) / 20
    last = closed[-1]
    ratio = vols[-1] / avg if avg else 0
    if ratio >= 1.5 and last["c"] != last["o"]:
        up = last["c"] > last["o"]
        add("Khối lượng", 5 if up else -5, f"nến {'tăng' if up else 'giảm'} với khối lượng gấp {ratio:.1f} lần TB20")
    else:
        add("Khối lượng", 0, f"khối lượng bình thường ({ratio:.1f} lần TB20)")

    score = max(-100, min(100, round(sum(p["points"] for p in parts))))
    return {"symbol": symbol, "tf": tf, "candle": last["t"], "price": price, "score": score,
            "rating": rating_of(score), "parts": parts, "atr": atr, "rsi": r, "adx": adx}


def overall(items):
    """Điểm tổng hợp mỗi coin: trung bình có trọng số theo khung (khung lớn nặng hơn)."""
    out = {}
    for sym in dict.fromkeys(i["symbol"] for i in items):
        rows = [i for i in items if i["symbol"] == sym]
        w = sum(TF_WEIGHT.get(i["tf"], 1) for i in rows)
        score = round(sum(i["score"] * TF_WEIGHT.get(i["tf"], 1) for i in rows) / w)
        out[sym] = {"score": score, "rating": rating_of(score)}
    return out


def decide_advice(items, state, now=None):
    """Trả về (gợi ý cần gửi, state mới).

    Chỉ gửi khi 1 coin + khung chuyển sang MUA hoặc BÁN, hoặc nâng lên mức mạnh.
    Đã ở MUA/BÁN thì giữ trạng thái cho tới khi điểm lùi qua ngưỡng HOLD, tránh báo đi báo lại.
    """
    now = now or datetime.now(timezone.utc)
    state = dict(state)
    alerts = []
    for it in items:
        key = f"advice|{it['symbol']}|{it['tf']}"
        prev = (state.get(key) or {}).get("rating", "neutral")
        rating = it["rating"]
        if rating == "neutral" and direction(prev) * it["score"] >= HOLD:
            rating = "buy" if direction(prev) > 0 else "sell"      # vẫn giữ hướng cũ
        new_dir = direction(rating) != 0 and direction(rating) != direction(prev)
        escalated = rating.startswith("strong") and not prev.startswith("strong")
        if new_dir or escalated:
            alerts.append({**it, "type": "advice", "ts": int(now.timestamp()),
                           "time": now.astimezone(VN).strftime("%Y-%m-%d %H:%M")})
        state[key] = {"rating": rating, "candle": it["candle"]}
    return alerts, state


def levels(a):
    """Mức tham khảo theo ATR: cắt lỗ 1.5 ATR, chốt lời 1.5 và 3 ATR."""
    sign = direction(a["rating"])
    return {"sl": a["price"] - sign * 1.5 * a["atr"], "tp1": a["price"] + sign * 1.5 * a["atr"],
            "tp2": a["price"] + sign * 3 * a["atr"]}


def format_advice(a, summary):
    coin = a["symbol"].replace("USDT", "")
    lv = levels(a)
    top = sorted((p for p in a["parts"] if p["points"]), key=lambda p: -abs(p["points"]))[:4]
    lines = [f"{ICON[a['rating']]} {coin} {a['tf']} — {LABEL[a['rating']]} (điểm {a['score']:+d}/100)",
             f"Giá đóng nến {fmt_price(a['price'])}"]
    lines += [f"{'＋' if p['points'] > 0 else '－'} {p['name']}: {p['note']}" for p in top]
    lines.append(f"Tham khảo: cắt lỗ {fmt_price(lv['sl'])} | chốt lời {fmt_price(lv['tp1'])} / {fmt_price(lv['tp2'])}")
    o = summary.get(a["symbol"])
    if o:
        lines.append(f"Tổng hợp các khung: {LABEL[o['rating']]} ({o['score']:+d})")
    lines.append(tv_link(a["symbol"], a["tf"]))
    return "\n".join(lines)


def format_advice_message(alerts, summary, cfg):
    parts = [f"🧭 Gợi ý mua/bán — {alerts[0]['time']} (giờ VN)"]
    parts += [format_advice(a, summary) for a in alerts]
    parts.append("⚠️ Chỉ là gợi ý từ chỉ báo kỹ thuật, không phải lời khuyên đầu tư. Tự quản lý vốn và rủi ro.")
    if cfg.dashboard_url:
        parts.append(f"Chi tiết: {cfg.dashboard_url.rstrip('/')}/signals.html")
    return "\n\n".join(parts)


def advice_subject(alerts):
    names = [f"{a['symbol'].replace('USDT', '')} {a['tf']} {'MUA' if direction(a['rating']) > 0 else 'BÁN'}"
             for a in alerts]
    more = f" (+{len(names) - 3})" if len(names) > 3 else ""
    return "[Trading] Gợi ý: " + ", ".join(names[:3]) + more
