"""Data layer: universe list + daily bars. Swap this file to change data source."""
import re
import time
import urllib.request
from pathlib import Path

import pandas as pd
import yfinance as yf

CACHE = Path(__file__).resolve().parent.parent / "cache"
SYMDIR = "https://www.nasdaqtrader.com/dynamic/SymDir/{}.txt"
SKIP_WORDS = ("warrant", " unit", " right", "preferred", "depositary", "notes due", "debenture",
              "% ", " etn", "trust preferred", "acquisition corp", " fund")


def _fetch(url):
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return r.read().decode()
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2 ** (attempt + 1))


def _clean(name):
    name = name.split(" - ")[0]
    for cut in (" Common Stock", " Class A", " Ordinary Shares", " Common Shares"):
        i = name.find(cut)
        if i > 0:
            name = name[:i]
    return name.strip().rstrip(",")


def load_universe():
    """US-listed common stocks from the exchanges' official symbol directory
    (Nasdaq, NYSE, NYSE American). ETFs, test issues, warrants, units etc. removed."""
    out = {}
    for fname, sym_col in (("nasdaqlisted", "Symbol"), ("otherlisted", "ACT Symbol")):
        lines = _fetch(SYMDIR.format(fname)).splitlines()
        head = lines[0].split("|")
        for line in lines[1:-1]:
            r = dict(zip(head, line.split("|")))
            sym, name = r[sym_col].strip(), r["Security Name"]
            if r.get("ETF") != "N" or r.get("Test Issue") != "N":
                continue
            if not re.fullmatch(r"[A-Z]{1,5}", sym):
                continue  # preferreds, units, share classes with odd symbols
            if fname == "nasdaqlisted" and len(sym) == 5 and sym[-1] in "WRUZ":
                continue  # Nasdaq warrant / right / unit suffixes
            if any(w in name.lower() for w in SKIP_WORDS):
                continue
            out[sym] = {"name": _clean(name)}
    return out


def download_bars(tickers, period="2y", batch=150):
    """Daily split/dividend-adjusted bars. Returns {ticker: DataFrame[O,H,L,C,V]}."""
    bars = {}
    tickers = list(tickers)
    for i in range(0, len(tickers), batch):
        chunk = tickers[i : i + batch]
        df = None
        for attempt in range(4):
            try:
                df = yf.download(chunk, period=period, interval="1d", auto_adjust=True,
                                 group_by="ticker", threads=True, progress=False)
                if df is not None and len(df):
                    break
            except Exception as e:  # rate limit / network
                print(f"  retry {attempt + 1}: {e}")
            time.sleep(2 ** (attempt + 1))
        if df is None or not len(df):
            continue
        for t in chunk:
            try:
                d = df[t][["Open", "High", "Low", "Close", "Volume"]].dropna()
            except KeyError:
                continue
            if len(d):
                bars[t] = d
        print(f"  bars {min(i + batch, len(tickers))}/{len(tickers)}", flush=True)
    return bars


def earnings_dates(tickers):
    """Next earnings date per ticker (best effort; Yahoo's dates are not reliable)."""
    from concurrent.futures import ThreadPoolExecutor

    today = pd.Timestamp.today().normalize().date()

    def one(t):
        try:
            cal = yf.Ticker(t).calendar
            ds = cal.get("Earnings Date") or []
            ds = [d for d in ds if d >= today]
            return t, (min(ds).isoformat() if ds else None)
        except Exception:
            return t, None

    with ThreadPoolExecutor(8) as ex:
        return dict(ex.map(one, tickers))
