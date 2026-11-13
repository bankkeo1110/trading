"""Gợi ý NÊN MUA / NÊN BÁN: chấm điểm nhiều chỉ báo trên từng coin + khung.

Hai kiểu tín hiệu: thuận xu hướng (EMA, MACD, ADX) và đảo chiều (quá bán/quá mua + xác nhận).
Quá bán thì không gợi ý bán mà chuyển sang "canh mua"; có xác nhận đảo chiều mới báo NÊN MUA.

Chỉ dùng nến ĐÃ ĐÓNG để tín hiệu không nhảy qua lại trong lúc nến đang chạy.
Điểm từ -100 (bán mạnh) đến +100 (mua mạnh). Đây là gợi ý tham khảo, không phải lời khuyên đầu tư.
"""
from datetime import datetime, timezone

from .indicators import atr_adx, bollinger, ema_series, macd, rsi_series, stoch_rsi
from .signals import VN, fmt_price, tv_link

MIN_CANDLES = 210                      # đủ cho EMA200
TF_WEIGHT = {"15m": 0.5, "30m": 0.5, "1h": 1, "2h": 1.5, "4h": 2, "1d": 3}
TF_MS = {"15m": 900_000, "30m": 1_800_000, "1h": 3_600_000, "2h": 7_200_000, "4h": 14_400_000, "1d": 86_400_000}
STRONG, WEAK, HOLD = 50, 20, 10        # ngưỡng mạnh / thường / giữ trạng thái (chống nhấp nháy)
RECENT = 6                             # số nến gần nhất còn tính là "vừa quá bán/quá mua"
WATCH_GAP = 6                          # không nhắc lại "canh mua/canh bán" trong vòng N nến
LABEL = {"strong_buy": "NÊN MUA (mạnh)", "buy": "NÊN MUA", "watch_buy": "QUÁ BÁN — CANH MUA",
         "neutral": "TRUNG LẬP", "watch_sell": "QUÁ MUA — CANH BÁN",
         "sell": "NÊN BÁN", "strong_sell": "NÊN BÁN (mạnh)"}
ICON = {"strong_buy": "🟢🟢", "buy": "🟢", "watch_buy": "🟡", "neutral": "⚪", "watch_sell": "🟠",
        "sell": "🔴", "strong_sell": "🔴🔴"}


def rating_of(score, zone=0):
    """zone = +1 đang/vừa quá bán, -1 đang/vừa quá mua.

    Không bao giờ gợi ý BÁN khi đang quá bán (bán đuổi ở đáy) hay MUA khi đang quá mua (mua đuổi ở đỉnh):
    lúc đó chuyển thành "canh mua"/"canh bán" cho tới khi có xác nhận đảo chiều đẩy điểm qua ngưỡng.
    """
    if zone > 0 and score < WEAK:
        return "watch_buy"
    if zone < 0 and score > -WEAK:
        return "watch_sell"
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
    """+1 MUA, -1 BÁN, 0 trung lập hoặc mới chỉ "canh"."""
    return 1 if rating in ("buy", "strong_buy") else -1 if rating in ("sell", "strong_sell") else 0


def _group(rating):
    return {"strong_buy": "buy", "strong_sell": "sell"}.get(rating, rating)


def _zone_now(r, cfg):
    return 1 if r <= cfg.rsi_low else -1 if r >= cfg.rsi_high else 0


