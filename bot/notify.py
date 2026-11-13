"""Gửi thông báo qua Telegram, Zalo Bot Platform và Gmail SMTP."""
import json
import smtplib
import urllib.error
import urllib.request
from email.message import EmailMessage

TELEGRAM_API = "https://api.telegram.org"
TELEGRAM_LIMIT = 4096
ZALO_API = "https://bot-api.zaloplatforms.com"
ZALO_LIMIT = 2000


def chunk(text, limit=ZALO_LIMIT):
    """Cắt tin dài theo đoạn (ngăn bởi dòng trống) để mỗi phần <= limit ký tự."""
    parts, cur = [], ""
    for block in text.split("\n\n"):
        while len(block) > limit:
            if cur:
                parts.append(cur)
                cur = ""
            parts.append(block[:limit])
            block = block[limit:]
        cand = f"{cur}\n\n{block}" if cur else block
        if len(cand) > limit:
            parts.append(cur)
            cur = block
        else:
            cur = cand
    if cur:
        parts.append(cur)
    return parts


def bot_call(api, token, method, body=None, timeout=40):
    """Gọi Bot API kiểu Telegram (Zalo Bot Platform dùng cùng dạng)."""
    req = urllib.request.Request(
        f"{api}/bot{token}/{method}",
        data=json.dumps(body or {}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        # Không đưa URL vào lỗi vì URL chứa token.
        raise RuntimeError(f"{method} lỗi HTTP {e.code}: {e.read().decode(errors='replace')[:200]}") from None
    if not data.get("ok"):
        raise RuntimeError(f"{method} lỗi: {data.get('description') or data}")
    return data.get("result")


def send_telegram(cfg, text):
    for part in chunk(text, TELEGRAM_LIMIT):
        bot_call(TELEGRAM_API, cfg.telegram_token, "sendMessage",
                 {"chat_id": cfg.telegram_chat_id, "text": part, "disable_web_page_preview": True})


def send_zalo(cfg, text):
    for part in chunk(text):
        bot_call(ZALO_API, cfg.zalo_token, "sendMessage", {"chat_id": cfg.zalo_chat_id, "text": part})


def discover_chat_ids(cfg):
    """Với kênh bot đã có token nhưng thiếu chat_id: đọc tin nhắn mới nhất gửi cho bot
    rồi nhắn chat_id vào chính cuộc trò chuyện đó (không in ra log công khai)."""
    notes = []
    bots = (("telegram", "Telegram", TELEGRAM_API, cfg.telegram_token, cfg.telegram_chat_id, "TELEGRAM_CHAT_ID"),
            ("zalo", "Zalo", ZALO_API, cfg.zalo_token, cfg.zalo_chat_id, "ZALO_CHAT_ID"))
    for key, name, api, token, chat_id, secret in bots:
        if key not in cfg.channels or not token or chat_id:
            continue
        try:
            upd = bot_call(api, token, "getUpdates", {"timeout": 20})
            items = upd if isinstance(upd, list) else [upd] if upd else []
            ids = {str(((u or {}).get("message") or {}).get("chat", {}).get("id", "")) for u in items} - {""}
            for cid in ids:
                bot_call(api, token, "sendMessage", {"chat_id": cid, "text": f"{secret} của bạn là: {cid}"})
            notes.append(f"{name}: đã nhắn {secret} vào {name} của bạn, hãy thêm nó vào Secrets." if ids
                         else f"{name}: chưa thấy tin nhắn nào. Hãy nhắn 1 tin cho bot rồi chạy lại.")
        except Exception as e:
            notes.append(f"{name}: lỗi lấy chat_id ({e})")
    return notes


def send_gmail(cfg, subject, text):
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg.gmail_user
    msg["To"] = cfg.email_to or cfg.gmail_user
    msg.set_content(text)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
        s.login(cfg.gmail_user, cfg.gmail_app_password.replace(" ", ""))
        s.send_message(msg)


def notify(cfg, subject, text):
    """Gửi qua các kênh được chọn trong CHANNELS và đã cấu hình đủ.

    Trả về (kênh gửi được, {kênh: lỗi}, kênh đã cấu hình).
    """
    available = {
        "telegram": ("Telegram", bool(cfg.telegram_token and cfg.telegram_chat_id), lambda: send_telegram(cfg, text)),
        "zalo": ("Zalo", bool(cfg.zalo_token and cfg.zalo_chat_id), lambda: send_zalo(cfg, text)),
        "gmail": ("Gmail", bool(cfg.gmail_user and cfg.gmail_app_password), lambda: send_gmail(cfg, subject, text)),
    }
    ok, errors, configured = [], {}, []
    for key in cfg.channels:
        if key not in available:
            errors[key] = "kênh không hợp lệ (chỉ nhận telegram, zalo, gmail)"
            continue
        name, ready, fn = available[key]
        if not ready:
            errors[name] = "đã chọn trong CHANNELS nhưng thiếu token/chat_id/mật khẩu"
            continue
        configured.append(name)
        try:
            fn()
            ok.append(name)
        except Exception as e:
            errors[name] = str(e)
    return ok, errors, configured
