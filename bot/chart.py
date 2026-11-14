"""Vẽ ảnh biểu đồ gửi kèm tín hiệu Telegram: nến, Bollinger Bands, EMA 20/50/200, RSI.

Cần matplotlib (workflow tự cài). Thiếu thư viện thì bot vẫn gửi tin chữ như cũ.
"""
import io
from datetime import datetime

from .advisor import LABEL, direction
from .indicators import bollinger, ema_series, rsi_series
from .signals import VN, fmt_price

BARS = 90                              # số nến hiển thị
MAX_CHARTS = 10                        # Telegram cho tối đa 10 ảnh trong 1 album
BG, PANEL, GRID, TEXT, DIM = "#0e1116", "#161b22", "#262d38", "#e6e9ee", "#8b95a5"
UP, DOWN, WARN, BLUE = "#2fbf71", "#f0554d", "#e3b341", "#5b9dff"


def caption(a):
    """1 dòng mô tả dưới ảnh."""
    coin = a["symbol"].replace("USDT", "")
    if a["type"] == "advice":
        return f"{coin} {a['tf']} — {LABEL[a['rating']]} ({a['score']:+d}) · giá {fmt_price(a['price'])}"
    if a["type"] == "squeeze":
        return f"{coin} {a['tf']} — BB co hẹp · giá {fmt_price(a['price'])}"
    verb = "Chạm" if a["level"] == "touch" else "Gần chạm"
    return f"{coin} {a['tf']} — {verb} BB {'trên' if a['side'] == 'upper' else 'dưới'} · giá {fmt_price(a['price'])}"


def render(candles, a, cfg):
    """Trả về ảnh PNG (bytes) của 1 tín hiệu."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    closes = [c["c"] for c in candles]
    n = min(BARS, len(candles))
    start = len(candles) - n
    xs = range(n)
    view = candles[start:]
    bands = [bollinger(closes[:i + 1], cfg.bb_period, cfg.bb_mult) if i + 1 >= cfg.bb_period else None
             for i in range(start, len(candles))]
    rs = rsi_series(closes, cfg.rsi_period)[start:]

    fig, (ax, ax2) = plt.subplots(2, 1, figsize=(10, 6.4), dpi=110, sharex=True,
                                  gridspec_kw={"height_ratios": [3.4, 1], "hspace": 0.05})
    fig.patch.set_facecolor(BG)
    for axis in (ax, ax2):
        axis.set_facecolor(PANEL)
        axis.grid(color=GRID, linewidth=0.6)
        axis.tick_params(colors=DIM, labelsize=8, length=0)
        axis.yaxis.tick_right()
        for spine in axis.spines.values():
            spine.set_color(GRID)

    # Nến
    for x, c in zip(xs, view):
        color = UP if c["c"] >= c["o"] else DOWN
        ax.vlines(x, c["l"], c["h"], color=color, linewidth=0.9)
        ax.bar(x, abs(c["c"] - c["o"]) or c["c"] * 1e-5, bottom=min(c["o"], c["c"]), width=0.66, color=color)

    # Bollinger Bands + EMA
    bx = [x for x, b in zip(xs, bands) if b]
    if bx:
        mid, up, lo = zip(*[b for b in bands if b])
        ax.plot(bx, up, color=BLUE, linewidth=1)
        ax.plot(bx, lo, color=BLUE, linewidth=1)
        ax.plot(bx, mid, color=BLUE, linewidth=0.8, linestyle="--", alpha=0.7)
        ax.fill_between(bx, lo, up, color=BLUE, alpha=0.07)
    handles = []
    for period, color in ((20, "#f5a623"), (50, "#c678dd"), (200, "#e6e9ee")):
        e = ema_series(closes, period)[start:]
        pts = [(x, v) for x, v in zip(xs, e) if v is not None]
        if pts:
            handles += ax.plot(*zip(*pts), color=color, linewidth=1, alpha=0.9, label=f"EMA{period}")
    if handles:
        ax.legend(loc="upper left", fontsize=8, frameon=False, labelcolor=DIM, ncol=3)

    # Mức giá: giá hiện tại, và cắt lỗ / chốt lời nếu là gợi ý MUA/BÁN
    def level(y, color, label, style="--"):
        ax.axhline(y, color=color, linewidth=1, linestyle=style, alpha=0.9)
        ax.annotate(f"{label} {fmt_price(y)}", xy=(0, y), xycoords=("axes fraction", "data"), xytext=(4, 3),
                    textcoords="offset points", color=color, fontsize=8, fontweight="bold")

    level(a["price"], TEXT, "Giá", ":")
    if a["type"] == "advice" and direction(a["rating"]) and "sl" in a:
        level(a["sl"], DOWN, "Cắt lỗ")
        level(a["tp1"], UP, "Chốt lời 1")
        level(a["tp2"], UP, "Chốt lời 2")
        ys = [a["sl"], a["tp2"]] + [c["l"] for c in view] + [c["h"] for c in view]
        pad = (max(ys) - min(ys)) * 0.04
        ax.set_ylim(min(ys) - pad, max(ys) + pad)

    # RSI
    rx = [(x, v) for x, v in zip(xs, rs) if v is not None]
    if rx:
        ax2.plot(*zip(*rx), color="#c678dd", linewidth=1.2)
    for y, color in ((cfg.rsi_high, DOWN), (cfg.rsi_low, UP)):
        ax2.axhline(y, color=color, linewidth=0.8, linestyle="--", alpha=0.8)
    ax2.set_ylim(0, 100)
    ax2.set_yticks([cfg.rsi_low, 50, cfg.rsi_high])
    ax2.text(0.005, 0.86, f"RSI {cfg.rsi_period}", transform=ax2.transAxes, color=DIM, fontsize=8)

    # Trục thời gian (giờ VN)
    step = max(1, n // 8)
    ticks = list(range(0, n, step))
    fmt = "%d/%m" if a["tf"] == "1d" else "%d/%m %H:%M"
    ax2.set_xticks(ticks)
    ax2.set_xticklabels([datetime.fromtimestamp(view[i]["t"] / 1000, VN).strftime(fmt) for i in ticks])
    ax.set_xlim(-1, n + 1)

    color = TEXT
    if a["type"] == "advice":
        color = WARN if a["rating"].startswith("watch") else UP if direction(a["rating"]) > 0 else DOWN
    elif a["type"] == "band":
        color = DOWN if a["side"] == "upper" else UP
    fig.suptitle(caption(a), color=color, fontsize=12, fontweight="bold", x=0.02, y=0.975, ha="left")
    fig.text(0.98, 0.975, "Bollinger 20,2 · giờ VN · chỉ là gợi ý", color=DIM, fontsize=8, ha="right", va="top")
    fig.subplots_adjust(left=0.035, right=0.93, top=0.93, bottom=0.06)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=BG)
    plt.close(fig)
    return buf.getvalue()


def make_charts(alerts, candles_by, cfg):
    """[(png, chú thích)] cho các tín hiệu, mỗi coin + khung 1 ảnh. Lỗi vẽ thì bỏ qua ảnh đó."""
    out, seen = [], set()
    for a in alerts:
        key = (a["symbol"], a["tf"])
        if key in seen or key not in candles_by or len(out) >= MAX_CHARTS:
            continue
        seen.add(key)
        try:
            out.append((render(candles_by[key], a, cfg), caption(a)))
        except ImportError:
            print("Chưa cài matplotlib nên không gửi kèm ảnh biểu đồ (pip install matplotlib).")
            return []
        except Exception as e:
            print(f"Không vẽ được biểu đồ {a['symbol']} {a['tf']}: {e}")
    return out
