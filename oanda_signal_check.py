import os
import requests


def _clean(s):
    return "".join(s.split())


SYMBOL = os.environ.get("SYMBOL", "EUR/USD")
INTERVAL = os.environ.get("INTERVAL", "15min")
STATE_FILE = "last_signal.txt"

TWELVEDATA_API_KEY = _clean(os.environ["TWELVEDATA_API_KEY"])
TELEGRAM_BOT_TOKEN = _clean(os.environ["TELEGRAM_BOT_TOKEN"])
TELEGRAM_CHAT_ID = _clean(os.environ["TELEGRAM_CHAT_ID"])


def fetch_closes(symbol, interval, outputsize=200):
    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol": symbol,
        "interval": interval,
        "outputsize": outputsize,
        "apikey": TWELVEDATA_API_KEY,
    }
    resp = requests.get(url, params=params, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    if data.get("status") == "error":
        raise RuntimeError(f"Twelve Data алдаа: {data.get('message')}")
    values = data["values"]
    closes = [float(v["close"]) for v in reversed(values)]
    return closes


def sma(values, period):
    out = [None] * len(values)
    for i in range(period - 1, len(values)):
        out[i] = sum(values[i - period + 1:i + 1]) / period
    return out


def ema(values, period):
    out = [None] * len(values)
    k = 2 / (period + 1)
    prev = None
    for i in range(len(values)):
        if i < period - 1:
            continue
        if prev is None:
            prev = sum(values[i - period + 1:i + 1]) / period
        else:
            prev = values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def rsi(values, period=14):
    out = [None] * len(values)
    gains, losses = 0.0, 0.0
    for i in range(1, len(values)):
        change = values[i] - values[i - 1]
        gain, loss = max(change, 0), max(-change, 0)
        if i <= period:
            gains += gain
            losses += loss
            if i == period:
                ag, al = gains / period, losses / period
                rs = 100.0 if al == 0 else ag / al
                out[i] = 100 - 100 / (1 + rs)
        else:
            gains = (gains * (period - 1) + gain) / period
            losses = (losses * (period - 1) + loss) / period
            rs = 100.0 if losses == 0 else gains / losses
            out[i] = 100 - 100 / (1 + rs)
    return out


def macd(values, fast=12, slow=26, signal_p=9):
    ef, es = ema(values, fast), ema(values, slow)
    macd_line = [(ef[i] - es[i]) if ef[i] is not None and es[i] is not None else None
                 for i in range(len(values))]
    first = next((i for i, v in enumerate(macd_line) if v is not None), None)
    if first is None:
        return macd_line, [None] * len(values)
    tail = [v for v in macd_line[first:] if v is not None]
    sig_tail = ema(tail, signal_p)
    signal_line = [None] * first + sig_tail
    hist = [(macd_line[i] - signal_line[i]) if macd_line[i] is not None and signal_line[i] is not None else None
            for i in range(len(values))]
    return macd_line, hist


def build_signal(closes):
    s20, s50 = sma(closes, 20), sma(closes, 50)
    r = rsi(closes, 14)
    _, hist = macd(closes)
    i = len(closes) - 1
    score = 0
    if s20[i] is not None and s50[i] is not None:
        score += 1 if s20[i] > s50[i] else -1
    if r[i] is not None:
        if r[i] < 30:
            score += 1
        elif r[i] > 70:
            score -= 1
    if hist[i] is not None:
        score += 1 if hist[i] > 0 else -1

    signal = "HOLD"
    if score >= 2:
        signal = "BUY"
    elif score <= -2:
        signal = "SELL"
    return signal, score, closes[i], r[i], hist[i]


def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    resp = requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": text}, timeout=15)
    resp.raise_for_status()


def read_last_signal():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return f.read().strip()
    return ""


def write_last_signal(signal):
    with open(STATE_FILE, "w") as f:
        f.write(signal)


def main():
    closes = fetch_closes(SYMBOL, INTERVAL)
    send_telegram("Test message ажиллаж байна")

    if len(closes) < 55:
        print("Дата хүрэлцэхгүй байна.")
        return

    signal, score, close, r, hist = build_signal(closes)
    last = read_last_signal()

    print(f"{SYMBOL} close={close:.5f} RSI={r:.1f} score={score:+d} -> {signal} (prev={last or '—'})")

    if signal != "HOLD" and signal != last:
        msg = (
            f"📊 {SYMBOL} ({INTERVAL})\n"
            f"Дохио: {signal}\n"
            f"Үнэ: {close:.5f}\n"
            f"RSI: {r:.1f}  MACD hist: {hist:.5f}\n"
            f"Score: {score:+d}/3"
        )
        send_telegram(msg)
        write_last_signal(signal)


if __name__ == "__main__":
    main()
