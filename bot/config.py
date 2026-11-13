"""Cấu hình đọc từ biến môi trường (GitHub Secrets/Variables hoặc file .env)."""
import os
from dataclasses import dataclass, field
from pathlib import Path


def load_dotenv(path=".env"):
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _list(name, default):
    return [x.strip() for x in (os.environ.get(name) or default).split(",") if x.strip()]


def _num(name, default, cast=float):
    return cast(os.environ.get(name) or default)


@dataclass
class Config:
    symbols: list = field(default_factory=lambda: _list("SYMBOLS", "BTCUSDT,ETHUSDT,SOLUSDT,SUIUSDT"))
    timeframes: list = field(default_factory=lambda: _list("TIMEFRAMES", "1h,4h,1d"))
    bb_period: int = field(default_factory=lambda: _num("BB_PERIOD", 20, int))
    bb_mult: float = field(default_factory=lambda: _num("BB_MULT", 2))
    # "Gần chạm" = giá nằm trong NEAR (tỉ lệ bề rộng dải) tính từ band. 0.10 = 10%.
    near: float = field(default_factory=lambda: _num("NEAR", 0.10))
    rsi_period: int = field(default_factory=lambda: _num("RSI_PERIOD", 14, int))
    rsi_high: float = field(default_factory=lambda: _num("RSI_HIGH", 70))
    rsi_low: float = field(default_factory=lambda: _num("RSI_LOW", 30))
    # Squeeze = bề rộng dải thuộc nhóm hẹp nhất SQUEEZE_PCT trong SQUEEZE_LOOKBACK nến
    # và nhỏ hơn SQUEEZE_RATIO lần mức trung vị.
    squeeze_lookback: int = field(default_factory=lambda: _num("SQUEEZE_LOOKBACK", 120, int))
    squeeze_pct: float = field(default_factory=lambda: _num("SQUEEZE_PCT", 0.05))
    squeeze_ratio: float = field(default_factory=lambda: _num("SQUEEZE_RATIO", 0.75))
    data_dir: Path = field(default_factory=lambda: Path(os.environ.get("DATA_DIR") or "data"))
    zalo_token: str = field(default_factory=lambda: os.environ.get("ZALO_BOT_TOKEN", ""))
    zalo_chat_id: str = field(default_factory=lambda: os.environ.get("ZALO_CHAT_ID", ""))
    gmail_user: str = field(default_factory=lambda: os.environ.get("GMAIL_USER", ""))
    gmail_app_password: str = field(default_factory=lambda: os.environ.get("GMAIL_APP_PASSWORD", ""))
    email_to: str = field(default_factory=lambda: os.environ.get("EMAIL_TO", ""))
    dashboard_url: str = field(default_factory=lambda: os.environ.get("DASHBOARD_URL", ""))
