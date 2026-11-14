"""Review hằng tuần: Claude CLI đọc thống kê, viết báo cáo và đề xuất chỉnh tham số (người dùng duyệt).

Chạy: python -m bot.review   (cần lệnh `claude` và CLAUDE_CODE_OAUTH_TOKEN hoặc ANTHROPIC_API_KEY)
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

from . import advisor, params, stats
from .config import Config, load_dotenv
from .notify import notify
from .signals import VN

MIN_RESOLVED = 30          # chưa đủ số tín hiệu đã có kết quả thì không đề xuất chỉnh
MAX_STEP = 0.3             # mỗi lần đổi tối đa ±30%
KEEP = 12                  # số báo cáo giữ lại
SCHEMA = {
    "type": "object",
    "properties": {
        "report": {"type": "string"},
        "changes": {"type": "array", "items": {
            "type": "object",
            "properties": {"param": {"type": "string", "enum": sorted(params.SPEC)},
                           "value": {"type": "number"}, "reason": {"type": "string"}},
            "required": ["param", "value", "reason"]}},
    },
    "required": ["report", "changes"],
}


def build_prompt(st, p, signals):
    spec = {k: {**v, "current": p[k]} for k, v in params.SPEC.items()}
    can_change = st["resolved"] >= MIN_RESOLVED
    return f"""Bạn là chuyên gia phân tích kỹ thuật crypto, đang đánh giá một bot gợi ý mua/bán BTC, ETH, SOL, SUI
trên khung 1h, 4h, 1d. Trả lời bằng tiếng Việt có dấu.

Cách bot chấm điểm (−100..+100, chỉ dùng nến đã đóng): EMA 20/50/200 (±30), MACD (±20), ADX/DI (±15),
RSI (±15), Stoch RSI (±10), Bollinger %B (±10), khối lượng (±5), xác nhận đảo chiều sau quá bán/quá mua (±50),
xu hướng khung 1d cho khung nhỏ (±8). Mỗi chỉ báo nhân trọng số w_*. Điểm ≥ weak là NÊN MUA, ≥ strong là mạnh
(âm là BÁN). Khi RSI ≤ rsi_low bot không bao giờ báo BÁN mà báo CANH MUA, chờ xác nhận mới báo MUA
(RSI ≥ rsi_high thì ngược lại). Cắt lỗ/chốt lời = sl_atr / tp1_atr / tp2_atr lần ATR.

Cách chấm đúng/sai: ĐÚNG (win) nếu chạm chốt lời 1 trước cắt lỗ trong 24 nến, SAI (loss) nếu chạm cắt lỗ trước
(nến chạm cả hai tính sai), HẾT HẠN (expired) nếu sau 24 nến chưa chạm. pnl_pct là % lãi/lỗ lúc thoát.
win_rate = win / (win + loss). Trong "indicators": agree = chỉ báo cùng chiều lệnh, against = ngược chiều.
"kind": trend = thuận xu hướng, reversal = lệnh đảo chiều sau quá bán/quá mua. CANH MUA/BÁN ("watch") chấm theo
giá sau 12 nến. Lưu ý tỉ lệ hoà vốn: với chốt lời {p['tp1_atr']} ATR và cắt lỗ {p['sl_atr']} ATR, cần win_rate
khoảng {p['sl_atr'] / (p['sl_atr'] + p['tp1_atr']):.0%} mới hoà vốn.

THỐNG KÊ (JSON):
{json.dumps(st, ensure_ascii=False)}

THAM SỐ HIỆN TẠI (current) VÀ GIỚI HẠN (min/max):
{json.dumps(spec, ensure_ascii=False)}

YÊU CẦU:
1. "report": báo cáo ngắn gọn (tối đa khoảng 1500 ký tự, văn bản thường, không markdown bảng) gồm: tổng quan
   hiệu quả; nhóm nào đang tốt/kém (coin, khung, loại tín hiệu, khoảng điểm); chỉ báo nào đang giúp hay đang hại;
   vì sao các lệnh thua gần đây thua; lời khuyên dùng tín hiệu cho người dùng. Nói rõ khi mẫu còn quá ít để kết luận
   (nhóm dưới ~10 lệnh chỉ nên coi là dấu hiệu).
2. "changes": {"đề xuất chỉnh tham số" if can_change else "PHẢI để mảng rỗng vì mới có " + str(st["resolved"]) + " tín hiệu đã có kết quả (cần " + str(MIN_RESOLVED) + ")"}.
   Mỗi thay đổi: chỉ dùng tên tham số trong danh sách, giá trị trong [min, max], đổi tối đa ±30% so với current,
   giữ hold < weak < strong, rsi_low < rsi_high, tp1_atr < tp2_atr. Chỉ đề xuất khi số liệu đủ rõ, tối đa 4 thay đổi,
   "reason" dẫn số liệu cụ thể. Không có gì đáng đổi thì để mảng rỗng.