def _confirmations(zone, closed, rs, cfg):
    """Dấu hiệu giá đã bắt đầu đảo chiều sau khi quá bán (zone=+1) hoặc quá mua (zone=-1)."""
    last, prev = closed[-1], closed[-2]
    found = []
    if zone > 0:
        if last["c"] > last["o"] and last["c"] > prev["h"]:
            found.append("nến tăng đóng trên đỉnh nến trước")
        if rs[-1] > cfg.rsi_low and rs[-1] > rs[-2] and min(rs[-RECENT:-1]) <= cfg.rsi_low:
            found.append(f"RSI quay lên trên {cfg.rsi_low:g}")
        ext = [c["l"] for c in closed]
        i_new = min(range(len(ext) - 3, len(ext)), key=ext.__getitem__)
        i_old = min(range(len(ext) - 30, len(ext) - 5), key=ext.__getitem__)
        if ext[i_new] < ext[i_old] and rs[i_old] <= 40 and rs[i_new] > rs[i_old] + 3:
            found.append("phân kỳ tăng (giá tạo đáy thấp hơn nhưng RSI cao hơn)")
    else:
        if last["c"] < last["o"] and last["c"] < prev["l"]:
            found.append("nến giảm đóng dưới đáy nến trước")
        if rs[-1] < cfg.rsi_high and rs[-1] < rs[-2] and max(rs[-RECENT:-1]) >= cfg.rsi_high:
            found.append(f"RSI quay xuống dưới {cfg.rsi_high:g}")
        ext = [c["h"] for c in closed]
        i_new = max(range(len(ext) - 3, len(ext)), key=ext.__getitem__)
        i_old = max(range(len(ext) - 30, len(ext) - 5), key=ext.__getitem__)
        if ext[i_new] > ext[i_old] and rs[i_old] >= 60 and rs[i_new] < rs[i_old] - 3:
            found.append("phân kỳ giảm (giá tạo đỉnh cao hơn nhưng RSI thấp hơn)")
    return found


def _finish(item):
    item["score"] = max(-100, min(100, round(sum(p["points"] for p in item["parts"]))))
    item["rating"] = rating_of(item["score"], item["zone"])
    return item


