"""Phân tích trạng thái từng coin/khung và quyết định tín hiệu nào cần báo."""
from datetime import datetime, timedelta, timezone

from .indicators import bandwidths, bollinger, rsi

VN = timezone(timedelta(hours=7))
TV_INTERVAL = {"15m": "15", "30m": "30", "1h": "60", "2h": "120", "4h": "240", "1d": "D"}
LEVEL_RANK = {"near": 1, "touch": 2}


def analyze(symbol, tf, candles, cfg):
    """Trạng thái hiện tại của 1 coin trên 1 khung."""
    closes = [c["c"] for c in candles]
    price = closes[-1]
    mid, upper, lower = bollinger(closes, cfg.bb_period, cfg.bb_mult)
    width = upper - lower
    pctb = (price - lower) / width if width else 0.5
    side = level = None
    if pctb >= 1:
        side, level = "upper", "touch"
    elif pctb >= 1 - cfg.near:
        side, level = "upper", "near"
    elif pctb <= 0:
        side, level = "lower", "touch"
    elif pctb <= cfg.near:
        side, level = "lower", "near"
    bws = bandwidths(closes, cfg.bb_period, cfg.bb_mult, cfg.squeeze_lookback)
    squeeze = False
    if len(bws) >= 30:
        rank = sum(1 for b in bws if b < bws[-1]) / len(bws)
        median = sorted(bws)[len(bws) // 2]
        squeeze = rank <= cfg.squeeze_pct and bws[-1] <= cfg.squeeze_ratio * median
    return {
        "symbol": symbol, "tf": tf, "candle": candles[-1]["t"], "price": price,
        "mid": mid, "upper": upper, "lower": lower, "pctb": pctb,
        "rsi": rsi(closes, cfg.rsi_period), "side": side, "level": level, "squeeze": squeeze,
    }


def decide(statuses, state, now=None):
    """So với state cũ, trả về (danh sách tín hiệu mới, state mới).

    Quy tắc chống spam: mỗi coin + khung + phía band chỉ báo 1 lần mỗi nến;
    báo lại nếu nâng mức từ "gần chạm" lên "chạm". Squeeze chỉ báo lúc bắt đầu.
    """
    now = now or datetime.now(timezone.utc)
    state = dict(state)
    alerts = []
    for s in statuses:
        confluence = sorted(
            (o["tf"] for o in statuses
             if o["symbol"] == s["symbol"] and s["side"] and o["side"] == s["side"]),
            key=lambda tf: ["15m", "30m", "1h", "2h", "4h", "1d"].index(tf) if tf in TV_INTERVAL else 9,
        )
        base = {**s, "ts": int(now.timestamp()), "time": now.astimezone(VN).strftime("%Y-%m-%d %H:%M"),
                "confluence": confluence if len(confluence) > 1 else []}
        if s["side"]:
            key = f"{s['symbol']}|{s['tf']}|{s['side']}"
            prev = state.get(key)
            new_candle = not prev or prev["candle"] != s["candle"]
            escalated = prev and LEVEL_RANK[s["level"]] > LEVEL_RANK.get(prev.get("level"), 0)
            if new_candle or escalated:
                alerts.append({**base, "type": "band"})
                state[key] = {"candle": s["candle"], "level": s["level"]}
        sq_key = f"{s['symbol']}|{s['tf']}|squeeze"
        if s["squeeze"] and not state.get(sq_key):
            alerts.append({**base, "type": "squeeze", "side": None, "level": None, "confluence": []})
        state[sq_key] = bool(s["squeeze"])
    return alerts, state


def fmt_price(p):
    if p >= 1000:
        return f"{p:,.1f}"
    if p >= 100:
        return f"{p:,.2f}"
    if p >= 1:
        return f"{p:,.3f}"
    return f"{p:.5f}"


def tv_link(symbol, tf):
    return f"https://www.tradingview.com/chart/?symbol=BINANCE:{symbol}&interval={TV_INTERVAL.get(tf, '60')}"


def format_alert(a, cfg):
    coin = a["symbol"].replace("USDT", "")
    rsi_txt = "—" if a["rsi"] is None else f"{a['rsi']:.0f}"
    if a["type"] == "squeeze":
        bw = (a["upper"] - a["lower"]) / a["mid"] * 100
        return (f"🟡 {coin} {a['tf']} — BB CO HẸP (squeeze)\n"
                f"Giá {fmt_price(a['price'])} | Bề rộng dải {bw:.2f}% | RSI {rsi_txt}\n"
                f"Dải hẹp nhất trong {cfg.squeeze_lookback} nến, dễ sắp biến động mạnh.\n"
                f"{tv_link(a['symbol'], a['tf'])}")
    upper = a["side"] == "upper"
    band = a["upper"] if upper else a["lower"]
    dist = (a["price"] - band) / band * 100
    icon = "🔴" if upper else "🟢"
    verb = ("CHẠM" if a["pctb"] in (0, 1) else "VƯỢT") if a["level"] == "touch" else "GẦN CHẠM"
    lines = [
        f"{icon} {coin} {a['tf']} — {verb} BB {'TRÊN' if upper else 'DƯỚI'}",
        f"Giá {fmt_price(a['price'])} | BB {'trên' if upper else 'dưới'} {fmt_price(band)} ({dist:+.2f}%)",
    ]
    extra = f"RSI {rsi_txt}"
    if a["rsi"] is not None:
        if upper and a["rsi"] >= cfg.rsi_high:
            extra += " (quá mua)"
        elif not upper and a["rsi"] <= cfg.rsi_low:
            extra += " (quá bán)"
    if a["squeeze"]:
        extra += " | dải đang co hẹp"
    lines.append(extra)
    if a["confluence"]:
        lines.append(f"⚡ Đồng thuận {len(a['confluence'])} khung: {', '.join(a['confluence'])}")
    lines.append(tv_link(a["symbol"], a["tf"]))
    return "\n".join(lines)


def format_message(alerts, cfg):
    head = f"📊 Cảnh báo Bollinger Bands — {alerts[0]['time']} (giờ VN)"
    parts = [head] + [format_alert(a, cfg) for a in alerts]
    if cfg.dashboard_url:
        parts.append(f"Xem biểu đồ: {cfg.dashboard_url}")
    return "\n\n".join(parts)


def subject(alerts):
    names = []
    for a in alerts:
        coin = a["symbol"].replace("USDT", "")
        tag = "squeeze" if a["type"] == "squeeze" else ("BB trên" if a["side"] == "upper" else "BB dưới")
        names.append(f"{coin} {a['tf']} {tag}")
    more = f" (+{len(names) - 3})" if len(names) > 3 else ""
    return "[Trading] " + ", ".join(names[:3]) + more
