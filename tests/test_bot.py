import statistics
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from bot.__main__ import apply_settings, scan
from bot.config import Config
from bot.indicators import bollinger, rsi
from bot import notify as notify_mod
from bot.notify import chunk, notify
from bot.signals import analyze, decide, format_message, subject


def candles(closes, t0=1_700_000_000_000, step=3_600_000):
    return [{"t": t0 + i * step, "o": c, "h": c, "l": c, "c": c, "v": 1} for i, c in enumerate(closes)]


def wave(n=160, last=None):
    xs = [100 + (3 if i % 2 else -3) for i in range(n)]
    if last is not None:
        xs[-1] = last
    return xs


class Indicators(unittest.TestCase):
    def test_bollinger_matches_population_std(self):
        xs = [float(x) for x in range(1, 41)]
        mid, up, lo = bollinger(xs, 20, 2)
        w = xs[-20:]
        self.assertAlmostEqual(mid, statistics.fmean(w))
        self.assertAlmostEqual(up, mid + 2 * statistics.pstdev(w))
        self.assertAlmostEqual(lo, mid - 2 * statistics.pstdev(w))

    def test_rsi_extremes(self):
        self.assertEqual(rsi([float(i) for i in range(50)]), 100.0)
        self.assertAlmostEqual(rsi([float(50 - i) for i in range(50)]), 0.0)
        self.assertAlmostEqual(rsi(wave(101)), 50, delta=5)
        self.assertIsNone(rsi([1.0, 2.0]))


class Signals(unittest.TestCase):
    def setUp(self):
        self.cfg = Config()

    def status(self, last, tf="1h", sym="BTCUSDT"):
        return analyze(sym, tf, candles(wave(last=last)), self.cfg)

    def test_levels(self):
        self.assertEqual((self.status(100)["side"], self.status(100)["level"]), (None, None))
        s = self.status(105.7)
        self.assertEqual((s["side"], s["level"]), ("upper", "near"))
        s = self.status(112)
        self.assertEqual((s["side"], s["level"]), ("upper", "touch"))
        s = self.status(94.3)
        self.assertEqual((s["side"], s["level"]), ("lower", "near"))
        s = self.status(88)
        self.assertEqual((s["side"], s["level"]), ("lower", "touch"))

    def test_dedup_and_escalation(self):
        near = self.status(105.7)
        alerts, state = decide([near], {})
        self.assertEqual(len(alerts), 1)
        alerts, state = decide([near], state)           # cùng nến, cùng mức -> im lặng
        self.assertEqual(alerts, [])
        alerts, state = decide([self.status(112)], state)  # nâng lên "chạm" -> báo lại
        self.assertEqual([a["level"] for a in alerts], ["touch"])
        alerts, state = decide([near], state)           # hạ mức trong cùng nến -> im lặng
        self.assertEqual(alerts, [])
        nxt = dict(near, candle=near["candle"] + 3_600_000)
        alerts, state = decide([nxt], state)            # nến mới -> báo
        self.assertEqual(len(alerts), 1)

    def test_confluence(self):
        alerts, _ = decide([self.status(88, "1h"), self.status(88, "4h"), self.status(100, "1d")], {})
        self.assertEqual(len(alerts), 2)
        self.assertEqual(alerts[0]["confluence"], ["1h", "4h"])
        self.assertIn("Đồng thuận 2 khung: 1h, 4h", format_message(alerts, self.cfg))

    def test_squeeze_alerts_once(self):
        closes = wave(150) + [100 + (0.05 if i % 2 else -0.05) for i in range(30)]
        s = analyze("SOLUSDT", "4h", candles(closes), self.cfg)
        self.assertTrue(s["squeeze"])
        alerts, state = decide([s], {})
        self.assertEqual([a["type"] for a in alerts], ["squeeze"])
        alerts, state = decide([dict(s, candle=s["candle"] + 1)], state)
        self.assertEqual(alerts, [])
        self.assertFalse(self.status(100)["squeeze"])

    def test_message(self):
        alerts, _ = decide([self.status(88, sym="SUIUSDT")], {}, datetime(2026, 11, 13, 1, 0, tzinfo=timezone.utc))
        text = format_message(alerts, self.cfg)
        self.assertIn("🟢 SUI 1h — VƯỢT BB DƯỚI", text)
        self.assertIn("2026-11-13 08:00 (giờ VN)", text)
        self.assertIn("BINANCE:SUIUSDT&interval=60", text)
        self.assertEqual(subject(alerts), "[Trading] SUI 1h BB dưới")


