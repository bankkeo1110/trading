import statistics
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from bot.__main__ import apply_settings, scan
from bot.advisor import advise, apply_context, decide_advice, format_advice_message, levels, overall, rating_of
from bot.config import Config
from bot.indicators import atr_adx, bollinger, ema_series, macd, rsi, rsi_series, stoch_rsi
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
    def test_properties_file_overrides_env(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "settings.properties"
            cfg = Config(channels=["telegram"])
            self.assertEqual(apply_settings(cfg, f).channels, ["telegram"])   # không có file
            f.write_text("# ghi chú\nchannels = Zalo, gmail\n", encoding="utf-8")
            self.assertEqual(apply_settings(cfg, f).channels, ["zalo", "gmail"])
            f.write_text("channels=\n", encoding="utf-8")
            self.assertEqual(apply_settings(cfg, f).channels, [])

    def test_repo_default_is_telegram(self):
        root = Path(__file__).resolve().parent.parent
        self.assertEqual(apply_settings(Config(channels=["zalo"]), root / "settings.properties").channels, ["telegram"])


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


def ohlc(closes, t0=1_700_000_000_000, step=3_600_000):
    """Nến có râu ±0.5% quanh giá đóng, giá mở = giá đóng nến trước; thêm 1 nến đang chạy ở cuối."""
    rows, prev = [], closes[0]
    for i, c in enumerate(closes + [closes[-1]]):
        rows.append({"t": t0 + i * step, "o": prev, "h": max(prev, c) * 1.005, "l": min(prev, c) * 0.995,
                     "c": c, "v": 100.0})
        prev = c
    return rows


def trend(n=300, step=0.002, wiggle=0.01):
    """Chuỗi giá đi theo 1 hướng (step > 0 tăng, < 0 giảm) kèm dao động nhỏ."""
    return [100 * (1 + step) ** i * (1 + wiggle * (1 if i % 3 == 0 else -0.5)) for i in range(n)]


class Advisor(unittest.TestCase):
    def setUp(self):
        self.cfg = Config()

    def test_indicator_series(self):
        xs = [float(i) for i in range(1, 61)]
        self.assertAlmostEqual(ema_series(xs, 10)[9], 5.5)            # khởi tạo bằng SMA
        self.assertAlmostEqual(ema_series(xs, 10)[-1], 55.5)          # chuỗi tuyến tính: EMA trễ (n-1)/2
        self.assertAlmostEqual(rsi_series(wave(101))[-1], rsi(wave(101)))
        m, sig, hist, prev = macd(xs)
        self.assertAlmostEqual(m, 7.0)                                # EMA12 - EMA26 = (25-11)/2
        self.assertAlmostEqual(hist, 0.0, places=6)
        atr, adx, pdi, mdi = atr_adx(ohlc(trend()))
        self.assertGreater(adx, 30)
        self.assertGreater(pdi, mdi)
        k, d, pk, pd = stoch_rsi(trend())
        self.assertTrue(0 <= k <= 100 and 0 <= d <= 100)

    def test_uptrend_is_buy_and_downtrend_is_sell(self):
        up = advise("BTCUSDT", "4h", ohlc(trend()), self.cfg)
        down = advise("BTCUSDT", "4h", ohlc(trend(step=-0.002)), self.cfg)
        self.assertIn(up["rating"], ("buy", "strong_buy"))
        self.assertEqual((up["ema_trend"], down["ema_trend"]), (1, -1))
        mixed = advise("BTCUSDT", "4h", ohlc(trend()[:-12] + [trend()[-13] * 0.97 ** i for i in range(1, 13)]), self.cfg)
        self.assertEqual(mixed["ema_trend"], 0)                       # giá rơi dưới EMA20/50 nhưng còn trên EMA200
        self.assertIn(down["rating"], ("sell", "strong_sell"))
        self.assertTrue(-100 <= down["score"] < 0 < up["score"] <= 100)
        lv = levels(up)
        self.assertTrue(lv["sl"] < up["price"] < lv["tp1"] < lv["tp2"])
        lv = levels(down)
        self.assertTrue(lv["sl"] > down["price"] > lv["tp1"] > lv["tp2"])

    def test_uses_closed_candles_only(self):
        rows = ohlc(trend())
        a = advise("BTCUSDT", "1h", rows, self.cfg)
        rows[-1]["c"] = 1                                             # nến đang chạy không ảnh hưởng
        self.assertEqual(advise("BTCUSDT", "1h", rows, self.cfg)["score"], a["score"])
        with self.assertRaises(ValueError):
            advise("BTCUSDT", "1h", ohlc(wave(100)), self.cfg)

    def item(self, score, tf="1h", zone=0, candle=1, ema_trend=0):
        return {"symbol": "BTCUSDT", "tf": tf, "candle": candle, "price": 100.0, "score": score, "zone": zone,
                "rating": rating_of(score, zone), "parts": [{"name": "MACD", "points": score, "note": "x"}],
                "atr": 2.0, "ema_trend": ema_trend, "swing_low": 95.0, "swing_high": 105.0}

    def crash(self, bounce=False):
        """Đi ngang rồi rơi mạnh 12 nến liền; bounce=True thêm 1 nến tăng đóng trên đỉnh nến trước."""
        import math
        xs = [100 + math.sin(i / 5) for i in range(288)]
        for _ in range(12):
            xs.append(xs[-1] * 0.985)
        rows = ohlc(xs)[:-1]
        if bounce:
            last = rows[-1]
            c = last["h"] * 1.01
            rows.append({"t": last["t"] + 3_600_000, "o": last["c"], "h": c * 1.002, "l": last["c"] * 0.999,
                         "c": c, "v": 100.0})
        return rows + [dict(rows[-1], t=rows[-1]["t"] + 3_600_000)]

    def test_oversold_is_never_sell(self):
        a = advise("BTCUSDT", "4h", self.crash(), self.cfg)
        self.assertLess(a["rsi"], 30)
        self.assertEqual((a["zone"], a["rating"]), (1, "watch_buy"))
        self.assertIn("chưa có", a["parts"][-1]["note"])
        text = format_advice_message(decide_advice([a], {})[0], {}, self.cfg)
        self.assertIn("QUÁ BÁN — CANH MUA", text)
        self.assertIn("Không bán đuổi", text)
        self.assertNotIn("cắt lỗ", text)

    def test_oversold_with_confirmation_is_buy(self):
        a = advise("BTCUSDT", "4h", self.crash(bounce=True), self.cfg)
        self.assertEqual(a["zone"], 1)
        self.assertIn(a["rating"], ("buy", "strong_buy"))
        self.assertIn("nến tăng đóng trên đỉnh nến trước", a["parts"][-1]["note"])
        lv = levels(a)
        self.assertLess(lv["sl"], a["swing_low"])                     # cắt lỗ dưới đáy gần nhất
        self.assertTrue(lv["sl"] < a["price"] < lv["tp1"] < lv["tp2"])
        self.assertIn("đảo chiều ngược xu hướng", format_advice_message(decide_advice([a], {})[0], {}, self.cfg))

    def test_overbought_is_never_buy(self):
        self.assertEqual(rating_of(70, -1), "watch_sell")
        self.assertEqual(rating_of(-30, -1), "sell")
        self.assertEqual(rating_of(-70, 1), "watch_buy")
        self.assertEqual(rating_of(30, 1), "buy")

    def test_daily_trend_context(self):
        items = apply_context([self.item(15, "1h"), self.item(40, "1d", ema_trend=1)])
        self.assertEqual((items[0]["score"], items[0]["rating"]), (23, "buy"))
        self.assertEqual(apply_context(items)[0]["score"], 23)        # không cộng 2 lần
        self.assertEqual(items[1]["score"], 40)

    def test_watch_alert_not_repeated(self):
        h = 3_600_000
        alerts, st = decide_advice([self.item(-40, zone=1, candle=h)], {})
        self.assertEqual([a["rating"] for a in alerts], ["watch_buy"])
        alerts, st = decide_advice([self.item(-40, zone=1, candle=2 * h)], st)
        self.assertEqual(alerts, [])
        alerts, st = decide_advice([self.item(0, candle=3 * h)], st)          # ra khỏi vùng
        alerts, st = decide_advice([self.item(-5, zone=1, candle=4 * h)], st)  # vào lại sớm: không nhắc
        self.assertEqual(alerts, [])
        alerts, st = decide_advice([self.item(30, zone=1, candle=5 * h)], st)  # có xác nhận: báo MUA
        self.assertEqual([a["rating"] for a in alerts], ["buy"])

    def test_alert_only_on_change(self):
        alerts, st = decide_advice([self.item(30)], {})
        self.assertEqual([a["rating"] for a in alerts], ["buy"])
        alerts, st = decide_advice([self.item(35)], st)               # vẫn MUA: không báo lại
        self.assertEqual(alerts, [])
        alerts, st = decide_advice([self.item(15)], st)               # lùi nhẹ: giữ MUA, không báo
        self.assertEqual((alerts, st["advice|BTCUSDT|1h"]["rating"]), ([], "buy"))
        alerts, st = decide_advice([self.item(25)], st)               # quay lại: không báo lại
        self.assertEqual(alerts, [])
        alerts, st = decide_advice([self.item(60)], st)               # nâng lên mạnh: báo
        self.assertEqual([a["rating"] for a in alerts], ["strong_buy"])
        alerts, st = decide_advice([self.item(0)], st)                # về trung lập: im lặng
        self.assertEqual(alerts, [])
        alerts, st = decide_advice([self.item(-30)], st)              # đảo chiều: báo
        self.assertEqual([a["rating"] for a in alerts], ["sell"])

    def test_overall_weights_higher_timeframes(self):
        o = overall([self.item(60, "1h"), self.item(-40, "1d")])
        self.assertEqual(o["BTCUSDT"]["score"], -15)                  # (60*1 - 40*3) / 4

    def test_message(self):
        alerts, _ = decide_advice([self.item(60)], {})
        text = format_advice_message(alerts, overall([self.item(60)]), Config(dashboard_url="https://x.vercel.app/"))
        self.assertIn("BTC 1h — NÊN MUA (mạnh)", text)
        self.assertIn("cắt lỗ 97.000", text)
        self.assertIn("không phải lời khuyên đầu tư", text)
        self.assertIn("https://x.vercel.app/signals.html", text)

    def test_scan_sends_advice_once(self):
        import json
        with tempfile.TemporaryDirectory() as d:
            cfg = Config(symbols=["BTCUSDT"], timeframes=["1h", "4h"], data_dir=Path(d), channels=[],
                         telegram_token="")
            fetch = lambda s, tf, n: ohlc(trend())
            self.assertEqual(scan(cfg, fetch=fetch), 0)
            self.assertEqual(scan(cfg, fetch=fetch), 0)
            hist = json.loads((Path(d) / "advice_signals.json").read_text(encoding="utf-8"))
            self.assertEqual(len(hist), 2)
            self.assertIn("sl", hist[0])
            snap = json.loads((Path(d) / "advice.json").read_text(encoding="utf-8"))
            self.assertEqual(len(snap["items"]), 2)
            self.assertIn("BTCUSDT", snap["overall"])
            cfg.advice = False
            (Path(d) / "advice.json").unlink()
            self.assertEqual(scan(cfg, fetch=fetch), 0)
            self.assertFalse((Path(d) / "advice.json").exists())


class Charts(unittest.TestCase):
    def alert(self):
        from bot.advisor import advise, decide_advice, levels
        rows = ohlc(trend())
        alerts, _ = decide_advice([advise("BTCUSDT", "4h", rows, Config())], {})
        alerts[0].update(levels(alerts[0]))
        return rows, alerts

    def test_chart_is_png_one_per_symbol_tf(self):
        from bot.chart import make_charts
        rows, alerts = self.alert()
        charts = make_charts(alerts + alerts, {("BTCUSDT", "4h"): rows}, Config())
        self.assertEqual(len(charts), 1)
        png, cap = charts[0]
        self.assertTrue(png.startswith(b"\x89PNG"))
        self.assertIn("BTC 4h — NÊN MUA", cap)
        self.assertEqual(make_charts(alerts, {}, Config()), [])       # không có nến thì không có ảnh

    def test_band_alert_chart(self):
        from bot.chart import make_charts
        rows = [{"t": i * 3_600_000, "o": c, "h": c + 1, "l": c - 1, "c": c, "v": 1.0} for i, c in enumerate(wave(160))]
        rows[-1]["c"] = 110
        alerts, _ = decide([analyze("ETHUSDT", "1h", rows, Config())], {})
        charts = make_charts(alerts, {("ETHUSDT", "1h"): rows}, Config())
        self.assertIn("ETH 1h — Chạm BB trên", charts[0][1])

    def send(self, photos, fail=False):
        import io, json
        calls = []

        def fake(req, timeout=0):
            if fail:
                raise OSError("mất mạng")
            calls.append((req.full_url.rsplit("/", 1)[1], req.data, req.headers["Content-type"]))
            return io.BytesIO(json.dumps({"ok": True, "result": {}}).encode())

        orig = notify_mod.urllib.request.urlopen
        notify_mod.urllib.request.urlopen = fake
        try:
            cfg = Config(channels=["telegram"], telegram_token="t", telegram_chat_id="42")
            return calls, notify(cfg, "s", "tin chữ", photos)
        finally:
            notify_mod.urllib.request.urlopen = orig

    def test_one_photo_and_album(self):
        calls, (ok, errors, _) = self.send([(b"PNG1", "BTC 4h")])
        self.assertEqual([c[0] for c in calls], ["sendMessage", "sendPhoto"])
        self.assertIn(b'name="photo"; filename="chart.png"', calls[1][1])
        self.assertIn("BTC 4h".encode(), calls[1][1])
        self.assertTrue(calls[1][2].startswith("multipart/form-data; boundary="))
        calls, _ = self.send([(b"PNG1", "a"), (b"PNG2", "b")])
        self.assertEqual([c[0] for c in calls], ["sendMessage", "sendMediaGroup"])
        self.assertIn(b"attach://p1", calls[1][1])
        self.assertIn(b"PNG2", calls[1][1])
        calls, _ = self.send([])
        self.assertEqual([c[0] for c in calls], ["sendMessage"])

    def test_photo_failure_does_not_fail_message(self):
        orig = notify_mod.send_telegram_photos
        notify_mod.send_telegram_photos = lambda cfg, photos: (_ for _ in ()).throw(RuntimeError("ảnh lỗi"))
        try:
            calls, (ok, errors, _) = self.send([(b"PNG1", "a")])
        finally:
            notify_mod.send_telegram_photos = orig
        self.assertEqual((ok, errors), (["Telegram"], {}))


class Params(unittest.TestCase):
    def tearDown(self):
        from bot import advisor
        advisor.configure({})

    def test_load_and_validate(self):
        from bot import params
        p = params.load("# x\nchannels=telegram\nadvice.strong=45\nadvice.w_ema=0.5\nadvice.la=3\nadvice.weak=abc\n")
        self.assertEqual((p["strong"], p["w_ema"], p["weak"]), (45.0, 0.5, 20))
        self.assertNotIn("la", p)
        self.assertEqual(params.validate(p), [])
        self.assertTrue(params.validate({**p, "hold": 25}))                 # hold phải < weak
        self.assertTrue(params.validate({**p, "tp1_atr": 3.5, "tp2_atr": 3}))
        self.assertTrue(params.validate({**p, "strong": 90}))               # ngoài max
        self.assertEqual(len(params.pid(p)), 8)
        self.assertNotEqual(params.pid(p), params.pid(params.load("")))

    def test_weights_and_thresholds_change_scores(self):
        from bot import advisor, params
        rows = ohlc(trend())
        base = advise("BTCUSDT", "4h", rows, Config())
        advisor.configure({"w_ema": 0})
        no_ema = advise("BTCUSDT", "4h", rows, Config())
        ema = next(p["points"] for p in base["parts"] if p["name"] == "EMA 20/50/200")
        self.assertEqual(next(p["points"] for p in no_ema["parts"] if p["name"] == "EMA 20/50/200"), 0)
        self.assertEqual(no_ema["score"], base["score"] - round(ema))
        advisor.configure({"strong": base["score"] - 1})
        self.assertEqual(advise("BTCUSDT", "4h", rows, Config())["rating"], "strong_buy")
        advisor.configure({})
        self.assertEqual(advise("BTCUSDT", "4h", rows, Config())["score"], base["score"])
        a = dict(base, rating="buy", zone=0)
        advisor.configure({"sl_atr": 2, "tp1_atr": 1, "tp2_atr": 4})
        lv = levels(a)
        self.assertAlmostEqual(lv["sl"], a["price"] - 2 * a["atr"])
        self.assertAlmostEqual(lv["tp2"], a["price"] + 4 * a["atr"])

    def test_settings_file_applies_params(self):
        from bot import advisor
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "settings.properties"
            f.write_text("channels=telegram\nadvice.rsi_low=25\nadvice.strong=60\n", encoding="utf-8")
            cfg = apply_settings(Config(), f)
        self.assertEqual((cfg.rsi_low, advisor.PARAMS["strong"]), (25, 60))
        alerts, _ = decide_advice([dict(Advisor.item(self, 70), params_id="x")], {})
        self.assertEqual(alerts[0]["params_id"], "x")
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "settings.properties"
            f.write_text("advice.hold=30\n", encoding="utf-8")             # sai ràng buộc: bỏ qua cả bộ
            apply_settings(Config(), f)
        self.assertEqual(advisor.PARAMS["hold"], 10)


if __name__ == "__main__":
    unittest.main()