"""


def call_claude(prompt):
    cmd = ["claude", "-p", "--tools", "", "--output-format", "json", "--json-schema", json.dumps(SCHEMA)]
    if os.environ.get("CLAUDE_MODEL"):
        cmd += ["--model", os.environ["CLAUDE_MODEL"]]
    try:
        r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=900)
    except FileNotFoundError:
        raise RuntimeError("chưa cài Claude CLI (npm i -g @anthropic-ai/claude-code)") from None
    if r.returncode and not r.stdout.strip():
        raise RuntimeError(f"claude thoát mã {r.returncode}: {(r.stderr or '').strip()[:300]}")
    return r.stdout


def _json_in(text):
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        raise ValueError("không tìm thấy JSON trong câu trả lời của Claude")
    return json.loads(m.group(0))


def parse(output):
    """Lấy {report, changes} từ kết quả `claude -p --output-format json` (hoặc văn bản có JSON)."""
    try:
        data = json.loads(output)
    except (json.JSONDecodeError, TypeError):
        data = _json_in(output)
    if isinstance(data, dict) and data.get("is_error"):
        raise ValueError(f"Claude báo lỗi: {str(data.get('result'))[:300]}")
    if isinstance(data, dict) and isinstance(data.get("structured_output"), dict):
        data = data["structured_output"]
    elif isinstance(data, dict) and "report" not in data and isinstance(data.get("result"), str):
        data = _json_in(data["result"])
    if not isinstance(data, dict) or not isinstance(data.get("report"), str):
        raise ValueError("câu trả lời của Claude thiếu trường report")
    data.setdefault("changes", [])
    return data


def check(changes, p, resolved):
    """Tách đề xuất hợp lệ / bị loại. Trả về (accepted, rejected)."""
    accepted, rejected = [], []

    def reject(c, why):
        rejected.append({"param": c.get("param"), "value": c.get("value"), "reason": c.get("reason", ""), "why": why})

    for c in changes if isinstance(changes, list) else []:
        key, value = c.get("param"), c.get("value")
        if resolved < MIN_RESOLVED:
            reject(c, f"Chưa đủ {MIN_RESOLVED} tín hiệu đã có kết quả (mới có {resolved})")
        elif key not in params.SPEC:
            reject(c, "tham số không có trong danh sách cho phép")
        elif isinstance(value, bool) or not isinstance(value, (int, float)):
            reject(c, "giá trị không phải số")
        elif any(a["param"] == key for a in accepted):
            reject(c, "trùng tham số")
        else:
            s, old = params.SPEC[key], p[key]
            value = round(float(value), 2)
            limit = MAX_STEP * (abs(old) if old else s["max"] - s["min"])
            if not s["min"] <= value <= s["max"]:
                reject(c, f"ngoài khoảng [{s['min']}, {s['max']}]")
            elif abs(value - old) > limit + 1e-9:
                reject(c, f"đổi quá ±{MAX_STEP:.0%}")
            elif value == old:
                reject(c, "không đổi")
            else:
                accepted.append({"param": key, "old": old, "new": value, "reason": c.get("reason", "")})
    errors = params.validate({**p, **{a["param"]: a["new"] for a in accepted}})
    if errors:
        for a in accepted:
            rejected.append({"param": a["param"], "value": a["new"], "reason": a["reason"],
                             "why": "cả bộ đề xuất sai ràng buộc: " + "; ".join(errors)})
        accepted = []
    return accepted, rejected


def _pct(x):
    return "—" if x is None else f"{x:.0%}"


def summary_text(st):
    o = st["overall"]
    lines = [f"Đã chấm {st['resolved']} tín hiệu: {o['win']} đúng, {o['loss']} sai, {o['expired']} hết hạn "
             f"(tỉ lệ đúng {_pct(o['win_rate'])}, lãi/lỗ TB {o['avg_pnl'] if o['avg_pnl'] is not None else '—'}%)."]
    for title, key in (("Theo khung", "by_tf"), ("Theo coin", "by_symbol")):
        g = st[key]
        if g:
            lines.append(f"{title}: " + ", ".join(f"{k} {_pct(v['win_rate'])} ({v['n']})" for k, v in g.items()))
    if st["watch"]["n"]:
        lines.append(f"Canh mua/bán: {st['watch']['right']}/{st['watch']['n']} đi đúng hướng sau 12 nến.")
    lines.append(f"Đang chờ kết quả: {st['pending']}.")
    return "\n".join(lines)


def _load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def run(cfg):
    hist = _load(cfg.data_dir / "advice_signals.json", [])
    st = stats.build(hist)
    p = dict(advisor.PARAMS)
    now = datetime.now(timezone.utc).astimezone(VN).strftime("%Y-%m-%d %H:%M")
    ok, error = True, ""
    try:
        data = parse(call_claude(build_prompt(st, p, hist)))
        report = data["report"].strip()
        accepted, rejected = check(data.get("changes"), p, st["resolved"])
    except Exception as e:
        ok, error, report, accepted, rejected = False, str(e), "", [], []
        print("LỖI AI review:", e, file=sys.stderr)
    entry = {"time": now, "ok": ok, "error": error, "report": report, "changes": accepted, "rejected": rejected,
             "resolved": st["resolved"], "params_id": params.pid(p), "summary": summary_text(st)}
    path = cfg.data_dir / "ai_review.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([entry] + _load(path, [])[:KEEP - 1], ensure_ascii=False, indent=1), encoding="utf-8")

    parts = [f"🤖 Báo cáo AI về tín hiệu — {now} (giờ VN)", entry["summary"]]
    parts.append(report if ok else f"⚠️ Không gọi được AI ({error[:200]}). Đây chỉ là số liệu thống kê.")
    if accepted:
        parts.append("Đề xuất chỉnh (chưa áp dụng, cần bạn duyệt):\n" +
                     "\n".join(f"• {a['param']}: {a['old']:g} → {a['new']:g} — {a['reason']}" for a in accepted))
    if cfg.dashboard_url:
        parts.append(f"Xem chi tiết và duyệt: {cfg.dashboard_url.rstrip('/')}/signals.html#ai")
    text = "\n\n".join(parts)
    print(text)
    sent, errors, _ = notify(cfg, "[Trading] Báo cáo AI về tín hiệu", text)
    for name, err in errors.items():
        print(f"LỖI gửi {name}: {err}", file=sys.stderr)
    return 0 if ok else 1


def main():
    from .__main__ import apply_settings
    load_dotenv()
    sys.exit(run(apply_settings(Config())))


if __name__ == "__main__":
    main()