class Notify(unittest.TestCase):
    def test_chunk(self):
        text = "\n\n".join("x" * 900 for _ in range(5))
        parts = chunk(text)
        self.assertTrue(all(len(p) <= 2000 for p in parts))
        self.assertEqual("\n\n".join(parts), text)
        self.assertEqual([len(p) for p in chunk("y" * 4500)], [2000, 2000, 500])


class Channels(unittest.TestCase):
    def run_notify(self, **kw):
        sent = []
        cfg = Config(telegram_token="t", telegram_chat_id="1", zalo_token="z", zalo_chat_id="2",
                     gmail_user="a@b.c", gmail_app_password="p", **kw)
        orig = (notify_mod.send_telegram, notify_mod.send_zalo, notify_mod.send_gmail)
        notify_mod.send_telegram = lambda c, t: sent.append("telegram")
        notify_mod.send_zalo = lambda c, t: sent.append("zalo")
        notify_mod.send_gmail = lambda c, s, t: sent.append("gmail")
        try:
            return sent, notify(cfg, "s", "t")
        finally:
            notify_mod.send_telegram, notify_mod.send_zalo, notify_mod.send_gmail = orig

    def test_default_is_telegram_only(self):
        sent, (ok, errors, _) = self.run_notify()
        self.assertEqual((sent, ok, errors), (["telegram"], ["Telegram"], {}))

    def test_selected_channels(self):
        sent, (ok, _, _) = self.run_notify(channels=["zalo", "gmail"])
        self.assertEqual(sent, ["zalo", "gmail"])
        sent, (ok, errors, _) = self.run_notify(channels=["telegram", "sms"])
        self.assertEqual(sent, ["telegram"])
        self.assertIn("sms", errors)

    def test_selected_but_unconfigured(self):
        ok, errors, configured = notify(Config(channels=["telegram"], telegram_token="", telegram_chat_id=""), "s", "t")
        self.assertEqual((ok, configured), ([], []))
        self.assertIn("Telegram", errors)


class Settings(unittest.TestCase):
    def test_dashboard_settings_override_env(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = Config(channels=["telegram"], data_dir=Path(d))
            self.assertEqual(apply_settings(cfg).channels, ["telegram"])
            (Path(d) / "settings.json").write_text('{"channels": ["Zalo", "gmail"]}', encoding="utf-8")
            self.assertEqual(apply_settings(cfg).channels, ["zalo", "gmail"])
            (Path(d) / "settings.json").write_text('{"channels": []}', encoding="utf-8")
            self.assertEqual(apply_settings(cfg).channels, [])


class Scan(unittest.TestCase):
    def test_scan_saves_signals_once(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = Config(symbols=["BTCUSDT"], timeframes=["1h"], data_dir=Path(d), channels=[],
                         telegram_token="")
            fetch = lambda s, tf, n: candles(wave(last=112))
            self.assertEqual(scan(cfg, fetch=fetch), 0)
            self.assertEqual(scan(cfg, fetch=fetch), 0)
            import json
            sigs = json.loads((Path(d) / "signals.json").read_text(encoding="utf-8"))
            self.assertEqual(len(sigs), 1)
            self.assertEqual(sigs[0]["level"], "touch")


if __name__ == "__main__":
    unittest.main()
