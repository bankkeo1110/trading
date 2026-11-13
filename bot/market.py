"""Lấy nến giá spot: Binance (endpoint dữ liệu công khai), dự phòng OKX."""
import json
import urllib.parse
import urllib.request

UA = {"User-Agent": "trading-bb-alert/1.0"}
OKX_BAR = {"1h": "1H", "4h": "4H", "1d": "1Dutc", "15m": "15m", "30m": "30m", "2h": "2H"}


def _get(url, timeout=15):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return json.loads(r.read().decode())


def _binance(symbol, tf, limit):
    q = urllib.parse.urlencode({"symbol": symbol, "interval": tf, "limit": limit})
    rows = _get(f"https://data-api.binance.vision/api/v3/klines?{q}")
    return [{"t": int(r[0]), "o": float(r[1]), "h": float(r[2]), "l": float(r[3]),
             "c": float(r[4]), "v": float(r[5])} for r in rows]


def _okx(symbol, tf, limit):
    inst = symbol[:-4] + "-" + symbol[-4:] if symbol.endswith("USDT") else symbol
    q = urllib.parse.urlencode({"instId": inst, "bar": OKX_BAR[tf], "limit": min(limit, 300)})
    data = _get(f"https://www.okx.com/api/v5/market/candles?{q}")
    if data.get("code") != "0":
        raise RuntimeError(f"OKX lỗi: {data.get('msg')}")
    rows = sorted(data["data"], key=lambda r: int(r[0]))
    return [{"t": int(r[0]), "o": float(r[1]), "h": float(r[2]), "l": float(r[3]),
             "c": float(r[4]), "v": float(r[5])} for r in rows]


def fetch_klines(symbol, tf, limit=200):
    """Danh sách nến tăng dần theo thời gian; nến cuối là nến đang chạy."""
    errors = []
    for name, fn in (("Binance", _binance), ("OKX", _okx)):
        try:
            rows = fn(symbol, tf, limit)
            if rows:
                return rows
            errors.append(f"{name}: không có dữ liệu")
        except Exception as e:  # thử nguồn kế tiếp
            errors.append(f"{name}: {e}")
    raise RuntimeError(f"Không lấy được nến {symbol} {tf} ({'; '.join(errors)})")
