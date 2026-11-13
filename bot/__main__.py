"""Chạy: python -m bot [--loop GIÂY] [--dry-run] [--test]"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

from .advisor import advice_subject, advise, apply_context, decide_advice, format_advice_message, levels, overall
from .config import Config, load_dotenv
from .market import fetch_klines
from .notify import discover_chat_ids, notify
from .signals import analyze, decide, format_message, subject

MAX_SIGNALS = 500


def _load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def apply_settings(cfg, path=None):
    """Dòng `channels=` trong settings.properties được ưu tiên hơn biến CHANNELS."""
    path = Path(path or os.environ.get("SETTINGS_FILE") or "settings.properties")
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return cfg
    for line in lines:
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() == "channels":
            cfg.channels = [c.strip().lower() for c in value.split(",") if c.strip()]
    return cfg


def _send(cfg, subj, text):
    """Gửi và in kết quả. Trả về (có nên lưu state không, có lỗi không)."""
    ok, errors, configured = notify(cfg, subj, text)
    for name, err in errors.items():
        print(f"LỖI gửi {name}: {err}", file=sys.stderr)
    if not cfg.channels:
        print("Đang tắt mọi kênh gửi, tín hiệu chỉ được lưu lại.")
    elif not configured:
        print("CẢNH BÁO: chưa kênh nào được chọn có đủ token, tín hiệu chỉ được lưu lại.", file=sys.stderr)
    if configured and not ok:
        return False, True  # không lưu state để lượt sau gửi lại
    print("Đã gửi qua:", ", ".join(ok) or "(không kênh nào)")
    return True, bool(errors)


def _scan_bands(cfg, statuses, dry_run):
    for s in statuses:
        tag = f"{s['level']} {s['side']}" if s["side"] else "-"
        print(f"{s['symbol']:9} {s['tf']:3} giá={s['price']:<12g} %B={s['pctb']:.2f} "
              f"RSI={s['rsi'] or 0:.0f} {tag}{' squeeze' if s['squeeze'] else ''}")
    state_path, sig_path = cfg.data_dir / "state.json", cfg.data_dir / "signals.json"
    alerts, new_state = decide(statuses, _load(state_path, {}))
    if not alerts:
        print("Không có tín hiệu Bollinger mới.")
        if not dry_run:
            _save(state_path, new_state)
        return 0
    text = format_message(alerts, cfg)
    print("\n" + text + "\n")
    if dry_run:
        return 0
    saved, had_error = _send(cfg, subject(alerts), text)
    if saved:
        _save(state_path, new_state)
        _save(sig_path, (_load(sig_path, []) + alerts)[-MAX_SIGNALS:])
    return 1 if had_error else 0


def _scan_advice(cfg, items, dry_run):
    """Gợi ý mua/bán: lưu ảnh chụp mới nhất cho trang signals.html và gửi khi có thay đổi."""
    summary = overall(apply_context(items))
    for it in items:
        print(f"{it['symbol']:9} {it['tf']:3} điểm={it['score']:+4d} {it['rating']}")
    state_path = cfg.data_dir / "state.json"
    alerts, new_state = decide_advice(items, _load(state_path, {}))
    for it in items + alerts:
        it.update(levels(it))
    text = format_advice_message(alerts, summary, cfg) if alerts else ""
    if text:
        print("\n" + text + "\n")
    else:
        print("Không có gợi ý mua/bán mới.")
    if dry_run:
        return 0
    # Ảnh chụp chỉ đổi khi có nến mới đóng nên nhánh data không bị commit liên tục.
    _save(cfg.data_dir / "advice.json", {"items": items, "overall": summary})
    if not alerts:
        _save(state_path, new_state)
        return 0
    saved, had_error = _send(cfg, advice_subject(alerts), text)
    if saved:
        hist_path = cfg.data_dir / "advice_signals.json"
        _save(state_path, new_state)
        _save(hist_path, (_load(hist_path, []) + alerts)[-MAX_SIGNALS:])
    return 1 if had_error else 0


def scan(cfg, dry_run=False, fetch=fetch_klines):
    """Quét 1 lượt. Trả về mã thoát (0 = ổn)."""
    need = max(cfg.bb_period + cfg.squeeze_lookback, 100)
    if cfg.advice:
        need = max(need, 300)
    statuses, items, failed = [], [], []
    for sym in cfg.symbols:
        for tf in cfg.timeframes:
            try:
                rows = fetch(sym, tf, need)
                statuses.append(analyze(sym, tf, rows, cfg))
            except Exception as e:
                failed.append(f"{sym} {tf}: {e}")
                continue
            if cfg.advice:
                try:
                    items.append(advise(sym, tf, rows, cfg))
                except Exception as e:
                    print(f"Bỏ qua gợi ý {sym} {tf}: {e}", file=sys.stderr)
    for f in failed:
        print("LỖI dữ liệu:", f, file=sys.stderr)
    if not statuses:
        return 1
    code = _scan_bands(cfg, statuses, dry_run)
    if items:
        code = max(code, _scan_advice(cfg, items, dry_run))
    return code


def main():
    load_dotenv()
    ap = argparse.ArgumentParser(description="Bot cảnh báo Bollinger Bands")
    ap.add_argument("--loop", type=int, metavar="GIÂY", help="quét lặp lại mỗi N giây")
    ap.add_argument("--dry-run", action="store_true", help="chỉ in ra, không gửi, không lưu")
    ap.add_argument("--test", action="store_true",
                    help="gửi 1 tin thử qua các kênh trong CHANNELS; kênh bot thiếu chat_id sẽ được nhắn chat_id")
    args = ap.parse_args()
    cfg = apply_settings(Config())

    if args.test:
        notes = discover_chat_ids(cfg)
        for n in notes:
            print(n)
        ok, errors, configured = notify(cfg, "[Trading] Tin thử", "✅ Bot cảnh báo Bollinger Bands đã kết nối.")
        print("Kênh được chọn:", ", ".join(cfg.channels), "| Gửi được:", ", ".join(ok) or "không")
        for name, err in errors.items():
            print(f"LỖI {name}: {err}", file=sys.stderr)
        sys.exit(0 if ok or (notes and not configured) else 1)
    if args.loop:
        while True:
            try:
                scan(cfg, args.dry_run)
            except Exception as e:
                print("LỖI:", e, file=sys.stderr)
            time.sleep(args.loop)
    sys.exit(scan(cfg, args.dry_run))


if __name__ == "__main__":
    main()
