"""Thống kê độ chính xác của các gợi ý đã chấm (xem bot/evaluate.py)."""
from .advisor import direction

TRADE = ("win", "loss", "expired")


def _group(rows):
    win = sum(r["outcome"] == "win" for r in rows)
    loss = sum(r["outcome"] == "loss" for r in rows)
    pnl = [r["pnl_pct"] for r in rows if r.get("pnl_pct") is not None]
    return {"n": len(rows), "win": win, "loss": loss, "expired": len(rows) - win - loss,
            "win_rate": round(win / (win + loss), 3) if win + loss else None,
            "avg_pnl": round(sum(pnl) / len(pnl), 2) if pnl else None}


def _by(rows, key):
    keys = sorted({key(r) for r in rows}, key=str)
    return {k: _group([r for r in rows if key(r) == k]) for k in keys}


def _bucket(score):
    s = abs(score)
    return "65+" if s >= 65 else "50-64" if s >= 50 else "35-49" if s >= 35 else "20-34"


def build(signals):
    advice = [s for s in signals if s.get("type") == "advice"]
    trades = [s for s in advice if s.get("outcome") in TRADE]
    watch = [s for s in advice if s.get("outcome") in ("right", "wrong")]
    indicators = {}
    for name in sorted({p["name"] for s in trades for p in s.get("parts", [])}):
        side = {"agree": [], "against": [], "neutral": []}
        for s in trades:
            pts = next((p["points"] for p in s.get("parts", []) if p["name"] == name), None)
            if pts is not None:
                v = pts * direction(s["rating"])
                side["agree" if v > 0 else "against" if v < 0 else "neutral"].append(s)
        indicators[name] = {k: _group(v) for k, v in side.items()}
    right = sum(s["outcome"] == "right" for s in watch)
    losses = [s for s in trades if s["outcome"] == "loss"][-15:]
    return {
        "resolved": len(trades),
        "pending": sum(not s.get("outcome") for s in advice),
        "skipped": sum(s.get("outcome") == "skip" for s in advice),
        "overall": _group(trades),
        "by_symbol": _by(trades, lambda s: s["symbol"].replace("USDT", "")),
        "by_tf": _by(trades, lambda s: s["tf"]),
        "by_rating": _by(trades, lambda s: s["rating"]),
        "by_kind": _by(trades, lambda s: "reversal" if s.get("zone") and s["zone"] == direction(s["rating"])
                       else "trend"),
        "by_score": _by(trades, lambda s: _bucket(s["score"])),
        "by_params": _by(trades, lambda s: s.get("params_id") or "cũ"),
        "indicators": indicators,
        "watch": {"n": len(watch), "right": right, "wrong": len(watch) - right,
                  "right_rate": round(right / len(watch), 3) if watch else None},
        "recent_losses": [{"time": s.get("time"), "symbol": s["symbol"], "tf": s["tf"], "rating": s["rating"],
                           "score": s["score"], "pnl_pct": s.get("pnl_pct"),
                           "parts": [f"{p['name']} {p['points']:+g}" for p in s.get("parts", []) if p["points"]]}
                          for s in losses],
    }