def advise(symbol, tf, candles, cfg):
    """Chấm điểm 1 coin trên 1 khung. `candles` gồm cả nến đang chạy ở cuối (sẽ bị bỏ)."""
    closed = candles[:-1]
    if len(closed) < MIN_CANDLES:
        raise ValueError(f"Cần ít nhất {MIN_CANDLES} nến đã đóng, đang có {len(closed)}")
    closes = [c["c"] for c in closed]
    price, last = closes[-1], closed[-1]

    # ---- Tính chỉ báo ----
    e20, e50, e200 = (ema_series(closes, n)[-1] for n in (20, 50, 200))
    atr, adx, pdi, mdi = atr_adx(closed)
    m, sig, hist, prev_hist = macd(closes)
    rs = rsi_series(closes, cfg.rsi_period)
    r = rs[-1]
    k, d, pk, pd = stoch_rsi(closes, cfg.rsi_period)
    mid, upper, lower = bollinger(closes, cfg.bb_period, cfg.bb_mult)
    pctb = (price - lower) / (upper - lower) if upper > lower else 0.5
    vols = [c["v"] for c in closed]
    avg_vol = sum(vols[-21:-1]) / 20
    vol_ratio = vols[-1] / avg_vol if avg_vol else 0

    # ---- Vùng quá bán / quá mua (đang ở trong vùng, hoặc vừa ra khỏi trong RECENT nến) ----
    zone = _zone_now(r, cfg)
    in_zone = zone != 0
    if not zone:
        recent = rs[-RECENT:]
        lo_i = max((i for i, x in enumerate(recent) if x <= cfg.rsi_low), default=-1)
        hi_i = max((i for i, x in enumerate(recent) if x >= cfg.rsi_high), default=-1)
        zone = 0 if lo_i == hi_i else 1 if lo_i > hi_i else -1
    confirms = _confirmations(zone, closed, rs, cfg) if zone else []
    ranging = adx < 20

    parts = []

    def add(name, pts, note):
        parts.append({"name": name, "points": round(pts, 1), "note": note})

    def trend(name, pts, note):
        """Điểm theo xu hướng: đi ngang tính 1/2; ngược với vùng quá bán/quá mua tính 1/2,
        có xác nhận đảo chiều thì còn 1/3 (xu hướng cũ đã đi quá xa, đuổi theo dễ dính đảo chiều)."""
        if ranging:
            pts /= 2
        if pts * zone < 0:
            pts /= 3 if confirms else 2
            note += f" — giảm trọng số vì {'quá bán' if zone > 0 else 'quá mua'}"
        add(name, pts, note)

    # 1. Sức mạnh xu hướng ADX/DI (tối đa ±15)
    if not ranging:
        sign = 1 if pdi > mdi else -1
        trend("ADX/DI", sign * (15 if adx >= 30 else 10),
              f"ADX {adx:.0f}: xu hướng {'tăng' if sign > 0 else 'giảm'} {'mạnh' if adx >= 30 else 'vừa'}")
    else:
        add("ADX/DI", 0, f"ADX {adx:.0f}: thị trường đi ngang, tín hiệu xu hướng kém tin cậy")

    # 2. Xu hướng theo EMA 20/50/200 (tối đa ±30)
    pts = (10 if price > e200 else -10) + (10 if e20 > e50 else -10) + (10 if e50 > e200 else -10)
    note = {30: "xu hướng tăng rõ (giá > EMA200, EMA20 > EMA50 > EMA200)",
            -30: "xu hướng giảm rõ (giá < EMA200, EMA20 < EMA50 < EMA200)"}.get(
        pts, f"xu hướng lẫn lộn (giá {'trên' if price > e200 else 'dưới'} EMA200, "
             f"EMA20 {'trên' if e20 > e50 else 'dưới'} EMA50)")
    ema_trend = pts // 30                               # +1 tăng rõ, -1 giảm rõ, 0 lẫn lộn
    trend("EMA 20/50/200", pts, note)

    # 3. MACD 12/26/9 (tối đa ±20)
    pts = (10 if m > sig else -10) + (5 if hist > prev_hist else -5) + (5 if m > 0 else -5)
    cross = (" (vừa cắt lên)" if hist > 0 >= prev_hist else " (vừa cắt xuống)" if hist < 0 <= prev_hist else "")
    trend("MACD", pts, f"MACD {'trên' if m > sig else 'dưới'} đường tín hiệu{cross}, "
                       f"động lượng {'tăng' if hist > prev_hist else 'giảm'} dần")

    # 4. RSI 14 (tối đa ±15)
    if r <= cfg.rsi_low:
        add("RSI", 15, f"RSI {r:.0f}: quá bán")
    elif r >= cfg.rsi_high:
        add("RSI", -15, f"RSI {r:.0f}: quá mua")
    else:
        add("RSI", max(-5, min(5, (r - 50) / 4)), f"RSI {r:.0f}: {'nghiêng mua' if r > 50 else 'nghiêng bán'}")

    # 5. Stochastic RSI (tối đa ±10)
    if k > d and pk <= pd and pk < 20:
        add("Stoch RSI", 10, f"K {k:.0f} cắt lên D từ vùng quá bán")
    elif k < d and pk >= pd and pk > 80:
        add("Stoch RSI", -10, f"K {k:.0f} cắt xuống D từ vùng quá mua")
    elif k < 20:
        add("Stoch RSI", 3, f"K {k:.0f}: vùng quá bán")
    elif k > 80:
        add("Stoch RSI", -3, f"K {k:.0f}: vùng quá mua")
    else:
        add("Stoch RSI", 0, f"K {k:.0f}: trung tính")

    # 6. Bollinger Bands %B (tối đa ±10)
    if pctb <= 0.05:
        add("Bollinger", 10, "giá ở BB dưới")
    elif pctb <= 0.2:
        add("Bollinger", 5, "giá gần BB dưới")
    elif pctb >= 0.95:
        add("Bollinger", -10, "giá ở BB trên")
    elif pctb >= 0.8:
        add("Bollinger", -5, "giá gần BB trên")
    else:
        add("Bollinger", 0, f"giá trong dải (%B {pctb:.2f})")

    # 7. Khối lượng xác nhận (±5)
    if vol_ratio >= 1.5 and last["c"] != last["o"]:
        up = last["c"] > last["o"]
        trend("Khối lượng", 5 if up else -5,
              f"nến {'tăng' if up else 'giảm'} với khối lượng gấp {vol_ratio:.1f} lần TB20")
    else:
        add("Khối lượng", 0, f"khối lượng bình thường ({vol_ratio:.1f} lần TB20)")

    # 8. Xác nhận đảo chiều sau quá bán/quá mua (±25 mỗi dấu hiệu, tối đa ±50)
    if zone:
        if confirms:
            add("Xác nhận đảo chiều", zone * min(50, 25 * len(confirms)), "; ".join(confirms))
        else:
            wait = ("nến tăng đóng trên đỉnh nến trước, hoặc RSI quay lên" if zone > 0
                    else "nến giảm đóng dưới đáy nến trước, hoặc RSI quay xuống")
            add("Xác nhận đảo chiều", 0, f"chưa có — chờ {wait}")

    return _finish({"symbol": symbol, "tf": tf, "candle": last["t"], "price": price, "parts": parts,
                    "zone": zone, "in_zone": in_zone, "ema_trend": ema_trend, "atr": atr, "rsi": r, "adx": adx,
                    "swing_low": min(c["l"] for c in closed[-10:]), "swing_high": max(c["h"] for c in closed[-10:])})


