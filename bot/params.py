"""Tham số gợi ý mua/bán chỉnh được: khai báo ở web/params-spec.json (dashboard dùng chung),
giá trị lưu ở các dòng `advice.<tên>=` trong settings.properties."""
import hashlib
import json
from pathlib import Path

SPEC = json.loads((Path(__file__).resolve().parent.parent / "web" / "params-spec.json").read_text(encoding="utf-8"))
DEFAULTS = {k: v["default"] for k, v in SPEC.items()}
WEIGHT_OF = {"ADX/DI": "w_adx", "EMA 20/50/200": "w_ema", "MACD": "w_macd", "RSI": "w_rsi",
             "Stoch RSI": "w_stoch", "Bollinger": "w_bb", "Khối lượng": "w_volume",
             "Xác nhận đảo chiều": "w_confirm", "Khung 1d": "w_daily"}


def load(text):
    """Đọc dòng `advice.<tên>=<số>`; tên lạ hoặc giá trị không phải số thì bỏ qua."""
    p = dict(DEFAULTS)
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("advice.") or "=" not in line:
            continue
        key, value = line[len("advice."):].split("=", 1)
        key = key.strip()
        if key in SPEC:
            try:
                p[key] = float(value)
            except ValueError:
                pass
    return p


def validate(p):
    """Danh sách lỗi (rỗng = hợp lệ)."""
    errors = [f"{k}={p[k]} ngoài khoảng [{s['min']}, {s['max']}]"
              for k, s in SPEC.items() if not s["min"] <= p.get(k, s["default"]) <= s["max"]]
    if not p["hold"] < p["weak"] < p["strong"]:
        errors.append("cần hold < weak < strong")
    if not p["rsi_low"] < p["rsi_high"]:
        errors.append("cần rsi_low < rsi_high")
    if not p["tp1_atr"] < p["tp2_atr"]:
        errors.append("cần tp1_atr < tp2_atr")
    return errors


def pid(p):
    """Mã ngắn của bộ tham số, để thống kê trước/sau khi đổi."""
    raw = json.dumps({k: float(p[k]) for k in sorted(SPEC)}, sort_keys=True)
    return hashlib.sha1(raw.encode()).hexdigest()[:8]