def apply_context(items):
    """Khung nhỏ (dưới 1d) được cộng/trừ 8 điểm theo xu hướng EMA của khung ngày: thuận khung lớn thì đáng tin hơn."""
    daily = {i["symbol"]: i for i in items if i["tf"] == "1d"}
    for it in items:
        d = daily.get(it["symbol"])
        if not d or it["tf"] == "1d" or any(p["name"] == "Khung 1d" for p in it["parts"]):
            continue
        t = d["ema_trend"]
        note = {1: "khung ngày đang tăng: ưu tiên mua nhịp điều chỉnh",
                -1: "khung ngày đang giảm: mua chỉ là đánh hồi, nên đi khối lượng nhỏ",
                0: "khung ngày chưa rõ xu hướng"}[t]
        it["parts"].append({"name": "Khung 1d", "points": 8 * t, "note": note})
        _finish(it)
    return items


def overall(items):
    """Điểm tổng hợp mỗi coin: trung bình có trọng số theo khung (khung lớn nặng hơn).
    Nếu khung 4h hoặc 1d đang quá bán/quá mua thì tổng hợp cũng không gợi ý đuổi theo."""
    out = {}
    for sym in dict.fromkeys(i["symbol"] for i in items):
        rows = [i for i in items if i["symbol"] == sym]
        w = sum(TF_WEIGHT.get(i["tf"], 1) for i in rows)
        score = round(sum(i["score"] * TF_WEIGHT.get(i["tf"], 1) for i in rows) / w)
        zones = {i["zone"] for i in rows if i["zone"] and TF_WEIGHT.get(i["tf"], 1) >= 2}
        zone = zones.pop() if len(zones) == 1 else 0
        out[sym] = {"score": score, "rating": rating_of(score, zone)}
    return out


def decide_advice(items, state, now=None):
    """Trả về (gợi ý cần gửi, state mới).

    Gửi khi 1 coin + khung chuyển sang MUA / BÁN / CANH MUA / CANH BÁN, hoặc nâng lên mức mạnh.
    Đã ở MUA/BÁN thì giữ trạng thái cho tới khi điểm lùi qua ngưỡng HOLD; "canh" chỉ nhắc lại sau WATCH_GAP nến.
    """
    now = now or datetime.now(timezone.utc)
    state = dict(state)
    alerts = []
    for it in items:
        key = f"advice|{it['symbol']}|{it['tf']}"
        old = state.get(key) or {}
        prev = old.get("rating", "neutral")
        rating = it["rating"]
        if rating == "neutral" and direction(prev) * it["score"] >= HOLD:
            rating = "buy" if direction(prev) > 0 else "sell"      # vẫn giữ hướng cũ
        entry = {"rating": rating, "candle": it["candle"]}
        if "watch_candle" in old:
            entry["watch_candle"] = old["watch_candle"]
        changed = rating != "neutral" and _group(rating) != _group(prev)
        escalated = rating.startswith("strong") and not prev.startswith("strong")
        if changed and rating.startswith("watch"):
            last_watch = old.get("watch_candle")
            changed = (last_watch is None
                       or (it["candle"] - last_watch) / TF_MS.get(it["tf"], 3_600_000) >= WATCH_GAP)
            if changed:
                entry["watch_candle"] = it["candle"]
        if changed or escalated:
            alerts.append({**it, "type": "advice", "ts": int(now.timestamp()),
                           "time": now.astimezone(VN).strftime("%Y-%m-%d %H:%M")})
        state[key] = entry
    return alerts, state


def levels(a):
    """Mức tham khảo. Cắt lỗ 1.5 ATR, chốt lời 1.5 và 3 ATR.
    Lệnh đảo chiều (mua sau quá bán / bán sau quá mua): cắt lỗ đặt ngoài đáy/đỉnh 10 nến gần nhất 0.5 ATR."""
    sign = direction(a["rating"])
    sl = a["price"] - sign * 1.5 * a["atr"]
    if sign and a.get("zone") == sign:
        sl = a["swing_low"] - 0.5 * a["atr"] if sign > 0 else a["swing_high"] + 0.5 * a["atr"]
    return {"sl": sl, "tp1": a["price"] + sign * 1.5 * a["atr"], "tp2": a["price"] + sign * 3 * a["atr"]}


def format_advice(a, summary):
    coin = a["symbol"].replace("USDT", "")
    top = sorted((p for p in a["parts"] if p["points"]), key=lambda p: -abs(p["points"]))[:4]
    lines = [f"{ICON[a['rating']]} {coin} {a['tf']} — {LABEL[a['rating']]} (điểm {a['score']:+d}/100)",
             f"Giá đóng nến {fmt_price(a['price'])}"]
    lines += [f"{'＋' if p['points'] > 0 else '－'} {p['name']}: {p['note']}" for p in top]
    if a["rating"] == "watch_buy":
        lines.append("👉 Không bán đuổi lúc này. Chưa vội mua: chờ nến tăng đóng trên đỉnh nến trước hoặc RSI quay lên, "
                     "bot sẽ báo NÊN MUA khi có xác nhận.")
    elif a["rating"] == "watch_sell":
        lines.append("👉 Không mua đuổi lúc này. Đang giữ thì canh chốt lời: chờ nến giảm đóng dưới đáy nến trước "
                     "hoặc RSI quay xuống, bot sẽ báo NÊN BÁN khi có xác nhận.")
    else:
        lv = levels(a)
        lines.append(f"Tham khảo: cắt lỗ {fmt_price(lv['sl'])} | chốt lời {fmt_price(lv['tp1'])} / {fmt_price(lv['tp2'])}")
        if a.get("zone") == direction(a["rating"]) and a.get("ema_trend") == -a["zone"]:
            lines.append("⚠️ Lệnh đảo chiều ngược xu hướng chính: đi khối lượng nhỏ, giữ đúng cắt lỗ.")
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
    short = {"strong_buy": "MUA mạnh", "buy": "MUA", "watch_buy": "canh mua",
             "watch_sell": "canh bán", "sell": "BÁN", "strong_sell": "BÁN mạnh"}
    names = [f"{a['symbol'].replace('USDT', '')} {a['tf']} {short[a['rating']]}" for a in alerts]
    more = f" (+{len(names) - 3})" if len(names) > 3 else ""
    return "[Trading] Gợi ý: " + ", ".join(names[:3]) + more
